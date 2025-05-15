import aiohttp
import os

HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.1"

async def gerar_resposta_ia(prompt_usuario):
    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {
        "inputs": prompt_usuario,
        "parameters": {"max_new_tokens": 150, "do_sample": True, "temperature": 0.7}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                resposta = await response.json()
                if isinstance(resposta, list) and "generated_text" in resposta[0]:
                    return resposta[0]["generated_text"].strip()
                elif "error" in resposta:
                    return f"❌ Erro da IA: {resposta['error']}"
                return "❌ Não foi possível gerar resposta da IA."
    except Exception as e:
        return f"❌ Erro na requisição da IA: {e}"
