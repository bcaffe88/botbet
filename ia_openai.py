from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def gerar_resposta_ia(pergunta):
    try:
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Você é um phd em probabilidades e mestre analista esportivo  com foco em sinais over 0.5 ht, responda:
📌 Conclusão:
[Resumo da situação com leitura tática e cruzamento de estatísticas]."""},
                {"role": "user", "content": pergunta}
                ],
    temperature=0.7,
    max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA: {e}"
