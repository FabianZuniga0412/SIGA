import os
import threading
from dotenv import load_dotenv
from flask import Flask

homebrew_lib = "/opt/homebrew/lib"
if os.path.isdir(homebrew_lib):
    actual = os.getenv("DYLD_FALLBACK_LIBRARY_PATH", "")
    if homebrew_lib not in actual.split(":"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{homebrew_lib}:{actual}" if actual else homebrew_lib

load_dotenv()

import firebase
import sync

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cambia-esta-clave-en-produccion")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)

import rutas
app.register_blueprint(rutas.rutas_bp)

_runtime_initialized = False
_sync_thread_started = False
IS_SERVERLESS = os.getenv("VERCEL") == "1" or os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None


def bootstrap_runtime(start_sync_worker = False):
    global _runtime_initialized, _sync_thread_started
    if not _runtime_initialized:
        firebase.init_firebase()
        if not IS_SERVERLESS:
            sync.ensure_pendientes_file()
        _runtime_initialized = True
    if start_sync_worker and not IS_SERVERLESS and not _sync_thread_started:
        hilo_sync = threading.Thread(target=sync.worker_sincronizacion, daemon=True)
        hilo_sync.start()
        _sync_thread_started = True


# Ensure Firebase/init runs even when started via `flask run` or WSGI.
bootstrap_runtime(start_sync_worker=False)

if __name__ == "__main__":
    bootstrap_runtime(start_sync_worker=True)
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    cert_file = os.getenv("LOCAL_SSL_CERT", "certs/localhost.pem")
    key_file = os.getenv("LOCAL_SSL_KEY", "certs/localhost-key.pem")
    if os.path.exists(cert_file) and os.path.exists(key_file):
        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False, ssl_context=(cert_file, key_file))
    else:
        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
