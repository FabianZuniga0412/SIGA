import os
import hashlib
import tempfile
import io
import csv
import time
import re
import unicodedata
from zoneinfo import ZoneInfo
import yagmail
import qrcode
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4
from flask import session
import firebase
import sync

# Global config variables
SALT_SECRETO = os.getenv("QR_SALT_SECRETO", "CAMBIA_ESTE_SALT")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PASSWORD_HASH = hashlib.sha512((ADMIN_PASSWORD + SALT_SECRETO).encode("utf-8")).hexdigest()
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SIGA")
VALID_EVENT_STATES = {"borrador", "activo", "cerrado"}
MIN_CUPO_TOTAL = 3
LECTOR_IDLE_TIMEOUT_SECONDS = 900
LECTOR_MAX_PIN_ATTEMPTS = 5
LECTOR_LOCKOUT_SECONDS = 300
LECTOR_ACTIVE_WINDOW_SECONDS = 120

def safe_int(value, default = 0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def parse_bool_param(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("true", "1", "si", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None

def pin_exists_in_staff(pin, exclude_uid = ""):
    pin = normalize_pin(pin)
    if not pin:
        return False
    staff = firebase.leer_staff()
    for uid, row in staff.items():
        if not isinstance(row, dict):
            continue
        if exclude_uid and str(uid) == str(exclude_uid):
            continue
        if normalize_pin(row.get("pin")) == pin:
            return True
    return False

def normalize_device_id(value):
    raw = str(value or "").strip().lower()
    if not raw:
        raw = f"device_{uuid4().hex[:10]}"
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    out = "".join(ch for ch in raw if ch in allowed)
    return out[:64] or f"device_{uuid4().hex[:10]}"

def staff_listado(staff):
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

def obtener_keys_lote(invitados, scope, keys, filters):
    if scope == "selected":
        return [k for k in keys if k in invitados]
    filtered = filtrar_y_paginar_invitados(invitados, filters, paginate=False)["items"]
    return [item["key"] for item in filtered]

def append_lector_to_log(evento, lector):
    if not isinstance(evento, dict):
        return {}
    if not isinstance(lector, dict):
        return evento
    evento["lector_uid"] = str(lector.get("uid") or "")
    evento["lector_nombre"] = str(lector.get("nombre") or "")
    evento["lector_pin"] = str(lector.get("pin") or "")
    evento["dispositivo_id"] = str(lector.get("device_id") or "")
    return evento

def invitados_listado(invitados):
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
                "tipo_invitado": data.get("tipo_invitado", "general"),
            }
        )
    return sorted(out, key=lambda x: x["id"] or x["key"])

def construir_dashboard_data(event_id = None, desde = None, hasta = None):
    invitados = firebase.leer_invitados()
    logs = firebase.leer_logs(limit=500)
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
    if firebase.firebase_ready:
        try:
            evento_db = firebase.db.reference("configuracion/evento_actual").get() or {}
            if isinstance(evento_db, dict):
                evento = evento_db
        except Exception as exc:
            print(f"[WARN] No se pudo leer configuracion/evento_actual: {exc}")
    aforo_max = safe_int(evento.get("aforo_max"), 0) or cupo_total

    if True:  # Lock quitado para simplificar
        sync_pendientes = sum(1 for item in sync.leer_pendientes() if not item.get("sincronizado"))

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

    lectores = firebase.leer_lectores_activos()
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
    if sync.sync_meta.get("last_error"):
        alerts.append(
            {
                "level": "error",
                "title": "Error de sincronización",
                "message": str(sync.sync_meta.get("last_error")),
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

    eventos = eventos_listado(firebase.leer_eventos())

    return {
        "aforo_actual": ingresados,
        "aforo_maximo": aforo_max,
        "total_invitados_registrados": total_registros,
        "invitados_pendientes": pendientes,
        "sincronizaciones_pendientes": sync_pendientes,
        "ultimos_ingresos": ultimos_ingresos,
        "firebase_ready": firebase.firebase_ready,
        "evento_nombre": evento.get("nombre", "Evento SIGA"),
        "evento_ubicacion": evento.get("ubicacion", ""),
        "eventos_disponibles": eventos,
        "selected_event_id": selected_event_id,
        "filters": {"desde": desde or "", "hasta": hasta or ""},
        "alerts": alerts,
        "ultima_sincronizacion": sync.sync_meta.get("last_success"),
        "ultimo_intento_sync": sync.sync_meta.get("last_attempt"),
        "sync_error": sync.sync_meta.get("last_error"),
        "lectores": {
            "online": lectores_online,
            "local": lectores_local,
            "total": len(lectores),
            "detalle": lectores[:20],
        },
    }

def reporte_csv(data):
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

def solicitudes_cupo_listado(solicitudes):
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

def active_event_id_from_rows(rows):
    for row in rows:
        if not isinstance(row, dict):
            continue
        if normalize_event_state(row.get("estado"), "borrador") == "activo":
            return str(row.get("id_evento", "")).strip()
    return ""

def normalizar_email(value):
    return str(value or "").strip().lower()


def safe_filename_token(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "sin_nombre"

def enviar_invitacion_email(client, invitado, key_hash):
    invitado_id = normalizar_id(invitado.get("id"))
    nombre = invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id
    email = normalizar_email(invitado.get("email"))
    cupo = safe_int(invitado.get("cupo_total", MIN_CUPO_TOTAL), MIN_CUPO_TOTAL)
    qr_payload = f"{invitado_id}|{key_hash}"
    evento = firebase.evento_actual_config() if firebase.firebase_ready else {}
    evento_nombre = str((evento or {}).get("nombre", "")).strip() or "SIGA"
    evento_ubicacion = str((evento or {}).get("ubicacion", "")).strip() or "Por confirmar"
    evento_timezone = str((evento or {}).get("timezone", "America/Mexico_City")).strip() or "America/Mexico_City"
    fecha_inicio = str((evento or {}).get("fecha_inicio", "")).strip()
    
    fecha_evento = "Por confirmar"
    hora_evento = "Por confirmar"
    ts_evento = parse_timestamp(fecha_inicio)
    if ts_evento.year > 1900:
        try:
            ts_evento = ts_evento.astimezone(ZoneInfo(evento_timezone))
        except Exception:
            ts_evento = ts_evento.astimezone()
        fecha_evento = ts_evento.strftime("%Y-%m-%d")
        hora_evento = ts_evento.strftime("%H:%M")

    asunto = f"{evento_nombre} - Invitación"
    
    # Generar QR optimizado
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    temp_dir = tempfile.gettempdir()
    nombre_token = safe_filename_token(nombre)
    qr_filename = os.path.join(temp_dir, f"qr_{invitado_id}_{nombre_token}.png")
    img.save(qr_filename)

    html_part1 = f"""<!doctype html>
<html lang="es">
<body style="margin:0;padding:14px;background:#f4f4f4;font-family:Arial,sans-serif;">
  <div style="max-width:420px;margin:0 auto;background:#ffffff;border:1px solid #dddddd;">
    <div style="background:#1a73e8;color:#ffffff;text-align:center;padding:10px 12px;font-size:18px;font-weight:700;">
      {evento_nombre}
    </div>
    <div style="padding:12px 14px;">
      <p style="margin:0;color:#1f2937;font-size:14px;line-height:1.25;">
        Hola {nombre},<br>
        Presenta esta invitación para el acceso.<br><br>
        ID de invitado: #{invitado_id}<br>
        Fecha y hora: {fecha_evento} | {hora_evento}<br>
        Ubicación: {evento_ubicacion}<br>
        Cupo autorizado: {cupo} personas<br><br>
        Escanea este código en la entrada:
      </p>
      <div style="margin-top:8px;text-align:center;">
    """

    html_part2 = """
      </div>
      <p style="margin:8px 0 0 0;color:#6b7280;font-size:11px;line-height:1.2;text-align:center;">
        Sistema SIGA - Acceso Inteligente
      </p>
    </div>
  </div>
</body>
</html>"""
    try:
        client.send(
            to=email,
            subject=asunto,
            contents=[
                html_part1,
                yagmail.inline(qr_filename),
                html_part2,
            ],
            attachments=[qr_filename],
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

def lector_session_data():
    data = session.get("lector_auth") or {}
    return data if isinstance(data, dict) else {}

def generar_csv_invitados(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["key", "id", "nombre", "email", "cupo_total", "cupo_usado", "tipo_invitado", "invitacion_enviada", "status"])
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
                bool(row.get("invitacion_enviada", False)),
                row.get("status", ""),
            ]
        )
    return output.getvalue()

def lector_touch_session(update_pin_time = False):
    data = lector_session_data()
    if not data:
        return {}
    data["last_seen_at"] = now_iso()
    if update_pin_time:
        data["last_pin_at"] = data["last_seen_at"]
    session["lector_auth"] = data
    return data

def existe_solicitud_pendiente(solicitudes, invitado_key):
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

def generar_hash_qr(invitado_id):
    """Genera hash SHA-512 usando ID + salt secreto."""
    base = f"{invitado_id}{obtener_salt_secreto()}"
    return hashlib.sha512(base.encode("utf-8")).hexdigest()

def reporte_pdf_bytes(data, desde, hasta):
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
    cfg = firebase.evento_actual_config() or {}
    evento_tz = str(cfg.get("timezone") or "America/Mexico_City").strip() or "America/Mexico_City"
    try:
        tzinfo = ZoneInfo(evento_tz)
    except Exception:
        tzinfo = datetime.now().astimezone().tzinfo

    horario_desde = str(desde or cfg.get("fecha_inicio") or "").strip()
    horario_hasta = str(hasta or cfg.get("fecha_fin") or "").strip()
    horario_desde_dt = parse_timestamp(horario_desde)
    horario_hasta_dt = parse_timestamp(horario_hasta)
    horario_desde_txt = horario_desde_dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M") if horario_desde_dt.year > 1900 else "inicio"
    horario_hasta_txt = horario_hasta_dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M") if horario_hasta_dt.year > 1900 else "actual"
    c.drawString(40, y, f"Horario: {horario_desde_txt} a {horario_hasta_txt}")
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
    c.drawString(40, y, "Detalle de movimientos")
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

def validar_datos_invitado(
    data,
    invitados,
    exclude_key = None,
    require_required = True,
):
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
        "tipo_invitado": str(data.get("tipo_invitado", "general")).strip().lower() or "general",
    }
    payload["cupo_usado"] = min(payload["cupo_usado"], payload["cupo_total"])
    return payload, None

def normalizar_nombre(value):
    return str(value or "").strip()

def construir_admin_state():
    invitados = firebase.leer_invitados()
    eventos = firebase.leer_eventos()
    config = sanitized_config(firebase.leer_configuracion())
    staff = firebase.leer_staff()
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

def audit_evento(entity, entity_id, action, before=None, after=None, extra=None):
    print(f"Cambio registrado: {entity} {action}")

def normalize_pin(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())

def invitados_indexes(invitados, exclude_key = None):
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

def get_col(row, *keys):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return ""

def lector_logout_session():
    session.pop("lector_auth", None)

def obtener_salt_secreto():
    """Fuente única de salt: variables de entorno del proyecto."""
    return SALT_SECRETO

def extraer_datos_qr(payload):
    """Formato esperado: ID|HASH"""
    if "|" not in payload:
        return None, None
    invitado_id, hash_qr = payload.split("|", 1)
    invitado_id = invitado_id.strip()
    hash_qr = hash_qr.strip()
    if not invitado_id or not hash_qr:
        return None, None
    return invitado_id, hash_qr

def actor_admin():
    return str(session.get("admin_user") or ADMIN_USER)

def parse_timestamp(value):
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

def aplicar_filtros_invitados(rows, q = "", pendiente = None, tipo = "", email_pendiente = None):
    qn = (q or "").strip().lower()
    tipo_n = (tipo or "").strip().lower()
    out = []
    for row in rows:
        if qn:
            searchable = f"{row.get('id','')} {row.get('nombre','')} {row.get('email','')}".lower()
            if qn not in searchable:
                continue
        is_pendiente = safe_int(row.get("cupo_usado"), 0) < safe_int(row.get("cupo_total"), 0)
        if pendiente is not None and is_pendiente != pendiente:
            continue
        has_pending_email = not bool(row.get("invitacion_enviada", False))
        if email_pendiente is not None and has_pending_email != email_pendiente:
            continue
        if tipo_n and str(row.get("tipo_invitado", "")).lower() != tipo_n:
            continue
        out.append(row)
    return out

def sanitized_config(config):
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

def calc_changes(before, after):
    return []

def normalize_event_state(value, default = "borrador"):
    state = str(value or "").strip().lower()
    return state if state in VALID_EVENT_STATES else default

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def required_event_fields(record):
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

def validar_hash_qr(invitado_id, hash_recibido):
    hash_esperado = generar_hash_qr(invitado_id)
    return hash_esperado == hash_recibido

def eventos_listado(eventos):
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

def filtrar_y_paginar_invitados(invitados, query_args, paginate = True):
    rows = invitados_listado(invitados)
    filtered = aplicar_filtros_invitados(
        rows,
        q=str(query_args.get("q", "") or ""),
        pendiente=parse_bool_param(query_args.get("pendiente")),
        tipo=str(query_args.get("tipo", "") or ""),
        email_pendiente=parse_bool_param(query_args.get("email_pendiente")),
    )
    if not paginate:
        return {"items": filtered, "page": 1, "page_size": len(filtered) or 1, "total": len(filtered), "total_pages": 1}
    page = safe_int(query_args.get("page", 1), 1)
    page_size = safe_int(query_args.get("page_size", 25), 25)
    return paginar_rows(filtered, page, page_size)

def is_valid_pin(pin):
    return len(pin) == 6 and pin.isdigit()

def require_lector_session():
    data = lector_session_data()
    if not data:
        return None, ({"ok": False, "error": "PIN requerido", "code": "LECTOR_PIN_REQUIRED"}, 401)
    if lector_is_idle(data):
        lector_logout_session()
        return None, ({"ok": False, "error": "Sesion de lector expirada por inactividad", "code": "LECTOR_SESSION_EXPIRED"}, 401)
    return lector_touch_session(), None

def normalizar_id(value):
    return str(value or "").strip()

def lector_is_idle(data):
    last_seen = parse_timestamp(data.get("last_seen_at") or data.get("login_at"))
    delta = (datetime.now(timezone.utc) - last_seen).total_seconds()
    return delta > max(LECTOR_IDLE_TIMEOUT_SECONDS, 60)

def smtp_client():
    if not SMTP_USER or not SMTP_APP_PASSWORD:
        return None, "Faltan SMTP_USER o SMTP_APP_PASSWORD en variables de entorno"
    try:
        return yagmail.SMTP(SMTP_USER, SMTP_APP_PASSWORD), None
    except Exception as exc:
        return None, str(exc)

def paginar_rows(rows, page, page_size):
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

def admin_logueado():
    return bool(session.get("admin_ok"))

def construir_reporte_data(fecha_desde = None, fecha_hasta = None):
    logs = firebase.leer_logs(limit=3000)
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

    cfg = firebase.evento_actual_config()
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

def indexar_invitados_por_id(invitados):
    idx = {}
    for key, value in invitados.items():
        if not isinstance(value, dict):
            continue
        invitado_id = str(value.get("id", "")).strip()
        if invitado_id:
            idx[invitado_id] = {"key": key, "data": value}
    return idx
