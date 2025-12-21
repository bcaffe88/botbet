"""
OverBot VIP v3.3 (produção) - aplicação Flask com Stripe e Telegram.
Conteúdo fornecido pelo cliente para integração neste repositório.
"""

import os
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

print("🚀 OverBot VIP v3.3 [MODO PRODUÇÃO - GATILHO OTIMIZADO]... Iniciando...")

app = Flask(__name__)

# Variáveis de ambiente
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "895248440"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

STRIPE_LINK_MENSAL = os.getenv("STRIPE_LINK_MENSAL")
STRIPE_LINK_VITALICIO = os.getenv("STRIPE_LINK_VITALICIO")
STRIPE_LINK_OFERTA_VITALICIO = os.getenv("STRIPE_LINK_OFERTA_VITALICIO")

# Configuração do banco de dados
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


def ensure_tables():
    try:
        with app.app_context():
            db.create_all()
            print("✅ Tabelas verificadas/criadas no banco")
    except Exception as e:
        print(f"❌ Erro ao criar/verificar tabelas: {e}")

# Controle de tarefas em segundo plano
task_control = {"last_run": None}

print(f"Bot Token: {'✅ Carregado' if BOT_TOKEN else '❌ Faltando'}")
print(f"Database URL: {'✅ Carregada' if DATABASE_URL else '❌ Faltando'}")
print(f"Channel ID: {'✅ Carregado' if CHANNEL_ID else '❌ Faltando'}")
print(f"Admin User ID: {ADMIN_USER_ID}")


class User(db.Model):
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    first_name = db.Column(db.String(100))
    username = db.Column(db.String(100), nullable=True)
    subscription_type = db.Column(db.String(50), default="none")
    subscription_end = db.Column(db.DateTime, nullable=True)
    has_used_trial = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    offer_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_active(self):
        if self.is_admin or self.subscription_type == "lifetime":
            return True
        return self.subscription_end and self.subscription_end > datetime.utcnow()


def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar mensagem para {chat_id}: {e}")
        return False


def answer_callback_query(callback_query_id, text="", show_alert=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert,
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao responder callback: {e}")


def create_invite_link(chat_id):
    if not CHANNEL_ID:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
    expire_date = int((datetime.now() + timedelta(days=1)).timestamp())
    payload = {"chat_id": CHANNEL_ID, "expire_date": expire_date, "member_limit": 1}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            print(f"🔗 Link de convite único criado para {chat_id}")
            return data["result"]["invite_link"]
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao criar link de convite: {e}")
    return None


def kick_user_from_channel(user_id):
    if not CHANNEL_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/banChatMember"
    payload = {"chat_id": CHANNEL_ID, "user_id": user_id, "revoke_messages": True}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"🚫 Usuário {user_id} expulso do canal.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao expulsar usuário {user_id}: {e}")
        return False


def get_or_create_user(tg_user_data):
    user_id = tg_user_data["id"]
    user = User.query.get(user_id)
    if not user:
        is_admin = user_id == ADMIN_USER_ID
        user = User(
            id=user_id,
            first_name=tg_user_data.get("first_name", "Recruta"),
            username=tg_user_data.get("username"),
            is_admin=is_admin,
            has_used_trial=is_admin,
        )
        if is_admin:
            user.subscription_type = "lifetime"
        db.session.add(user)
        print(f"📝 Novo recruta: {user.first_name} ({user.id})")
    else:
        user.first_name = tg_user_data.get("first_name", user.first_name)
        user.username = tg_user_data.get("username", user.username)
    db.session.commit()
    return user


def handle_start(message):
    chat_id = message["chat"]["id"]
    user = get_or_create_user(message["from"])
    welcome_text = f"""Olá, {user.first_name}. Bem-vindo à sala de controle do OverBot VIP. 🫡

Aqui, a sorte não tem vez. Nosso trabalho é identificar o padrão matemático do gol e te entregar a análise.

Sua missão é simples: *parar de apostar e começar a operar.*

Selecione sua ordem abaixo:"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "🎁 Iniciar Teste de Batalha (3 Dias)", "callback_data": "trial"}],
            [{"text": "💳 Plano Mensal de Operações", "callback_data": "monthly"}],
            [{"text": "👑 Acesso VITALÍCIO ao Arsenal", "callback_data": "lifetime"}],
            [{"text": "📊 Meu Status de Acesso", "callback_data": "status"}],
            [{"text": "💬 Contatar Suporte", "callback_data": "support"}],
        ]
    }
    send_telegram_message(chat_id, welcome_text, keyboard)


def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    user = get_or_create_user(callback_query["from"])
    data = callback_query["data"]
    callback_id = callback_query["id"]

    if data == "trial":
        if user.has_used_trial:
            answer_callback_query(
                callback_id, "Seu período de testes já foi utilizado.", show_alert=True
            )
            send_telegram_message(
                chat_id,
                "🚫 *Acesso Negado.*\n\nSeu teste de batalha já foi concluído. Para voltar ao campo, selecione um dos planos de acesso.",
            )
        else:
            end_date = datetime.utcnow() + timedelta(days=3)
            user.subscription_type = "trial"
            user.subscription_end = end_date
            user.has_used_trial = True
            user.offer_sent = False
            db.session.commit()
            invite_link = create_invite_link(chat_id)
            if invite_link:
                answer_callback_query(callback_id, "Teste de Batalha Ativado!")
                send_telegram_message(
                    chat_id,
                    f"✅ *Teste de Batalha ATIVADO!* ⚡️\n\nVocê tem 3 dias de acesso total ao arsenal. Use com sabedoria.\n\n*Sua missão expira em:* {end_date.strftime('%d/%m/%Y às %H:%M')} (UTC).",
                )
                send_telegram_message(
                    chat_id,
                    f"Seu link de acesso *pessoal e intransferível* à sala de operações é:\n\n🔗 {invite_link}\n\nEste link só pode ser usado uma vez.",
                )
            else:
                answer_callback_query(
                    callback_id, "Erro ao gerar seu acesso. Contate o suporte.", show_alert=True
                )
                send_telegram_message(
                    chat_id,
                    "⚠️ Ocorreu um erro ao gerar seu link de acesso. Por favor, contate o suporte em @bcaffe para assistência imediata.",
                )
    elif data == "monthly":
        message = f"💳 *Plano Mensal de Operações* | R$ 29,87\n\nAcesso contínuo ao fluxo de inteligência.\n\nClique no link seguro abaixo para ativar seu acesso por 30 dias. A ativação é imediata.\n\n🔗 {STRIPE_LINK_MENSAL}?client_reference_id={user.id}"
        send_telegram_message(chat_id, message)
    elif data == "lifetime":
        message = f"👑 *Acesso VITALÍCIO ao Arsenal* | R$ 197,87\n\nUm único pagamento para acesso eterno. A elite do OverBot VIP.\n\nClique no link seguro abaixo para se tornar um membro permanente. A ativação é imediata.\n\n🔗 {STRIPE_LINK_VITALICIO}?client_reference_id={user.id}"
        send_telegram_message(chat_id, message)
    elif data == "status":
        if user.is_admin:
            status_text = "📊 *Status:* General do Exército (Admin)\n*Acesso:* Total e irrestrito."
        elif user.is_active:
            if user.subscription_type == "lifetime":
                status_text = "📊 *Status:* Operador VITALÍCIO\n*Acesso:* Permanente."
            else:
                remaining_time = user.subscription_end - datetime.utcnow()
                days = max(0, remaining_time.days)
                hours = max(0, remaining_time.seconds // 3600)
                status_text = f"📊 *Status:* Ativo\n*Plano:* {user.subscription_type.capitalize()}\n*Tempo restante:* {days} dias e {hours} horas."
        else:
            status_text = "📊 *Status:* Inativo.\n\nSeu acesso expirou. Use /start para selecionar um novo plano."
        send_telegram_message(chat_id, status_text)
    elif data == "support":
        send_telegram_message(chat_id, "Para contatar o suporte, envie sua dúvida diretamente para o General @bcaffe.")


def activate_subscription(user_id, plan_type):
    user = User.query.get(user_id)
    if not user:
        return
    if plan_type == "lifetime":
        user.subscription_type = "lifetime"
        user.subscription_end = None
        msg = f"👑 *Acesso VITALÍCIO Confirmado!*\n\nParabéns, {user.first_name}. Você agora é um membro permanente do OverBot VIP. Bem-vindo à elite."
    elif plan_type == "monthly":
        user.subscription_type = "monthly"
        user.subscription_end = datetime.utcnow() + timedelta(days=31)
        msg = f"💳 *Plano Mensal ATIVADO!*\n\nSeu acesso por 30 dias está confirmado, {user.first_name}. Boas operações."
    else:
        return
    db.session.commit()
    send_telegram_message(user_id, msg)
    invite_link = create_invite_link(user_id)
    if invite_link:
        send_telegram_message(
            user_id,
            f"Seu novo link de acesso *pessoal e intransferível* é:\n\n🔗 {invite_link}",
        )
    else:
        send_telegram_message(
            user_id,
            "⚠️ Erro ao gerar seu novo link de acesso. Contate o suporte.",
        )


def check_trial_expiring_soon():
    now = datetime.utcnow()
    expiration_window = now + timedelta(hours=24)
    expiring_users = User.query.filter(
        User.subscription_type == "trial",
        User.offer_sent == False,  # noqa: E712
        User.subscription_end <= expiration_window,
        User.subscription_end > now,
    ).all()
    if not expiring_users:
        return
    print(f"⏳ {len(expiring_users)} usuários em teste prestes a expirar encontrados.")
    for user in expiring_users:
        offer_text = f"""Fala, {user.first_name}! 👋
Seu teste de batalha está nas últimas 24 horas. Você viu o poder da análise de dados em campo.
Como um dos nossos primeiros recrutas, você tem uma oportunidade única que não vai se repetir:
🔥 *Acesso VITALÍCIO por apenas R$49,90*
Sem mensalidade. Sem renovação. É seu pra sempre.
Esta é uma oferta de agradecimento pela sua confiança inicial. Ela expira junto com o seu teste.
Para garantir sua vaga na elite, clique no link seguro abaixo:
👉 {STRIPE_LINK_OFERTA_VITALICIO}?client_reference_id={user.id}
Não deixe a oportunidade passar. Tamo junto! 👊"""
        if send_telegram_message(user.id, offer_text):
            user.offer_sent = True
            db.session.commit()
            print(f"💸 Oferta de expiração enviada para {user.first_name} ({user.id})")


def check_expired_subscriptions():
    now = datetime.utcnow()
    expired_users = User.query.filter(
        User.subscription_type.in_(["trial", "monthly"]),
        User.subscription_end <= now,
    ).all()
    if not expired_users:
        return
    print(f"⏰ {len(expired_users)} usuários expirados encontrados.")
    for user in expired_users:
        expiration_text = """*Acesso Expirado* ⌛️
Seu período de acesso terminou. Para voltar a receber os sinais e operar com base em dados, renove seu plano.
Use /start para ver as opções. Não conte com a sorte!"""
        send_telegram_message(user.id, expiration_text)
        kick_user_from_channel(user.id)
        user.subscription_type = "none"
        user.subscription_end = None
        db.session.commit()
        print(f"💀 Acesso desativado e usuário expulso para {user.first_name} ({user.id})")


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if "message" in update and "text" in update["message"] and update["message"]["text"] == "/start":
        with app.app_context():
            handle_start(update["message"])
    elif "callback_query" in update:
        with app.app_context():
            handle_callback(update["callback_query"])
    return jsonify(ok=True)


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        client_reference_id = session.get("client_reference_id")
        amount_total = session.get("amount_total", 0) / 100
        if not client_reference_id:
            send_telegram_message(
                ADMIN_USER_ID,
                f"🚨 PAGAMENTO ÓRFÃO RECEBIDO!\n\nValor: R${amount_total}\nEmail: {session.get('customer_details', {}).get('email')}",
            )
            return jsonify(status="received_orphan")
        user_id = int(client_reference_id)
        plan_type = None
        if abs(amount_total - 29.87) < 0.01:
            plan_type = "monthly"
        elif abs(amount_total - 197.87) < 0.01:
            plan_type = "lifetime"
        elif abs(amount_total - 49.90) < 0.01:
            plan_type = "lifetime"
        if plan_type:
            with app.app_context():
                activate_subscription(user_id, plan_type)
        else:
            print(f"⚠️ Valor de pagamento não reconhecido: {amount_total}")
    return jsonify(status="success")


@app.route("/health", methods=["GET"])
def health_check():
    now = datetime.utcnow()
    if task_control["last_run"] and (now - task_control["last_run"] < timedelta(hours=1)):
        return jsonify(status="ok_skipped_tasks"), 200

    print(f"⚙️ GATILHO DE SAÚDE ATIVADO - {now.strftime('%Y-%m-%d %H:%M:%S')} UTC - Executando tarefas periódicas...")
    try:
        with app.app_context():
            check_trial_expiring_soon()
            check_expired_subscriptions()

        task_control["last_run"] = now
        print("✅ Tarefas periódicas concluídas com sucesso.")
        return jsonify(status="ok_tasks_executed"), 200
    except Exception as e:
        print(f"❌ Erro grave na execução das tarefas periódicas: {e}")
        return jsonify(status="error_in_tasks", error=str(e)), 500


@app.before_request
def _bootstrap_tables():
    if not task_control.get("last_run"):
        ensure_tables()
        task_control["last_run"] = task_control.get("last_run")


LANDING_TEMPLATE = """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OverBot VIP</title>
  <style>
    body { font-family: Arial, sans-serif; margin:0; padding:0; background:#0b132b; color:#f5f7fa; }
    header { padding:32px; text-align:center; background:#1c2541; }
    h1 { margin:0 0 8px; }
    p { margin:0; }
    section { padding:32px 20px; max-width:960px; margin:0 auto; }
    .cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:16px; }
    .card { background:#1c2541; padding:20px; border-radius:12px; border:1px solid #243b53; }
    .btn { display:inline-block; padding:10px 16px; background:#ff7e67; color:#fff; text-decoration:none; border-radius:8px; font-weight:bold; }
    footer { text-align:center; padding:24px; color:#9fb3c8; }
  </style>
</head>
<body>
  <header>
    <h1>OverBot VIP</h1>
    <p>Previsão de gols no 1º tempo com inteligência de dados e triagem automatizada.</p>
    <p><strong>Canal:</strong> {{ channel or 'configurar CHANNEL_ID' }}</p>
  </header>

  <section id="planos">
    <h2>Planos</h2>
    <div class="cards">
      <div class="card">
        <h3>Teste de Batalha</h3>
        <p>3 dias de acesso para validar o arsenal.</p>
        <p><strong>Ative via /start no bot</strong></p>
      </div>
      <div class="card">
        <h3>Mensal</h3>
        <p>Acesso contínuo ao fluxo de inteligência.</p>
        <p><strong>Link:</strong> {{ link_mensal or 'configure STRIPE_LINK_MENSAL' }}</p>
      </div>
      <div class="card">
        <h3>Vitalício</h3>
        <p>Acesso permanente para operadores da elite.</p>
        <p><strong>Link:</strong> {{ link_vitalicio or 'configure STRIPE_LINK_VITALICIO' }}</p>
      </div>
    </div>
  </section>

  <section id="contato">
    <h2>Contato</h2>
    <p>Suporte via Telegram: <a class="btn" href="https://t.me/{{ botadmin or 'botadmin' }}" target="_blank">Abrir botadmin</a></p>
  </section>

  <footer>
    <p>OverBot VIP — overbotvip.up.railway.app</p>
  </footer>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def landing_page():
    return render_template_string(
        LANDING_TEMPLATE,
        channel=CHANNEL_ID,
        link_mensal=STRIPE_LINK_MENSAL,
        link_vitalicio=STRIPE_LINK_VITALICIO,
        botadmin="botadmin",
    )


if __name__ == "__main__":
    ensure_tables()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
