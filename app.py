import base64
import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from urllib.parse import urlencode
from uuid import uuid4

import cv2
import numpy as np
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

# macOS + Homebrew: ayuda a pyzbar a encontrar libzbar.dylib
homebrew_lib = "/opt/homebrew/lib"
if os.path.isdir(homebrew_lib):
    actual = os.getenv("DYLD_FALLBACK_LIBRARY_PATH", "")
    if homebrew_lib not in actual.split(":"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{homebrew_lib}:{actual}" if actual else homebrew_lib

import qrcode

from pyzbar.pyzbar import decode

import firebase_admin
from firebase_admin import credentials, db
import yagmail

# Carga variables desde .env local (si existe)
load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cambia-esta-clave-en-produccion")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # En local HTTP, cookie debe viajar sin HTTPS obligatorio.
)

# =========================
# Config global
# =========================
SALT_SECRETO = os.getenv("QR_SALT_SECRETO", "CAMBIA_ESTE_SALT")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PASSWORD_HASH = hashlib.sha512((ADMIN_PASSWORD + SALT_SECRETO).encode("utf-8")).hexdigest()
PENDIENTES_FILE = os.getenv("PENDIENTES_FILE", "pendientes.json")
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "")
FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase-service-account.json")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SIGA")
VALID_EVENT_STATES = {"borrador", "activo", "cerrado"}
MIN_CUPO_TOTAL = 3
try:
    LECTOR_IDLE_TIMEOUT_SECONDS = int(os.getenv("LECTOR_IDLE_TIMEOUT_SECONDS", "900"))
except ValueError:
    LECTOR_IDLE_TIMEOUT_SECONDS = 900
try:
    LECTOR_MAX_PIN_ATTEMPTS = int(os.getenv("LECTOR_MAX_PIN_ATTEMPTS", "5"))
except ValueError:
    LECTOR_MAX_PIN_ATTEMPTS = 5
try:
    LECTOR_LOCKOUT_SECONDS = int(os.getenv("LECTOR_LOCKOUT_SECONDS", "300"))
except ValueError:
    LECTOR_LOCKOUT_SECONDS = 300
try:
    LECTOR_ACTIVE_WINDOW_SECONDS = int(os.getenv("LECTOR_ACTIVE_WINDOW_SECONDS", "120"))
except ValueError:
    LECTOR_ACTIVE_WINDOW_SECONDS = 120

firebase_ready = False
pendientes_lock = threading.Lock()
sync_meta = {
    "last_attempt": None,
    "last_success": None,
    "last_error": None,
}


# =========================
# Utilidades de seguridad
# =========================
def generar_hash_qr(invitado_id: str) -> str:
    """Genera hash SHA-512 usando ID + salt secreto."""
    base = f"{invitado_id}{obtener_salt_secreto()}"
    return hashlib.sha512(base.encode("utf-8")).hexdigest()


def validar_hash_qr(invitado_id: str, hash_recibido: str) -> bool:
    hash_esperado = generar_hash_qr(invitado_id)
    return hmac.compare_digest(hash_esperado, hash_recibido)


def obtener_salt_secreto() -> str:
    """Fuente única de salt: variables de entorno del proyecto."""
    return SALT_SECRETO


# =========================
# Firebase y persistencia
# =========================
def init_firebase() -> None:
    global firebase_ready

    if not FIREBASE_DB_URL:
        print("[WARN] FIREBASE_DB_URL no configurado. Modo local sin Firebase.")
        firebase_ready = False
        return

    if not os.path.exists(FIREBASE_CRED_PATH):
        print(f"[WARN] No existe archivo de credenciales: {FIREBASE_CRED_PATH}")
        firebase_ready = False
        return

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        firebase_ready = True
        print("[OK] Firebase inicializado.")
    except Exception as exc:
        firebase_ready = False
        print(f"[ERROR] Firebase no inicializado: {exc}")


def ensure_pendientes_file() -> None:
    if not os.path.exists(PENDIENTES_FILE):
        with open(PENDIENTES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def leer_pendientes() -> list:
    ensure_pendientes_file()
    with open(PENDIENTES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def escribir_pendientes(data: list) -> None:
    with open(PENDIENTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def guardar_log(evento: dict) -> None:
    """Intenta guardar en Firebase; si falla, guarda en cola offline."""
    evento.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    if firebase_ready:
        try:
            db.reference("logs").push(evento)
            return
        except Exception as exc:
            print(f"[WARN] Fallo guardando en Firebase, se encola: {exc}")

    with pendientes_lock:
        pendientes = leer_pendientes()
        evento["sincronizado"] = False
        pendientes.append(evento)
        escribir_pendientes(pendientes)


def sincronizar_pendientes() -> None:
    stats = {"processed": 0, "synced": 0, "failed": 0}
    if not firebase_ready:
        return stats

    with pendientes_lock:
        pendientes = leer_pendientes()

    if not pendientes:
        return stats

    actualizado = []
    for item in pendientes:
        if item.get("sincronizado") is True:
            actualizado.append(item)
            continue

        stats["processed"] += 1
        try:
            payload = dict(item)
            payload.pop("sincronizado", None)
            db.reference("logs").push(payload)
            item["sincronizado"] = True
            stats["synced"] += 1
        except Exception as exc:
            print(f"[WARN] No se pudo sincronizar item pendiente: {exc}")
            stats["failed"] += 1

        actualizado.append(item)

    with pendientes_lock:
        escribir_pendientes(actualizado)
    return stats


def worker_sincronizacion() -> None:
    while True:
        try:
            sync_meta["last_attempt"] = now_iso()
            stats = sincronizar_pendientes()
            if stats.get("failed", 0) == 0:
                sync_meta["last_success"] = now_iso()
                sync_meta["last_error"] = None
            else:
                sync_meta["last_error"] = f"Fallos de sincronización: {stats.get('failed', 0)}"
        except Exception as exc:
            print(f"[ERROR] Worker sync: {exc}")
            sync_meta["last_error"] = str(exc)
        time.sleep(30)


# =========================
# PDI: pipeline OpenCV + pyzbar
# =========================
def decodificar_qr(imagen) -> Optional[str]:
    resultados = decode(imagen)
    if not resultados:
        return None
    return resultados[0].data.decode("utf-8", errors="ignore")


def pipeline_decodificacion(imagen_bgr) -> Tuple[Optional[str], Optional[str]]:
    """
    Orden obligatorio:
    1) Grises
    2) Threshold fijo
    3) Threshold adaptativo gaussiano
    """
    gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
    texto = decodificar_qr(gris)
    if texto:
        return texto, "Fase 1: Escala de grises"

    _, fijo = cv2.threshold(gris, 127, 255, cv2.THRESH_BINARY)
    texto = decodificar_qr(fijo)
    if texto:
        return texto, "Fase 2: Threshold fijo"

    adaptativo = cv2.adaptiveThreshold(
        gris,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    texto = decodificar_qr(adaptativo)
    if texto:
        return texto, "Fase 3: Threshold adaptativo gaussiano"

    return None, None


def extraer_datos_qr(payload: str) -> Tuple[Optional[str], Optional[str]]:
    """Formato esperado: ID|HASH"""
    if "|" not in payload:
        return None, None
    invitado_id, hash_qr = payload.split("|", 1)
    invitado_id = invitado_id.strip()
    hash_qr = hash_qr.strip()
    if not invitado_id or not hash_qr:
        return None, None
    return invitado_id, hash_qr


# =========================
# Auth simple para /admin
# =========================
def admin_logueado() -> bool:
    return bool(session.get("admin_ok"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    usuario = request.form.get("usuario", "")
    password = request.form.get("password", "")

    hash_input = hashlib.sha512((password + SALT_SECRETO).encode("utf-8")).hexdigest()

    if usuario == ADMIN_USER and hmac.compare_digest(hash_input, ADMIN_PASSWORD_HASH):
        session.permanent = True
        session["admin_ok"] = True
        session["admin_user"] = usuario
        return redirect(url_for("admin"))

    return render_template("login.html", error="Credenciales inválidas")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin")
def admin():
    if not admin_logueado():
        return redirect(url_for("login"))
    return render_template("admin.html")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event_state(value: Any, default: str = "borrador") -> str:
    state = str(value or "").strip().lower()
    return state if state in VALID_EVENT_STATES else default


def parse_timestamp(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)

    iso = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_device_id(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raw = f"device_{uuid4().hex[:10]}"
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    out = "".join(ch for ch in raw if ch in allowed)
    return out[:64] or f"device_{uuid4().hex[:10]}"


def lector_session_data() -> dict:
    data = session.get("lector_auth") or {}
    return data if isinstance(data, dict) else {}


def lector_logout_session() -> None:
    session.pop("lector_auth", None)


def lector_is_idle(data: dict) -> bool:
    last_seen = parse_timestamp(data.get("last_seen_at") or data.get("login_at"))
    delta = (datetime.now(timezone.utc) - last_seen).total_seconds()
    return delta > max(LECTOR_IDLE_TIMEOUT_SECONDS, 60)


def lector_touch_session(update_pin_time: bool = False) -> dict:
    data = lector_session_data()
    if not data:
        return {}
    data["last_seen_at"] = now_iso()
    if update_pin_time:
        data["last_pin_at"] = data["last_seen_at"]
    session["lector_auth"] = data
    return data


def require_lector_session() -> Tuple[Optional[dict], Optional[Tuple[dict, int]]]:
    data = lector_session_data()
    if not data:
        return None, ({"ok": False, "error": "PIN requerido", "code": "LECTOR_PIN_REQUIRED"}, 401)
    if lector_is_idle(data):
        lector_logout_session()
        return None, ({"ok": False, "error": "Sesion de lector expirada por inactividad", "code": "LECTOR_SESSION_EXPIRED"}, 401)
    return lector_touch_session(), None


def append_lector_to_log(evento: dict, lector: Optional[dict]) -> dict:
    if not isinstance(evento, dict):
        return {}
    if not isinstance(lector, dict):
        return evento
    evento["lector_uid"] = str(lector.get("uid") or "")
    evento["lector_nombre"] = str(lector.get("nombre") or "")
    evento["lector_pin"] = str(lector.get("pin") or "")
    evento["dispositivo_id"] = str(lector.get("device_id") or "")
    return evento


def lector_lockout_ref(device_id: str):
    return db.reference(f"seguridad/lector_pin_lockouts/{normalize_device_id(device_id)}")


def leer_lectores_activos() -> list:
    if not firebase_ready:
        return []
    try:
        raw = db.reference("lectores_activos").get() or {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer lectores_activos: {exc}")
        return []
    if not isinstance(raw, dict):
        return []

    now_dt = datetime.now(timezone.utc)
    out = []
    for device_id, item in raw.items():
        if not isinstance(item, dict):
            continue
        last_seen = parse_timestamp(item.get("last_seen_at"))
        delta = (now_dt - last_seen).total_seconds()
        if delta > max(LECTOR_ACTIVE_WINDOW_SECONDS, 30):
            continue
        modo = str(item.get("modo") or "online").strip().lower()
        out.append(
            {
                "device_id": str(item.get("device_id") or device_id),
                "staff_id": str(item.get("staff_uid") or ""),
                "nombre": str(item.get("staff_nombre") or item.get("staff_uid") or device_id),
                "pin": str(item.get("pin") or ""),
                "timestamp": item.get("last_seen_at") or "",
                "modo": "local" if modo == "local" else "online",
            }
        )
    return sorted(out, key=lambda x: parse_timestamp(x.get("timestamp")), reverse=True)


def registrar_lector_activo(lector: dict, modo: str = "online") -> None:
    if not firebase_ready:
        return
    device_id = normalize_device_id(lector.get("device_id"))
    payload = {
        "device_id": device_id,
        "staff_uid": str(lector.get("uid") or ""),
        "staff_nombre": str(lector.get("nombre") or ""),
        "pin": str(lector.get("pin") or ""),
        "rol": str(lector.get("rol") or "lector"),
        "modo": "local" if str(modo).strip().lower() == "local" else "online",
        "last_seen_at": now_iso(),
    }
    try:
        db.reference(f"lectores_activos/{device_id}").set(payload)
    except Exception as exc:
        print(f"[WARN] No se pudo registrar lector activo: {exc}")


def quitar_lector_activo(device_id: str) -> None:
    if not firebase_ready:
        return
    did = normalize_device_id(device_id)
    try:
        db.reference(f"lectores_activos/{did}").delete()
    except Exception as exc:
        print(f"[WARN] No se pudo quitar lector activo: {exc}")


def leer_invitados() -> dict:
    if not firebase_ready:
        return {}
    try:
        invitados = db.reference("invitados").get() or {}
        return invitados if isinstance(invitados, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer invitados: {exc}")
        return {}


def total_boletos_entregados(invitados: dict) -> int:
    total = 0
    for item in invitados.values():
        if not isinstance(item, dict):
            continue
        total += max(safe_int(item.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), 0)
    return total


def resumen_disponibilidad_cupo(invitados: Optional[dict] = None) -> dict:
    invitados_data = invitados if isinstance(invitados, dict) else leer_invitados()
    entregados = total_boletos_entregados(invitados_data)
    cfg = evento_actual_config()
    aforo_max = max(safe_int((cfg or {}).get("aforo_max", 0), 0), 0)
    disponibles = max(aforo_max - entregados, 0)
    return {
        "aforo_max": aforo_max,
        "boletos_entregados": entregados,
        "boletos_disponibles": disponibles,
    }


def leer_solicitudes_cupo() -> dict:
    if not firebase_ready:
        return {}
    try:
        data = db.reference("solicitudes_cupo").get() or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer solicitudes_cupo: {exc}")
        return {}


def solicitudes_cupo_listado(solicitudes: dict) -> list:
    rows = []
    for key, data in (solicitudes or {}).items():
        if not isinstance(data, dict):
            continue
        rows.append(
            {
                "id": key,
                "invitado_id": str(data.get("invitado_id", "")).strip(),
                "invitado_key": str(data.get("invitado_key", "")).strip(),
                "nombre_invitado": str(data.get("nombre_invitado", "")).strip(),
                "cantidad_solicitada": max(safe_int(data.get("cantidad_solicitada", 1), 1), 1),
                "cantidad_aprobada": max(safe_int(data.get("cantidad_aprobada", 0), 0), 0),
                "status": str(data.get("status", "pendiente")).strip().lower() or "pendiente",
                "motivo": str(data.get("motivo", "")).strip(),
                "solicitado_por_uid": str(data.get("solicitado_por_uid", "")).strip(),
                "solicitado_por_nombre": str(data.get("solicitado_por_nombre", "")).strip(),
                "solicitado_desde": str(data.get("solicitado_desde", "lector")).strip().lower() or "lector",
                "created_at": str(data.get("created_at", "")).strip(),
                "resolved_at": str(data.get("resolved_at", "")).strip(),
                "resolved_by": str(data.get("resolved_by", "")).strip(),
                "decision_note": str(data.get("decision_note", "")).strip(),
            }
        )
    return sorted(rows, key=lambda x: parse_timestamp(x.get("created_at")), reverse=True)


def existe_solicitud_pendiente(solicitudes: dict, invitado_key: str) -> bool:
    invitado_key = str(invitado_key or "").strip()
    if not invitado_key:
        return False
    for item in (solicitudes or {}).values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "pendiente")).strip().lower()
        if status != "pendiente":
            continue
        if str(item.get("invitado_key", "")).strip() == invitado_key:
            return True
    return False


def indexar_invitados_por_id(invitados: dict) -> dict:
    idx = {}
    for key, value in invitados.items():
        if not isinstance(value, dict):
            continue
        invitado_id = str(value.get("id", "")).strip()
        if invitado_id:
            idx[invitado_id] = {"key": key, "data": value}
    return idx


def buscar_invitado(invitado_id: str, hash_qr: Optional[str] = None) -> Tuple[Optional[str], Optional[dict]]:
    """Busca primero por hash (nuevo esquema), luego por id."""
    if not firebase_ready:
        return None, None
    try:
        ref = db.reference("invitados")

        if hash_qr:
            invitado = ref.child(hash_qr).get()
            if isinstance(invitado, dict):
                return hash_qr, invitado

        invitado = ref.child(invitado_id).get()
        if isinstance(invitado, dict):
            return invitado_id, invitado

        todos = ref.get() or {}
        if isinstance(todos, dict):
            for key, value in todos.items():
                if isinstance(value, dict) and str(value.get("id", "")).strip() == invitado_id:
                    return key, value
    except Exception as exc:
        print(f"[WARN] No se pudo buscar invitado: {exc}")
    return None, None


def leer_logs(limit: int = 400) -> list:
    logs = []

    if firebase_ready:
        try:
            raw = db.reference("logs").order_by_key().limit_to_last(limit).get() or {}
            if isinstance(raw, dict):
                logs.extend(raw.values())
        except Exception as exc:
            print(f"[WARN] No se pudieron leer logs de Firebase: {exc}")

    with pendientes_lock:
        pendientes = leer_pendientes()
    logs.extend(pendientes)

    return [log for log in logs if isinstance(log, dict)]


def leer_configuracion() -> dict:
    if not firebase_ready:
        return {}
    try:
        cfg = db.reference("configuracion").get() or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer configuracion: {exc}")
        return {}


def leer_eventos() -> dict:
    if not firebase_ready:
        return {}
    try:
        eventos = db.reference("eventos").get() or {}
        return eventos if isinstance(eventos, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer eventos: {exc}")
        return {}


def leer_staff() -> dict:
    if not firebase_ready:
        return {}
    try:
        staff = db.reference("usuarios_staff").get() or {}
        return staff if isinstance(staff, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer usuarios_staff: {exc}")
        return {}


def evento_actual_config() -> dict:
    if not firebase_ready:
        return {}
    try:
        data = db.reference("configuracion/evento_actual").get() or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer evento_actual: {exc}")
        return {}


def estado_evento_activo() -> Tuple[Optional[str], dict]:
    cfg = evento_actual_config()
    event_id = str(cfg.get("id_evento", "")).strip()
    if not event_id:
        return None, cfg
    try:
        ev = db.reference(f"eventos/{event_id}").get() or {}
        if isinstance(ev, dict):
            cfg["estado"] = ev.get("estado", cfg.get("estado", "borrador"))
    except Exception as exc:
        print(f"[WARN] No se pudo leer estado evento activo: {exc}")
    return event_id, cfg


def actor_admin() -> str:
    return str(session.get("admin_user") or ADMIN_USER)


def calc_changes(before: dict, after: dict) -> list:
    fields = sorted(set(before.keys()) | set(after.keys()))
    out = []
    for field in fields:
        b = before.get(field)
        a = after.get(field)
        if b != a:
            out.append({"field": field, "before": b, "after": a})
    return out


def audit_evento(entity: str, entity_id: str, action: str, before: Optional[dict], after: Optional[dict], extra: Optional[dict] = None) -> None:
    if not firebase_ready:
        return
    payload = {
        "timestamp": now_iso(),
        "actor": actor_admin(),
        "entidad": entity,
        "entity_id": entity_id,
        "accion": action,
        "changes": calc_changes(before or {}, after or {}),
    }
    if extra:
        payload["meta"] = extra
    try:
        db.reference("auditoria/eventos").push(payload)
    except Exception as exc:
        print(f"[WARN] No se pudo escribir auditoria: {exc}")


def required_event_fields(record: dict) -> dict:
    return {
        "id_evento": str(record.get("id_evento", "")).strip(),
        "nombre": record.get("nombre", ""),
        "ubicacion": record.get("ubicacion", ""),
        "aforo_max": max(safe_int(record.get("aforo_max", 0), 0), 0),
        "aforo_actual": max(safe_int(record.get("aforo_actual", 0), 0), 0),
        "estado": normalize_event_state(record.get("estado", "borrador")),
        "fecha_inicio": record.get("fecha_inicio", ""),
        "fecha_fin": record.get("fecha_fin", ""),
        "timezone": record.get("timezone", "America/Mexico_City"),
    }


def sanitized_config(config: dict) -> dict:
    if not isinstance(config, dict):
        return {}
    out = dict(config)
    out.pop("salt_secreto", None)
    evento = out.get("evento_actual")
    if isinstance(evento, dict):
        evento_copy = dict(evento)
        evento_copy.pop("salt_secreto", None)
        evento_copy.pop("umbral_alerta_aforo", None)
        evento_copy.pop("requiere_validacion_admin", None)
        evento_copy.pop("permitir_reingreso", None)
        evento_copy.pop("modo_operacion", None)
        out["evento_actual"] = evento_copy
    return out


def invitados_listado(invitados: dict) -> list:
    out = []
    for key, data in invitados.items():
        if not isinstance(data, dict):
            continue
        cupo_total = max(safe_int(data.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), MIN_CUPO_TOTAL)
        cupo_usado = max(safe_int(data.get("cupo_usado", data.get("ingresados", 0)), 0), 0)
        out.append(
            {
                "key": key,
                "id": str(data.get("id", "")),
                "nombre": data.get("nombre_lider") or data.get("nombre") or "",
                "email": data.get("email", ""),
                "cupo_total": cupo_total,
                "cupo_usado": min(cupo_usado, cupo_total),
                "status": data.get("status", "fuera"),
                "invitacion_enviada": bool(data.get("invitacion_enviada", False)),
                "bloqueado": bool(data.get("bloqueado", False)),
                "tipo_invitado": data.get("tipo_invitado", "general"),
                "grupo_nombre": data.get("grupo_nombre", ""),
            }
        )
    return sorted(out, key=lambda x: x["id"] or x["key"])


def parse_bool_param(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("true", "1", "si", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


def normalizar_id(value: Any) -> str:
    return str(value or "").strip()


def normalizar_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalizar_nombre(value: Any) -> str:
    return str(value or "").strip()


def invitados_indexes(invitados: dict, exclude_key: Optional[str] = None) -> Tuple[dict, dict]:
    id_index = {}
    email_index = {}
    for key, item in invitados.items():
        if key == exclude_key or not isinstance(item, dict):
            continue
        id_norm = normalizar_id(item.get("id"))
        email_norm = normalizar_email(item.get("email"))
        if id_norm:
            id_index[id_norm.lower()] = key
        if email_norm:
            email_index[email_norm] = key
    return id_index, email_index


def validar_datos_invitado(
    data: dict,
    invitados: dict,
    exclude_key: Optional[str] = None,
    require_required: bool = True,
) -> Tuple[Optional[dict], Optional[dict]]:
    id_norm = normalizar_id(data.get("id"))
    nombre_norm = normalizar_nombre(data.get("nombre") or data.get("nombre_lider"))
    email_norm = normalizar_email(data.get("email"))
    cupo_total = max(safe_int(data.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), MIN_CUPO_TOTAL)

    if require_required and not id_norm:
        return None, {"field": "id", "message": "ID es requerido"}
    if require_required and not nombre_norm:
        return None, {"field": "nombre", "message": "Nombre es requerido"}
    if require_required and not email_norm:
        return None, {"field": "email", "message": "Email es requerido"}
    if email_norm and "@" not in email_norm:
        return None, {"field": "email", "message": "Email inválido"}

    id_index, email_index = invitados_indexes(invitados, exclude_key=exclude_key)
    conflict = {}
    if id_norm and id_norm.lower() in id_index:
        conflict["id_conflict_key"] = id_index[id_norm.lower()]
    if email_norm and email_norm in email_index:
        conflict["email_conflict_key"] = email_index[email_norm]
    if conflict:
        return None, {"field": "duplicate", "message": "ID o email duplicado", "conflict": conflict}

    payload = {
        "id": id_norm,
        "nombre": nombre_norm,
        "nombre_lider": nombre_norm,
        "email": email_norm,
        "cupo_total": cupo_total,
        "cupo_usado": max(safe_int(data.get("cupo_usado", 0), 0), 0),
        "status": data.get("status", "fuera"),
        "invitacion_enviada": bool(data.get("invitacion_enviada", False)),
        "bloqueado": bool(data.get("bloqueado", False)),
        "tipo_invitado": str(data.get("tipo_invitado", "general")).strip().lower() or "general",
        "grupo_nombre": str(data.get("grupo_nombre", "")).strip(),
    }
    payload["cupo_usado"] = min(payload["cupo_usado"], payload["cupo_total"])
    return payload, None


def aplicar_filtros_invitados(rows: list, q: str = "", bloqueado: Optional[bool] = None, pendiente: Optional[bool] = None, tipo: str = "") -> list:
    qn = (q or "").strip().lower()
    tipo_n = (tipo or "").strip().lower()
    out = []
    for row in rows:
        if qn:
            searchable = f"{row.get('id','')} {row.get('nombre','')} {row.get('email','')}".lower()
            if qn not in searchable:
                continue
        if bloqueado is not None and bool(row.get("bloqueado")) != bloqueado:
            continue
        is_pendiente = safe_int(row.get("cupo_usado"), 0) < safe_int(row.get("cupo_total"), 0)
        if pendiente is not None and is_pendiente != pendiente:
            continue
        if tipo_n and str(row.get("tipo_invitado", "")).lower() != tipo_n:
            continue
        out.append(row)
    return out


def paginar_rows(rows: list, page: int, page_size: int) -> dict:
    total = len(rows)
    page_size = max(1, min(page_size, 200))
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": rows[start:end],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def filtrar_y_paginar_invitados(invitados: dict, query_args: dict, paginate: bool = True) -> dict:
    rows = invitados_listado(invitados)
    filtered = aplicar_filtros_invitados(
        rows,
        q=str(query_args.get("q", "") or ""),
        bloqueado=parse_bool_param(query_args.get("bloqueado")),
        pendiente=parse_bool_param(query_args.get("pendiente")),
        tipo=str(query_args.get("tipo", "") or ""),
    )
    if not paginate:
        return {"items": filtered, "page": 1, "page_size": len(filtered) or 1, "total": len(filtered), "total_pages": 1}
    page = safe_int(query_args.get("page", 1), 1)
    page_size = safe_int(query_args.get("page_size", 25), 25)
    return paginar_rows(filtered, page, page_size)


def obtener_keys_lote(invitados: dict, scope: str, keys: list, filters: dict) -> list:
    if scope == "selected":
        return [k for k in keys if k in invitados]
    filtered = filtrar_y_paginar_invitados(invitados, filters, paginate=False)["items"]
    return [item["key"] for item in filtered]


def generar_csv_invitados(rows: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["key", "id", "nombre", "email", "cupo_total", "cupo_usado", "tipo_invitado", "bloqueado", "invitacion_enviada", "status"])
    for row in rows:
        writer.writerow(
            [
                row.get("key", ""),
                row.get("id", ""),
                row.get("nombre", ""),
                row.get("email", ""),
                row.get("cupo_total", 0),
                row.get("cupo_usado", 0),
                row.get("tipo_invitado", ""),
                bool(row.get("bloqueado", False)),
                bool(row.get("invitacion_enviada", False)),
                row.get("status", ""),
            ]
        )
    return output.getvalue()


def smtp_client() -> Tuple[Optional[yagmail.SMTP], Optional[str]]:
    if not SMTP_USER or not SMTP_APP_PASSWORD:
        return None, "Faltan SMTP_USER o SMTP_APP_PASSWORD en variables de entorno"
    try:
        return yagmail.SMTP(SMTP_USER, SMTP_APP_PASSWORD), None
    except Exception as exc:
        return None, str(exc)


def enviar_invitacion_email(client: yagmail.SMTP, invitado: dict, key_hash: str) -> Optional[str]:
    invitado_id = normalizar_id(invitado.get("id"))
    nombre = invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id
    email = normalizar_email(invitado.get("email"))
    cupo = safe_int(invitado.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL)
    qr_payload = f"{invitado_id}|{key_hash}"
    asunto = "Invitacion SIGA - Acceso al evento"
    
    # Generar QR optimizado
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    temp_dir = tempfile.gettempdir()
    qr_filename = os.path.join(temp_dir, f"qr_{invitado_id}_{int(time.time())}.png")
    img.save(qr_filename)

    html_part1 = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f7fb; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            .header {{ background-color: #6366f1; color: #ffffff; padding: 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.5px; }}
            .content {{ padding: 32px 24px; color: #333333; text-align: center; }}
            .content p {{ font-size: 15px; line-height: 1.6; margin-bottom: 24px; color: #475569; }}
            .info-box {{ background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; text-align: left; display: inline-block; }}
            .info-box p {{ margin: 8px 0; font-size: 14px; color: #1e293b; }}
            .info-box strong {{ color: #6366f1; font-weight: 600; display: inline-block; min-width: 120px; }}
            .qr-section p {{ font-weight: 600; color: #1e293b; margin-bottom: 12px; }}
            .footer {{ background-color: #f8fafc; color: #64748b; text-align: center; padding: 16px; font-size: 13px; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Invitación Oficial SIGA</h1>
            </div>
            <div class="content">
                <p>Hola <strong style="color:#1e293b;">{nombre}</strong>,</p>
                <p>Tu registro se ha completado con éxito. Usa esta invitación digital para tener un acceso o ingreso rápido el día del evento.</p>
                
                <div class="info-box">
                    <p><strong>ID de Invitado:</strong> {invitado_id}</p>
                    <p><strong>Cupo Máximo:</strong> {cupo} personas</p>
                </div>
                
                <div class="qr-section">
                    <p>Presenta este código QR en el acceso:</p>
                    <!-- Yagmail injects inline img class here -->
    """
    
    html_part2 = f"""
                </div>
            </div>
            <div class="footer">
                <p>Este es un correo automático provisto de forma segura por SIGA.</p>
            </div>
        </div>
    </body>
    </html>
    """

    contenido = [
        html_part1,
        yagmail.inline(qr_filename),
        html_part2
    ]
    try:
        client.send(
            to=email,
            subject=asunto,
            contents=contenido,
            headers={"From": f"{SMTP_FROM_NAME} <{SMTP_USER}>"},
        )
        return None
    except Exception as exc:
        return str(exc)
    finally:
        if os.path.exists(qr_filename):
            try:
                os.remove(qr_filename)
            except OSError:
                pass


def eventos_listado(eventos: dict) -> list:
    out = []
    for key, data in eventos.items():
        if not isinstance(data, dict):
            continue
        out.append(
            {
                "id_evento": data.get("id_evento", key),
                "nombre": data.get("nombre", ""),
                "ubicacion": data.get("ubicacion", ""),
                "estado": data.get("estado", "borrador"),
                "aforo_max": safe_int(data.get("aforo_max", 0), 0),
                "fecha_inicio": data.get("fecha_inicio", ""),
                "fecha_fin": data.get("fecha_fin", ""),
                "timezone": data.get("timezone", "America/Mexico_City"),
            }
        )
    return sorted(out, key=lambda x: x["id_evento"])


def active_event_id_from_rows(rows: list) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if normalize_event_state(row.get("estado"), "borrador") == "activo":
            return str(row.get("id_evento", "")).strip()
    return ""


def staff_listado(staff: dict) -> list:
    out = []
    for key, data in staff.items():
        if not isinstance(data, dict):
            continue
        out.append(
            {
                "uid": key,
                "nombre": data.get("nombre", ""),
                "email": data.get("email", ""),
                "rol": data.get("rol", "lector"),
                "activo": bool(data.get("activo", True)),
                "pin": str(data.get("pin", "")),
            }
        )
    return sorted(out, key=lambda x: x["nombre"])


def normalize_pin(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_valid_pin(pin: str) -> bool:
    return len(pin) == 6 and pin.isdigit()


def pin_exists_in_staff(pin: str, exclude_uid: str = "") -> bool:
    pin = normalize_pin(pin)
    if not pin:
        return False
    staff = leer_staff()
    for uid, row in staff.items():
        if not isinstance(row, dict):
            continue
        if exclude_uid and str(uid) == str(exclude_uid):
            continue
        if normalize_pin(row.get("pin")) == pin:
            return True
    return False


def construir_dashboard_data(event_id: Optional[str] = None, desde: Optional[str] = None, hasta: Optional[str] = None) -> dict:
    invitados = leer_invitados()
    logs = leer_logs(limit=500)
    invitados_idx = indexar_invitados_por_id(invitados)

    total_registros = len(invitados)
    cupo_total = sum(
        max(safe_int(item.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), 0)
        for item in invitados.values()
        if isinstance(item, dict)
    )
    ingresados = sum(
        max(safe_int(item.get("cupo_usado", item.get("ingresados", 0)), 0), 0)
        for item in invitados.values()
        if isinstance(item, dict)
    )
    pendientes = max(cupo_total - ingresados, 0)

    evento = {}
    if firebase_ready:
        try:
            evento_db = db.reference("configuracion/evento_actual").get() or {}
            if isinstance(evento_db, dict):
                evento = evento_db
        except Exception as exc:
            print(f"[WARN] No se pudo leer configuracion/evento_actual: {exc}")
    aforo_max = safe_int(evento.get("aforo_max"), 0) or cupo_total

    with pendientes_lock:
        sync_pendientes = sum(1 for item in leer_pendientes() if not item.get("sincronizado"))

    current_event_id = str(evento.get("id_evento", "")).strip()
    selected_event_id = (event_id or current_event_id or "").strip()
    desde_dt = parse_timestamp(desde) if desde else None
    hasta_dt = parse_timestamp(hasta) if hasta else None

    logs_ordenados = sorted(logs, key=lambda item: parse_timestamp(item.get("timestamp")), reverse=True)
    logs_filtrados = []
    for item in logs_ordenados:
        log_event_id = str(item.get("id_evento") or item.get("evento_id") or "").strip()
        ts = parse_timestamp(item.get("timestamp"))
        if selected_event_id:
            if log_event_id and log_event_id != selected_event_id:
                continue
        if desde_dt and ts < desde_dt:
            continue
        if hasta_dt and ts > hasta_dt:
            continue
        logs_filtrados.append(item)

    fase_por_invitado = {}
    for item in logs_filtrados:
        if item.get("evento") not in ("qr_valido", None) and "fase_pdi" not in item:
            continue
        invitado_id = str(item.get("invitado_id", "")).strip()
        if not invitado_id or invitado_id in fase_por_invitado:
            continue
        fase_por_invitado[invitado_id] = item.get("fase_pdi") or item.get("fase_exitosa") or "N/D"

    ultimos_ingresos = []
    for item in logs_filtrados:
        if item.get("evento") != "ingreso_registrado" and "cantidad_entrada" not in item:
            continue

        invitado_id = str(item.get("invitado_id", "")).strip()
        invitado = invitados_idx.get(invitado_id, {}).get("data", {})
        fecha = parse_timestamp(item.get("timestamp"))
        hora = fecha.astimezone().strftime("%H:%M") if fecha.year > 1900 else "--:--"
        cupo = max(safe_int(item.get("cupo_total", invitado.get("cupo_total", 0)), 0), 0)
        entraron = max(safe_int(item.get("cantidad_entrada", item.get("sumar", 0)), 0), 0)

        ultimos_ingresos.append(
            {
                "hora": hora,
                "nombre_lider": item.get("nombre_invitado")
                or invitado.get("nombre_lider")
                or invitado.get("nombre")
                or invitado_id
                or "N/D",
                "cupo": cupo,
                "entraron": entraron,
                "fase_pdi": fase_por_invitado.get(invitado_id, "N/D"),
            }
        )
        if len(ultimos_ingresos) >= 5:
            break

    lectores = leer_lectores_activos()
    lectores_online = sum(1 for x in lectores if x.get("modo") == "online")
    lectores_local = sum(1 for x in lectores if x.get("modo") == "local")

    aforo_pct = round((ingresados / aforo_max) * 100) if aforo_max > 0 else 0
    alerts = []
    if aforo_pct >= 100:
        alerts.append(
            {
                "level": "error",
                "title": "Aforo al 100%",
                "message": "El evento alcanzó su capacidad máxima.",
                "action": "Ir a Reportes",
                "action_view": "reportes",
            }
        )
    elif aforo_pct >= 90:
        alerts.append(
            {
                "level": "warning",
                "title": "Aforo en zona de alerta",
                "message": f"Capacidad actual al {aforo_pct}%.",
                "action": "Monitorear ingresos",
                "action_view": "dashboard",
            }
        )
    if sync_pendientes > 0:
        alerts.append(
            {
                "level": "warning",
                "title": "Sincronización pendiente",
                "message": f"Hay {sync_pendientes} registros locales sin subir.",
                "action": "Reintentar Sync",
                "action_api": "retry_sync",
            }
        )
    if sync_meta.get("last_error"):
        alerts.append(
            {
                "level": "error",
                "title": "Error de sincronización",
                "message": str(sync_meta.get("last_error")),
                "action": "Reintentar Sync",
                "action_api": "retry_sync",
            }
        )
    if not lectores:
        alerts.append(
            {
                "level": "info",
                "title": "Sin lectores activos",
                "message": "No se detectó actividad reciente de dispositivos de lectura.",
            }
        )

    eventos = eventos_listado(leer_eventos())

    return {
        "aforo_actual": ingresados,
        "aforo_maximo": aforo_max,
        "total_invitados_registrados": total_registros,
        "invitados_pendientes": pendientes,
        "sincronizaciones_pendientes": sync_pendientes,
        "ultimos_ingresos": ultimos_ingresos,
        "firebase_ready": firebase_ready,
        "evento_nombre": evento.get("nombre", "Evento SIGA"),
        "evento_ubicacion": evento.get("ubicacion", ""),
        "eventos_disponibles": eventos,
        "selected_event_id": selected_event_id,
        "filters": {"desde": desde or "", "hasta": hasta or ""},
        "alerts": alerts,
        "ultima_sincronizacion": sync_meta.get("last_success"),
        "ultimo_intento_sync": sync_meta.get("last_attempt"),
        "sync_error": sync_meta.get("last_error"),
        "lectores": {
            "online": lectores_online,
            "local": lectores_local,
            "total": len(lectores),
            "detalle": lectores[:20],
        },
    }


def construir_reporte_data(fecha_desde: Optional[str] = None, fecha_hasta: Optional[str] = None) -> dict:
    logs = leer_logs(limit=3000)
    logs_ordenados = sorted(logs, key=lambda item: parse_timestamp(item.get("timestamp")), reverse=True)
    desde = parse_timestamp(fecha_desde) if fecha_desde else None
    hasta = parse_timestamp(fecha_hasta) if fecha_hasta else None

    filtrados = []
    for item in logs_ordenados:
        ts = parse_timestamp(item.get("timestamp"))
        if desde and ts < desde:
            continue
        if hasta and ts > hasta:
            continue
        filtrados.append(item)

    movimientos = []
    entradas_total = 0
    salidas_total = 0

    for item in filtrados:
        evento = str(item.get("evento", "")).strip().lower()
        entrada_qty = max(safe_int(item.get("cantidad_entrada", item.get("sumar", 0)), 0), 0)
        salida_qty = max(safe_int(item.get("cantidad_salida", item.get("restar", 0)), 0), 0)

        tipo = None
        cantidad = 0
        if evento == "ingreso_registrado" or entrada_qty > 0:
            tipo = "entrada"
            cantidad = entrada_qty
            entradas_total += cantidad
        elif evento in {"salida_registrada", "egreso_registrado"} or salida_qty > 0:
            tipo = "salida"
            cantidad = salida_qty
            salidas_total += cantidad

        if not tipo:
            continue

        fecha = parse_timestamp(item.get("timestamp"))
        movimientos.append(
            {
                "timestamp": item.get("timestamp", ""),
                "hora": fecha.astimezone().strftime("%Y-%m-%d %H:%M") if fecha.year > 1900 else "",
                "tipo": tipo,
                "cantidad": cantidad,
                "invitado_id": str(item.get("invitado_id", "")).strip(),
                "nombre_invitado": item.get("nombre_invitado", "") or "",
                "modo": item.get("modo_conexion") or item.get("modo", "nube"),
            }
        )

    movimientos = sorted(movimientos, key=lambda x: parse_timestamp(x.get("timestamp")), reverse=True)

    cfg = evento_actual_config()
    aforo_total = max(safe_int(cfg.get("aforo_max", 0), 0), 0)
    aforo_utilizado = max(safe_int(cfg.get("aforo_actual", 0), 0), 0)
    capacidad_disponible = max(aforo_total - aforo_utilizado, 0)

    return {
        "resumen": {
            "entradas_total": entradas_total,
            "salidas_total": salidas_total,
            "movimientos_total": len(movimientos),
            "aforo_total": aforo_total,
            "aforo_utilizado": aforo_utilizado,
            "capacidad_disponible": capacidad_disponible,
        },
        "movimientos": movimientos[:200],
    }


def reporte_csv(data: dict) -> str:
    resumen = data.get("resumen", {})
    movimientos = data.get("movimientos", [])
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["REPORTE SIGA"])
    w.writerow(["Metrica", "Valor"])
    w.writerow(["Entradas total", resumen.get("entradas_total", 0)])
    w.writerow(["Salidas total", resumen.get("salidas_total", 0)])
    w.writerow(["Movimientos total", resumen.get("movimientos_total", 0)])
    w.writerow(["Capacidad total", resumen.get("aforo_total", 0)])
    w.writerow(["Capacidad utilizada", resumen.get("aforo_utilizado", 0)])
    w.writerow(["Capacidad disponible", resumen.get("capacidad_disponible", 0)])
    w.writerow([])
    w.writerow(["Hora", "Movimiento", "Cantidad", "ID", "Nombre", "Modo"])
    for m in movimientos:
        w.writerow([m.get("hora", ""), m.get("tipo", ""), m.get("cantidad", 0), m.get("invitado_id", ""), m.get("nombre_invitado", ""), m.get("modo", "")])
    return s.getvalue()


def reporte_pdf_bytes(data: dict, desde: Optional[str], hasta: Optional[str]) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError(f"reportlab no disponible: {exc}") from exc

    resumen = data.get("resumen", {})
    movimientos = data.get("movimientos", [])
    buff = io.BytesIO()
    c = canvas.Canvas(buff, pagesize=letter)
    width, height = letter
    y = height - 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Reporte SIGA")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Rango: {desde or 'inicio'} a {hasta or 'ahora'}")
    y -= 20

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Resumen")
    y -= 14
    c.setFont("Helvetica", 9)
    resumen_lines = [
        f"Entradas total: {resumen.get('entradas_total', 0)}",
        f"Salidas total: {resumen.get('salidas_total', 0)}",
        f"Movimientos total: {resumen.get('movimientos_total', 0)}",
        f"Capacidad total: {resumen.get('aforo_total', 0)}",
        f"Capacidad utilizada: {resumen.get('aforo_utilizado', 0)}",
        f"Capacidad disponible: {resumen.get('capacidad_disponible', 0)}",
    ]
    for line in resumen_lines:
        c.drawString(50, y, line)
        y -= 12

    y -= 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Detalle de movimientos (max 100)")
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "Hora")
    c.drawString(155, y, "Mov")
    c.drawString(205, y, "Cant")
    c.drawString(245, y, "ID")
    c.drawString(315, y, "Nombre")
    y -= 10
    c.setFont("Helvetica", 8)

    for m in movimientos[:100]:
        if y < 40:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica-Bold", 8)
            c.drawString(40, y, "Hora")
            c.drawString(155, y, "Mov")
            c.drawString(205, y, "Cant")
            c.drawString(245, y, "ID")
            c.drawString(315, y, "Nombre")
            y -= 10
            c.setFont("Helvetica", 8)

        nombre = str(m.get("nombre_invitado", ""))[:35]
        c.drawString(40, y, str(m.get("hora", ""))[:16])
        c.drawString(155, y, str(m.get("tipo", ""))[:8])
        c.drawString(205, y, str(m.get("cantidad", 0)))
        c.drawString(245, y, str(m.get("invitado_id", ""))[:10])
        c.drawString(315, y, nombre)
        y -= 10

    c.save()
    return buff.getvalue()


def construir_admin_state() -> dict:
    invitados = leer_invitados()
    eventos = leer_eventos()
    config = sanitized_config(leer_configuracion())
    staff = leer_staff()
    eventos_rows = eventos_listado(eventos)
    active_id = active_event_id_from_rows(eventos_rows)
    for row in eventos_rows:
        row["is_active"] = row.get("id_evento") == active_id

    return {
        "dashboard": construir_dashboard_data(),
        "configuracion": config,
        "invitados": invitados_listado(invitados),
        "eventos": eventos_rows,
        "evento_activo_id": active_id,
        "usuarios_staff": staff_listado(staff),
        "reportes": construir_reporte_data(),
    }


# =========================
# Vistas públicas
# =========================
@app.route("/")
def home():
    return redirect(url_for("lector"))


@app.route("/lector")
def lector():
    return render_template("lector.html")


@app.route("/api/lector/staff")
def api_lector_staff():
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    staff = leer_staff()
    items = []
    for uid, row in staff.items():
        if not isinstance(row, dict):
            continue
        if not bool(row.get("activo", True)):
            continue
        pin = normalize_pin(row.get("pin", ""))
        if not is_valid_pin(pin):
            continue
        items.append(
            {
                "uid": uid,
                "nombre": row.get("nombre") or uid,
                "rol": row.get("rol", "lector"),
            }
        )
    items.sort(key=lambda x: str(x.get("nombre", "")))
    return jsonify({"ok": True, "data": {"items": items}})


@app.route("/api/lector/login", methods=["POST"])
def api_lector_login():
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    payload = request.get_json(silent=True) or {}
    pin = normalize_pin(payload.get("pin", ""))
    device_id = normalize_device_id(payload.get("device_id"))
    modo = str(payload.get("modo") or "online").strip().lower()

    if not is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos", "code": "PIN_FORMAT_INVALID"}), 400

    lock_ref = lector_lockout_ref(device_id)
    lock_data = lock_ref.get() or {}
    if isinstance(lock_data, dict):
        locked_until = parse_timestamp(lock_data.get("locked_until"))
        now_dt = datetime.now(timezone.utc)
        if locked_until > now_dt:
            wait_seconds = int((locked_until - now_dt).total_seconds())
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"PIN bloqueado temporalmente. Intenta en {wait_seconds}s.",
                        "code": "PIN_LOCKED",
                        "retry_in_seconds": wait_seconds,
                    }
                ),
                423,
            )

    staff_all = leer_staff()
    matches = []
    for uid, row in staff_all.items():
        if not isinstance(row, dict):
            continue
        if not bool(row.get("activo", True)):
            continue
        rol = str(row.get("rol", "lector")).strip().lower()
        if rol not in {"lector", "supervisor", "admin"}:
            continue
        if normalize_pin(row.get("pin", "")) == pin:
            matches.append((uid, row))

    if len(matches) > 1:
        return jsonify({"ok": False, "error": "PIN duplicado. Contacta a un administrador.", "code": "PIN_DUPLICATE"}), 409

    if len(matches) != 1:
        fail_count = safe_int((lock_data or {}).get("fail_count"), 0) + 1
        update = {"fail_count": fail_count, "last_fail_at": now_iso()}
        if fail_count >= max(LECTOR_MAX_PIN_ATTEMPTS, 1):
            locked_until = datetime.now(timezone.utc).timestamp() + max(LECTOR_LOCKOUT_SECONDS, 60)
            update["locked_until"] = datetime.fromtimestamp(locked_until, tz=timezone.utc).isoformat()
            update["fail_count"] = 0
        lock_ref.update(update)
        return jsonify({"ok": False, "error": "PIN inválido", "code": "PIN_INVALID"}), 401

    uid, staff = matches[0]
    expected_pin = normalize_pin(staff.get("pin", ""))
    lock_ref.delete()
    now = now_iso()
    lector = {
        "uid": uid,
        "nombre": staff.get("nombre") or uid,
        "rol": staff.get("rol", "lector"),
        "pin": expected_pin,
        "device_id": device_id,
        "login_at": now,
        "last_seen_at": now,
        "last_pin_at": now,
    }
    session["lector_auth"] = lector
    session.permanent = True
    registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True, "data": {"uid": uid, "nombre": lector["nombre"], "rol": lector["rol"]}})


@app.route("/api/lector/admin_login", methods=["POST"])
def api_lector_admin_login():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado", "code": "ADMIN_REQUIRED"}), 401

    payload = request.get_json(silent=True) or {}
    device_id = normalize_device_id(payload.get("device_id"))
    modo = str(payload.get("modo") or "online").strip().lower()
    admin_user = str(session.get("admin_user") or ADMIN_USER).strip() or ADMIN_USER

    now = now_iso()
    lector = {
        "uid": f"admin_{admin_user}",
        "nombre": f"{admin_user} (admin)",
        "rol": "admin",
        "pin": "",
        "device_id": device_id,
        "login_at": now,
        "last_seen_at": now,
        "last_pin_at": now,
    }
    session["lector_auth"] = lector
    session.permanent = True
    registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True, "data": {"uid": lector["uid"], "nombre": lector["nombre"], "rol": lector["rol"]}})


@app.route("/api/lector/heartbeat", methods=["POST"])
def api_lector_heartbeat():
    lector, error = require_lector_session()
    if error:
        payload = error[0] if isinstance(error[0], dict) else {"ok": False, "error": "PIN requerido"}
        payload["requires_pin"] = True
        return jsonify(payload), 200
    payload = request.get_json(silent=True) or {}
    if payload.get("device_id"):
        lector["device_id"] = normalize_device_id(payload.get("device_id"))
        session["lector_auth"] = lector
    modo = str(payload.get("modo") or "online").strip().lower()
    registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True})


@app.route("/api/lector/logout", methods=["POST"])
def api_lector_logout():
    data = lector_session_data()
    payload = request.get_json(silent=True) or {}
    device_id = normalize_device_id(payload.get("device_id") or data.get("device_id"))
    if device_id:
        quitar_lector_activo(device_id)
    lector_logout_session()
    return jsonify({"ok": True})


@app.route("/health")
def health():
    return jsonify({"ok": True, "firebase_ready": firebase_ready})


@app.route("/api/lector_estado")
def api_lector_estado():
    lector = lector_session_data()
    if not lector or lector_is_idle(lector):
        if lector and lector_is_idle(lector):
            lector_logout_session()
        cfg = evento_actual_config()
        if not isinstance(cfg, dict):
            cfg = {}
        aforo_max = max(safe_int(cfg.get("aforo_max", 0), 0), 0)
        aforo_actual = max(safe_int(cfg.get("aforo_actual", 0), 0), 0)
        estado = normalize_event_state(cfg.get("estado", "borrador"), "borrador")
        return jsonify(
            {
                "ok": True,
                "data": {
                    "firebase_ready": firebase_ready,
                    "evento_nombre": cfg.get("nombre", "Evento SIGA"),
                    "evento_id": cfg.get("id_evento", ""),
                    "evento_estado": estado,
                    "aforo_actual": aforo_actual,
                    "aforo_max": aforo_max,
                    "lector": {"uid": "", "nombre": "", "rol": ""},
                    "requires_pin": True,
                },
            }
        )

    lector = lector_touch_session()

    modo = "online" if firebase_ready else "local"
    registrar_lector_activo(lector, modo=modo)

    cfg = evento_actual_config()
    if not isinstance(cfg, dict):
        cfg = {}
    aforo_max = max(safe_int(cfg.get("aforo_max", 0), 0), 0)
    aforo_actual = max(safe_int(cfg.get("aforo_actual", 0), 0), 0)
    estado = normalize_event_state(cfg.get("estado", "borrador"), "borrador")
    return jsonify(
        {
            "ok": True,
            "data": {
                "firebase_ready": firebase_ready,
                "evento_nombre": cfg.get("nombre", "Evento SIGA"),
                "evento_id": cfg.get("id_evento", ""),
                "evento_estado": estado,
                "aforo_actual": aforo_actual,
                "aforo_max": aforo_max,
                "lector": {
                    "uid": lector.get("uid", ""),
                    "nombre": lector.get("nombre", ""),
                    "rol": lector.get("rol", ""),
                },
                "requires_pin": False,
            },
        }
    )


@app.route("/api/dashboard")
def api_dashboard():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    event_id = request.args.get("event_id")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    return jsonify({"ok": True, "data": construir_dashboard_data(event_id=event_id, desde=desde, hasta=hasta)})


@app.route("/api/sync/retry", methods=["POST"])
def api_sync_retry():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    sync_meta["last_attempt"] = now_iso()
    try:
        stats = sincronizar_pendientes()
        if stats.get("failed", 0) == 0:
            sync_meta["last_success"] = now_iso()
            sync_meta["last_error"] = None
        else:
            sync_meta["last_error"] = f"Fallos de sincronización: {stats.get('failed', 0)}"
        return jsonify({"ok": True, "stats": stats, "last_success": sync_meta.get("last_success"), "last_error": sync_meta.get("last_error")})
    except Exception as exc:
        sync_meta["last_error"] = str(exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/admin_state")
def api_admin_state():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    return jsonify({"ok": True, "data": construir_admin_state()})


@app.route("/api/configuracion/evento_actual", methods=["PUT"])
def api_actualizar_evento_actual():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    payload = request.get_json(silent=True) or {}
    permitido = {
        "id_evento",
        "nombre",
        "ubicacion",
        "aforo_max",
        "aforo_actual",
        "estado",
        "fecha_inicio",
        "fecha_fin",
        "timezone",
    }
    update = {k: v for k, v in payload.items() if k in permitido}
    if "estado" in update:
        update["estado"] = normalize_event_state(update.get("estado"), "borrador")
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400
    ref = db.reference("configuracion/evento_actual")
    before = ref.get() or {}
    ref.update(update)
    after = ref.get() or {}
    audit_evento("configuracion.evento_actual", str(after.get("id_evento", "")), "update_config", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})
    return jsonify({"ok": True})


@app.route("/api/invitados", methods=["GET", "POST"])
def api_invitados():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = leer_invitados()

    if request.method == "GET":
        do_paginate = not parse_bool_param(request.args.get("all"))
        paged = filtrar_y_paginar_invitados(invitados, request.args, paginate=do_paginate)
        return jsonify({"ok": True, "data": paged})

    data = request.get_json(silent=True) or {}
    # Alta inicial siempre con cupo base fijo.
    data["cupo_total"] = MIN_CUPO_TOTAL
    payload, error = validar_datos_invitado(data, invitados, exclude_key=None, require_required=True)
    if error:
        status = 409 if error.get("field") == "duplicate" else 400
        return jsonify({"ok": False, "error": error}), status

    invitado_id = payload["id"]
    key = generar_hash_qr(invitado_id)
    if key in invitados:
        return jsonify({"ok": False, "error": {"field": "duplicate", "message": "Invitado ya existe", "conflict": {"id_conflict_key": key}}}), 409

    payload["creado_en"] = now_iso()
    db.reference(f"invitados/{key}").set(payload)
    return jsonify({"ok": True, "key": key, "invitado": payload})


@app.route("/api/invitados/<invitado_key>", methods=["PUT"])
def api_actualizar_invitado(invitado_key: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = leer_invitados()
    actual = invitados.get(invitado_key)
    if not isinstance(actual, dict):
        return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404

    body = request.get_json(silent=True) or {}
    candidato = dict(actual)
    allowed_inline = {"nombre", "nombre_lider", "email", "cupo_total", "tipo_invitado", "bloqueado"}
    has_change = False
    for field in allowed_inline:
        if field in body:
            candidato[field] = body[field]
            has_change = True
    if not has_change:
        return jsonify({"ok": False, "error": "Sin campos válidos para edición inline"}), 400

    payload, error = validar_datos_invitado(candidato, invitados, exclude_key=invitado_key, require_required=True)
    if error:
        status = 409 if error.get("field") == "duplicate" else 400
        return jsonify({"ok": False, "error": error}), status

    update = {
        "nombre": payload["nombre"],
        "nombre_lider": payload["nombre_lider"],
        "email": payload["email"],
        "cupo_total": payload["cupo_total"],
        "tipo_invitado": payload["tipo_invitado"],
        "bloqueado": payload["bloqueado"],
    }
    db.reference(f"invitados/{invitado_key}").update(update)
    return jsonify({"ok": True, "updated": update})


@app.route("/api/invitados/<invitado_key>", methods=["DELETE"])
def api_eliminar_invitado(invitado_key: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    db.reference(f"invitados/{invitado_key}").delete()
    return jsonify({"ok": True})


@app.route("/api/invitados/import", methods=["POST"])
def api_importar_invitados():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Archivo requerido"}), 400

    filename = file.filename.lower()
    rows = []
    try:
        if filename.endswith(".csv"):
            text = file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        elif filename.endswith(".xlsx"):
            try:
                from openpyxl import load_workbook
            except Exception:
                return jsonify({"ok": False, "error": "openpyxl no instalado para importar .xlsx"}), 500
            wb = load_workbook(file, read_only=True, data_only=True)
            ws = wb.active
            header = None
            for row in ws.iter_rows(values_only=True):
                if header is None:
                    header = [str(x or "").strip() for x in row]
                    continue
                values = [x if x is not None else "" for x in row]
                rows.append({header[i]: values[i] if i < len(values) else "" for i in range(len(header))})
        else:
            return jsonify({"ok": False, "error": "Formato no soportado. Usa CSV o XLSX"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"No se pudo leer archivo: {exc}"}), 400

    invitados = leer_invitados()
    id_index, email_index = invitados_indexes(invitados)
    inserted = 0
    duplicated = 0
    invalid = 0
    errors = []

    def get_col(row: dict, *keys: str) -> Any:
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        return ""

    for idx, row in enumerate(rows, start=2):
        row_data = {
            "id": get_col(row, "id", "ID", "Id"),
            "nombre": get_col(row, "nombre", "Nombre", "nombre_lider", "Nombre_lider"),
            "email": get_col(row, "email", "Email", "correo", "Correo"),
            # En importación también se crea con cupo base fijo.
            "cupo_total": MIN_CUPO_TOTAL,
            "tipo_invitado": row.get("tipo_invitado", "general"),
            "grupo_nombre": row.get("grupo_nombre", ""),
            "bloqueado": parse_bool_param(str(row.get("bloqueado", ""))) is True,
            "invitacion_enviada": parse_bool_param(str(row.get("invitacion_enviada", ""))) is True,
        }

        payload, error = validar_datos_invitado(row_data, invitados, exclude_key=None, require_required=True)
        if error:
            if error.get("field") == "duplicate":
                duplicated += 1
            else:
                invalid += 1
            errors.append({"row": idx, "id": row_data.get("id", ""), "email": row_data.get("email", ""), "error": error.get("message", "Error")})
            continue

        id_norm = payload["id"].lower()
        email_norm = payload["email"]
        if id_norm in id_index or email_norm in email_index:
            duplicated += 1
            errors.append({"row": idx, "id": payload["id"], "email": payload["email"], "error": "Duplicado en base o en archivo"})
            continue

        key = generar_hash_qr(payload["id"])
        payload["creado_en"] = now_iso()
        db.reference(f"invitados/{key}").set(payload)
        invitados[key] = payload
        id_index[id_norm] = key
        email_index[email_norm] = key
        inserted += 1

    error_csv = ""
    if errors:
        s = io.StringIO()
        w = csv.writer(s)
        w.writerow(["row", "id", "email", "error"])
        for e in errors:
            w.writerow([e["row"], e["id"], e["email"], e["error"]])
        error_csv = s.getvalue()

    return jsonify(
        {
            "ok": True,
            "summary": {
                "total_rows": len(rows),
                "inserted": inserted,
                "duplicated": duplicated,
                "invalid": invalid,
                "errors": len(errors),
            },
            "errors": errors[:200],
            "error_report_csv": error_csv,
        }
    )


@app.route("/api/invitados/batch", methods=["POST"])
def api_invitados_batch():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip().lower()
    scope = str(data.get("scope", "selected")).strip().lower()
    keys = data.get("keys") or []
    filters = data.get("filters") or {}

    if action not in {"bloquear", "desbloquear", "enviar_invitacion", "exportar"}:
        return jsonify({"ok": False, "error": "Acción inválida"}), 400
    if scope not in {"selected", "filtered"}:
        return jsonify({"ok": False, "error": "Scope inválido"}), 400

    invitados = leer_invitados()
    target_keys = obtener_keys_lote(invitados, scope, keys, filters)
    if not target_keys:
        return jsonify({"ok": False, "error": "Sin invitados seleccionados"}), 400

    if action == "exportar":
        if scope == "selected":
            return jsonify({"ok": True, "export_url": f"/api/invitados/export?{urlencode({'keys': ','.join(target_keys)})}"})
        params = {}
        for k in ("q", "bloqueado", "pendiente", "tipo"):
            v = str(filters.get(k, "")).strip()
            if v:
                params[k] = v
        query = urlencode(params)
        return jsonify({"ok": True, "export_url": f"/api/invitados/export?{query}"})

    if action in {"bloquear", "desbloquear"}:
        flag = action == "bloquear"
        for key in target_keys:
            db.reference(f"invitados/{key}").update({"bloqueado": flag})
        return jsonify({"ok": True, "updated": len(target_keys), "action": action})

    # enviar_invitacion
    client, smtp_error = smtp_client()
    if smtp_error:
        return jsonify({"ok": False, "error": smtp_error}), 500

    sent = 0
    failed = 0
    results = []
    try:
        for key in target_keys:
            invitado = invitados.get(key)
            if not isinstance(invitado, dict):
                failed += 1
                continue
            err = enviar_invitacion_email(client, invitado, key)
            if err:
                failed += 1
                results.append({"key": key, "id": invitado.get("id"), "ok": False, "error": err})
                continue
            sent += 1
            db.reference(f"invitados/{key}").update({"invitacion_enviada": True})
            results.append({"key": key, "id": invitado.get("id"), "ok": True})
    finally:
        try:
            client.close()
        except Exception:
            pass

    return jsonify({"ok": True, "action": action, "sent": sent, "failed": failed, "results": results})


@app.route("/api/invitados/export")
def api_exportar_invitados():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = leer_invitados()
    keys_param = str(request.args.get("keys", "")).strip()
    if keys_param:
        keys = [k for k in keys_param.split(",") if k in invitados]
        rows = [item for item in invitados_listado(invitados) if item["key"] in keys]
    else:
        rows = filtrar_y_paginar_invitados(invitados, request.args, paginate=False)["items"]

    csv_text = generar_csv_invitados(rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=invitados_export_{int(time.time())}.csv"},
    )


@app.route("/api/solicitudes_cupo", methods=["GET", "POST"])
def api_solicitudes_cupo():
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    if request.method == "GET":
        if not admin_logueado():
            return jsonify({"ok": False, "error": "No autorizado"}), 401
        status_filter = str(request.args.get("status", "")).strip().lower()
        limit = max(1, min(safe_int(request.args.get("limit", 100), 100), 300))
        rows = solicitudes_cupo_listado(leer_solicitudes_cupo())
        if status_filter:
            rows = [x for x in rows if str(x.get("status", "")).lower() == status_filter]
        return jsonify({"ok": True, "data": {"items": rows[:limit], "total": len(rows)}})

    solicitante = None
    if admin_logueado():
        solicitante = {
            "uid": actor_admin(),
            "nombre": actor_admin(),
            "origen": "admin",
        }
    else:
        lector, error = require_lector_session()
        if error:
            return jsonify(error[0]), error[1]
        solicitante = {
            "uid": str(lector.get("uid", "")).strip(),
            "nombre": str(lector.get("nombre", "")).strip(),
            "origen": "lector",
        }

    payload = request.get_json(silent=True) or {}
    invitado_id = str(payload.get("invitado_id", "")).strip()
    invitado_key_input = str(payload.get("invitado_key", "")).strip()
    cantidad_solicitada = max(safe_int(payload.get("cantidad_solicitada", 1), 1), 1)
    motivo = str(payload.get("motivo", "")).strip()

    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    invitado_key, invitado = buscar_invitado(invitado_id, invitado_key_input or None)
    if not invitado_key or not isinstance(invitado, dict):
        return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404

    solicitudes = leer_solicitudes_cupo()
    if existe_solicitud_pendiente(solicitudes, invitado_key):
        return jsonify({"ok": False, "error": "Ya existe una solicitud pendiente para este invitado", "code": "SOLICITUD_DUPLICADA"}), 409

    invitados = leer_invitados()
    disponibilidad = resumen_disponibilidad_cupo(invitados)
    disponibles = max(safe_int(disponibilidad.get("boletos_disponibles"), 0), 0)
    if disponibles <= 0:
        return jsonify(
            {
                "ok": False,
                "error": "No hay disponibilidad de aforo para asignar más cupo",
                "code": "AFORO_SIN_DISPONIBILIDAD",
                "aforo": disponibilidad,
            }
        ), 409
    if cantidad_solicitada > disponibles:
        return jsonify(
            {
                "ok": False,
                "error": f"Solo hay {disponibles} boletos disponibles antes de alcanzar el aforo máximo",
                "code": "SOLICITUD_EXCEDE_AFORO",
                "aforo": disponibilidad,
            }
        ), 409

    registro = {
        "invitado_id": invitado_id,
        "invitado_key": invitado_key,
        "nombre_invitado": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
        "cantidad_solicitada": cantidad_solicitada,
        "cantidad_aprobada": 0,
        "status": "pendiente",
        "motivo": motivo,
        "solicitado_por_uid": solicitante["uid"],
        "solicitado_por_nombre": solicitante["nombre"],
        "solicitado_desde": solicitante["origen"],
        "created_at": now_iso(),
        "resolved_at": "",
        "resolved_by": "",
        "decision_note": "",
    }
    ref = db.reference("solicitudes_cupo").push(registro)
    solicitud_id = str(ref.key or "").strip()
    return jsonify({"ok": True, "solicitud": {"id": solicitud_id, **registro}, "aforo": disponibilidad})


@app.route("/api/solicitudes_cupo/<solicitud_id>/resolver", methods=["POST"])
def api_resolver_solicitud_cupo(solicitud_id: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    solicitud_id = str(solicitud_id or "").strip()
    if not solicitud_id:
        return jsonify({"ok": False, "error": "solicitud_id requerido"}), 400

    payload = request.get_json(silent=True) or {}
    accion = str(payload.get("accion", "aprobar")).strip().lower()
    decision_note = str(payload.get("decision_note", "")).strip()
    if accion not in {"aprobar", "rechazar"}:
        return jsonify({"ok": False, "error": "Acción inválida"}), 400

    solicitud_ref = db.reference(f"solicitudes_cupo/{solicitud_id}")
    solicitud = solicitud_ref.get() or {}
    if not isinstance(solicitud, dict):
        return jsonify({"ok": False, "error": "Solicitud no encontrada"}), 404

    status_actual = str(solicitud.get("status", "pendiente")).strip().lower()
    if status_actual != "pendiente":
        return jsonify({"ok": False, "error": f"La solicitud ya fue procesada ({status_actual})"}), 409

    if accion == "rechazar":
        update = {
            "status": "rechazada",
            "resolved_at": now_iso(),
            "resolved_by": actor_admin(),
            "decision_note": decision_note,
            "cantidad_aprobada": 0,
        }
        solicitud_ref.update(update)
        return jsonify({"ok": True, "solicitud": {"id": solicitud_id, **solicitud, **update}})

    cantidad_solicitada = max(safe_int(solicitud.get("cantidad_solicitada", 1), 1), 1)
    cantidad_aprobada = safe_int(payload.get("cantidad_aprobada", cantidad_solicitada), cantidad_solicitada)
    cantidad_aprobada = max(cantidad_aprobada, 1)
    if cantidad_aprobada > cantidad_solicitada:
        return jsonify({"ok": False, "error": "cantidad_aprobada no puede ser mayor a cantidad_solicitada"}), 400

    invitado_key = str(solicitud.get("invitado_key", "")).strip()
    invitado_id = str(solicitud.get("invitado_id", "")).strip()
    invitado_key_found, invitado = buscar_invitado(invitado_id, invitado_key or None)
    if not invitado_key_found or not isinstance(invitado, dict):
        return jsonify({"ok": False, "error": "Invitado asociado no encontrado"}), 404

    invitados = leer_invitados()
    disponibilidad = resumen_disponibilidad_cupo(invitados)
    disponibles = max(safe_int(disponibilidad.get("boletos_disponibles"), 0), 0)
    if disponibles <= 0:
        return jsonify(
            {
                "ok": False,
                "error": "No hay disponibilidad de aforo para aprobar esta solicitud",
                "code": "AFORO_SIN_DISPONIBILIDAD",
                "aforo": disponibilidad,
            }
        ), 409
    if cantidad_aprobada > disponibles:
        return jsonify(
            {
                "ok": False,
                "error": f"Solo hay {disponibles} boletos disponibles para aprobar",
                "code": "APROBACION_EXCEDE_AFORO",
                "aforo": disponibilidad,
            }
        ), 409

    cupo_total_actual = max(safe_int(invitado.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), MIN_CUPO_TOTAL)
    nuevo_cupo_total = cupo_total_actual + cantidad_aprobada
    db.reference(f"invitados/{invitado_key_found}").update({"cupo_total": nuevo_cupo_total})

    update = {
        "status": "aprobada",
        "cantidad_aprobada": cantidad_aprobada,
        "resolved_at": now_iso(),
        "resolved_by": actor_admin(),
        "decision_note": decision_note,
    }
    solicitud_ref.update(update)
    return jsonify(
        {
            "ok": True,
            "solicitud": {"id": solicitud_id, **solicitud, **update},
            "invitado": {
                "key": invitado_key_found,
                "id": invitado_id,
                "nombre": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
                "cupo_total_anterior": cupo_total_actual,
                "cupo_total_nuevo": nuevo_cupo_total,
            },
        }
    )


@app.route("/api/eventos", methods=["GET", "POST"])
def api_eventos():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if request.method == "GET":
        items = eventos_listado(leer_eventos())
        active_id = active_event_id_from_rows(items)
        for item in items:
            item["is_active"] = item.get("id_evento") == active_id
        return jsonify({"ok": True, "data": {"items": items, "active_event_id": active_id}})

    payload = request.get_json(silent=True) or {}
    event_id = str(payload.get("id_evento", "")).strip() or f"ev_{uuid4().hex[:8]}"
    registro = {
        "id_evento": event_id,
        "nombre": payload.get("nombre", "Evento SIGA"),
        "ubicacion": payload.get("ubicacion", ""),
        "aforo_max": max(safe_int(payload.get("aforo_max", 0), 0), 0),
        "aforo_actual": max(safe_int(payload.get("aforo_actual", 0), 0), 0),
        # Estado operativo cambia solo por endpoints publish/close.
        "estado": "borrador",
        "fecha_inicio": payload.get("fecha_inicio", ""),
        "fecha_fin": payload.get("fecha_fin", ""),
        "timezone": payload.get("timezone", "America/Mexico_City"),
        "created_at": now_iso(),
    }
    db.reference(f"eventos/{event_id}").set(registro)
    audit_evento("evento", event_id, "create", {}, registro)
    return jsonify({"ok": True, "evento": registro})


@app.route("/api/eventos/<event_id>", methods=["PUT"])
def api_actualizar_evento(event_id: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    payload = request.get_json(silent=True) or {}
    permitido = {"nombre", "ubicacion", "aforo_max", "aforo_actual", "fecha_inicio", "fecha_fin", "timezone"}
    update = {k: v for k, v in payload.items() if k in permitido}
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400
    if "aforo_max" in update:
        update["aforo_max"] = max(safe_int(update.get("aforo_max"), 0), 0)
    if "aforo_actual" in update:
        update["aforo_actual"] = max(safe_int(update.get("aforo_actual"), 0), 0)
    ref = db.reference(f"eventos/{event_id}")
    before = ref.get() or {}
    if not isinstance(before, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404
    ref.update(update)
    after = ref.get() or {}
    audit_evento("evento", event_id, "update", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})
    return jsonify({"ok": True})


@app.route("/api/eventos/<event_id>/publish", methods=["POST"])
def api_publicar_evento(event_id: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    eventos_ref = db.reference("eventos")
    all_events = eventos_ref.get() or {}
    if not isinstance(all_events, dict) or event_id not in all_events:
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404

    previous_active = None
    for key, ev in all_events.items():
        if isinstance(ev, dict) and ev.get("estado") == "activo":
            previous_active = key
            break

    if previous_active and previous_active != event_id:
        prev_ref = db.reference(f"eventos/{previous_active}")
        prev_before = prev_ref.get() or {}
        prev_ref.update({"estado": "borrador"})
        prev_after = prev_ref.get() or {}
        audit_evento("evento", previous_active, "demote_to_draft", prev_before if isinstance(prev_before, dict) else {}, prev_after if isinstance(prev_after, dict) else {})

    target_ref = db.reference(f"eventos/{event_id}")
    before = target_ref.get() or {}
    target_ref.update({"estado": "activo"})
    after = target_ref.get() or {}
    audit_evento("evento", event_id, "publish", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})

    evento_cfg = required_event_fields(after if isinstance(after, dict) else {})
    cfg_ref = db.reference("configuracion/evento_actual")
    cfg_before = cfg_ref.get() or {}
    cfg_ref.set(evento_cfg)
    cfg_after = cfg_ref.get() or {}
    audit_evento("configuracion.evento_actual", event_id, "set_active_event", cfg_before if isinstance(cfg_before, dict) else {}, cfg_after if isinstance(cfg_after, dict) else {})
    return jsonify({"ok": True, "active_event_id": event_id})


@app.route("/api/eventos/<event_id>/close", methods=["POST"])
def api_cerrar_evento(event_id: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    ref = db.reference(f"eventos/{event_id}")
    before = ref.get() or {}
    if not isinstance(before, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404
    ref.update({"estado": "cerrado"})
    after = ref.get() or {}
    audit_evento("evento", event_id, "close", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})

    cfg_ref = db.reference("configuracion/evento_actual")
    cfg = cfg_ref.get() or {}
    if isinstance(cfg, dict) and str(cfg.get("id_evento", "")).strip() == event_id:
        cfg_before = dict(cfg)
        cfg["estado"] = "cerrado"
        cfg_ref.set(cfg)
        audit_evento("configuracion.evento_actual", event_id, "close_active_event", cfg_before, cfg)

    # Junior feature: Flush attendees globally when an event is closed to prepare for the next event cleanly
    try:
        db.reference("invitados").delete()
        db.reference("solicitudes_cupo").delete()
    except Exception as exc:
        print(f"[WARN] No se pudo limpiar invitados al cerrar evento: {exc}")

    return jsonify({"ok": True})


@app.route("/api/eventos/<event_id>/clone", methods=["POST"])
def api_clonar_evento(event_id: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    source = db.reference(f"eventos/{event_id}").get() or {}
    if not isinstance(source, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404

    payload = request.get_json(silent=True) or {}
    new_id = str(payload.get("id_evento", "")).strip() or f"{event_id}_clone_{uuid4().hex[:6]}"
    clone = required_event_fields(source)
    clone.update(
        {
            "id_evento": new_id,
            "nombre": f"{source.get('nombre', 'Evento')} (Copia)",
            "estado": "borrador",
            "aforo_actual": 0,
            "created_at": now_iso(),
        }
    )
    db.reference(f"eventos/{new_id}").set(clone)
    audit_evento("evento", new_id, "clone", {}, clone, extra={"source_event_id": event_id})
    return jsonify({"ok": True, "evento": clone})


@app.route("/api/eventos/audit")
def api_eventos_audit():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    event_id = str(request.args.get("event_id", "")).strip()
    actor = str(request.args.get("actor", "")).strip().lower()
    desde = parse_timestamp(request.args.get("desde")) if request.args.get("desde") else None
    hasta = parse_timestamp(request.args.get("hasta")) if request.args.get("hasta") else None

    raw = db.reference("auditoria/eventos").order_by_key().limit_to_last(500).get() or {}
    rows = list(raw.values()) if isinstance(raw, dict) else []
    rows_sorted = sorted(rows, key=lambda x: parse_timestamp((x or {}).get("timestamp")), reverse=True)

    out = []
    for item in rows_sorted:
        if not isinstance(item, dict):
            continue
        ts = parse_timestamp(item.get("timestamp"))
        if desde and ts < desde:
            continue
        if hasta and ts > hasta:
            continue
        if event_id and str(item.get("entity_id", "")).strip() != event_id:
            continue
        if actor and str(item.get("actor", "")).strip().lower() != actor:
            continue
        out.append(item)
    return jsonify({"ok": True, "data": {"items": out}})


@app.route("/api/usuarios_staff", methods=["POST"])
def api_crear_staff():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    payload = request.get_json(silent=True) or {}
    uid = str(payload.get("uid", "")).strip() or f"uid_{uuid4().hex[:8]}"
    rol = str(payload.get("rol", "lector")).strip().lower()
    pin = normalize_pin(payload.get("pin", ""))

    if pin and not is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos"}), 400
    if rol in {"lector", "supervisor"} and not is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN requerido para lectores/supervisores (6 dígitos)"}), 400
    if pin_exists_in_staff(pin):
        return jsonify({"ok": False, "error": "PIN ya asignado a otro usuario"}), 409

    registro = {
        "nombre": payload.get("nombre", ""),
        "rol": rol,
        "email": payload.get("email", ""),
        "pin": pin,
        "activo": bool(payload.get("activo", True)),
        "ultimo_login": payload.get("ultimo_login", ""),
        "permisos": payload.get("permisos", {}),
    }
    if not registro["nombre"] or not registro["email"]:
        return jsonify({"ok": False, "error": "nombre y email son requeridos"}), 400
    db.reference(f"usuarios_staff/{uid}").set(registro)
    return jsonify({"ok": True, "uid": uid, "staff": registro})


@app.route("/api/usuarios_staff/<uid>", methods=["PUT"])
def api_actualizar_staff(uid: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    current = db.reference(f"usuarios_staff/{uid}").get() or {}
    if not isinstance(current, dict):
        return jsonify({"ok": False, "error": "Usuario staff no encontrado"}), 404

    payload = request.get_json(silent=True) or {}
    permitido = {"nombre", "rol", "email", "pin", "activo", "ultimo_login", "permisos"}
    update = {k: v for k, v in payload.items() if k in permitido}
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400

    effective_role = str(update.get("rol", current.get("rol", "lector"))).strip().lower()

    if "pin" in update:
        pin = normalize_pin(update.get("pin", ""))
        if pin and not is_valid_pin(pin):
            return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos"}), 400
        if effective_role in {"lector", "supervisor"} and not is_valid_pin(pin):
            return jsonify({"ok": False, "error": "PIN requerido para lectores/supervisores (6 dígitos)"}), 400
        if pin_exists_in_staff(pin, exclude_uid=uid):
            return jsonify({"ok": False, "error": "PIN ya asignado a otro usuario"}), 409
        update["pin"] = pin
    elif "rol" in update:
        current_pin = normalize_pin(current.get("pin", ""))
        if effective_role in {"lector", "supervisor"} and not is_valid_pin(current_pin):
            return jsonify({"ok": False, "error": "Este usuario requiere un PIN de 6 dígitos para cambiar a ese rol"}), 400

    if "rol" in update:
        update["rol"] = effective_role

    db.reference(f"usuarios_staff/{uid}").update(update)
    return jsonify({"ok": True})


@app.route("/api/usuarios_staff/<uid>", methods=["DELETE"])
def api_eliminar_staff(uid: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    db.reference(f"usuarios_staff/{uid}").delete()
    return jsonify({"ok": True})


@app.route("/api/lectores/<uid>/disconnect", methods=["POST"])
def api_desconectar_lector(uid: str):
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    uid = str(uid or "").strip()
    if not uid:
        return jsonify({"ok": False, "error": "uid requerido"}), 400

    raw = db.reference("lectores_activos").get() or {}
    if not isinstance(raw, dict):
        return jsonify({"ok": True, "removed": 0})

    removed = 0
    for device_id, item in raw.items():
        if not isinstance(item, dict):
            continue
        if str(item.get("staff_uid", "")).strip() != uid:
            continue
        try:
            db.reference(f"lectores_activos/{device_id}").delete()
            removed += 1
        except Exception:
            pass

    return jsonify({"ok": True, "removed": removed})


@app.route("/api/reportes")
def api_reportes():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    return jsonify({"ok": True, "data": construir_reporte_data(desde, hasta)})


@app.route("/api/reportes/export")
def api_reportes_export():
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    fmt = str(request.args.get("format", "csv")).strip().lower()
    data = construir_reporte_data(desde, hasta)

    if fmt == "csv":
        text = reporte_csv(data)
        return Response(
            text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=reporte_siga_{int(time.time())}.csv"},
        )

    if fmt == "pdf":
        try:
            payload = reporte_pdf_bytes(data, desde, hasta)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return Response(
            payload,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=reporte_siga_{int(time.time())}.pdf"},
        )

    return jsonify({"ok": False, "error": "Formato no soportado. Usa csv o pdf"}), 400


# =========================
# API
# =========================
@app.route("/validar_qr", methods=["POST"])
def validar_qr():
    lector, error = require_lector_session()
    if error:
        return jsonify(error[0]), error[1]

    data = request.get_json(silent=True) or {}
    imagen_b64 = data.get("imagen_base64", "")

    if not imagen_b64:
        return jsonify({"ok": False, "error": "imagen_base64 requerida"}), 400

    try:
        if "," in imagen_b64:
            imagen_b64 = imagen_b64.split(",", 1)[1]

        imagen_bytes = base64.b64decode(imagen_b64)
        np_buffer = np.frombuffer(imagen_bytes, np.uint8)
        imagen_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    except Exception:
        return jsonify({"ok": False, "error": "Imagen inválida"}), 400

    if imagen_bgr is None:
        return jsonify({"ok": False, "error": "No se pudo decodificar imagen"}), 400

    payload, fase = pipeline_decodificacion(imagen_bgr)
    event_id, event_cfg = estado_evento_activo()
    evento_estado = str((event_cfg or {}).get("estado", "borrador")).strip().lower()

    if not payload:
        evento = append_lector_to_log({"evento": "qr_no_leido", "fase_exitosa": None, "id_evento": event_id}, lector)
        guardar_log(evento)
        return jsonify({"ok": False, "error": "QR no legible", "fase_exitosa": None}), 400

    invitado_id, hash_qr = extraer_datos_qr(payload)
    if not invitado_id:
        evento = append_lector_to_log({"evento": "qr_formato_invalido", "payload": payload, "fase_exitosa": fase, "id_evento": event_id}, lector)
        guardar_log(evento)
        return jsonify({"ok": False, "error": "Formato de QR inválido", "fase_exitosa": fase}), 400

    if not validar_hash_qr(invitado_id, hash_qr):
        evento = append_lector_to_log(
            {
            "evento": "qr_hash_invalido",
            "invitado_id": invitado_id,
            "fase_exitosa": fase,
            "id_evento": event_id,
            },
            lector,
        )
        guardar_log(evento)
        return jsonify({"ok": False, "error": "Hash inválido", "fase_exitosa": fase}), 401

    invitado_key, invitado = buscar_invitado(invitado_id, hash_qr)

    if not invitado:
        evento = append_lector_to_log(
            {
            "evento": "qr_valido_sin_registro",
            "invitado_id": invitado_id,
            "fase_exitosa": fase,
            "id_evento": event_id,
            },
            lector,
        )
        guardar_log(evento)
        return jsonify(
            {
                "ok": True,
                "valido": True,
                "fase_exitosa": fase,
                "invitado_id": invitado_id,
                "invitado": None,
                "mensaje": "QR válido, pero invitado no encontrado en Firebase",
                "evento_id": event_id,
                "evento_estado": evento_estado,
                "permite_override_admin": evento_estado == "cerrado",
            }
        )

    evento = append_lector_to_log(
        {
        "evento": "qr_valido",
        "invitado_id": invitado_id,
        "id_evento": event_id,
        "fase_exitosa": fase,
        "fase_pdi": fase,
        "nombre_invitado": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
        },
        lector,
    )
    guardar_log(evento)

    return jsonify(
        {
            "ok": True,
            "valido": True,
            "fase_exitosa": fase,
            "invitado_id": invitado_id,
            "invitado_key": invitado_key,
            "invitado": invitado,
            "evento_id": event_id,
            "evento_estado": evento_estado,
            "permite_override_admin": evento_estado == "cerrado",
        }
    )


@app.route("/registrar_ingreso", methods=["POST"])
def registrar_ingreso():
    """Permite +1, +2 o todos según cupo_total/cupo_usado."""
    lector = None
    if admin_logueado():
        lector = {
            "uid": actor_admin(),
            "nombre": actor_admin(),
            "pin": "",
            "device_id": str((request.get_json(silent=True) or {}).get("device_id", "")).strip(),
        }
    else:
        lector, error = require_lector_session()
        if error:
            return jsonify(error[0]), error[1]

    data = request.get_json(silent=True) or {}
    invitado_id = str(data.get("invitado_id", "")).strip()
    invitado_key_input = str(data.get("invitado_key", "")).strip()
    modo = str(data.get("modo", "1")).strip().lower()  # 1,2,todos
    admin_override = bool(data.get("admin_override", False))

    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    active_event_id, active_event_cfg = estado_evento_activo()
    active_estado = str((active_event_cfg or {}).get("estado", "borrador")).strip().lower()

    if admin_override and not admin_logueado():
        pin_confirm = str(data.get("pin_confirm", "")).strip()
        if not pin_confirm:
            return jsonify({"ok": False, "error": "PIN requerido para override", "code": "PIN_CONFIRM_REQUIRED"}), 403
        if pin_confirm != str((lector or {}).get("pin", "")):
            return jsonify({"ok": False, "error": "PIN inválido para override", "code": "PIN_CONFIRM_INVALID"}), 403
        lector_touch_session(update_pin_time=True)

    if active_estado == "cerrado" and not admin_override:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Evento cerrado: solo admin con override puede registrar ingresos",
                    "code": "EVENT_CLOSED",
                    "evento_id": active_event_id,
                    "evento_estado": active_estado,
                }
            ),
            423,
        )

    try:
        invitado_key, invitado = buscar_invitado(invitado_id, invitado_key_input or None)
        if not invitado:
            return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404
        ref = db.reference(f"invitados/{invitado_key}")

        cupo_total = int(invitado.get("cupo_total", MIN_CUPO_TOTAL))
        usados = int(invitado.get("cupo_usado", invitado.get("ingresados", 0)))

        disponibles = max(cupo_total - usados, 0)
        if disponibles <= 0:
            return jsonify({"ok": False, "error": "Cupo agotado para este invitado"}), 409

        if modo == "todos":
            sumar = disponibles
        elif modo == "2":
            if disponibles < 2:
                return jsonify({"ok": False, "error": "Este invitado no tiene cupo para +2"}), 409
            sumar = 2
        else:
            # Cualquier valor no reconocido se trata como +1.
            sumar = 1

        nuevos_usados = min(usados + sumar, cupo_total)
        ref.update(
            {
                "cupo_usado": nuevos_usados,
                "ingresados": nuevos_usados,  # compatibilidad con esquema anterior
                "status": "dentro" if nuevos_usados > 0 else "fuera",
            }
        )

        # Mantener aforo_actual en configuracion/evento_actual
        try:
            cfg_ref = db.reference("configuracion/evento_actual")
            cfg = cfg_ref.get() or {}
            if isinstance(cfg, dict):
                aforo_actual = safe_int(cfg.get("aforo_actual"), 0)
                delta_real = max(nuevos_usados - usados, 0)
                cfg_ref.update({"aforo_actual": aforo_actual + delta_real})
        except Exception as exc:
            print(f"[WARN] No se pudo actualizar aforo_actual: {exc}")

        evento = append_lector_to_log(
            {
            "evento": "ingreso_registrado",
            "invitado_id": invitado_id,
            "id_evento": active_event_id,
            "nombre_invitado": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
            "modo": modo,
            "sumar": sumar,
            "cantidad_entrada": max(nuevos_usados - usados, 0),
            "ingresados_antes": usados,
            "ingresados_despues": nuevos_usados,
            "cupo_total": cupo_total,
            "fase_pdi": data.get("fase_pdi") or "N/D",
            "modo_conexion": "nube" if firebase_ready else "local",
            "admin_override": admin_override,
            },
            lector,
        )
        guardar_log(evento)

        return jsonify(
            {
                "ok": True,
                "invitado_id": invitado_id,
                "invitado_key": invitado_key,
                "ingresados": nuevos_usados,
                "cupo_usado": nuevos_usados,
                "cupo_total": cupo_total,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/registrar_salida", methods=["POST"])
def registrar_salida():
    """Permite registrar salida de +1, +2 o todos (reduce cupo_usado)."""
    if not admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    data = request.get_json(silent=True) or {}
    invitado_id = str(data.get("invitado_id", "")).strip()
    invitado_key_input = str(data.get("invitado_key", "")).strip()
    modo = str(data.get("modo", "1")).strip().lower()  # 1,2,todos

    if not firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    try:
        invitado_key, invitado = buscar_invitado(invitado_id, invitado_key_input or None)
        if not invitado:
            return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404
        ref = db.reference(f"invitados/{invitado_key}")

        cupo_total = int(invitado.get("cupo_total", MIN_CUPO_TOTAL))
        usados = int(invitado.get("cupo_usado", invitado.get("ingresados", 0)))

        if usados <= 0:
            return jsonify({"ok": False, "error": "No hay ingresos activos para descontar"}), 409

        if modo == "todos":
            restar = usados
        elif modo == "2":
            restar = 2
        else:
            restar = 1

        nuevos_usados = max(usados - restar, 0)
        salida_real = max(usados - nuevos_usados, 0)

        ref.update(
            {
                "cupo_usado": nuevos_usados,
                "ingresados": nuevos_usados,  # compatibilidad con esquema anterior
                "status": "dentro" if nuevos_usados > 0 else "fuera",
            }
        )

        try:
            cfg_ref = db.reference("configuracion/evento_actual")
            cfg = cfg_ref.get() or {}
            if isinstance(cfg, dict):
                aforo_actual = safe_int(cfg.get("aforo_actual"), 0)
                cfg_ref.update({"aforo_actual": max(aforo_actual - salida_real, 0)})
        except Exception as exc:
            print(f"[WARN] No se pudo actualizar aforo_actual en salida: {exc}")

        evento = {
            "evento": "salida_registrada",
            "invitado_id": invitado_id,
            "nombre_invitado": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
            "modo": modo,
            "restar": restar,
            "cantidad_salida": salida_real,
            "ingresados_antes": usados,
            "ingresados_despues": nuevos_usados,
            "cupo_total": cupo_total,
            "fase_pdi": data.get("fase_pdi") or "N/D",
            "modo_conexion": "nube" if firebase_ready else "local",
        }
        guardar_log(evento)

        return jsonify(
            {
                "ok": True,
                "invitado_id": invitado_id,
                "invitado_key": invitado_key,
                "ingresados": nuevos_usados,
                "cupo_usado": nuevos_usados,
                "cupo_total": cupo_total,
                "cantidad_salida": salida_real,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    init_firebase()
    ensure_pendientes_file()

    hilo_sync = threading.Thread(target=worker_sincronizacion, daemon=True)
    hilo_sync.start()
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"

    # Soporte local SSL con mkcert. Si no hay certs, usa HTTP normal.
    cert_file = os.getenv("LOCAL_SSL_CERT", "certs/localhost.pem")
    key_file = os.getenv("LOCAL_SSL_KEY", "certs/localhost-key.pem")

    if os.path.exists(cert_file) and os.path.exists(key_file):
        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False, ssl_context=(cert_file, key_file))
    else:
        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
