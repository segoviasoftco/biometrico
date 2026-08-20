import {
  AuditOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DesktopOutlined,
  FileTextOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Dropdown, Layout as AntLayout, Menu, Tag, theme } from 'antd';
import { useMemo } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { esAdministrador, useAuth } from '../store/auth';

const { Header, Sider, Content } = AntLayout;

export default function Layout() {
  const { usuario, logout } = useAuth();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const { token } = theme.useToken();

  // El menu se arma segun el rol: mostrar opciones que luego devuelven 403
  // seria confuso para el usuario.
  const opciones = useMemo(() => {
    const base = [
      { key: '/', icon: <DashboardOutlined />, label: <Link to="/">Dashboard</Link> },
      { key: '/empleados', icon: <TeamOutlined />, label: <Link to="/empleados">Empleados</Link> },
      {
        key: '/asistencia',
        icon: <ClockCircleOutlined />,
        label: <Link to="/asistencia">Asistencia</Link>,
      },
      {
        key: '/horarios',
        icon: <BarChartOutlined />,
        label: <Link to="/horarios">Horarios y Turnos</Link>,
      },
      {
        key: '/reportes',
        icon: <FileTextOutlined />,
        label: <Link to="/reportes">Reportes</Link>,
      },
      {
        key: '/dispositivo',
        icon: <DesktopOutlined />,
        label: <Link to="/dispositivo">Dispositivo</Link>,
      },
    ];

    if (esAdministrador(usuario)) {
      base.push(
        {
          key: '/configuracion',
          icon: <SettingOutlined />,
          label: <Link to="/configuracion">Configuracion</Link>,
        },
        {
          key: '/auditoria',
          icon: <AuditOutlined />,
          label: <Link to="/auditoria">Auditoria</Link>,
        },
      );
    }
    return base;
  }, [usuario]);

  // Resalta la seccion activa aunque la ruta tenga subniveles (/empleados/12).
  const seleccionada = useMemo(() => {
    const coincidencia = opciones
      .map((o) => o.key)
      .filter((key) => key !== '/' && ubicacion.pathname.startsWith(key))
      .sort((a, b) => b.length - a.length)[0];
    return coincidencia ?? '/';
  }, [opciones, ubicacion.pathname]);

  const cerrarSesion = () => {
    logout();
    navegar('/login');
  };

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0" width={230} theme="dark">
        <div
          style={{
            padding: '20px 16px',
            color: '#fff',
            borderBottom: '1px solid rgba(255,255,255,0.12)',
          }}
        >
          <div style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.2 }}>Control de</div>
          <div style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.2 }}>Asistencia</div>
          <div style={{ fontSize: 11, opacity: 0.55, marginTop: 6 }}>ZKTeco MB560-VL</div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[seleccionada]} items={opciones} />
      </Sider>

      <AntLayout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 12,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          {usuario?.sede_nombre && <Tag color="blue">{usuario.sede_nombre}</Tag>}
          <Tag color={esAdministrador(usuario) ? 'gold' : 'default'}>{usuario?.rol_display}</Tag>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'perfil',
                  icon: <UserOutlined />,
                  label: <Link to="/perfil">Mi perfil</Link>,
                },
                { type: 'divider' },
                {
                  key: 'salir',
                  icon: <LogoutOutlined />,
                  label: 'Cerrar sesion',
                  danger: true,
                  onClick: cerrarSesion,
                },
              ],
            }}
          >
            <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar style={{ backgroundColor: token.colorPrimary }} icon={<UserOutlined />} />
              <span>{usuario?.nombre_completo}</span>
            </div>
          </Dropdown>
        </Header>

        <Content style={{ margin: 20 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
