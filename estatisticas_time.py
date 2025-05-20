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

def resumo_estatistico(nome_mandante, nome_visitante, league_id=71, season=2024):
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

        media = media_gols_liga(league_id, season)
        texto_resumo.append(f"📊 Média de gols da liga: {media}")

        return "\n".join(texto_resumo)

    except Exception as e:
        print(f"❌ Erro ao gerar resumo estatístico: {e}")
        return "⚠️ Histórico indisponível"
