import { useQuery } from '@tanstack/react-query';
import { Card, Col, DatePicker, Input, Row, Select, Space, Table, Tag, Typography } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';

import { auditoriaApi } from '../api/endpoints';
import type { RegistroAuditoria } from '../types';

const { Title } = Typography;
const { RangePicker } = DatePicker;

const COLOR_ACCION: Record<string, string> = {
  crear: 'green',
  actualizar: 'blue',
  eliminar: 'red',
  iniciar_sesion: 'default',
  sincronizar: 'purple',
  generar_reporte: 'cyan',
  ajuste_manual: 'orange',
  aprobar_permiso: 'geekblue',
};

export default function Auditoria() {
  const [pagina, setPagina] = useState(1);
  const [busqueda, setBusqueda] = useState('');
  const [accion, setAccion] = useState<string | undefined>();
  const [rango, setRango] = useState<[Dayjs, Dayjs] | null>(null);

  const params = {
    page: pagina,
    search: busqueda || undefined,
    accion,
    fecha_hora__gte: rango?.[0].startOf('day').toISOString(),
    fecha_hora__lte: rango?.[1].endOf('day').toISOString(),
  };

  const { data, isLoading } = useQuery({
    queryKey: ['auditoria', params],
    queryFn: () => auditoriaApi.listar(params),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={3} style={{ margin: 0 }}>
        Bitacora de Auditoria
      </Title>

      <Card>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
            <Input.Search
              allowClear
              placeholder="Buscar en la descripcion o el usuario"
              onSearch={(v) => {
                setBusqueda(v);
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={12} md={7}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="Tipo de accion"
              options={[
                { value: 'crear', label: 'Crear' },
                { value: 'actualizar', label: 'Actualizar' },
                { value: 'eliminar', label: 'Eliminar' },
                { value: 'iniciar_sesion', label: 'Iniciar sesion' },
                { value: 'sincronizar', label: 'Sincronizar dispositivo' },
                { value: 'generar_reporte', label: 'Generar reporte' },
                { value: 'ajuste_manual', label: 'Ajuste manual' },
                { value: 'aprobar_permiso', label: 'Aprobar permiso' },
              ]}
              onChange={(v) => {
                setAccion(v);
                setPagina(1);
              }}
            />
          </Col>
          <Col xs={24} md={9}>
            <RangePicker
              style={{ width: '100%' }}
              format="DD/MM/YYYY"
              onChange={(v) => {
                setRango(v?.[0] && v?.[1] ? [v[0], v[1]] : null);
                setPagina(1);
              }}
            />
          </Col>
        </Row>
      </Card>

      <Card styles={{ body: { padding: 0 } }}>
        <Table<RegistroAuditoria>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.results ?? []}
          scroll={{ x: 1000 }}
          pagination={{
            current: pagina,
            total: data?.count ?? 0,
            pageSize: 25,
            onChange: setPagina,
            showTotal: (t) => `${t} registros`,
          }}
          expandable={{
            expandedRowRender: (fila) => (
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(fila.cambios, null, 2)}
              </pre>
            ),
            rowExpandable: (fila) => !!fila.cambios,
          }}
          columns={[
            {
              title: 'Fecha y hora',
              dataIndex: 'fecha_hora',
              width: 160,
              render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm:ss'),
            },
            { title: 'Usuario', dataIndex: 'usuario_email', width: 200, ellipsis: true },
            {
              title: 'Accion',
              dataIndex: 'accion_display',
              width: 150,
              render: (texto: string, f) => (
                <Tag color={COLOR_ACCION[f.accion] ?? 'default'}>{texto}</Tag>
              ),
            },
            { title: 'Modelo', dataIndex: 'modelo', width: 130 },
            { title: 'Descripcion', dataIndex: 'descripcion', ellipsis: true },
            { title: 'IP', dataIndex: 'ip', width: 120 },
          ]}
        />
      </Card>
    </Space>
  );
}
