import os
import time
from pathlib import Path
from typing import List, Dict, Any
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from vartalap.settings import get_settings


# Selectors for Reddit Chat & Messages
INBOX_THREAD_SELECTOR = "div[data-testid='chat-channel-item'], a[href*='/chat/'], div.thing.message, div.message-container, div[data-testid='inbox-thread']"
UNREAD_BADGE_SELECTOR = "[data-testid='unread-badge'], .unread, span.unread"
THREAD_USER_SELECTOR = "[data-testid='chat-channel-name'], a.author, [data-testid='thread-user'], .sender"
THREAD_SNIPPET_SELECTOR = "[data-testid='chat-snippet'], div.entry div.md, [data-testid='thread-snippet']"

# Thread Message Detail Selectors
MESSAGE_ITEM_SELECTOR = "div[data-testid='chat-message'], [role='listitem'], div.thing.message, div[data-testid='message-bubble'], div.message-item"
MESSAGE_SENDER_SELECTOR = "[data-testid='message-sender'], a.author, span.sender"
MESSAGE_BODY_SELECTOR = "[data-testid='message-body'], p.message-text, div.md"
MESSAGE_TIME_SELECTOR = "[data-testid='message-time'], time, span.timestamp"


async def list_conversation_threads(page: Page) -> List[Dict[str, Any]]:
    """Opens DM inbox and lists conversation threads.
    
    Returns:
        [{"username": "elonmusk", "unread": True, "snippet": "Hey there..."}]
    """
    settings = get_settings()
    inbox_url = settings.reddit.inbox_url

    print(f"[PERCEPTION] Navigating to DM inbox: {inbox_url}")
    await page.goto(inbox_url, wait_until="domcontentloaded")
    
    threads: List[Dict[str, Any]] = []

    try:
        # Wait briefly for thread elements to render
        await page.wait_for_selector(INBOX_THREAD_SELECTOR, timeout=5000)
    except PlaywrightTimeoutError:
        print("[PERCEPTION] Standard thread selector not found immediately. Attempting general DOM inspection...")

    # DOM Extraction from thread elements
    thread_elements = await page.query_selector_all(INBOX_THREAD_SELECTOR)
    
    if not thread_elements:
        # Fallback: check alternative links or accessibility tree elements
        print("[PERCEPTION] No threads matched standard selectors. Searching for user links in message container...")
        alt_elements = await page.query_selector_all("div.message, div.thing")
        thread_elements = alt_elements

    for el in thread_elements:
        try:
            # Extract Username
            user_el = await el.query_selector(THREAD_USER_SELECTOR)
            username = (await user_el.inner_text()).strip() if user_el else "unknown"
            username = username.lstrip("u/").lstrip("/u/")

            # Extract Unread Flag
            unread_el = await el.query_selector(UNREAD_BADGE_SELECTOR)
            is_unread = bool(unread_el) or ("unread" in ((await el.get_attribute("class")) or ""))

            # Extract Snippet
            snippet_el = await el.query_selector(THREAD_SNIPPET_SELECTOR)
            snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""

            if username != "unknown":
                threads.append({
                    "username": username,
                    "unread": is_unread,
                    "snippet": snippet[:100]
                })
        except Exception as e:
            print(f"[PERCEPTION] Error parsing individual thread element: {e}")
            continue

    print(f"[PERCEPTION] Extracted {len(threads)} conversation threads.")
    return threads


async def get_thread_messages(page: Page, username: str) -> List[Dict[str, Any]]:
    """Opens a specific user's thread and extracts message history.
    
    Returns:
        [{"sender": "elonmusk", "text": "Hello", "timestamp": "2026-09-25T01:00:00"}]
    """
    settings = get_settings()

    # Direct Reddit Chat URL or Legacy Message URL
    if "chat.reddit.com" in settings.reddit.inbox_url:
        thread_url = f"https://chat.reddit.com/user/{username}"
    else:
        thread_url = f"{settings.reddit.inbox_url.rstrip('/')}/messages/{username}"

    print(f"[PERCEPTION] Opening thread for user '{username}' via URL: {thread_url}")

    try:
        await page.goto(thread_url, wait_until="domcontentloaded")
    except Exception as e:
        print(f"[PERCEPTION] Navigation error: {e}")

    messages: List[Dict[str, Any]] = []

    try:
        await page.wait_for_selector(MESSAGE_ITEM_SELECTOR, timeout=5000)
    except PlaywrightTimeoutError:
        print(f"[PERCEPTION] Message selector '{MESSAGE_ITEM_SELECTOR}' timed out.")

    # Extract messages from DOM
    msg_elements = await page.query_selector_all(MESSAGE_ITEM_SELECTOR)

    for el in msg_elements:
        try:
            # Extract Sender
            sender_el = await el.query_selector(MESSAGE_SENDER_SELECTOR)
            sender = (await sender_el.inner_text()).strip() if sender_el else "unknown"
            sender = sender.lstrip("u/").lstrip("/u/")

            # Extract Text
            body_el = await el.query_selector(MESSAGE_BODY_SELECTOR)
            text = (await body_el.inner_text()).strip() if body_el else ""

            # Extract Timestamp
            time_el = await el.query_selector(MESSAGE_TIME_SELECTOR)
            timestamp = ""
            if time_el:
                timestamp = (await time_el.get_attribute("datetime")) or (await time_el.inner_text()).strip()

            if text:
                messages.append({
                    "sender": sender,
                    "text": text,
                    "timestamp": timestamp
                })
        except Exception as e:
            print(f"[PERCEPTION] Error parsing message element: {e}")
            continue

    # Fallback to Screenshot if DOM extraction yields zero messages
    if not messages:
        print(f"[PERCEPTION] DOM extraction yielded 0 messages for '{username}'. Triggering screenshot fallback...")
        screenshot_dir = Path(__file__).parent.parent / "logs" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"fallback_{username}_{int(time.time())}.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"[PERCEPTION] Saved fallback screenshot to: {screenshot_path}")

    print(f"[PERCEPTION] Extracted {len(messages)} messages from thread '{username}'.")
    return messages
