# Vartalap 🤖💬

**Vartalap** is an autonomous browser-agent service that manages Reddit DM conversations on your behalf using Playwright, FastAPI, APScheduler, and a backend-agnostic LLM planner.

---

## 🌟 Architecture & Features

- **Session Manager (`vartalap/session.py`)**: Manages persistent Playwright Chromium contexts using `storage_state.json` (cookies & localStorage) so you stay logged into Reddit without re-authenticating every run.
- **Perception (`vartalap/perception.py`)**: DOM-first page state extractor for DM inbox threads and conversation history `[{sender, text, timestamp}]`. Automatically falls back to screenshot capture if DOM parsing fails.
- **Planner (`vartalap/planner.py`)**: Backend-agnostic LLM decision layer with 3 interchangeable backends configured purely via `config.yaml`:
  - **`cli`**: Shells out to agentic CLI tools (e.g. `antigravity -p "{prompt}"`).
  - **`ollama_cloud`**: Connects to Ollama Cloud REST endpoints.
  - **`api`**: Hosted LLM providers (OpenAI / Anthropic compatible).
- **Executor (`vartalap/executor.py`)**: Converts JSON planner actions (`open_thread`, `reply`, `done`, `skip`) into real Playwright interactions. Features randomized 300–1200ms delays between human-like typing and clicking. Supports **`dry_run`** mode.
- **Agent Loop (`vartalap/agent_loop.py`)**: Coordinates the `perceive ➔ plan ➔ execute ➔ re-perceive` lifecycle with hard caps on `max_steps_per_conversation` and daily message limits (`max_messages_per_day`).
- **Scheduler (`vartalap/scheduler.py`)**: Built-in APScheduler background service that scans for unread DMs on a watchlist and triggers conversation handlers at configurable polling intervals. Hot-reloads configuration without service restarts.
- **FastAPI API (`vartalap/main.py`)**: REST API with endpoints (`POST /run`, `GET /logs`, `GET /health`, `POST /scheduler/tick`) protected via API key authentication.
- **SQLite Logger (`vartalap/logger.py`)**: Audit log tracking all LLM prompts, raw responses, executed actions, and sent messages with UTC timestamps.

---

## 🚀 Quick Start & Installation

### 1. Clone & Install Dependencies

```bash
cd vartalap
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and set your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```env
OLLAMA_API_KEY=your_ollama_key_here
LLM_API_KEY=your_openai_or_anthropic_key_here
VARTALAP_API_KEY=your_secret_api_key_here
```

### 3. One-Time Reddit Login Step 🔑

Run the headed browser login helper to log in manually once and save your authentication session state to `storage_state.json`:

```bash
python -m vartalap.login
# OR
python vartalap/session.py
```

1. A Chromium browser window will open at `https://www.reddit.com/login`.
2. Log into your Reddit account manually (including 2FA if enabled).
3. Return to the terminal and press **ENTER**.
4. The session cookies and localStorage will be saved to `./storage_state.json`.

---

## ⚙️ Configuration (`config.yaml`)

All service settings are centralized in `config.yaml`. Environment variables inside `${VAR}` syntax are dynamically resolved from `.env` and system env.

```yaml
llm:
  backend: cli              # Options: cli | ollama_cloud | api
  cli:
    command: "antigravity -p {prompt}"
    timeout_seconds: 60
  ollama_cloud:
    endpoint: "https://ollama.example/api"
    model: "llama3.1-cloud"
    api_key: "${OLLAMA_API_KEY}"
  api:
    provider: "openai"      # Options: openai | anthropic
    model: "gpt-4o-mini"
    api_key: "${LLM_API_KEY}"

reddit:
  storage_state_path: "./storage_state.json"
  inbox_url: "https://www.reddit.com/message/messages"
  chat_url: "https://chat.reddit.com"

agent:
  watchlist: []              # empty = handle any unread DM; e.g. ["elonmusk", "samaltman"]
  max_steps_per_conversation: 6
  max_messages_per_day: 20
  dry_run: true              # Safety default: set false for live sends

scheduler:
  polling_interval_minutes: 10

security:
  api_key: "${VARTALAP_API_KEY}"
```

### Switching LLM Backends

To switch backends, simply change `llm.backend` in `config.yaml`:
- **CLI Mode**: `backend: cli` (uses local tool like `antigravity`)
- **Ollama Cloud**: `backend: ollama_cloud`
- **Hosted API**: `backend: api`

No code edits are required! The scheduler hot-reloads `config.yaml` on every polling tick.

---

## 🏃 Running the Service & API

Start the FastAPI server (which automatically starts the background scheduler):

```bash
uvicorn vartalap.main:app --host 0.0.0.0 --port 8000 --reload
```

### 📡 API Endpoints

#### 1. Trigger Conversation Run: `POST /run`

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_api_key_here" \
  -d '{
    "username": "elonmusk",
    "instruction": "Reply to elon, keep the tone casual",
    "dry_run": true
  }'
```

#### 2. Retrieve Audit Logs: `GET /logs`

```bash
curl -X GET "http://localhost:8000/logs?limit=50&username=elonmusk" \
  -H "X-API-Key: your_secret_api_key_here"
```

#### 3. Health Check: `GET /health`

```bash
curl http://localhost:8000/health
```

---

## 🔧 Updating Reddit CSS Selectors (TODOs)

Reddit occasionally updates its HTML markup. Selectors are centralized in the respective modules for easy tuning:

- **Perception Selectors (`vartalap/perception.py`)**:
  - `INBOX_THREAD_SELECTOR`: Container for thread items in inbox list.
  - `UNREAD_BADGE_SELECTOR`: Selector identifying unread status.
  - `MESSAGE_ITEM_SELECTOR`: Message bubble or message container.
  - `MESSAGE_SENDER_SELECTOR`, `MESSAGE_BODY_SELECTOR`, `MESSAGE_TIME_SELECTOR`.

- **Executor Selectors (`vartalap/executor.py`)**:
  - `THREAD_ITEM_TEMPLATE`: Pattern to click on a target user thread.
  - `COMPOSER_SELECTOR`: Textarea or contenteditable element for typing replies.
  - `SEND_BUTTON_SELECTOR`: Button to submit/send reply.

---

## 🧪 Running Tests

Run the unit and integration test suite:

```bash
PYTHONPATH=. pytest tests/test_vartalap.py
```
