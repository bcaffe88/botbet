# main.py - Webhook + Telethon + IA Refinada

from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from telethon.sync import TelegramClient, events
import os, re, asyncio, aiohttp, time, threading
from ia_openai import gerar_resposta_ia

# VARIÁVEIS DE AMBIENTE
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))  # canal ou grupo
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))  # onde envia o veredito
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# OBJETOS PRINCIPAIS
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# COMANDOS
def start(update: Update, context: CallbackContext):
    update.message.reply_text("🤖 Bot de sinais refinados ativo com Webhook!")

def veredito_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("""⚙️ Critérios Técnicos de Entrada:
- IA ≥ 85%
- Minuto 18–27
- 3+ ataques perigosos recentes
- 1+ chute no gol
- Escanteios ≥ 2
- Vento < 20 m/s
- Histórico gols 1T ≥ 2 (últimos 5 jogos)
- Visitante dominante
Entrada apenas com 3 ou mais critérios.""")

def teste_ia(update, context):
    texto_usuario = update.message.text
    resposta = gerar_resposta_ia(texto_usuario)
    update.message.reply_text(f"🧠 IA respondeu:\n\n{resposta}")
        
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("veredito", veredito_cmd))
dispatcher.add_handler(CommandHandler("testeia", teste_ia))

# ROTAS FLASK
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def home():
    return "🏠 Webhook online"

# FUNÇÃO MONITORAMENTO DE ODD +0.5
async def monitorar_odd(jogo, link, timeout=300):
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    for partida in data:
                        nome = partida.get("home_team", "") + " x " + partida.get("away_team", "")
                        if jogo.lower() in nome.lower():
                            for bk in partida.get("bookmakers", []):
                                for mkt in bk.get("markets", []):
                                    if mkt["key"] == "totals":
                                        for linha in mkt["outcomes"]:
                                            if linha["point"] == 0.5 and linha["name"] == "Over":
                                                odd = linha["price"]
                                                if odd >= 1.50:
                                                    msg = f"⚽️ ENTRADA VALIDADA\n\n📌 Jogo: {nome}\n📈 Odd +0.5 HT: {odd}\n💰 Valor sugerido: R$15"
                                                    bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg,
                                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👉 Apostar agora", url=link)]]))
                                                    return
        except Exception as e:
            print("❌ Erro monitorando odd:", e)
        await asyncio.sleep(30)

# FUNÇÃO DE ANÁLISE DO SINAL
async def analisar(texto):
    try:
        jogo_match = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo_match.group(1).strip() if jogo_match else "Times não identificados"

        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None

        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0]))
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0]))
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0]))
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0]))
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0]))
        vento_match = re.search(r"💨\s*([\d.]+)\s*m/s", texto)
        vento = float(vento_match.group(1)) if vento_match else None

        total_perigosos = sum(perigosos)
        total_no_gol = sum(no_gol)
        posse_dominante = posse[0] >= 60 or posse[1] >= 60
        desequilibrio = abs(perigosos[0] - perigosos[1]) >= 7

        historico = 2  # fixo por enquanto

        criterios = []
        resumo = []

        if ia and ia >= 85:
            criterios.append("IA")
        resumo.append(f"• IA: {ia if ia else 'não encontrado'} {'✓' if ia and ia >= 85 else '✘'}")

        if minuto and 18 <= minuto <= 27:
            criterios.append("Minuto ideal")
        resumo.append(f"• Minuto: {minuto if minuto else 'não encontrado'} {'✓' if minuto and 18 <= minuto <= 27 else '✘'}")

        if total_perigosos >= 12 and desequilibrio:
            criterios.append("Ataques perigosos")
        resumo.append(f"• Ataques perigosos: {perigosos[0]} x {perigosos[1]} {'✓' if total_perigosos >= 12 and desequilibrio else '✘'}")

        if total_no_gol >= 1:
            criterios.append("Finalizações no gol")
        resumo.append(f"• Finalizações no gol: {no_gol[0]} x {no_gol[1]} {'✓' if total_no_gol >= 1 else '✘'}")

        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
        resumo.append(f"• Escanteios: {escanteios[0]} x {escanteios[1]} {'✓' if sum(escanteios) >= 2 else '✘'}")

        if vento is not None and vento < 20:
            criterios.append("Vento favorável")
        resumo.append(f"• Vento: {vento} m/s {'✓' if vento < 20 else '✘'}")

        if historico >= 2:
            criterios.append("Histórico de gols 1T")
        resumo.append(f"• Histórico recente da equipe dominante: {historico} {'✓' if historico >= 2 else '✘'}")

        if posse_dominante:
            criterios.append("Posse dominante")
        resumo.append(f"• Posse: {posse[0]}% x {posse[1]}% {'✓' if posse_dominante else '✘'}")

        if len(criterios) >= 3:
            veredito = "✅ ENTRAR"
            confianca = "Alta"
            conclusao = "Confluência positiva em múltiplos critérios técnicos."
            asyncio.create_task(monitorar_odd(jogo, "https://bet365.com"))
        elif 1 <= len(criterios) < 3:
            veredito = "⏳ AGUARDAR"
            confianca = "Média"
            conclusao = "Critérios parciais, aguardar evolução."
        else:
            veredito = "❌ NÃO ENTRAR"
            confianca = "Baixa"
            conclusao = "Sinais insuficientes."

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
            msg += f"\n\n🧠 Avaliação IA:\n❌ Erro: {e}"

        await asyncio.to_thread(bot.send_message, chat_id=CHAT_ID_DESTINO, text=msg)

    except Exception as e:
        print(f"❌ Erro ao analisar: {e}")

# TELETHON ESCUTA
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def tratar(event):
    print(f"📩 Nova mensagem recebida: {event.chat_id}")
    print(f"🔍 Conteúdo da mensagem:\n{event.message.message}")

    if event.chat_id != CHAT_ID_SINAL:
        print(f"🔍 CHAT_ID recebido: {event.chat_id}")
        print(f"🔐 CHAT_ID esperado: {CHAT_ID_SINAL}")
        return

    if re.search(r"OVER\s*0\.5\s*HT", event.message.message, re.IGNORECASE):
        print("✅ Palavra-chave detectada, sinal será analisado.")
        await analisar(event.message.message)
    else:
        print("⚠️ Mensagem ignorada (sem OVER 0.5 HT).")

# RODAR FLASK + TELETHON
def rodar_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    threading.Thread(target=rodar_flask).start()
    client.start()
    client.run_until_disconnected()
