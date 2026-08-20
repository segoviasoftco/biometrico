import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { mensajeError } from '../api/client';
import { useAuth } from '../store/auth';

const { Title, Text } = Typography;

export default function Login() {
  const { login, cargando } = useAuth();
  const navegar = useNavigate();
  const [error, setError] = useState('');

  const enviar = async (valores: { email: string; password: string }) => {
    setError('');
    try {
      await login(valores.email, valores.password);
      navegar('/');
    } catch (err) {
      setError(mensajeError(err, 'No se pudo iniciar sesion. Verifique sus credenciales.'));
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1F4E79 0%, #2d6ba3 100%)',
        padding: 16,
      }}
    >
      <Card style={{ width: 400, maxWidth: '100%' }} variant="borderless">
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <Title level={3} style={{ marginBottom: 4 }}>
            Control de Asistencia
          </Title>
          <Text type="secondary">Sistema biometrico ZKTeco MB560-VL</Text>
        </div>

        {error && (
          <Alert type="error" title={error} showIcon style={{ marginBottom: 16 }} closable />
        )}

        <Form layout="vertical" onFinish={enviar} requiredMark={false} size="large">
          <Form.Item
            name="email"
            label="Correo electronico"
            rules={[
              { required: true, message: 'Ingrese su correo electronico.' },
              { type: 'email', message: 'El correo no tiene un formato valido.' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="usuario@empresa.com" autoFocus />
          </Form.Item>

          <Form.Item
            name="password"
            label="Clave"
            rules={[{ required: true, message: 'Ingrese su clave.' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="Su clave" />
          </Form.Item>

          <Button type="primary" htmlType="submit" block loading={cargando}>
            Ingresar
          </Button>
        </Form>
      </Card>
    </div>
  );
}
