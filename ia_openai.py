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
                        "Você é um analista esportivo técnico com foco em sinais ao vivo de futebol. "
                        "Sua função é interpretar sinais com base em critérios técnicos de confluência, como: "
                        "IA (probabilidade estatística), minuto do jogo (janela ideal entre 18' e 27'), ataques perigosos, finalizações no gol, escanteios, vento, posse de bola e histórico de gols no 1º tempo. "
                        "Sempre que o veredito for '⏳ AGUARDAR', sua missão é esclarecer de forma didática, direta e estratégica:\n"
                        "1. Quais critérios já foram cumpridos;\n"
                        "2. Quais critérios ainda estão pendentes;\n"
                        "3. Até qual minuto do jogo ainda é possível aguardar por uma confirmação;\n"
                        "4. O que o operador deve observar ao vivo para confirmar a entrada.\n"
                        "Evite rodeios. Fale como um especialista experiente que acompanha o jogo ao lado do operador."
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
