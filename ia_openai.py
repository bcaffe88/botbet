from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def gerar_resposta_ia(pergunta):
    try:
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um analista esportivo técnico."},
                {"role": "user", "content": pergunta}
            ]
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA: {e}"
