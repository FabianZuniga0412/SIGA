import os
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, db
import funciones_extras
import sync

firebase_ready = False
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "")
FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase-service-account.json")
MIN_CUPO_TOTAL = 3

def init_firebase():
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

def lector_lockout_ref(device_id):
    return db.reference(f"seguridad/lector_pin_lockouts/{funciones_extras.normalize_device_id(device_id)}")

def leer_lectores_activos():
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
        last_seen = funciones_extras.parse_timestamp(item.get("last_seen_at"))
        delta = (now_dt - last_seen).total_seconds()
        if delta > max(funciones_extras.LECTOR_ACTIVE_WINDOW_SECONDS, 30):
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
    return sorted(out, key=lambda x: funciones_extras.parse_timestamp(x.get("timestamp")), reverse=True)

def registrar_lector_activo(lector, modo = "online"):
    if not firebase_ready:
        return
    device_id = funciones_extras.normalize_device_id(lector.get("device_id"))
    payload = {
        "device_id": device_id,
        "staff_uid": str(lector.get("uid") or ""),
        "staff_nombre": str(lector.get("nombre") or ""),
        "pin": str(lector.get("pin") or ""),
        "rol": str(lector.get("rol") or "lector"),
        "modo": "local" if str(modo).strip().lower() == "local" else "online",
        "last_seen_at": funciones_extras.now_iso(),
    }
    try:
        db.reference(f"lectores_activos/{device_id}").set(payload)
    except Exception as exc:
        print(f"[WARN] No se pudo registrar lector activo: {exc}")

def quitar_lector_activo(device_id):
    if not firebase_ready:
        return
    did = funciones_extras.normalize_device_id(device_id)
    try:
        db.reference(f"lectores_activos/{did}").delete()
    except Exception as exc:
        print(f"[WARN] No se pudo quitar lector activo: {exc}")

def leer_invitados():
    if not firebase_ready:
        return {}
    try:
        invitados = db.reference("invitados").get() or {}
        return invitados if isinstance(invitados, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer invitados: {exc}")
        return {}

def total_boletos_entregados(invitados):
    total = 0
    for item in invitados.values():
        if not isinstance(item, dict):
            continue
        total += max(funciones_extras.safe_int(item.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL), 0)
    return total

def resumen_disponibilidad_cupo(invitados = None):
    invitados_data = invitados if isinstance(invitados, dict) else leer_invitados()
    entregados = total_boletos_entregados(invitados_data)
    cfg = evento_actual_config()
    aforo_max = max(funciones_extras.safe_int((cfg or {}).get("aforo_max", 0), 0), 0)
    disponibles = max(aforo_max - entregados, 0)
    return {
        "aforo_max": aforo_max,
        "boletos_entregados": entregados,
        "boletos_disponibles": disponibles,
    }

def leer_solicitudes_cupo():
    if not firebase_ready:
        return {}
    try:
        data = db.reference("solicitudes_cupo").get() or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer solicitudes_cupo: {exc}")
        return {}

def buscar_invitado(invitado_id, hash_qr = None):
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

def leer_logs(limit = 400):
    logs = []

    if firebase_ready:
        try:
            raw = db.reference("logs").order_by_key().limit_to_last(limit).get() or {}
            if isinstance(raw, dict):
                logs.extend(raw.values())
        except Exception as exc:
            print(f"[WARN] No se pudieron leer logs de Firebase: {exc}")

    if True:  # Lock quitado para simplificar
        pendientes = sync.leer_pendientes()
    logs.extend(pendientes)

    return [log for log in logs if isinstance(log, dict)]

def leer_configuracion():
    if not firebase_ready:
        return {}
    try:
        cfg = db.reference("configuracion").get() or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer configuracion: {exc}")
        return {}

def leer_eventos():
    if not firebase_ready:
        return {}
    try:
        eventos = db.reference("eventos").get() or {}
        return eventos if isinstance(eventos, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudieron leer eventos: {exc}")
        return {}

def leer_staff():
    if not firebase_ready:
        return {}
    try:
        staff = db.reference("usuarios_staff").get() or {}
        return staff if isinstance(staff, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer usuarios_staff: {exc}")
        return {}

def evento_actual_config():
    if not firebase_ready:
        return {}
    try:
        data = db.reference("configuracion/evento_actual").get() or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[WARN] No se pudo leer evento_actual: {exc}")
        return {}

def estado_evento_activo():
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
