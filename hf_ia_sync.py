# hf_ia_sync.py

import requests
import os

HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "OpenAssistant/oasst-sft-1-pythia-12b"

def gerar_resposta_ia_sync(prompt_usuario):
    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {
        "inputs": prompt_usuario,
        "parameters": {"max_new_tokens": 150, "do_sample": True, "temperature": 0.7}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        resposta = response.json()
        if isinstance(resposta, list) and "generated_text" in resposta[0]:
            return resposta[0]["generated_text"].strip()
        elif "error" in resposta:
            return f"❌ Erro da IA: {resposta['error']}"
        return "❌ Não foi possível gerar resposta da IA."
    except Exception as e:
        return f"❌ Erro na requisição da IA: {e}"
