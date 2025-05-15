from openai import OpenAI
import os
import asyncio

# Cria o cliente corretamente sem argumentos inválidos
client = OpenAI()

async def gerar_resposta_ia(mensagem_usuario):
    try:
        resposta = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um analista esportivo técnico com foco em sinais ao vivo."},
                {"role": "user", "content": mensagem_usuario}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA OpenAI: {e}"
