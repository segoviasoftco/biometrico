import {
  ApiOutlined,
  CloudDownloadOutlined,
  CloudUploadOutlined,
  ClockCircleOutlined,
  FieldTimeOutlined,
  ReloadOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Empty,
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
import { dispositivosApi } from '../api/endpoints';
import { esAdministrador, puedeEditar, useAuth } from '../store/auth';
import type {
  ComandoDispositivo,
  Dispositivo as TipoDispositivo,
  PeticionADMS,
  RegistroSincronizacion,
} from '../types';

const { Title, Text, Paragraph } = Typography;

const COLOR_ESTADO_SYNC: Record<string, string> = {
  exitoso: 'success',
  fallido: 'error',
  parcial: 'warning',
  en_proceso: 'processing',
};

const COLOR_ESTADO_COMANDO: Record<string, string> = {
  pendiente: 'default',
  enviado: 'processing',
  confirmado: 'success',
  fallido: 'error',
};

export default function Dispositivo() {
  const { usuario } = useAuth();
  const editable = puedeEditar(usuario);
  const admin = esAdministrador(usuario);
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [formConfig] = Form.useForm();

  const [configAbierta, setConfigAbierta] = useState(false);
  const [desde, setDesde] = useState<Dayjs | null>(null);

  const { data: dispositivos, isLoading } = useQuery({
    queryKey: ['dispositivos'],
    queryFn: dispositivosApi.listar,
  });

  const equipo: TipoDispositivo | undefined = dispositivos?.results[0];
  const modoADMS = equipo?.modo === 'adms';

  const { data: sincronizaciones } = useQuery({
    queryKey: ['sincronizaciones'],
    queryFn: () => dispositivosApi.sincronizaciones({ page_size: 20 }),
    refetchInterval: 30_000,
  });

  const { data: comandos } = useQuery({
    queryKey: ['comandos-dispositivo', equipo?.id],
    queryFn: () => dispositivosApi.comandos({ dispositivo: equipo?.id, page_size: 20 }),
    enabled: !!equipo && modoADMS,
    refetchInterval: 15_000,
  });

  const { data: peticionesADMS } = useQuery({
    queryKey: ['peticiones-adms', equipo?.id],
    queryFn: () => dispositivosApi.peticionesADMS({ dispositivo: equipo?.id, page_size: 30 }),
    enabled: !!equipo && admin && modoADMS,
    refetchInterval: 15_000,
  });

  const invalidar = () => {
    queryClient.invalidateQueries({ queryKey: ['dispositivos'] });
    queryClient.invalidateQueries({ queryKey: ['sincronizaciones'] });
    queryClient.invalidateQueries({ queryKey: ['comandos-dispositivo'] });
    queryClient.invalidateQueries({ queryKey: ['peticiones-adms'] });
  };

  /**
   * Construye la mutacion de una operacion contra el equipo. Todas comparten el
   * mismo manejo de exito y error, que es lo unico que las diferencia del resto.
   */
  const useAccionEquipo = (
    fn: (id: number) => Promise<unknown>,
    exito: string,
    invalidarEmpleados = false,
  ) =>
    useMutation({
      mutationFn: () => fn(equipo!.id),
      onSuccess: (r: unknown) => {
        const detalle = (r as { detalle?: string })?.detalle;
        message.success(detalle ?? exito);
        invalidar();
        if (invalidarEmpleados) queryClient.invalidateQueries({ queryKey: ['empleados'] });
      },
      onError: (e) => message.error(mensajeError(e)),
    });

  const probar = useAccionEquipo(dispositivosApi.probarConexion, 'Conexion establecida.');
  const sincronizarHora = useAccionEquipo(dispositivosApi.sincronizarHora, 'Hora sincronizada.');
  const subirEmpleados = useAccionEquipo(
    (id) => dispositivosApi.subirEmpleados(id, true),
    'Empleados sincronizados.',
    true,
  );
  const respaldarHuellas = useAccionEquipo(
    dispositivosApi.respaldarHuellas,
    'Huellas respaldadas.',
    true,
  );

  const descargar = useMutation({
    mutationFn: () =>
      dispositivosApi.descargarMarcaciones(equipo!.id, {
        desde: desde ? desde.format('YYYY-MM-DD') : undefined,
        procesar: true,
      }),
    onSuccess: (r) => {
      message.success(r.detalle ?? 'Marcaciones descargadas.');
      invalidar();
      queryClient.invalidateQueries({ queryKey: ['registros-asistencia'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const guardarConfig = useMutation({
    mutationFn: (valores: Partial<TipoDispositivo>) =>
      dispositivosApi.actualizar(equipo!.id, valores),
    onSuccess: () => {
      message.success('Configuracion actualizada.');
      setConfigAbierta(false);
      invalidar();
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const cancelarComando = useMutation({
    mutationFn: (id: number) => dispositivosApi.cancelarComando(id),
    onSuccess: () => {
      message.success('Comando cancelado.');
      queryClient.invalidateQueries({ queryKey: ['comandos-dispositivo'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const reintentarFallidos = useMutation({
    mutationFn: () => dispositivosApi.reintentarComandosFallidos(equipo?.id),
    onSuccess: (r) => {
      message.success(r.detalle ?? 'Comandos reencolados.');
      queryClient.invalidateQueries({ queryKey: ['comandos-dispositivo'] });
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  const confirmarLimpieza = () => {
    modal.confirm({
      title: 'Borrar las marcaciones almacenadas en el equipo?',
      okText: 'Si, borrar del equipo',
      okButtonProps: { danger: true },
      cancelText: 'Cancelar',
      content: (
        <>
          <Paragraph>
            Esta operacion es <b>irreversible</b>: borra del dispositivo todas las marcaciones
            que tiene guardadas.
          </Paragraph>
          <Paragraph type="secondary">
            Ejecutela solo despues de confirmar que las marcaciones ya fueron descargadas al
            sistema. Las que estan en la base de datos no se ven afectadas.
          </Paragraph>
        </>
      ),
      onOk: async () => {
        try {
          await dispositivosApi.limpiarMarcaciones(equipo!.id);
          message.success('Se borraron las marcaciones del equipo.');
          invalidar();
        } catch (e) {
          message.error(mensajeError(e));
        }
      },
    });
  };

  if (isLoading) return <Card loading />;
  if (!equipo) {
    return (
      <Empty description="No hay un dispositivo configurado. Ejecute el comando de inicializacion en el backend." />
    );
  }

  const conectado = equipo.estado === 'conectado';

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          Dispositivo Biometrico
        </Title>
        {admin && (
          <Button
            onClick={() => {
              formConfig.setFieldsValue(equipo);
              setConfigAbierta(true);
            }}
          >
            Configurar
          </Button>
        )}
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <Badge status={conectado ? 'success' : 'error'} />
                {equipo.nombre}
              </Space>
            }
            extra={
              <Space>
                <Tag color={modoADMS ? 'purple' : 'blue'}>{equipo.modo_display}</Tag>
                <Tag color={conectado ? 'green' : 'red'}>{equipo.estado_display}</Tag>
              </Space>
            }
          >
            <Descriptions column={{ xs: 1, sm: 2 }} size="small" bordered>
              <Descriptions.Item label="Direccion IP">
                {equipo.ip}:{equipo.puerto}
              </Descriptions.Item>
              <Descriptions.Item label="Modelo">{equipo.modelo || '-'}</Descriptions.Item>
              <Descriptions.Item label="Numero de serie">
                {equipo.numero_serie || (
                  <Text type="danger">Sin registrar (obligatorio para ADMS)</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Firmware">
                {equipo.version_firmware || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Algoritmo facial">
                {equipo.version_rostro || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Algoritmo de huella">
                {equipo.version_huella || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Admin del equipo">
                <Tag color="gold">{equipo.admin_user_id}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Ubicacion">{equipo.ubicacion || '-'}</Descriptions.Item>
              <Descriptions.Item label="Ultima conexion">
                {equipo.ultima_conexion
                  ? dayjs(equipo.ultima_conexion).format('DD/MM/YYYY HH:mm')
                  : 'Nunca'}
              </Descriptions.Item>
              <Descriptions.Item label="Ultima descarga">
                {equipo.ultima_sincronizacion_marcaciones
                  ? dayjs(equipo.ultima_sincronizacion_marcaciones).format('DD/MM/YYYY HH:mm')
                  : 'Nunca'}
              </Descriptions.Item>
              {modoADMS && (
                <>
                  <Descriptions.Item label="Ultimo contacto ADMS">
                    {equipo.ultima_conexion_adms
                      ? dayjs(equipo.ultima_conexion_adms).format('DD/MM/YYYY HH:mm:ss')
                      : 'El equipo aun no se ha conectado'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Comandos pendientes">
                    <Tag color={equipo.comandos_pendientes > 0 ? 'orange' : 'default'}>
                      {equipo.comandos_pendientes}
                    </Tag>
                  </Descriptions.Item>
                </>
              )}
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="Operaciones">
            <Space orientation="vertical" style={{ width: '100%' }} size="middle">
              {!modoADMS && (
                <Button
                  block
                  icon={<ApiOutlined />}
                  loading={probar.isPending}
                  onClick={() => probar.mutate()}
                >
                  Probar conexion
                </Button>
              )}

              {editable && (
                <>
                  <Button
                    block
                    icon={<CloudUploadOutlined />}
                    loading={subirEmpleados.isPending}
                    onClick={() => subirEmpleados.mutate()}
                  >
                    {modoADMS ? 'Encolar empleados pendientes' : 'Subir empleados pendientes'}
                  </Button>

                  <Button
                    block
                    icon={<SafetyOutlined />}
                    loading={respaldarHuellas.isPending}
                    onClick={() => respaldarHuellas.mutate()}
                  >
                    {modoADMS ? 'Solicitar reenvio de huellas' : 'Respaldar huellas del equipo'}
                  </Button>

                  <div>
                    <Space.Compact style={{ width: '100%' }}>
                      <DatePicker
                        style={{ width: '55%' }}
                        placeholder="Desde (opcional)"
                        value={desde}
                        onChange={setDesde}
                        format="DD/MM/YYYY"
                        disabled={modoADMS}
                      />
                      <Button
                        type="primary"
                        style={{ width: '45%' }}
                        icon={<CloudDownloadOutlined />}
                        loading={descargar.isPending}
                        onClick={() => descargar.mutate()}
                      >
                        {modoADMS ? 'Solicitar reenvio' : 'Descargar'}
                      </Button>
                    </Space.Compact>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {modoADMS
                        ? 'En ADMS las marcaciones llegan solas cada vez que el equipo consulta al servidor.'
                        : 'Sin fecha descarga desde la ultima sincronizacion. Repetir un rango no duplica marcaciones.'}
                    </Text>
                  </div>

                  {!modoADMS && (
                    <Button
                      block
                      icon={<FieldTimeOutlined />}
                      loading={sincronizarHora.isPending}
                      onClick={() => sincronizarHora.mutate()}
                    >
                      Sincronizar hora del equipo
                    </Button>
                  )}
                </>
              )}

              {admin && !modoADMS && (
                <Button block danger icon={<ClockCircleOutlined />} onClick={confirmarLimpieza}>
                  Limpiar marcaciones del equipo
                </Button>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      {modoADMS && equipo.numero_serie && !equipo.ultima_conexion_adms && (
        <Alert
          type="warning"
          showIcon
          title="El equipo aun no se ha conectado por ADMS"
          description={
            <>
              Verifique en el menu del equipo (Comunicacion / Servidor en la nube) que la
              direccion del servidor apunte a esta maquina y que ADMS este habilitado. El
              equipo debe enviar sus datos a la ruta <code>/iclock/cdata</code>. Revise la
              pestana &quot;Peticiones ADMS&quot; para ver si algo esta llegando y por que se
              rechaza.
            </>
          }
        />
      )}

      <Alert
        type="info"
        showIcon
        title="Sobre el enrolamiento de rostro y huella"
        description={
          'El registro biometrico se realiza en el propio equipo MB560-VL. Este sistema sube ' +
          'los datos del empleado al dispositivo, descarga las marcaciones y respalda las ' +
          'plantillas de huella para poder restaurarlas si el equipo se reemplaza o se resetea. ' +
          'La plantilla de rostro permanece unicamente en el dispositivo, porque el algoritmo ' +
          'facial de ZKTeco es propietario y no se expone por el protocolo de comunicacion.'
        }
      />

      <Tabs
        defaultActiveKey="sincronizaciones"
        items={[
          {
            key: 'sincronizaciones',
            label: 'Historial de sincronizaciones',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table<RegistroSincronizacion>
                  rowKey="id"
                  size="small"
                  dataSource={sincronizaciones?.results ?? []}
                  scroll={{ x: 900 }}
                  pagination={{ pageSize: 10 }}
                  expandable={{
                    expandedRowRender: (fila) => (
                      <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(fila.detalle, null, 2)}
                      </pre>
                    ),
                    rowExpandable: (fila) => !!fila.detalle,
                  }}
                  columns={[
                    {
                      title: 'Inicio',
                      dataIndex: 'inicio',
                      width: 150,
                      render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm:ss'),
                    },
                    { title: 'Operacion', dataIndex: 'operacion_display' },
                    {
                      title: 'Estado',
                      dataIndex: 'estado_display',
                      width: 110,
                      render: (texto: string, fila) => (
                        <Badge status={COLOR_ESTADO_SYNC[fila.estado] as never} text={texto} />
                      ),
                    },
                    {
                      title: 'Procesados',
                      dataIndex: 'registros_procesados',
                      width: 100,
                      align: 'right',
                    },
                    { title: 'Nuevos', dataIndex: 'registros_nuevos', width: 80, align: 'right' },
                    {
                      title: 'Fallidos',
                      dataIndex: 'registros_fallidos',
                      width: 80,
                      align: 'right',
                    },
                    {
                      title: 'Duracion',
                      dataIndex: 'duracion_segundos',
                      width: 90,
                      align: 'right',
                      render: (v: number | null) => (v !== null ? `${v.toFixed(1)} s` : '-'),
                    },
                    { title: 'Ejecutado por', dataIndex: 'ejecutado_por_nombre', ellipsis: true },
                    { title: 'Mensaje', dataIndex: 'mensaje', ellipsis: true },
                  ]}
                />
              </Card>
            ),
          },
          ...(modoADMS
            ? [
                {
                  key: 'comandos',
                  label: `Cola de comandos${
                    equipo.comandos_pendientes ? ` (${equipo.comandos_pendientes})` : ''
                  }`,
                  children: (
                    <Card
                      styles={{ body: { padding: 0 } }}
                      extra={
                        admin ? (
                          <Button
                            size="small"
                            icon={<ReloadOutlined />}
                            loading={reintentarFallidos.isPending}
                            onClick={() => reintentarFallidos.mutate()}
                          >
                            Reintentar fallidos
                          </Button>
                        ) : undefined
                      }
                    >
                      <Table<ComandoDispositivo>
                        rowKey="id"
                        size="small"
                        dataSource={comandos?.results ?? []}
                        scroll={{ x: 900 }}
                        pagination={{ pageSize: 10 }}
                        locale={{
                          emptyText:
                            'Sin comandos en cola. Apareceran aqui al subir empleados o ' +
                            'solicitar datos mientras el equipo trabaje en modo ADMS.',
                        }}
                        columns={[
                          {
                            title: 'Creado',
                            dataIndex: 'creado_en',
                            width: 150,
                            render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm:ss'),
                          },
                          { title: 'Tipo', dataIndex: 'tipo_display' },
                          { title: 'Empleado', dataIndex: 'empleado_nombre', ellipsis: true },
                          {
                            title: 'Estado',
                            dataIndex: 'estado_display',
                            width: 120,
                            render: (texto: string, fila) => (
                              <Badge
                                status={COLOR_ESTADO_COMANDO[fila.estado] as never}
                                text={texto}
                              />
                            ),
                          },
                          { title: 'Retorno', dataIndex: 'codigo_retorno', width: 80 },
                          { title: 'Respuesta', dataIndex: 'respuesta', ellipsis: true },
                          ...(admin
                            ? [
                                {
                                  title: '',
                                  key: 'acciones',
                                  width: 90,
                                  render: (_: unknown, fila: ComandoDispositivo) =>
                                    fila.estado === 'pendiente' ? (
                                      <Button
                                        size="small"
                                        danger
                                        loading={cancelarComando.isPending}
                                        onClick={() => cancelarComando.mutate(fila.id)}
                                      >
                                        Cancelar
                                      </Button>
                                    ) : null,
                                },
                              ]
                            : []),
                        ]}
                      />
                    </Card>
                  ),
                },
                ...(admin
                  ? [
                      {
                        key: 'peticiones',
                        label: 'Peticiones ADMS',
                        children: (
                          <Card styles={{ body: { padding: 0 } }}>
                            <Table<PeticionADMS>
                              rowKey="id"
                              size="small"
                              dataSource={peticionesADMS?.results ?? []}
                              scroll={{ x: 1000 }}
                              pagination={{ pageSize: 15 }}
                              locale={{
                                emptyText:
                                  'Todavia no llego ninguna peticion. Verifique la ' +
                                  'configuracion del servidor en el menu del equipo.',
                              }}
                              expandable={{
                                expandedRowRender: (fila) => (
                                  <div style={{ fontSize: 12 }}>
                                    <Text strong>Cuerpo de la peticion:</Text>
                                    <pre style={{ whiteSpace: 'pre-wrap', margin: '4px 0 12px' }}>
                                      {fila.cuerpo || '(vacio)'}
                                    </pre>
                                    <Text strong>Respuesta enviada:</Text>
                                    <pre style={{ whiteSpace: 'pre-wrap', margin: '4px 0' }}>
                                      {fila.respuesta || '(vacia)'}
                                    </pre>
                                  </div>
                                ),
                              }}
                              columns={[
                                {
                                  title: 'Recibida',
                                  dataIndex: 'recibida_en',
                                  width: 150,
                                  render: (v: string) => dayjs(v).format('DD/MM/YYYY HH:mm:ss'),
                                },
                                { title: 'Ruta', dataIndex: 'ruta', width: 160 },
                                { title: 'Metodo', dataIndex: 'metodo', width: 80 },
                                { title: 'Serie', dataIndex: 'numero_serie', width: 140 },
                                { title: 'IP origen', dataIndex: 'ip_origen', width: 120 },
                                {
                                  title: 'Aceptada',
                                  dataIndex: 'aceptada',
                                  width: 100,
                                  render: (v: boolean) =>
                                    v ? (
                                      <Tag color="green">Si</Tag>
                                    ) : (
                                      <Tag color="red">Rechazada</Tag>
                                    ),
                                },
                                {
                                  title: 'Registros',
                                  dataIndex: 'registros_procesados',
                                  width: 90,
                                  align: 'right',
                                },
                              ]}
                            />
                          </Card>
                        ),
                      },
                    ]
                  : []),
              ]
            : []),
        ]}
      />

      <Modal
        open={configAbierta}
        title="Configuracion del dispositivo"
        onCancel={() => setConfigAbierta(false)}
        onOk={() => formConfig.submit()}
        confirmLoading={guardarConfig.isPending}
        okText="Guardar"
        cancelText="Cancelar"
        width={640}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="Cambiar la IP redirige todas las operaciones a otro equipo."
        />
        <Form form={formConfig} layout="vertical" onFinish={(v) => guardarConfig.mutate(v)}>
          <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Row gutter={12}>
            <Col span={14}>
              <Form.Item
                name="ip"
                label="Direccion IP"
                rules={[
                  { required: true, message: 'Ingrese la IP del equipo.' },
                  {
                    pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
                    message: 'Formato de IP invalido.',
                  },
                ]}
              >
                <Input placeholder="192.168.18.202" />
              </Form.Item>
            </Col>
            <Col span={10}>
              <Form.Item name="puerto" label="Puerto" rules={[{ required: true }]}>
                <InputNumber style={{ width: '100%' }} min={1} max={65535} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="timeout" label="Timeout (segundos)">
                <InputNumber style={{ width: '100%' }} min={1} max={120} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="admin_user_id"
                label="ID del administrador del equipo"
                tooltip="Este usuario nunca se elimina durante una sincronizacion."
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="ubicacion" label="Ubicacion fisica">
            <Input />
          </Form.Item>
          <Form.Item
            name="force_udp"
            label="Forzar UDP"
            valuePropName="checked"
            tooltip="Active solo si el equipo no responde por TCP en modo SDK."
          >
            <Switch />
          </Form.Item>

          <Alert
            type="info"
            showIcon
            style={{ margin: '8px 0 16px' }}
            title="Comunicacion con el equipo"
            description={
              'SDK: el servidor llama al equipo por el puerto configurado arriba (requiere ' +
              'que el equipo tenga ese puerto abierto). ADMS: el equipo llama al servidor; ' +
              'requiere su numero de serie y que su menu de comunicacion apunte a esta maquina.'
            }
          />
          <Form.Item name="modo" label="Modo de comunicacion" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'sdk', label: 'SDK (el servidor consulta al equipo)' },
                { value: 'adms', label: 'ADMS / Push (el equipo envia los datos)' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="numero_serie"
            label="Numero de serie del equipo"
            tooltip="Es la unica identificacion que presenta el equipo al usar ADMS: obligatorio para habilitarlo."
          >
            <Input placeholder="Ej. COVG215160131" />
          </Form.Item>
          <Form.Item
            name="adms_habilitado"
            label="Aceptar conexiones ADMS de este equipo"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="adms_ip_permitida"
            label="IP autorizada para ADMS (recomendado)"
            tooltip="Si se indica, solo se aceptan peticiones ADMS que vengan de esta IP exacta."
          >
            <Input placeholder="192.168.18.202" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
