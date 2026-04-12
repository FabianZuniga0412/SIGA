import re

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# Remove typing imports
code = re.sub(r'^from typing import .*?\n', '', code, flags=re.MULTILINE)

# Remove -> ReturnType:
code = re.sub(r'\s*->\s*[a-zA-Z0-9_\[\], ]+:', ':', code)

def replacer(match):
    arg_str = match.group(0)
    for t in [r':\s*Optional\[.*?\]', r':\s*Tuple\[.*?\]', r':\s*list', r':\s*dict', r':\s*str', r':\s*int', r':\s*bool', r':\s*Any', r':\s*Optional', r':\s*yagmail\.SMTP']:
        arg_str = re.sub(t, '', arg_str)
    return arg_str

code = re.sub(r'def\s+\w+\s*\((.*?)\)\s*:', replacer, code, flags=re.DOTALL)

# HMAC
code = code.replace("import hmac\n", "")
code = code.replace("hmac.compare_digest(hash_esperado, hash_recibido)", "hash_esperado == hash_recibido")
code = code.replace("hmac.compare_digest(hash_input, ADMIN_PASSWORD_HASH)", "hash_input == ADMIN_PASSWORD_HASH")

# LOCKS
code = code.replace("pendientes_lock = threading.Lock()", "")
code = code.replace("with pendientes_lock:", "if True:  # Lock quitado para simplificar")

# AUDITORIA
auditoria_pattern = r'def calc_changes\(.*?\n(.*?)def required_event_fields'
replacement = """def calc_changes(before, after):
    return []

def audit_evento(entity, entity_id, action, before=None, after=None, extra=None):
    print(f"Cambio registrado: {entity} {action}")

def required_event_fields"""
code = re.sub(r'def calc_changes\(.*?\n(.*?)def required_event_fields', replacement, code, flags=re.DOTALL)

# LECTOR PIN LOCKOUT
code = re.sub(r'^[ ]+lock_ref = lector_lockout_ref\(device_id\)\n.*?(?=^[ ]+staff_all = leer_staff)', '', code, flags=re.MULTILINE|re.DOTALL)

fail_replace = """    if len(matches) != 1:
        fail_count = safe_int((lock_data or {}).get("fail_count"), 0) + 1
        update = {"fail_count": fail_count, "last_fail_at": now_iso()}
        if fail_count >= max(LECTOR_MAX_PIN_ATTEMPTS, 1):
            locked_until = datetime.now(timezone.utc).timestamp() + max(LECTOR_LOCKOUT_SECONDS, 60)
            update["locked_until"] = datetime.fromtimestamp(locked_until, tz=timezone.utc).isoformat()
            update["fail_count"] = 0
        lock_ref.update(update)
        return jsonify({"ok": False, "error": "PIN inválido", "code": "PIN_INVALID"}), 401"""

code = code.replace(fail_replace, """    if len(matches) != 1:
        return jsonify({"ok": False, "error": "PIN inválido"}), 401""")

code = code.replace("    lock_ref.delete()\n", "")

config_vars = '''try:
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
    LECTOR_ACTIVE_WINDOW_SECONDS = 120'''
simple_config_vars = """LECTOR_IDLE_TIMEOUT_SECONDS = 900
LECTOR_MAX_PIN_ATTEMPTS = 5
LECTOR_LOCKOUT_SECONDS = 300
LECTOR_ACTIVE_WINDOW_SECONDS = 120"""
code = code.replace(config_vars, simple_config_vars)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Modificaciones aplicadas!")
