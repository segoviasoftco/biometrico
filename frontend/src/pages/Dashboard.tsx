import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Card,
  Col,
  DatePicker,
  Divider,
  Progress,
  Radio,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { dashboardApi } from '../api/endpoints';
import type { ComparativoDepartamento, FilaRanking } from '../types';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

export default function Dashboard() {
  const [fecha, setFecha] = useState<Dayjs>(dayjs());
  const [rango, setRango] = useState<[Dayjs, Dayjs]>([dayjs().subtract(3, 'month'), dayjs()]);
  const [granularidad, setGranularidad] = useState<'semanal' | 'mensual'>('semanal');

  const paramsRango = {
    fecha_inicio: rango[0].format('YYYY-MM-DD'),
    fecha_fin: rango[1].format('YYYY-MM-DD'),
  };

  const { data: resumen, isLoading: cargandoResumen } = useQuery({
    queryKey: ['resumen-dia', fecha.format('YYYY-MM-DD')],
    queryFn: () => dashboardApi.resumenDia({ fecha: fecha.format('YYYY-MM-DD') }),
  });

  const { data: tendencia = [] } = useQuery({
    queryKey: ['tendencia', granularidad, paramsRango],
    queryFn: () =>
      granularidad === 'semanal'
        ? dashboardApi.tendenciaSemanal(paramsRango)
        : dashboardApi.tendenciaMensual(paramsRango),
  });

  const { data: ranking } = useQuery({
    queryKey: ['ranking', paramsRango],
    queryFn: () => dashboardApi.ranking(paramsRango),
  });

  const { data: comparativo = [] } = useQuery({
    queryKey: ['comparativo', paramsRango],
    queryFn: () => dashboardApi.comparativoDepartamento(paramsRango),
  });

  const { data: estado } = useQuery({
    queryKey: ['estado-sistema'],
    queryFn: dashboardApi.estadoSistema,
    refetchInterval: 60_000,
  });

  const datosGrafico = tendencia.map((punto) => ({
    ...punto,
    etiqueta:
      granularidad === 'semanal'
        ? dayjs(punto.periodo).format('DD MMM')
        : dayjs(punto.periodo).format('MMM YYYY'),
  }));

  const dispositivoCaido = estado?.dispositivos.some((d) => d.estado !== 'conectado');

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          Dashboard de Asistencia
        </Title>
        <Space wrap>
          <DatePicker
            value={fecha}
            onChange={(v) => v && setFecha(v)}
            allowClear={false}
            format="DD/MM/YYYY"
          />
          <RangePicker
            value={rango}
            onChange={(v) => v?.[0] && v?.[1] && setRango([v[0], v[1]])}
            allowClear={false}
            format="DD/MM/YYYY"
          />
        </Space>
      </div>

      {/* Avisos que exigen accion: sin equipo no entran marcaciones nuevas. */}
      {dispositivoCaido && (
        <Alert
          type="warning"
          showIcon
          icon={<AlertOutlined />}
          title="El dispositivo biometrico no esta conectado"
          description="Mientras el equipo no responda no ingresan marcaciones nuevas. Revise la seccion Dispositivo."
        />
      )}
      {estado && estado.sin_biometria > 0 && (
        <Alert
          type="info"
          showIcon
          title={`${estado.sin_biometria} empleado(s) activos sin huella ni rostro enrolado`}
          description="Estos empleados deben registrar su biometria en el equipo para poder marcar."
        />
      )}

      {/* --- Indicadores del dia --- */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={cargandoResumen}>
            <Statistic
              title="Puntuales"
              value={resumen?.puntuales ?? 0}
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#3f8600' } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={cargandoResumen}>
            <Statistic
              title="Tardanzas"
              value={resumen?.tardanzas ?? 0}
              prefix={<ClockCircleOutlined />}
              styles={{ content: { color: '#d48806' } }}
              suffix={
                <Text type="secondary" style={{ fontSize: 13 }}>
                  ({resumen?.minutos_tardanza ?? 0} min)
                </Text>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={cargandoResumen}>
            <Statistic
              title="Faltas"
              value={resumen?.faltas ?? 0}
              prefix={<CloseCircleOutlined />}
              styles={{ content: { color: '#cf1322' } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={cargandoResumen}>
            <Statistic
              title="Empleados activos"
              value={resumen?.total_empleados_activos ?? 0}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title={`Asistencia del ${fecha.format('DD/MM/YYYY')}`}>
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="dashboard"
                percent={resumen?.porcentaje_asistencia ?? 0}
                strokeColor={
                  (resumen?.porcentaje_asistencia ?? 0) >= 90
                    ? '#52c41a'
                    : (resumen?.porcentaje_asistencia ?? 0) >= 75
                      ? '#faad14'
                      : '#f5222d'
                }
              />
              <div style={{ marginTop: 12 }}>
                <Text type="secondary">
                  {resumen?.asistieron ?? 0} de {resumen?.esperados ?? 0} esperados
                </Text>
              </div>
            </div>
            <Divider style={{ margin: '16px 0' }} />
            <Space orientation="vertical" style={{ width: '100%' }} size={4}>
              <FilaResumen etiqueta="Permisos / vacaciones" valor={resumen?.permisos ?? 0} />
              <FilaResumen etiqueta="Faltas justificadas" valor={resumen?.justificadas ?? 0} />
              <FilaResumen etiqueta="Marcacion incompleta" valor={resumen?.incompletos ?? 0} />
              <FilaResumen etiqueta="Descanso / feriado" valor={resumen?.descansos ?? 0} />
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Card
            title="Tendencia de faltas y tardanzas"
            extra={
              <Radio.Group
                size="small"
                value={granularidad}
                onChange={(e) => setGranularidad(e.target.value)}
              >
                <Radio.Button value="semanal">Semanal</Radio.Button>
                <Radio.Button value="mensual">Mensual</Radio.Button>
              </Radio.Group>
            }
          >
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={datosGrafico}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="etiqueta" fontSize={12} />
                <YAxis fontSize={12} allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="faltas"
                  name="Faltas"
                  stroke="#cf1322"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="tardanzas"
                  name="Tardanzas"
                  stroke="#d48806"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="puntuales"
                  name="Puntuales"
                  stroke="#52c41a"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* --- Rankings --- */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Empleados con mas tardanzas del periodo">
            <Table<FilaRanking>
              size="small"
              rowKey="empleado_id"
              dataSource={ranking?.tardanzas ?? []}
              pagination={false}
              locale={{ emptyText: 'Sin tardanzas en el periodo' }}
              columns={[
                { title: 'Codigo', dataIndex: 'codigo', width: 90 },
                { title: 'Empleado', dataIndex: 'nombre', ellipsis: true },
                { title: 'Departamento', dataIndex: 'departamento', ellipsis: true },
                { title: 'Dias', dataIndex: 'dias', width: 70, align: 'right' },
                {
                  title: 'Minutos',
                  dataIndex: 'minutos',
                  width: 90,
                  align: 'right',
                  render: (v: number) => <Tag color="orange">{v}</Tag>,
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Empleados con mas faltas del periodo">
            <Table<FilaRanking>
              size="small"
              rowKey="empleado_id"
              dataSource={ranking?.faltas ?? []}
              pagination={false}
              locale={{ emptyText: 'Sin faltas en el periodo' }}
              columns={[
                { title: 'Codigo', dataIndex: 'codigo', width: 90 },
                { title: 'Empleado', dataIndex: 'nombre', ellipsis: true },
                { title: 'Departamento', dataIndex: 'departamento', ellipsis: true },
                {
                  title: 'Faltas',
                  dataIndex: 'dias',
                  width: 80,
                  align: 'right',
                  render: (v: number) => <Tag color="red">{v}</Tag>,
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card title="Comparativo por departamento">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={comparativo}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="departamento" fontSize={12} />
            <YAxis fontSize={12} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar dataKey="puntuales" name="Puntuales" fill="#52c41a" />
            <Bar dataKey="tardanzas" name="Tardanzas" fill="#faad14" />
            <Bar dataKey="faltas" name="Faltas" fill="#f5222d" />
          </BarChart>
        </ResponsiveContainer>

        <Table<ComparativoDepartamento>
          size="small"
          rowKey="departamento_id"
          dataSource={comparativo}
          pagination={false}
          style={{ marginTop: 16 }}
          columns={[
            { title: 'Departamento', dataIndex: 'departamento' },
            { title: 'Sede', dataIndex: 'sede' },
            { title: 'Puntuales', dataIndex: 'puntuales', align: 'right' },
            { title: 'Tardanzas', dataIndex: 'tardanzas', align: 'right' },
            { title: 'Faltas', dataIndex: 'faltas', align: 'right' },
            {
              title: 'Min. tardanza',
              dataIndex: 'minutos_tardanza',
              align: 'right',
            },
            {
              title: '% Asistencia',
              dataIndex: 'porcentaje_asistencia',
              align: 'right',
              render: (v: number) => (
                <Tag color={v >= 90 ? 'green' : v >= 75 ? 'orange' : 'red'}>{v}%</Tag>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}

function FilaResumen({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <Text type="secondary">{etiqueta}</Text>
      <Text strong>{valor}</Text>
    </div>
  );
}
