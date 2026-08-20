import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { tokens } from '../api/client';
import { authApi } from '../api/endpoints';
import type { Usuario } from '../types';

interface EstadoAuth {
  usuario: Usuario | null;
  autenticado: boolean;
  cargando: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refrescarPerfil: () => Promise<void>;
}

export const useAuth = create<EstadoAuth>()(
  persist(
    (set) => ({
      usuario: null,
      autenticado: false,
      cargando: false,

      login: async (email, password) => {
        set({ cargando: true });
        try {
          const datos = await authApi.login(email, password);
          tokens.guardar(datos.access, datos.refresh);
          set({ usuario: datos.usuario, autenticado: true, cargando: false });
        } catch (error) {
          set({ cargando: false });
          throw error;
        }
      },

      logout: () => {
        tokens.limpiar();
        set({ usuario: null, autenticado: false });
      },

      refrescarPerfil: async () => {
        // El rol pudo cambiar desde otra sesion; conviene releerlo al arrancar.
        const usuario = await authApi.perfil();
        set({ usuario, autenticado: true });
      },
    }),
    {
      name: 'biometrico_auth',
      // Los tokens viven en su propio almacenamiento, gestionado por el cliente
      // HTTP; aqui solo se persiste la identidad para pintar el menu al recargar.
      partialize: (estado) => ({ usuario: estado.usuario, autenticado: estado.autenticado }),
    },
  ),
);

/** Indica si el usuario actual puede modificar datos operativos. */
export function puedeEditar(usuario: Usuario | null): boolean {
  return usuario?.rol === 'administrador' || usuario?.rol === 'rrhh';
}

/** Indica si el usuario actual tiene acceso a la configuracion del sistema. */
export function esAdministrador(usuario: Usuario | null): boolean {
  return usuario?.rol === 'administrador';
}
