import os
import json
import time
from datetime import datetime, timezone
import firebase
import funciones_extras

PENDIENTES_FILE = os.getenv("PENDIENTES_FILE", "pendientes.json")
IS_SERVERLESS = os.getenv("VERCEL") == "1" or os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None
sync_meta = {"last_attempt": None, "last_success": None, "last_error": None}

def ensure_pendientes_file():
    if IS_SERVERLESS:
        return
    if not os.path.exists(PENDIENTES_FILE):
        with open(PENDIENTES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def leer_pendientes():
    if IS_SERVERLESS:
        return []
    ensure_pendientes_file()
    with open(PENDIENTES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

def escribir_pendientes(data):
    if IS_SERVERLESS:
        return
    with open(PENDIENTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def guardar_log(evento):
    """Intenta guardar en Firebase; si falla, guarda en cola offline."""
    evento.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    if firebase.firebase_ready:
        try:
            firebase.db.reference("logs").push(evento)
            return
        except Exception as exc:
            print(f"[WARN] Fallo guardando en Firebase, se encola: {exc}")

    if IS_SERVERLESS:
        print("[WARN] Firebase no disponible en serverless; no se persiste cola offline.")
        return

    pendientes = leer_pendientes()
    evento["sincronizado"] = False
    pendientes.append(evento)
    escribir_pendientes(pendientes)

def sincronizar_pendientes():
    stats = {"processed": 0, "synced": 0, "failed": 0}
    if not firebase.firebase_ready:
        return stats

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
            firebase.db.reference("logs").push(payload)
            item["sincronizado"] = True
            stats["synced"] += 1
        except Exception as exc:
            print(f"[WARN] No se pudo sincronizar item pendiente: {exc}")
            stats["failed"] += 1

        actualizado.append(item)

    escribir_pendientes(actualizado)
    return stats

def worker_sincronizacion():
    if IS_SERVERLESS:
        return
    while True:
        try:
            sync_meta["last_attempt"] = funciones_extras.now_iso()
            stats = sincronizar_pendientes()
            if stats.get("failed", 0) == 0:
                sync_meta["last_success"] = funciones_extras.now_iso()
                sync_meta["last_error"] = None
            else:
                sync_meta["last_error"] = f"Fallos de sincronización: {stats.get('failed', 0)}"
        except Exception as exc:
            print(f"[ERROR] Worker sync: {exc}")
            sync_meta["last_error"] = str(exc)
        time.sleep(30)
