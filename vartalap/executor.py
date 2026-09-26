import random
import asyncio
from typing import Dict, Any
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from vartalap.logger import log_action
from vartalap.settings import get_settings


# Selectors for Reddit Chat & Messages
THREAD_ITEM_TEMPLATE = "a[href*='{username}'], div:has-text('{username}'), [data-testid='chat-channel-item']:has-text('{username}')"
COMPOSER_SELECTOR = "[data-testid='chat-composer-textarea'], textarea[name='body'], textarea.reply-textarea, [contenteditable='true'], [data-testid='message-composer'], textarea"
SEND_BUTTON_SELECTOR = "[data-testid='chat-send-button'], button[type='submit']:has-text('send'), button.reply-button, button:has-text('Send'), [data-testid='send-button']"


async def random_human_delay(min_ms: int = 300, max_ms: int = 1200):
    """Sleep for a randomized duration between min_ms and max_ms to simulate human behavior."""
    delay = random.uniform(min_ms / 1000.0, max_ms / 1000.0)
    await asyncio.sleep(delay)


async def execute_action(
    page: Page,
    action_data: Dict[str, Any],
    target_username: str,
    dry_run: bool = True
) -> Dict[str, Any]:
    """Execute a single planner action on the Playwright page.
    
    Args:
        page: Playwright Page instance
        action_data: JSON object from planner (e.g. {"action": "reply", "text": "..."})
        target_username: Target Reddit username
        dry_run: If True, do not submit real messages
    """
    action_type = action_data.get("action")
    settings = get_settings()

    print(f"[EXECUTOR] Executing action '{action_type}' for user '{target_username}' (dry_run={dry_run})")
    await random_human_delay()

    if action_type == "open_thread":
        username = action_data.get("username", target_username)
        selector = THREAD_ITEM_TEMPLATE.format(username=username)
        try:
            thread_elem = await page.query_selector(selector)
            if thread_elem:
                await thread_elem.click()
                await random_human_delay()
            else:
                # Direct navigation fallback
                if "chat.reddit.com" in settings.reddit.inbox_url:
                    thread_url = f"https://chat.reddit.com/user/{username}"
                else:
                    thread_url = f"{settings.reddit.inbox_url.rstrip('/')}/messages/{username}"
                await page.goto(thread_url, wait_until="domcontentloaded")
            
            log_action(
                thread_username=username,
                action="open_thread",
                details=f"Opened thread for {username}",
                dry_run=dry_run,
                success=True
            )
            return {"success": True, "action": "open_thread", "username": username}
        except Exception as e:
            err_msg = f"Failed to open thread for {username}: {str(e)}"
            log_action(thread_username=username, action="open_thread", details=err_msg, dry_run=dry_run, success=False)
            return {"success": False, "error": err_msg}

    elif action_type == "reply":
        reply_text = action_data.get("text", "")
        if not reply_text:
            return {"success": False, "error": "Reply action missing 'text' field."}

        try:
            # Locate reply composer
            # TODO: Update COMPOSER_SELECTOR based on live Reddit DOM
            await page.wait_for_selector(COMPOSER_SELECTOR, timeout=5000)
            composer = await page.query_selector(COMPOSER_SELECTOR)
            if not composer:
                raise RuntimeError("Reply composer element not found in DOM.")

            # Focus and fill text
            await composer.focus()
            await random_human_delay(200, 500)
            await composer.fill(reply_text)
            await random_human_delay(400, 900)

            if dry_run:
                log_msg = f"[DRY RUN] Would send reply to u/{target_username}: '{reply_text}'"
                print(f"[EXECUTOR] {log_msg}")
                log_action(
                    thread_username=target_username,
                    action="reply",
                    details=f"[DRY RUN] Reply text: {reply_text}",
                    dry_run=True,
                    success=True
                )
                return {"success": True, "action": "reply", "dry_run": True, "text": reply_text}

            # REAL SEND - Click send button
            # TODO: Update SEND_BUTTON_SELECTOR based on live Reddit DOM
            await random_human_delay(300, 800)
            send_btn = await page.query_selector(SEND_BUTTON_SELECTOR)
            if send_btn:
                await send_btn.click()
            else:
                # Fallback: press Enter or Ctrl+Enter in composer
                await composer.press("Enter")

            await random_human_delay(500, 1000)

            log_action(
                thread_username=target_username,
                action="reply",
                details=f"Sent reply: {reply_text}",
                dry_run=False,
                success=True
            )
            print(f"[EXECUTOR] Successfully sent reply to u/{target_username}")
            return {"success": True, "action": "reply", "dry_run": False, "text": reply_text}

        except Exception as e:
            err_msg = f"Failed to send reply to u/{target_username}: {str(e)}"
            log_action(
                thread_username=target_username,
                action="reply",
                details=err_msg,
                dry_run=dry_run,
                success=False
            )
            return {"success": False, "error": err_msg}

    elif action_type == "done":
        reason = action_data.get("reason", "Task finished.")
        log_action(
            thread_username=target_username,
            action="done",
            details=f"Conversation marked done: {reason}",
            dry_run=dry_run,
            success=True
        )
        return {"success": True, "action": "done", "reason": reason}

    elif action_type == "skip":
        reason = action_data.get("reason", "No action needed.")
        log_action(
            thread_username=target_username,
            action="skip",
            details=f"Skipped thread: {reason}",
            dry_run=dry_run,
            success=True
        )
        return {"success": True, "action": "skip", "reason": reason}

    else:
        err_msg = f"Unknown action type: '{action_type}'"
        log_action(thread_username=target_username, action="error", details=err_msg, dry_run=dry_run, success=False)
        return {"success": False, "error": err_msg}
