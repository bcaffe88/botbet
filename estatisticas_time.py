import os
import asyncio
import logging
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from typing import Optional, List, Tuple
import aiohttp

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações da API
API_FOOTBALL_KEY = os.getenv("FOOTBALL_API_KEY")
if not API_FOOTBALL_KEY:
    raise ValueError("FOOTBALL_API_KEY não encontrada nas variáveis de ambiente")

HEADERS = {
    "x-apisports-key": API_FOOTBALL_KEY,
    "Accept": "application/json"
}
BASE_URL = "https://v3.football.api-sports.io"

# Mapeamento manual de nomes comuns para nomes oficiais na API
NOMES_OFICIAIS = {
    "Alajuelense": "Liga Deportiva Alajuelense",
    "Saprissa": "Deportivo Saprissa",
    "Deportivo Saprissa": "Deportivo Saprissa",
    "Real Madrid": "Real Madrid CF",
    "Barcelona": "FC Barcelona",
    "Atletico Madrid": "Atletico de Madrid",
    "PSG": "Paris Saint Germain",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Liverpool": "Liverpool FC",
    "Chelsea": "Chelsea FC",
    "Arsenal": "Arsenal FC",
}

def normalizar(texto: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas"""
    if not texto:
        return ""
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8").lower()

def similaridade(a: str, b: str) -> float:
    """Calcula similaridade entre duas strings"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

async def verificar_gol_ht(nome_jogo: str) -> str:
    """Verifica se houve gol no primeiro tempo do jogo especificado"""
    if not nome_jogo:
        logger.warning("Nome do jogo não fornecido")
        return "⏳ NÃO LOCALIZADO"
        
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/fixtures?date={data_hoje}"
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return "⏳ ERRO NA API"
                
                data = await resp.json()
                if "response" not in data:
                    logger.error("Resposta da API sem campo 'response'")
                    return "⏳ ERRO NA API"
                
                logger.info(f"📅 {len(data['response'])} jogos encontrados em {data_hoje}")
                
                for item in data["response"]:
                    try:
                        if not all(key in item for key in ["teams", "score"]):
                            continue
                            
                        teams = item["teams"]
                        score = item["score"]
                        halftime = score.get("halftime")
                        
                        if not teams or not halftime:
                            continue
                            
                        casa = teams.get("home", {}).get("name", "")
                        fora = teams.get("away", {}).get("name", "")
                        
                        if not casa or not fora:
                            continue
                            
                        nome_match = f"{casa} x {fora}"
                        
                        if similaridade(nome_jogo, nome_match) > 0.75:
                            gols_casa_ht = halftime.get("home") or 0
                            gols_fora_ht = halftime.get("away") or 0
                            gols_ht = gols_casa_ht + gols_fora_ht
                            
                            logger.info(f"🔍 Match encontrado: {nome_jogo} ≈ {nome_match} | Gols HT: {gols_ht}")
                            return "✅ BATEU" if gols_ht >= 1 else "❌ NÃO BATEU"
                            
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Erro ao processar jogo: {e}")
                        continue
                        
    except asyncio.TimeoutError:
        logger.error("Timeout ao consultar API")
        return "⏳ TIMEOUT"
    except Exception as e:
        logger.error(f"Erro ao consultar API-Football: {e}")
        return "⏳ ERRO"
    
    logger.info(f"Jogo não encontrado: {nome_jogo}")
    return "⏳ NÃO LOCALIZADO"

async def buscar_team_id(nome_time: str, pais: str = "Costa Rica") -> Optional[int]:
    """Busca o ID de um time na API Football"""
    if not nome_time:
        return None
        
    nome_limpo = normalizar(nome_time)
    nome_oficial = NOMES_OFICIAIS.get(nome_time.strip(), nome_time.strip())

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{BASE_URL}/teams?search={nome_oficial}"
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return None
                    
                data = await resp.json()
                dados = data.get("response", [])
                
                if dados:
                    melhores = sorted(
                        dados, 
                        key=lambda x: similaridade(nome_limpo, x.get("team", {}).get("name", "")), 
                        reverse=True
                    )
                    
                    if melhores:
                        melhor_match = melhores[0]
                        team_info = melhor_match.get("team", {})
                        score = similaridade(nome_limpo, team_info.get("name", ""))
                        
                        if score >= 0.4:
                            logger.info(f"✅ Time encontrado: {nome_time} ≈ {team_info.get('name')} ({score:.2f})")
                            return team_info.get("id")
                            
    except Exception as e:
        logger.error(f"Erro na busca por {nome_time}: {e}")
        return None

    logger.warning(f"Time não encontrado: {nome_time}")
    return None

async def gols_primeiro_tempo(team_id: int) -> int:
    """Retorna quantos dos últimos 5 jogos do time tiveram gol no primeiro tempo"""
    if not team_id:
        return 0
        
    url = f"{BASE_URL}/fixtures?team={team_id}&last=5"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return 0
                    
                data = await resp.json()
                if "response" not in data:
                    logger.error("Resposta da API sem campo 'response'")
                    return 0
                    
                jogos = data["response"]
                contador = 0
                
                for jogo in jogos:
                    try:
                        halftime = jogo.get("score", {}).get("halftime", {})
                        if halftime:
                            gols_casa = halftime.get("home", 0) or 0
                            gols_fora = halftime.get("away", 0) or 0
                            if gols_casa > 0 or gols_fora > 0:
                                contador += 1
                    except (KeyError, TypeError):
                        continue
                        
                return contador
                
    except Exception as e:
        logger.error(f"Erro ao buscar gols 1T: {e}")
        return 0

async def media_gols_liga(league_id: int, season: int) -> float:
    """Calcula a média de gols dos últimos 10 jogos da liga"""
    if not league_id or not season:
        return 0.0
        
    url = f"{BASE_URL}/fixtures?league={league_id}&season={season}&last=10"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return 0.0
                    
                data = await resp.json()
                if "response" not in data:
                    logger.error("Resposta da API sem campo 'response'")
                    return 0.0
                    
                jogos = data["response"]
                if not jogos:
                    return 0.0
                    
                total_gols = 0
                jogos_validos = 0
                
                for jogo in jogos:
                    try:
                        goals = jogo.get("goals", {})
                        gols_casa = goals.get("home", 0) or 0
                        gols_fora = goals.get("away", 0) or 0
                        total_gols += gols_casa + gols_fora
                        jogos_validos += 1
                    except (KeyError, TypeError):
                        continue
                        
                return round(total_gols / jogos_validos, 2) if jogos_validos > 0 else 0.0
                
    except Exception as e:
        logger.error(f"Erro média da liga: {e}")
        return 0.0

async def confrontos_diretos(team1_id: int, team2_id: int) -> List[str]:
    """Retorna histórico de confrontos diretos entre dois times"""
    if not team1_id or not team2_id:
        return []
        
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}&last=5"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return []
                    
                data = await resp.json()
                if "response" not in data:
                    logger.error("Resposta da API sem campo 'response'")
                    return []
                    
                jogos = data["response"]
                confrontos = []
                
                for jogo in jogos:
                    try:
                        teams = jogo.get("teams", {})
                        halftime = jogo.get("score", {}).get("halftime", {})
                        
                        if not teams or not halftime:
                            continue
                            
                        casa = teams.get("home", {}).get("name", "")
                        fora = teams.get("away", {}).get("name", "")
                        gols_casa = halftime.get("home", 0) or 0
                        gols_fora = halftime.get("away", 0) or 0
                        
                        if casa and fora:
                            confrontos.append(f"{casa} {gols_casa}x{gols_fora} {fora}")
                            
                    except (KeyError, TypeError):
                        continue
                        
                return confrontos
                
    except Exception as e:
        logger.error(f"Erro confrontos diretos: {e}")
        return []

async def buscar_liga_time(team_id: int) -> Tuple[Optional[int], Optional[int]]:
    """Busca informações da liga do time"""
    if not team_id:
        return None, None
        
    url = f"{BASE_URL}/fixtures?team={team_id}&last=1"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.error(f"Erro na API: Status {resp.status}")
                    return None, None
                    
                data = await resp.json()
                if "response" not in data or not data["response"]:
                    logger.error("Resposta da API sem dados")
                    return None, None
                    
                jogo = data["response"][0]
                liga = jogo.get("league", {})
                
                if not liga:
                    logger.error("Jogo sem informação de liga")
                    return None, None
                    
                return liga.get("id"), liga.get("season")
                
    except Exception as e:
        logger.error(f"Erro buscar liga time: {e}")
        return None, None

async def resumo_estatistico(nome_mandante: str, nome_visitante: str) -> str:
    """Gera resumo estatístico dos times"""
    try:
        logger.info(f"Gerando resumo para: {nome_mandante} x {nome_visitante}")
        
        # Buscar IDs dos times
        team1_id = await buscar_team_id(nome_mandante)
        team2_id = await buscar_team_id(nome_visitante)
        
        texto_resumo = []

        # Estatísticas do mandante
        if team1_id:
            gols_ht = await gols_primeiro_tempo(team1_id)
            texto_resumo.append(f"🏠 {nome_mandante}: {gols_ht}/5 jogos com gol no 1T")
        else:
            texto_resumo.append(f"🏠 {nome_mandante}: dados não disponíveis")
            
        # Estatísticas do visitante
        if team2_id:
            gols_ht = await gols_primeiro_tempo(team2_id)
            texto_resumo.append(f"🚶 {nome_visitante}: {gols_ht}/5 jogos com gol no 1T")
        else:
            texto_resumo.append(f"🚶 {nome_visitante}: dados não disponíveis")

        # Confrontos diretos
        if team1_id and team2_id:
            confrontos = await confrontos_diretos(team1_id, team2_id)
            gols_confronto = 0
            
            for confronto in confrontos:
                try:
                    if "x" in confronto:
                        partes = confronto.split("x")
                        gols_casa = int(partes[0].split()[-1])
                        gols_fora = int(partes[1].split()[0])
                        if gols_casa + gols_fora > 0:
                            gols_confronto += 1
                except (ValueError, IndexError):
                    continue
                    
            texto_resumo.append(f"⚔️ Confrontos diretos: {gols_confronto}/{len(confrontos)} com gol no 1T")

        # Média da liga
        liga_id, temporada = await buscar_liga_time(team1_id or team2_id)
        if liga_id and temporada:
            media = await media_gols_liga(liga_id, temporada)
            texto_resumo.append(f"📊 Média de gols da liga: {media}")
        else:
            texto_resumo.append("📊 Média de gols da liga: indisponível")

        return "\n".join(texto_resumo) if texto_resumo else "⚠️ Histórico indisponível"
        
    except Exception as e:
        logger.error(f"Erro resumo estatístico: {e}")
        return "⚠️ Erro ao gerar histórico"

async def resumo_estendido(nome_time: str) -> str:
    """Gera resumo estendido com informações da liga"""
    try:
        team_id = await buscar_team_id(nome_time)
        if not team_id:
            return f"⚠️ Time não encontrado: {nome_time}"

        liga_id, temporada = await buscar_liga_time(team_id)
        if not liga_id or not temporada:
            return f"⚠️ Informações da liga não disponíveis para: {nome_time}"

        # Buscar informações detalhadas da liga
        url = f"{BASE_URL}/leagues?id={liga_id}&season={temporada}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    return f"⚠️ Erro ao buscar dados da liga: Status {resp.status}"
                    
                data = await resp.json()
                if "response" not in data or not data["response"]:
                    return f"⚠️ Dados da liga não encontrados"

                liga_info = data["response"][0].get("league", {})
                country_info = data["response"][0].get("country", {})
                
                media = await media_gols_liga(liga_id, temporada)
                tendencia = "🔥 Liga com tendência OVER" if media >= 2.2 else "⚠️ Liga tende ao UNDER"

                return (
                    f"🏆 {liga_info.get('name', 'Desconhecido')} ({country_info.get('name', 'Desconhecido')}) – Temporada {temporada}\n"
                    f"📊 Média de gols: {media}\n"
                    f"{tendencia}"
                )
                
    except Exception as e:
        logger.error(f"Erro resumo estendido: {e}")
        return f"⚠️ Erro ao buscar informações da liga de {nome_time}"

# Função para testar o módulo
async def teste_modulo():
    """Função de teste para verificar funcionamento do módulo"""
    logger.info("🧪 Testando módulo Football API")
    
    # Teste de verificação de gol no HT
    resultado = await verificar_gol_ht("Real Madrid x Barcelona")
    logger.info(f"Teste verificar_gol_ht: {resultado}")
    
    # Teste de busca de time
    team_id = await buscar_team_id("Real Madrid")
    logger.info(f"Teste buscar_team_id: {team_id}")
    
    if team_id:
        # Teste de gols no primeiro tempo
        gols_ht = await gols_primeiro_tempo(team_id)
        logger.info(f"Teste gols_primeiro_tempo: {gols_ht}")
        
        # Teste de resumo estendido
        resumo = await resumo_estendido("Real Madrid")
        logger.info(f"Teste resumo_estendido: {resumo}")

if __name__ == "__main__":
    asyncio.run(teste_modulo())
