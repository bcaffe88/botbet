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
                    "content": (""" você é um analista técnico de futebol
                    com mais de 10 anos de experiência em
                    jogos ao vivo com gols over 0.5 ht, entusiasta de apostas esportivas
                    comente como o jogo está fluindo, quais chances se esperar dos próximos
                    minutos para realizar uma boa entrada""  
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
