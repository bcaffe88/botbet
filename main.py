import os
import re
import unicodedata
import asyncio
from datetime import datetime
from difflib import SequenceMatcher

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient, events
import aiohttp

from estatisticas_time import buscar_team_id, gols_primeiro_tempo, media_gols_liga, confrontos_diretos

# CONFIGURAÇÕES
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHAT_ID_SINAL = int(os.getenv("CHAT_ID_SINAL"))
CHAT_ID_DESTINO = int(os.getenv("CHAT_ID_DESTINO"))
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

bot = Bot(token=BOT_TOKEN)

# UTILITÁRIOS
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

# API-FOOTBALL - Verifica gol no HT
async def verificar_gol_ht(nome_jogo):
    headers = { "x-apisports-key": FOOTBALL_API_KEY }
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                jogos = data.get("response", [])
                for item in jogos:
                    teams = item["teams"]
                    halftime = item["score"]["halftime"]
                    casa = teams["home"]["name"]
                    fora = teams["away"]["name"]
                    nome_match = f"{casa} x {fora}"
                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime["home"] or 0) + (halftime["away"] or 0)
                        return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
    except Exception as e:
        print("❌ Erro ao consultar API-Football:", e)
    return "⏳ NÃO LOCALIZADO"

# Pontuação estatística histórica
async def pontuacao_estatistica_histórica(nome_mandante, nome_visitante):
    pontos = 0
    try:
        team1_id = buscar_team_id(nome_mandante)
        team2_id = buscar_team_id(nome_visitante)
        if team1_id and team2_id:
            gols_mandante = gols_primeiro_tempo(team1_id)
            gols_visitante = gols_primeiro_tempo(team2_id)
            if gols_mandante >= 3: pontos += 1
            if gols_visitante >= 3: pontos += 1
            confrontos = confrontos_diretos(team1_id, team2_id)
            gols_confronto_1t = sum(1 for c in confrontos if "x" in c and int(c.split("x")[0].split()[-1]) + int(c.split("x")[1].split()[0]) > 0)
            if gols_confronto_1t >= 2: pontos += 1
        return pontos
    except Exception as e:
        print(f"❌ Erro na pontuação histórica: {e}")
        return 0

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot de sinais refinados ativo!")

# Veredito após 25 minutos
async def tarefa_veredito(jogo, msg_original):
    await asyncio.sleep(1500)
    resultado = await verificar_gol_ht(jogo)
    resultado_final = "G R E N N ✅✅✅✅✅✅✅✅✅✅ " if resultado == "✅ BATEU" else ("R E D ❌" if resultado == "❌ NÃO BATEU" else "⏳ BUSCANDO RESULTADO*")
    novo_texto = f"""{msg_original.text}\n\n{resultado_final}"""
    await bot.edit_message_text(chat_id=CHAT_ID_DESTINO, message_id=msg_original.message_id, text=novo_texto, parse_mode="Markdown")

# Análise do sinal
# Análise do sinal com logs detalhados
async def analisar(texto):
    try:
        print("📊 Iniciando análise do sinal")

        # Extração segura
        match_jogo = re.search(r'⚽️\s*(.+)', texto)
        jogo = match_jogo.group(1).strip() if match_jogo else None
        if not jogo:
            print("❌ Jogo não identificado.")
            return

        match_minuto = re.search(r"⏰\s*(\d+)", texto)
        minuto = int(match_minuto.group(1)) if match_minuto else None

        match_ia = re.search(r"OVER 0\\.5 HT:\\s*([\\d.]+)%", texto)
        ia = float(match_ia.group(1)) if match_ia else None

        perigosos = list(map(int, re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Ataques Perigosos:\s*(\d+)/(\d+)", texto) else [0, 0]
        posse = list(map(int, re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Posse de Bola:\s*(\d+)/(\d+)", texto) else [0, 0]
        escanteios = list(map(int, re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Escanteios:\s*(\d+)/(\d+)", texto) else [0, 0]
        no_gol = list(map(int, re.findall(r"No Gol:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"No Gol:\s*(\d+)/(\d+)", texto) else [0, 0]
        chutes = list(map(int, re.findall(r"Total:\s*(\d+)/(\d+)", texto)[0])) if re.findall(r"Total:\s*(\d+)/(\d+)", texto) else [0, 0]
        match_vento = re.search(r"🌬️\s*([\d.]+)\s*m/s", texto)
        vento = float(match_vento.group(1)) if match_vento else None

        criterios, resumo = [], []
        pontos = 0

        if ia and ia >= 75:
            pontos += 2
            criterios.append("IA")
            resumo.append(f"• IA: {ia}%")
            print("✅ IA alta - +2")
        else:
            print("❌ IA insuficiente")

        if minuto and 16 <= minuto <= 22:
            pontos += 1
            criterios.append("Minuto ideal")
            print("✅ Minuto ideal - +1")
        else:
            print(f"❌ Minuto fora da janela (valor: {minuto})")

        if sum(perigosos) >= 10 and abs(perigosos[0] - perigosos[1]) >= 7:
            pontos += 2
            criterios.append("Ataques perigosos")
            print(f"✅ Ataques perigosos: {perigosos} - +2")
        else:
            print(f"❌ Ataques perigosos insuficientes: {perigosos}")

        if sum(no_gol) >= 1:
            pontos += 2
            criterios.append("Finalizações no gol")
            print(f"✅ Finalizações no gol: {no_gol} - +2")
        else:
            print(f"❌ Nenhuma finalização no gol: {no_gol}")

        if sum(escanteios) >= 2:
            pontos += 1
            criterios.append("Escanteios")
            print(f"✅ Escanteios suficientes: {escanteios} - +1")
        else:
            print(f"❌ Escanteios insuficientes: {escanteios}")

        if vento and vento < 15:
            pontos += 1
            criterios.append("Vento ideal")
            print(f"✅ Vento ideal: {vento} m/s - +1")
        else:
            print(f"⚠️ Vento alto ou não informado: {vento}")

        if sum(chutes) >= 4:
            pontos += 1
            criterios.append("Chutes totais")
            print(f"✅ Chutes totais: {chutes} - +1")
        else:
            print(f"❌ Chutes insuficientes: {chutes}")

        if posse[0] >= 60 or posse[1] >= 60:
            pontos += 1
            criterios.append("Posse dominante")
            print(f"✅ Posse dominante: {posse} - +1")
        else:
            print(f"❌ Posse não dominante: {posse}")

        print(f"🧮 Pontuação parcial: {pontos} pontos")

        # Pontuação histórica adicional
        try:
            nome_mandante, nome_visitante = jogo.split(" x ")
            pontos_hist = await pontuacao_estatistica_histórica(nome_mandante, nome_visitante)
            pontos += pontos_hist
            print(f"🧠 Pontos históricos: +{pontos_hist}")
        except Exception as e:
            print(f"⚠️ Erro ao calcular pontos históricos: {e}")

        print(f"🔚 Pontuação final: {pontos} pontos")

        if pontos >= 9:
            veredito = "ENTRAR ✅"
            conclusao = "OVER 0.5 HT."
            msg = f"""⚽️ {veredito} 
🏟 {jogo}
🤖 OVERBOT VIP:
{chr(10).join(resumo)}
▶ ENTRADA: {conclusao}"""
            msg_enviada = await bot.send_message(chat_id=CHAT_ID_DESTINO, text=msg)
            asyncio.create_task(tarefa_veredito(jogo, msg_enviada))
        else:
            print("❌ Veredito não é 'ENTRAR'. Nenhum envio será feito.")

    except Exception as e:
        print("❌ Erro ao analisar:", e)

# MONITORAMENTO TELEGRAM
client = TelegramClient("sessao_sinais", API_ID, API_HASH)

@client.on(events.NewMessage())
async def escutar(event):
    if str(event.chat_id) == str(CHAT_ID_SINAL) and "OVER 0.5 HT" in event.message.message:
        await analisar(event.message.message)

# INICIALIZAÇÃO
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    client.start()
    app.run_polling()
