import os
import json
import asyncio
import logging
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict, Any
import aiohttp
from collections import Counter

try:
    import psycopg2
except ImportError:  # pragma: no cover - optional dependency
    psycopg2 = None

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
_metrics = Counter()


def metric(nome: str):
    """Incrementa contador de métrica e loga com prefixo metrics."""
    _metrics[nome] += 1
    logger.info(f"metrics.{nome}")


def metrics_snapshot(reset: bool = False) -> dict:
    """Retorna snapshot simples das métricas registradas."""
    snap = dict(_metrics)
    if reset:
        _metrics.clear()
    return snap

# Configurações da API
API_FOOTBALL_KEY = os.getenv("FOOTBALL_API_KEY")
if not API_FOOTBALL_KEY:
    raise ValueError("FOOTBALL_API_KEY não encontrada nas variáveis de ambiente")

HEADERS = {
    "x-apisports-key": API_FOOTBALL_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}
BASE_URL = "https://v3.football.api-sports.io"

# Timeout padrão para requisições
DEFAULT_TIMEOUT = 15
DB_PATH = Path(os.getenv("ESTATISTICAS_DB_PATH", "estatisticas.db"))
MAX_CACHE_DIAS = int(os.getenv("ESTATISTICAS_CACHE_DIAS", "7"))
ISO_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

PG_DSN = os.getenv("DATABASE_URL")
PG_HOST = os.getenv("PGHOST")
PG_PORT = os.getenv("PGPORT")
PG_USER = os.getenv("PGUSER")
PG_PASSWORD = os.getenv("PGPASSWORD")
PG_DATABASE = os.getenv("PGDATABASE")

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
    "FC Twente": "Twente",
    "NEC Nijmegen": "NEC Nijmegen",
}

def normalizar(texto: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas"""
    if not texto:
        return ""
    try:
        normalized = unicodedata.normalize("NFKD", str(texto))
        ascii_text = normalized.encode("ASCII", "ignore").decode("utf-8")
        return ascii_text.lower().strip()
    except Exception as e:
        logger.error(f"Erro ao normalizar texto '{texto}': {e}")
        return str(texto).lower().strip()

def similaridade(a: str, b: str) -> float:
    """Calcula similaridade entre duas strings"""
    if not a or not b:
        return 0.0
    try:
        norm_a = normalizar(a)
        norm_b = normalizar(b)
        return SequenceMatcher(None, norm_a, norm_b).ratio()
    except Exception as e:
        logger.error(f"Erro ao calcular similaridade entre '{a}' e '{b}': {e}")
        return 0.0


def usar_postgres() -> bool:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 não instalado; Postgres é obrigatório.")
    if not (PG_DSN or (PG_HOST and PG_USER and PG_PASSWORD and PG_DATABASE)):
        raise RuntimeError("Variáveis do Postgres ausentes: defina DATABASE_URL ou PGHOST/PGUSER/PGPASSWORD/PGDATABASE.")
    return True


def _get_pg_conn():
    if PG_DSN:
        return psycopg2.connect(PG_DSN)
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT or 5432,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
    )


def _get_conn():
    usar_postgres()
    conn = _get_pg_conn()
    conn.autocommit = True
    return conn


def _ordenar_dupla(time1: str, time2: str) -> Tuple[str, str, str, str]:
    """Normaliza e ordena os nomes dos times para manter chave determinística"""
    t1_norm = normalizar(time1)
    t2_norm = normalizar(time2)
    if t1_norm <= t2_norm:
        return time1, time2, t1_norm, t2_norm
    return time2, time1, t2_norm, t1_norm


def init_db():
    """Inicializa o banco SQLite para armazenar históricos"""
    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS historico_resumos (
                    id SERIAL PRIMARY KEY,
                    time1 TEXT NOT NULL,
                    time2 TEXT NOT NULL,
                    time1_norm TEXT NOT NULL,
                    time2_norm TEXT NOT NULL,
                    resumo TEXT NOT NULL,
                    gols_1t_time1 INTEGER,
                    gols_1t_time2 INTEGER,
                    confrontos_json TEXT,
                    tendencia TEXT,
                    odd_registrada TEXT DEFAULT '',
                    data_ref DATE DEFAULT CURRENT_DATE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fixtures_cache (
                    id SERIAL PRIMARY KEY,
                    fixture_id BIGINT UNIQUE,
                    time1 TEXT NOT NULL,
                    time2 TEXT NOT NULL,
                    time1_norm TEXT NOT NULL,
                    time2_norm TEXT NOT NULL,
                    odd_referencia TEXT,
                    status TEXT DEFAULT 'PENDENTE',
                    gols_ht INTEGER,
                    gols_ft INTEGER,
                    resultado TEXT,
                    data_jogo TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_hr_unique ON historico_resumos(time1_norm, time2_norm, data_ref, odd_registrada);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fx_times ON fixtures_cache(time1_norm, time2_norm, updated_at);")
    except Exception as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")


def salvar_resumo_db(
    time1: str,
    time2: str,
    resumo: str,
    gols_1t_time1: int,
    gols_1t_time2: int,
    confrontos: List[str],
    tendencia: str,
    odd_referencia: Optional[str] = None,
):
    """Persiste o resumo estatístico para uso futuro"""
    try:
        init_db()
        time1_ord, time2_ord, t1_norm, t2_norm = _ordenar_dupla(time1, time2)
        confrontos_json = json.dumps(confrontos or [])
        odd_valor = odd_referencia or ""

        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO historico_resumos
                (time1, time2, time1_norm, time2_norm, resumo, gols_1t_time1, gols_1t_time2, confrontos_json, tendencia, odd_registrada, data_ref, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, NOW(), NOW())
                ON CONFLICT (time1_norm, time2_norm, data_ref, odd_registrada)
                DO UPDATE SET resumo=EXCLUDED.resumo, gols_1t_time1=EXCLUDED.gols_1t_time1, gols_1t_time2=EXCLUDED.gols_1t_time2, confrontos_json=EXCLUDED.confrontos_json, tendencia=EXCLUDED.tendencia, updated_at=NOW();
                """,
                (
                    time1_ord,
                    time2_ord,
                    t1_norm,
                    t2_norm,
                    resumo,
                    gols_1t_time1,
                    gols_1t_time2,
                    confrontos_json,
                    tendencia,
                    odd_valor,
                ),
            )
    except Exception as e:
        logger.error(f"Erro ao salvar resumo no banco de dados: {e}")

def salvar_fixture_pendente(time1: str, time2: str, fixture_id: Optional[int], odd_referencia: Optional[str], data_jogo: Optional[str]):
    """Grava fixture pendente para atualização posterior"""
    try:
        init_db()
        time1_ord, time2_ord, t1_norm, t2_norm = _ordenar_dupla(time1, time2)
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO fixtures_cache (fixture_id, time1, time2, time1_norm, time2_norm, odd_referencia, status, data_jogo, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDENTE', %s, NOW(), NOW())
                ON CONFLICT (fixture_id) DO UPDATE SET odd_referencia = EXCLUDED.odd_referencia, data_jogo = COALESCE(EXCLUDED.data_jogo, fixtures_cache.data_jogo), updated_at = NOW(), status = 'PENDENTE';
                """,
                (fixture_id, time1_ord, time2_ord, t1_norm, t2_norm, odd_referencia, data_jogo),
            )
    except Exception as e:
        logger.error(f"Erro ao salvar fixture pendente: {e}")


def atualizar_fixture_resultado(fixture_id: Optional[int], gols_ht: Optional[int], gols_ft: Optional[int], resultado: Optional[str], data_jogo: Optional[str]):
    """Atualiza resultado de fixture pós-jogo"""
    if not fixture_id:
        return
    try:
        init_db()
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE fixtures_cache
                SET gols_ht = %s, gols_ft = %s, resultado = %s, status = 'FINALIZADO', data_jogo = COALESCE(%s, data_jogo), updated_at = NOW()
                WHERE fixture_id = %s;
                """,
                (gols_ht, gols_ft, resultado, data_jogo, fixture_id),
            )
            metric("result_updated")
    except Exception as e:
        logger.error(f"Erro ao atualizar fixture: {e}")


def obter_metricas_historicas(time1: str, time2: str, max_rows: int = 10) -> Tuple[float, Optional[str]]:
    """Retorna percentual de gols no 1T em fixtures próprios e último resultado"""
    try:
        init_db()
        _, _, t1_norm, t2_norm = _ordenar_dupla(time1, time2)
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT gols_ht, resultado
                FROM fixtures_cache
                WHERE time1_norm = %s AND time2_norm = %s AND status = 'FINALIZADO'
                ORDER BY updated_at DESC
                LIMIT %s;
                """,
                (t1_norm, t2_norm, max_rows),
            )
            rows = cur.fetchall()
        if not rows:
            metric("hist_empty")
            return 0.0, None
        com_gol = sum(1 for r in rows if r[0] and r[0] > 0)
        perc = com_gol / len(rows)
        last_result = rows[0][1]
        metric("hist_available")
        return perc, last_result
    except Exception as e:
        logger.error(f"Erro ao obter métricas históricas: {e}")
        return 0.0, None


def calcular_bonus_historico(
    perc_hist: float,
    ultimo_res: Optional[str],
    bonus_high: float,
    bonus_med: float,
    penalty_red: float,
) -> Tuple[float, List[str]]:
    """Calcula bônus/penalidade histórica de forma pura para testes."""
    bonus = 0.0
    criterios: List[str] = []

    if perc_hist >= bonus_high:
        bonus += 1
        criterios.append("Histórico próprio favorável")
    elif perc_hist >= bonus_med:
        bonus += 0.5
        criterios.append("Histórico próprio moderado")

    if ultimo_res and "RED" in ultimo_res:
        bonus -= penalty_red
        criterios.append("Alerta RED recente")

    return bonus, criterios

def carregar_resumo_recente(time1: str, time2: str) -> Optional[Dict[str, Any]]:
    """Recupera resumo recente salvo no banco para evitar chamadas repetidas à API"""
    _, _, t1_norm, t2_norm = _ordenar_dupla(time1, time2)
    # SQLite datetime('now','utc') usa o formato abaixo; mantemos a mesma assinatura para comparações
    limite = (datetime.now(timezone.utc) - timedelta(days=MAX_CACHE_DIAS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT resumo, confrontos_json, tendencia, odd_registrada, gols_1t_time1, gols_1t_time2, created_at
                FROM historico_resumos
                WHERE time1_norm = %s AND time2_norm = %s AND created_at >= %s::timestamptz
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (t1_norm, t2_norm, limite),
            )
            row = cur.fetchone()
            if row:
                keys = ["resumo", "confrontos_json", "tendencia", "odd_registrada", "gols_1t_time1", "gols_1t_time2", "criado_em"]
                metric("cache_hit")
                return dict(zip(keys, row))
            metric("cache_miss")
    except Exception as e:
        logger.error(f"Erro ao carregar resumo do banco: {e}")

    return None

async def fazer_requisicao_api(url: str, params: Dict[str, Any] = None, retries: int = 3) -> Optional[Dict[str, Any]]:
    """Função genérica para fazer requisições à API Football com retry"""
    if params is None:
        params = {}
    
    for tentativa in range(retries):
        try:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Construir URL com parâmetros
                if params:
                    query_string = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])
                    full_url = f"{url}?{query_string}" if query_string else url
                else:
                    full_url = url
                
                logger.info(f"Fazendo requisição para: {full_url}")
                
                async with session.get(full_url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Validar estrutura da resposta
                        if not isinstance(data, dict):
                            logger.error(f"Resposta não é um JSON válido: {type(data)}")
                            return None
                        
                        if "response" not in data:
                            logger.error(f"Resposta da API sem campo 'response': {data}")
                            return None
                        
                        logger.info(f"Requisição bem-sucedida. Dados recebidos: {len(data.get('response', []))} itens")
                        return data
                    
                    elif resp.status == 429:
                        logger.warning(f"Rate limit atingido. Tentativa {tentativa + 1}/{retries}")
                        if tentativa < retries - 1:
                            await asyncio.sleep(2 ** tentativa)  # Backoff exponencial
                            continue
                    
                    elif resp.status == 401:
                        logger.error("Erro de autenticação - verifique a API key")
                        return None
                    
                    else:
                        logger.error(f"Erro na API: Status {resp.status}")
                        error_text = await resp.text()
                        logger.error(f"Resposta de erro: {error_text}")
                        
                        if tentativa < retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return None
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout na requisição. Tentativa {tentativa + 1}/{retries}")
            if tentativa < retries - 1:
                await asyncio.sleep(1)
                continue
        except aiohttp.ClientError as e:
            logger.error(f"Erro de cliente HTTP: {e}. Tentativa {tentativa + 1}/{retries}")
            if tentativa < retries - 1:
                await asyncio.sleep(1)
                continue
        except Exception as e:
            logger.error(f"Erro inesperado na requisição: {e}. Tentativa {tentativa + 1}/{retries}")
            if tentativa < retries - 1:
                await asyncio.sleep(1)
                continue
    
    logger.error(f"Falha após {retries} tentativas para URL: {url}")
    return None

async def buscar_team_id(nome_time: str, pais: str = None) -> Optional[int]:
    """Busca o ID de um time na API Football"""
    if not nome_time or not nome_time.strip():
        logger.warning("Nome do time não fornecido")
        return None
    
    nome_time = nome_time.strip()
    nome_limpo = normalizar(nome_time)
    nome_oficial = NOMES_OFICIAIS.get(nome_time, nome_time)
    
    # Tentar busca com nome oficial primeiro
    for nome_busca in [nome_oficial, nome_time]:
        if not nome_busca:
            continue
        
        url = f"{BASE_URL}/teams"
        params = {"search": nome_busca}
        
        data = await fazer_requisicao_api(url, params)
        if not data:
            continue
        
        teams = data.get("response", [])
        logger.info(f"Encontrados {len(teams)} times para busca '{nome_busca}'")
        
        if teams:
            # Ordenar por similaridade
            teams_com_score = []
            for team_data in teams:
                if not isinstance(team_data, dict):
                    continue
                
                team_info = team_data.get("team", {})
                if not team_info:
                    continue
                
                team_name = team_info.get("name", "")
                if not team_name:
                    continue
                
                score = similaridade(nome_limpo, team_name)
                teams_com_score.append((score, team_info))
            
            if teams_com_score:
                # Ordenar por maior similaridade
                teams_com_score.sort(key=lambda x: x[0], reverse=True)
                melhor_score, melhor_team = teams_com_score[0]
                
                if melhor_score >= 0.4:
                    team_id = melhor_team.get("id")
                    team_name = melhor_team.get("name", "")
                    country = melhor_team.get("country", "")
                    
                    logger.info(f"✅ Time encontrado: {nome_time} ≈ {team_name} ({melhor_score:.2f}) - País: {country}")
                    return team_id
    
    logger.warning(f"Time não encontrado: {nome_time}")
    return None

async def gols_primeiro_tempo(team_id: int, num_jogos: int = 5) -> int:
    """Retorna quantos dos últimos N jogos do time tiveram gol no primeiro tempo"""
    if not team_id:
        logger.warning("ID do time não fornecido")
        return 0
    
    url = f"{BASE_URL}/fixtures"
    params = {
        "team": team_id,
        "last": num_jogos,
        "status": "FT"  # Apenas jogos finalizados
    }
    
    data = await fazer_requisicao_api(url, params)
    if not data:
        return 0
    
    jogos = data.get("response", [])
    logger.info(f"Analisando {len(jogos)} jogos para gols no 1º tempo")
    
    contador = 0
    jogos_analisados = 0
    
    for jogo in jogos:
        try:
            if not isinstance(jogo, dict):
                continue
            
            score = jogo.get("score", {})
            if not score:
                continue
            
            halftime = score.get("halftime", {})
            if not halftime:
                continue
            
            gols_casa = halftime.get("home")
            gols_fora = halftime.get("away")
            
            # Verificar se os dados estão disponíveis
            if gols_casa is None or gols_fora is None:
                continue
            
            jogos_analisados += 1
            
            if gols_casa > 0 or gols_fora > 0:
                contador += 1
                
                # Log detalhado
                teams = jogo.get("teams", {})
                home = teams.get("home", {}).get("name", "")
                away = teams.get("away", {}).get("name", "")
                logger.debug(f"Gol no 1T: {home} {gols_casa}-{gols_fora} {away}")
        
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Erro ao processar jogo para gols 1T: {e}")
            continue
    
    logger.info(f"Resultado: {contador}/{jogos_analisados} jogos com gol no 1º tempo")
    return contador

async def confrontos_diretos(team1_id: int, team2_id: int, num_jogos: int = 5) -> List[str]:
    """Retorna histórico de confrontos diretos entre dois times"""
    if not team1_id or not team2_id:
        logger.warning("IDs dos times não fornecidos")
        return []
    
    url = f"{BASE_URL}/fixtures/headtohead"
    params = {
        "h2h": f"{team1_id}-{team2_id}",
        "last": num_jogos
    }
    
    data = await fazer_requisicao_api(url, params)
    if not data:
        return []
    
    jogos = data.get("response", [])
    logger.info(f"Encontrados {len(jogos)} confrontos diretos")
    
    confrontos = []
    
    for jogo in jogos:
        try:
            if not isinstance(jogo, dict):
                continue
            
            teams = jogo.get("teams", {})
            score = jogo.get("score", {})
            
            if not teams or not score:
                continue
            
            # Dados dos times
            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            
            if not home_team or not away_team:
                continue
            
            casa = home_team.get("name", "")
            fora = away_team.get("name", "")
            
            if not casa or not fora:
                continue
            
            # Gols do primeiro tempo
            halftime = score.get("halftime", {})
            if halftime:
                gols_casa_ht = halftime.get("home")
                gols_fora_ht = halftime.get("away")
                
                if gols_casa_ht is not None and gols_fora_ht is not None:
                    confronto = f"{casa} {gols_casa_ht}x{gols_fora_ht} {fora} (1T)"
                    confrontos.append(confronto)
                    
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Erro ao processar confronto: {e}")
            continue
    
    return confrontos

async def resumo_estatistico(time1: str, time2: str, odd_referencia: Optional[str] = None) -> str:
    """Gera e persiste um resumo estatístico completo do confronto entre dois times"""
    try:
        logger.info(f"📊 Gerando resumo estatístico: {time1} vs {time2}")

        cache = carregar_resumo_recente(time1, time2)
        if cache:
            resumo_cache = cache.get("resumo", "")
            odd_salva = cache.get("odd_registrada")
            confrontos_cache = json.loads(cache.get("confrontos_json") or "[]")
            precisa_refrescar = False
            if odd_referencia and odd_referencia != odd_salva:
                precisa_refrescar = True

            criado_str = cache.get("criado_em")
            if criado_str:
                try:
                    criado_dt = datetime.fromisoformat(criado_str.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - criado_dt > timedelta(days=MAX_CACHE_DIAS / 2):
                        precisa_refrescar = True
                except ValueError:
                    precisa_refrescar = True
            else:
                precisa_refrescar = True

            if precisa_refrescar:
                salvar_resumo_db(
                    time1,
                    time2,
                    resumo_cache,
                    cache.get("gols_1t_time1") or 0,
                    cache.get("gols_1t_time2") or 0,
                    confrontos_cache,
                    cache.get("tendencia") or "",
                    odd_referencia or odd_salva,
                )
            return resumo_cache
        
        # Buscar IDs dos times
        team1_id = await buscar_team_id(time1)
        team2_id = await buscar_team_id(time2)
        
        if not team1_id:
            return f"⚠️ Time '{time1}' não encontrado na base de dados"
        
        if not team2_id:
            return f"⚠️ Time '{time2}' não encontrado na base de dados"
        
        # Obter estatísticas de cada time
        gols_1t_time1 = await gols_primeiro_tempo(team1_id, 5)
        gols_1t_time2 = await gols_primeiro_tempo(team2_id, 5)
        
        # Obter confrontos diretos
        confrontos = await confrontos_diretos(team1_id, team2_id, 3)
        
        # Montar resumo
        resumo = f"""📊 ESTATÍSTICAS DO CONFRONTO
        
🏠 {time1}: {gols_1t_time1}/5 jogos com gol no 1ºT
🏃 {time2}: {gols_1t_time2}/5 jogos com gol no 1ºT

📈 TENDÊNCIA: {gols_1t_time1 + gols_1t_time2}/10 jogos recentes com gol 1ºT"""
        
        # Adicionar confrontos diretos se existirem
        if confrontos:
            resumo += f"\n\n🤝 ÚLTIMOS CONFRONTOS (1ºT):"
            for confronto in confrontos[:3]:  # Máximo 3 confrontos
                resumo += f"\n• {confronto}"
        else:
            resumo += "\n\n🤝 Sem confrontos diretos recentes"
        
        # Adicionar análise de tendência
        total_gols_1t = gols_1t_time1 + gols_1t_time2
        if total_gols_1t >= 7:
            tendencia = "🟢 ALTA probabilidade de gol no 1ºT"
        elif total_gols_1t >= 4:
            tendencia = "🟡 MÉDIA probabilidade de gol no 1ºT"
        else:
            tendencia = "🔴 BAIXA probabilidade de gol no 1ºT"
        
        resumo += f"\n\n🎯 ANÁLISE: {tendencia}"
        salvar_resumo_db(
            time1,
            time2,
            resumo,
            gols_1t_time1,
            gols_1t_time2,
            confrontos,
            tendencia,
            odd_referencia,
        )
        
        logger.info(f"✅ Resumo estatístico gerado com sucesso")
        return resumo
        
    except Exception as e:
        logger.error(f"Erro ao gerar resumo estatístico: {e}")
        return f"⚠️ Erro ao obter estatísticas do confronto: {str(e)}"
