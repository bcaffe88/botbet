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
BOT_TOKEN_ADMIN = os.getenv("BOT_TOKEN_ADMIN") or os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "895248440"))
CHANNEL_ID_ADMIN = os.getenv("CHANNEL_ID_ADMIN") or os.getenv("CHANNEL_ID")
BOT_USERNAME_ADMIN = os.getenv("BOT_USERNAME_ADMIN", "overbotvip_bot")

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

print(f"Bot Token Admin: {'✅ Carregado' if BOT_TOKEN_ADMIN else '❌ Faltando'}")
print(f"Database URL: {'✅ Carregada' if DATABASE_URL else '❌ Faltando'}")
print(f"Channel ID Admin: {'✅ Carregado' if CHANNEL_ID_ADMIN else '❌ Faltando'}")
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
    url = f"https://api.telegram.org/bot{BOT_TOKEN_ADMIN}/sendMessage"
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
    url = f"https://api.telegram.org/bot{BOT_TOKEN_ADMIN}/answerCallbackQuery"
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
    if not CHANNEL_ID_ADMIN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN_ADMIN}/createChatInviteLink"
    expire_date = int((datetime.now() + timedelta(days=1)).timestamp())
    payload = {"chat_id": CHANNEL_ID_ADMIN, "expire_date": expire_date, "member_limit": 1}
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
    if not CHANNEL_ID_ADMIN:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN_ADMIN}/banChatMember"
    payload = {"chat_id": CHANNEL_ID_ADMIN, "user_id": user_id, "revoke_messages": True}
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


@app.route(f"/{BOT_TOKEN_ADMIN}", methods=["POST"])
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
    if not task_control.get("tables_created"):
        ensure_tables()
        task_control["tables_created"] = True


LANDING_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OverBot VIP — Inteligência de gols HT</title>
    <style>
      :root {
        --bg: #070914;
        --panel: #0c1224;
        --border: #1e293b;
        --text: #e2e8f0;
        --muted: #94a3b8;
        --accent: #22c55e;
        --accent-2: #3b82f6;
      }
      body { font-family: 'Inter', Arial, sans-serif; margin: 0; color: var(--text); background: var(--bg); }
      .hero { padding: 80px 20px 64px; text-align: center; background: radial-gradient(circle at 15% 20%, rgba(34,197,94,0.18), transparent 28%), radial-gradient(circle at 80% 10%, rgba(59,130,246,0.20), transparent 32%), var(--bg); }
      .hero h1 { font-size: 2.6rem; margin: 0 0 14px; }
      .hero p { margin: 0 auto 26px; max-width: 760px; line-height: 1.7; color: #cbd5e1; }
      .badge { display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 999px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); color: #0b1021; font-weight: 800; font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.4px; }
      .cta { display: inline-block; margin-top: 14px; padding: 14px 18px; border-radius: 12px; background: var(--accent); color: #0b1021; font-weight: 800; text-decoration: none; box-shadow: 0 14px 34px rgba(34,197,94,0.28); }
      .section { padding: 60px 20px; max-width: 1100px; margin: 0 auto; }
      .section h2 { margin: 0 0 12px; text-align: center; }
      .section p.lead { text-align: center; margin: 0 auto 32px; max-width: 760px; color: #cbd5e1; }
      .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 20px; }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px; color: var(--text); box-shadow: 0 10px 28px rgba(0,0,0,0.28); }
      .card h3 { margin: 0 0 10px; font-size: 1.25rem; }
      .card p { margin: 0 0 12px; color: #cbd5e1; line-height: 1.6; }
      .price { font-size: 1.4rem; font-weight: 800; color: var(--accent); }
      ul.features { list-style: none; padding: 0; margin: 12px 0 0; color: #cbd5e1; }
      ul.features li { margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
      .footer { text-align: center; padding: 30px 20px; color: var(--muted); background: var(--bg); border-top: 1px solid var(--border); }
      a.btn { display: inline-block; padding: 12px 14px; margin-top: 10px; background: var(--accent-2); color: white; border-radius: 10px; text-decoration: none; font-weight: 700; }
      @media (max-width: 480px) { .hero h1 { font-size: 1.9rem; } }
    </style>
  </head>
  <body>
    <header class="hero">
      <div class="badge">Primeiro tempo • Over 0.5</div>
      <h1>OverBot VIP — inteligência para gols no 1º tempo</h1>
      <p>Operações guiadas por leitura de padrões e odds pré-live, entregues em tempo real. Menos feeling, mais método.</p>
      <a class="cta" href="#planos">Ver planos</a>
    </header>

    <section class="section" id="planos">
      <h2>Planos para operar com disciplina</h2>
      <p class="lead">Escolha o acesso que melhor se encaixa na sua estratégia. Links configuráveis via Stripe.</p>
      <div class="cards">
        <div class="card">
          <h3>Teste de Batalha (3 dias)</h3>
          <p>Valide o fluxo de leitura antes de escalar.</p>
          <ul class="features">
            <li>⚡ Sinais de over 0.5 HT</li>
            <li>📊 Canal de operações</li>
            <li>🛠️ Triagem automática</li>
          </ul>
          <p class="price">R$ 0</p>
          <p><strong>Ative via /start no bot</strong></p>
        </div>
        <div class="card">
          <h3>Mensal</h3>
          <p>Acesso contínuo ao fluxo de inteligência e gestão.</p>
          <ul class="features">
            <li>🔁 Atualizações diárias</li>
            <li>🧠 Leitura pré-live + refinamento</li>
            <li>🎯 Estatísticas e histórico</li>
          </ul>
          <p class="price">R$ 29,87</p>
          <p><strong>Link:</strong> {{ link_mensal or 'configure STRIPE_LINK_MENSAL' }}</p>
        </div>
        <div class="card">
          <h3>Vitalício</h3>
          <p>Acesso permanente para operadores da elite.</p>
          <ul class="features">
            <li>🚀 Suporte prioritário</li>
            <li>📈 Atualizações futuras</li>
            <li>♾️ Sem mensalidades</li>
          </ul>
          <p class="price">R$ 197,87</p>
          <p><strong>Link:</strong> {{ link_vitalicio or 'configure STRIPE_LINK_VITALICIO' }}</p>
        </div>
      </div>
    </section>

    <section class="section" id="contato">
      <h2>Fale com o botadmin</h2>
      <p class="lead">Tire dúvidas, libere acesso e acompanhe suporte direto no Telegram.</p>
      <p style="text-align:center;">
        <a class="btn" href="https://t.me/{{ botadmin or 'botadmin' }}" target="_blank">Abrir botadmin</a>
      </p>
      <p style="text-align:center; color: var(--muted);">Canal principal: {{ channel or 'configurar CHANNEL_ID_ADMIN' }}</p>
    </section>

    <footer class="footer">
      <p>OverBot VIP — overbotvip.up.railway.app</p>
    </footer>
  </body>
</html>
"""


@app.route("/", methods=["GET"])
def landing_page():
    return render_template_string(
        LANDING_TEMPLATE,
        channel=CHANNEL_ID_ADMIN,
        link_mensal=STRIPE_LINK_MENSAL,
        link_vitalicio=STRIPE_LINK_VITALICIO,
        botadmin=BOT_USERNAME_ADMIN,
    )


if __name__ == "__main__":
    ensure_tables()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
