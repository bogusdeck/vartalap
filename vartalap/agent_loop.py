import asyncio
from typing import Dict, Any, Optional, List

from vartalap.settings import get_settings
from vartalap.session import get_page
from vartalap.perception import get_thread_messages
from vartalap.planner import Planner
from vartalap.executor import execute_action
from vartalap.fast_api import FastRedditAPI
from vartalap.logger import get_messages_sent_today_count, log_action


async def run_agent(
    username: str,
    instruction: str,
    dry_run: Optional[bool] = None,
    mode: Optional[str] = None
) -> Dict[str, Any]:
    """Runs the perceive -> plan -> execute -> re-perceive loop for a target username.
    
    Supports modes:
      - 'fast_browser': Playwright with resource blocking (3x speed boost)
      - 'browser': Playwright standard mode
      - 'direct_api': Direct HTTP REST API (<300ms sub-second speed)
    """
    settings = get_settings()
    max_steps = settings.agent.max_steps_per_conversation
    max_daily_messages = settings.agent.max_messages_per_day
    exec_mode = mode or settings.agent.mode

    # Determine effective dry_run
    is_dry_run = settings.agent.dry_run if dry_run is None else dry_run

    # Check daily message safety limit
    sent_today = get_messages_sent_today_count()
    if not is_dry_run and sent_today >= max_daily_messages:
        print(f"[SAFETY] Daily message cap reached ({sent_today}/{max_daily_messages}). Forcing dry_run=True.")
        is_dry_run = True
        log_action(
            thread_username=username,
            action="safety_limit",
            details=f"Daily message limit reached ({sent_today}/{max_daily_messages}). Forcing dry run.",
            dry_run=True,
            success=True
        )

    planner = Planner()
    history_log: List[Dict[str, Any]] = []

    print(f"[AGENT] Starting conversation run for u/{username} (mode={exec_mode}, max_steps={max_steps}, dry_run={is_dry_run})")

    # --- TERMINAL BROWSER MODE (zenbu-labs/terminal-browser) ---
    if exec_mode == "terminal_browser":
        try:
            from vartalap.terminal_browser import run_terminal_browser_agent
            if "chat.reddit.com" in settings.reddit.inbox_url:
                target_url = f"https://chat.reddit.com/user/{username}"
            else:
                target_url = f"{settings.reddit.inbox_url.rstrip('/')}/messages/{username}"
            tb_result = await run_terminal_browser_agent(url=target_url)
            return {
                "username": username,
                "status": "completed" if tb_result.get("success") else "failed",
                "mode": "terminal_browser",
                "final_action": "open_terminal_browser",
                "dry_run": is_dry_run,
                "execution_result": tb_result
            }
        except Exception as e:
            err_msg = f"Terminal browser mode failed: {e}"
            print(f"[AGENT] {err_msg}")
            return {"username": username, "status": "error", "error": err_msg}

    # --- DIRECT HTTP REST API MODE (<300ms) ---
    if exec_mode == "direct_api":
        try:
            api_client = FastRedditAPI()
            unread_messages = await api_client.get_unread_messages()
            target_msgs = [m for m in unread_messages if (m.get("username") or "").lower() == username.lower()]

            if not target_msgs:
                message_history = [{"sender": username, "text": f"Unread message check for {username}"}]
            else:
                message_history = [{"sender": m["username"], "text": m["body"]} for m in target_msgs]

            action_decision = await planner.decide_next_action(
                instruction=instruction,
                target_username=username,
                message_history=message_history
            )

            action_type = action_decision.get("action")
            reasoning = action_decision.get("reason", "")
            
            if action_type == "reply":
                thing_id = target_msgs[0]["id"] if target_msgs else f"t4_{username}"
                reply_text = action_decision.get("text", "")
                exec_result = await api_client.send_reply(thing_id=thing_id, text=reply_text, dry_run=is_dry_run)
            else:
                exec_result = {"success": True, "action": action_type, "details": reasoning}

            return {
                "username": username,
                "status": "completed",
                "mode": "direct_api",
                "final_action": action_type,
                "reasoning": reasoning,
                "dry_run": is_dry_run,
                "execution_result": exec_result
            }
        except Exception as e:
            err_msg = f"Direct API mode execution failed: {e}"
            print(f"[AGENT] {err_msg}")
            return {"username": username, "status": "error", "error": err_msg}

    # --- PLAYWRIGHT BROWSER MODES (fast_browser / browser) ---
    use_fast_mode = (exec_mode == "fast_browser")

    async with get_page(fast_mode=use_fast_mode) as page:
        for step in range(1, max_steps + 1):
            print(f"\n[AGENT] --- STEP {step}/{max_steps} ({exec_mode}) ---")

            # 1. PERCEIVE
            try:
                message_history = await get_thread_messages(page, username)
            except Exception as e:
                print(f"[AGENT] Perception failed on step {step}: {e}")
                message_history = []

            # 2. PLAN
            try:
                action_decision = await planner.decide_next_action(
                    instruction=instruction,
                    target_username=username,
                    message_history=message_history
                )
            except Exception as e:
                err_msg = f"Planning failed on step {step}: {e}"
                print(f"[AGENT] {err_msg}")
                return {
                    "username": username,
                    "status": "error",
                    "error": err_msg,
                    "steps_executed": step - 1,
                    "history": history_log
                }

            action_type = action_decision.get("action")
            reasoning = action_decision.get("reason", "")
            print(f"[AGENT] LLM Action Decision: {action_decision}")

            history_log.append({
                "step": step,
                "perceived_messages_count": len(message_history),
                "planned_action": action_decision
            })

            # 3. EXECUTE
            exec_result = await execute_action(
                page=page,
                action_data=action_decision,
                target_username=username,
                dry_run=is_dry_run
            )

            history_log[-1]["execution_result"] = exec_result

            # 4. EVALUATE TERMINATION
            if action_type in ("done", "skip") or not exec_result.get("success", False):
                print(f"[AGENT] Conversation run ending at step {step} on action '{action_type}'.")
                return {
                    "username": username,
                    "status": "completed" if exec_result.get("success") else "failed",
                    "mode": exec_mode,
                    "final_action": action_type,
                    "reasoning": reasoning,
                    "dry_run": is_dry_run,
                    "steps_executed": step,
                    "history": history_log
                }

        # Capped at max_steps hard stop
        print(f"[AGENT] Hard stop reached max_steps ({max_steps}) for u/{username}.")
        log_action(
            thread_username=username,
            action="max_steps_stop",
            details=f"Reached hard limit of {max_steps} steps.",
            dry_run=is_dry_run,
            success=True
        )
        return {
            "username": username,
            "status": "max_steps_reached",
            "mode": exec_mode,
            "dry_run": is_dry_run,
            "steps_executed": max_steps,
            "history": history_log
        }
