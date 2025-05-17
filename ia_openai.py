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
                    "content": ("""
                        Responda objetivamente com lógica de probabilidades, considerando:  

1. **Confluência Atual** (em 1 frase):  
   - Alta (5/5 critérios)  
   - Média (4/5 critérios)  
   - Baixa (≤3/5 critérios)  

2. **Histórico Recente** (em 1 linha):  
   - 📊 X/5 jogos com gol no 1º tempo  

3. **Veredito Final** (em 1 frase):  
   - ENTRAR: [Probabilidade]% de gol até X min  
   - AGUARDAR: [Faltam Y critérios, explique] até X min"  
   - EVITAR: [Razão técnica]  

**Exemplo Prático:**  
Alta confluência (5/5). 📊 4/5 jogos com gol HT. ENTRAR: 85% de gol até 25 min.

**Regras:**  
- Máximo 3 frases  
- Dados concretos (números, %)  
- Linguagem direta (sem rodeios)"""  
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
