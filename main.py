# main_webhook.py – Bot de Sinais com Webhook e IA explicativa

from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from telethon.sync import TelegramClient, events
import asyncio, os, re, aiohttp, threading
from hf_openassistant import gerar_resposta_ia

# CONFIGURAÇÃO
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# COMANDOS
def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Bot ativo com IA refinada e Webhook!")

def veredito_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("""⚙️ Critérios Técnicos de Entrada:
- IA ≥ 85%
- Minuto 18–27
- 3+ ataques perigosos recentes
- 1+ chute no gol
- Escanteios ≥ 2
- Vento < 20 m/s
- Histórico gols 1T ≥ 2
- Visitante dominante""")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("veredito", veredito_cmd))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "🏠 Webhook do bot está funcionando"

# ANÁLISE PRINCIPAL
async def analisar(texto, link="https://bet365.com"):
    try:
        jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo.group(1).strip() if jogo else "Times não identificados"

        minuto_match = re.search(r"⏰\s*(\d+)[\"'”]", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia = float(re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto).group(1))
        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        vento = float(vento_match.group(1)) if vento_match else None

        total_perigosos = sum(perigosos)
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7
        total_no_gol = sum(no_gol)
        posse_dominante = posse[0] >= 60 or posse[1] >= 60

        if ia >= 85: criterios.append("IA")
        resumo.append(f"• IA: {ia:.2f}% {'✓' if ia >= 85 else '✘'}")
        if minuto and 18 <= minuto <= 27: criterios.append("Minuto")
        resumo.append(f"• Minuto: {minuto if minuto else 'não encontrado'} {'✓' if minuto and 18 <= minuto <= 27 else '✘'}")
        if total_perigosos >= 12 and desequilibrio: criterios.append("Ataques")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")
        if total_no_gol >= 1: criterios.append("Finalizações")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")
        if sum(escanteios) >= 2: criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")
        if vento is not None and vento < 20: criterios.append("Vento")
        resumo.append(f"• Vento: {vento if vento else 'não encontrado'} m/s {'✓' if vento and vento < 20 else '✘'}")
        if historico >= 2: criterios.append("Histórico")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")
        if posse_dominante: criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Confluência positiva em múltiplos critérios técnicos."
            asyncio.create_task(monitorar_odd(jogo, link))
        elif 1 <= len(criterios) < 3:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios parciais, aguardar evolução."
            asyncio.create_task(monitorar_odd(jogo, link))
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Poucos critérios atendidos."

        msg = f"""{veredito} (Sinal Técnico) – {jogo}

Análise conforme o Prompt Fixo:
{chr(10).join(resumo)}

📌 Conclusão:
{conclusao}

Veredito: {veredito}
Confiança: {confianca}
"""

        try:
            explicacao = await gerar_resposta_ia(msg)
            msg += f"\n\n🧠 Avaliação IA:\n{explicacao}"
        except Exception as e:
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro da IA: {e}"

        bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as erro:
        print(f"❌ Erro na análise: {erro}")

# ESCUTA COM TELETHON
client = TelegramClient('sessao_sinais', API_ID, API_HASH)

@client.on(events.NewMessage())
async def tratar (event):
    if event.chat_id == CHAT_ID_SINAL and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

# INICIAR FLASK E TELETHON
def rodar_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    threading.Thread(target=rodar_flask).start()
    client.start()
    client.run_until_disconnected()
