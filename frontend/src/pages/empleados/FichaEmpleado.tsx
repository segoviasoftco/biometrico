import { ArrowLeftOutlined, SyncOutlined, UndoOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Avatar,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { mensajeError } from '../../api/client';
import { asistenciaApi, empleadosApi } from '../../api/endpoints';
import { useAuth, puedeEditar } from '../../store/auth';
import type { RegistroAsistencia } from '../../types';
import { COLOR_ESTADO } from '../asistencia/estados';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

export default function FichaEmpleado() {
  const { id } = useParams<{ id: string }>();
  const empleadoId = Number(id);
  const navegar = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { usuario } = useAuth();
  const editable = puedeEditar(usuario);

  const [rango, setRango] = useState<[Dayjs, Dayjs]>([
    dayjs().startOf('month'),
    dayjs().endOf('month'),
  ]);

  const paramsRango = {
    fecha_inicio: rango[0].format('YYYY-MM-DD'),
    fecha_fin: rango[1].format('YYYY-MM-DD'),
  };

  const { data: empleado, isLoading } = useQuery({
    queryKey: ['empleado', empleadoId],
    queryFn: () => empleadosApi.obtener(empleadoId),
  });

  const { data: resumen } = useQuery({
    queryKey: ['resumen-empleado', empleadoId, paramsRango],
    queryFn: () => asistenciaApi.resumenEmpleado(empleadoId, paramsRango),
  });

  const { data: registros } = useQuery({
    queryKey: ['registros-empleado', empleadoId, paramsRango],
    queryFn: () =>
      asistenciaApi.registros({
        empleado: empleadoId,
        fecha__gte: paramsRango.fecha_inicio,
        fecha__lte: paramsRango.fecha_fin,
        page_size: 100,
        ordering: '-fecha',
      }),
  });

  const sincronizar = useMutation({
    mutationFn: () => empleadosApi.sincronizar(empleadoId),
    onSuccess: (r) => {
      message.success(r.detalle ?? 'Empleado sincronizado.');
      queryClient.invalidateQueries({ queryKey: ['empleado', empleadoId] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const restaurar = useMutation({
    mutationFn: () => empleadosApi.restaurarHuellas(empleadoId),
    onSuccess: (r) => message.success(r.detalle ?? 'Huellas restauradas en el equipo.'),
    onError: (e) => message.error(mensajeError(e)),
  });

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;
  if (!empleado) return <Empty description="No se encontro el empleado" />;

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navegar('/empleados')}>
            Volver
          </Button>
          <Title level={3} style={{ margin: 0 }}>
            {empleado.nombre_completo}
          </Title>
        </Space>
        {editable && (
          <Space>
            <Button
              icon={<SyncOutlined />}
              loading={sincronizar.isPending}
              onClick={() => sincronizar.mutate()}
            >
              Sincronizar con el equipo
            </Button>
            {empleado.huellas.length > 0 && (
              <Button
                icon={<UndoOutlined />}
                loading={restaurar.isPending}
                onClick={() => restaurar.mutate()}
              >
                Restaurar huellas
              </Button>
            )}
          </Space>
        )}
      </div>

      <Card>
        <Row gutter={[24, 16]} align="middle">
          <Col flex="none">
            <Avatar size={88} src={empleado.foto}>
              {empleado.nombres.charAt(0)}
            </Avatar>
          </Col>
          <Col flex="auto">
            <Space orientation="vertical" size={2}>
              <Text strong style={{ fontSize: 16 }}>
                {empleado.codigo_empleado} &middot; {empleado.cargo_nombre}
              </Text>
              <Text type="secondary">
                {empleado.sede_nombre} / {empleado.departamento_nombre}
                {empleado.area_nombre ? ` / ${empleado.area_nombre}` : ''}
              </Text>
              <Space wrap style={{ marginTop: 6 }}>
                <Tag color={empleado.estado === 'activo' ? 'green' : 'default'}>
                  {empleado.estado_display}
                </Tag>
                <Tag color={empleado.tiene_huella ? 'green' : 'default'}>
                  Huella: {empleado.tiene_huella ? `${empleado.cantidad_huellas} dedo(s)` : 'no'}
                </Tag>
                <Tag color={empleado.tiene_rostro ? 'blue' : 'default'}>
                  Rostro: {empleado.tiene_rostro ? 'enrolado' : 'no'}
                </Tag>
                <Tag color={empleado.sincronizado_dispositivo ? 'green' : 'orange'}>
                  {empleado.sincronizado_dispositivo ? 'En el equipo' : 'Pendiente de sincronizar'}
                </Tag>
                {empleado.turno_actual && <Tag color="purple">{empleado.turno_actual.nombre}</Tag>}
              </Space>
            </Space>
          </Col>
        </Row>
      </Card>

      <Tabs
        defaultActiveKey="asistencia"
        items={[
          {
            key: 'asistencia',
            label: 'Asistencia',
            children: (
              <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                <Card>
                  <Space wrap>
                    <Text>Periodo:</Text>
                    <RangePicker
                      value={rango}
                      onChange={(v) => v?.[0] && v?.[1] && setRango([v[0], v[1]])}
                      allowClear={false}
                      format="DD/MM/YYYY"
                    />
                  </Space>
                </Card>

                <Row gutter={[16, 16]}>
                  <Col xs={12} md={6}>
                    <Card>
                      <Statistic
                        title="Dias puntuales"
                        value={resumen?.dias_puntuales ?? 0}
                        styles={{ content: { color: '#3f8600' } }}
                      />
                    </Card>
                  </Col>
                  <Col xs={12} md={6}>
                    <Card>
                      <Statistic
                        title="Tardanzas"
                        value={resumen?.dias_tardanza ?? 0}
                        suffix={
                          <Text type="secondary" style={{ fontSize: 13 }}>
                            ({resumen?.minutos_tardanza ?? 0} min)
                          </Text>
                        }
                        styles={{ content: { color: '#d48806' } }}
                      />
                    </Card>
                  </Col>
                  <Col xs={12} md={6}>
                    <Card>
                      <Statistic
                        title="Faltas"
                        value={resumen?.dias_falta ?? 0}
                        styles={{ content: { color: '#cf1322' } }}
                      />
                    </Card>
                  </Col>
                  <Col xs={12} md={6}>
                    <Card>
                      <Statistic
                        title="Horas trabajadas"
                        value={resumen?.horas_trabajadas ?? 0}
                        precision={1}
                      />
                    </Card>
                  </Col>
                </Row>

                <Card title="Detalle diario" styles={{ body: { padding: 0 } }}>
                  <Table<RegistroAsistencia>
                    rowKey="id"
                    size="small"
                    dataSource={registros?.results ?? []}
                    pagination={{ pageSize: 31 }}
                    scroll={{ x: 800 }}
                    columns={[
                      {
                        title: 'Fecha',
                        dataIndex: 'fecha',
                        render: (f: string) => dayjs(f).format('DD/MM/YYYY (ddd)'),
                      },
                      { title: 'Horario', dataIndex: 'horario_nombre', ellipsis: true },
                      {
                        title: 'Entrada',
                        dataIndex: 'marcacion_entrada',
                        render: (v: string | null) => (v ? dayjs(v).format('HH:mm') : '-'),
                      },
                      {
                        title: 'Salida',
                        dataIndex: 'marcacion_salida',
                        render: (v: string | null) => (v ? dayjs(v).format('HH:mm') : '-'),
                      },
                      {
                        title: 'Tardanza',
                        dataIndex: 'minutos_tardanza',
                        align: 'right',
                        render: (v: number) => (v > 0 ? <Tag color="orange">{v} min</Tag> : '-'),
                      },
                      {
                        title: 'Horas',
                        dataIndex: 'horas_trabajadas',
                        align: 'right',
                      },
                      {
                        title: 'Estado',
                        dataIndex: 'estado_display',
                        render: (texto: string, fila) => (
                          <Tag color={COLOR_ESTADO[fila.estado]}>{texto}</Tag>
                        ),
                      },
                      { title: 'Observacion', dataIndex: 'observacion', ellipsis: true },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: 'datos',
            label: 'Datos del empleado',
            children: (
              <Card>
                <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small">
                  <Descriptions.Item label="Codigo">{empleado.codigo_empleado}</Descriptions.Item>
                  <Descriptions.Item label="DNI">{empleado.dni}</Descriptions.Item>
                  <Descriptions.Item label="Nombres">{empleado.nombres}</Descriptions.Item>
                  <Descriptions.Item label="Apellidos">
                    {empleado.apellido_paterno} {empleado.apellido_materno}
                  </Descriptions.Item>
                  <Descriptions.Item label="Fecha de nacimiento">
                    {empleado.fecha_nacimiento
                      ? dayjs(empleado.fecha_nacimiento).format('DD/MM/YYYY')
                      : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Correo">{empleado.email || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Telefono">{empleado.telefono || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Direccion">
                    {empleado.direccion || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Sede">{empleado.sede_nombre}</Descriptions.Item>
                  <Descriptions.Item label="Departamento">
                    {empleado.departamento_nombre}
                  </Descriptions.Item>
                  <Descriptions.Item label="Area">{empleado.area_nombre ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="Cargo">{empleado.cargo_nombre}</Descriptions.Item>
                  <Descriptions.Item label="Fecha de ingreso">
                    {dayjs(empleado.fecha_ingreso).format('DD/MM/YYYY')}
                  </Descriptions.Item>
                  <Descriptions.Item label="Tipo de contrato">
                    {empleado.tipo_contrato_display}
                  </Descriptions.Item>
                  <Descriptions.Item label="Sueldo basico">
                    {empleado.sueldo_basico ? `S/ ${empleado.sueldo_basico}` : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Turno actual">
                    {empleado.turno_actual?.nombre ?? 'Sin turno asignado'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            ),
          },
          {
            key: 'biometria',
            label: 'Biometria',
            children: (
              <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                <Alert
                  type="info"
                  showIcon
                  title="El enrolamiento se realiza en el dispositivo"
                  description={
                    'El empleado registra su huella y su rostro directamente en el equipo ' +
                    'MB560-VL. El sistema respalda las plantillas de huella para poder ' +
                    'restaurarlas si el equipo se reemplaza. La plantilla de rostro no puede ' +
                    'extraerse del dispositivo porque el algoritmo facial de ZKTeco es ' +
                    'propietario; de ella solo se conserva el indicador de enrolamiento.'
                  }
                />

                <Row gutter={[16, 16]}>
                  <Col xs={24} md={8}>
                    <Card>
                      <Statistic
                        title="Huellas registradas"
                        value={empleado.cantidad_huellas}
                        suffix="/ 10"
                      />
                    </Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card>
                      <Statistic
                        title="Rostro"
                        value={empleado.tiene_rostro ? 'Enrolado' : 'No enrolado'}
                        styles={{ content: { color: empleado.tiene_rostro ? '#3f8600' : '#cf1322' } }}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card>
                      <Statistic
                        title="UID en el equipo"
                        value={empleado.uid_dispositivo ?? 'Sin asignar'}
                      />
                    </Card>
                  </Col>
                </Row>

                <Card title="Plantillas de huella respaldadas">
                  <Table
                    rowKey="id"
                    size="small"
                    dataSource={empleado.huellas}
                    pagination={false}
                    locale={{
                      emptyText:
                        'Sin huellas respaldadas. Use "Respaldar huellas" en la seccion Dispositivo.',
                    }}
                    columns={[
                      { title: 'Dedo', dataIndex: 'finger_id', render: (v: number) => `Dedo ${v}` },
                      { title: 'Tamano', dataIndex: 'size', render: (v: number) => `${v} bytes` },
                      { title: 'Validez', dataIndex: 'valid' },
                      {
                        title: 'Capturado',
                        dataIndex: 'capturado_en',
                        render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm'),
                      },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}
