import { useMutation } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Form, Input, Space, Tag, Typography } from 'antd';

import { mensajeError } from '../api/client';
import { authApi } from '../api/endpoints';
import { useAuth } from '../store/auth';

const { Title } = Typography;

export default function Perfil() {
  const { usuario } = useAuth();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  const cambiar = useMutation({
    mutationFn: (v: { password_actual: string; password_nueva: string }) =>
      authApi.cambiarPassword(v.password_actual, v.password_nueva),
    onSuccess: () => {
      message.success('La clave se actualizo correctamente.');
      form.resetFields();
    },
    onError: (e) => message.error(mensajeError(e)),
  });

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%', maxWidth: 720 }}>
      <Title level={3} style={{ margin: 0 }}>
        Mi Perfil
      </Title>

      <Card title="Datos de la cuenta">
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Nombre">{usuario?.nombre_completo}</Descriptions.Item>
          <Descriptions.Item label="Correo">{usuario?.email}</Descriptions.Item>
          <Descriptions.Item label="Rol">
            <Tag color={usuario?.rol === 'administrador' ? 'gold' : 'blue'}>
              {usuario?.rol_display}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Sede asignada">
            {usuario?.sede_nombre ?? 'Todas las sedes'}
          </Descriptions.Item>
          <Descriptions.Item label="Telefono">{usuario?.telefono || '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Cambiar clave">
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => cambiar.mutate(v)}
          style={{ maxWidth: 400 }}
        >
          <Form.Item
            name="password_actual"
            label="Clave actual"
            rules={[{ required: true, message: 'Ingrese su clave actual.' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="password_nueva"
            label="Nueva clave"
            rules={[
              { required: true, message: 'Ingrese la nueva clave.' },
              { min: 8, message: 'La clave debe tener al menos 8 caracteres.' },
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirmacion"
            label="Confirmar nueva clave"
            dependencies={['password_nueva']}
            rules={[
              { required: true, message: 'Repita la nueva clave.' },
              ({ getFieldValue }) => ({
                validator(_, valor) {
                  if (!valor || getFieldValue('password_nueva') === valor) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('Las claves no coinciden.'));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={cambiar.isPending}>
            Cambiar clave
          </Button>
        </Form>
      </Card>
    </Space>
  );
}
