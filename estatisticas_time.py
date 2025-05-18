import requests
import os

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
BASE_URL = "https://v3.football.api-sports.io"

def buscar_team_id(nome_time):
    url = f"{BASE_URL}/teams?search={nome_time}"
    try:
        response = requests.get(url, headers=HEADERS)
        dados = response.json()['response']
        if dados:
            return dados[0]['team']['id']
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
            placar = jogo['score']['fulltime']
            resultados.append(f"{casa} {placar['home']}x{placar['away']} {fora}")
        return resultados
    except Exception as e:
        print(f"❌ Erro confrontos diretos: {e}")
        return []
