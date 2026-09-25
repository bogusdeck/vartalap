import asyncio
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from vartalap.settings import reload_settings, get_settings
from vartalap.session import get_page
from vartalap.perception import list_conversation_threads
from vartalap.agent_loop import run_agent
from vartalap.logger import log_action

_scheduler_instance: Optional[AsyncIOScheduler] = None


async def poll_unread_dms_job():
    """APScheduler task triggered periodically to scan unread DMs and run agent loop."""
    print("\n[SCHEDULER] --- Starting periodic polling tick ---")
    # Hot-reload config on every tick so watchlist, dry_run, interval edits take effect
    settings = reload_settings()
    
    interval = settings.scheduler.polling_interval_minutes
    watchlist = [u.lower() for u in settings.agent.watchlist]
    dry_run = settings.agent.dry_run

    print(f"[SCHEDULER] Config loaded: interval={interval}m, watchlist={watchlist}, dry_run={dry_run}")

    try:
        async with get_page() as page:
            threads = await list_conversation_threads(page)

        unread_threads = [t for t in threads if t.get("unread")]
        print(f"[SCHEDULER] Found {len(unread_threads)} unread DM threads out of {len(threads)} total.")

        for thread in unread_threads:
            username = thread.get("username", "").strip()
            if not username:
                continue

            # Watchlist filtering logic
            if watchlist and username.lower() not in watchlist:
                print(f"[SCHEDULER] Skipping u/{username} (not in watchlist: {watchlist})")
                continue

            print(f"[SCHEDULER] Triggering agent run for u/{username}...")
            instruction = f"Handle DM conversation with u/{username}. Match tone and keep response natural."
            
            result = await run_agent(
                username=username,
                instruction=instruction,
                dry_run=dry_run
            )
            print(f"[SCHEDULER] Agent run completed for u/{username}: {result.get('status')}")

    except Exception as e:
        print(f"[SCHEDULER] Error during polling tick: {e}")
        log_action(
            thread_username="system_scheduler",
            action="scheduler_tick_error",
            details=str(e),
            dry_run=dry_run,
            success=False
        )


def start_scheduler() -> AsyncIOScheduler:
    """Start the background APScheduler."""
    global _scheduler_instance
    if _scheduler_instance and _scheduler_instance.running:
        return _scheduler_instance

    settings = get_settings()
    interval_minutes = settings.scheduler.polling_interval_minutes

    _scheduler_instance = AsyncIOScheduler()
    _scheduler_instance.add_job(
        poll_unread_dms_job,
        trigger="interval",
        minutes=interval_minutes,
        id="poll_unread_dms",
        replace_existing=True
    )
    _scheduler_instance.start()
    print(f"[SCHEDULER] APScheduler started. Polling every {interval_minutes} minutes.")
    return _scheduler_instance


def stop_scheduler():
    """Shutdown the background scheduler."""
    global _scheduler_instance
    if _scheduler_instance and _scheduler_instance.running:
        _scheduler_instance.shutdown(wait=False)
        print("[SCHEDULER] APScheduler stopped.")
