import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

const CLAVE_ACCESO = 'biometrico_access';
const CLAVE_REFRESH = 'biometrico_refresh';

export const tokens = {
  acceso: () => localStorage.getItem(CLAVE_ACCESO),
  refresh: () => localStorage.getItem(CLAVE_REFRESH),
  guardar(acceso: string, refresh: string) {
    localStorage.setItem(CLAVE_ACCESO, acceso);
    localStorage.setItem(CLAVE_REFRESH, refresh);
  },
  limpiar() {
    localStorage.removeItem(CLAVE_ACCESO);
    localStorage.removeItem(CLAVE_REFRESH);
  },
};

api.interceptors.request.use((config) => {
  const token = tokens.acceso();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Una sola renovacion a la vez: si varias peticiones caducan juntas, todas
// esperan el mismo refresh en lugar de dispararlo en paralelo.
let renovacionEnCurso: Promise<string> | null = null;

async function renovarToken(): Promise<string> {
  const refresh = tokens.refresh();
  if (!refresh) throw new Error('No hay token de refresco');

  const { data } = await axios.post(`${BASE_URL}/auth/refresh/`, { refresh });
  tokens.guardar(data.access, data.refresh ?? refresh);
  return data.access;
}

api.interceptors.response.use(
  (respuesta) => respuesta,
  async (error: AxiosError) => {
    const peticion = error.config as InternalAxiosRequestConfig & { _reintentada?: boolean };

    if (error.response?.status === 401 && peticion && !peticion._reintentada) {
      peticion._reintentada = true;
      try {
        renovacionEnCurso = renovacionEnCurso ?? renovarToken();
        const nuevoToken = await renovacionEnCurso;
        renovacionEnCurso = null;
        peticion.headers.Authorization = `Bearer ${nuevoToken}`;
        return api(peticion);
      } catch {
        renovacionEnCurso = null;
        tokens.limpiar();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

/** Extrae un mensaje legible del error que devuelve la API. */
export function mensajeError(error: unknown, porDefecto = 'Ocurrio un error inesperado.'): string {
  if (axios.isAxiosError(error)) {
    const datos = error.response?.data as Record<string, unknown> | undefined;
    if (typeof datos?.detalle === 'string') return datos.detalle;
    if (typeof datos?.detail === 'string') return datos.detail;

    if (datos && typeof datos === 'object') {
      // Errores de validacion por campo: se muestran como "campo: mensaje".
      const partes = Object.entries(datos).map(([campo, valor]) => {
        const texto = Array.isArray(valor) ? valor.join(' ') : String(valor);
        return campo === 'non_field_errors' ? texto : `${campo}: ${texto}`;
      });
      if (partes.length) return partes.join(' | ');
    }
    if (!error.response) {
      return 'No se pudo contactar al servidor. Verifique que el backend este en ejecucion.';
    }
  }
  return porDefecto;
}
