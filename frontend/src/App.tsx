import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import esES from 'antd/locale/es_ES';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';

import Layout from './components/Layout';
import Asistencia from './pages/Asistencia';
import Auditoria from './pages/Auditoria';
import Configuracion from './pages/Configuracion';
import Dashboard from './pages/Dashboard';
import Dispositivo from './pages/Dispositivo';
import Empleados from './pages/Empleados';
import FichaEmpleado from './pages/empleados/FichaEmpleado';
import Horarios from './pages/Horarios';
import Login from './pages/Login';
import Perfil from './pages/Perfil';
import Reportes from './pages/Reportes';
import { esAdministrador, useAuth } from './store/auth';

dayjs.locale('es');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

/** Deja pasar solo a los usuarios autenticados. */
function RutaProtegida() {
  const autenticado = useAuth((estado) => estado.autenticado);
  return autenticado ? <Outlet /> : <Navigate to="/login" replace />;
}

/** Restringe una seccion al administrador del sistema. */
function RutaAdministrador() {
  const usuario = useAuth((estado) => estado.usuario);
  return esAdministrador(usuario) ? <Outlet /> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <ConfigProvider
      locale={esES}
      theme={{
        token: {
          colorPrimary: '#1F4E79',
          borderRadius: 6,
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />

              <Route element={<RutaProtegida />}>
                <Route element={<Layout />}>
                  <Route index element={<Dashboard />} />
                  <Route path="empleados" element={<Empleados />} />
                  <Route path="empleados/:id" element={<FichaEmpleado />} />
                  <Route path="asistencia" element={<Asistencia />} />
                  <Route path="horarios" element={<Horarios />} />
                  <Route path="reportes" element={<Reportes />} />
                  <Route path="dispositivo" element={<Dispositivo />} />
                  <Route path="perfil" element={<Perfil />} />

                  <Route element={<RutaAdministrador />}>
                    <Route path="configuracion" element={<Configuracion />} />
                    <Route path="auditoria" element={<Auditoria />} />
                  </Route>
                </Route>
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
