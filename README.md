# Hunkbot 🤖

An AI-powered GitHub App that automatically reviews pull requests using GPT-4o. When a PR is opened or updated, Hunkbot analyzes the diff, identifies bugs, security issues, and maintainability problems, and posts a structured review comment directly on the PR.

---

## Example Review

![Hunkbot reviewing a PR and identifying a bug in parking lot logic](docs/review-screenshot.png)

Hunkbot caught a critical bug: removing `floor.decrease_spotAvailability()` would allow vehicles to park beyond capacity, causing over-parking. It flagged the issue with severity, file location, and a concrete fix suggestion.

---

## How It Works

```
GitHub PR opened/updated
        ↓
POST /github/webhook        ← HMAC-SHA256 signature verified
        ↓
diff_processor.py           ← filter lock files, truncate large diffs
        ↓
llm_reviewer.py             ← GPT-4o structured output → PRReviewResult
        ↓
github_service.py           ← JWT auth → post review comment
```

1. GitHub sends a webhook event to Hunkbot when a PR is opened or updated
2. The diff is filtered (lock files, generated code removed) and truncated to stay within token limits
3. GPT-4o reviews the diff and returns a structured JSON response (Pydantic-validated)
4. Hunkbot posts the review back to GitHub with severity labels, file locations, and fix suggestions

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Uvicorn |
| LLM | GPT-4o (OpenAI structured outputs) |
| GitHub integration | PyGithub + GitHub App JWT auth |
| Data validation | Pydantic v2 |
| Deployment | Railway |
| Language | Python 3.12 |

---

## Features

- **Structured reviews** — every comment includes severity (`error` / `warning` / `suggestion`), category (`bug` / `security` / `performance` / `style` / `maintainability`), file path, line number, and a fix suggestion
- **Smart filtering** — skips lock files (`package-lock.json`, `poetry.lock`), build artifacts, and auto-generated code
- **Token-aware** — truncates large diffs to stay within context limits
- **Async processing** — webhook returns 200 immediately; review runs in background so GitHub never times out
- **Secure** — HMAC-SHA256 webhook signature verification; GitHub App JWT authentication (no long-lived tokens)

---

## Local Development

### Prerequisites
- Python 3.12
- A GitHub App ([create one here](https://github.com/settings/apps/new))
- OpenAI API key

### Setup

```bash
# Clone and install
git clone https://github.com/yiweigao0226/Hunkbot.git
cd Hunkbot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Fill in GITHUB_APP_ID, GITHUB_WEBHOOK_SECRET, OPENAI_API_KEY
# Place your GitHub App private key at ./private-key.pem

# Run
uvicorn app.main:app --reload --port 8000

# Expose to GitHub (for local testing)
ngrok http 8000
```

### Run Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
Hunkbot/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── api/
│   │   └── webhook.py           # POST /github/webhook
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   └── models.py            # Pydantic models
│   └── services/
│       ├── diff_processor.py    # Parse & filter PR diffs
│       ├── llm_reviewer.py      # GPT-4o structured output
│       └── github_service.py    # GitHub App auth + post review
└── tests/
    └── test_diff_processor.py
```

---

## Deployment

Hunkbot is deployed on Railway. Every push to `main` triggers an automatic redeploy.

The GitHub App webhook URL is set to `https://hunkbot-production.up.railway.app/github/webhook`.

For production, the GitHub App private key is stored as a base64-encoded environment variable (`GITHUB_PRIVATE_KEY_BASE64`) rather than a file.
