# main.py - Sinais refinados com verificação automática de gol HT via Sofascore

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import os, re, asyncio, aiohttp, time, unicodedata

# Configurações
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))

bot = Bot(token=BOT_TOKEN)

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo!")

# Normalização de texto
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

# Verifica se houve gol no 1º tempo via Sofascore
from datetime import datetime

async def verificar_gol_ht(nome_jogo):
    try:
        # 1. Tenta buscar nos jogos ao vivo
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.sofascore.com/api/v1/sport/football/events/live") as resp:
                data = await resp.json()
                eventos = data.get("events", [])

                print("🧩 Jogos AO VIVO encontrados:")
                for evento in eventos:
                    casa = evento["homeTeam"]["name"]
                    fora = evento["awayTeam"]["name"]
                    nome_match = f"{casa} x {fora}"
                    print(f"- {nome_match}")

                    if normalizar(nome_jogo) in normalizar(nome_match):
                        gols_1t = evento.get("homeScore", {}).get("period1", 0) + evento.get("awayScore", {}).get("period1", 0)
                        print(f"🔍 Comparando: {nome_jogo} ≈ {nome_match} | Gols 1T: {gols_1t}")
                        return "✅ BATEU" if gols_1t >= 1 else "❌ NÃO BATEU"

        # 2. Se não encontrar, busca nos jogos do dia
        print("🔄 Não encontrado ao vivo. Verificando jogos do dia (fallback)...")
        hoje = datetime.now().strftime("%Y-%m-%d")
        url_fallback = f"https://api.sofascore.com/api/v1/sport/football/events/{hoje}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url_fallback) as resp:
                data = await resp.json()
                eventos = data.get("events", [])

                print(f"📅 Jogos do dia {hoje}:")
                for evento in eventos:
                    casa = evento["homeTeam"]["name"]
                    fora = evento["awayTeam"]["name"]
                    nome_match = f"{casa} x {fora}"
                    print(f"- {nome_match}")

                    if normalizar(nome_jogo) in normalizar(nome_match):
                        gols_1t = evento.get("homeScore", {}).get("period1", 0) + evento.get("awayScore", {}).get("period1", 0)
                        print(f"🔍 Comparando (fallback): {nome_jogo} ≈ {nome_match} | Gols 1T: {gols_1t}")
                        return "✅ BATEU" if gols_1t >= 1 else "❌ NÃO BATEU"

        print("⚠️ Jogo não localizado ao vivo nem nos jogos do dia.")

    except Exception as e:
        print("❌ Erro ao verificar Sofascore (com fallback):", e)

    return "⏳ NÃO LOCALIZADO"

# Análise do sinal
async def analisar(texto):
    print("📊 Iniciando análise do sinal")
    try:
        jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = jogo.group(1).strip() if jogo else "Times não identificados"
        print(f"📌 Jogo detectado: {jogo}")

        minuto_match = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(minuto_match.group(1)) if minuto_match else None

        ia_match = re.search(r"OVER 0\.5 HT:\s*([\d.]+)%", texto)
        ia = float(ia_match.group(1)) if ia_match else None

        match_perigosos = re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)
        perigosos = list(map(int, match_perigosos[0])) if match_perigosos else [0, 0]

        match_posse = re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)
        posse = list(map(int, match_posse[0])) if match_posse else [0, 0]

        match_escanteios = re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)
        escanteios = list(map(int, match_escanteios[0])) if match_escanteios else [0, 0]

        match_no_gol = re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)
        no_gol = list(map(int, match_no_gol[0])) if match_no_gol else [0, 0]

        match_chutes = re.findall(r"Total:\s*(\d+)/(\d+)", texto)
        chutes = list(map(int, match_chutes[0])) if match_chutes else [0, 0]

        vento_match = re.search(r"🌬️\s*([\d.]+)\s*m/s", texto)
        vento = float(vento_match.group(1)) if vento_match else None

        criterios, resumo = [], []
        pontos = 0

        if ia and ia >= 75:
            criterios.append("IA")
            pontos += 2
        resumo.append(f"• IA: {ia} {'✓' if ia and ia >= 80 else '✗'}")

        if minuto and 16 <= minuto <= 22:
            criterios.append("Minuto ideal")
            pontos += 1

        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            criterios.append("Ataques perigosos")
            pontos += 2

        if sum(no_gol) >= 1:
            criterios.append("Finalizações no gol")
            pontos += 2

        if sum(escanteios) >= 2:
            criterios.append("Escanteios")
            pontos += 1

        if vento and vento < 15:
            criterios.append("Vento ideal")
            pontos += 1

        if sum(chutes) >= 4:
            criterios.append("Chutes totais")
            pontos += 1

        if posse[0] >= 60 or posse[1] >= 60:
            criterios.append("Posse dominante")
            pontos += 1

        if pontos >= 7:
            veredito = "ENTRAR ✅"
            conclusao = "100.00."

            msg = f"""⚽️ {veredito}
🏟️ {jogo}
🤖 OVERBOT VIP:
{chr(10).join(resumo)}
Responsabilidade: {conclusao}"""

            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)

            # Espera 25 minutos
            await asyncio.sleep(1500)
            resultado = await verificar_gol_ht(jogo)

            if resultado == "✅ BATEU":
                resultado_final = "G R E E N ✅✅✅✅✅✅✅✅✅✅."
            elif resultado == "❌ NÃO BATEU":
                resultado_final = "R E D ❌."
            else:
                resultado_final = "⏳ Resultado do sinal: *Não foi possível localizar o jogo.*"

            msg_editado = f"""{msg}

{resultado_final}"""

            await bot.edit_message_text(
                chat_id=CHAT_ID_DESTINO,
                message_id=msg_enviada.message_id,
                text=msg_editado,
                parse_mode="Markdown"
            )
        else:
            print("❌ Veredito não é 'ENTRAR'. Nenhum envio será feito.")

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# TELETHON
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    print(f"📨 Mensagem recebida de {event.chat_id}:")
    print(f"🔍 CHAT_ID recebido: {event.chat_id}")
    print(event.message.message)

    if str(event.chat_id) == str(CHAT_ID_SINAL) and "OVER 0.5 HT" in event.message.message:
        print("✅ Sinal detectado, enviando para análise.")
        await analisar(event.message.message)
    else:
        print("⚠️ Mensagem ignorada (ID ou palavra-chave não conferem).")

# Inicialização
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    client.start()
    app.run_polling()
