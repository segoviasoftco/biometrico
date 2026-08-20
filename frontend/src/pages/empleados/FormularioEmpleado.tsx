import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Col,
  DatePicker,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Button,
} from 'antd';
import dayjs from 'dayjs';
import { useEffect } from 'react';

import { mensajeError } from '../../api/client';
import { empleadosApi, organizacionApi } from '../../api/endpoints';

interface Props {
  abierto: boolean;
  empleadoId: number | null;
  onCerrar: () => void;
  onGuardado: () => void;
}

export default function FormularioEmpleado({ abierto, empleadoId, onCerrar, onGuardado }: Props) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const esEdicion = empleadoId !== null;

  const sedeSeleccionada = Form.useWatch('sede', form);
  const departamentoSeleccionado = Form.useWatch('departamento', form);

  const { data: sedes } = useQuery({
    queryKey: ['sedes'],
    queryFn: () => organizacionApi.sedes({ page_size: 100 }),
  });
  const { data: departamentos } = useQuery({
    queryKey: ['departamentos', sedeSeleccionada],
    queryFn: () => organizacionApi.departamentos({ page_size: 100, sede: sedeSeleccionada }),
    enabled: !!sedeSeleccionada,
  });
  const { data: areas } = useQuery({
    queryKey: ['areas', departamentoSeleccionado],
    queryFn: () => organizacionApi.areas({ page_size: 100, departamento: departamentoSeleccionado }),
    enabled: !!departamentoSeleccionado,
  });
  const { data: cargos } = useQuery({
    queryKey: ['cargos'],
    queryFn: () => organizacionApi.cargos({ page_size: 100 }),
  });

  const { data: empleado } = useQuery({
    queryKey: ['empleado', empleadoId],
    queryFn: () => empleadosApi.obtener(empleadoId!),
    enabled: esEdicion && abierto,
  });

  useEffect(() => {
    if (!abierto) return;
    if (empleado && esEdicion) {
      form.setFieldsValue({
        ...empleado,
        fecha_ingreso: empleado.fecha_ingreso ? dayjs(empleado.fecha_ingreso) : null,
        fecha_cese: empleado.fecha_cese ? dayjs(empleado.fecha_cese) : null,
        fecha_nacimiento: empleado.fecha_nacimiento ? dayjs(empleado.fecha_nacimiento) : null,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        estado: 'activo',
        tipo_contrato: 'indefinido',
        privilegio_dispositivo: 0,
        fecha_ingreso: dayjs(),
      });
    }
  }, [abierto, empleado, esEdicion, form]);

  const guardar = useMutation({
    mutationFn: async (valores: Record<string, unknown>) => {
      const datos = {
        ...valores,
        fecha_ingreso: valores.fecha_ingreso
          ? dayjs(valores.fecha_ingreso as string).format('YYYY-MM-DD')
          : null,
        fecha_cese: valores.fecha_cese
          ? dayjs(valores.fecha_cese as string).format('YYYY-MM-DD')
          : null,
        fecha_nacimiento: valores.fecha_nacimiento
          ? dayjs(valores.fecha_nacimiento as string).format('YYYY-MM-DD')
          : null,
      };
      return esEdicion
        ? empleadosApi.actualizar(empleadoId, datos)
        : empleadosApi.crear(datos);
    },
    onSuccess: () => {
      message.success(esEdicion ? 'Empleado actualizado.' : 'Empleado registrado.');
      onGuardado();
    },
    onError: (error) => message.error(mensajeError(error, 'No se pudo guardar el empleado.')),
  });

  return (
    <Drawer
      open={abierto}
      onClose={onCerrar}
      size={720}
      title={esEdicion ? 'Editar empleado' : 'Nuevo empleado'}
      extra={
        <Space>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button type="primary" loading={guardar.isPending} onClick={() => form.submit()}>
            Guardar
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={(v) => guardar.mutate(v)}>
        <Divider titlePlacement="start">Datos personales</Divider>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item
              name="codigo_empleado"
              label="Codigo de empleado"
              tooltip="Identificador numerico que se usa en el dispositivo biometrico."
              rules={[
                { required: true, message: 'Ingrese el codigo.' },
                { pattern: /^\d+$/, message: 'El codigo debe ser numerico.' },
              ]}
            >
              <Input placeholder="1001" disabled={esEdicion} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="dni"
              label="DNI"
              rules={[{ required: true, message: 'Ingrese el DNI.' }]}
            >
              <Input placeholder="70000000" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="sexo" label="Sexo">
              <Select
                allowClear
                options={[
                  { value: 'M', label: 'Masculino' },
                  { value: 'F', label: 'Femenino' },
                ]}
              />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col span={8}>
            <Form.Item
              name="nombres"
              label="Nombres"
              rules={[{ required: true, message: 'Ingrese los nombres.' }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="apellido_paterno"
              label="Apellido paterno"
              rules={[{ required: true, message: 'Ingrese el apellido paterno.' }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="apellido_materno" label="Apellido materno">
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col span={8}>
            <Form.Item name="fecha_nacimiento" label="Fecha de nacimiento">
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="email" label="Correo" rules={[{ type: 'email', message: 'Correo invalido.' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="telefono" label="Telefono">
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="direccion" label="Direccion">
          <Input />
        </Form.Item>

        <Divider titlePlacement="start">Datos laborales</Divider>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item
              name="sede"
              label="Sede"
              rules={[{ required: true, message: 'Seleccione la sede.' }]}
            >
              <Select
                options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
                onChange={() => form.setFieldsValue({ departamento: undefined, area: undefined })}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="departamento"
              label="Departamento"
              rules={[{ required: true, message: 'Seleccione el departamento.' }]}
            >
              <Select
                disabled={!sedeSeleccionada}
                options={departamentos?.results.map((d) => ({ value: d.id, label: d.nombre }))}
                onChange={() => form.setFieldsValue({ area: undefined })}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="area" label="Area">
              <Select
                allowClear
                disabled={!departamentoSeleccionado}
                options={areas?.results.map((a) => ({ value: a.id, label: a.nombre }))}
              />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col span={8}>
            <Form.Item
              name="cargo"
              label="Cargo"
              rules={[{ required: true, message: 'Seleccione el cargo.' }]}
            >
              <Select options={cargos?.results.map((c) => ({ value: c.id, label: c.nombre }))} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="fecha_ingreso"
              label="Fecha de ingreso"
              rules={[{ required: true, message: 'Ingrese la fecha de ingreso.' }]}
            >
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="fecha_cese" label="Fecha de cese">
              <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col span={8}>
            <Form.Item name="tipo_contrato" label="Tipo de contrato">
              <Select
                options={[
                  { value: 'indefinido', label: 'Plazo indeterminado' },
                  { value: 'plazo_fijo', label: 'Plazo fijo' },
                  { value: 'practicas', label: 'Practicas' },
                  { value: 'locacion', label: 'Locacion de servicios' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="estado" label="Estado">
              <Select
                options={[
                  { value: 'activo', label: 'Activo' },
                  { value: 'inactivo', label: 'Inactivo' },
                  { value: 'vacaciones', label: 'De vacaciones' },
                  { value: 'cesado', label: 'Cesado' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="sueldo_basico"
              label="Sueldo basico"
              tooltip="Se usa para valorizar los descuentos por tardanza y falta."
            >
              <InputNumber style={{ width: '100%' }} min={0} precision={2} prefix="S/" />
            </Form.Item>
          </Col>
        </Row>

        <Divider titlePlacement="start">Configuracion en el dispositivo</Divider>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="El rostro y la huella se registran en el equipo"
          description={
            'Aqui solo se definen los datos que el sistema envia al dispositivo. El ' +
            'enrolamiento biometrico lo realiza el empleado en el equipo MB560-VL; luego, ' +
            'al respaldar huellas, el sistema refleja automaticamente su estado.'
          }
        />
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item
              name="privilegio_dispositivo"
              label="Privilegio en el equipo"
              tooltip="El firmware solo admite estos dos niveles."
            >
              <Select
                options={[
                  { value: 0, label: 'Usuario' },
                  { value: 14, label: 'Administrador del equipo' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="password_dispositivo"
              label="Clave del equipo"
              tooltip="Clave numerica para marcar por teclado."
            >
              <Input placeholder="Opcional" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="numero_tarjeta" label="Numero de tarjeta">
              <Input placeholder="Opcional" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Drawer>
  );
}
