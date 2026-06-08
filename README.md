# PR Review Bot

AI-powered GitHub PR reviewer. Posts inline code review comments using GPT-4o.

## Architecture

```
GitHub PR Event
    ↓
POST /github/webhook  (FastAPI, signature-verified)
    ↓
diff_processor.py     (filter files, truncate, extract context)
    ↓
llm_reviewer.py       (structured prompt → GPT-4o → PRReviewResult)
    ↓
github_service.py     (post inline comments via GitHub App API)
```

## Setup

### 1. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a GitHub App
1. Go to GitHub → Settings → Developer settings → GitHub Apps → New GitHub App
2. Set Webhook URL to your public URL (use [ngrok](https://ngrok.com) for local dev)
3. Set Webhook secret (save it — goes in `.env`)
4. Permissions needed:
   - Pull requests: **Read & Write**
   - Contents: **Read**
5. Generate a private key → download the `.pem` file → put it in project root

### 3. Configure environment
```bash
cp .env.example .env
# Fill in GITHUB_APP_ID, GITHUB_WEBHOOK_SECRET, OPENAI_API_KEY
```

### 4. Run locally
```bash
# Terminal 1: start the server
uvicorn app.main:app --reload --port 8000

# Terminal 2: expose to GitHub via ngrok
ngrok http 8000
# Copy the https://xxx.ngrok.io URL → set as webhook URL in GitHub App settings
```

### 5. Install your GitHub App on a repo
Go to your GitHub App → Install App → select a repo → open a PR → watch the bot comment!

## Running Tests
```bash
pytest tests/ -v
```

## Project Structure
```
pr-review-bot/
├── app/
│   ├── main.py                  # FastAPI app
│   ├── api/
│   │   └── webhook.py           # POST /github/webhook
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   └── models.py            # Pydantic models (PRReviewResult, etc.)
│   └── services/
│       ├── diff_processor.py    # Parse & filter PR diffs
│       ├── llm_reviewer.py      # OpenAI structured output
│       └── github_service.py    # GitHub App auth + post review
└── tests/
    └── test_diff_processor.py
```

## Resume Bullet Points (fill in numbers after running it)
> Built an AI-powered GitHub PR review bot; designed a diff-chunking pipeline with file filtering and context truncation, GPT-4o structured outputs (Pydantic-validated), and dynamic rule injection; FastAPI webhook backend with HMAC-SHA256 verification; reduced per-review latency to ~Xs (p50) at ~$X/review cost.
