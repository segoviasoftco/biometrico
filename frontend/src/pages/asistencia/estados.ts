import type { EstadoAsistencia } from '../../types';

/** Color con el que se muestra cada estado de asistencia en toda la aplicacion. */
export const COLOR_ESTADO: Record<EstadoAsistencia, string> = {
  puntual: 'green',
  tardanza: 'orange',
  falta: 'red',
  falta_justificada: 'blue',
  permiso: 'cyan',
  vacaciones: 'geekblue',
  descanso: 'default',
  feriado: 'purple',
  incompleto: 'gold',
  sin_turno: 'default',
};

export const ETIQUETAS_ESTADO: { value: EstadoAsistencia; label: string }[] = [
  { value: 'puntual', label: 'Puntual' },
  { value: 'tardanza', label: 'Tardanza' },
  { value: 'falta', label: 'Falta injustificada' },
  { value: 'falta_justificada', label: 'Falta justificada' },
  { value: 'permiso', label: 'Permiso' },
  { value: 'vacaciones', label: 'Vacaciones' },
  { value: 'descanso', label: 'Descanso' },
  { value: 'feriado', label: 'Feriado' },
  { value: 'incompleto', label: 'Asistencia incompleta' },
  { value: 'sin_turno', label: 'Sin turno asignado' },
];
