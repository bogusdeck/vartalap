import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

from vartalap.settings import get_settings
from vartalap.logger import log_action


def load_cookies_from_storage(storage_state_path: str) -> Dict[str, str]:
    """Extract cookie key-value pairs from Playwright storage_state.json."""
    path = Path(storage_state_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Storage state file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cookies = {}
    for c in data.get("cookies", []):
        cookies[c["name"]] = c["value"]

    return cookies


class FastRedditAPI:
    """Direct HTTP REST API Client for sub-second Reddit DM operations bypassing browser rendering."""

    def __init__(self, storage_state_path: Optional[str] = None):
        settings = get_settings()
        state_path = storage_state_path or settings.reddit.storage_state_path
        self.cookies = load_cookies_from_storage(state_path)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        self.base_url = "https://www.reddit.com"

    async def get_unread_messages(self) -> List[Dict[str, Any]]:
        """Fetch unread messages directly via Reddit JSON endpoint in <100ms."""
        url = f"{self.base_url}/message/unread.json"
        print(f"[FAST-API] Direct HTTP GET {url}")

        async with httpx.AsyncClient(cookies=self.cookies, headers=self.headers, timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        messages = []
        children = data.get("data", {}).get("children", [])
        for child in children:
            item = child.get("data", {})
            messages.append({
                "id": item.get("name"),  # e.g. t4_12345
                "username": item.get("author"),
                "subject": item.get("subject"),
                "body": item.get("body"),
                "unread": item.get("new", True),
                "timestamp": item.get("created_utc")
            })

        print(f"[FAST-API] Fetched {len(messages)} unread messages in ultra-fast mode.")
        return messages

    async def send_reply(self, thing_id: str, text: str, dry_run: bool = True) -> Dict[str, Any]:
        """Send a message reply directly via Reddit HTTP POST API in <150ms."""
        if dry_run:
            print(f"[FAST-API] [DRY RUN] Direct HTTP POST reply to '{thing_id}': '{text}'")
            log_action(
                thread_username=thing_id,
                action="reply_fast_api",
                details=f"[DRY RUN] Text: {text}",
                dry_run=True,
                success=True
            )
            return {"success": True, "dry_run": True, "text": text}

        url = f"{self.base_url}/api/comment"
        payload = {
            "thing_id": thing_id,
            "text": text,
            "api_type": "json"
        }

        print(f"[FAST-API] Sending direct HTTP POST reply to {thing_id}...")
        async with httpx.AsyncClient(cookies=self.cookies, headers=self.headers, timeout=10.0) as client:
            resp = await client.post(url, data=payload)
            resp.raise_for_status()
            res_data = resp.json()

        log_action(
            thread_username=thing_id,
            action="reply_fast_api",
            details=f"Sent text: {text}",
            dry_run=False,
            success=True
        )
        return {"success": True, "dry_run": False, "data": res_data}
