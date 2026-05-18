import copy
import hashlib
import os
from datetime import datetime, timezone
from uuid import uuid4


DEMO_MODE = os.getenv("SIGA_DEMO", "").strip().lower() in {"1", "true", "yes", "si"}
DEMO_RESET_ON_BOOT = os.getenv("DEMO_RESET_ON_BOOT", "1").strip().lower() not in {"0", "false", "no"}
MIN_CUPO_TOTAL = 3


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def demo_hash(invitado_id):
    salt = os.getenv("QR_SALT_SECRETO", "CAMBIA_ESTE_SALT")
    return hashlib.sha512(f"{invitado_id}{salt}".encode("utf-8")).hexdigest()


def _demo_invitado(invitado_id, nombre, email, cupo_total=3, cupo_usado=0, tipo="general", grupo=""):
    return {
        "id": invitado_id,
        "nombre": nombre,
        "nombre_lider": nombre,
        "email": email,
        "cupo_total": max(int(cupo_total), MIN_CUPO_TOTAL),
        "cupo_usado": max(int(cupo_usado), 0),
        "ingresados": max(int(cupo_usado), 0),
        "status": "dentro" if cupo_usado else "fuera",
        "invitacion_enviada": True,
        "bloqueado": False,
        "tipo_invitado": tipo,
        "grupo_nombre": grupo,
        "creado_en": now_iso(),
    }


def initial_data():
    evento = {
        "id_evento": "demo-siga-2026",
        "nombre": "Demo SIGA 2026",
        "ubicacion": "Auditorio Principal",
        "aforo_max": 120,
        "aforo_actual": 5,
        "estado": "activo",
        "fecha_inicio": "2026-06-01T18:00:00-06:00",
        "fecha_fin": "2026-06-01T22:00:00-06:00",
        "timezone": "America/Mexico_City",
        "created_at": now_iso(),
    }
    invitados = {
        demo_hash("SIGA-001"): _demo_invitado("SIGA-001", "Ana Martinez", "ana.demo@example.com", 4, 2, "vip", "Mesa A"),
        demo_hash("SIGA-002"): _demo_invitado("SIGA-002", "Carlos Rivera", "carlos.demo@example.com", 3, 0, "general", "General"),
        demo_hash("SIGA-003"): _demo_invitado("SIGA-003", "Lucia Gomez", "lucia.demo@example.com", 5, 3, "staff", "Produccion"),
        demo_hash("SIGA-004"): _demo_invitado("SIGA-004", "Miguel Torres", "miguel.demo@example.com", 3, 0, "general", "General"),
    }
    staff = {
        "lector_demo": {
            "nombre": "Lector Demo",
            "email": "lector.demo@example.com",
            "rol": "lector",
            "pin": "123456",
            "activo": True,
            "ultimo_login": "",
            "permisos": {},
        },
        "supervisor_demo": {
            "nombre": "Supervisor Demo",
            "email": "supervisor.demo@example.com",
            "rol": "supervisor",
            "pin": "654321",
            "activo": True,
            "ultimo_login": "",
            "permisos": {},
        },
    }
    logs = {
        "log_demo_1": {
            "evento": "ingreso_registrado",
            "invitado_id": "SIGA-001",
            "id_evento": evento["id_evento"],
            "nombre_invitado": "Ana Martinez",
            "modo": "2",
            "sumar": 2,
            "cantidad_entrada": 2,
            "ingresados_antes": 0,
            "ingresados_despues": 2,
            "cupo_total": 4,
            "fase_pdi": "Demo",
            "modo_conexion": "demo",
            "timestamp": now_iso(),
        },
        "log_demo_2": {
            "evento": "ingreso_registrado",
            "invitado_id": "SIGA-003",
            "id_evento": evento["id_evento"],
            "nombre_invitado": "Lucia Gomez",
            "modo": "todos",
            "sumar": 3,
            "cantidad_entrada": 3,
            "ingresados_antes": 0,
            "ingresados_despues": 3,
            "cupo_total": 5,
            "fase_pdi": "Demo",
            "modo_conexion": "demo",
            "timestamp": now_iso(),
        },
    }
    return {
        "configuracion": {"evento_actual": copy.deepcopy(evento)},
        "eventos": {evento["id_evento"]: copy.deepcopy(evento)},
        "invitados": invitados,
        "usuarios_staff": staff,
        "lectores_activos": {},
        "logs": logs,
        "solicitudes_cupo": {},
        "auditoria": {"eventos": {}},
        "seguridad": {"lector_pin_lockouts": {}},
    }


_DATA = initial_data()


def reset():
    global _DATA
    _DATA = initial_data()


def _split(path):
    return [part for part in str(path or "").strip("/").split("/") if part]


def _walk(path, create=False):
    parts = _split(path)
    node = _DATA
    for part in parts[:-1]:
        value = node.get(part)
        if not isinstance(value, dict):
            if not create:
                return None, None
            value = {}
            node[part] = value
        node = value
    key = parts[-1] if parts else None
    return node, key


def _get_path(path):
    parts = _split(path)
    node = _DATA
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class DemoReference:
    def __init__(self, path="", key=None):
        self.path = str(path or "").strip("/")
        self.key = key if key is not None else (_split(self.path)[-1] if self.path else None)
        self._limit_to_last = None

    def child(self, child_path):
        child = str(child_path or "").strip("/")
        path = "/".join(part for part in (self.path, child) if part)
        return DemoReference(path)

    def get(self):
        value = _get_path(self.path)
        if isinstance(value, dict) and self._limit_to_last is not None:
            items = list(value.items())[-self._limit_to_last :]
            value = dict(items)
        return copy.deepcopy(value)

    def set(self, value):
        if not self.path:
            raise ValueError("Cannot replace demo root")
        parent, key = _walk(self.path, create=True)
        parent[key] = copy.deepcopy(value)

    def update(self, value):
        if not isinstance(value, dict):
            raise ValueError("Demo update expects a dict")
        parent, key = _walk(self.path, create=True)
        current = parent.get(key)
        if not isinstance(current, dict):
            current = {}
            parent[key] = current
        current.update(copy.deepcopy(value))

    def delete(self):
        parent, key = _walk(self.path, create=False)
        if isinstance(parent, dict) and key in parent:
            del parent[key]

    def push(self, value=None):
        key = f"demo_{uuid4().hex}"
        ref = DemoReference("/".join(part for part in (self.path, key) if part), key=key)
        if value is not None:
            ref.set(value)
        return ref

    def order_by_key(self):
        return self

    def limit_to_last(self, count):
        self._limit_to_last = max(int(count), 0)
        return self


class DemoDB:
    @staticmethod
    def reference(path=""):
        return DemoReference(path)


db = DemoDB()
