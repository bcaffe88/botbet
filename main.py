from telethon import TelegramClient, events
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import asyncio, os, re
from keep_alive import keep_alive

# === SECRETS DO RAILWAY ===
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
chat_id_destino = int(os.getenv("CHAT_ID_DESTINO"))
chat_id_sinal = int(os.getenv("CHAT_ID_SINAL"))

bot = Bot(token=bot_token)

# === FUNÇÃO DE ENVIO PARA O GRUPO ===
def enviar_analise(msg):
    try:
        bot.send_message(chat_id=chat_id_destino, text=msg)
        print(f"✅ Análise enviada para chat {chat_id_destino}")
    except Exception as e:
        print(f"❌ [ERRO ENVIO] Falha ao enviar para chat {chat_id_destino}: {e}")

# === COMANDOS INTERATIVOS ===
def start(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id, text="👋 Bot ativo e pronto para refinar sinais!")

def veredito(update: Update, context: CallbackContext):
    texto = (
        "📊 Critérios para ENTRAR:\n"
        "- IA ≥ 85%\n"
        "- Minuto ideal: 18’–22’ (aceitável: 15’–35’)\n"
        "- Ataques perigosos ≥ 12 com desequilíbrio\n"
        "- Chutes ≥ 3 (≥ 2 no gol)\n"
        "- Escanteios ≥ 1\n"
        "- Posse ≥ 60% ou compensação\n"
        "- Vento ideal: 3–8 m/s (ou compensado)"
    )
    context.bot.send_message(chat_id=update.effective_chat.id, text=texto)

def testar(update: Update, context: CallbackContext):
    sinal = """
⚽️ Louisville City x Pittsburgh Riverhounds
⏰ 19” - 1º TEMPO

📲 Link do jogo: https://betanobr.com/?m=live
🌡️ 21.7 °C | ☁ 0% | 💧 39% | 💨 6.75 m/s 
🤖 Inteligência Artificial
OVER 0.5 HT: 87.345%

⚽️ Eventos Casa/Visitante
Ataques: 27/12
Ataques Perigosos: 18/6
Posse de Bola: 63/37
Escanteios: 2/0

🥅 Chutes Casa/Visitante
Total: 4/1
No Gol: 2/0
Fora do Gol: 2/1
"""
    resultado = analisar_sinal(sinal)
    context.bot.send_message(chat_id=update.effective_chat.id, text=resultado)

def testefraco(update: Update, context: CallbackContext):
    sinal = """
⚽️ Time A x Time B
⏰ 10” - 1º TEMPO
🌡️ 25 °C | 💨 11.5 m/s 
🤖 Inteligência Artificial
OVER 0.5 HT: 72.41%

Ataques Perigosos: 9/7
Escanteios: 0/0
Total: 1/2
No Gol: 0/0
"""
    resultado = analisar_sinal(sinal)
    context.bot.send_message(chat_id=update.effective_chat.id, text=resultado)

def testevento(update: Update, context: CallbackContext):
    sinal = """
⚽️ Jogo Ventoso FC x Calmaria United
⏰ 22” - 1º TEMPO
💨 12.4 m/s 
🤖 Inteligência Artificial
OVER 0.5 HT: 80.1%

Ataques Perigosos: 15/7
Escanteios: 2/1
Total: 4/3
No Gol: 2/1
Posse de Bola: 55/45
"""
    resultado = analisar_sinal(sinal)
    context.bot.send_message(chat_id=update.effective_chat.id, text=resultado)

def chat_id(update: Update, context: CallbackContext):
    chat = update.effective_chat
    context.bot.send_message(chat_id=chat.id, text=f"🆔 ID deste grupo: `{chat.id}`", parse_mode="Markdown")

# === REGISTRAR COMANDOS ===
updater = Updater(token=bot_token, use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("veredito", veredito))
dispatcher.add_handler(CommandHandler("testar", testar))
dispatcher.add_handler(CommandHandler("testefraco", testefraco))
dispatcher.add_handler(CommandHandler("testevento", testevento))
dispatcher.add_handler(CommandHandler("id", chat_id))

# === LÓGICA DE ANÁLISE ===
def analisar_sinal(texto):
    try:
        ia = float(re.search(r'OVER 0\.5 HT:\s*([\d.]+)%', texto).group(1))
        minuto = int(re.search(r'⏰\s*(\d+)[”\']', texto).group(1))
        vento = float(re.search(r'💨\s*([\d.]+)\s*m/s', texto).group(1))
        perigosos = list(map(int, re.findall(r'Ataques Perigosos:\s*(\d+)/(\d+)', texto)[0]))
        total_perigosos = sum(perigosos)
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7
        chutes = list(map(int, re.findall(r'Total:\s*(\d+)/(\d+)', texto)[0]))
        no_gol = list(map(int, re.findall(r'No Gol:\s*(\d+)/(\d+)', texto)[0]))
        total_chutes = sum(chutes)
        total_no_gol = sum(no_gol)
        escanteios = sum(map(int, re.findall(r'Escanteios:\s*(\d+)/(\d+)', texto)[0]))
        posse = list(map(int, re.findall(r'Posse de Bola:\s*(\d+)/(\d+)', texto)[0]))
        posse_dominante = posse[0] >= 60 or posse[1] >= 60

        justificativa = []

        if ia >= 85 and 15 <= minuto <= 35 and total_perigosos >= 12 and desequilibrio and total_chutes >= 3 and total_no_gol >= 2 and escanteios >= 1 and (posse_dominante or total_chutes >= 4):
            veredito = "✅ ENTRAR"
            justificativa.append(f"IA: {ia:.2f}% | Min: {minuto} | Perigosos: {perigosos[0]}x{perigosos[1]}")
            justificativa.append(f"Chutes: {total_chutes} (no gol: {total_no_gol}) | Escanteios: {escanteios}")
            justificativa.append(f"Posse: {posse[0]}x{posse[1]} | Vento: {vento} m/s")
        elif vento > 10 and ia < 85:
            if total_no_gol >= 2 and escanteios >= 1 and desequilibrio:
                veredito = "✅ ENTRAR"
                justificativa.append("⚠️ Vento alto compensado por chutes e escanteio")
            else:
                veredito = "❌ NÃO ENTRAR"
                justificativa.append("Vento alto + IA baixa sem compensação")
        elif 0 < minuto < 15:
            veredito = "⏳ AGUARDAR"
            justificativa.append(f"Aguardando minuto ideal (atual: {minuto}’)")
        else:
            veredito = "❌ NÃO ENTRAR"
            justificativa.append("Critérios insuficientes")

        return f"{veredito}\n" + "\n".join(justificativa)

    except Exception as e:
        return f"❌ ERRO NA ANÁLISE\n{e}"

# === ESCUTA DE SINAL REAL ===
client = TelegramClient('sessao_sinais', api_id, api_hash)

@client.on(events.NewMessage())
async def tratar_sinal(event):
    print(f"📡 Mensagem recebida do chat {event.chat_id}")
    if event.chat_id != chat_id_sinal:
        print(f"❌ Chat ignorado: {event.chat_id} (esperando: {chat_id_sinal})")
        return

    if 'OVER 0.5 HT' in event.message.message:
        print("📥 Sinal OVER 0.5 HT captado!")
        try:
            resultado = analisar_sinal(event.message.message)
            print("✅ Sinal analisado!")
            enviar_analise(resultado)
        except Exception as e:
            print(f"❌ Erro ao processar sinal: {e}")

# === INÍCIO DO BOT ===
async def main():
    try:
        print("🔄 Iniciando cliente Telegram...")
        await client.start()
        print("✅ Cliente Telegram conectado")
        keep_alive()
        print("✅ Servidor Flask iniciado")
        updater.start_polling()
        print("✅ Bot Telegram iniciado")
        print(f"🎯 Monitorando chat ID: {chat_id_sinal}")
        print(f"📤 Enviando para chat ID: {chat_id_destino}")
        print("🤖 Bot ouvindo sinais e comandos...")
        await client.run_until_disconnected()
    except Exception as e:
        print(f"❌ Erro crítico: {e}")

asyncio.run(main())
