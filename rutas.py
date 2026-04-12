import os
import base64
import time
import csv
import io
import hashlib
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlencode
import urllib.parse
import tempfile
import numpy as np
import cv2
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from flask import Blueprint
rutas_bp = Blueprint("rutas", __name__)
import firebase
import sync
import funciones_extras
import qr_lector

@rutas_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    usuario = request.form.get("usuario", "")
    password = request.form.get("password", "")

    hash_input = hashlib.sha512((password + funciones_extras.SALT_SECRETO).encode("utf-8")).hexdigest()

    if usuario == funciones_extras.ADMIN_USER and hash_input == funciones_extras.ADMIN_PASSWORD_HASH:
        session.permanent = True
        session["admin_ok"] = True
        session["admin_user"] = usuario
        return redirect(url_for("rutas.admin"))

    return render_template("login.html", error="Credenciales inválidas")

@rutas_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("rutas.login"))

@rutas_bp.route("/admin")
def admin():
    if not funciones_extras.admin_logueado():
        return redirect(url_for("rutas.login"))
    return render_template("admin.html")

@rutas_bp.route("/")
def home():
    return redirect(url_for("rutas.admin"))

@rutas_bp.route("/lector")
def lector():
    return render_template("lector.html")

@rutas_bp.route("/api/lector/staff")
def api_lector_staff():
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    staff = firebase.leer_staff()
    items = []
    for uid, row in staff.items():
        if not isinstance(row, dict):
            continue
        if not bool(row.get("activo", True)):
            continue
        pin = funciones_extras.normalize_pin(row.get("pin", ""))
        if not funciones_extras.is_valid_pin(pin):
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

@rutas_bp.route("/api/lector/login", methods=["POST"])
def api_lector_login():
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    payload = request.get_json(silent=True) or {}
    pin = funciones_extras.normalize_pin(payload.get("pin", ""))
    device_id = funciones_extras.normalize_device_id(payload.get("device_id"))
    modo = str(payload.get("modo") or "online").strip().lower()

    if not funciones_extras.is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos", "code": "PIN_FORMAT_INVALID"}), 400

    staff_all = firebase.leer_staff()
    matches = []
    for uid, row in staff_all.items():
        if not isinstance(row, dict):
            continue
        if not bool(row.get("activo", True)):
            continue
        rol = str(row.get("rol", "lector")).strip().lower()
        if rol not in {"lector", "supervisor", "admin"}:
            continue
        if funciones_extras.normalize_pin(row.get("pin", "")) == pin:
            matches.append((uid, row))

    if len(matches) > 1:
        return jsonify({"ok": False, "error": "PIN duplicado. Contacta a un administrador.", "code": "PIN_DUPLICATE"}), 409

    if len(matches) != 1:
        return jsonify({"ok": False, "error": "PIN inválido"}), 401

    uid, staff = matches[0]
    expected_pin = funciones_extras.normalize_pin(staff.get("pin", ""))
    now = funciones_extras.now_iso()
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
    firebase.registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True, "data": {"uid": uid, "nombre": lector["nombre"], "rol": lector["rol"]}})

@rutas_bp.route("/api/lector/admin_login", methods=["POST"])
def api_lector_admin_login():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado", "code": "ADMIN_REQUIRED"}), 401

    payload = request.get_json(silent=True) or {}
    device_id = funciones_extras.normalize_device_id(payload.get("device_id"))
    modo = str(payload.get("modo") or "online").strip().lower()
    admin_user = str(session.get("admin_user") or funciones_extras.ADMIN_USER).strip() or funciones_extras.ADMIN_USER

    now = funciones_extras.now_iso()
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
    firebase.registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True, "data": {"uid": lector["uid"], "nombre": lector["nombre"], "rol": lector["rol"]}})

@rutas_bp.route("/api/lector/heartbeat", methods=["POST"])
def api_lector_heartbeat():
    lector, error = funciones_extras.require_lector_session()
    if error:
        payload = error[0] if isinstance(error[0], dict) else {"ok": False, "error": "PIN requerido"}
        payload["requires_pin"] = True
        return jsonify(payload), 200
    payload = request.get_json(silent=True) or {}
    if payload.get("device_id"):
        lector["device_id"] = funciones_extras.normalize_device_id(payload.get("device_id"))
        session["lector_auth"] = lector
    modo = str(payload.get("modo") or "online").strip().lower()
    firebase.registrar_lector_activo(lector, modo=modo)
    return jsonify({"ok": True})

@rutas_bp.route("/api/lector/logout", methods=["POST"])
def api_lector_logout():
    data = funciones_extras.lector_session_data()
    payload = request.get_json(silent=True) or {}
    device_id = funciones_extras.normalize_device_id(payload.get("device_id") or data.get("device_id"))
    if device_id:
        firebase.quitar_lector_activo(device_id)
    funciones_extras.lector_logout_session()
    return jsonify({"ok": True})

@rutas_bp.route("/health")
def health():
    return jsonify({"ok": True, "firebase_ready": firebase.firebase_ready})

@rutas_bp.route("/api/lector_estado")
def api_lector_estado():
    lector = funciones_extras.lector_session_data()
    if not lector or funciones_extras.lector_is_idle(lector):
        if lector and funciones_extras.lector_is_idle(lector):
            funciones_extras.lector_logout_session()
        cfg = firebase.evento_actual_config()
        if not isinstance(cfg, dict):
            cfg = {}
        aforo_max = max(funciones_extras.safe_int(cfg.get("aforo_max", 0), 0), 0)
        aforo_actual = max(funciones_extras.safe_int(cfg.get("aforo_actual", 0), 0), 0)
        estado = funciones_extras.normalize_event_state(cfg.get("estado", "borrador"), "borrador")
        return jsonify(
            {
                "ok": True,
                "data": {
                    "firebase_ready": firebase.firebase_ready,
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

    lector = funciones_extras.lector_touch_session()

    modo = "online" if firebase.firebase_ready else "local"
    firebase.registrar_lector_activo(lector, modo=modo)

    cfg = firebase.evento_actual_config()
    if not isinstance(cfg, dict):
        cfg = {}
    aforo_max = max(funciones_extras.safe_int(cfg.get("aforo_max", 0), 0), 0)
    aforo_actual = max(funciones_extras.safe_int(cfg.get("aforo_actual", 0), 0), 0)
    estado = funciones_extras.normalize_event_state(cfg.get("estado", "borrador"), "borrador")
    return jsonify(
        {
            "ok": True,
            "data": {
                "firebase_ready": firebase.firebase_ready,
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

@rutas_bp.route("/api/dashboard")
def api_dashboard():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    event_id = request.args.get("event_id")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    return jsonify({"ok": True, "data": funciones_extras.construir_dashboard_data(event_id=event_id, desde=desde, hasta=hasta)})

@rutas_bp.route("/api/sync/retry", methods=["POST"])
def api_sync_retry():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    sync.sync_meta["last_attempt"] = funciones_extras.now_iso()
    try:
        stats = sincronizar_pendientes()
        if stats.get("failed", 0) == 0:
            sync.sync_meta["last_success"] = funciones_extras.now_iso()
            sync.sync_meta["last_error"] = None
        else:
            sync.sync_meta["last_error"] = f"Fallos de sincronización: {stats.get('failed', 0)}"
        return jsonify({"ok": True, "stats": stats, "last_success": sync.sync_meta.get("last_success"), "last_error": sync.sync_meta.get("last_error")})
    except Exception as exc:
        sync.sync_meta["last_error"] = str(exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

@rutas_bp.route("/api/admin_state")
def api_admin_state():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    return jsonify({"ok": True, "data": funciones_extras.construir_admin_state()})

@rutas_bp.route("/api/configuracion/evento_actual", methods=["PUT"])
def api_actualizar_evento_actual():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
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
        update["estado"] = funciones_extras.normalize_event_state(update.get("estado"), "borrador")
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400
    ref = firebase.db.reference("configuracion/evento_actual")
    before = ref.get() or {}
    ref.update(update)
    after = ref.get() or {}
    funciones_extras.audit_evento("configuracion.evento_actual", str(after.get("id_evento", "")), "update_config", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})
    return jsonify({"ok": True})

@rutas_bp.route("/api/invitados", methods=["GET", "POST"])
def api_invitados():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = firebase.leer_invitados()

    if request.method == "GET":
        do_paginate = not funciones_extras.parse_bool_param(request.args.get("all"))
        paged = funciones_extras.filtrar_y_paginar_invitados(invitados, request.args, paginate=do_paginate)
        return jsonify({"ok": True, "data": paged})

    data = request.get_json(silent=True) or {}
    # Alta inicial siempre con cupo base fijo.
    data["cupo_total"] = funciones_extras.MIN_CUPO_TOTAL
    payload, error = funciones_extras.validar_datos_invitado(data, invitados, exclude_key=None, require_required=True)
    if error:
        status = 409 if error.get("field") == "duplicate" else 400
        return jsonify({"ok": False, "error": error}), status

    invitado_id = payload["id"]
    key = funciones_extras.generar_hash_qr(invitado_id)
    if key in invitados:
        return jsonify({"ok": False, "error": {"field": "duplicate", "message": "Invitado ya existe", "conflict": {"id_conflict_key": key}}}), 409

    payload["creado_en"] = funciones_extras.now_iso()
    firebase.db.reference(f"invitados/{key}").set(payload)
    return jsonify({"ok": True, "key": key, "invitado": payload})

@rutas_bp.route("/api/invitados/<invitado_key>", methods=["PUT"])
def api_actualizar_invitado(invitado_key):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = firebase.leer_invitados()
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

    payload, error = funciones_extras.validar_datos_invitado(candidato, invitados, exclude_key=invitado_key, require_required=True)
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
    firebase.db.reference(f"invitados/{invitado_key}").update(update)
    return jsonify({"ok": True, "updated": update})

@rutas_bp.route("/api/invitados/<invitado_key>", methods=["DELETE"])
def api_eliminar_invitado(invitado_key):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    firebase.db.reference(f"invitados/{invitado_key}").delete()
    return jsonify({"ok": True})

@rutas_bp.route("/api/invitados/import", methods=["POST"])
def api_importar_invitados():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
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

    invitados = firebase.leer_invitados()
    id_index, email_index = funciones_extras.invitados_indexes(invitados)
    inserted = 0
    duplicated = 0
    invalid = 0
    errors = []

    def get_col(row, *keys):
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        return ""

    for idx, row in enumerate(rows, start=2):
        row_data = {
            "id": funciones_extras.get_col(row, "id", "ID", "Id"),
            "nombre": funciones_extras.get_col(row, "nombre", "Nombre", "nombre_lider", "Nombre_lider"),
            "email": funciones_extras.get_col(row, "email", "Email", "correo", "Correo"),
            # En importación también se crea con cupo base fijo.
            "cupo_total": funciones_extras.MIN_CUPO_TOTAL,
            "tipo_invitado": row.get("tipo_invitado", "general"),
            "grupo_nombre": row.get("grupo_nombre", ""),
            "bloqueado": funciones_extras.parse_bool_param(str(row.get("bloqueado", ""))) is True,
            "invitacion_enviada": funciones_extras.parse_bool_param(str(row.get("invitacion_enviada", ""))) is True,
        }

        payload, error = funciones_extras.validar_datos_invitado(row_data, invitados, exclude_key=None, require_required=True)
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

        key = funciones_extras.generar_hash_qr(payload["id"])
        payload["creado_en"] = funciones_extras.now_iso()
        firebase.db.reference(f"invitados/{key}").set(payload)
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

@rutas_bp.route("/api/invitados/batch", methods=["POST"])
def api_invitados_batch():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
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

    invitados = firebase.leer_invitados()
    target_keys = funciones_extras.obtener_keys_lote(invitados, scope, keys, filters)
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
            firebase.db.reference(f"invitados/{key}").update({"bloqueado": flag})
        return jsonify({"ok": True, "updated": len(target_keys), "action": action})

    # enviar_invitacion
    client, smtp_error = funciones_extras.smtp_client()
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
            err = funciones_extras.enviar_invitacion_email(client, invitado, key)
            if err:
                failed += 1
                results.append({"key": key, "id": invitado.get("id"), "ok": False, "error": err})
                continue
            sent += 1
            firebase.db.reference(f"invitados/{key}").update({"invitacion_enviada": True})
            results.append({"key": key, "id": invitado.get("id"), "ok": True})
    finally:
        try:
            client.close()
        except Exception:
            pass

    return jsonify({"ok": True, "action": action, "sent": sent, "failed": failed, "results": results})

@rutas_bp.route("/api/invitados/export")
def api_exportar_invitados():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    invitados = firebase.leer_invitados()
    keys_param = str(request.args.get("keys", "")).strip()
    if keys_param:
        keys = [k for k in keys_param.split(",") if k in invitados]
        rows = [item for item in funciones_extras.invitados_listado(invitados) if item["key"] in keys]
    else:
        rows = funciones_extras.filtrar_y_paginar_invitados(invitados, request.args, paginate=False)["items"]

    csv_text = funciones_extras.generar_csv_invitados(rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=invitados_export_{int(time.time())}.csv"},
    )

@rutas_bp.route("/api/solicitudes_cupo", methods=["GET", "POST"])
def api_solicitudes_cupo():
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    if request.method == "GET":
        if not funciones_extras.admin_logueado():
            return jsonify({"ok": False, "error": "No autorizado"}), 401
        status_filter = str(request.args.get("status", "")).strip().lower()
        limit = max(1, min(funciones_extras.safe_int(request.args.get("limit", 100), 100), 300))
        rows = funciones_extras.solicitudes_cupo_listado(firebase.leer_solicitudes_cupo())
        if status_filter:
            rows = [x for x in rows if str(x.get("status", "")).lower() == status_filter]
        return jsonify({"ok": True, "data": {"items": rows[:limit], "total": len(rows)}})

    solicitante = None
    if funciones_extras.admin_logueado():
        solicitante = {
            "uid": funciones_extras.actor_admin(),
            "nombre": funciones_extras.actor_admin(),
            "origen": "admin",
        }
    else:
        lector, error = funciones_extras.require_lector_session()
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
    cantidad_solicitada = max(funciones_extras.safe_int(payload.get("cantidad_solicitada", 1), 1), 1)
    motivo = str(payload.get("motivo", "")).strip()

    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    invitado_key, invitado = firebase.buscar_invitado(invitado_id, invitado_key_input or None)
    if not invitado_key or not isinstance(invitado, dict):
        return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404

    invitados = firebase.leer_invitados()
    disponibilidad = firebase.resumen_disponibilidad_cupo(invitados)
    disponibles = max(funciones_extras.safe_int(disponibilidad.get("boletos_disponibles"), 0), 0)
    cupo_total_actual = max(
        funciones_extras.safe_int(invitado.get("cupo_total", funciones_extras.MIN_CUPO_TOTAL), funciones_extras.MIN_CUPO_TOTAL),
        funciones_extras.MIN_CUPO_TOTAL,
    )
    auto_aprobada = disponibles > 0 and cantidad_solicitada <= disponibles
    cantidad_aprobada = cantidad_solicitada if auto_aprobada else 0
    nuevo_cupo_total = cupo_total_actual + cantidad_aprobada
    status = "aprobada" if auto_aprobada else "rechazada"
    decision_note = (
        "Aprobación automática por disponibilidad de aforo."
        if auto_aprobada
        else f"Rechazo automático: disponibilidad insuficiente (disponibles: {disponibles})."
    )

    if auto_aprobada:
        firebase.db.reference(f"invitados/{invitado_key}").update({"cupo_total": nuevo_cupo_total})

    registro = {
        "invitado_id": invitado_id,
        "invitado_key": invitado_key,
        "nombre_invitado": invitado.get("nombre_lider") or invitado.get("nombre") or invitado_id,
        "cantidad_solicitada": cantidad_solicitada,
        "cantidad_aprobada": cantidad_aprobada,
        "status": status,
        "motivo": motivo,
        "solicitado_por_uid": solicitante["uid"],
        "solicitado_por_nombre": solicitante["nombre"],
        "solicitado_desde": solicitante["origen"],
        "created_at": funciones_extras.now_iso(),
        "resolved_at": funciones_extras.now_iso(),
        "resolved_by": "sistema_auto",
        "decision_note": decision_note,
        "cupo_total_anterior": cupo_total_actual,
        "cupo_total_nuevo": nuevo_cupo_total,
        "delta_cupo": cantidad_aprobada,
    }
    ref = firebase.db.reference("solicitudes_cupo").push(registro)
    solicitud_id = str(ref.key or "").strip()
    return jsonify(
        {
            "ok": True,
            "solicitud": {"id": solicitud_id, **registro},
            "decision_automatica": status,
            "aforo": disponibilidad,
        }
    )

@rutas_bp.route("/api/solicitudes_cupo/<solicitud_id>/resolver", methods=["POST"])
def api_resolver_solicitud_cupo(solicitud_id):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    solicitud_id = str(solicitud_id or "").strip()
    if not solicitud_id:
        return jsonify({"ok": False, "error": "solicitud_id requerido"}), 400

    payload = request.get_json(silent=True) or {}
    accion = str(payload.get("accion", "aprobar")).strip().lower()
    decision_note = str(payload.get("decision_note", "")).strip()
    if accion not in {"aprobar", "rechazar"}:
        return jsonify({"ok": False, "error": "Acción inválida"}), 400

    solicitud_ref = firebase.db.reference(f"solicitudes_cupo/{solicitud_id}")
    solicitud = solicitud_ref.get() or {}
    if not isinstance(solicitud, dict):
        return jsonify({"ok": False, "error": "Solicitud no encontrada"}), 404

    status_actual = str(solicitud.get("status", "pendiente")).strip().lower()
    if status_actual != "pendiente":
        return jsonify({"ok": False, "error": f"La solicitud ya fue procesada ({status_actual})"}), 409

    if accion == "rechazar":
        update = {
            "status": "rechazada",
            "resolved_at": funciones_extras.now_iso(),
            "resolved_by": funciones_extras.actor_admin(),
            "decision_note": decision_note,
            "cantidad_aprobada": 0,
        }
        solicitud_ref.update(update)
        return jsonify({"ok": True, "solicitud": {"id": solicitud_id, **solicitud, **update}})

    cantidad_solicitada = max(funciones_extras.safe_int(solicitud.get("cantidad_solicitada", 1), 1), 1)
    cantidad_aprobada = funciones_extras.safe_int(payload.get("cantidad_aprobada", cantidad_solicitada), cantidad_solicitada)
    cantidad_aprobada = max(cantidad_aprobada, 1)
    if cantidad_aprobada > cantidad_solicitada:
        return jsonify({"ok": False, "error": "cantidad_aprobada no puede ser mayor a cantidad_solicitada"}), 400

    invitado_key = str(solicitud.get("invitado_key", "")).strip()
    invitado_id = str(solicitud.get("invitado_id", "")).strip()
    invitado_key_found, invitado = firebase.buscar_invitado(invitado_id, invitado_key or None)
    if not invitado_key_found or not isinstance(invitado, dict):
        return jsonify({"ok": False, "error": "Invitado asociado no encontrado"}), 404

    invitados = firebase.leer_invitados()
    disponibilidad = firebase.resumen_disponibilidad_cupo(invitados)
    disponibles = max(funciones_extras.safe_int(disponibilidad.get("boletos_disponibles"), 0), 0)
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

    cupo_total_actual = max(funciones_extras.safe_int(invitado.get("cupo_total", funciones_extras.MIN_CUPO_TOTAL), funciones_extras.MIN_CUPO_TOTAL), funciones_extras.MIN_CUPO_TOTAL)
    nuevo_cupo_total = cupo_total_actual + cantidad_aprobada
    firebase.db.reference(f"invitados/{invitado_key_found}").update({"cupo_total": nuevo_cupo_total})

    update = {
        "status": "aprobada",
        "cantidad_aprobada": cantidad_aprobada,
        "resolved_at": funciones_extras.now_iso(),
        "resolved_by": funciones_extras.actor_admin(),
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

@rutas_bp.route("/api/eventos", methods=["GET", "POST"])
def api_eventos():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if request.method == "GET":
        items = funciones_extras.eventos_listado(firebase.leer_eventos())
        active_id = funciones_extras.active_event_id_from_rows(items)
        for item in items:
            item["is_active"] = item.get("id_evento") == active_id
        return jsonify({"ok": True, "data": {"items": items, "active_event_id": active_id}})

    payload = request.get_json(silent=True) or {}
    event_id = str(payload.get("id_evento", "")).strip() or f"ev_{uuid4().hex[:8]}"
    registro = {
        "id_evento": event_id,
        "nombre": payload.get("nombre", "Evento SIGA"),
        "ubicacion": payload.get("ubicacion", ""),
        "aforo_max": max(funciones_extras.safe_int(payload.get("aforo_max", 0), 0), 0),
        "aforo_actual": max(funciones_extras.safe_int(payload.get("aforo_actual", 0), 0), 0),
        # Estado operativo cambia solo por endpoints publish/close.
        "estado": "borrador",
        "fecha_inicio": payload.get("fecha_inicio", ""),
        "fecha_fin": payload.get("fecha_fin", ""),
        "timezone": payload.get("timezone", "America/Mexico_City"),
        "created_at": funciones_extras.now_iso(),
    }
    firebase.db.reference(f"eventos/{event_id}").set(registro)
    funciones_extras.audit_evento("evento", event_id, "create", {}, registro)
    return jsonify({"ok": True, "evento": registro})

@rutas_bp.route("/api/eventos/<event_id>", methods=["PUT"])
def api_actualizar_evento(event_id):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    payload = request.get_json(silent=True) or {}
    permitido = {"nombre", "ubicacion", "aforo_max", "aforo_actual", "fecha_inicio", "fecha_fin", "timezone"}
    update = {k: v for k, v in payload.items() if k in permitido}
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400
    if "aforo_max" in update:
        update["aforo_max"] = max(funciones_extras.safe_int(update.get("aforo_max"), 0), 0)
    if "aforo_actual" in update:
        update["aforo_actual"] = max(funciones_extras.safe_int(update.get("aforo_actual"), 0), 0)
    ref = firebase.db.reference(f"eventos/{event_id}")
    before = ref.get() or {}
    if not isinstance(before, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404
    ref.update(update)
    after = ref.get() or {}
    funciones_extras.audit_evento("evento", event_id, "update", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})
    return jsonify({"ok": True})

@rutas_bp.route("/api/eventos/<event_id>/publish", methods=["POST"])
def api_publicar_evento(event_id):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    eventos_ref = firebase.db.reference("eventos")
    all_events = eventos_ref.get() or {}
    if not isinstance(all_events, dict) or event_id not in all_events:
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404

    previous_active = None
    for key, ev in all_events.items():
        if isinstance(ev, dict) and ev.get("estado") == "activo":
            previous_active = key
            break

    if previous_active and previous_active != event_id:
        prev_ref = firebase.db.reference(f"eventos/{previous_active}")
        prev_before = prev_ref.get() or {}
        prev_ref.update({"estado": "borrador"})
        prev_after = prev_ref.get() or {}
        funciones_extras.audit_evento("evento", previous_active, "demote_to_draft", prev_before if isinstance(prev_before, dict) else {}, prev_after if isinstance(prev_after, dict) else {})

    target_ref = firebase.db.reference(f"eventos/{event_id}")
    before = target_ref.get() or {}
    target_ref.update({"estado": "activo"})
    after = target_ref.get() or {}
    funciones_extras.audit_evento("evento", event_id, "publish", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})

    evento_cfg = funciones_extras.required_event_fields(after if isinstance(after, dict) else {})
    cfg_ref = firebase.db.reference("configuracion/evento_actual")
    cfg_before = cfg_ref.get() or {}
    cfg_ref.set(evento_cfg)
    cfg_after = cfg_ref.get() or {}
    funciones_extras.audit_evento("configuracion.evento_actual", event_id, "set_active_event", cfg_before if isinstance(cfg_before, dict) else {}, cfg_after if isinstance(cfg_after, dict) else {})
    return jsonify({"ok": True, "active_event_id": event_id})

@rutas_bp.route("/api/eventos/<event_id>/close", methods=["POST"])
def api_cerrar_evento(event_id):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    ref = firebase.db.reference(f"eventos/{event_id}")
    before = ref.get() or {}
    if not isinstance(before, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404
    ref.update({"estado": "cerrado"})
    after = ref.get() or {}
    funciones_extras.audit_evento("evento", event_id, "close", before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})

    cfg_ref = firebase.db.reference("configuracion/evento_actual")
    cfg = cfg_ref.get() or {}
    if isinstance(cfg, dict) and str(cfg.get("id_evento", "")).strip() == event_id:
        cfg_before = dict(cfg)
        cfg["estado"] = "cerrado"
        cfg_ref.set(cfg)
        funciones_extras.audit_evento("configuracion.evento_actual", event_id, "close_active_event", cfg_before, cfg)

    # Junior feature: Flush attendees globally when an event is closed to prepare for the next event cleanly
    try:
        firebase.db.reference("invitados").delete()
        firebase.db.reference("solicitudes_cupo").delete()
    except Exception as exc:
        print(f"[WARN] No se pudo limpiar invitados al cerrar evento: {exc}")

    return jsonify({"ok": True})

@rutas_bp.route("/api/eventos/<event_id>/clone", methods=["POST"])
def api_clonar_evento(event_id):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    source = firebase.db.reference(f"eventos/{event_id}").get() or {}
    if not isinstance(source, dict):
        return jsonify({"ok": False, "error": "Evento no encontrado"}), 404

    payload = request.get_json(silent=True) or {}
    new_id = str(payload.get("id_evento", "")).strip() or f"{event_id}_clone_{uuid4().hex[:6]}"
    clone = funciones_extras.required_event_fields(source)
    clone.update(
        {
            "id_evento": new_id,
            "nombre": f"{source.get('nombre', 'Evento')} (Copia)",
            "estado": "borrador",
            "aforo_actual": 0,
            "created_at": funciones_extras.now_iso(),
        }
    )
    firebase.db.reference(f"eventos/{new_id}").set(clone)
    funciones_extras.audit_evento("evento", new_id, "clone", {}, clone, extra={"source_event_id": event_id})
    return jsonify({"ok": True, "evento": clone})

@rutas_bp.route("/api/eventos/audit")
def api_eventos_audit():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    event_id = str(request.args.get("event_id", "")).strip()
    actor = str(request.args.get("actor", "")).strip().lower()
    desde = funciones_extras.parse_timestamp(request.args.get("desde")) if request.args.get("desde") else None
    hasta = funciones_extras.parse_timestamp(request.args.get("hasta")) if request.args.get("hasta") else None

    raw = firebase.db.reference("auditoria/eventos").order_by_key().limit_to_last(500).get() or {}
    rows = list(raw.values()) if isinstance(raw, dict) else []
    rows_sorted = sorted(rows, key=lambda x: funciones_extras.parse_timestamp((x or {}).get("timestamp")), reverse=True)

    out = []
    for item in rows_sorted:
        if not isinstance(item, dict):
            continue
        ts = funciones_extras.parse_timestamp(item.get("timestamp"))
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

@rutas_bp.route("/api/usuarios_staff", methods=["POST"])
def api_crear_staff():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    payload = request.get_json(silent=True) or {}
    uid = str(payload.get("uid", "")).strip() or f"uid_{uuid4().hex[:8]}"
    rol = str(payload.get("rol", "lector")).strip().lower()
    pin = funciones_extras.normalize_pin(payload.get("pin", ""))

    if pin and not funciones_extras.is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos"}), 400
    if rol in {"lector", "supervisor"} and not funciones_extras.is_valid_pin(pin):
        return jsonify({"ok": False, "error": "PIN requerido para lectores/supervisores (6 dígitos)"}), 400
    if funciones_extras.pin_exists_in_staff(pin):
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
    firebase.db.reference(f"usuarios_staff/{uid}").set(registro)
    return jsonify({"ok": True, "uid": uid, "staff": registro})

@rutas_bp.route("/api/usuarios_staff/<uid>", methods=["PUT"])
def api_actualizar_staff(uid):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    current = firebase.db.reference(f"usuarios_staff/{uid}").get() or {}
    if not isinstance(current, dict):
        return jsonify({"ok": False, "error": "Usuario staff no encontrado"}), 404

    payload = request.get_json(silent=True) or {}
    permitido = {"nombre", "rol", "email", "pin", "activo", "ultimo_login", "permisos"}
    update = {k: v for k, v in payload.items() if k in permitido}
    if not update:
        return jsonify({"ok": False, "error": "Sin campos válidos para actualizar"}), 400

    effective_role = str(update.get("rol", current.get("rol", "lector"))).strip().lower()

    if "pin" in update:
        pin = funciones_extras.normalize_pin(update.get("pin", ""))
        if pin and not funciones_extras.is_valid_pin(pin):
            return jsonify({"ok": False, "error": "PIN inválido. Debe tener 6 dígitos"}), 400
        if effective_role in {"lector", "supervisor"} and not funciones_extras.is_valid_pin(pin):
            return jsonify({"ok": False, "error": "PIN requerido para lectores/supervisores (6 dígitos)"}), 400
        if funciones_extras.pin_exists_in_staff(pin, exclude_uid=uid):
            return jsonify({"ok": False, "error": "PIN ya asignado a otro usuario"}), 409
        update["pin"] = pin
    elif "rol" in update:
        current_pin = funciones_extras.normalize_pin(current.get("pin", ""))
        if effective_role in {"lector", "supervisor"} and not funciones_extras.is_valid_pin(current_pin):
            return jsonify({"ok": False, "error": "Este usuario requiere un PIN de 6 dígitos para cambiar a ese rol"}), 400

    if "rol" in update:
        update["rol"] = effective_role

    firebase.db.reference(f"usuarios_staff/{uid}").update(update)
    return jsonify({"ok": True})

@rutas_bp.route("/api/usuarios_staff/<uid>", methods=["DELETE"])
def api_eliminar_staff(uid):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    firebase.db.reference(f"usuarios_staff/{uid}").delete()
    return jsonify({"ok": True})

@rutas_bp.route("/api/lectores/<uid>/disconnect", methods=["POST"])
def api_desconectar_lector(uid):
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503

    uid = str(uid or "").strip()
    if not uid:
        return jsonify({"ok": False, "error": "uid requerido"}), 400

    raw = firebase.db.reference("lectores_activos").get() or {}
    if not isinstance(raw, dict):
        return jsonify({"ok": True, "removed": 0})

    removed = 0
    for device_id, item in raw.items():
        if not isinstance(item, dict):
            continue
        if str(item.get("staff_uid", "")).strip() != uid:
            continue
        try:
            firebase.db.reference(f"lectores_activos/{device_id}").delete()
            removed += 1
        except Exception:
            pass

    return jsonify({"ok": True, "removed": removed})

@rutas_bp.route("/api/reportes")
def api_reportes():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    return jsonify({"ok": True, "data": funciones_extras.construir_reporte_data(desde, hasta)})

@rutas_bp.route("/api/reportes/export")
def api_reportes_export():
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    fmt = str(request.args.get("format", "csv")).strip().lower()
    data = funciones_extras.construir_reporte_data(desde, hasta)

    if fmt == "csv":
        text = funciones_extras.reporte_csv(data)
        return Response(
            text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=reporte_siga_{int(time.time())}.csv"},
        )

    if fmt == "pdf":
        try:
            payload = funciones_extras.reporte_pdf_bytes(data, desde, hasta)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return Response(
            payload,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=reporte_siga_{int(time.time())}.pdf"},
        )

    return jsonify({"ok": False, "error": "Formato no soportado. Usa csv o pdf"}), 400

@rutas_bp.route("/validar_qr", methods=["POST"])
def validar_qr():
    lector, error = funciones_extras.require_lector_session()
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

    payload, fase = qr_lector.pipeline_decodificacion(imagen_bgr)
    event_id, event_cfg = firebase.estado_evento_activo()
    evento_estado = str((event_cfg or {}).get("estado", "borrador")).strip().lower()

    if not payload:
        evento = funciones_extras.append_lector_to_log({"evento": "qr_no_leido", "fase_exitosa": None, "id_evento": event_id}, lector)
        sync.guardar_log(evento)
        return jsonify({"ok": False, "error": "QR no legible", "fase_exitosa": None}), 400

    invitado_id, hash_qr = funciones_extras.extraer_datos_qr(payload)
    if not invitado_id:
        evento = funciones_extras.append_lector_to_log({"evento": "qr_formato_invalido", "payload": payload, "fase_exitosa": fase, "id_evento": event_id}, lector)
        sync.guardar_log(evento)
        return jsonify({"ok": False, "error": "Formato de QR inválido", "fase_exitosa": fase}), 400

    if not funciones_extras.validar_hash_qr(invitado_id, hash_qr):
        evento = funciones_extras.append_lector_to_log(
            {
            "evento": "qr_hash_invalido",
            "invitado_id": invitado_id,
            "fase_exitosa": fase,
            "id_evento": event_id,
            },
            lector,
        )
        sync.guardar_log(evento)
        return jsonify({"ok": False, "error": "Hash inválido", "fase_exitosa": fase}), 401

    invitado_key, invitado = firebase.buscar_invitado(invitado_id, hash_qr)

    if not invitado:
        evento = funciones_extras.append_lector_to_log(
            {
            "evento": "qr_valido_sin_registro",
            "invitado_id": invitado_id,
            "fase_exitosa": fase,
            "id_evento": event_id,
            },
            lector,
        )
        sync.guardar_log(evento)
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

    evento = funciones_extras.append_lector_to_log(
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
    sync.guardar_log(evento)

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

@rutas_bp.route("/registrar_ingreso", methods=["POST"])
def registrar_ingreso():
    """Permite +1, +2 o todos según cupo_total/cupo_usado."""
    lector = None
    if funciones_extras.admin_logueado():
        lector = {
            "uid": funciones_extras.actor_admin(),
            "nombre": funciones_extras.actor_admin(),
            "pin": "",
            "device_id": str((request.get_json(silent=True) or {}).get("device_id", "")).strip(),
        }
    else:
        lector, error = funciones_extras.require_lector_session()
        if error:
            return jsonify(error[0]), error[1]

    data = request.get_json(silent=True) or {}
    invitado_id = str(data.get("invitado_id", "")).strip()
    invitado_key_input = str(data.get("invitado_key", "")).strip()
    modo = str(data.get("modo", "1")).strip().lower()  # 1,2,todos
    admin_override = bool(data.get("admin_override", False))

    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    active_event_id, active_event_cfg = firebase.estado_evento_activo()
    active_estado = str((active_event_cfg or {}).get("estado", "borrador")).strip().lower()

    if admin_override and not funciones_extras.admin_logueado():
        pin_confirm = str(data.get("pin_confirm", "")).strip()
        if not pin_confirm:
            return jsonify({"ok": False, "error": "PIN requerido para override", "code": "PIN_CONFIRM_REQUIRED"}), 403
        if pin_confirm != str((lector or {}).get("pin", "")):
            return jsonify({"ok": False, "error": "PIN inválido para override", "code": "PIN_CONFIRM_INVALID"}), 403
        funciones_extras.lector_touch_session(update_pin_time=True)

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
        invitado_key, invitado = firebase.buscar_invitado(invitado_id, invitado_key_input or None)
        if not invitado:
            return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404
        ref = firebase.db.reference(f"invitados/{invitado_key}")

        cupo_total = int(invitado.get("cupo_total", funciones_extras.MIN_CUPO_TOTAL))
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
            cfg_ref = firebase.db.reference("configuracion/evento_actual")
            cfg = cfg_ref.get() or {}
            if isinstance(cfg, dict):
                aforo_actual = funciones_extras.safe_int(cfg.get("aforo_actual"), 0)
                delta_real = max(nuevos_usados - usados, 0)
                cfg_ref.update({"aforo_actual": aforo_actual + delta_real})
        except Exception as exc:
            print(f"[WARN] No se pudo actualizar aforo_actual: {exc}")

        evento = funciones_extras.append_lector_to_log(
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
            "modo_conexion": "nube" if firebase.firebase_ready else "local",
            "admin_override": admin_override,
            },
            lector,
        )
        sync.guardar_log(evento)

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

@rutas_bp.route("/registrar_salida", methods=["POST"])
def registrar_salida():
    """Permite registrar salida de +1, +2 o todos (reduce cupo_usado)."""
    if not funciones_extras.admin_logueado():
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    data = request.get_json(silent=True) or {}
    invitado_id = str(data.get("invitado_id", "")).strip()
    invitado_key_input = str(data.get("invitado_key", "")).strip()
    modo = str(data.get("modo", "1")).strip().lower()  # 1,2,todos

    if not firebase.firebase_ready:
        return jsonify({"ok": False, "error": "Firebase no disponible"}), 503
    if not invitado_id:
        return jsonify({"ok": False, "error": "invitado_id requerido"}), 400

    try:
        invitado_key, invitado = firebase.buscar_invitado(invitado_id, invitado_key_input or None)
        if not invitado:
            return jsonify({"ok": False, "error": "Invitado no encontrado"}), 404
        ref = firebase.db.reference(f"invitados/{invitado_key}")

        cupo_total = int(invitado.get("cupo_total", funciones_extras.MIN_CUPO_TOTAL))
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
            cfg_ref = firebase.db.reference("configuracion/evento_actual")
            cfg = cfg_ref.get() or {}
            if isinstance(cfg, dict):
                aforo_actual = funciones_extras.safe_int(cfg.get("aforo_actual"), 0)
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
            "modo_conexion": "nube" if firebase.firebase_ready else "local",
        }
        sync.guardar_log(evento)

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
