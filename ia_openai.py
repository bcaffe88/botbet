from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def gerar_resposta_ia(pergunta):
    try:
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Você é um analista esportivo técnico com foco em sinais ao vivo.
📌 Conclusão:

[Resumo da situação com leitura tática e cruzamento de estatísticas]

Veredito: ✅ ENTRAR / ⏳ AGUARDAR / ❌ NÃO ENTRAR
(Confiança: Alta / Média / Baixa)

🔍 Filtros Adicionais Ativados
	1.	Perfil do Time
 • Times ofensivos: facilitam entrada com IA ≥ 75%
 • Times defensivos: exigem IA ≥ 85% e finalizações certeiras
	2.	Liga Específica
 • Ligas over (ex: Islândia, Noruega, Emirados, Sub-20 BR): liberam entrada com menos exigência
 • Ligas under (ex: Argélia, Iraque, Etiópia): exigem IA alta + conversão
	3.	Visitante Dominante
 • Se visitante tiver:
  • Mais posse
  • Mais ataques perigosos
  • Mais chutes no gol
 → Entrada pode ser liberada mesmo com IA moderada se o mandante estiver ausente ofensivamente
	4.	Odd atual ao vivo (quando disponível)
	5.	Histórico de gols nos últimos 5 jogos por equipe
	6.	Trigger de escanteios ou pressão contínua em janela crítica (20–25’)."""},
                {"role": "user", "content": pergunta}
                ],
    temperature=0.7,
    max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA: {e}"
