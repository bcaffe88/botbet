
import aiohttp
import os

HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "google/flan-t5-small"  # Modelo leve e disponível publicamente

async def gerar_resposta_ia(prompt_usuario):
    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {
        "inputs": f"Resuma esse texto: {prompt_usuario}",
        "parameters": {"max_new_tokens": 100}
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                resposta = await response.json()
                if isinstance(resposta, list) and "generated_text" in resposta[0]:
                    return resposta[0]["generated_text"].strip()
                elif isinstance(resposta, dict) and "generated_text" in resposta:
                    return resposta["generated_text"].strip()
                elif "error" in resposta:
                    return f"❌ Erro da IA: {resposta['error']}"
                return "❌ Não foi possível gerar resposta da IA."
    except Exception as e:
        return f"❌ Erro na requisição da IA: {e}"
