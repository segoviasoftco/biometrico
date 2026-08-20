# Registro de desarrollo

Bitácora técnica del Sistema de Control de Asistencia Biométrico. Documenta qué
se construyó, qué decisiones se tomaron y por qué, y qué problemas reales
aparecieron y cómo se resolvieron. El README explica cómo instalar y operar el
sistema; este archivo explica cómo llegó a ser lo que es.

---

## 2026-08-19 — Arquitectura y decisión de stack

**Contexto.** Se pidió diseñar un sistema de control de asistencia integrado
con un dispositivo biométrico ZKTeco MB560-VL (IP `192.168.18.202`), inspirado
en BioTime Pro, con gestión de empleados (incluyendo datos de rostro y huella),
horarios y turnos, dashboard, y reportes de tardanzas/faltas para descuentos de
planilla.

**Decisión de stack.** Backend Django 5.1 + Django REST Framework, base de
datos PostgreSQL en producción (SQLite en desarrollo), Celery + Redis para
tareas programadas, `pyzk` para hablar el protocolo nativo del dispositivo.
Frontend React 19 + TypeScript + Vite, Ant Design 6, React Query, Zustand,
Recharts.

**Aclaración de alcance decidida con el usuario antes de programar:** el
enrolamiento de rostro y huella se hace en el equipo físico, no desde la web.
No es una limitación de diseño sino del protocolo: el algoritmo facial de
ZKTeco es propietario y no expone sus plantillas. El sistema sube los datos
maestros del empleado al equipo y respalda las huellas (sí accesibles) para
poder restaurarlas si el equipo se resetea.

## 2026-08-19/20 — Backend: modelos, motor de asistencia y API

Se crearon 9 apps Django: `accounts`, `organization`, `employees`, `devices`,
`schedules`, `attendance`, `reports`, `dashboard`, `audit`.

**Motor de asistencia** (`attendance/services/processor.py`): evalúa cada
empleado y cada día contra su turno vigente en esa fecha (no el turno actual),
aplicando tolerancias, refrigerio, feriados, permisos aprobados y turnos que
cruzan medianoche. Es idempotente: recalcular un periodo produce siempre el
mismo resultado, salvo en los registros ajustados manualmente.

**Bug real encontrado durante las pruebas:** la ventana de búsqueda de
marcaciones estaba anclada al día calendario con un margen fijo. Eso hacía que
un turno nocturno perdiera su marcación de salida (ocurre al día siguiente) y
que un turno diurno arrastrara marcaciones de la noche anterior. Se corrigió
anclando la ventana al horario programado del turno, no al día calendario.

**API REST completa**: autenticación JWT con renovación automática, permisos
por rol (administrador / RRHH / supervisor con alcance por sede), CRUD de
empleados con sincronización al dispositivo, horarios/turnos/feriados/permisos
con aprobación, marcaciones manuales justificadas, ajustes manuales auditados,
generación de reportes en Excel y PDF.

## 2026-08-19/20 — Integración con el dispositivo (SDK)

Se construyó `devices/services/zk_service.py` sobre `pyzk`. Al leer el código
fuente de la librería (no solo su documentación) aparecieron dos bugs que
habrían sido invisibles hasta producción:

1. **Desbordamiento del `uid`.** El protocolo ZKTeco empaqueta el `uid` del
   usuario en un entero de 16 bits (máx. 65535) y es distinto del código de
   empleado. Usar el código de empleado como `uid` directamente habría
   desbordado con códigos como `6999383`, y probablemente habría duplicado
   usuarios en cada sincronización. Se corrigió reutilizando el `uid` que el
   equipo ya asignó (guardado en `Empleado.uid_dispositivo`) y asignando uno
   nuevo solo para usuarios sin `uid` previo.
2. **Privilegio degradado en silencio.** El firmware solo admite privilegio 0
   (usuario) o 14 (administrador); cualquier otro valor lo convierte en 0 sin
   avisar. Se retiró la opción "Registrador" que se había contemplado
   inicialmente, para no dar una falsa sensación de control.

Se protegió explícitamente al usuario administrador del equipo (`6999383`)
contra borrado en cualquier sincronización.

## 2026-08-20 — Diagnóstico de red y decisión de pivotar a ADMS

Al intentar la primera conexión real contra `192.168.18.202` desde la LAN:

| Prueba | Resultado |
|---|---|
| Ping | Responde (2–5 ms) |
| MAC (`00:17:61:11:1f:77`) | OUI confirmado de ZKTeco — es el equipo correcto |
| TCP 4370 (protocolo SDK) | Cerrado |
| UDP 4370 | Sin respuesta (paquete crudo, 10 s de espera) |
| Puerto 80 | Acepta la conexión y la corta de inmediato |
| Barrido de toda la subred `192.168.18.0/24` | Solo hay un equipo ZKTeco; ningún dispositivo de la red tiene el 4370 abierto |

Conclusión: el equipo está en línea pero su servicio de comunicación SDK no
está escuchando (probablemente el modo "servidor en la nube / ADMS" está
activo en el equipo, lo que lo pone en modo *push* y le hace dejar de
escuchar conexiones entrantes). Se decidió implementar la vía **ADMS** como
alternativa, sin descartar el código SDK: ambos modos conviven y el sistema
elige el camino según la configuración de cada dispositivo.

## 2026-08-20 — Implementación de ADMS (protocolo push)

Diferencia de fondo con el modo SDK: en SDK el servidor llama al equipo; en
ADMS el equipo llama al servidor. El servidor no puede iniciar la
comunicación, así que las órdenes hacia el equipo (alta de empleados, pedir
reenvío de datos) se dejan en una cola que el equipo consulta periódicamente.

**Componentes construidos** (`devices/adms/`):

- `parsers.py` — interpreta el texto plano tabulado que envía el equipo
  (`ATTLOG` para marcaciones, `OPERLOG` para altas de usuario, huellas y
  rostro), tolerante a líneas corruptas: una línea ilegible no aborta el lote.
- `commands.py` — construye y encola los comandos hacia el equipo
  (`DATA UPDATE USERINFO`, `DATA UPDATE FINGERTMP`, etc.).
- `services.py` — reutiliza el mismo motor de asistencia que la vía SDK: el
  origen de los datos cambia, las reglas de negocio no.
- `views.py` — endpoints `/iclock/cdata`, `/iclock/getrequest`,
  `/iclock/devicecmd`, `/iclock/fdata`, `/iclock/ping`, según el protocolo
  que impone el firmware (fuera de `/api/`, sin autenticación JWT porque el
  equipo no puede presentarla).

**Modelos nuevos**: `ComandoDispositivo` (cola de comandos con estado
pendiente/enviado/confirmado/fallido) y `PeticionADMS` (bitácora cruda de
cada petición del equipo, aceptada o rechazada, para poder diagnosticar el
protocolo de un firmware concreto sin adivinar).

**Seguridad.** El equipo no puede autenticarse con credenciales; su única
identificación es el número de serie en la URL, que viaja en claro. Se
aplicaron tres controles: (1) solo se aceptan números de serie de equipos
registrados con ADMS habilitado explícitamente, (2) IP de origen opcional en
lista blanca, (3) toda petición queda registrada, aceptada o no, con motivo
de rechazo.

**Bug real encontrado en pruebas:** el límite por defecto de Django
(`DATA_UPLOAD_MAX_MEMORY_SIZE` = 2.5 MB) es menor que un volcado completo de
plantillas de huella en base64 para una plantilla de cientos de empleados.
Sin corregirlo, una sincronización masiva de huellas habría fallado con un
400 genérico sin explicación. Se subió el límite de Django a 12 MB y se
añadió un límite propio de 10 MB en la vista, para que sea esta la que
rechace con un mensaje claro y quede registrado, en vez de un error opaco de
Django.

## 2026-08-20 — Pruebas automatizadas

106 pruebas en verde (`pytest`), sin depender del equipo físico:

- **Motor de asistencia** (23): tolerancias, tardanza que se convierte en
  falta, turnos nocturnos, feriados (fijos y recurrentes), permisos
  aprobados/pendientes/sin goce, marcación única, idempotencia, respeto y
  sobrescritura de ajustes manuales, turno vigente por fecha.
- **Servicio SDK** (21): con `pyzk` sustituido por un doble de prueba —
  asignación de `uid`, reutilización de `uid` en re-sincronización, protección
  del administrador del equipo, respaldo/restauración de huellas, descarga
  idempotente de marcaciones, zona horaria.
- **Protocolo ADMS** (31): rechazo sin número de serie / con serie
  desconocida / con equipo deshabilitado / con IP no autorizada, handshake,
  recepción y no-duplicación de marcaciones, líneas corruptas toleradas,
  disparo automático del recálculo de asistencia, respaldo de huellas con
  validación de base64, cola de comandos (entrega, confirmación, aislamiento
  entre equipos), límite de tamaño de peticiones.
- **Dashboard** (17): las seis vistas de agregación responden con y sin
  datos; cubre el bug real descrito abajo.
- **Permisos por rol** (14): alcance por sede del supervisor, restricciones de
  escritura, validaciones de negocio (supervisor requiere sede, empleado se
  cesa en vez de borrarse).

**Bug real encontrado por estas pruebas, no por inspección manual:** el
endpoint de comparativo por departamento devolvía error 500. La causa era que
el alias de un `Sum` se llamaba igual que el campo (`minutos_tardanza`), y
Django resolvía el `Avg` posterior contra el propio agregado en lugar del
campo original. Se corrigió renombrando el alias y calculando el promedio en
Python sobre los días que realmente tuvieron tardanza.

**Otro hallazgo de las pruebas de permisos:** los endpoints de reportes usan
POST porque los filtros viajan en el cuerpo, pero son operaciones de lectura.
El permiso genérico los bloqueaba para el supervisor, que sí debe poder
consultar los reportes de su propia sede.

## 2026-08-20 — Frontend

Ocho módulos (Dashboard, Empleados con ficha completa, Asistencia, Horarios y
Turnos, Reportes, Dispositivo, Configuración, Auditoría) más Login y Perfil,
con el menú lateral ajustado al rol de la sesión. Cliente HTTP con renovación
automática de token JWT.

Al migrar a Ant Design 6 aparecieron warnings de APIs obsoletas
(`Space.direction`, `Statistic.valueStyle`, `Alert.message`,
`Drawer.width`); se migraron todas a su reemplazo (`orientation`,
`styles.content`, `title`, `size`) hasta dejar la consola sin advertencias.

## 2026-08-20 — UI de ADMS y validación en vivo

Se extendió el frontend para exponer lo que el backend de ADMS ya soportaba:
selector de modo de comunicación (SDK/ADMS) en la configuración del
dispositivo, campo de número de serie, IP autorizada, y dos pestañas nuevas
en la pantalla Dispositivo — **Cola de comandos** y **Peticiones ADMS** (esta
última, herramienta de diagnóstico del protocolo).

**Validación end-to-end realizada desde la propia aplicación:**

1. Se configuró el dispositivo real (`ZKTeco MB560-VL`, número de serie
   `COVG215160131`, provisto por el usuario) en modo ADMS desde la interfaz.
2. Se simuló el handshake y el envío de marcaciones que haría el equipo real,
   sin tocar hardware. Una petición sin la IP autorizada fue rechazada con
   403 y quedó registrada — confirma que el control de seguridad funciona.
   Una petición desde la IP autorizada fue aceptada: handshake 200, dos
   marcaciones nuevas guardadas (`OK: 2`).
3. El motor de asistencia recalculó el día automáticamente, sin intervención
   manual, y el Dashboard reflejó el cambio al recargar. El estado del
   dispositivo pasó a "Conectado" en la interfaz en tiempo real.

Con esto, todo el circuito servidor queda probado de punta a punta. Lo único
pendiente es un paso físico fuera del alcance del código: configurar en el
menú del equipo (**Comunicación → Servidor en la nube**) la IP de este
servidor y el puerto 8000, y habilitar ADMS.

---

## Estado actual

- **106 pruebas automatizadas en verde.**
- Backend y frontend verificados end-to-end en el navegador, incluida la
  generación real de reportes Excel/PDF.
- Repositorio Git inicializado, con `.gitignore`/`.gitattributes` que
  excluyen secretos (`.env`, base de datos, `media/`, `logs/`).
- Endurecimiento de producción (`SECURE_*`, HSTS, cookies seguras) preparado
  en `settings.py`, activo solo cuando `DEBUG=False`.

## Pendiente

- **Configurar el menú del equipo físico** para completar la conexión ADMS
  real (paso manual, no de código).
- Decidir qué hacer con las marcaciones de prueba generadas durante la
  simulación (empleado de prueba `5001`): conservarlas como evidencia o
  limpiarlas antes de operar con datos reales.
- Instalar PostgreSQL y Redis para el paso a producción (hoy corre en SQLite
  con Celery en modo inmediato).
- Definir dónde alojar el repositorio remoto (debe ser privado: contiene la
  lógica de cálculo de descuentos de planilla).
