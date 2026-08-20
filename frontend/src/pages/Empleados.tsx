import { PlusOutlined, ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Avatar,
  Button,
  Card,
  Col,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { mensajeError } from '../api/client';
import { empleadosApi, organizacionApi } from '../api/endpoints';
import { useAuth, puedeEditar } from '../store/auth';
import type { EmpleadoLista } from '../types';
import FormularioEmpleado from './empleados/FormularioEmpleado';

const { Title } = Typography;

export default function Empleados() {
  const { usuario } = useAuth();
  const editable = puedeEditar(usuario);
  const navegar = useNavigate();
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();

  const [pagina, setPagina] = useState(1);
  const [busqueda, setBusqueda] = useState('');
  const [filtros, setFiltros] = useState<Record<string, unknown>>({ estado: 'activo' });
  const [formularioAbierto, setFormularioAbierto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);

  const params = { page: pagina, search: busqueda || undefined, ...filtros };

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['empleados', params],
    queryFn: () => empleadosApi.listar(params),
  });

  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });
  const { data: departamentos } = useQuery({
    queryKey: ['departamentos', filtros.sede],
    queryFn: () => organizacionApi.departamentos({ page_size: 100, sede: filtros.sede }),
  });

  const sincronizar = useMutation({
    mutationFn: (id: number) => empleadosApi.sincronizar(id),
    onSuccess: (respuesta) => {
      message.success(respuesta.detalle ?? 'Empleado sincronizado con el dispositivo.');
      queryClient.invalidateQueries({ queryKey: ['empleados'] });
    },
    onError: (error) =>
      message.error(mensajeError(error, 'No se pudo sincronizar con el dispositivo.')),
  });

  const cesar = useMutation({
    mutationFn: (id: number) => empleadosApi.cesar(id),
    onSuccess: () => {
      message.success('El empleado fue dado de baja.');
      queryClient.invalidateQueries({ queryKey: ['empleados'] });
    },
    onError: (error) => message.error(mensajeError(error)),
  });

  const confirmarCese = (empleado: EmpleadoLista) => {
    modal.confirm({
      title: `Dar de baja a ${empleado.nombre_completo}?`,
      content:
        'El empleado quedara como cesado. No se elimina ningun dato: sus marcaciones y ' +
        'registros de asistencia se conservan como respaldo de la planilla.',
      okText: 'Dar de baja',
      okButtonProps: { danger: true },
      cancelText: 'Cancelar',
      onOk: () => cesar.mutateAsync(empleado.id),
    });
  };

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          Empleados
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            Actualizar
          </Button>
          {editable && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditandoId(null);
                setFormularioAbierto(true);
              }}
            >
              Nuevo empleado
            </Button>
          )}
        </Space>
      </div>

      <Card>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="Buscar por codigo, DNI o nombre"
              onChange={(e) => {
                setBusqueda(e.target.value);
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={5}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Sede"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
              onChange={(v) => {
                setFiltros((f) => ({ ...f, sede: v, departamento: undefined }));
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={5}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Departamento"
              options={departamentos?.results.map((d) => ({ value: d.id, label: d.nombre }))}
              onChange={(v) => {
                setFiltros((f) => ({ ...f, departamento: v }));
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={3}>
            <Select
              style={{ width: '100%' }}
              defaultValue="activo"
              options={[
                { value: 'activo', label: 'Activos' },
                { value: 'cesado', label: 'Cesados' },
                { value: 'vacaciones', label: 'Vacaciones' },
                { value: '', label: 'Todos' },
              ]}
              onChange={(v) => {
                setFiltros((f) => ({ ...f, estado: v || undefined }));
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={3}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Biometria"
              options={[
                { value: 'con', label: 'Con biometria' },
                { value: 'sin', label: 'Sin biometria' },
              ]}
              onChange={(v) => {
                setFiltros((f) => ({
                  ...f,
                  tiene_huella: v === 'sin' ? false : undefined,
                  tiene_rostro: v === 'sin' ? false : undefined,
                }));
                setPagina(1);
              }}
            />
          </Col>
        </Row>
      </Card>

      <Card styles={{ body: { padding: 0 } }}>
        <Table<EmpleadoLista>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          scroll={{ x: 1100 }}
          pagination={{
            current: pagina,
            total: data?.count ?? 0,
            pageSize: 25,
            onChange: setPagina,
            showTotal: (total) => `${total} empleados`,
          }}
          columns={[
            {
              title: '',
              dataIndex: 'foto',
              width: 60,
              render: (foto: string | null, fila) => (
                <Avatar src={foto}>{fila.nombre_completo.charAt(0)}</Avatar>
              ),
            },
            { title: 'Codigo', dataIndex: 'codigo_empleado', width: 100 },
            { title: 'DNI', dataIndex: 'dni', width: 110 },
            {
              title: 'Empleado',
              dataIndex: 'nombre_completo',
              render: (nombre: string, fila) => (
                <a onClick={() => navegar(`/empleados/${fila.id}`)}>{nombre}</a>
              ),
            },
            { title: 'Departamento', dataIndex: 'departamento_nombre', ellipsis: true },
            { title: 'Cargo', dataIndex: 'cargo_nombre', ellipsis: true },
            {
              title: 'Biometria',
              key: 'biometria',
              width: 150,
              render: (_, fila) => (
                <Space size={4}>
                  <Tooltip title={`${fila.cantidad_huellas} huella(s) registrada(s)`}>
                    <Tag color={fila.tiene_huella ? 'green' : 'default'}>
                      Huella {fila.tiene_huella ? `(${fila.cantidad_huellas})` : 'no'}
                    </Tag>
                  </Tooltip>
                  <Tag color={fila.tiene_rostro ? 'blue' : 'default'}>
                    Rostro {fila.tiene_rostro ? 'si' : 'no'}
                  </Tag>
                </Space>
              ),
            },
            {
              title: 'Equipo',
              dataIndex: 'sincronizado_dispositivo',
              width: 110,
              render: (sincronizado: boolean) =>
                sincronizado ? (
                  <Tag color="green">Sincronizado</Tag>
                ) : (
                  <Tag color="orange">Pendiente</Tag>
                ),
            },
            {
              title: 'Estado',
              dataIndex: 'estado_display',
              width: 100,
              render: (texto: string, fila) => (
                <Tag color={fila.estado === 'activo' ? 'green' : 'default'}>{texto}</Tag>
              ),
            },
            {
              title: 'Acciones',
              key: 'acciones',
              fixed: 'right',
              width: editable ? 220 : 90,
              render: (_, fila) => (
                <Space size={4}>
                  <Button size="small" onClick={() => navegar(`/empleados/${fila.id}`)}>
                    Ver
                  </Button>
                  {editable && (
                    <>
                      <Tooltip title="Enviar los datos de este empleado al dispositivo">
                        <Button
                          size="small"
                          icon={<SyncOutlined />}
                          loading={sincronizar.isPending && sincronizar.variables === fila.id}
                          onClick={() => sincronizar.mutate(fila.id)}
                        />
                      </Tooltip>
                      <Button
                        size="small"
                        onClick={() => {
                          setEditandoId(fila.id);
                          setFormularioAbierto(true);
                        }}
                      >
                        Editar
                      </Button>
                      {fila.estado === 'activo' && (
                        <Button size="small" danger onClick={() => confirmarCese(fila)}>
                          Baja
                        </Button>
                      )}
                    </>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <FormularioEmpleado
        abierto={formularioAbierto}
        empleadoId={editandoId}
        onCerrar={() => setFormularioAbierto(false)}
        onGuardado={() => {
          setFormularioAbierto(false);
          queryClient.invalidateQueries({ queryKey: ['empleados'] });
        }}
      />
    </Space>
  );
}
