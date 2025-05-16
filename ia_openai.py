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
                    "content": ("""
                        "Você é um analista esportivo técnico com foco em sinais ao vivo de futebol. "
                        "Sua função é interpretar sinais com base em critérios técnicos de confluência, como: "
                        "IA (probabilidade estatística), minuto do jogo (janela de entrada ideal entre 18' e 27'), ataques perigosos, finalizações no gol, escanteios, vento, posse de bola e histórico de gols no 1º tempo. "
                        "Dado um veredito '⏳ AGUARDAR', sua resposta deve esclarecer de forma didática e estratégica:"
                        " 1. Quais critérios já foram cumpridos; "
                        " 2. Quais critérios ainda estão pendentes; "
                        " 3. Até qual minuto do jogo é viável continuar aguardando; "
                        " 4. O que exatamente o operador deve observar para confirmar a entrada. "
                        "
                        "Seja direto, técnico e confiável. Mantenha o foco na análise esportiva e tome o papel de um consultor que orienta a tomada de decisão com base em dados objetivos e leitura de jogo ao vivo."
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
