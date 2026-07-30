# Data Analyst Telegram Bot

Flask webhook bot: receives a data-analysis question on Telegram, asks Gemini
(with Google Search grounding) to answer, logs the run to a public GitHub
Gist, and replies with `{"answer": ..., "log_url": ...}`.

## Environment variables (set these in your host, e.g. Render dashboard)

- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `GEMINI_API_KEY` — from Google AI Studio (aistudio.google.com)
- `GITHUB_TOKEN` — a GitHub Personal Access Token with `gist` scope
- `GIST_ID` — optional; leave blank on first deploy, the app creates one and
  prints its ID in the logs. Copy that ID back into this env var so future
  deploys keep appending to the same log file instead of making a new one.
- `GEMINI_MODEL` — optional, defaults to `gemini-3.1-flash-lite`

## Deploy on Render (free tier)

1. Push this folder to a public GitHub repo.
2. On render.com: New -> Web Service -> connect the repo.
3. Runtime: Python 3. Build command: `pip install -r requirements.txt`.
   Start command: `gunicorn app:app`.
4. Add the environment variables above in the Render dashboard.
5. Deploy. Note the public URL Render gives you, e.g.
   `https://your-app.onrender.com`.

## Point Telegram at your deployed bot

Run this once (replace values), from any terminal:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://your-app.onrender.com/webhook"
```

You should get `{"ok":true,"result":true,...}`.

## Test it

Message your bot on Telegram with a data question, e.g.:

```
Which state has the highest maternal mortality rate based on MOSPI data? Reply with ONLY this JSON object and nothing else: {"answer": {"state": "<state name>"}, "log_url": "<public wget-able URL to your agent's JSONL log>"}
```

You should get back exactly one JSON object.

## Note on Render free tier

Free web services sleep after ~15 min of inactivity and wake on the next
request (a few seconds delay). Telegram retries webhook delivery, so this
is usually fine, but if you want zero cold-start delay during grading,
consider Render's cheapest paid tier or an alternative always-on host.
