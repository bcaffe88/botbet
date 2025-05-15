import os
from openai import OpenAI

# Cria o cliente com a chave de API
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def gerar_resposta_ia(texto):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um analista esportivo técnico com foco em sinais ao vivo."},
                {"role": "user", "content": texto}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA OpenAI: {e}"
