import requests
import os
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
import aiohttp

API_FOOTBALL_KEY = os.getenv("FOOTBALL_API_KEY")
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
BASE_URL = "https://v3.football.api-sports.io"

def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

async def verificar_gol_ht(nome_jogo):
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/fixtures?date={data_hoje}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as resp:
                data = await resp.json()
                for item in data.get("response", []):
                    casa = item["teams"]["home"]["name"]
                    fora = item["teams"]["away"]["name"]
                    halftime = item["score"]["halftime"]
                    nome_match = f"{casa} x {fora}"
                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime["home"] or 0) + (halftime["away"] or 0)
                        return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
    except Exception as e:
        print("❌ Erro ao verificar gol no HT:", e)
    return "⏳ NÃO LOCALIZADO"

def buscar_team_id_completo_por_liga(nome_time, liga_nome="Primera Division", pais="Costa Rica"):
    nome_limpo = normalizar(nome_time)
    try:
        liga_url = f"{BASE_URL}/leagues?search={liga_nome}&country={pais}"
        liga_resp = requests.get(liga_url, headers=HEADERS)
        ligas = liga_resp.json().get("response", [])
        if not ligas:
            print(f"❌ Nenhuma liga encontrada: {liga_nome} ({pais})")
            return None
        liga_id = ligas[0]["league"]["id"]
        temporada = ligas[0]["seasons"][-1]["year"]
        print(f"✅ Liga encontrada: {liga_id} / Temporada: {temporada}")
        teams_url = f"{BASE_URL}/teams?league={liga_id}&season={temporada}"
        teams_resp = requests.get(teams_url, headers=HEADERS)
        times = teams_resp.json().get("response", [])
        if not times:
            print(f"❌ Nenhum time listado para liga {liga_id}")
            return None
        melhores = sorted(
            times,
            key=lambda x: similaridade(nome_limpo, normalizar(x["team"]["name"])),
            reverse=True
        )
        melhor = melhores[0]
        score = similaridade(nome_limpo, normalizar(melhor["team"]["name"]))
        if score >= 0.5:
            print(f"✅ Match por liga: {nome_time} ≈ {melhor['team']['name']} ({score:.2f})")
            return melhor["team"]["id"]
    except Exception as e:
        print(f"❌ Erro na busca por liga: {e}")
    return None

def buscar_team_id(nome_time):
    def tentar_buscar(termo):
        try:
            url = f"{BASE_URL}/teams?search={termo}"
            resp = requests.get(url, headers=HEADERS)
            return resp.json().get("response", [])
        except Exception as e:
            print(f"❌ Erro na busca direta: {e}")
            return []
    nome_limpo = normalizar(nome_time.strip())
    dados = tentar_buscar(nome_time)
    if not dados:
        dados = tentar_buscar(f"Club {nome_time}")
    if not dados:
        return buscar_team_id_completo_por_liga(nome_time)
    melhores = sorted(
        dados,
        key=lambda x: similaridade(nome_limpo, normalizar(x["team"]["name"])),
        reverse=True
    )
    melhor = melhores[0]
    score = similaridade(nome_limpo, normalizar(melhor["team"]["name"]))
    return melhor["team"]["id"] if score >= 0.5 else None

def gols_primeiro_tempo(team_id):
    url = f"{BASE_URL}/fixtures?team={team_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        jogos = resp.json()['response']
        return sum(1 for j in jogos if j['score']['halftime']['home'] > 0 or j['score']['halftime']['away'] > 0)
    except Exception as e:
        print(f"❌ Erro gols 1T: {e}")
        return 0

def media_gols_liga(league_id, season):
    url = f"{BASE_URL}/fixtures?league={league_id}&season={season}&last=10"
    try:
        resp = requests.get(url, headers=HEADERS)
        jogos = resp.json()['response']
        if not jogos:
            return 0
        total = sum(j['goals']['home'] + j['goals']['away'] for j in jogos)
        return round(total / len(jogos), 2)
    except Exception as e:
        print(f"❌ Erro média da liga: {e}")
        return 0

def confrontos_diretos(team1_id, team2_id):
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        jogos = resp.json()['response']
        return [
            f"{j['teams']['home']['name']} {j['score']['halftime']['home']}x{j['score']['halftime']['away']} {j['teams']['away']['name']}"
            for j in jogos
        ]
    except Exception as e:
        print(f"❌ Erro confrontos diretos: {e}")
        return []

def buscar_liga_time(team_id):
    url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
    try:
        resp = requests.get(url, headers=HEADERS)
        jogos = resp.json()['response']
        if jogos:
            liga = jogos[0]['league']
            return liga['id'], liga['season']
    except Exception as e:
        print(f"❌ Erro buscar liga time: {e}")
    return None, None

def resumo_estatistico(nome_mandante, nome_visitante):
    try:
        team1_id = buscar_team_id(nome_mandante)
        team2_id = buscar_team_id(nome_visitante)
        texto_resumo = []
        if team1_id:
            texto_resumo.append(f"🏠 {nome_mandante}: {gols_primeiro_tempo(team1_id)}/5 jogos com gol no 1T")
        if team2_id:
            texto_resumo.append(f"🚶 {nome_visitante}: {gols_primeiro_tempo(team2_id)}/5 jogos com gol no 1T")
        if team1_id and team2_id:
            confrontos = confrontos_diretos(team1_id, team2_id)
            gols_confronto = sum(1 for c in confrontos if "x" in c and int(c.split("x")[0].split()[-1]) + int(c.split("x")[1].split()[0]) > 0)
            texto_resumo.append(f"⚔️ Confrontos diretos: {gols_confronto}/5 com gol no 1T")
        liga_id, temporada = buscar_liga_time(team1_id)
        if liga_id and temporada:
            media = media_gols_liga(liga_id, temporada)
            texto_resumo.append(f"📊 Média de gols da liga: {media}")
        else:
            texto_resumo.append("📊 Média de gols da liga: indisponível")
        return "\n".join(texto_resumo)
    except Exception as e:
        print(f"❌ Erro resumo estatístico: {e}")
        return "⚠️ Histórico indisponível"

def resumo_estendido(nome_time):
    try:
        team_id = buscar_team_id(nome_time)
        if not team_id:
            return f"⚠️ Time não encontrado: {nome_time}"
        url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
        resp = requests.get(url, headers=HEADERS)
        jogo = resp.json()['response'][0]
        liga = jogo['league']
        media = media_gols_liga(liga['id'], liga['season'])
        tendencia = "🔥 Liga com tendência OVER" if media >= 2.2 else "⚠️ Liga tende ao UNDER"
        return (
            f"🏆 {liga['name']} ({liga['country']}) – Temporada {liga['season']}\n"
            f"📊 Média de gols: {media}\n"
            f"{tendencia}"
        )
    except Exception as e:
        return f"⚠️ Erro ao buscar info da liga de {nome_time}"
