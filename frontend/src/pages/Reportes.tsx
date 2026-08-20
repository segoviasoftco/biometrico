import { DownloadOutlined, EyeOutlined, FilePdfOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';

import { mensajeError } from '../api/client';
import { organizacionApi, reportesApi, type SolicitudReporte } from '../api/endpoints';
import type { PrevisualizacionReporte } from '../types';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const TIPOS = [
  { valor: 'descuentos', etiqueta: 'Descuentos (para planilla)' },
  { valor: 'tardanzas', etiqueta: 'Tardanzas' },
  { valor: 'faltas', etiqueta: 'Faltas' },
  { valor: 'horas_trabajadas', etiqueta: 'Horas trabajadas' },
  { valor: 'asistencia_general', etiqueta: 'Asistencia general' },
  { valor: 'marcaciones', etiqueta: 'Marcaciones detalladas' },
];

const ATAJOS: Record<string, () => [Dayjs, Dayjs]> = {
  'Esta semana': () => [dayjs().startOf('week'), dayjs().endOf('week')],
  'Semana pasada': () => [
    dayjs().subtract(1, 'week').startOf('week'),
    dayjs().subtract(1, 'week').endOf('week'),
  ],
  'Este mes': () => [dayjs().startOf('month'), dayjs().endOf('month')],
  'Mes pasado': () => [
    dayjs().subtract(1, 'month').startOf('month'),
    dayjs().subtract(1, 'month').endOf('month'),
  ],
};

export default function Reportes() {
  const { message } = App.useApp();
  const [tipo, setTipo] = useState('descuentos');
  const [rango, setRango] = useState<[Dayjs, Dayjs]>([
    dayjs().startOf('month'),
    dayjs().endOf('month'),
  ]);
  const [sede, setSede] = useState<number | undefined>();
  const [departamento, setDepartamento] = useState<number | undefined>();
  const [vista, setVista] = useState<PrevisualizacionReporte | null>(null);

  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });
  const { data: departamentos } = useQuery({
    queryKey: ['departamentos', sede],
    queryFn: () => organizacionApi.departamentos({ page_size: 100, sede }),
  });

  const solicitud = (): SolicitudReporte => ({
    tipo,
    fecha_inicio: rango[0].format('YYYY-MM-DD'),
    fecha_fin: rango[1].format('YYYY-MM-DD'),
    sede: sede ?? null,
    departamento: departamento ?? null,
  });

  const previsualizar = useMutation({
    mutationFn: () => reportesApi.previsualizar(solicitud()),
    onSuccess: setVista,
    onError: (e) => message.error(mensajeError(e, 'No se pudo generar la vista previa.')),
  });

  const descargar = useMutation({
    mutationFn: async (formato: 'excel' | 'pdf') => {
      const respuesta = await reportesApi.generar({ ...solicitud(), formato, guardar: true });
      const extension = formato === 'excel' ? 'xlsx' : 'pdf';
      const nombre = `${tipo}_${solicitud().fecha_inicio}_${solicitud().fecha_fin}.${extension}`;

      // El navegador recibe un blob; se fuerza la descarga con un enlace temporal.
      const url = URL.createObjectURL(new Blob([respuesta.data]));
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = nombre;
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      URL.revokeObjectURL(url);
    },
    onSuccess: () => message.success('Reporte descargado.'),
    onError: (e) => message.error(mensajeError(e, 'No se pudo generar el reporte.')),
  });

  const columnasTabla = (vista?.columnas ?? []).map((c) => ({
    title: c.etiqueta,
    dataIndex: c.clave,
    key: c.clave,
    ellipsis: true,
    render: (valor: unknown) => {
      if (valor === null || valor === undefined || valor === '') return '-';
      return String(valor);
    },
  }));

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={3} style={{ margin: 0 }}>
        Reportes
      </Title>

      <Card>
        <Row gutter={[12, 12]} align="bottom">
          <Col xs={24} md={7}>
            <Text type="secondary">Tipo de reporte</Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              value={tipo}
              onChange={(v) => {
                setTipo(v);
                setVista(null);
              }}
              options={TIPOS.map((t) => ({ value: t.valor, label: t.etiqueta }))}
            />
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">Periodo</Text>
            <RangePicker
              style={{ width: '100%', marginTop: 4 }}
              value={rango}
              onChange={(v) => v?.[0] && v?.[1] && setRango([v[0], v[1]])}
              allowClear={false}
              format="DD/MM/YYYY"
              presets={Object.entries(ATAJOS).map(([label, fn]) => ({ label, value: fn() }))}
            />
          </Col>
          <Col xs={12} md={4}>
            <Text type="secondary">Sede</Text>
            <Select
              allowClear
              style={{ width: '100%', marginTop: 4 }}
              placeholder="Todas"
              value={sede}
              onChange={(v) => {
                setSede(v);
                setDepartamento(undefined);
              }}
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Col>
          <Col xs={12} md={5}>
            <Text type="secondary">Departamento</Text>
            <Select
              allowClear
              style={{ width: '100%', marginTop: 4 }}
              placeholder="Todos"
              value={departamento}
              onChange={setDepartamento}
              options={departamentos?.results.map((d) => ({ value: d.id, label: d.nombre }))}
            />
          </Col>
        </Row>

        <Space style={{ marginTop: 16 }} wrap>
          <Button
            type="primary"
            icon={<EyeOutlined />}
            loading={previsualizar.isPending}
            onClick={() => previsualizar.mutate()}
          >
            Previsualizar
          </Button>
          <Button
            icon={<DownloadOutlined />}
            loading={descargar.isPending && descargar.variables === 'excel'}
            onClick={() => descargar.mutate('excel')}
          >
            Descargar Excel
          </Button>
          <Button
            icon={<FilePdfOutlined />}
            loading={descargar.isPending && descargar.variables === 'pdf'}
            onClick={() => descargar.mutate('pdf')}
          >
            Descargar PDF
          </Button>
        </Space>
      </Card>

      {tipo === 'descuentos' && (
        <Alert
          type="info"
          showIcon
          title="Reporte de descuentos"
          description={
            'Consolida los minutos de tardanza, la salida anticipada y los dias de falta ' +
            'injustificada de cada empleado. Los dias con permiso con goce de haber no se ' +
            'descuentan. El monto se calcula con el valor configurado del minuto o, en su ' +
            'defecto, a partir del sueldo basico registrado en la ficha del empleado.'
          }
        />
      )}

      {vista && (
        <Card
          title={vista.titulo}
          extra={<Tag color="blue">{vista.total_registros} registros</Tag>}
          styles={{ body: { padding: 0 } }}
        >
          {vista.filas.length === 0 ? (
            <Empty
              style={{ padding: 40 }}
              description="No hay datos para los filtros seleccionados"
            />
          ) : (
            <Table
              rowKey={(_, indice) => String(indice)}
              size="small"
              dataSource={vista.filas}
              columns={columnasTabla}
              scroll={{ x: 'max-content' }}
              pagination={{ pageSize: 25, showTotal: (t) => `${t} filas` }}
              summary={() =>
                Object.keys(vista.totales).length ? (
                  <Table.Summary fixed>
                    <Table.Summary.Row>
                      {vista.columnas.map((c, indice) => (
                        <Table.Summary.Cell key={c.clave} index={indice}>
                          {indice === 0 ? (
                            <Text strong>TOTALES</Text>
                          ) : c.clave in vista.totales ? (
                            <Text strong>{vista.totales[c.clave]}</Text>
                          ) : null}
                        </Table.Summary.Cell>
                      ))}
                    </Table.Summary.Row>
                  </Table.Summary>
                ) : null
              }
            />
          )}
          {vista.nota && (
            <div style={{ padding: 12, borderTop: '1px solid #f0f0f0' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {vista.nota}
              </Text>
            </div>
          )}
        </Card>
      )}
    </Space>
  );
}
