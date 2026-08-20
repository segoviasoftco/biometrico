// Funciones de acceso a la API, agrupadas por modulo.

import { api } from './client';
import type {
  Area,
  AsignacionTurno,
  Cargo,
  ComandoDispositivo,
  ComparativoDepartamento,
  Departamento,
  Dispositivo,
  Empleado,
  EmpleadoLista,
  EstadoSistema,
  Feriado,
  FilaRanking,
  Horario,
  Marcacion,
  Paginado,
  PeticionADMS,
  Permiso,
  PrevisualizacionReporte,
  PuntoTendencia,
  RegistroAsistencia,
  RegistroAuditoria,
  RegistroSincronizacion,
  RespuestaLogin,
  ResumenDia,
  Sede,
  Turno,
  Usuario,
} from '../types';

type Params = Record<string, unknown>;

export const authApi = {
  login: (email: string, password: string) =>
    api.post<RespuestaLogin>('/auth/login/', { email, password }).then((r) => r.data),
  perfil: () => api.get<Usuario>('/auth/perfil/').then((r) => r.data),
  cambiarPassword: (password_actual: string, password_nueva: string) =>
    api.post('/auth/perfil/cambiar-password/', { password_actual, password_nueva }),
};

export const usuariosApi = {
  listar: (params?: Params) =>
    api.get<Paginado<Usuario>>('/auth/usuarios/', { params }).then((r) => r.data),
  crear: (datos: Partial<Usuario> & { password?: string }) =>
    api.post<Usuario>('/auth/usuarios/', datos).then((r) => r.data),
  actualizar: (id: number, datos: Partial<Usuario> & { password?: string }) =>
    api.patch<Usuario>(`/auth/usuarios/${id}/`, datos).then((r) => r.data),
  desactivar: (id: number) => api.delete(`/auth/usuarios/${id}/`),
};

export const organizacionApi = {
  sedes: (params?: Params) =>
    api.get<Paginado<Sede>>('/organizacion/sedes/', { params }).then((r) => r.data),
  crearSede: (datos: Partial<Sede>) => api.post<Sede>('/organizacion/sedes/', datos),
  actualizarSede: (id: number, datos: Partial<Sede>) =>
    api.patch<Sede>(`/organizacion/sedes/${id}/`, datos),

  departamentos: (params?: Params) =>
    api.get<Paginado<Departamento>>('/organizacion/departamentos/', { params }).then((r) => r.data),
  crearDepartamento: (datos: Partial<Departamento>) =>
    api.post('/organizacion/departamentos/', datos),
  actualizarDepartamento: (id: number, datos: Partial<Departamento>) =>
    api.patch(`/organizacion/departamentos/${id}/`, datos),

  areas: (params?: Params) =>
    api.get<Paginado<Area>>('/organizacion/areas/', { params }).then((r) => r.data),
  crearArea: (datos: Partial<Area>) => api.post('/organizacion/areas/', datos),
  actualizarArea: (id: number, datos: Partial<Area>) =>
    api.patch(`/organizacion/areas/${id}/`, datos),

  cargos: (params?: Params) =>
    api.get<Paginado<Cargo>>('/organizacion/cargos/', { params }).then((r) => r.data),
  crearCargo: (datos: Partial<Cargo>) => api.post('/organizacion/cargos/', datos),
  actualizarCargo: (id: number, datos: Partial<Cargo>) =>
    api.patch(`/organizacion/cargos/${id}/`, datos),
};

export const empleadosApi = {
  listar: (params?: Params) =>
    api.get<Paginado<EmpleadoLista>>('/empleados/', { params }).then((r) => r.data),
  obtener: (id: number) => api.get<Empleado>(`/empleados/${id}/`).then((r) => r.data),
  // Los datos llegan del formulario con las fechas ya normalizadas a texto, por
  // lo que no encajan en `Partial<Empleado>` (que no admite nulos en fechas).
  crear: (datos: FormData | Params) => api.post<Empleado>('/empleados/', datos),
  actualizar: (id: number, datos: FormData | Params) =>
    api.patch<Empleado>(`/empleados/${id}/`, datos),
  cesar: (id: number) => api.delete(`/empleados/${id}/`),
  sincronizar: (id: number) => api.post(`/empleados/${id}/sincronizar/`).then((r) => r.data),
  restaurarHuellas: (id: number) =>
    api.post(`/empleados/${id}/restaurar-huellas/`).then((r) => r.data),
  sinBiometria: () => api.get<EmpleadoLista[]>('/empleados/sin-biometria/').then((r) => r.data),
  pendientesSincronizar: () =>
    api.get<EmpleadoLista[]>('/empleados/pendientes-sincronizar/').then((r) => r.data),
};

export const dispositivosApi = {
  listar: () => api.get<Paginado<Dispositivo>>('/dispositivos/').then((r) => r.data),
  obtener: (id: number) => api.get<Dispositivo>(`/dispositivos/${id}/`).then((r) => r.data),
  crear: (datos: Partial<Dispositivo>) => api.post('/dispositivos/', datos),
  actualizar: (id: number, datos: Partial<Dispositivo>) =>
    api.patch(`/dispositivos/${id}/`, datos),
  probarConexion: (id: number) =>
    api.post(`/dispositivos/${id}/probar-conexion/`).then((r) => r.data),
  sincronizarHora: (id: number) =>
    api.post(`/dispositivos/${id}/sincronizar-hora/`).then((r) => r.data),
  subirEmpleados: (id: number, solo_pendientes = true) =>
    api.post(`/dispositivos/${id}/subir-empleados/`, { solo_pendientes }).then((r) => r.data),
  empleadosEnEquipo: (id: number) =>
    api.get(`/dispositivos/${id}/empleados-en-equipo/`).then((r) => r.data),
  respaldarHuellas: (id: number) =>
    api.post(`/dispositivos/${id}/respaldar-huellas/`).then((r) => r.data),
  descargarMarcaciones: (id: number, datos: { desde?: string; procesar?: boolean }) =>
    api.post(`/dispositivos/${id}/descargar-marcaciones/`, datos).then((r) => r.data),
  limpiarMarcaciones: (id: number) =>
    api.post(`/dispositivos/${id}/limpiar-marcaciones/`, { confirmacion: 'CONFIRMO' }),
  sincronizaciones: (params?: Params) =>
    api
      .get<Paginado<RegistroSincronizacion>>('/dispositivos/sincronizaciones/', { params })
      .then((r) => r.data),

  comandos: (params?: Params) =>
    api
      .get<Paginado<ComandoDispositivo>>('/dispositivos/comandos/', { params })
      .then((r) => r.data),
  cancelarComando: (id: number) => api.post(`/dispositivos/comandos/${id}/cancelar/`),
  reintentarComandosFallidos: (dispositivoId?: number) =>
    api
      .post('/dispositivos/comandos/reintentar-fallidos/', { dispositivo: dispositivoId })
      .then((r) => r.data),

  peticionesADMS: (params?: Params) =>
    api
      .get<Paginado<PeticionADMS>>('/dispositivos/peticiones-adms/', { params })
      .then((r) => r.data),
};

export const horariosApi = {
  horarios: (params?: Params) =>
    api.get<Paginado<Horario>>('/horarios/horarios/', { params }).then((r) => r.data),
  crearHorario: (datos: Partial<Horario>) => api.post('/horarios/horarios/', datos),
  actualizarHorario: (id: number, datos: Partial<Horario>) =>
    api.patch(`/horarios/horarios/${id}/`, datos),
  eliminarHorario: (id: number) => api.delete(`/horarios/horarios/${id}/`),

  turnos: (params?: Params) =>
    api.get<Paginado<Turno>>('/horarios/turnos/', { params }).then((r) => r.data),
  crearTurno: (datos: Partial<Turno>) => api.post('/horarios/turnos/', datos),
  actualizarTurno: (id: number, datos: Partial<Turno>) =>
    api.patch(`/horarios/turnos/${id}/`, datos),
  eliminarTurno: (id: number) => api.delete(`/horarios/turnos/${id}/`),
  asignarMasivo: (datos: {
    empleados: number[];
    turno: number;
    fecha_inicio: string;
    fecha_fin?: string | null;
    cerrar_asignacion_anterior?: boolean;
  }) => api.post('/horarios/turnos/asignar-masivo/', datos).then((r) => r.data),

  asignaciones: (params?: Params) =>
    api.get<Paginado<AsignacionTurno>>('/horarios/asignaciones/', { params }).then((r) => r.data),
  crearAsignacion: (datos: Partial<AsignacionTurno>) => api.post('/horarios/asignaciones/', datos),
  actualizarAsignacion: (id: number, datos: Partial<AsignacionTurno>) =>
    api.patch(`/horarios/asignaciones/${id}/`, datos),

  feriados: (params?: Params) =>
    api.get<Paginado<Feriado>>('/horarios/feriados/', { params }).then((r) => r.data),
  crearFeriado: (datos: Partial<Feriado>) => api.post('/horarios/feriados/', datos),
  eliminarFeriado: (id: number) => api.delete(`/horarios/feriados/${id}/`),

  permisos: (params?: Params) =>
    api.get<Paginado<Permiso>>('/horarios/permisos/', { params }).then((r) => r.data),
  crearPermiso: (datos: FormData | Partial<Permiso>) => api.post('/horarios/permisos/', datos),
  aprobarPermiso: (id: number, aprobar: boolean, observacion = '') =>
    api.post(`/horarios/permisos/${id}/aprobar/`, { aprobar, observacion }).then((r) => r.data),

  configuracion: () => api.get('/horarios/configuracion/').then((r) => r.data),
  guardarConfiguracion: (datos: Params) =>
    api.post('/horarios/configuracion/', datos).then((r) => r.data),
};

export const asistenciaApi = {
  marcaciones: (params?: Params) =>
    api.get<Paginado<Marcacion>>('/asistencia/marcaciones/', { params }).then((r) => r.data),
  crearMarcacionManual: (datos: {
    empleado: number;
    fecha_hora: string;
    tipo_marcacion: number;
    observacion: string;
  }) => api.post('/asistencia/marcaciones/', datos),
  eliminarMarcacion: (id: number) => api.delete(`/asistencia/marcaciones/${id}/`),

  registros: (params?: Params) =>
    api.get<Paginado<RegistroAsistencia>>('/asistencia/registros/', { params }).then((r) => r.data),
  procesar: (datos: {
    fecha_inicio: string;
    fecha_fin: string;
    empleados?: number[];
    forzar?: boolean;
  }) => api.post('/asistencia/registros/procesar/', datos).then((r) => r.data),
  ajustar: (
    id: number,
    datos: {
      estado: string;
      minutos_tardanza?: number;
      es_descontable?: boolean;
      observacion: string;
    },
  ) => api.post(`/asistencia/registros/${id}/ajustar/`, datos).then((r) => r.data),
  resumenEmpleado: (empleadoId: number, params?: Params) =>
    api
      .get(`/asistencia/registros/resumen-empleado/${empleadoId}/`, { params })
      .then((r) => r.data),
};

export const dashboardApi = {
  resumenDia: (params?: Params) =>
    api.get<ResumenDia>('/dashboard/resumen-dia/', { params }).then((r) => r.data),
  tendenciaSemanal: (params?: Params) =>
    api.get<PuntoTendencia[]>('/dashboard/tendencia-semanal/', { params }).then((r) => r.data),
  tendenciaMensual: (params?: Params) =>
    api.get<PuntoTendencia[]>('/dashboard/tendencia-mensual/', { params }).then((r) => r.data),
  ranking: (params?: Params) =>
    api
      .get<{ tardanzas: FilaRanking[]; faltas: FilaRanking[] }>('/dashboard/ranking/', { params })
      .then((r) => r.data),
  comparativoDepartamento: (params?: Params) =>
    api
      .get<ComparativoDepartamento[]>('/dashboard/comparativo-departamento/', { params })
      .then((r) => r.data),
  estadoSistema: () => api.get<EstadoSistema>('/dashboard/estado-sistema/').then((r) => r.data),
};

export interface SolicitudReporte {
  tipo: string;
  formato?: 'excel' | 'pdf';
  fecha_inicio: string;
  fecha_fin: string;
  sede?: number | null;
  departamento?: number | null;
  area?: number | null;
  empleados?: number[];
  guardar?: boolean;
}

export const reportesApi = {
  tipos: () =>
    api.get<{ valor: string; etiqueta: string }[]>('/reportes/tipos/').then((r) => r.data),
  previsualizar: (datos: SolicitudReporte) =>
    api.post<PrevisualizacionReporte>('/reportes/previsualizar/', datos).then((r) => r.data),
  /** Descarga el archivo del reporte como blob. */
  generar: (datos: SolicitudReporte) =>
    api.post('/reportes/generar/', datos, { responseType: 'blob' }),
  historial: (params?: Params) => api.get('/reportes/', { params }).then((r) => r.data),
};

export const auditoriaApi = {
  listar: (params?: Params) =>
    api.get<Paginado<RegistroAuditoria>>('/auditoria/', { params }).then((r) => r.data),
};
