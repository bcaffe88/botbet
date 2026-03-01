"""
Testes para as funções do botadmin (overbot_vip.py)
"""
import os
import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Set required environment variables before importing
os.environ.setdefault('BOT_TOKEN_ADMIN', 'test-token')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STRIPE_API_KEY', 'test-key')
os.environ.setdefault('STRIPE_WEBHOOK_SECRET', 'test-secret')
os.environ.setdefault('ADMIN_USER_ID', '12345')
os.environ.setdefault('CHANNEL_ID_ADMIN', '-100123456789')
os.environ.setdefault('STRIPE_LINK_MENSAL', 'https://stripe.test/mensal')
os.environ.setdefault('STRIPE_LINK_VITALICIO', 'https://stripe.test/vitalicio')
os.environ.setdefault('STRIPE_LINK_OFERTA_VITALICIO', 'https://stripe.test/oferta')

import overbot_vip  # noqa: E402


class TestBotAdminFunctions(unittest.TestCase):
    """Testes para funções do botadmin"""

    def setUp(self):
        """Setup para cada teste"""
        self.app = overbot_vip.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        with self.app.app_context():
            overbot_vip.db.create_all()

    def tearDown(self):
        """Cleanup após cada teste"""
        with self.app.app_context():
            overbot_vip.db.session.remove()
            overbot_vip.db.drop_all()

    def test_landing_page_loads(self):
        """Testa se a landing page carrega corretamente"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('OverBot VIP', html)
        self.assertIn('inteligência para gols no 1º tempo', html)

    def test_landing_page_has_planos(self):
        """Testa se a landing page contém os planos"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Verifica se os planos estão na página
        self.assertIn('Teste de Batalha', html)
        self.assertIn('Mensal', html)
        self.assertIn('Vitalício', html)

    def test_health_endpoint(self):
        """Testa o endpoint de health check"""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('status', data)

    def test_user_creation(self):
        """Testa criação de usuário"""
        with self.app.app_context():
            tg_user_data = {
                'id': 99999,
                'first_name': 'Test User',
                'username': 'testuser'
            }
            user = overbot_vip.get_or_create_user(tg_user_data)
            self.assertEqual(user.id, 99999)
            self.assertEqual(user.first_name, 'Test User')
            self.assertEqual(user.username, 'testuser')
            self.assertFalse(user.is_admin)

    def test_admin_user_creation(self):
        """Testa criação de usuário admin"""
        with self.app.app_context():
            tg_user_data = {
                'id': 12345,  # ADMIN_USER_ID
                'first_name': 'Admin User',
                'username': 'admin'
            }
            user = overbot_vip.get_or_create_user(tg_user_data)
            self.assertTrue(user.is_admin)
            self.assertEqual(user.subscription_type, 'lifetime')
            self.assertTrue(user.has_used_trial)

    def test_user_is_active_lifetime(self):
        """Testa se usuário vitalício está ativo"""
        with self.app.app_context():
            user = overbot_vip.User(
                id=99998,
                first_name='Test',
                subscription_type='lifetime'
            )
            overbot_vip.db.session.add(user)
            overbot_vip.db.session.commit()
            self.assertTrue(user.is_active)

    def test_user_is_active_with_valid_subscription(self):
        """Testa se usuário com assinatura válida está ativo"""
        with self.app.app_context():
            future_date = datetime.utcnow() + timedelta(days=10)
            user = overbot_vip.User(
                id=99997,
                first_name='Test',
                subscription_type='monthly',
                subscription_end=future_date
            )
            overbot_vip.db.session.add(user)
            overbot_vip.db.session.commit()
            self.assertTrue(user.is_active)

    def test_user_is_not_active_expired(self):
        """Testa se usuário com assinatura expirada não está ativo"""
        with self.app.app_context():
            past_date = datetime.utcnow() - timedelta(days=1)
            user = overbot_vip.User(
                id=99996,
                first_name='Test',
                subscription_type='monthly',
                subscription_end=past_date
            )
            overbot_vip.db.session.add(user)
            overbot_vip.db.session.commit()
            self.assertFalse(user.is_active)

    @patch('overbot_vip.requests.post')
    def test_send_telegram_message(self, mock_post):
        """Testa envio de mensagem via Telegram"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = overbot_vip.send_telegram_message(12345, 'Test message')
        self.assertTrue(result)
        mock_post.assert_called_once()

    def test_stripe_webhook_monthly(self):
        """Testa webhook do Stripe para plano mensal"""
        with self.app.app_context():
            # Criar usuário primeiro
            user = overbot_vip.User(id=88888, first_name='Test')
            overbot_vip.db.session.add(user)
            overbot_vip.db.session.commit()

            # Simular webhook do Stripe
            payload = {
                'type': 'checkout.session.completed',
                'data': {
                    'object': {
                        'client_reference_id': '88888',
                        'amount_total': 2987,  # 29.87 * 100
                        'customer_details': {'email': 'test@test.com'}
                    }
                }
            }
            
            with patch('overbot_vip.send_telegram_message'):
                with patch('overbot_vip.create_invite_link', return_value='https://t.me/+abc123'):
                    response = self.client.post('/stripe-webhook',
                                                data=json.dumps(payload),
                                                content_type='application/json')
                    self.assertEqual(response.status_code, 200)
                    
                    # Verificar se o usuário foi atualizado
                    user = overbot_vip.User.query.get(88888)
                    self.assertEqual(user.subscription_type, 'monthly')
                    self.assertIsNotNone(user.subscription_end)

    def test_activate_subscription_lifetime(self):
        """Testa ativação de assinatura vitalícia"""
        with self.app.app_context():
            user = overbot_vip.User(id=77777, first_name='Test')
            overbot_vip.db.session.add(user)
            overbot_vip.db.session.commit()

            with patch('overbot_vip.send_telegram_message'):
                with patch('overbot_vip.create_invite_link', return_value='https://t.me/+test'):
                    overbot_vip.activate_subscription(77777, 'lifetime')
                    
                    user = overbot_vip.User.query.get(77777)
                    self.assertEqual(user.subscription_type, 'lifetime')
                    self.assertIsNone(user.subscription_end)


class TestBotAdminWebhooks(unittest.TestCase):
    """Testes para webhooks do botadmin"""

    def setUp(self):
        """Setup para cada teste"""
        self.app = overbot_vip.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        with self.app.app_context():
            overbot_vip.db.create_all()

    def tearDown(self):
        """Cleanup após cada teste"""
        with self.app.app_context():
            overbot_vip.db.session.remove()
            overbot_vip.db.drop_all()

    @patch('overbot_vip.send_telegram_message')
    def test_telegram_webhook_start(self, mock_send):
        """Testa webhook do Telegram com comando /start"""
        mock_send.return_value = True
        
        update = {
            'message': {
                'chat': {'id': 123456},
                'from': {
                    'id': 123456,
                    'first_name': 'John',
                    'username': 'john_doe'
                },
                'text': '/start'
            }
        }
        
        response = self.client.post(f'/{overbot_vip.BOT_TOKEN_ADMIN}',
                                    json=update,
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()
        
        # Verificar se a mensagem de boas-vindas foi enviada
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][0], 123456)
        self.assertIn('Bem-vindo', call_args[0][1])


if __name__ == '__main__':
    unittest.main()
