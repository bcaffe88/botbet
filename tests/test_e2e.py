"""
Comprehensive End-to-End tests for botbet application.
Tests utility functions, climate analysis, signal analysis, and API integrations.
"""
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
from zoneinfo import ZoneInfo

# Set required environment variables before importing main module
os.environ.setdefault("BOT_TOKEN", "test-bot-token-123")
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test-api-hash")
os.environ.setdefault("CHAT_ID_SINAL", "-100123456789")
os.environ.setdefault("CHAT_ID_DESTINO", "-100987654321")
os.environ.setdefault("FOOTBALL_API_KEY", "test-football-api-key")
os.environ.setdefault("DATABASE_URL", "postgres://user:pass@localhost/db")

# Import main module after setting environment variables
import main  # noqa: E402


class MockResponse:
    """Helper class to mock aiohttp response."""
    def __init__(self, status, json_data):
        self.status = status
        self._json_data = json_data
    
    async def json(self):
        return self._json_data
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockClientSession:
    """Helper class to mock aiohttp ClientSession."""
    def __init__(self, responses):
        self.responses = responses if isinstance(responses, list) else [responses]
        self.call_count = 0
    
    def get(self, *args, **kwargs):
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return response
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        pass


class TestUtilityFunctions:
    """Test suite for utility functions."""

    def test_normalizar_basic_text(self):
        """Test text normalization with basic ASCII text."""
        result = main.normalizar("Hello World")
        assert result == "hello world"

    def test_normalizar_accents(self):
        """Test text normalization removes accents."""
        result = main.normalizar("São Paulo")
        assert result == "sao paulo"

    def test_normalizar_special_chars(self):
        """Test text normalization with special characters."""
        result = main.normalizar("Atlético-MG")
        assert result == "atletico-mg"

    def test_normalizar_empty_string(self):
        """Test text normalization with empty string."""
        result = main.normalizar("")
        assert result == ""

    def test_normalizar_none(self):
        """Test text normalization with None."""
        result = main.normalizar(None)
        assert result == ""

    def test_similaridade_identical_strings(self):
        """Test similarity calculation with identical strings."""
        result = main.similaridade("Flamengo", "Flamengo")
        assert result == 1.0

    def test_similaridade_different_strings(self):
        """Test similarity calculation with different strings."""
        result = main.similaridade("Flamengo", "Palmeiras")
        assert result < 0.5

    def test_similaridade_similar_strings(self):
        """Test similarity calculation with similar strings."""
        result = main.similaridade("Corinthians", "Corinthias")
        assert result > 0.8

    def test_similaridade_empty_strings(self):
        """Test similarity calculation with empty strings."""
        result = main.similaridade("", "")
        assert result == 0.0

    def test_similaridade_none_values(self):
        """Test similarity calculation with None values."""
        result = main.similaridade(None, "Test")
        assert result == 0.0

    def test_extrair_times_with_x_separator(self):
        """Test team name extraction with 'x' separator."""
        result = main.extrair_times("Flamengo x Palmeiras")
        assert result == ["Flamengo", "Palmeiras"]

    def test_extrair_times_with_vs_separator(self):
        """Test team name extraction with 'vs' separator."""
        result = main.extrair_times("Real Madrid vs Barcelona")
        assert result == ["Real Madrid", "Barcelona"]

    def test_extrair_times_with_dash_separator(self):
        """Test team name extraction with '-' separator."""
        result = main.extrair_times("Bayern - Dortmund")
        assert result == ["Bayern", "Dortmund"]

    def test_extrair_times_with_extra_spaces(self):
        """Test team name extraction handles extra spaces."""
        result = main.extrair_times("  Team A   x   Team B  ")
        assert result == ["Team A", "Team B"]

    def test_extrair_times_invalid_format(self):
        """Test team name extraction with invalid format."""
        result = main.extrair_times("Single Team Name")
        assert result == []

    def test_extrair_times_empty_string(self):
        """Test team name extraction with empty string."""
        result = main.extrair_times("")
        assert result == []

    def test_extrair_liga_with_match(self):
        """Test league extraction with valid liga text."""
        result = main.extrair_liga("Liga: Brasileirão Série A")
        assert result == "Brasileirão Série A"

    def test_extrair_liga_with_colon(self):
        """Test league extraction with colon separator."""
        result = main.extrair_liga("Liga: Premier League")
        assert result == "Premier League"

    def test_extrair_liga_with_dash(self):
        """Test league extraction with dash separator."""
        result = main.extrair_liga("Liga- La Liga")
        assert result == "La Liga"

    def test_extrair_liga_case_insensitive(self):
        """Test league extraction is case insensitive."""
        result = main.extrair_liga("LIGA: Champions League")
        assert result == "Champions League"

    def test_extrair_liga_no_match(self):
        """Test league extraction with no match."""
        result = main.extrair_liga("No league information here")
        assert result is None

    def test_extrair_pais_with_match(self):
        """Test country extraction with valid país text."""
        result = main.extrair_pais("País: Brasil")
        assert result == "Brasil"

    def test_extrair_pais_with_accent(self):
        """Test country extraction with accented país."""
        result = main.extrair_pais("país: Inglaterra")
        assert result == "Inglaterra"

    def test_extrair_pais_with_dash(self):
        """Test country extraction with dash separator."""
        result = main.extrair_pais("País- Espanha")
        assert result == "Espanha"

    def test_extrair_pais_case_insensitive(self):
        """Test country extraction is case insensitive."""
        result = main.extrair_pais("PAÍS: França")
        assert result == "França"

    def test_extrair_pais_no_match(self):
        """Test country extraction with no match."""
        result = main.extrair_pais("No country information")
        assert result is None

    def test_eh_mercado_primeiro_tempo_over_valid(self):
        """Test first half over market detection with valid market name."""
        result = main.eh_mercado_primeiro_tempo_over("1st Half - Over/Under")
        assert result is True

    def test_eh_mercado_primeiro_tempo_over_with_first(self):
        """Test first half market detection with 'first' keyword."""
        result = main.eh_mercado_primeiro_tempo_over("First Half Total Over")
        assert result is True

    def test_eh_mercado_primeiro_tempo_over_with_half(self):
        """Test first half market detection with 'half' keyword."""
        result = main.eh_mercado_primeiro_tempo_over("Over Half Time Goals")
        assert result is True

    def test_eh_mercado_primeiro_tempo_over_with_tempo(self):
        """Test first half market detection with 'tempo' keyword."""
        result = main.eh_mercado_primeiro_tempo_over("Over - Primeiro Tempo")
        assert result is True

    def test_eh_mercado_primeiro_tempo_over_invalid(self):
        """Test first half market detection with invalid market name."""
        result = main.eh_mercado_primeiro_tempo_over("Full Time Result")
        assert result is False

    def test_eh_mercado_primeiro_tempo_over_empty(self):
        """Test first half market detection with empty string."""
        result = main.eh_mercado_primeiro_tempo_over("")
        assert result is False

    def test_eh_mercado_primeiro_tempo_over_none(self):
        """Test first half market detection with None."""
        result = main.eh_mercado_primeiro_tempo_over(None)
        assert result is False

    def test_dentro_janela_operacao_morning(self):
        """Test operating window validation for morning hours."""
        result = main.dentro_janela_operacao(10)
        assert result is True

    def test_dentro_janela_operacao_afternoon(self):
        """Test operating window validation for afternoon hours."""
        result = main.dentro_janela_operacao(15)
        assert result is True

    def test_dentro_janela_operacao_evening(self):
        """Test operating window validation for evening hours."""
        result = main.dentro_janela_operacao(23)
        assert result is True

    def test_dentro_janela_operacao_early_morning(self):
        """Test operating window validation for hours before start."""
        result = main.dentro_janela_operacao(3)
        assert result is False

    def test_dentro_janela_operacao_start_boundary(self):
        """Test operating window validation at start boundary."""
        result = main.dentro_janela_operacao(8)
        assert result is True

    def test_dentro_janela_operacao_end_boundary(self):
        """Test operating window validation at end boundary."""
        result = main.dentro_janela_operacao(0)
        assert result is False


class TestClimateAnalysis:
    """Test suite for climate analysis function."""

    def test_analisar_clima_ideal_conditions(self):
        """Test climate analysis with ideal conditions."""
        texto = "🌡️ 22°C ☁️ 40% 💧 60% 💨 5 m/s"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 4
        assert "Temperatura ideal" in criterios
        assert "Nebulosidade ideal (sem sol forte)" in criterios
        assert "Umidade ideal" in criterios
        assert "Vento ótimo" in criterios
        assert status == "🟢 FAVORÁVEL"

    def test_analisar_clima_favorable(self):
        """Test climate analysis with favorable conditions."""
        texto = "🌡️ 25°C ☁️ 30% 💧 65%"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 3
        assert status == "🟡 NEUTRO"

    def test_analisar_clima_neutral(self):
        """Test climate analysis with neutral conditions."""
        texto = "🌡️ 20°C ☁️ 25%"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 2
        assert status == "🟡 NEUTRO"

    def test_analisar_clima_unfavorable(self):
        """Test climate analysis with unfavorable conditions."""
        texto = "🌡️ 35°C ☁️ 5%"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos < 2
        assert status == "🔴 DESFAVORÁVEL"

    def test_analisar_clima_moderate_wind(self):
        """Test climate analysis with moderate wind."""
        texto = "🌡️ 22°C ☁️ 40% 💧 60% 💨 8 m/s"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 3.5
        assert "Vento moderado" in criterios
        assert status == "🟢 FAVORÁVEL"

    def test_analisar_clima_high_wind(self):
        """Test climate analysis with high wind (no points)."""
        texto = "🌡️ 22°C ☁️ 40% 💧 60% 💨 15 m/s"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 3
        assert "Vento" not in " ".join(criterios)

    def test_analisar_clima_no_data(self):
        """Test climate analysis with no climate data."""
        texto = "Some text without climate information"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 0
        assert len(criterios) == 0
        assert status == "🔴 DESFAVORÁVEL"

    def test_analisar_clima_partial_data(self):
        """Test climate analysis with partial data."""
        texto = "🌡️ 23°C"
        pontos, criterios, status = main.analisar_clima(texto)
        assert pontos == 1
        assert "Temperatura ideal" in criterios


class TestOddResultadoNamedTuple:
    """Test suite for OddResultado NamedTuple."""

    def test_oddresultado_creation(self):
        """Test OddResultado creation."""
        odd = main.OddResultado(valor="2.05", origem="live")
        assert odd.valor == "2.05"
        assert odd.origem == "live"

    def test_oddresultado_field_access(self):
        """Test OddResultado field access."""
        odd = main.OddResultado("1.90", "pre-live")
        assert odd.valor == "1.90"
        assert odd.origem == "pre-live"

    def test_oddresultado_immutability(self):
        """Test OddResultado is immutable."""
        odd = main.OddResultado("3.00", "unavailable")
        with pytest.raises(AttributeError):
            odd.valor = "4.00"


class TestSignalAnalysis:
    """Test suite for signal analysis function (analisar)."""

    @pytest.mark.asyncio
    async def test_analisar_u20_game_ignored(self):
        """Test that U20 games are ignored."""
        texto = "⚽️ Flamengo U20 x Palmeiras U20\n⏰ 20"
        
        with patch.object(main, 'bot') as mock_bot, \
             patch('main.datetime') as mock_datetime:
            # Mock the datetime to return an hour within operating window
            mock_dt = MagicMock()
            mock_dt.hour = 10
            mock_datetime.now.return_value = mock_dt
            
            result = await main.analisar(texto)
            
            assert result is None
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_analisar_u19_game_ignored(self):
        """Test that U19 games are ignored."""
        texto = "⚽️ Corinthians U19 x Santos U19\n⏰ 20"
        
        with patch.object(main, 'bot') as mock_bot, \
             patch('main.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.hour = 10
            mock_datetime.now.return_value = mock_dt
            
            result = await main.analisar(texto)
            
            assert result is None
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_analisar_outside_operating_window(self):
        """Test that signals outside operating window are ignored."""
        texto = "⚽️ Flamengo x Palmeiras\n⏰ 20"
        
        with patch.object(main, 'bot') as mock_bot, \
             patch('main.datetime') as mock_datetime:
            # Mock the datetime to return an hour outside operating window
            mock_dt = MagicMock()
            mock_dt.hour = 3  # Outside window
            mock_datetime.now.return_value = mock_dt
            
            result = await main.analisar(texto)
            
            assert result is None
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_analisar_high_confidence_calculation(self):
        """Test signal analysis calculates high confidence correctly."""
        texto = """⚽️ Flamengo x Palmeiras
⏰ 18
OVER 0.5 HT: 75%
Ataques Perigosos: 10/8
Posse de Bola: 65%/35%
Escanteios: 3/1
No Gol: 2/1
Fora do Gol: 2/1
🌡️ 22°C
☁️ 40%
💧 60%
💨 5 m/s"""
        
        with patch.object(main, 'bot') as mock_bot, \
             patch.object(main, 'buscar_fixture_id', new_callable=AsyncMock) as mock_fixture, \
             patch.object(main, 'buscar_odd_pre_live', new_callable=AsyncMock) as mock_odd, \
             patch.object(main, 'verificar_placar_ht_ao_vivo', new_callable=AsyncMock) as mock_placar, \
             patch.object(main, 'resumo_estatistico', new_callable=AsyncMock) as mock_resumo, \
             patch.object(main, 'salvar_fixture_pendente') as mock_salvar, \
             patch.object(main, 'obter_metricas_historicas') as mock_metricas, \
             patch.object(main, 'calcular_bonus_historico') as mock_bonus, \
             patch('main.datetime') as mock_datetime:
            
            # Setup mocks
            mock_dt = MagicMock()
            mock_dt.hour = 10
            mock_datetime.now.return_value = mock_dt
            
            mock_fixture.return_value = 12345
            mock_odd.return_value = main.OddResultado("2.05", "live")
            mock_placar.return_value = 0
            mock_resumo.return_value = "Historical data"
            mock_metricas.return_value = (0.65, None)
            mock_bonus.return_value = (1, ["Histórico favorável"])
            
            mock_bot.send_message = AsyncMock()
            
            await main.analisar(texto)
            
            # Verify message was sent with ALTA confidence
            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args
            message_text = call_args[1]['text']
            assert "ALTA" in message_text or "MUITO ALTA" in message_text

    @pytest.mark.asyncio
    async def test_analisar_muito_alta_confidence(self):
        """Test signal analysis identifies MUITO ALTA confidence correctly."""
        # Create text that will generate >= 12 points
        texto = """⚽️ Flamengo x Palmeiras
⏰ 18
OVER 0.5 HT: 75%
Ataques Perigosos: 20/15
Posse de Bola: 65%/35%
Escanteios: 5/3
No Gol: 3/2
Fora do Gol: 3/2
🌡️ 22°C
☁️ 40%
💧 60%
💨 5 m/s"""
        
        with patch.object(main, 'bot') as mock_bot, \
             patch.object(main, 'buscar_fixture_id', new_callable=AsyncMock) as mock_fixture, \
             patch.object(main, 'buscar_odd_pre_live', new_callable=AsyncMock) as mock_odd, \
             patch.object(main, 'verificar_placar_ht_ao_vivo', new_callable=AsyncMock) as mock_placar, \
             patch.object(main, 'resumo_estatistico', new_callable=AsyncMock) as mock_resumo, \
             patch.object(main, 'salvar_fixture_pendente') as mock_salvar, \
             patch.object(main, 'obter_metricas_historicas') as mock_metricas, \
             patch.object(main, 'calcular_bonus_historico') as mock_bonus, \
             patch('main.datetime') as mock_datetime:
            
            mock_dt = MagicMock()
            mock_dt.hour = 10
            mock_datetime.now.return_value = mock_dt
            
            mock_fixture.return_value = 12345
            mock_odd.return_value = main.OddResultado("2.05", "live")
            mock_placar.return_value = 0
            mock_resumo.return_value = "Historical data"
            mock_metricas.return_value = (0.80, "GREEN")
            mock_bonus.return_value = (1, ["Histórico próprio favorável"])
            
            mock_bot.send_message = AsyncMock()
            
            await main.analisar(texto)
            
            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args
            message_text = call_args[1]['text']
            # Should have MUITO ALTA confidence
            assert "MUITO ALTA" in message_text


class TestAPIIntegration:
    """Test suite for API integration functions."""

    @pytest.mark.asyncio
    async def test_buscar_fixture_id_not_found(self):
        """Test buscar_fixture_id returns None when fixture not found."""
        mock_response = MockResponse(200, {"response": []})
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.buscar_fixture_id("NonExistent Team x Another Team")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_buscar_fixture_id_empty_name(self):
        """Test buscar_fixture_id returns None for empty game name."""
        result = await main.buscar_fixture_id("")
        assert result is None

    @pytest.mark.asyncio
    async def test_buscar_fixture_id_success(self):
        """Test buscar_fixture_id returns fixture ID on success."""
        mock_response = MockResponse(200, {
            "response": [{
                "fixture": {"id": 12345},
                "teams": {
                    "home": {"name": "Flamengo"},
                    "away": {"name": "Palmeiras"}
                }
            }]
        })
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.buscar_fixture_id("Flamengo x Palmeiras")
            
            assert result == 12345

    @pytest.mark.asyncio
    async def test_buscar_odd_ao_vivo_not_found(self):
        """Test buscar_odd_ao_vivo returns N/D when odd not found."""
        mock_response = MockResponse(200, {"response": []})
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.buscar_odd_ao_vivo(12345, 0.5)
            
            assert result == "N/D"

    @pytest.mark.asyncio
    async def test_buscar_odd_ao_vivo_success(self):
        """Test buscar_odd_ao_vivo returns odd value on success."""
        mock_response = MockResponse(200, {
            "response": [{
                "bookmakers": [{
                    "bets": [{
                        "name": "1st Half - Over/Under",
                        "values": [{
                            "value": "Over 0.5",
                            "odd": "2.05"
                        }]
                    }]
                }]
            }]
        })
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.buscar_odd_ao_vivo(12345, 0.5)
            
            assert result == "2.05"

    @pytest.mark.asyncio
    async def test_buscar_odd_pre_live_no_fixture_id(self):
        """Test buscar_odd_pre_live returns unavailable for no fixture ID."""
        result = await main.buscar_odd_pre_live(None, 0.5)
        
        assert result.valor == "N/D"
        assert result.origem == "unavailable"

    @pytest.mark.asyncio
    async def test_buscar_odd_pre_live_success(self):
        """Test buscar_odd_pre_live returns odd on success."""
        mock_response = MockResponse(200, {
            "response": [{
                "bookmakers": [{
                    "bets": [{
                        "name": "First Half Total",
                        "values": [{
                            "value": "Over 0.5",
                            "odd": "1.95"
                        }]
                    }]
                }]
            }]
        })
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.buscar_odd_pre_live(12345, 0.5)
            
            assert result.valor == "1.95"
            assert result.origem == "pre-live"

    @pytest.mark.asyncio
    async def test_buscar_odd_pre_live_fallback_to_live(self):
        """Test buscar_odd_pre_live falls back to live odds."""
        # Mock response for pre-live (empty)
        mock_pre_live_response = MockResponse(200, {"response": []})
        
        # Mock response for live odds (has data)
        mock_live_response = MockResponse(200, {
            "response": [{
                "bookmakers": [{
                    "bets": [{
                        "name": "1st Half Over/Under",
                        "values": [{
                            "value": "Over 0.5",
                            "odd": "2.10"
                        }]
                    }]
                }]
            }]
        })
        
        # Create separate sessions for pre-live and live calls
        mock_pre_live_session = MockClientSession(mock_pre_live_response)
        mock_live_session = MockClientSession(mock_live_response)
        
        with patch('aiohttp.ClientSession', side_effect=[mock_pre_live_session, mock_live_session]):
            result = await main.buscar_odd_pre_live(12345, 0.5)
            
            assert result.valor == "2.10"
            assert result.origem == "live"

    @pytest.mark.asyncio
    async def test_verificar_placar_ht_ao_vivo_no_fixture_id(self):
        """Test verificar_placar_ht_ao_vivo returns None for no fixture ID."""
        result = await main.verificar_placar_ht_ao_vivo(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_verificar_placar_ht_ao_vivo_success(self):
        """Test verificar_placar_ht_ao_vivo returns correct score."""
        mock_response = MockResponse(200, {
            "results": 1,
            "response": [{
                "score": {
                    "halftime": {
                        "home": 1,
                        "away": 0
                    }
                }
            }]
        })
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.verificar_placar_ht_ao_vivo(12345)
            
            assert result == 1

    @pytest.mark.asyncio
    async def test_verificar_placar_ht_ao_vivo_no_results(self):
        """Test verificar_placar_ht_ao_vivo returns 0 when no results."""
        mock_response = MockResponse(200, {"results": 0})
        mock_session = MockClientSession(mock_response)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await main.verificar_placar_ht_ao_vivo(12345)
            
            assert result == 0
