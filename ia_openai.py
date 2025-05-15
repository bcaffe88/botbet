# ia_openai.py - Compatível com openai==0.28.0

import openai
import os

# Define a chave da API
openai.api_key = os.getenv("OPENAI_API_KEY")

async def gerar_resposta_ia(mensagem_usuario):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um analista esportivo técnico com foco em sinais ao vivo. Seja direto, objetivo e técnico nas respostas."
                },
                {
                    "role": "user",
                    "content": mensagem_usuario
                }
            ],
            temperature=0.7,
            max_tokens=350
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Erro na IA OpenAI: {e}"
