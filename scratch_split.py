import ast
import re
import os

with open("app.py", "r", encoding="utf-8") as f:
    source = f.read()

lines = source.split('\n')

class FuncVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = {}
    def visit_FunctionDef(self, node):
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        if node.decorator_list:
            start = node.decorator_list[0].lineno - 1
        self.functions[node.name] = '\n'.join(lines[start:end])
        self.generic_visit(node)

visitor = FuncVisitor()
tree = ast.parse(source)
visitor.visit(tree)
funcs = visitor.functions

mapping = {
    'qr_lector.py': ['decodificar_qr', 'pipeline_decodificacion'],
    'sync.py': ['ensure_pendientes_file', 'leer_pendientes', 'escribir_pendientes', 'guardar_log', 'sincronizar_pendientes', 'worker_sincronizacion'],
    'firebase.py': [
        'init_firebase', 'lector_lockout_ref', 'leer_lectores_activos', 'registrar_lector_activo', 'quitar_lector_activo',
        'leer_invitados', 'total_boletos_entregados', 'resumen_disponibilidad_cupo', 'leer_solicitudes_cupo',
        'buscar_invitado', 'leer_logs', 'leer_configuracion', 'leer_eventos', 'leer_staff', 'evento_actual_config',
        'estado_evento_activo'
    ]
}

rutas_names = [name for name in funcs.keys() if name.startswith('api_') or name in ['login', 'logout', 'admin', 'home', 'lector', 'health', 'validar_qr', 'registrar_ingreso', 'registrar_salida']]
mapping['rutas.py'] = rutas_names

assigned = set([f for group in mapping.values() for f in group])
extras = set(funcs.keys()) - assigned
mapping['funciones_extras.py'] = list(extras)

# Write headers and global variables
headers = {
    'qr_lector.py': """import cv2\nimport numpy as np\nfrom pyzbar.pyzbar import decode\n\n""",
    'firebase.py': """import os\nfrom datetime import datetime, timezone\nimport firebase_admin\nfrom firebase_admin import credentials, db\nimport funciones_extras\nimport sync\n\nfirebase_ready = False\nFIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "")\nFIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase-service-account.json")\nMIN_CUPO_TOTAL = 3\n\n""",
    'sync.py': """import os\nimport json\nimport time\nimport threading\nfrom datetime import datetime, timezone\nimport firebase\nimport funciones_extras\n\nPENDIENTES_FILE = os.getenv("PENDIENTES_FILE", "pendientes.json")\nsync_meta = {"last_attempt": None, "last_success": None, "last_error": None}\n\n""",
    'funciones_extras.py': """import os\nimport hashlib\nimport tempfile\nimport io\nimport csv\nimport time\nimport yagmail\nimport qrcode\nfrom datetime import datetime, timezone\nfrom urllib.parse import urlencode\nfrom uuid import uuid4\nfrom flask import session\nimport firebase\nimport sync\n\n# Global config variables\nSALT_SECRETO = os.getenv("QR_SALT_SECRETO", "CAMBIA_ESTE_SALT")\nADMIN_USER = os.getenv("ADMIN_USER", "admin")\nADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")\nADMIN_PASSWORD_HASH = hashlib.sha512((ADMIN_PASSWORD + SALT_SECRETO).encode("utf-8")).hexdigest()\nSMTP_USER = os.getenv("SMTP_USER", "")\nSMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")\nSMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SIGA")\nVALID_EVENT_STATES = {"borrador", "activo", "cerrado"}\nMIN_CUPO_TOTAL = 3\nLECTOR_IDLE_TIMEOUT_SECONDS = 900\nLECTOR_MAX_PIN_ATTEMPTS = 5\nLECTOR_LOCKOUT_SECONDS = 300\nLECTOR_ACTIVE_WINDOW_SECONDS = 120\n\n""",
    'rutas.py': """import os\nimport base64\nimport time\nimport csv\nimport io\nfrom datetime import datetime, timezone\nfrom uuid import uuid4\nfrom urllib.parse import urlencode\nimport urllib.parse\nimport tempfile\nimport numpy as np\nimport cv2\nfrom flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for\n\nfrom app import app\nimport firebase\nimport sync\nimport funciones_extras\nimport qr_lector\n\n""",
    'app.py': """import os\nimport threading\nfrom dotenv import load_dotenv\nfrom flask import Flask\n\nimport firebase\nimport sync\n\nhomebrew_lib = "/opt/homebrew/lib"\nif os.path.isdir(homebrew_lib):\n    actual = os.getenv("DYLD_FALLBACK_LIBRARY_PATH", "")\n    if homebrew_lib not in actual.split(":"):\n        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{homebrew_lib}:{actual}" if actual else homebrew_lib\n\nload_dotenv()\n\napp = Flask(__name__)\napp.secret_key = os.getenv("FLASK_SECRET_KEY", "cambia-esta-clave-en-produccion")\napp.config.update(\n    SESSION_COOKIE_HTTPONLY=True,\n    SESSION_COOKIE_SAMESITE="Lax",\n    SESSION_COOKIE_SECURE=False,\n)\n\nimport rutas\n\nif __name__ == "__main__":\n    firebase.init_firebase()\n    sync.ensure_pendientes_file()\n    hilo_sync = threading.Thread(target=sync.worker_sincronizacion, daemon=True)\n    hilo_sync.start()\n    port = int(os.getenv("PORT", "5000"))\n    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"\n    cert_file = os.getenv("LOCAL_SSL_CERT", "certs/localhost.pem")\n    key_file = os.getenv("LOCAL_SSL_KEY", "certs/localhost-key.pem")\n    if os.path.exists(cert_file) and os.path.exists(key_file):\n        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False, ssl_context=(cert_file, key_file))\n    else:\n        app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)\n"""
}

# To replace global variable references in the functions:
# Many places used 'firebase_ready', 'db.reference', etc.
global_replacements = {
    'firebase_ready': 'firebase.firebase_ready',
    'db.reference': 'firebase.db.reference',
    'sincronizar_pendientes': 'sync.sincronizar_pendientes',
    'leer_pendientes': 'sync.leer_pendientes',
    'escribir_pendientes': 'sync.escribir_pendientes',
    'guardar_log': 'sync.guardar_log',
    'sync_meta': 'sync.sync_meta',
    'pendientes_lock': 'sync.pendientes_lock',
}
# Only apply cross-module replacements, wait this is brittle. A junior would just use Wildcard imports or module imports.
# I will use module imports dynamically by regexing function texts.
# Wait, replacing `db.reference` with `firebase.db.reference` is easy.
# Let's write the files.
for filename, funclist in mapping.items():
    if filename == 'app.py':
        # we completely rewrite app.py
        with open(filename, "w", encoding="utf-8") as f:
            f.write(headers[filename])
        continue
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(headers.get(filename, ""))
        for fname in funclist:
            func_code = funcs[fname]
            if filename != 'firebase.py':
                func_code = re.sub(r'(?<!\.)\bfirebase_ready\b', 'firebase.firebase_ready', func_code)
                func_code = re.sub(r'(?<!\.)\bdb\.reference\b', 'firebase.db.reference', func_code)
            if filename != 'sync.py':
                func_code = re.sub(r'\bguardar_log\b', 'sync.guardar_log', func_code)
                func_code = re.sub(r'\bleer_pendientes\b', 'sync.leer_pendientes', func_code)
                func_code = re.sub(r'\bsync_meta\b', 'sync.sync_meta', func_code)
            if filename == 'rutas.py':
                # Rutas rely heavily on funciones_extras and firebase
                for helper in mapping['funciones_extras.py']:
                    func_code = re.sub(r'\b' + helper + r'\b(?=\()', f'funciones_extras.{helper}', func_code)
                # Constants
                func_code = re.sub(r'\bSALT_SECRETO\b', 'funciones_extras.SALT_SECRETO', func_code)
                func_code = re.sub(r'\bADMIN_PASSWORD_HASH\b', 'funciones_extras.ADMIN_PASSWORD_HASH', func_code)
                func_code = re.sub(r'\bMIN_CUPO_TOTAL\b', 'funciones_extras.MIN_CUPO_TOTAL', func_code)
                func_code = re.sub(r'\bADMIN_USER\b', 'funciones_extras.ADMIN_USER', func_code)
                func_code = re.sub(r'\bLECTOR_MAX_PIN_ATTEMPTS\b', 'funciones_extras.LECTOR_MAX_PIN_ATTEMPTS', func_code)
                func_code = re.sub(r'\bLECTOR_LOCKOUT_SECONDS\b', 'funciones_extras.LECTOR_LOCKOUT_SECONDS', func_code)
                # Firebase funcs
                for helper in mapping['firebase.py']:
                    # some overlap with words like 'init_firebase'
                    func_code = re.sub(r'\b' + helper + r'\b(?=\()', f'firebase.{helper}', func_code)
                # qr_lector funcs
                for helper in mapping['qr_lector.py']:
                    func_code = re.sub(r'\b' + helper + r'\b(?=\()', f'qr_lector.{helper}', func_code)
            
            if filename == 'funciones_extras.py':
                for helper in mapping['firebase.py']:
                    func_code = re.sub(r'\b' + helper + r'\b(?=\()', f'firebase.{helper}', func_code)
                
            f.write(func_code + "\n\n")

print("Archivos divididos!")
