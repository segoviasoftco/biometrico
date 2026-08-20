// Tipos que reflejan los serializers del backend.

export type Rol = 'administrador' | 'rrhh' | 'supervisor';

export interface Usuario {
  id: number;
  email: string;
  nombres: string;
  apellidos: string;
  nombre_completo: string;
  rol: Rol;
  rol_display: string;
  telefono: string;
  sede: number | null;
  sede_nombre: string | null;
  is_active: boolean;
  last_login: string | null;
  creado_en: string;
}

export interface RespuestaLogin {
  access: string;
  refresh: string;
  usuario: Usuario;
}

/** Respuesta paginada estandar de Django REST Framework. */
export interface Paginado<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Sede {
  id: number;
  nombre: string;
  codigo: string;
  direccion: string;
  telefono: string;
  activo: boolean;
  total_empleados: number;
}

export interface Departamento {
  id: number;
  nombre: string;
  codigo: string;
  sede: number;
  sede_nombre: string;
  descripcion: string;
  activo: boolean;
  total_empleados: number;
}

export interface Area {
  id: number;
  nombre: string;
  codigo: string;
  departamento: number;
  departamento_nombre: string;
  sede_nombre: string;
  activo: boolean;
}

export interface Cargo {
  id: number;
  nombre: string;
  descripcion: string;
  activo: boolean;
}

export type EstadoEmpleado = 'activo' | 'inactivo' | 'cesado' | 'vacaciones';

export interface EmpleadoLista {
  id: number;
  codigo_empleado: string;
  dni: string;
  nombre_completo: string;
  foto: string | null;
  sede: number;
  sede_nombre: string;
  departamento: number;
  departamento_nombre: string;
  cargo: number;
  cargo_nombre: string;
  estado: EstadoEmpleado;
  estado_display: string;
  tiene_huella: boolean;
  tiene_rostro: boolean;
  cantidad_huellas: number;
  sincronizado_dispositivo: boolean;
}

export interface HuellaEmpleado {
  id: number;
  finger_id: number;
  size: number;
  valid: number;
  capturado_en: string;
}

export interface Empleado extends EmpleadoLista {
  nombres: string;
  apellido_paterno: string;
  apellido_materno: string;
  fecha_nacimiento: string | null;
  sexo: string;
  email: string;
  telefono: string;
  direccion: string;
  area: number | null;
  area_nombre: string | null;
  fecha_ingreso: string;
  fecha_cese: string | null;
  tipo_contrato: string;
  tipo_contrato_display: string;
  sueldo_basico: string | null;
  tiene_tarjeta: boolean;
  numero_tarjeta: string;
  privilegio_dispositivo: number;
  uid_dispositivo: number | null;
  fecha_ultima_sincronizacion: string | null;
  huellas: HuellaEmpleado[];
  turno_actual: { id: number; nombre: string } | null;
}

export interface Dispositivo {
  id: number;
  nombre: string;
  ip: string;
  puerto: number;
  timeout: number;
  force_udp: boolean;
  sede: number | null;
  sede_nombre: string | null;
  ubicacion: string;
  modelo: string;
  numero_serie: string;
  version_firmware: string;
  version_plataforma: string;
  version_rostro: string;
  version_huella: string;
  mac: string;
  admin_user_id: string;
  estado: 'conectado' | 'desconectado' | 'error' | 'desconocido';
  estado_display: string;
  ultima_conexion: string | null;
  ultima_sincronizacion_marcaciones: string | null;
  activo: boolean;
}

export interface RegistroSincronizacion {
  id: number;
  dispositivo: number;
  dispositivo_nombre: string;
  operacion: string;
  operacion_display: string;
  estado: 'en_proceso' | 'exitoso' | 'fallido' | 'parcial';
  estado_display: string;
  registros_procesados: number;
  registros_nuevos: number;
  registros_fallidos: number;
  mensaje: string;
  detalle: unknown;
  ejecutado_por_nombre: string;
  inicio: string;
  fin: string | null;
  duracion_segundos: number | null;
}

export interface Horario {
  id: number;
  nombre: string;
  hora_entrada: string;
  hora_salida: string;
  tolerancia_entrada: number;
  tolerancia_salida: number;
  tiene_refrigerio: boolean;
  hora_inicio_refrigerio: string | null;
  hora_fin_refrigerio: string | null;
  minutos_falta: number;
  horas_jornada: number;
  cruza_medianoche: boolean;
  activo: boolean;
}

export interface TurnoDetalle {
  id?: number;
  dia_semana: number;
  dia_display?: string;
  horario: number | null;
  horario_nombre?: string | null;
  es_descanso?: boolean;
}

export interface Turno {
  id: number;
  nombre: string;
  tipo: 'fijo' | 'rotativo' | 'flexible';
  tipo_display: string;
  descripcion: string;
  detalles: TurnoDetalle[];
  total_empleados: number;
  activo: boolean;
}

export interface AsignacionTurno {
  id: number;
  empleado: number;
  empleado_nombre: string;
  empleado_codigo: string;
  turno: number;
  turno_nombre: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  vigente: boolean;
  observacion: string;
}

export interface Feriado {
  id: number;
  fecha: string;
  descripcion: string;
  es_recurrente: boolean;
  sede: number | null;
  sede_nombre: string;
}

export interface Permiso {
  id: number;
  empleado: number;
  empleado_nombre: string;
  empleado_codigo: string;
  tipo: string;
  tipo_display: string;
  fecha_inicio: string;
  fecha_fin: string;
  dias_totales: number;
  con_goce: boolean;
  motivo: string;
  documento: string | null;
  estado: 'pendiente' | 'aprobado' | 'rechazado';
  estado_display: string;
  aprobado_por_nombre: string | null;
  fecha_aprobacion: string | null;
  observacion_aprobacion: string;
}

export interface Marcacion {
  id: number;
  empleado: number;
  empleado_nombre: string;
  empleado_codigo: string;
  dispositivo_nombre: string | null;
  fecha_hora: string;
  tipo_verificacion: number;
  tipo_verificacion_display: string;
  tipo_marcacion: number;
  tipo_marcacion_display: string;
  origen: 'dispositivo' | 'manual';
  observacion: string;
}

export type EstadoAsistencia =
  | 'puntual'
  | 'tardanza'
  | 'falta'
  | 'falta_justificada'
  | 'permiso'
  | 'vacaciones'
  | 'descanso'
  | 'feriado'
  | 'incompleto'
  | 'sin_turno';

export interface RegistroAsistencia {
  id: number;
  empleado: number;
  empleado_nombre: string;
  empleado_codigo: string;
  sede_nombre: string;
  departamento_nombre: string;
  fecha: string;
  turno_nombre: string | null;
  horario_nombre: string | null;
  hora_entrada_programada: string | null;
  hora_salida_programada: string | null;
  marcacion_entrada: string | null;
  marcacion_salida: string | null;
  total_marcaciones: number;
  minutos_tardanza: number;
  minutos_salida_anticipada: number;
  minutos_trabajados: number;
  horas_trabajadas: number;
  estado: EstadoAsistencia;
  estado_display: string;
  es_descontable: boolean;
  observacion: string;
  ajustado_manualmente: boolean;
}

export interface ResumenDia {
  fecha: string;
  puntuales: number;
  tardanzas: number;
  faltas: number;
  incompletos: number;
  permisos: number;
  justificadas: number;
  descansos: number;
  minutos_tardanza: number;
  esperados: number;
  asistieron: number;
  porcentaje_asistencia: number;
  total_empleados_activos: number;
}

export interface PuntoTendencia {
  periodo: string;
  faltas: number;
  tardanzas: number;
  minutos_tardanza: number;
  puntuales: number;
}

export interface FilaRanking {
  empleado_id: number;
  codigo: string;
  nombre: string;
  departamento: string;
  dias: number;
  minutos?: number;
}

export interface ComparativoDepartamento {
  departamento_id: number;
  departamento: string;
  sede: string;
  puntuales: number;
  tardanzas: number;
  faltas: number;
  minutos_tardanza: number;
  promedio_minutos_tardanza: number;
  porcentaje_asistencia: number;
}

export interface EstadoSistema {
  dispositivos: Array<{
    id: number;
    nombre: string;
    ip: string;
    estado: string;
    estado_display: string;
    ultima_conexion: string | null;
    ultima_sincronizacion_marcaciones: string | null;
  }>;
  empleados_activos: number;
  sin_biometria: number;
  pendientes_sincronizar: number;
  sin_turno: number;
}

export interface ColumnaReporte {
  clave: string;
  etiqueta: string;
}

export interface PrevisualizacionReporte {
  titulo: string;
  columnas: ColumnaReporte[];
  filas: Record<string, unknown>[];
  totales: Record<string, number>;
  nota: string;
  total_registros: number;
}

export interface RegistroAuditoria {
  id: number;
  usuario_nombre: string;
  usuario_email: string;
  accion: string;
  accion_display: string;
  modelo: string;
  objeto_id: string;
  descripcion: string;
  cambios: unknown;
  ip: string | null;
  ruta: string;
  metodo: string;
  fecha_hora: string;
}
