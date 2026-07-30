import os
import json
import time
import uuid
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GIST_ID = os.environ.get("GIST_ID", "")  # leave blank on first deploy; we create one automatically
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# in-memory per-chat history (fine for this scale; resets on redeploy)
chat_history = {}


def send_telegram_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=30)


def call_llm(prompt):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def ensure_gist():
    global GIST_ID
    if GIST_ID:
        return GIST_ID
    r = requests.post(
        "https://api.github.com/gists",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={
            "description": "TDS Project 1 - Telegram data analyst bot run log",
            "public": True,
            "files": {"run.jsonl": {"content": "{}\n"}},
        },
        timeout=30,
    )
    r.raise_for_status()
    GIST_ID = r.json()["id"]
    print(f"Created new gist: {GIST_ID}. Set GIST_ID env var to this to reuse it.", flush=True)
    return GIST_ID


def append_log(entry):
    gist_id = ensure_gist()
    r = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    current = r.json()["files"]["run.jsonl"]["content"]
    new_content = current.rstrip("\n") + "\n" + json.dumps(entry) + "\n"
    requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"files": {"run.jsonl": {"content": new_content}}},
        timeout=30,
    )
    user = r.json()["owner"]["login"]
    return f"https://gist.githubusercontent.com/{user}/{gist_id}/raw/run.jsonl"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return jsonify(ok=True)

    chat_id = message["chat"]["id"]
    text = message["text"]

    history = chat_history.setdefault(chat_id, [])
    history.append(text)
    if len(history) > 10:
        history.pop(0)

    convo = "\n".join(f"Message {i + 1}: {t}" for i, t in enumerate(history))
    prompt = (
        "You are a data analyst. Below is a conversation of messages sent to you in order. "
        "Answer only the LAST message, using earlier messages as context if relevant. "
        "If the last message specifies an exact JSON output format, respond with ONLY that "
        "exact JSON object and nothing else — no markdown formatting, no code fences, no "
        "explanation before or after it.\n\n"
        f"{convo}"
    )

    run_id = str(uuid.uuid4())

    try:
        answer_text = call_llm(prompt)
        error = None
    except Exception as e:
        answer_text = ""
        error = str(e)

    log_url = append_log(
        {
            "run_id": run_id,
            "ts": time.time(),
            "chat_id": chat_id,
            "input": text,
            "history": history[:],
            "model_output": answer_text,
            "error": error,
        }
    )

    # try to parse model output as JSON and inject the correct log_url
    final_text = None
    try:
        cleaned = answer_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            parsed["log_url"] = log_url
            final_text = json.dumps(parsed)
    except Exception:
        pass

    if final_text is None:
        # fallback: wrap whatever we got so the reply is still valid JSON
        final_text = json.dumps({"answer": answer_text or None, "log_url": log_url})

    send_telegram_message(chat_id, final_text)
    return jsonify(ok=True)


@app.route("/", methods=["GET"])
def health():
    return "OK - bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
