# Sistema de Control de Asistencia Biométrico

Sistema web de control de asistencia integrado con el dispositivo biométrico **ZKTeco MB560-VL**
(IP por defecto `192.168.18.202:4370`), inspirado en BioTime Pro.

Gestiona el maestro de empleados, sincroniza sus datos con el equipo, descarga las marcaciones,
las evalúa contra horarios y turnos, y produce los reportes de **tardanzas y faltas** que RRHH
usa para aplicar descuentos en planilla.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Django 5.1 + Django REST Framework |
| Base de datos | PostgreSQL (producción) / SQLite (desarrollo) |
| Tareas asíncronas | Celery + Redis |
| Dispositivo | `pyzk` (protocolo nativo ZKTeco, TCP/UDP 4370) |
| Frontend | React 19 + TypeScript + Vite |
| UI | Ant Design 6 + Recharts + React Query |

---

## Enrolamiento biométrico: cómo funciona

El registro de **rostro y huella se realiza en el equipo físico**, no desde la web. Esto no es una
limitación del sistema sino del protocolo: el algoritmo de reconocimiento facial de ZKTeco es
propietario y no expone sus plantillas.

El flujo real es:

1. Se registra al empleado en el sistema web (datos personales, laborales, código de empleado).
2. Se **suben sus datos al dispositivo** (botón "Subir empleados pendientes").
3. El empleado se acerca al equipo y **enrola su huella y su rostro** allí.
4. Se ejecuta **"Respaldar huellas del equipo"**: el sistema descarga las plantillas de huella,
   las guarda cifradas en base64 y actualiza los indicadores `tiene_huella` / `tiene_rostro`.
5. Desde ese momento las marcaciones se descargan automáticamente cada 15 minutos.

Las huellas respaldadas pueden **restaurarse** en un equipo nuevo o reseteado (botón "Restaurar
huellas" en la ficha del empleado), evitando que el personal deba volver a enrolarse. La plantilla
de rostro permanece únicamente en el dispositivo.

---

## Instalación

### Requisitos

- Python 3.12+
- Node.js 20+
- PostgreSQL 14+ (opcional en desarrollo; ver más abajo)
- Redis (opcional en desarrollo; ver más abajo)
- Acceso de red al dispositivo ZKTeco

### Backend

```bash
python -m venv venv
```

```bash
venv\Scripts\pip install -r backend\requirements.txt
```

Copie `backend/.env.example` a `backend/.env` y ajuste los valores. Luego:

```bash
cd backend && ..\venv\Scripts\python manage.py migrate
```

```bash
cd backend && ..\venv\Scripts\python manage.py inicializar
```

El comando `inicializar` es idempotente y crea: el usuario administrador, el dispositivo apuntando
a `192.168.18.202` (con el admin de equipo `6999383` protegido), la sede y departamentos base, y
un horario y turno de lunes a viernes.

Credenciales iniciales: `admin@biometrico.local` / `Admin2025!` — **cámbielas al primer ingreso**.

```bash
cd backend && ..\venv\Scripts\python manage.py runserver
```

### Frontend

```bash
cd frontend && npm install
```

```bash
cd frontend && npm run dev
```

La aplicación queda en `http://localhost:5173` y consume la API en `http://localhost:8000/api`
(configurable con `VITE_API_URL` en `frontend/.env`).

### Tareas programadas (Celery)

En desarrollo, `CELERY_TASK_ALWAYS_EAGER=True` en el `.env` ejecuta las tareas en línea y evita
tener que instalar Redis. En producción se levantan dos procesos:

```bash
cd backend && ..\venv\Scripts\celery -A config worker -l info --pool=solo
```

```bash
cd backend && ..\venv\Scripts\celery -A config beat -l info
```

Programación por defecto:
- **Cada 15 minutos**: descarga de marcaciones y procesamiento de los días afectados.
- **03:00 diario**: recálculo de la asistencia del día anterior (a esa hora ya llegaron las
  salidas de los turnos nocturnos).

---

## Paso a producción

1. En `backend/.env`: `DEBUG=False`, `SECRET_KEY` nueva, `ALLOWED_HOSTS` con el host real.
2. Cambiar `DB_ENGINE=postgres` y completar las credenciales de PostgreSQL.
3. `CELERY_TASK_ALWAYS_EAGER=False` y apuntar `CELERY_BROKER_URL` al Redis real.
4. **Cambiar la IP del dispositivo** desde la pantalla *Dispositivo → Configurar* (o `ZK_DEVICE_IP`).
5. Servir con Gunicorn/Waitress detrás de Nginx, y `npm run build` para el frontend estático.
6. El servidor debe estar en la **misma LAN** que el dispositivo (puerto 4370).

---

## Módulos

| Módulo | Contenido |
|---|---|
| **Dashboard** | Faltas y tardanzas del día, tendencia semanal/mensual, ranking de empleados, comparativo por departamento, estado del equipo |
| **Empleados** | Maestro con datos personales, laborales y biométricos; ficha con historial de asistencia; sincronización individual con el equipo |
| **Asistencia** | Registros diarios procesados, marcaciones crudas del equipo, marcación manual justificada, ajuste manual con sustento |
| **Horarios y Turnos** | Horarios con tolerancias y refrigerio, turnos con patrón semanal, asignación masiva, feriados, permisos con aprobación |
| **Reportes** | Tardanzas, faltas, **descuentos para planilla**, horas trabajadas, asistencia general y marcaciones detalladas — en Excel y PDF |
| **Dispositivo** | Prueba de conexión, subida de empleados, respaldo de huellas, descarga de marcaciones, sincronización de hora, historial de operaciones |
| **Configuración** | Usuarios y roles, sedes/departamentos/áreas/cargos, parámetros del motor de asistencia |
| **Auditoría** | Bitácora de quién hizo qué y cuándo, con el detalle de los cambios |

### Roles

- **Administrador** — acceso total, incluida la configuración del dispositivo y la auditoría.
- **RRHH** — gestiona empleados, horarios, asistencia y reportes; no toca la configuración.
- **Supervisor** — solo consulta, y **únicamente de su sede** (se le exige una sede asignada).

---

## Cómo se calcula la asistencia

El motor (`backend/apps/attendance/services/processor.py`) evalúa cada empleado y día:

1. Fuera del periodo laboral (antes del ingreso o después del cese) → no se evalúa.
2. Sin turno vigente en esa fecha → `sin_turno`, no genera falta.
3. Feriado o día de descanso del turno → no genera falta ni tardanza.
4. Permiso **aprobado** → vacaciones / falta justificada / permiso. Solo descuenta si es sin goce.
5. Sin marcaciones en día laborable → **falta**.
6. Una sola marcación → asistencia incompleta (o falta, según configuración).
7. Con entrada y salida → calcula tardanza, salida anticipada y horas trabajadas.

Detalles que afectan directamente el dinero de una persona:

- La **tolerancia decide si hay tardanza, no cuánto se descuenta**: superada la tolerancia se
  cuenta el retraso completo desde la hora programada.
- Una tardanza que supera el `minutos_falta` del horario se convierte en **falta**.
- Los turnos que **cruzan medianoche** toman su salida del día siguiente; la ventana de búsqueda
  se ancla al horario programado, no al día calendario.
- El procesamiento es **idempotente**: recalcular un periodo da siempre el mismo resultado.
- Los registros **ajustados manualmente** no se sobrescriben en el recálculo automático.
- Aprobar un permiso **recalcula automáticamente** los días que abarca.

---

## Pruebas

```bash
cd backend && ..\venv\Scripts\python -m pytest
```

75 pruebas cubren el motor de asistencia (tolerancias, turnos nocturnos, permisos, feriados,
idempotencia), el servicio del dispositivo con `pyzk` simulado (sin necesidad del equipo), los
endpoints del dashboard y el control de acceso por rol.

---

## Notas sobre la integración con el dispositivo

Dos particularidades del protocolo ZKTeco que el código maneja explícitamente:

- **El `uid` es un entero de 16 bits** (máximo 65535) y es distinto del código de empleado. Un
  código como `6999383` desbordaría si se usara como `uid`, por eso el sistema reutiliza el índice
  que el equipo ya asignó (guardado en `uid_dispositivo`) y solo asigna uno nuevo cuando el
  usuario no existe en el equipo. Sin esto, cada sincronización duplicaría empleados.
- **El firmware solo acepta privilegio 0 (usuario) o 14 (administrador)**; cualquier otro valor lo
  degrada silenciosamente a usuario, así que la interfaz ofrece solo esos dos.

Otras protecciones:

- El usuario administrador del equipo (`6999383`) **nunca se elimina** en una sincronización.
- La descarga de marcaciones es **idempotente**: repetir un rango no genera duplicados.
- `Limpiar marcaciones del equipo` es irreversible y exige confirmación explícita.
- Los empleados **no se borran**, se marcan como cesados: sus marcaciones son el respaldo de los
  descuentos ya aplicados en planilla.

Si el equipo no responde, verifique la conectividad (`ping 192.168.18.202`), que el puerto 4370
esté accesible, y que la clave de comunicación configurada en el equipo coincida con la del
sistema. Como último recurso, active *Forzar UDP* en la configuración del dispositivo.
