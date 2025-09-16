### Bluesky Image Feed (Flask + Bluesky + OpenAI)

A Flask web app and bot that authenticates to Bluesky, fetches posts with images from your home timeline (followed accounts only), downloads media, and exposes a simple API/UI. It also includes an AI reply helper that sends images + context to OpenAI GPT‑4o.

### What’s inside
- Bluesky client with AWS SSM–backed secrets (`src/bluesky_bot.py`)
- Flask API and UI (`src/app.py`, `templates/`, `static/`)
- AI persona/config system with file-backed defaults (`src/ai_config.py`, `user_config.json`)
- Functional test suite (real keys supported) with pytest (`tests/`)

### Quick start
1) Install deps
```bash
pip install -r requirements.txt
```
2) Configure
- In AWS SSM Parameter Store: set `BLUESKY_PASSWORD_BIKELIFE` to your password
- In `src/config.py`: set `BLUESKY_HANDLE` and `AWS_REGION`
3) Run
```bash
python main.py
```

### API overview
- GET `/api/posts` — posts with images from your home timeline
  - Query: `count` (1–18), `max_per_user` (must be 1), `max_fetches` (1–2000)
- GET `/api/image/<filename>` — serve downloaded images from a temp dir
- GET `/api/status` — app status and metadata
- GET `/api/ai-config` — read AI persona/config
- POST `/api/ai-config` — update persona/config (selected fields)
- POST `/api/ai-config/reset` — reset persona/config to defaults
- POST `/api/ai-reply` — generate a witty reply using GPT‑4o for provided images
- GET `/api/posts/stream` — server-sent events stream of progress while fetching

### Testing
- Streamlined test suite with real API integration tests and unit tests
- Recommended env: conda `fastai`
- Tests use real API keys and calls (no mocks for integration tests)

**Run tests:**
```bash
# Unit tests only (no external dependencies)
python run_tests.py --type unit

# Integration tests (requires real API keys)
python run_tests.py --type integration

# All tests
python run_tests.py --type all

# Include slow tests
python run_tests.py --type integration --slow
```

**Or use pytest directly:**
```bash
# Unit tests
pytest -m unit

# Integration tests  
pytest -m integration

# All tests
pytest
```

### Use cases
- Personal, image‑focused Bluesky reader for followed accounts
- Back-end for a lightweight social dashboard or content pipeline
- Dataset creation: collect post metadata + images for analysis
- Human-in-the-loop reply assistant using OpenAI for humor/style

### GitHub Actions CI/CD

The project includes automated testing via GitHub Actions that runs on pushes to the `main` branch. The CI workflow supports both AWS SSM and GitHub Secrets for configuration.

**Required GitHub Secrets:**
- `BLUESKY_PASSWORD_BIKELIFE` - Your Bluesky password
- `OPENAI_API_KEY` - Your OpenAI API key for AI reply generation

**Configuration Notes:**
- `BLUESKY_HANDLE` - Your Bluesky handle (not secret, configured in config.py with default value)

**How it works:**
1. The CI workflow first attempts to use AWS SSM Parameter Store for secrets
2. If SSM is unavailable, it falls back to GitHub Secrets via environment variables
3. Tests run with real API calls to ensure integration works properly
4. No AWS credentials are required in GitHub Actions - only the actual secret values

**Setting up GitHub Secrets:**
1. Go to your repository → Settings → Secrets and variables → Actions
2. Add the required secrets listed above
3. Push to `main` branch to trigger the CI workflow

### Notes
- Credentials are pulled from AWS SSM with GitHub Secrets fallback; no `.env` is required
- GitHub Actions uses secrets directly without requiring AWS credentials
- Images are stored in a temporary directory and served via `/api/image/...`
- Rate limiting and basic security checks are enabled by default

### License
MIT