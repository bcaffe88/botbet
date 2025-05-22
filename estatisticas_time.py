import requests
import os
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
import aiohttp

API_FOOTBALL_KEY = os.getenv("FOOTBALL_API_KEY")
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
BASE_URL = "https://v3.football.api-sports.io"

# Mapeamento manual de nomes comuns para nomes oficiais na API
NOMES_OFICIAIS = {
    "Alajuelense": "Liga Deportiva Alajuelense",
    "Saprissa": "Deportivo Saprissa",
    "Deportivo Saprissa": "Deportivo Saprissa",
}

def normalizar(texto):
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8").lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

async def verificar_gol_ht(nome_jogo):
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/fixtures?date={data_hoje}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    print(f"❌ Erro na API: Status {resp.status}")
                    return "⏳ NÃO LOCALIZADO"
                
                data = await resp.json()
                if "response" not in data:
                    print("❌ Resposta da API sem campo 'response'")
                    return "⏳ NÃO LOCALIZADO"
                
                for item in data["response"]:
                    if not all(key in item for key in ["teams", "score"]):
                        continue
                        
                    casa = item["teams"]["home"]["name"]
                    fora = item["teams"]["away"]["name"]
                    halftime = item["score"]["halftime"]
                    
                    if halftime is None:
                        continue
                        
                    nome_match = f"{casa} x {fora}"
                    if similaridade(normalizar(nome_jogo), normalizar(nome_match)) > 0.75:
                        gols_ht = (halftime.get("home", 0) or 0) + (halftime.get("away", 0) or 0)
                        return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
    except Exception as e:
        print(f"❌ Erro ao consultar API-Football: {str(e)}")
    return "⏳ NÃO LOCALIZADO"

def buscar_team_id(nome_time, pais="Costa Rica"):
    nome_limpo = normalizar(nome_time)
    nome_oficial = NOMES_OFICIAIS.get(nome_time.strip(), nome_time.strip())

    try:
        url = f"{BASE_URL}/teams?search={nome_oficial}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro na API: Status {resp.status_code}")
            return None
            
        dados = resp.json().get("response", [])
        if dados:
            melhores = sorted(
                dados, 
                key=lambda x: similaridade(nome_limpo, normalizar(x["team"]["name"])), 
                reverse=True
            )
            score = similaridade(nome_limpo, normalizar(melhores[0]["team"]["name"]))
            if score >= 0.5:
                print(f"✅ Match encontrado: {nome_time} ≈ {melhores[0]['team']['name']} ({score:.2f})")
                return melhores[0]["team"]["id"]
    except Exception as e:
        print(f"❌ Erro na busca por {nome_time}: {str(e)}")

    print(f"⚠️ Nenhum match encontrado para: {nome_time}")
    return None

def gols_primeiro_tempo(team_id):
    if not team_id:
        return 0
        
    url = f"{BASE_URL}/fixtures?team={team_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro na API: Status {resp.status_code}")
            return 0
            
        data = resp.json()
        if "response" not in data:
            print("❌ Resposta da API sem campo 'response'")
            return 0
            
        jogos = data["response"]
        return sum(1 for j in jogos 
                  if j.get("score", {}).get("halftime", {}) 
                  and (j["score"]["halftime"].get("home", 0) > 0 
                       or j["score"]["halftime"].get("away", 0) > 0))
    except Exception as e:
        print(f"❌ Erro ao buscar gols 1T: {str(e)}")
        return 0

def media_gols_liga(league_id, season):
    if not league_id or not season:
        return 0
        
    url = f"{BASE_URL}/fixtures?league={league_id}&season={season}&last=10"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro na API: Status {resp.status_code}")
            return 0
            
        data = resp.json()
        if "response" not in data:
            print("❌ Resposta da API sem campo 'response'")
            return 0
            
        jogos = data["response"]
        if not jogos:
            return 0
            
        total = sum(j.get("goals", {}).get("home", 0) + j.get("goals", {}).get("away", 0) 
                for j in jogos)
        return round(total / len(jogos), 2)
    except Exception as e:
        print(f"❌ Erro média da liga: {str(e)}")
        return 0

def confrontos_diretos(team1_id, team2_id):
    if not team1_id or not team2_id:
        return []
        
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}&last=5"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro na API: Status {resp.status_code}")
            return []
            
        data = resp.json()
        if "response" not in data:
            print("❌ Resposta da API sem campo 'response'")
            return []
            
        jogos = data["response"]
        return [
            f"{j['teams']['home']['name']} {j['score']['halftime']['home']}x{j['score']['halftime']['away']} {j['teams']['away']['name']}"
            for j in jogos 
            if all(key in j for key in ["teams", "score", "halftime"])
        ]
    except Exception as e:
        print(f"❌ Erro confrontos diretos: {str(e)}")
        return []

def buscar_liga_time(team_id):
    if not team_id:
        return None, None
        
    url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"❌ Erro na API: Status {resp.status_code}")
            return None, None
            
        data = resp.json()
        if "response" not in data or not data["response"]:
            print("❌ Resposta da API sem dados")
            return None, None
            
        jogo = data["response"][0]
        if "league" not in jogo:
            print("❌ Jogo sem informação de liga")
            return None, None
            
        liga = jogo["league"]
        return liga.get("id"), liga.get("season")
    except Exception as e:
        print(f"❌ Erro buscar liga time: {str(e)}")
        return None, None

def resumo_estatistico(nome_mandante, nome_visitante):
    try:
        team1_id = buscar_team_id(nome_mandante)
        team2_id = buscar_team_id(nome_visitante)
        texto_resumo = []

        if team1_id:
            gols_ht = gols_primeiro_tempo(team1_id)
            texto_resumo.append(f"🏠 {nome_mandante}: {gols_ht}/5 jogos com gol no 1T")
            
        if team2_id:
            gols_ht = gols_primeiro_tempo(team2_id)
            texto_resumo.append(f"🚶 {nome_visitante}: {gols_ht}/5 jogos com gol no 1T")

        if team1_id and team2_id:
            confrontos = confrontos_diretos(team1_id, team2_id)
            gols_confronto = sum(
                1 for c in confrontos 
                if "x" in c 
                and int(c.split("x")[0].split()[-1]) + int(c.split("x")[1].split()[0]) > 0
            )
            texto_resumo.append(f"⚔️ Confrontos diretos: {gols_confronto}/5 com gol no 1T")

        liga_id, temporada = buscar_liga_time(team1_id or team2_id)
        if liga_id and temporada:
            media = media_gols_liga(liga_id, temporada)
            texto_resumo.append(f"📊 Média de gols da liga: {media}")
        else:
            texto_resumo.append("📊 Média de gols da liga: indisponível")

        return "\n".join(texto_resumo) if texto_resumo else "⚠️ Histórico indisponível"
    except Exception as e:
        print(f"❌ Erro resumo estatístico: {str(e)}")
        return "⚠️ Histórico indisponível"

def resumo_estendido(nome_time):
    try:
        team_id = buscar_team_id(nome_time)
        if not team_id:
            return f"⚠️ Time não encontrado: {nome_time}"

        url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            return f"⚠️ Erro ao buscar dados do time: Status {resp.status_code}"
            
        data = resp.json()
        if "response" not in data or not data["response"]:
            return f"⚠️ Sem jogos recentes para: {nome_time}"

        jogo = data["response"][0]
        if "league" not in jogo:
            return f"⚠️ Sem informação de liga para: {nome_time}"
            
        liga = jogo["league"]
        media = media_gols_liga(liga.get("id"), liga.get("season"))
        tendencia = "🔥 Liga com tendência OVER" if media >= 2.2 else "⚠️ Liga tende ao UNDER"

        return (
            f"🏆 {liga.get('name', 'Desconhecido')} ({liga.get('country', 'Desconhecido')}) – Temporada {liga.get('season', 'Desconhecido')}\n"
            f"📊 Média de gols: {media}\n"
            f"{tendencia}"
        )
    except Exception as e:
        return f"⚠️ Erro ao buscar info da liga de {nome_time}: {str(e)}"
