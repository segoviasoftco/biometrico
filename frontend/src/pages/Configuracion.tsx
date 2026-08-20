import { PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';

import { mensajeError } from '../api/client';
import { horariosApi, organizacionApi, usuariosApi } from '../api/endpoints';
import type { Area, Cargo, Departamento, Sede, Usuario } from '../types';

const { Title, Text } = Typography;

export default function Configuracion() {
  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={3} style={{ margin: 0 }}>
        Configuracion del Sistema
      </Title>
      <Tabs
        defaultActiveKey="usuarios"
        items={[
          { key: 'usuarios', label: 'Usuarios y roles', children: <PanelUsuarios /> },
          { key: 'organizacion', label: 'Organizacion', children: <PanelOrganizacion /> },
          { key: 'asistencia', label: 'Parametros de asistencia', children: <PanelParametros /> },
        ]}
      />
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelUsuarios() {
  const [form] = Form.useForm();
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);

  const rolSeleccionado = Form.useWatch('rol', form);

  const { data, isLoading } = useQuery({
    queryKey: ['usuarios'],
    queryFn: () => usuariosApi.listar({ page_size: 100 }),
  });
  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });

  const guardar = useMutation({
    mutationFn: (valores: Record<string, unknown>) =>
      editandoId
        ? usuariosApi.actualizar(editandoId, valores as never)
        : usuariosApi.crear(valores as never),
    onSuccess: () => {
      message.success('Usuario guardado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['usuarios'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const desactivar = useMutation({
    mutationFn: (id: number) => usuariosApi.desactivar(id),
    onSuccess: () => {
      message.success('Usuario desactivado.');
      queryClient.invalidateQueries({ queryKey: ['usuarios'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={() => {
          setEditandoId(null);
          form.resetFields();
          form.setFieldsValue({ rol: 'rrhh', is_active: true });
          setAbierto(true);
        }}
      >
        Nuevo usuario
      </Button>

      <Card styles={{ body: { padding: 0 } }}>
        <Table<Usuario>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={{ pageSize: 25 }}
          scroll={{ x: 800 }}
          columns={[
            { title: 'Nombre', dataIndex: 'nombre_completo' },
            { title: 'Correo', dataIndex: 'email' },
            {
              title: 'Rol',
              dataIndex: 'rol_display',
              render: (texto: string, f) => (
                <Tag color={f.rol === 'administrador' ? 'gold' : f.rol === 'rrhh' ? 'blue' : 'default'}>
                  {texto}
                </Tag>
              ),
            },
            { title: 'Sede', dataIndex: 'sede_nombre', render: (v: string | null) => v ?? 'Todas' },
            {
              title: 'Estado',
              dataIndex: 'is_active',
              render: (v: boolean) =>
                v ? <Tag color="green">Activo</Tag> : <Tag>Inactivo</Tag>,
            },
            {
              title: 'Acciones',
              key: 'acciones',
              width: 160,
              render: (_, f) => (
                <Space size={4}>
                  <Button
                    size="small"
                    onClick={() => {
                      setEditandoId(f.id);
                      form.setFieldsValue({ ...f, password: '' });
                      setAbierto(true);
                    }}
                  >
                    Editar
                  </Button>
                  {f.is_active && (
                    <Button
                      size="small"
                      danger
                      onClick={() =>
                        modal.confirm({
                          title: `Desactivar a ${f.nombre_completo}?`,
                          content:
                            'No podra iniciar sesion. Su historial en la auditoria se conserva.',
                          okText: 'Desactivar',
                          okButtonProps: { danger: true },
                          cancelText: 'Cancelar',
                          onOk: () => desactivar.mutateAsync(f.id),
                        })
                      }
                    >
                      Desactivar
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title={editandoId ? 'Editar usuario' : 'Nuevo usuario'}
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={guardar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => guardar.mutate(v)}>
          <Form.Item
            name="email"
            label="Correo electronico"
            rules={[{ required: true, type: 'email', message: 'Ingrese un correo valido.' }]}
          >
            <Input />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="nombres" label="Nombres" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="apellidos" label="Apellidos" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="rol" label="Rol" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'administrador', label: 'Administrador (acceso total)' },
                { value: 'rrhh', label: 'Recursos Humanos (gestion operativa)' },
                { value: 'supervisor', label: 'Supervisor (solo consulta de su sede)' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="sede"
            label="Sede asignada"
            tooltip="El supervisor solo ve la informacion de su sede."
            rules={[
              {
                required: rolSeleccionado === 'supervisor',
                message: 'Un supervisor debe tener una sede asignada.',
              },
            ]}
          >
            <Select
              allowClear
              placeholder={rolSeleccionado === 'supervisor' ? 'Obligatorio' : 'Todas las sedes'}
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Form.Item>
          <Form.Item
            name="password"
            label={editandoId ? 'Nueva clave (dejar vacio para no cambiar)' : 'Clave'}
            rules={[{ required: !editandoId, message: 'Ingrese la clave inicial.' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_active" label="Activo" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelOrganizacion() {
  return (
    <Tabs
      tabPosition="left"
      items={[
        { key: 'sedes', label: 'Sedes', children: <TablaSedes /> },
        { key: 'departamentos', label: 'Departamentos', children: <TablaDepartamentos /> },
        { key: 'areas', label: 'Areas', children: <TablaAreas /> },
        { key: 'cargos', label: 'Cargos', children: <TablaCargos /> },
      ]}
    />
  );
}

function TablaSedes() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });

  const crear = useMutation({
    mutationFn: (v: Record<string, unknown>) => organizacionApi.crearSede(v),
    onSuccess: () => {
      message.success('Sede creada.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['sedes'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} onClick={() => setAbierto(true)}>
        Nueva sede
      </Button>
      <Table<Sede>
        rowKey="id"
        size="small"
        loading={isLoading}
        dataSource={data?.results ?? []}
        pagination={false}
        columns={[
          { title: 'Codigo', dataIndex: 'codigo', width: 100 },
          { title: 'Nombre', dataIndex: 'nombre' },
          { title: 'Direccion', dataIndex: 'direccion', ellipsis: true },
          { title: 'Empleados', dataIndex: 'total_empleados', width: 100, align: 'right' },
        ]}
      />
      <Modal
        open={abierto}
        title="Nueva sede"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={crear.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => crear.mutate(v)}>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="codigo" label="Codigo" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="direccion" label="Direccion">
            <Input />
          </Form.Item>
          <Form.Item name="telefono" label="Telefono">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function TablaDepartamentos() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['departamentos-todos'],
    queryFn: () => organizacionApi.departamentos({ page_size: 200 }),
  });
  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });

  const crear = useMutation({
    mutationFn: (v: Record<string, unknown>) => organizacionApi.crearDepartamento(v),
    onSuccess: () => {
      message.success('Departamento creado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['departamentos-todos'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} onClick={() => setAbierto(true)}>
        Nuevo departamento
      </Button>
      <Table<Departamento>
        rowKey="id"
        size="small"
        loading={isLoading}
        dataSource={data?.results ?? []}
        pagination={false}
        columns={[
          { title: 'Codigo', dataIndex: 'codigo', width: 100 },
          { title: 'Nombre', dataIndex: 'nombre' },
          { title: 'Sede', dataIndex: 'sede_nombre' },
          { title: 'Empleados', dataIndex: 'total_empleados', width: 100, align: 'right' },
        ]}
      />
      <Modal
        open={abierto}
        title="Nuevo departamento"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={crear.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => crear.mutate(v)}>
          <Form.Item name="sede" label="Sede" rules={[{ required: true }]}>
            <Select options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))} />
          </Form.Item>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="codigo" label="Codigo" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function TablaAreas() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['areas-todas'],
    queryFn: () => organizacionApi.areas({ page_size: 200 }),
  });
  const { data: departamentos } = useQuery({
    queryKey: ['departamentos-todos'],
    queryFn: () => organizacionApi.departamentos({ page_size: 200 }),
  });

  const crear = useMutation({
    mutationFn: (v: Record<string, unknown>) => organizacionApi.crearArea(v),
    onSuccess: () => {
      message.success('Area creada.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['areas-todas'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} onClick={() => setAbierto(true)}>
        Nueva area
      </Button>
      <Table<Area>
        rowKey="id"
        size="small"
        loading={isLoading}
        dataSource={data?.results ?? []}
        pagination={false}
        columns={[
          { title: 'Codigo', dataIndex: 'codigo', width: 100 },
          { title: 'Nombre', dataIndex: 'nombre' },
          { title: 'Departamento', dataIndex: 'departamento_nombre' },
          { title: 'Sede', dataIndex: 'sede_nombre' },
        ]}
      />
      <Modal
        open={abierto}
        title="Nueva area"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={crear.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => crear.mutate(v)}>
          <Form.Item name="departamento" label="Departamento" rules={[{ required: true }]}>
            <Select
              options={departamentos?.results.map((d) => ({
                value: d.id,
                label: `${d.nombre} (${d.sede_nombre})`,
              }))}
            />
          </Form.Item>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="codigo" label="Codigo" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function TablaCargos() {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['cargos'],
    queryFn: () => organizacionApi.cargos({ page_size: 200 }),
  });

  const crear = useMutation({
    mutationFn: (v: Record<string, unknown>) => organizacionApi.crearCargo(v),
    onSuccess: () => {
      message.success('Cargo creado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['cargos'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} onClick={() => setAbierto(true)}>
        Nuevo cargo
      </Button>
      <Table<Cargo>
        rowKey="id"
        size="small"
        loading={isLoading}
        dataSource={data?.results ?? []}
        pagination={false}
        columns={[
          { title: 'Nombre', dataIndex: 'nombre' },
          { title: 'Descripcion', dataIndex: 'descripcion', ellipsis: true },
        ]}
      />
      <Modal
        open={abierto}
        title="Nuevo cargo"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={crear.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => crear.mutate(v)}>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="descripcion" label="Descripcion">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelParametros() {
  const [form] = Form.useForm();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ['config-asistencia'],
    queryFn: horariosApi.configuracion,
  });

  const guardar = useMutation({
    mutationFn: (v: Record<string, unknown>) => horariosApi.guardarConfiguracion(v),
    onSuccess: () => message.success('Configuracion guardada.'),
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Card loading={isLoading} style={{ maxWidth: 640 }}>
      <Form
        form={form}
        layout="vertical"
        initialValues={data}
        onFinish={(v) => guardar.mutate(v)}
        key={JSON.stringify(data)}
      >
        <Form.Item
          name="minutos_tolerancia_global"
          label="Tolerancia global adicional"
          tooltip="Se suma a la tolerancia propia de cada horario."
        >
          <InputNumber min={0} max={60} addonAfter="minutos" style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="considerar_marcacion_unica_como_falta"
          label="Un dia con una sola marcacion cuenta como falta"
          valuePropName="checked"
          tooltip="Si esta desactivado, se registra como asistencia incompleta."
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name="valor_minuto_tardanza"
          label="Costo del minuto de tardanza"
          tooltip="Si es 0, el descuento se calcula a partir del sueldo basico del empleado."
        >
          <InputNumber min={0} precision={4} prefix="S/" style={{ width: '100%' }} />
        </Form.Item>

        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          Estos parametros afectan el calculo de nuevas evaluaciones. Para aplicarlos a un
          periodo ya procesado, use "Recalcular periodo" en la seccion Asistencia.
        </Text>

        <Button type="primary" htmlType="submit" loading={guardar.isPending}>
          Guardar configuracion
        </Button>
      </Form>
    </Card>
  );
}
