import os
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from vartalap.settings import load_settings, Settings, resolve_env_vars
from vartalap.planner import clean_json_response, get_llm_provider, CLILLMProvider, Planner
from vartalap.logger import init_db, log_action, log_llm_call, get_recent_logs
from vartalap.executor import execute_action
from vartalap.main import app


def test_resolve_env_vars():
    os.environ["TEST_VAR"] = "hello_world"
    text = "Value is ${TEST_VAR}"
    resolved = resolve_env_vars(text)
    assert resolved == "Value is hello_world"


def test_clean_json_response():
    markdown_json = "```json\n{\"action\": \"reply\", \"text\": \"hi\"}\n```"
    result = clean_json_response(markdown_json)
    assert result == {"action": "reply", "text": "hi"}

    raw_text = "Some intro text {\"action\": \"done\", \"reason\": \"all good\"} ending text"
    result2 = clean_json_response(raw_text)
    assert result2 == {"action": "done", "reason": "all good"}


def test_logger_db(tmp_path):
    db_file = tmp_path / "test_vartalap.db"
    with patch("vartalap.logger.DB_PATH", db_file):
        init_db(db_file)
        log_action(
            thread_username="testuser",
            action="reply",
            details="Sent hello",
            dry_run=True,
            success=True
        )
        logs = get_recent_logs(limit=10, username="testuser")
        assert len(logs) == 1
        assert logs[0]["thread_username"] == "testuser"
        assert logs[0]["action"] == "reply"
        assert logs[0]["dry_run"] == 1


@pytest.mark.asyncio
async def test_executor_dry_run():
    mock_page = AsyncMock()
    mock_composer = AsyncMock()
    mock_page.query_selector.return_value = mock_composer
    mock_page.wait_for_selector.return_value = True

    action_data = {"action": "reply", "text": "Casual reply test"}
    result = await execute_action(
        page=mock_page,
        action_data=action_data,
        target_username="elonmusk",
        dry_run=True
    )
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["text"] == "Casual reply test"
    # Ensure send button was NOT clicked in dry run
    assert mock_page.click.call_count == 0


def test_fastapi_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_fast_api_client(tmp_path):
    storage_file = tmp_path / "storage_state.json"
    dummy_data = {
        "cookies": [
            {"name": "reddit_session", "value": "test_token_123"}
        ]
    }
    storage_file.write_text(json.dumps(dummy_data))

    from vartalap.fast_api import FastRedditAPI
    api = FastRedditAPI(storage_state_path=str(storage_file))
    assert api.cookies["reddit_session"] == "test_token_123"

    # Test reply dry run in sub-second API mode
    reply_res = await api.send_reply(thing_id="t4_test", text="Fast API reply test", dry_run=True)
    assert reply_res["success"] is True
    assert reply_res["dry_run"] is True


def test_tui_css_compilation():
    from vartalap.tui import VartalapTUI
    app_inst = VartalapTUI()
    assert app_inst.CSS is not None
    assert "text-style: bold;" in app_inst.CSS

