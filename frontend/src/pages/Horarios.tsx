import { CheckOutlined, CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
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
  TimePicker,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';

import { mensajeError } from '../api/client';
import { empleadosApi, horariosApi, organizacionApi } from '../api/endpoints';
import { puedeEditar, useAuth } from '../store/auth';
import type { AsignacionTurno, Feriado, Horario, Permiso, Turno } from '../types';

const { Title, Text } = Typography;

const DIAS = [
  { valor: 0, nombre: 'Lunes' },
  { valor: 1, nombre: 'Martes' },
  { valor: 2, nombre: 'Miercoles' },
  { valor: 3, nombre: 'Jueves' },
  { valor: 4, nombre: 'Viernes' },
  { valor: 5, nombre: 'Sabado' },
  { valor: 6, nombre: 'Domingo' },
];

export default function Horarios() {
  const { usuario } = useAuth();
  const editable = puedeEditar(usuario);

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={3} style={{ margin: 0 }}>
        Horarios y Turnos
      </Title>
      <Tabs
        defaultActiveKey="horarios"
        items={[
          { key: 'horarios', label: 'Horarios', children: <PanelHorarios editable={editable} /> },
          { key: 'turnos', label: 'Turnos', children: <PanelTurnos editable={editable} /> },
          {
            key: 'asignaciones',
            label: 'Asignaciones',
            children: <PanelAsignaciones editable={editable} />,
          },
          { key: 'feriados', label: 'Feriados', children: <PanelFeriados editable={editable} /> },
          { key: 'permisos', label: 'Permisos', children: <PanelPermisos editable={editable} /> },
        ]}
      />
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelHorarios({ editable }: { editable: boolean }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['horarios'],
    queryFn: () => horariosApi.horarios({ page_size: 100 }),
  });

  const guardar = useMutation({
    mutationFn: (valores: Record<string, unknown>) => {
      const datos = {
        ...valores,
        hora_entrada: dayjs(valores.hora_entrada as string).format('HH:mm:ss'),
        hora_salida: dayjs(valores.hora_salida as string).format('HH:mm:ss'),
        hora_inicio_refrigerio: valores.hora_inicio_refrigerio
          ? dayjs(valores.hora_inicio_refrigerio as string).format('HH:mm:ss')
          : null,
        hora_fin_refrigerio: valores.hora_fin_refrigerio
          ? dayjs(valores.hora_fin_refrigerio as string).format('HH:mm:ss')
          : null,
      };
      return editandoId
        ? horariosApi.actualizarHorario(editandoId, datos)
        : horariosApi.crearHorario(datos);
    },
    onSuccess: () => {
      message.success('Horario guardado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['horarios'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const tieneRefrigerio = Form.useWatch('tiene_refrigerio', form);

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {editable && (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditandoId(null);
            form.resetFields();
            form.setFieldsValue({ tolerancia_entrada: 5, tolerancia_salida: 5, minutos_falta: 120 });
            setAbierto(true);
          }}
        >
          Nuevo horario
        </Button>
      )}

      <Card styles={{ body: { padding: 0 } }}>
        <Table<Horario>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={false}
          scroll={{ x: 900 }}
          columns={[
            { title: 'Nombre', dataIndex: 'nombre' },
            {
              title: 'Jornada',
              key: 'jornada',
              render: (_, f) => (
                <Space>
                  <Text>
                    {f.hora_entrada.slice(0, 5)} - {f.hora_salida.slice(0, 5)}
                  </Text>
                  {f.cruza_medianoche && <Tag color="purple">Nocturno</Tag>}
                </Space>
              ),
            },
            {
              title: 'Tolerancia',
              dataIndex: 'tolerancia_entrada',
              render: (v: number) => `${v} min`,
            },
            {
              title: 'Refrigerio',
              key: 'refrigerio',
              render: (_, f) =>
                f.tiene_refrigerio
                  ? `${f.hora_inicio_refrigerio?.slice(0, 5)} - ${f.hora_fin_refrigerio?.slice(0, 5)}`
                  : 'Sin refrigerio',
            },
            {
              title: 'Horas',
              dataIndex: 'horas_jornada',
              render: (v: number) => `${v} h`,
            },
            {
              title: 'Limite de falta',
              dataIndex: 'minutos_falta',
              render: (v: number) => `${v} min`,
            },
            ...(editable
              ? [
                  {
                    title: '',
                    key: 'acciones',
                    width: 80,
                    render: (_: unknown, f: Horario) => (
                      <Button
                        size="small"
                        onClick={() => {
                          setEditandoId(f.id);
                          form.setFieldsValue({
                            ...f,
                            hora_entrada: dayjs(f.hora_entrada, 'HH:mm:ss'),
                            hora_salida: dayjs(f.hora_salida, 'HH:mm:ss'),
                            hora_inicio_refrigerio: f.hora_inicio_refrigerio
                              ? dayjs(f.hora_inicio_refrigerio, 'HH:mm:ss')
                              : null,
                            hora_fin_refrigerio: f.hora_fin_refrigerio
                              ? dayjs(f.hora_fin_refrigerio, 'HH:mm:ss')
                              : null,
                          });
                          setAbierto(true);
                        }}
                      >
                        Editar
                      </Button>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title={editandoId ? 'Editar horario' : 'Nuevo horario'}
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={guardar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => guardar.mutate(v)}>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input placeholder="Administrativo (08:00 - 17:00)" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="hora_entrada" label="Hora de entrada" rules={[{ required: true }]}>
                <TimePicker style={{ width: '100%' }} format="HH:mm" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="hora_salida" label="Hora de salida" rules={[{ required: true }]}>
                <TimePicker style={{ width: '100%' }} format="HH:mm" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item
                name="tolerancia_entrada"
                label="Tolerancia entrada"
                tooltip="Minutos de gracia antes de contar tardanza."
              >
                <InputNumber style={{ width: '100%' }} min={0} max={120} addonAfter="min" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="tolerancia_salida" label="Tolerancia salida">
                <InputNumber style={{ width: '100%' }} min={0} max={120} addonAfter="min" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="minutos_falta"
                label="Limite de falta"
                tooltip="Si la tardanza supera estos minutos, el dia se marca como falta."
              >
                <InputNumber style={{ width: '100%' }} min={0} addonAfter="min" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tiene_refrigerio" label="Tiene refrigerio" valuePropName="checked">
            <Switch />
          </Form.Item>
          {tieneRefrigerio && (
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item
                  name="hora_inicio_refrigerio"
                  label="Inicio de refrigerio"
                  rules={[{ required: true }]}
                >
                  <TimePicker style={{ width: '100%' }} format="HH:mm" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="hora_fin_refrigerio"
                  label="Fin de refrigerio"
                  rules={[{ required: true }]}
                >
                  <TimePicker style={{ width: '100%' }} format="HH:mm" />
                </Form.Item>
              </Col>
            </Row>
          )}
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelTurnos({ editable }: { editable: boolean }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['turnos'],
    queryFn: () => horariosApi.turnos({ page_size: 100 }),
  });
  const { data: horarios } = useQuery({
    queryKey: ['horarios'],
    queryFn: () => horariosApi.horarios({ page_size: 100 }),
  });

  const opcionesHorario = [
    { value: null, label: 'Descanso' },
    ...(horarios?.results ?? []).map((h) => ({ value: h.id, label: h.nombre })),
  ];

  const guardar = useMutation({
    mutationFn: (valores: Record<string, unknown>) => {
      // El patron semanal se envia completo: el backend reemplaza los detalles.
      const detalles = DIAS.map((d) => ({
        dia_semana: d.valor,
        horario: (valores[`dia_${d.valor}`] as number | null) ?? null,
      }));
      const datos = {
        nombre: valores.nombre,
        tipo: valores.tipo,
        descripcion: valores.descripcion ?? '',
        detalles,
      };
      return editandoId
        ? horariosApi.actualizarTurno(editandoId, datos as never)
        : horariosApi.crearTurno(datos as never);
    },
    onSuccess: () => {
      message.success('Turno guardado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['turnos'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {editable && (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditandoId(null);
            form.resetFields();
            form.setFieldsValue({ tipo: 'fijo' });
            setAbierto(true);
          }}
        >
          Nuevo turno
        </Button>
      )}

      <Card styles={{ body: { padding: 0 } }}>
        <Table<Turno>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={false}
          scroll={{ x: 1000 }}
          columns={[
            { title: 'Nombre', dataIndex: 'nombre', width: 180 },
            { title: 'Tipo', dataIndex: 'tipo_display', width: 100 },
            {
              title: 'Patron semanal',
              key: 'patron',
              render: (_, f) => (
                <Space size={4} wrap>
                  {DIAS.map((d) => {
                    const detalle = f.detalles.find((x) => x.dia_semana === d.valor);
                    const descanso = !detalle?.horario;
                    return (
                      <Tag key={d.valor} color={descanso ? 'default' : 'blue'}>
                        {d.nombre.slice(0, 3)}: {descanso ? 'Desc.' : detalle?.horario_nombre}
                      </Tag>
                    );
                  })}
                </Space>
              ),
            },
            {
              title: 'Empleados',
              dataIndex: 'total_empleados',
              width: 100,
              align: 'right',
            },
            ...(editable
              ? [
                  {
                    title: '',
                    key: 'acciones',
                    width: 80,
                    render: (_: unknown, f: Turno) => (
                      <Button
                        size="small"
                        onClick={() => {
                          setEditandoId(f.id);
                          const valores: Record<string, unknown> = {
                            nombre: f.nombre,
                            tipo: f.tipo,
                            descripcion: f.descripcion,
                          };
                          DIAS.forEach((d) => {
                            valores[`dia_${d.valor}`] =
                              f.detalles.find((x) => x.dia_semana === d.valor)?.horario ?? null;
                          });
                          form.setFieldsValue(valores);
                          setAbierto(true);
                        }}
                      >
                        Editar
                      </Button>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title={editandoId ? 'Editar turno' : 'Nuevo turno'}
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={guardar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={(v) => guardar.mutate(v)}>
          <Row gutter={12}>
            <Col span={16}>
              <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
                <Input placeholder="Lunes a Viernes" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="tipo" label="Tipo">
                <Select
                  options={[
                    { value: 'fijo', label: 'Fijo' },
                    { value: 'rotativo', label: 'Rotativo' },
                    { value: 'flexible', label: 'Flexible' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="descripcion" label="Descripcion">
            <Input />
          </Form.Item>

          <Text strong>Horario por dia</Text>
          <div style={{ marginTop: 8 }}>
            {DIAS.map((d) => (
              <Form.Item
                key={d.valor}
                name={`dia_${d.valor}`}
                label={d.nombre}
                style={{ marginBottom: 10 }}
              >
                <Select allowClear={false} options={opcionesHorario} placeholder="Descanso" />
              </Form.Item>
            ))}
          </div>
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelAsignaciones({ editable }: { editable: boolean }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['asignaciones'],
    queryFn: () => horariosApi.asignaciones({ page_size: 100, vigentes: 'true' }),
  });
  const { data: turnos } = useQuery({
    queryKey: ['turnos'],
    queryFn: () => horariosApi.turnos({ page_size: 100 }),
  });
  const { data: empleados } = useQuery({
    queryKey: ['empleados-activos'],
    queryFn: () => empleadosApi.listar({ estado: 'activo', page_size: 500 }),
  });

  const asignar = useMutation({
    mutationFn: (valores: Record<string, unknown>) =>
      horariosApi.asignarMasivo({
        empleados: valores.empleados as number[],
        turno: valores.turno as number,
        fecha_inicio: dayjs(valores.fecha_inicio as string).format('YYYY-MM-DD'),
        fecha_fin: valores.fecha_fin
          ? dayjs(valores.fecha_fin as string).format('YYYY-MM-DD')
          : null,
        cerrar_asignacion_anterior: valores.cerrar_asignacion_anterior as boolean,
      }),
    onSuccess: (r) => {
      message.success(r.detalle);
      if (r.omitidos?.length) {
        message.warning(`${r.omitidos.length} empleado(s) fueron omitidos por tener turno vigente.`);
      }
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['asignaciones'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {editable && (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields();
            form.setFieldsValue({ fecha_inicio: dayjs(), cerrar_asignacion_anterior: true });
            setAbierto(true);
          }}
        >
          Asignar turno a empleados
        </Button>
      )}

      <Card styles={{ body: { padding: 0 } }}>
        <Table<AsignacionTurno>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={{ pageSize: 25 }}
          scroll={{ x: 800 }}
          columns={[
            { title: 'Codigo', dataIndex: 'empleado_codigo', width: 100 },
            { title: 'Empleado', dataIndex: 'empleado_nombre' },
            { title: 'Turno', dataIndex: 'turno_nombre' },
            {
              title: 'Desde',
              dataIndex: 'fecha_inicio',
              render: (v: string) => dayjs(v).format('DD/MM/YYYY'),
            },
            {
              title: 'Hasta',
              dataIndex: 'fecha_fin',
              render: (v: string | null) =>
                v ? dayjs(v).format('DD/MM/YYYY') : <Tag color="green">Vigente</Tag>,
            },
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title="Asignar turno"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={asignar.isPending}
        okText="Asignar"
        cancelText="Cancelar"
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={(v) => asignar.mutate(v)}>
          <Form.Item
            name="empleados"
            label="Empleados"
            rules={[{ required: true, message: 'Seleccione al menos un empleado.' }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              placeholder="Buscar y seleccionar empleados"
              options={empleados?.results.map((e) => ({
                value: e.id,
                label: `${e.codigo_empleado} - ${e.nombre_completo}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="turno" label="Turno" rules={[{ required: true }]}>
            <Select options={turnos?.results.map((t) => ({ value: t.id, label: t.nombre }))} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="fecha_inicio" label="Vigente desde" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="fecha_fin" label="Vigente hasta (opcional)">
                <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="cerrar_asignacion_anterior"
            label="Cerrar el turno anterior automaticamente"
            valuePropName="checked"
            tooltip="Evita que un empleado quede con dos turnos vigentes a la vez."
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelFeriados({ editable }: { editable: boolean }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['feriados'],
    queryFn: () => horariosApi.feriados({ page_size: 200 }),
  });
  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });

  const guardar = useMutation({
    mutationFn: (valores: Record<string, unknown>) =>
      horariosApi.crearFeriado({
        ...valores,
        fecha: dayjs(valores.fecha as string).format('YYYY-MM-DD'),
      } as never),
    onSuccess: () => {
      message.success('Feriado registrado.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['feriados'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {editable && (
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAbierto(true)}>
          Nuevo feriado
        </Button>
      )}

      <Card styles={{ body: { padding: 0 } }}>
        <Table<Feriado>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={{ pageSize: 25 }}
          columns={[
            {
              title: 'Fecha',
              dataIndex: 'fecha',
              render: (v: string) => dayjs(v).format('DD/MM/YYYY'),
            },
            { title: 'Descripcion', dataIndex: 'descripcion' },
            {
              title: 'Recurrente',
              dataIndex: 'es_recurrente',
              render: (v: boolean) =>
                v ? <Tag color="blue">Cada ano</Tag> : <Tag>Solo este ano</Tag>,
            },
            { title: 'Sede', dataIndex: 'sede_nombre' },
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title="Nuevo feriado"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={guardar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => guardar.mutate(v)}>
          <Form.Item name="fecha" label="Fecha" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
          </Form.Item>
          <Form.Item name="descripcion" label="Descripcion" rules={[{ required: true }]}>
            <Input placeholder="Fiestas Patrias" />
          </Form.Item>
          <Form.Item
            name="es_recurrente"
            label="Se repite cada ano"
            valuePropName="checked"
            tooltip="Para feriados de fecha fija."
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="sede"
            label="Sede"
            tooltip="Dejar vacio para que aplique a todas las sedes."
          >
            <Select
              allowClear
              placeholder="Todas las sedes"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

// ----------------------------------------------------------------------
function PanelPermisos({ editable }: { editable: boolean }) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [filtroEstado, setFiltroEstado] = useState<string | undefined>();

  const { data, isLoading } = useQuery({
    queryKey: ['permisos', filtroEstado],
    queryFn: () => horariosApi.permisos({ page_size: 100, estado: filtroEstado }),
  });
  const { data: empleados } = useQuery({
    queryKey: ['empleados-activos'],
    queryFn: () => empleadosApi.listar({ estado: 'activo', page_size: 500 }),
  });

  const crear = useMutation({
    mutationFn: (valores: Record<string, unknown>) => {
      const [inicio, fin] = valores.rango as [string, string];
      return horariosApi.crearPermiso({
        empleado: valores.empleado,
        tipo: valores.tipo,
        fecha_inicio: dayjs(inicio).format('YYYY-MM-DD'),
        fecha_fin: dayjs(fin).format('YYYY-MM-DD'),
        con_goce: valores.con_goce,
        motivo: valores.motivo ?? '',
      } as never);
    },
    onSuccess: () => {
      message.success('Permiso registrado. Queda pendiente de aprobacion.');
      setAbierto(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['permisos'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const aprobar = useMutation({
    mutationFn: ({ id, aprobar: ok }: { id: number; aprobar: boolean }) =>
      horariosApi.aprobarPermiso(id, ok),
    onSuccess: (r) => {
      message.success(`${r.detalle} Se recalcularon ${r.dias_recalculados} dia(s).`);
      queryClient.invalidateQueries({ queryKey: ['permisos'] });
      queryClient.invalidateQueries({ queryKey: ['registros-asistencia'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap>
        {editable && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields();
              form.setFieldsValue({ con_goce: true });
              setAbierto(true);
            }}
          >
            Registrar permiso
          </Button>
        )}
        <Select
          allowClear
          style={{ width: 200 }}
          placeholder="Filtrar por estado"
          options={[
            { value: 'pendiente', label: 'Pendientes' },
            { value: 'aprobado', label: 'Aprobados' },
            { value: 'rechazado', label: 'Rechazados' },
          ]}
          onChange={setFiltroEstado}
        />
      </Space>

      <Card styles={{ body: { padding: 0 } }}>
        <Table<Permiso>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          pagination={{ pageSize: 25 }}
          scroll={{ x: 1000 }}
          columns={[
            { title: 'Codigo', dataIndex: 'empleado_codigo', width: 90 },
            { title: 'Empleado', dataIndex: 'empleado_nombre', ellipsis: true },
            { title: 'Tipo', dataIndex: 'tipo_display' },
            {
              title: 'Periodo',
              key: 'periodo',
              render: (_, f) =>
                `${dayjs(f.fecha_inicio).format('DD/MM/YYYY')} - ${dayjs(f.fecha_fin).format('DD/MM/YYYY')}`,
            },
            { title: 'Dias', dataIndex: 'dias_totales', width: 70, align: 'right' },
            {
              title: 'Goce',
              dataIndex: 'con_goce',
              width: 110,
              render: (v: boolean) =>
                v ? <Tag color="green">Con goce</Tag> : <Tag color="orange">Sin goce</Tag>,
            },
            {
              title: 'Estado',
              dataIndex: 'estado_display',
              width: 110,
              render: (texto: string, f) => (
                <Tag
                  color={
                    f.estado === 'aprobado' ? 'green' : f.estado === 'rechazado' ? 'red' : 'orange'
                  }
                >
                  {texto}
                </Tag>
              ),
            },
            ...(editable
              ? [
                  {
                    title: 'Acciones',
                    key: 'acciones',
                    fixed: 'right' as const,
                    width: 130,
                    render: (_: unknown, f: Permiso) =>
                      f.estado === 'pendiente' ? (
                        <Space size={4}>
                          <Button
                            size="small"
                            type="primary"
                            icon={<CheckOutlined />}
                            loading={aprobar.isPending}
                            onClick={() => aprobar.mutate({ id: f.id, aprobar: true })}
                          />
                          <Button
                            size="small"
                            danger
                            icon={<CloseOutlined />}
                            loading={aprobar.isPending}
                            onClick={() => aprobar.mutate({ id: f.id, aprobar: false })}
                          />
                        </Space>
                      ) : (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {f.aprobado_por_nombre ?? '-'}
                        </Text>
                      ),
                  },
                ]
              : []),
          ]}
        />
      </Card>

      <Modal
        open={abierto}
        title="Registrar permiso"
        onCancel={() => setAbierto(false)}
        onOk={() => form.submit()}
        confirmLoading={crear.isPending}
        okText="Registrar"
        cancelText="Cancelar"
      >
        <Form form={form} layout="vertical" onFinish={(v) => crear.mutate(v)}>
          <Form.Item name="empleado" label="Empleado" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={empleados?.results.map((e) => ({
                value: e.id,
                label: `${e.codigo_empleado} - ${e.nombre_completo}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="tipo" label="Tipo de permiso" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'vacaciones', label: 'Vacaciones' },
                { value: 'descanso_medico', label: 'Descanso medico' },
                { value: 'permiso_personal', label: 'Permiso personal' },
                { value: 'licencia', label: 'Licencia' },
                { value: 'capacitacion', label: 'Capacitacion' },
                { value: 'comision', label: 'Comision de servicio' },
              ]}
            />
          </Form.Item>
          <Form.Item name="rango" label="Periodo" rules={[{ required: true }]}>
            <DatePicker.RangePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
          </Form.Item>
          <Form.Item
            name="con_goce"
            label="Con goce de haber"
            valuePropName="checked"
            tooltip="Si es sin goce, los dias se consideran para el descuento."
          >
            <Switch />
          </Form.Item>
          <Form.Item name="motivo" label="Motivo">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
