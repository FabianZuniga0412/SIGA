# Documentacion Tecnica Completa de SIGA

Fecha de elaboracion: 2026-04-13  
Base de esta documentacion: codigo fuente real del repositorio `SIGA`

---

## 1. Vision general del sistema

SIGA es una aplicacion web para administrar eventos con control de acceso por QR.

Su objetivo operativo es:

- Registrar invitados.
- Asignarles un cupo de acceso.
- Generar y enviar invitaciones por correo con QR.
- Operar uno o varios lectores en celular, tablet o escritorio.
- Validar QRs al momento del acceso.
- Registrar entradas y salidas.
- Llevar el aforo actual del evento.
- Mostrar paneles y reportes para administracion.

En el codigo actual, el sistema esta dividido en dos superficies principales:

- **Panel administrador**: `/admin`
- **Portal lector**: `/lector`

Las dos superficies hablan con un backend en Flask y almacenan la mayor parte de sus datos en Firebase Realtime Database.

---

## 2. Arquitectura general

### 2.1 Diagrama mental rapido

```text
Administrador / Navegador
        |
        v
   Flask (app.py + rutas.py)
        |
        +--> Firebase Realtime Database
        |
        +--> Cola local pendientes.json (solo logs, modo local no serverless)
        |
        +--> SMTP / Gmail App Password para envio de invitaciones


Lector / Navegador
        |
        +--> BarcodeDetector del navegador para detectar si hay QR en pantalla
        |
        +--> Envia frame a Flask (/validar_qr)
                |
                +--> OpenCV decodifica QR
                +--> Firebase busca invitado
                +--> Flask responde si el QR es valido
```

### 2.2 Capas

- **Capa web**: Flask sirve HTML, JS, CSS y expone endpoints JSON.
- **Capa de negocio**: `rutas.py` y `funciones_extras.py`.
- **Capa de persistencia**: `firebase.py`.
- **Capa de sincronizacion**: `sync.py`.
- **Capa de vision / QR**: `qr_lector.py` y parte de `static/js/lector.js`.
- **Capa de presentacion**: `templates/*.html`, `static/js/*.js`, `static/css/styles.css`.

---

## 3. Stack tecnologico

### 3.1 Backend

- Python
- Flask `3.0.3`
- firebase-admin `6.6.0`
- python-dotenv `1.0.1`
- yagmail `0.15.293`
- qrcode[pil] `7.4.2`
- reportlab `4.2.2`
- openpyxl `3.1.5`
- opencv-python-headless `4.10.0.84`
- numpy `1.26.4`

### 3.2 Frontend

- HTML renderizado por Flask
- CSS propio en `static/css/styles.css`
- JavaScript plano sin framework
- `BarcodeDetector` del navegador para deteccion previa
- `qrcodejs` para generar QRs en el panel admin
- `Phosphor Icons`
- Fuente `Inter` desde Google Fonts

### 3.3 Infraestructura

- Firebase Realtime Database
- Vercel para despliegue serverless Python
- SSL local opcional con certificados en `certs/`

---

## 4. Estructura del repositorio

### 4.1 Archivos principales de runtime

| Ruta | Rol |
|---|---|
| `app.py` | Punto de arranque principal de Flask |
| `api/index.py` | Shim para Vercel; exporta `app` |
| `rutas.py` | Endpoints HTML y API; contiene casi toda la logica HTTP |
| `firebase.py` | Conexion y lecturas/escrituras a Firebase |
| `funciones_extras.py` | Utilidades, validaciones, reportes, QR hash, email |
| `sync.py` | Cola local de logs y sincronizacion con Firebase |
| `qr_lector.py` | Pipeline de decodificacion QR con OpenCV |
| `templates/admin.html` | Vista del panel admin |
| `templates/lector.html` | Vista del lector QR |
| `templates/login.html` | Login del admin |
| `static/js/admin.js` | Logica cliente del panel admin |
| `static/js/lector.js` | Logica cliente del lector |
| `static/css/styles.css` | Estilos de toda la app |
| `vercel.json` | Routing de Vercel hacia `api/index.py` |
| `.env.example` | Variables de entorno necesarias |

### 4.2 Archivos de apoyo y ejemplo

| Ruta | Rol |
|---|---|
| `schema_v2_ejemplo.json` | Ejemplo amplio del esquema esperado en Firebase |
| `siga_schema_seed.json` | Ejemplo mas simple de seed inicial |
| `estudiantes_prueba.csv` | CSV de muestra para importacion |
| `pendientes.json` | Cola local de logs pendientes de sincronizar |
| `certs/localhost.pem` y `certs/localhost-key.pem` | SSL local opcional |

### 4.3 Archivos auxiliares no usados por runtime

| Ruta | Rol aparente |
|---|---|
| `fix_types.py` | Script utilitario para remover type hints por regex |
| `scratch_split.py` | Script experimental para separar `app.py` por modulos |
| `scratch_modify_app.py` | Script experimental para transformar codigo |

Estos archivos **no forman parte del flujo de ejecucion de produccion**.

---

## 5. Arranque del sistema

## 5.1 `app.py`

`app.py` hace lo siguiente:

1. Ajusta `DYLD_FALLBACK_LIBRARY_PATH` si existe `/opt/homebrew/lib`.
2. Carga variables de entorno con `load_dotenv()`.
3. Importa `firebase` y `sync`.
4. Detecta si corre en modo serverless:
   - `VERCEL == "1"`
   - o `AWS_LAMBDA_FUNCTION_NAME` definido
5. Detecta si esta en produccion:
   - `APP_ENV=production`
   - o modo serverless
6. Valida variables obligatorias en produccion:
   - `FLASK_SECRET_KEY`
   - `QR_SALT_SECRETO`
   - `ADMIN_PASSWORD`
   - `FIREBASE_DB_URL`
7. Crea la aplicacion Flask.
8. Configura cookies de sesion:
   - `SESSION_COOKIE_HTTPONLY=True`
   - `SESSION_COOKIE_SAMESITE="Lax"`
   - `SESSION_COOKIE_SECURE=IS_PRODUCTION`
9. Registra el blueprint de `rutas.py`.
10. Ejecuta `bootstrap_runtime()`:
   - inicializa Firebase
   - crea `pendientes.json` si no es serverless
   - opcionalmente arranca el worker de sincronizacion
11. Si se corre como script principal:
   - arranca worker de sincronizacion
   - usa `PORT` o 5000
   - usa `FLASK_DEBUG`
   - si existen certificados locales, levanta HTTPS

### 5.2 `api/index.py`

Este archivo solo contiene:

```python
from app import app
```

Su finalidad es que Vercel encuentre un objeto `app` a nivel modulo.

### 5.3 `vercel.json`

Todo request cae en `api/index.py`.

```json
{
  "version": 2,
  "routes": [
    {
      "src": "/(.*)",
      "dest": "/api/index.py"
    }
  ]
}
```

Esto significa que el routing lo resuelve Flask, no Vercel por separado.

---

## 6. Variables de entorno

Basado en `.env.example` y en el uso real del codigo.

| Variable | Uso |
|---|---|
| `APP_ENV` | Determina si el runtime es `production` o no |
| `FLASK_SECRET_KEY` | Firma la sesion Flask |
| `QR_SALT_SECRETO` | Salt del hash SHA-512 usado para QR y login admin |
| `ADMIN_USER` | Usuario admin esperado |
| `ADMIN_PASSWORD` | Password admin en texto plano; se hashea al iniciar |
| `FIREBASE_DB_URL` | URL del Realtime Database |
| `FIREBASE_CREDENTIALS_JSON` | Credenciales JSON en una sola linea, ideal para Vercel |
| `FIREBASE_CRED_PATH` | Ruta local al service account JSON |
| `PENDIENTES_FILE` | Archivo local de cola offline |
| `LOCAL_SSL_CERT` | Certificado local |
| `LOCAL_SSL_KEY` | Llave privada local |
| `SMTP_USER` | Cuenta para mandar correos |
| `SMTP_APP_PASSWORD` | App password de Gmail |
| `SMTP_FROM_NAME` | Nombre mostrado en el correo |
| `PORT` | Puerto local de Flask |
| `FLASK_DEBUG` | Modo debug |

### 6.1 Validacion en produccion

El codigo rechaza valores inseguros por defecto en produccion, por ejemplo:

- `FLASK_SECRET_KEY=cambia-esta-clave-en-produccion`
- `QR_SALT_SECRETO=CAMBIA_ESTE_SALT`
- `ADMIN_PASSWORD=admin123`

Si se intenta correr asi en produccion, lanza `RuntimeError`.

---

## 7. Modelo de datos en Firebase Realtime Database

La app usa Firebase Realtime Database como fuente principal de verdad.

El esquema real sale de:

- `firebase.py`
- `rutas.py`
- `funciones_extras.py`
- `schema_v2_ejemplo.json`
- `siga_schema_seed.json`

## 7.1 Nodo `configuracion/evento_actual`

Representa el evento operativo en curso.

Campos usados por el codigo actual:

| Campo | Tipo | Uso |
|---|---|---|
| `id_evento` | string | Evento activo actual |
| `nombre` | string | Nombre mostrado en panel y lector |
| `ubicacion` | string | Ubicacion del evento |
| `aforo_max` | int | Capacidad maxima |
| `aforo_actual` | int | Ocupacion actual |
| `estado` | string | `borrador`, `activo`, `cerrado` |
| `fecha_inicio` | string ISO | Fecha/hora inicio |
| `fecha_fin` | string ISO | Fecha/hora fin |
| `timezone` | string | Zona horaria |

Campos presentes en el esquema de ejemplo pero no usados activamente por la UI actual:

| Campo | Observacion |
|---|---|
| `modo_operacion` | Solo aparece en ejemplo |
| `umbral_alerta_aforo` | No se toma desde DB en panel actual |
| `permitir_reingreso` | No afecta la logica actual |
| `max_por_escaneo` | No se usa; el lector usa `1`, `2` o `todos` |
| `requiere_validacion_admin` | No se usa actualmente |
| `salt_secreto` | Se elimina al exponer configuracion al frontend |

### Ejemplo

```json
{
  "id_evento": "ev_2026_graduacion",
  "nombre": "Evento SIGA 2026",
  "aforo_max": 200,
  "aforo_actual": 0,
  "ubicacion": "Auditorio Principal",
  "estado": "activo",
  "fecha_inicio": "2026-04-11T10:00:00-06:00",
  "fecha_fin": "2026-04-11T22:00:00-06:00",
  "timezone": "America/Mexico_City"
}
```

## 7.2 Nodo `configuracion/seguridad`

Aparece en `schema_v2_ejemplo.json`, pero el codigo actual no lo consume de forma activa.

Campos de ejemplo:

- `hash_algoritmo`
- `version_qr`

En la practica, el algoritmo esta cableado en el codigo: **SHA-512**.

## 7.3 Nodo `eventos/{id_evento}`

Guarda el catalogo historico de eventos.

Campos:

| Campo | Tipo | Uso |
|---|---|---|
| `id_evento` | string | Identificador unico |
| `nombre` | string | Nombre del evento |
| `ubicacion` | string | Ubicacion |
| `aforo_max` | int | Capacidad maxima |
| `aforo_actual` | int | Aforo en ese evento |
| `estado` | string | `borrador`, `activo`, `cerrado` |
| `fecha_inicio` | string ISO | Inicio |
| `fecha_fin` | string ISO | Fin |
| `timezone` | string | Zona horaria |
| `created_at` | string ISO | Fecha de creacion |

Estados importantes:

- `borrador`: listo para preparacion
- `activo`: evento operativo
- `cerrado`: evento finalizado

## 7.4 Nodo `invitados/{hash_qr}`

Es la coleccion principal de invitados.

La **key del invitado es el hash SHA-512 del `id` + `QR_SALT_SECRETO`**.  
Eso significa:

- la key sirve como identificador interno
- la key tambien coincide con el hash incluido en el QR

Campos:

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string | ID o numero de cuenta del invitado |
| `nombre` | string | Nombre base |
| `nombre_lider` | string | Nombre mostrado como lider del grupo |
| `email` | string | Correo para envio de invitacion |
| `grupo_nombre` | string | Solo aparece en esquema ejemplo |
| `tipo_invitado` | string | Categoria, default `general` |
| `cupo_total` | int | Cupo maximo autorizado |
| `cupo_usado` | int | Cupo ya utilizado |
| `ingresados` | int | Campo legacy mantenido por compatibilidad |
| `status` | string | `dentro` o `fuera` |
| `invitacion_enviada` | bool | Si ya se envio correo |
| `bloqueado` | bool | Solo aparece en ejemplo, no usado en logica actual |
| `creado_en` | string ISO | Fecha de creacion |

### Reglas reales

- Al crear invitado por UI o importacion, el sistema fuerza `cupo_total = 3`.
- `cupo_usado` nunca puede exceder `cupo_total`.
- El status queda:
  - `dentro` si `cupo_usado > 0`
  - `fuera` si `cupo_usado == 0`

## 7.5 Nodo `logs/{push_id}`

Se usa para registrar trazabilidad operativa.

El contenido exacto cambia segun el evento.

Campos frecuentes:

| Campo | Uso |
|---|---|
| `evento` | Tipo de log |
| `timestamp` | Fecha del movimiento |
| `invitado_id` | Invitado afectado |
| `nombre_invitado` | Nombre mostrado |
| `id_evento` | Evento actual |
| `cantidad_entrada` | Personas que entraron |
| `cantidad_salida` | Personas que salieron |
| `sumar` | Modo de entrada solicitado |
| `restar` | Modo de salida solicitado |
| `cupo_total` | Cupo total del invitado |
| `ingresados_antes` | Estado anterior |
| `ingresados_despues` | Estado posterior |
| `fase_pdi` | Fase del pipeline QR que logro decodificar |
| `modo_conexion` | `nube` o `local` |
| `admin_override` | Si se forzo entrada con override |
| `lector_uid` | UID del lector que opero |
| `lector_nombre` | Nombre del lector |
| `lector_pin` | PIN del lector guardado en log |
| `dispositivo_id` | Dispositivo desde el que se opero |
| `sincronizado` | Solo aparece cuando el log esta en cola local |

Tipos de evento vistos en codigo:

- `qr_no_leido`
- `qr_formato_invalido`
- `qr_hash_invalido`
- `qr_valido_sin_registro`
- `qr_valido`
- `ingreso_registrado`
- `salida_registrada`

## 7.6 Nodo `usuarios_staff/{uid}`

Catalogo de operadores.

Campos:

| Campo | Tipo |
|---|---|
| `nombre` | string |
| `rol` | string |
| `email` | string |
| `pin` | string de 6 digitos |
| `activo` | bool |
| `ultimo_login` | string |
| `permisos` | objeto |

Roles admitidos en la practica:

- `admin`
- `lector`
- `supervisor`

### Reglas

- `lector` y `supervisor` requieren PIN valido de 6 digitos.
- El PIN debe ser unico entre usuarios staff.
- `admin` puede existir con o sin PIN, aunque en flujo actual el admin entra por login web.

## 7.7 Nodo `lectores_activos/{device_id}`

Se usa para mostrar lectores online y su ultimo heartbeat.

Campos:

| Campo | Tipo |
|---|---|
| `device_id` | string |
| `staff_uid` | string |
| `staff_nombre` | string |
| `pin` | string |
| `rol` | string |
| `modo` | `online` o `local` |
| `last_seen_at` | string ISO |

Solo se consideran activos si su `last_seen_at` esta dentro de la ventana de actividad.

Constante:

- `LECTOR_ACTIVE_WINDOW_SECONDS = 120`

## 7.8 Nodo `solicitudes_cupo/{push_id}`

Historial de solicitudes o decisiones de aumento de cupo.

Campos:

| Campo | Tipo | Uso |
|---|---|---|
| `invitado_id` | string | Invitado afectado |
| `invitado_key` | string | Key Firebase del invitado |
| `nombre_invitado` | string | Nombre visible |
| `cantidad_solicitada` | int | Cuanto se pidio |
| `cantidad_aprobada` | int | Cuanto se aprobo |
| `status` | string | `pendiente`, `aprobada`, `rechazada` |
| `motivo` | string | Motivo de solicitud |
| `solicitado_por_uid` | string | Quien solicito |
| `solicitado_por_nombre` | string | Nombre de quien solicito |
| `solicitado_desde` | string | `lector` o `admin` |
| `created_at` | string ISO | Creacion |
| `resolved_at` | string ISO | Resolucion |
| `resolved_by` | string | Actor que resolvio |
| `decision_note` | string | Justificacion |
| `cupo_total_anterior` | int | Cupo antes del cambio |
| `cupo_total_nuevo` | int | Cupo despues del cambio |
| `delta_cupo` | int | Diferencia aprobada |

## 7.9 Nodo `auditoria/eventos`

**Existe como destino esperado, pero no se escribe realmente desde el codigo actual.**

El endpoint `/api/eventos/audit` intenta leerlo, pero la funcion `audit_evento()` hoy solo hace `print`.

Conclusion:

- El historial de auditoria **esta planeado**.
- El endpoint existe.
- Pero la persistencia real de auditoria esta incompleta en el estado actual del proyecto.

## 7.10 Nodo `seguridad/lector_pin_lockouts/{device_id}`

Existe referencia en `firebase.py` por medio de `lector_lockout_ref(device_id)`.

Sin embargo:

- no se usa en el flujo real actual de login lector
- no hay bloqueo de PIN activo en el codigo final presente

Es decir, **es un remanente de una idea de lockout**, pero no una funcionalidad activa.

---

## 8. Flujo de autenticacion y sesiones

## 8.1 Login admin

Ruta: `/login`

Flujo:

1. El usuario envia `usuario` y `password`.
2. El backend calcula:

```text
sha512(password + QR_SALT_SECRETO)
```

3. Compara:
   - `usuario` contra `ADMIN_USER`
   - hash calculado contra `ADMIN_PASSWORD_HASH`
4. Si coincide:
   - `session["admin_ok"] = True`
   - `session["admin_user"] = usuario`
5. Redirige a `/admin`

## 8.2 Login lector por PIN

Ruta: `POST /api/lector/login`

Flujo:

1. Recibe `pin`, `device_id`, `modo`.
2. Normaliza `pin`.
3. Verifica formato de 6 digitos.
4. Lee `usuarios_staff`.
5. Filtra usuarios:
   - activos
   - rol en `lector`, `supervisor`, `admin`
6. Busca coincidencias por PIN.
7. Si hay mas de una, devuelve conflicto.
8. Si hay exactamente una:
   - guarda `session["lector_auth"]`
   - registra lector activo en Firebase

## 8.3 Auto-login de admin en lector

En `static/js/lector.js`, si el navegador ya tiene sesion admin valida, el lector intenta:

- `POST /api/lector/admin_login`

Esto permite abrir `/lector` desde el panel sin volver a capturar PIN.

## 8.4 Donde vive la sesion

El sistema usa `flask.session`.

Eso implica:

- la sesion se firma con `FLASK_SECRET_KEY`
- la informacion queda serializada en cookie de Flask
- no hay backend propio de sesiones

### Dato importante

La sesion del lector contiene:

- `uid`
- `nombre`
- `rol`
- `pin`
- `device_id`
- timestamps

O sea, el PIN del lector queda dentro de la estructura de sesion de Flask.

---

## 9. Reglas de negocio principales

## 9.1 Estados del evento

Estados validos:

- `borrador`
- `activo`
- `cerrado`

Reglas:

- un evento nuevo nace en `borrador`
- solo el endpoint `publish` lo vuelve `activo`
- solo el endpoint `close` lo vuelve `cerrado`

## 9.2 Cupo de invitados

Reglas observadas:

- cupo inicial por alta e importacion: `3`
- el lector puede registrar:
  - `+1`
  - `+2`
  - `todos`
- el cupo usado no puede superar el total

## 9.3 Aforo global

El aforo global se guarda en `configuracion/evento_actual.aforo_actual`.

Se actualiza:

- al registrar entrada: suma `delta_real`
- al registrar salida: resta `salida_real`

## 9.4 Formato del QR

Formato esperado:

```text
ID|HASH
```

Donde:

- `ID` es el identificador del invitado
- `HASH` es `sha512(ID + QR_SALT_SECRETO)`

## 9.5 Key del invitado

La key Firebase del invitado tambien se genera con:

```text
sha512(invitado_id + QR_SALT_SECRETO)
```

Por eso el backend puede buscar:

- primero por hash
- despues por ID

## 9.6 Override admin

Si el evento esta cerrado:

- un lector normal no puede registrar ingreso
- admin puede forzar ingreso
- lector no-admin puede hacer override solo si confirma su PIN actual

## 9.7 Solicitudes de aumento de cupo

La logica actual hace una resolucion automatica:

- si hay disponibilidad de aforo suficiente: `aprobada`
- si no: `rechazada`

Esto significa que en el flujo normal **no quedan solicitudes pendientes**.

---

## 10. Backend por modulo

## 10.1 `firebase.py`

Este modulo encapsula acceso a Firebase.

### Funciones principales

| Funcion | Que hace |
|---|---|
| `_resolve_firebase_credentials()` | Carga credenciales desde JSON inline o archivo |
| `init_firebase()` | Inicializa Firebase y hace lectura de prueba |
| `leer_invitados()` | Lee nodo `invitados` |
| `leer_eventos()` | Lee nodo `eventos` |
| `leer_staff()` | Lee nodo `usuarios_staff` |
| `leer_logs()` | Lee logs Firebase y ademas mezcla cola local |
| `leer_solicitudes_cupo()` | Lee solicitudes de cupo |
| `evento_actual_config()` | Lee `configuracion/evento_actual` |
| `estado_evento_activo()` | Devuelve ID y config del evento activo |
| `buscar_invitado()` | Busca primero por hash, luego por ID |
| `registrar_lector_activo()` | Marca un lector como activo |
| `quitar_lector_activo()` | Elimina lector activo |
| `leer_lectores_activos()` | Regresa lectores recientes |
| `resumen_disponibilidad_cupo()` | Calcula aforo disponible restante |

### Observaciones

- Si Firebase no esta listo, casi todas las lecturas devuelven vacio.
- `leer_logs()` mezcla:
  - logs remotos
  - pendientes locales

Eso hace que panel y reportes puedan ver datos no sincronizados.

## 10.2 `sync.py`

Este modulo solo sincroniza **logs**, no toda la operacion.

### Flujo

1. `guardar_log(evento)` intenta escribir a Firebase.
2. Si falla:
   - agrega `sincronizado=False`
   - guarda el evento en `pendientes.json`
3. `worker_sincronizacion()` corre cada 30 segundos.
4. `sincronizar_pendientes()` reintenta subir los logs pendientes.

### Importante

En serverless:

- no hay archivo local persistente real
- no se usa la cola offline
- el worker no arranca

### Consecuencia

La sincronizacion offline es util principalmente en ejecucion local tradicional, no en Vercel.

## 10.3 `qr_lector.py`

Encapsula la decodificacion QR con OpenCV.

### Pipeline actual

Orden obligatorio:

1. escala de grises
2. threshold fijo
3. threshold adaptativo gaussiano

La funcion principal es:

- `pipeline_decodificacion(imagen_bgr)`

Devuelve:

- `texto` del QR si pudo decodificar
- `fase` que funciono

Ejemplos de fase:

- `Fase 1: Escala de grises`
- `Fase 2: Threshold fijo`
- `Fase 3: Threshold adaptativo gaussiano`

## 10.4 `funciones_extras.py`

Es el modulo utilitario mas grande.

### Areas funcionales

#### A. Normalizacion y validacion

- `safe_int`
- `parse_bool_param`
- `normalizar_email`
- `normalizar_nombre`
- `normalizar_id`
- `normalize_pin`
- `normalize_device_id`
- `is_valid_pin`
- `validar_datos_invitado`

#### B. Construccion de vistas de datos

- `invitados_listado`
- `staff_listado`
- `eventos_listado`
- `solicitudes_cupo_listado`
- `filtrar_y_paginar_invitados`
- `paginar_rows`
- `indexar_invitados_por_id`

#### C. Sesion y autorizacion

- `admin_logueado`
- `lector_session_data`
- `lector_touch_session`
- `lector_logout_session`
- `lector_is_idle`
- `require_lector_session`
- `actor_admin`

#### D. QR y seguridad

- `obtener_salt_secreto`
- `generar_hash_qr`
- `extraer_datos_qr`
- `validar_hash_qr`

#### E. Email e invitaciones

- `smtp_client`
- `enviar_invitacion_email`

#### F. Dashboard y reportes

- `construir_dashboard_data`
- `construir_reporte_data`
- `reporte_csv`
- `reporte_pdf_bytes`

#### G. Configuracion y eventos

- `required_event_fields`
- `sanitized_config`
- `normalize_event_state`
- `active_event_id_from_rows`

#### H. Auditoria

- `calc_changes`
- `audit_evento`

### Estado real de auditoria

Actualmente:

- `calc_changes()` devuelve `[]`
- `audit_evento()` solo imprime `Cambio registrado: ...`

No guarda registros en Firebase.

## 10.5 `rutas.py`

Es el corazon del sistema.

Aqui vive:

- login
- panel admin
- lector
- CRUD de invitados
- importaciones
- eventos
- staff
- reportes
- validacion QR
- registro de entradas y salidas

Como este archivo es el mas importante, se documenta aparte por endpoint.

---

## 11. Catalogo completo de endpoints

## 11.1 Paginas HTML

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET/POST` | `/login` | Publico | Login admin |
| `GET` | `/logout` | Admin | Limpia sesion y redirige a login |
| `GET` | `/admin` | Admin | Renderiza panel admin |
| `GET` | `/` | Publico | Redirige a `/admin` |
| `GET` | `/lector` | Publico | Renderiza portal lector |
| `GET` | `/health` | Publico | Salud simple del backend |

## 11.2 API del lector

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/lector/staff` | Publico | Lista staff activo con PIN valido |
| `POST` | `/api/lector/login` | Publico | Login lector por PIN |
| `POST` | `/api/lector/admin_login` | Admin | Auto-login de admin dentro del lector |
| `POST` | `/api/lector/heartbeat` | Lector | Mantiene sesion y presencia activa |
| `POST` | `/api/lector/logout` | Lector/Admin | Remueve lector activo y limpia sesion lector |
| `GET` | `/api/lector_estado` | Lector opcional | Devuelve evento, aforo y estado lector |

### Notas

- `heartbeat` devuelve `200` incluso cuando requiere PIN, con `requires_pin=true`.
- `lector_estado` devuelve `requires_pin=true` si no hay sesion.

## 11.3 Dashboard y estado admin

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/dashboard` | Admin | Dashboard operativo |
| `POST` | `/api/sync/retry` | Admin | Reintento manual de sincronizacion |
| `GET` | `/api/admin_state` | Admin | Snapshot general de admin |
| `PUT` | `/api/configuracion/evento_actual` | Admin | Actualiza evento actual |

## 11.4 Invitados

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/invitados` | Admin | Lista invitados paginados o completos |
| `POST` | `/api/invitados` | Admin | Crea invitado |
| `PUT` | `/api/invitados/<invitado_key>` | Admin | Edita invitado |
| `DELETE` | `/api/invitados/<invitado_key>` | Admin | Elimina invitado |
| `POST` | `/api/invitados/import` | Admin | Importa CSV/XLSX |
| `POST` | `/api/invitados/batch` | Admin | Lote: enviar invitacion o exportar |
| `GET` | `/api/invitados/export` | Admin | Descarga CSV |

### Reglas del import

Acepta:

- `.csv`
- `.xlsx`

Campos esperados:

- `id`
- `nombre`
- `email`

Alias soportados:

- `ID`
- `Id`
- `Nombre`
- `nombre_lider`
- `Email`
- `correo`
- `Correo`

### Dato importante

El frontend acepta `.xls` visualmente, pero el backend **no lo procesa**.  
Eso genera una diferencia entre UI y servidor.

## 11.5 Solicitudes de cupo

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/solicitudes_cupo` | Admin | Lista historial de solicitudes |
| `POST` | `/api/solicitudes_cupo` | Admin o Lector | Solicita aumento de cupo |
| `POST` | `/api/solicitudes_cupo/<solicitud_id>/resolver` | Admin | Resuelve solicitud pendiente |

### Importante

Aunque existe el endpoint de resolucion manual, el `POST /api/solicitudes_cupo` actual:

- auto-aprueba
- o auto-rechaza

Por eso, en condiciones normales, es raro que exista una solicitud `pendiente`.

## 11.6 Eventos

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/eventos` | Admin | Lista eventos |
| `POST` | `/api/eventos` | Admin | Crea evento nuevo en borrador |
| `PUT` | `/api/eventos/<event_id>` | Admin | Actualiza evento |
| `POST` | `/api/eventos/<event_id>/publish` | Admin | Activa evento |
| `POST` | `/api/eventos/<event_id>/close` | Admin | Cierra evento |
| `POST` | `/api/eventos/<event_id>/clone` | Admin | Clona evento |
| `GET` | `/api/eventos/audit` | Admin | Intenta leer auditoria |

### Regla fuerte al cerrar evento

Cuando se cierra un evento, el sistema intenta:

- marcarlo como `cerrado`
- actualizar `configuracion/evento_actual`
- borrar `invitados`
- borrar `solicitudes_cupo`

Eso significa que **el cierre limpia asistentes y cupos para el siguiente evento**.

## 11.7 Staff y lectores

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `POST` | `/api/usuarios_staff` | Admin | Crea usuario staff |
| `PUT` | `/api/usuarios_staff/<uid>` | Admin | Edita staff |
| `DELETE` | `/api/usuarios_staff/<uid>` | Admin | Elimina staff |
| `POST` | `/api/lectores/<uid>/disconnect` | Admin | Desconecta sesiones activas de ese UID |

## 11.8 Reportes

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `GET` | `/api/reportes` | Admin | Devuelve resumen y movimientos |
| `GET` | `/api/reportes/export` | Admin | Exporta CSV o PDF |

Formatos soportados:

- `csv`
- `pdf`

## 11.9 Escaneo y control de acceso

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| `POST` | `/validar_qr` | Lector | Decodifica y valida QR |
| `POST` | `/registrar_ingreso` | Lector/Admin | Registra entrada |
| `POST` | `/registrar_salida` | Admin | Registra salida |

---

## 12. Flujo operativo completo

## 12.1 Preparacion del evento

1. El admin entra por `/login`.
2. Crea eventos desde la seccion "Preparar Siguiente Evento".
3. El evento se guarda en `eventos/{id_evento}` con estado `borrador`.
4. Cuando quiere usarlo, lo publica:
   - el evento pasa a `activo`
   - cualquier evento activo previo pasa a `borrador`
   - `configuracion/evento_actual` se sobreescribe con ese evento

## 12.2 Registro de invitados

Hay dos caminos:

### Alta manual

1. Se abre modal "Nuevo Invitado".
2. Se captura:
   - nombre
   - email
   - ID
3. El backend:
   - valida duplicados por ID/email
   - fija `cupo_total = 3`
   - genera key hash
   - guarda en Firebase

### Importacion masiva

1. Se sube CSV/XLSX.
2. Se parsea fila por fila.
3. Se validan errores y duplicados.
4. Se insertan invitados validos.
5. Si hubo errores, se genera CSV de errores.

## 12.3 Envio de invitaciones

1. El admin puede enviar invitacion individual o en lote.
2. Se crea payload QR:

```text
invitado_id|hash_qr
```

3. `qrcode` genera una imagen PNG.
4. `yagmail` envia correo HTML con:
   - nombre
   - ID
   - cupo
   - fecha del evento
   - hora del evento
   - ubicacion
   - QR embebido
5. Si sale bien:
   - `invitacion_enviada = True`

## 12.4 Alta de lectores

1. El admin crea usuarios en `usuarios_staff`.
2. Los roles tipicos son `lector` o `supervisor`.
3. Cada lector requiere PIN de 6 digitos.
4. En la seccion "Portal de Lectores" se genera:
   - enlace a `/lector`
   - QR del enlace

## 12.5 Login del lector

En `/lector`:

1. Se genera o reutiliza `deviceId` en `localStorage`.
2. Si el navegador ya tiene sesion admin:
   - intenta auto-login admin
3. Si no:
   - muestra modal de PIN
4. Tras login:
   - guarda sesion lector
   - reporta presencia a `lectores_activos`
   - intenta encender camara

## 12.6 Deteccion de QR en el lector

La deteccion real tiene dos capas:

### Capa 1: frontend

`static/js/lector.js`:

- abre la camara
- recorta un area cuadrada del centro
- dibuja el frame en un canvas
- usa `BarcodeDetector` para saber si parece haber QR

Esto es una optimizacion: evita mandar frames al backend si no se detecta nada.

### Capa 2: backend

`/validar_qr`:

1. recibe `imagen_base64`
2. la convierte a bytes
3. la convierte a `numpy array`
4. OpenCV la decodifica
5. intenta varias fases del pipeline
6. si obtiene texto:
   - separa `ID|HASH`
   - recalcula hash esperado
   - busca invitado en Firebase
7. responde:
   - si el QR es invalido
   - si el hash no corresponde
   - si el invitado no existe
   - o si el invitado es valido

## 12.7 Registro de ingreso

Una vez validado el QR:

1. El lector muestra datos del invitado.
2. Calcula disponibilidad:
   - `cupo_total - cupo_usado`
3. Habilita botones:
   - `+1`
   - `+2`
   - `Todos`
4. Al confirmar:
   - llama `/registrar_ingreso`
5. El backend:
   - valida sesion
   - valida si el evento esta cerrado
   - aplica override si corresponde
   - encuentra al invitado
   - suma el cupo solicitado
   - actualiza `cupo_usado`, `ingresados`, `status`
   - actualiza `aforo_actual`
   - registra log

## 12.8 Solicitud de aumento de cupo

Si el invitado ya agoto cupo:

1. El lector ofrece "Solicitar mas cupo".
2. El operador escribe una cantidad.
3. Se envia a `/api/solicitudes_cupo`.
4. El backend calcula disponibilidad global:
   - `aforo_max - boletos_entregados`
5. Si alcanza:
   - aprueba automatico
   - aumenta `cupo_total`
   - registra solicitud como `aprobada`
6. Si no alcanza:
   - registra solicitud como `rechazada`

## 12.9 Registro de salida

Solo el admin puede registrar salida.

1. Se manda `/registrar_salida`.
2. El backend:
   - resta `1`, `2` o `todos`
   - actualiza `cupo_usado`
   - actualiza `status`
   - reduce `aforo_actual`
   - genera log `salida_registrada`

## 12.10 Reportes

Los reportes se construyen a partir de logs:

1. Se leen logs remotos y pendientes locales.
2. Se filtran por fecha si aplica.
3. Se clasifican movimientos en:
   - entrada
   - salida
4. Se genera resumen:
   - entradas total
   - salidas total
   - movimientos total
   - aforo total
   - aforo utilizado
   - capacidad disponible
5. Se exporta CSV o PDF

---

## 13. Frontend administrador

## 13.1 Vista general de `templates/admin.html`

El panel tiene estas vistas:

| Vista | ID HTML | Proposito |
|---|---|---|
| Panel de control | `view-dashboard` | KPIs, aforo, sync, lectores, ultimos ingresos |
| Invitados | `view-invitados` | CRUD, filtros, lote, importacion, historial de cupo |
| Eventos | `view-eventos` | Evento activo y configuracion del evento actual |
| Planeacion e historial | `view-nuevo-evento` | Crear siguiente evento e historial |
| Lectores | `view-lectores` | Portal, alta y gestion de lectores |
| Lector QR | `view-lector-qr` | Iframe embebido de `/lector` |
| Reportes | `view-reportes` | Resumen y exportaciones |
| Debug QRs | `view-debug-qrs` | Visualizacion de QRs de prueba |

Tambien hay modales:

- `inviteModal`
- `editInviteModal`
- `editLectorModal`

## 13.2 `static/js/admin.js`

Este archivo funciona como controlador completo del panel.

### Estados locales principales

| Variable | Uso |
|---|---|
| `adminState` | Snapshot del backend |
| `eventosState` | Eventos + auditoria |
| `invitadosState` | Filtros, pagina, seleccion y resultados |
| `solicitudesCupoState` | Historial de cupo |
| `lectoresState` | Staff + presencias online |
| `debugQrsState` | Cache para debug de QRs |

### Refresh automatico

Al iniciar:

- `refreshAll()`
- luego cada 15 segundos vuelve a ejecutar `refreshAll()`

### Que carga `refreshAll()`

1. `/api/admin_state`
2. `renderEventos()`
3. `prepareLectoresData()`
4. `renderLectores()`
5. `renderConfig()`
6. `renderReportes()`
7. `refreshEventosAudit()`
8. `refreshDashboard()`
9. `refreshInvitados()`
10. `refreshSolicitudesCupo()`

### Funciones importantes

| Funcion | Rol |
|---|---|
| `bindUI()` | Conecta botones y formularios |
| `setView(view)` | Cambia de seccion visible |
| `refreshDashboard()` | Llama `/api/dashboard` |
| `refreshInvitados()` | Llama `/api/invitados` paginado |
| `refreshSolicitudesCupo()` | Llama `/api/solicitudes_cupo` |
| `renderDashboard()` | Pinta KPIs |
| `renderInvitados()` | Pinta tabla invitados |
| `ejecutarBatch()` | Envia invitaciones o exporta en lote |
| `renderEventos()` | Pinta evento activo |
| `renderEventosHistory()` | Pinta historial de eventos |
| `prepareLectoresData()` | Une staff con sesiones activas |
| `renderLectores()` | Pinta lectores y sus acciones |
| `setupLectorAccess()` | Genera QR del portal lector |
| `handleImportFile()` | Importa CSV/XLSX |
| `renderReportes()` | Pinta tabla de movimientos |

### Debug QRs

La vista de debug:

1. llama `/api/invitados?all=true`
2. toma `id`, `nombre`, `key`
3. genera en cliente el QR con payload:

```text
id|key
```

Esto es muy util para pruebas porque reproduce el formato real que espera `/validar_qr`.

---

## 14. Frontend lector

## 14.1 Vista `templates/lector.html`

La pantalla del lector tiene:

- encabezado con nombre del evento y lector
- estado de conexion `Nube` / `Local`
- aforo actual
- stage de camara
- overlay de procesamiento
- panel del invitado detectado
- botones `+1`, `+2`, `Todos`
- boton para pausar/reanudar camara
- boton de flash
- modal de login por PIN

## 14.2 `static/js/lector.js`

Este archivo implementa la operacion del lector en tiempo real.

### Variables clave

| Variable | Uso |
|---|---|
| `stream` | Stream de la camara |
| `currentValidatedGuest` | Invitado actualmente validado |
| `currentAforo` | Aforo local visible |
| `currentEvent` | Evento mostrado |
| `currentLector` | Sesion actual |
| `scanIntervalId` | Loop de escaneo |
| `isProcessing` | Evita escaneos en paralelo |
| `isFrameFrozen` | Congela pantalla al detectar QR |
| `qrDetector` | Instancia `BarcodeDetector` |
| `deviceId` | ID persistente del dispositivo |

### `deviceId`

Se guarda en:

```text
localStorage["siga_lector_device_id"]
```

Formato generado:

```text
dev_<random><timestamp>
```

### Heartbeat

Se manda cada 10 segundos a:

- `/api/lector/heartbeat`

### Refresh de estado

Se consulta cada 20 segundos:

- `/api/lector_estado`

### Flujo de camara

1. pide `getUserMedia`
2. usa camara trasera idealmente
3. cada 650 ms intenta escanear
4. si encuentra QR:
   - congela frame
   - manda imagen al backend

### Optimizaciones visuales

- pausar scan si la pestaña queda oculta
- congelar el frame para que el operador vea lo que se valido
- vibracion distinta para exito, warning y error

### Flujo cuando el invitado es valido

1. muestra nombre
2. muestra ID
3. muestra cupo usado/total
4. muestra fase PDI
5. habilita botones de entrada segun disponibilidad

### Flujo cuando el cupo esta agotado

1. muestra snapshot del invitado
2. advierte cupo agotado
3. ofrece solicitar aumento de cupo

### Flash

Usa `track.getCapabilities().torch` si el dispositivo lo soporta.

### Compatibilidad

Si el navegador no soporta `BarcodeDetector`, el lector muestra mensaje de incompatibilidad y deshabilita acciones.

---

## 15. Reportes y dashboard

## 15.1 Dashboard

`construir_dashboard_data()` produce:

- aforo actual
- aforo maximo
- total de invitados registrados
- invitados pendientes
- sincronizaciones pendientes
- ultimos ingresos
- firebase ready
- nombre y ubicacion del evento
- lista de eventos
- alertas
- ultima sincronizacion
- lectores online/local/total

### Alertas actuales

Se generan si:

- aforo >= 100%
- aforo >= 90%
- hay pendientes de sincronizacion
- hubo error de sync
- no hay lectores activos

## 15.2 Reportes operativos

`construir_reporte_data()` toma logs y produce:

### Resumen

- `entradas_total`
- `salidas_total`
- `movimientos_total`
- `aforo_total`
- `aforo_utilizado`
- `capacidad_disponible`

### Movimientos

Para cada log clasificado:

- timestamp
- hora
- tipo
- cantidad
- invitado_id
- nombre_invitado
- modo

## 15.3 Export CSV

Incluye:

- bloque de resumen
- detalle de movimientos

## 15.4 Export PDF

Se arma con `reportlab` y muestra:

- titulo
- rango
- resumen
- tabla de detalle

Limite de detalle en PDF:

- maximo 100 movimientos en el render del documento

---

## 16. Diseño del QR y seguridad logica

## 16.1 Generacion del hash

Funcion:

- `funciones_extras.generar_hash_qr(invitado_id)`

Formula:

```text
sha512(invitado_id + QR_SALT_SECRETO)
```

## 16.2 Validacion del hash

Funcion:

- `funciones_extras.validar_hash_qr(invitado_id, hash_recibido)`

Simplemente recalcula el hash esperado y lo compara con el recibido.

## 16.3 Ventaja

- evita que un QR con solo ID sea suficiente
- obliga a conocer el salt para falsificar correctamente

## 16.4 Limitacion

- si el salt se expone, todos los QRs pueden recalcularse
- el QR no incluye expiracion ni nonce
- no esta ligado a un evento especifico en el payload actual

---

## 17. Modo local y sincronizacion offline

Este punto es importante porque el proyecto habla de "Nube" y "Local".

## 17.1 Lo que si hace

- marca la conexion visual como `Nube` o `Local`
- guarda logs en `pendientes.json` si falla subirlos
- intenta resincronizar esos logs cada 30 segundos

## 17.2 Lo que no hace completamente

La operacion critica sigue dependiendo de Firebase:

- buscar invitado
- validar existencia de invitado
- registrar entradas
- registrar salidas
- consultar invitados
- crear/modificar invitados

Por ejemplo:

- `/registrar_ingreso` devuelve `503` si `firebase_ready` es falso
- `/registrar_salida` tambien
- `firebase.buscar_invitado()` devuelve `None` sin Firebase

### Conclusión tecnica

El "modo local" actual es **parcial**:

- hay tolerancia para logs
- pero no hay operacion offline completa del control de acceso

---

## 18. Comportamiento al cerrar evento

Esta es una de las decisiones mas fuertes del sistema.

Cuando se ejecuta:

- `POST /api/eventos/<event_id>/close`

Sucede:

1. el evento pasa a `cerrado`
2. si es el evento activo, `configuracion/evento_actual.estado = "cerrado"`
3. se intenta borrar:
   - `invitados`
   - `solicitudes_cupo`

### Implicacion

El cierre del evento funciona como una limpieza operativa para arrancar el siguiente evento.

Si se esperaba conservar la lista de invitados dentro de Firebase despues del cierre, **el codigo actual no lo hace**.

---

## 19. Inconsistencias o huecos detectados en el codigo actual

Esta seccion no es critica del proyecto; es documentacion del estado real.

## 19.1 Auditoria incompleta

- `audit_evento()` no guarda nada, solo imprime.
- `calc_changes()` devuelve lista vacia.
- `/api/eventos/audit` intenta leer `auditoria/eventos`.

Resultado:

- existe UI de historial de cambios
- existe endpoint
- pero la persistencia de auditoria no esta terminada

## 19.2 Lockout de PIN no activo

Hay rastros de diseño para bloqueo por intentos fallidos:

- constantes `LECTOR_MAX_PIN_ATTEMPTS`
- `LECTOR_LOCKOUT_SECONDS`
- `firebase.lector_lockout_ref()`

Pero el flujo actual de login lector no usa ese mecanismo.

## 19.3 Resolver solicitudes pendientes vs auto-resolucion

Existe:

- `POST /api/solicitudes_cupo/<solicitud_id>/resolver`

Pero el endpoint de creacion normalmente auto-resuelve:

- `aprobada`
- o `rechazada`

Eso deja la ruta de resolver manual con poco uso real.

## 19.4 Frontend acepta `.xls`, backend no

- UI: permite `.csv,.xlsx,.xls`
- backend: solo maneja `.csv` y `.xlsx`

## 19.5 "Descargar Plantilla Excel" en realidad descarga CSV

El boton del panel dice "Descargar Plantilla Excel", pero el archivo generado por JS es un CSV simple.

## 19.6 Filtros de reporte existen en JS/backend, pero no en la UI

El backend soporta:

- `desde`
- `hasta`

`admin.js` tambien puede armar esos params, pero el form de reportes actual no tiene campos de fecha visibles; solo botones de exportacion.

## 19.7 Link "Ver todos los ingresos"

En `templates/admin.html` existe `#viewAllIngresos`, pero no hay una logica visible en `admin.js` que lo conecte a una accion real.

## 19.8 Modo offline parcial

Ya explicado antes:

- la cola offline solo cubre logs
- no cubre operacion transaccional completa

## 19.9 Campos del esquema ejemplo no usados por la app actual

En `schema_v2_ejemplo.json` hay campos mas ricos que el frontend no explota hoy, por ejemplo:

- `modo_operacion`
- `permitir_reingreso`
- `requiere_validacion_admin`
- `umbral_alerta_aforo`
- `configuracion/seguridad`

---

## 20. Archivos auxiliares y su sentido

## 20.1 `fix_types.py`

Script de mantenimiento que recorre archivos `.py` y elimina anotaciones de tipos usando regex.

No se usa en runtime.

## 20.2 `scratch_split.py`

Script experimental que intenta partir un `app.py` monolitico en varios modulos.

No se usa en runtime.

## 20.3 `scratch_modify_app.py`

Script experimental que modifica codigo por regex:

- remueve typing
- cambia comparaciones
- toca auditoria
- toca lockouts

No se usa en runtime.

## 20.4 `estudiantes_prueba.csv`

Archivo de ejemplo para importar invitados.

Contenido esperado:

- `ID`
- `nombre`
- `correo`

## 20.5 `schema_v2_ejemplo.json`

Documento de referencia del esquema aspiracional o extendido.

## 20.6 `siga_schema_seed.json`

Seed inicial simplificado.

---

## 21. Resumen por archivo

| Archivo | Resumen corto |
|---|---|
| `app.py` | Inicializa Flask, valida entorno, arranca Firebase y sync |
| `api/index.py` | Entrada para Vercel |
| `rutas.py` | Toda la capa HTTP y gran parte de la logica del negocio |
| `firebase.py` | Fachada de acceso a Firebase |
| `funciones_extras.py` | Utilidades, reportes, email, QR hash, sesiones |
| `sync.py` | Cola de logs offline |
| `qr_lector.py` | Decodificador QR por fases |
| `admin.html` | Interfaz admin de varias secciones |
| `lector.html` | Interfaz minimalista de escaneo |
| `admin.js` | Controlador del panel admin |
| `lector.js` | Controlador del lector y escaneo |
| `styles.css` | Estilos comunes de login, admin y lector |

---

## 22. Resumen funcional final

SIGA, en su estado actual, es un sistema web de operacion de eventos con estos componentes funcionales claros:

1. **Administracion del evento**
   - crear
   - activar
   - cerrar
   - editar configuracion actual

2. **Gestion de invitados**
   - alta manual
   - importacion
   - exportacion
   - envio de invitaciones por correo

3. **Gestion de lectores**
   - alta de staff lector
   - PIN por lector
   - monitoreo de sesiones activas
   - portal lector compartible por QR

4. **Operacion en acceso**
   - login por PIN
   - lectura de QR
   - validacion criptografica basica por hash
   - registro de ingreso
   - solicitud de aumento de cupo

5. **Control de aforo**
   - contador de ocupacion actual
   - reportes de entradas/salidas
   - alertas de capacidad

6. **Persistencia y tolerancia parcial a fallos**
   - Firebase como base central
   - cola local solo para logs

7. **Puntos pendientes o incompletos**
   - auditoria persistente
   - lockout de PIN
   - offline operativo completo

---

## 23. Si quieres extender el sistema, donde tocar

### Si quieres cambiar el esquema de invitados

- `funciones_extras.validar_datos_invitado`
- `funciones_extras.invitados_listado`
- `rutas.api_invitados`
- `rutas.api_importar_invitados`
- `templates/admin.html`
- `static/js/admin.js`

### Si quieres cambiar la forma del QR

- `funciones_extras.generar_hash_qr`
- `funciones_extras.extraer_datos_qr`
- `funciones_extras.validar_hash_qr`
- `funciones_extras.enviar_invitacion_email`
- `static/js/admin.js` en la vista Debug QRs

### Si quieres hacer offline real

- `firebase.buscar_invitado`
- `registrar_ingreso`
- `registrar_salida`
- alguna base local para invitados y aforo
- sincronizacion bidireccional, no solo de logs

### Si quieres arreglar auditoria

- implementar escritura en `funciones_extras.audit_evento`
- implementar `calc_changes`
- revisar consumo en `/api/eventos/audit`

### Si quieres endurecer seguridad

- mover sesiones a backend server-side
- no guardar PIN en sesion
- implementar lockout real
- no almacenar service accounts dentro del repo

---

## 24. Cierre

Esta documentacion describe **el comportamiento real del codigo actual**, no solo la intencion del sistema.

En resumen:

- la arquitectura principal esta clara y funcional
- el flujo operativo de evento, invitados, lector y reportes existe
- la base de datos gira alrededor de Firebase Realtime Database
- el QR usa hash SHA-512 con salt secreto
- el panel admin y el lector estan bien separados
- la sincronizacion offline existe, pero solo para logs
- hay varias piezas planeadas que todavia no estan completas, especialmente auditoria y lockout de PIN

Si despues quieres, el siguiente paso natural es hacer un segundo documento:

- uno orientado a **manual de usuario**
- o uno orientado a **manual de mantenimiento y desarrollo**

