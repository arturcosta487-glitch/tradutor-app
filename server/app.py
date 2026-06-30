"""
SERVIDOR DE KEYS - Tradutor PT-BR
=================================
API simples que:
  - gera keys novas (usadas pelo site)
  - valida uma key + hwid (usado pelo app desktop)

Cada key fica "travada" no primeiro computador que validar com ela
(igual a maioria dos sistemas de licença por aí). Se quiser permitir
mais de um computador por key, é só mexer na função validate().

----------------------------------------------------------------------
COMO RODAR LOCALMENTE (teste):
----------------------------------------------------------------------
1) pip install -r requirements.txt
2) python app.py
   -> sobe em http://localhost:5000

----------------------------------------------------------------------
COMO SUBIR DE GRAÇA NO RENDER (produção):
----------------------------------------------------------------------
1) Crie um repositório no GitHub só com a pasta "server" (este arquivo
   + requirements.txt).
2) Entre em https://render.com -> New + -> Web Service -> conecte o
   repositório.
3) Configurações:
     Build Command:  pip install -r requirements.txt
     Start Command:  gunicorn app:app
4) Depois do deploy, o Render te dá uma URL tipo:
     https://tradutor-key-server.onrender.com
   Essa URL é o BASE_URL que você vai colocar no site (index.html) e
   no app desktop (launcher.py).

OBS: o plano free do Render "dorme" depois de uns minutos sem uso e
demora ~30s pra acordar na primeira chamada. Pra um app pessoal/grupo
pequeno não costuma ser problema.
----------------------------------------------------------------------
"""

import os
import time
import sqlite3
import secrets

from flask import Flask, request, jsonify
from flask_cors import CORS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.db")

app = Flask(__name__)
CORS(app)  # permite o site (rodando em outro domínio) chamar essa API


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            hwid TEXT,
            created_at INTEGER,
            last_used_at INTEGER,
            active INTEGER DEFAULT 1
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def generate_unique_key():
    conn = get_db()
    while True:
        chunks = [secrets.token_hex(2).upper() for _ in range(3)]
        key = "TRAD-" + "-".join(chunks)  # ex: TRAD-9F3A-1C2B-77E0
        exists = conn.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone()
        if not exists:
            conn.close()
            return key


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "tradutor-key-server"})


@app.route("/api/keys/generate", methods=["POST"])
def generate():
    """Cria uma key nova e devolve pro site. Sem limite por enquanto -
    se quiser, dá pra travar por IP ou exigir login antes de chamar
    essa rota (recomendo isso se for distribuir publicamente)."""
    key = generate_unique_key()
    conn = get_db()
    conn.execute(
        "INSERT INTO keys (key, hwid, created_at, last_used_at, active) "
        "VALUES (?, NULL, ?, NULL, 1)",
        (key, int(time.time())),
    )
    conn.commit()
    conn.close()
    return jsonify({"key": key})


@app.route("/api/keys/validate", methods=["POST"])
def validate():
    """Chamada pelo app desktop toda vez que clica em LAUNCH."""
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip()
    hwid = (data.get("hwid") or "").strip()

    if not key:
        return jsonify({"valid": False, "reason": "Digite uma key."}), 400
    if not hwid:
        return jsonify({"valid": False, "reason": "Não foi possível identificar o computador."}), 400

    conn = get_db()
    row = conn.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"valid": False, "reason": "Key inválida."}), 404

    if not row["active"]:
        conn.close()
        return jsonify({"valid": False, "reason": "Essa key foi desativada."}), 403

    if row["hwid"] is None:
        # primeira vez que essa key é usada -> trava nesse computador
        conn.execute(
            "UPDATE keys SET hwid=?, last_used_at=? WHERE key=?",
            (hwid, int(time.time()), key),
        )
        conn.commit()
    elif row["hwid"] != hwid:
        conn.close()
        return jsonify({"valid": False, "reason": "Essa key já está em uso em outro computador."}), 403
    else:
        conn.execute("UPDATE keys SET last_used_at=? WHERE key=?", (int(time.time()), key))
        conn.commit()

    conn.close()
    return jsonify({"valid": True})


# --- rotas opcionais de administração (uso manual, não tem tela) -----
# Dá pra chamar com curl/Postman pra gerenciar keys na mão.

@app.route("/api/keys/<key>/deactivate", methods=["POST"])
def deactivate(key):
    conn = get_db()
    conn.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/keys/<key>/reset-hwid", methods=["POST"])
def reset_hwid(key):
    """Libera a key pra ser usada em outro computador (ex: usuário
    trocou de PC)."""
    conn = get_db()
    conn.execute("UPDATE keys SET hwid=NULL WHERE key=?", (key,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
