from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def gerar_resposta_ia(pergunta):
    try:
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Você é uma IA especialista em probabilidades (PhD) e análises técnicas de jogos de futebol (Mestre), 
                com foco em apostas esportivas. Forneça insights baseados em dados, como: estatísticas de times, odds value,
                desempenho em casa/fora, lesões, confrontos históricos e tendências de mercado.
                Seja direto, use métricas claras e sugira apostas apenas quando houver valor estatístico. 
                Adapte respostas para iniciantes ou experts, conforme o contexto."""},
                {"role": "user", "content": pergunta}
                ],
    temperature=0.7,
    max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA: {e}"
