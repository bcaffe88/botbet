import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def gerar_resposta_ia(msg):
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um analista esportivo técnico com foco em sinais ao vivo."},
                {"role": "user", "content": msg}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return resposta['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"❌ Erro na IA: {e}"
