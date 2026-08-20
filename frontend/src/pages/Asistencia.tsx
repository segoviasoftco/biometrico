import { EditOutlined, SyncOutlined } from '@ant-design/icons';
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
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';

import { mensajeError } from '../api/client';
import { asistenciaApi, organizacionApi } from '../api/endpoints';
import { puedeEditar, useAuth } from '../store/auth';
import type { Marcacion, RegistroAsistencia } from '../types';
import { COLOR_ESTADO, ETIQUETAS_ESTADO } from './asistencia/estados';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

export default function Asistencia() {
  const { usuario } = useAuth();
  const editable = puedeEditar(usuario);
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [formAjuste] = Form.useForm();

  const [rango, setRango] = useState<[Dayjs, Dayjs]>([
    dayjs().startOf('month'),
    dayjs(),
  ]);
  const [filtros, setFiltros] = useState<Record<string, unknown>>({});
  const [pagina, setPagina] = useState(1);
  const [ajustando, setAjustando] = useState<RegistroAsistencia | null>(null);

  const paramsBase = {
    fecha__gte: rango[0].format('YYYY-MM-DD'),
    fecha__lte: rango[1].format('YYYY-MM-DD'),
    ...filtros,
  };

  const { data: registros, isLoading } = useQuery({
    queryKey: ['registros-asistencia', paramsBase, pagina],
    queryFn: () => asistenciaApi.registros({ ...paramsBase, page: pagina }),
  });

  const { data: marcaciones } = useQuery({
    queryKey: ['marcaciones', rango, filtros],
    queryFn: () =>
      asistenciaApi.marcaciones({
        fecha_hora__gte: rango[0].startOf('day').toISOString(),
        fecha_hora__lte: rango[1].endOf('day').toISOString(),
        page_size: 50,
      }),
  });

  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });

  const procesar = useMutation({
    mutationFn: () =>
      asistenciaApi.procesar({
        fecha_inicio: rango[0].format('YYYY-MM-DD'),
        fecha_fin: rango[1].format('YYYY-MM-DD'),
      }),
    onSuccess: (r) => {
      message.success(r.detalle ?? 'Asistencia procesada.');
      queryClient.invalidateQueries({ queryKey: ['registros-asistencia'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const ajustar = useMutation({
    mutationFn: (valores: Record<string, unknown>) =>
      asistenciaApi.ajustar(ajustando!.id, valores as never),
    onSuccess: () => {
      message.success('Registro ajustado. El cambio quedo en la auditoria.');
      setAjustando(null);
      formAjuste.resetFields();
      queryClient.invalidateQueries({ queryKey: ['registros-asistencia'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const confirmarProceso = () => {
    modal.confirm({
      title: 'Recalcular la asistencia del periodo?',
      content:
        `Se volveran a evaluar las marcaciones del ${rango[0].format('DD/MM/YYYY')} al ` +
        `${rango[1].format('DD/MM/YYYY')} contra los horarios vigentes. Los registros ` +
        'ajustados manualmente se conservan.',
      okText: 'Recalcular',
      cancelText: 'Cancelar',
      onOk: () => procesar.mutateAsync(),
    });
  };

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          Asistencia
        </Title>
        {editable && (
          <Button
            type="primary"
            icon={<SyncOutlined />}
            loading={procesar.isPending}
            onClick={confirmarProceso}
          >
            Recalcular periodo
          </Button>
        )}
      </div>

      <Card>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={8}>
            <RangePicker
              style={{ width: '100%' }}
              value={rango}
              onChange={(v) => {
                if (v?.[0] && v?.[1]) {
                  setRango([v[0], v[1]]);
                  setPagina(1);
                }
              }}
              allowClear={false}
              format="DD/MM/YYYY"
            />
          </Col>
          <Col xs={12} md={5}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Sede"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
              onChange={(v) => {
                setFiltros((f) => ({ ...f, empleado__sede: v }));
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={5}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Estado"
              options={ETIQUETAS_ESTADO}
              onChange={(v) => {
                setFiltros((f) => ({ ...f, estado: v }));
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={6}>
            <Input.Search
              allowClear
              placeholder="Buscar empleado"
              onSearch={(v) => {
                setFiltros((f) => ({ ...f, search: v || undefined }));
                setPagina(1);
              }}
            />
          </Col>
        </Row>
      </Card>

      <Tabs
        defaultActiveKey="registros"
        items={[
          {
            key: 'registros',
            label: 'Registros diarios',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table<RegistroAsistencia>
                  rowKey="id"
                  loading={isLoading}
                  dataSource={registros?.results ?? []}
                  scroll={{ x: 1200 }}
                  pagination={{
                    current: pagina,
                    total: registros?.count ?? 0,
                    pageSize: 25,
                    onChange: setPagina,
                    showTotal: (t) => `${t} registros`,
                  }}
                  columns={[
                    {
                      title: 'Fecha',
                      dataIndex: 'fecha',
                      width: 120,
                      render: (f: string) => dayjs(f).format('DD/MM/YYYY'),
                    },
                    { title: 'Codigo', dataIndex: 'empleado_codigo', width: 90 },
                    { title: 'Empleado', dataIndex: 'empleado_nombre', ellipsis: true },
                    { title: 'Departamento', dataIndex: 'departamento_nombre', ellipsis: true },
                    {
                      title: 'Programado',
                      key: 'programado',
                      width: 130,
                      render: (_, f) =>
                        f.hora_entrada_programada
                          ? `${f.hora_entrada_programada.slice(0, 5)} - ${f.hora_salida_programada?.slice(0, 5)}`
                          : '-',
                    },
                    {
                      title: 'Entrada',
                      dataIndex: 'marcacion_entrada',
                      width: 90,
                      render: (v: string | null) => (v ? dayjs(v).format('HH:mm') : '-'),
                    },
                    {
                      title: 'Salida',
                      dataIndex: 'marcacion_salida',
                      width: 90,
                      render: (v: string | null) => (v ? dayjs(v).format('HH:mm') : '-'),
                    },
                    {
                      title: 'Tardanza',
                      dataIndex: 'minutos_tardanza',
                      width: 100,
                      align: 'right',
                      render: (v: number) => (v > 0 ? <Tag color="orange">{v} min</Tag> : '-'),
                    },
                    {
                      title: 'Horas',
                      dataIndex: 'horas_trabajadas',
                      width: 80,
                      align: 'right',
                    },
                    {
                      title: 'Estado',
                      dataIndex: 'estado_display',
                      width: 150,
                      render: (texto: string, fila) => (
                        <Space size={4}>
                          <Tag color={COLOR_ESTADO[fila.estado]}>{texto}</Tag>
                          {fila.ajustado_manualmente && <Tag color="purple">Ajustado</Tag>}
                        </Space>
                      ),
                    },
                    ...(editable
                      ? [
                          {
                            title: '',
                            key: 'acciones',
                            fixed: 'right' as const,
                            width: 60,
                            render: (_: unknown, fila: RegistroAsistencia) => (
                              <Button
                                size="small"
                                icon={<EditOutlined />}
                                onClick={() => {
                                  setAjustando(fila);
                                  formAjuste.setFieldsValue({
                                    estado: fila.estado,
                                    minutos_tardanza: fila.minutos_tardanza,
                                    es_descontable: fila.es_descontable,
                                  });
                                }}
                              />
                            ),
                          },
                        ]
                      : []),
                  ]}
                />
              </Card>
            ),
          },
          {
            key: 'marcaciones',
            label: 'Marcaciones del equipo',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table<Marcacion>
                  rowKey="id"
                  dataSource={marcaciones?.results ?? []}
                  scroll={{ x: 900 }}
                  pagination={{ pageSize: 25, showTotal: (t) => `${t} marcaciones` }}
                  columns={[
                    {
                      title: 'Fecha y hora',
                      dataIndex: 'fecha_hora',
                      render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm:ss'),
                    },
                    { title: 'Codigo', dataIndex: 'empleado_codigo', width: 90 },
                    { title: 'Empleado', dataIndex: 'empleado_nombre', ellipsis: true },
                    {
                      title: 'Verificacion',
                      dataIndex: 'tipo_verificacion_display',
                      render: (texto: string, fila) => (
                        <Tag color={fila.tipo_verificacion === 15 ? 'blue' : 'green'}>{texto}</Tag>
                      ),
                    },
                    { title: 'Tipo', dataIndex: 'tipo_marcacion_display' },
                    {
                      title: 'Origen',
                      dataIndex: 'origen',
                      render: (v: string) =>
                        v === 'manual' ? (
                          <Tag color="purple">Manual</Tag>
                        ) : (
                          <Tag>Dispositivo</Tag>
                        ),
                    },
                    { title: 'Observacion', dataIndex: 'observacion', ellipsis: true },
                  ]}
                />
              </Card>
            ),
          },
        ]}
      />

      <Modal
        open={ajustando !== null}
        title="Ajustar registro de asistencia"
        onCancel={() => setAjustando(null)}
        onOk={() => formAjuste.submit()}
        confirmLoading={ajustar.isPending}
        okText="Guardar ajuste"
        cancelText="Cancelar"
      >
        {ajustando && (
          <>
            <Text type="secondary">
              {ajustando.empleado_nombre} &middot; {dayjs(ajustando.fecha).format('DD/MM/YYYY')}
            </Text>
            <Form
              form={formAjuste}
              layout="vertical"
              style={{ marginTop: 16 }}
              onFinish={(v) => ajustar.mutate(v)}
            >
              <Form.Item name="estado" label="Estado" rules={[{ required: true }]}>
                <Select options={ETIQUETAS_ESTADO} />
              </Form.Item>
              <Form.Item name="minutos_tardanza" label="Minutos de tardanza">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="es_descontable"
                label="Afecta el descuento de planilla"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="observacion"
                label="Sustento del ajuste"
                tooltip="Queda registrado en la auditoria junto con su usuario."
                rules={[{ required: true, message: 'El sustento es obligatorio.' }]}
              >
                <Input.TextArea rows={3} placeholder="Motivo por el que se corrige este dia" />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </Space>
  );
}
