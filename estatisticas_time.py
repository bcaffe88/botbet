import requests
import os
import unicodedata
from difflib import SequenceMatcher

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
BASE_URL = "https://v3.football.api-sports.io"

def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def buscar_team_id(nome_time):
    nome_limpo = normalizar(nome_time.strip())
    termo_busca = normalizar(nome_time.strip().split()[0])  # Usa apenas a primeira palavra

    url = f"{BASE_URL}/teams?search={termo_busca}"
    try:
        response = requests.get(url, headers=HEADERS)
        dados = response.json().get('response', [])

        if not dados:
            print(f"⚠️ Nenhum resultado encontrado na API para: {nome_time}")
            return None

        melhor_match = max(
            dados,
            key=lambda x: similaridade(nome_limpo, normalizar(x['team']['name']))
        )
        score = similaridade(nome_limpo, normalizar(melhor_match['team']['name']))

        if score >= 0.7:
            print(f"✅ Match: {nome_time} ≈ {melhor_match['team']['name']} ({score:.2f})")
            return melhor_match['team']['id']
        else:
            print(f"⚠️ Similaridade baixa: {nome_time} ≠ {melhor_match['team']['name']} ({score:.2f})")
            return None

    except Exception as e:
        print(f"❌ Erro ao buscar team_id de {nome_time}: {e}")
    return None

def gols_primeiro_tempo(team_id):
    url = f"{BASE_URL}/fixtures?team={team_id}&last=5"
    try:
        response = requests.get(url, headers=HEADERS)
        jogos = response.json()['response']
        gols_1t = 0
        for jogo in jogos:
            placar_1t = jogo['score']['halftime']
            if placar_1t['home'] > 0 or placar_1t['away'] > 0:
                gols_1t += 1
        return gols_1t
    except Exception as e:
        print(f"❌ Erro buscando gols 1T: {e}")
        return 0

def media_gols_liga(league_id, season):
    url = f"{BASE_URL}/fixtures?league={league_id}&season={season}&last=10"
    try:
        response = requests.get(url, headers=HEADERS)
        jogos = response.json()['response']
        if not jogos:
            print(f"⚠️ Nenhum jogo encontrado para liga {league_id} - temporada {season}")
            return 0
        total = sum(j['goals']['home'] + j['goals']['away'] for j in jogos)
        return round(total / len(jogos), 2)
    except Exception as e:
        print(f"❌ Erro na média da liga: {e}")
        return 0

def confrontos_diretos(team1_id, team2_id):
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}&last=5"
    try:
        response = requests.get(url, headers=HEADERS)
        jogos = response.json()['response']
        resultados = []
        for jogo in jogos:
            casa = jogo['teams']['home']['name']
            fora = jogo['teams']['away']['name']
            placar = jogo['score']['halftime']
            resultados.append(f"{casa} {placar['home']}x{placar['away']} {fora}")
        return resultados
    except Exception as e:
        print(f"❌ Erro confrontos diretos: {e}")
        return []

def buscar_liga_time(team_id):
    url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
    try:
        response = requests.get(url, headers=HEADERS)
        jogos = response.json()['response']
        if jogos:
            liga_id = jogos[0]['league']['id']
            temporada = jogos[0]['league']['season']
            return liga_id, temporada
    except Exception as e:
        print(f"❌ Erro ao buscar liga do time {team_id}: {e}")
    return None, None

def resumo_estatistico(nome_mandante, nome_visitante):
    try:
        team1_id = buscar_team_id(nome_mandante)
        team2_id = buscar_team_id(nome_visitante)

        texto_resumo = []

        if team1_id:
            gols_mandante = gols_primeiro_tempo(team1_id)
            texto_resumo.append(f"🏠 {nome_mandante}: {gols_mandante}/5 jogos com gol no 1T")

        if team2_id:
            gols_visitante = gols_primeiro_tempo(team2_id)
            texto_resumo.append(f"🚶 {nome_visitante}: {gols_visitante}/5 jogos com gol no 1T")

        if team1_id and team2_id:
            confrontos = confrontos_diretos(team1_id, team2_id)
            gols_confronto_1t = sum(
                1 for c in confrontos if "x" in c and int(c.split("x")[0].split()[-1]) + int(c.split("x")[1].split()[0]) > 0
            )
            texto_resumo.append(f"⚔️ Confrontos diretos: {gols_confronto_1t}/5 com gol no 1T")

        liga_id, temporada = buscar_liga_time(team1_id)
        if liga_id and temporada:
            media = media_gols_liga(liga_id, temporada)
            texto_resumo.append(f"📊 Média de gols da liga: {media}")
        else:
            texto_resumo.append("📊 Média de gols da liga: indisponível")

        return "\n".join(texto_resumo)

    except Exception as e:
        print(f"❌ Erro ao gerar resumo estatístico: {e}")
        return "⚠️ Histórico indisponível"

def resumo_estendido(nome_time):
    try:
        team_id = buscar_team_id(nome_time)
        if not team_id:
            return f"⚠️ Time não encontrado: {nome_time}"

        url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
        response = requests.get(url, headers=HEADERS)
        data = response.json()['response']
        if not data:
            return f"⚠️ Sem jogos recentes para: {nome_time}"

        jogo = data[0]
        liga = jogo['league']
        league_id = liga['id']
        nome_liga = liga['name']
        pais = liga['country']
        temporada = liga['season']

        media = media_gols_liga(league_id, temporada)
        interpretacao = "🔥 Liga com tendência OVER" if media >= 2.2 else "⚠️ Liga tende ao UNDER"

        return (
            f"🏆 {nome_liga} ({pais}) – Temporada {temporada}\n"
            f"📊 Média de gols: {media}\n"
            f"{interpretacao}"
        )

    except Exception as e:
        print(f"❌ Erro no resumo estendido: {e}")
        return f"⚠️ Erro ao buscar info da liga de {nome_time}"
