from openai import AsyncOpenAI
import os

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def gerar_resposta_ia(pergunta):
    try:
        resposta = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista técnico especialista em sinais ao vivo de futebol. "
                        "Sua tarefa é analisar critérios técnicos como: IA, minuto do jogo, ataques perigosos, finalizações no gol, posse de bola, escanteios, vento e histórico de gols no 1º tempo. "
                        "Se o veredito for '⏳ AGUARDAR', você deve explicar o que já foi atendido e o que ainda falta para haver confluência técnica suficiente para uma entrada com confiança e até qual minuto aguardar. "
                        "Sua resposta deve ser objetiva, tática e baseada em dados. Use linguagem clara, como se estivesse orientando um trader atento que precisa de segurança para agir."
                        "Evite rodeios. Fale como um especialista experiente que acompanha o jogo ao lado do operador."
                    )
                },
                {"role": "user", "content": pergunta}
            ],
            temperature=0.7,
            max_tokens=350
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro na IA OpenAI: {e}"
