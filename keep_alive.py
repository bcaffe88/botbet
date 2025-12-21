from flask import Flask, jsonify
from datetime import datetime, timezone
from estatisticas_time import metrics_snapshot
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Webhook ativo e monitorando"

@app.route('/metrics')
def metrics():
    snap = metrics_snapshot()
    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": snap,
    })

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
