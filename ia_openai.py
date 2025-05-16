import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def gerar_resposta_ia(pergunta):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista esportivo técnico focado em sinais ao vivo de futebol. "
                        "Sua função é interpretar sinais com base nos seguintes critérios técnicos: "
                        "IA (Inteligência Artificial), minuto do jogo, ataques perigosos, finalizações no gol, escanteios, vento, posse de bola e histórico de gols no 1º tempo. "
                        "Dado um veredito '⏳ AGUARDAR', você deve responder com clareza quais critérios já foram cumpridos, quais ainda faltam, e até qual minuto ainda é viável aguardar evolução para realizar a entrada. "
                        "Sua resposta deve ser objetiva, com tom de especialista, orientando o operador a observar se a confluência esperada se confirma nos próximos minutos."
                    ),
                },
                {"role": "user", "content": pergunta}
            ],
            temperature=0.7,
            max_tokens=350
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"❌ Erro na IA OpenAI: {e}"
