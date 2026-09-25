import sys
import argparse
import asyncio
from vartalap.settings import get_settings
from vartalap.agent_loop import run_agent
from vartalap.split_launcher import launch_split_session


def main():
    parser = argparse.ArgumentParser(description="Vartalap Interactive Terminal Agent CLI & Split Launcher")
    parser.add_argument("--user", "-u", type=str, default=None, help="Target Reddit username (if omitted, launches split TUI dashboard)")
    parser.add_argument("--instruction", "-i", type=str, default="Reply matching tone, keep casual", help="High-level instruction for the agent")
    parser.add_argument("--mode", "-m", type=str, choices=["fast_browser", "direct_api", "terminal_browser", "browser"], default=None, help="Execution speed mode")
    parser.add_argument("--split", action="store_true", help="Launch TUI + terminal-browser split panel session")
    parser.add_argument("--headed", action="store_true", help="Launch visible browser window on right side of screen")
    parser.add_argument("--live", action="store_true", help="Perform real sends (dry_run=False)")

    args = parser.parse_args()

    # If no user specified or --split flag passed, launch TUI + terminal-browser split session
    if args.user is None or args.split:
        launch_split_session()
        return

    settings = get_settings()
    exec_mode = args.mode or settings.agent.mode
    
    # Override settings for CLI run if flags provided
    if args.headed:
        settings.reddit.headless = False
    
    dry_run = not args.live

    print("=" * 65)
    print(" 🤖 VARTALAP LIVE INTERACTIVE TERMINAL RUNNER")
    print("=" * 65)
    print(f" Target User  : u/{args.user}")
    print(f" Instruction  : {args.instruction}")
    print(f" Exec Mode    : {exec_mode}")
    print(f" LLM Backend  : {settings.llm.backend}")
    print(f" Browser Mode : {'Headed (Visible)' if not settings.reddit.headless else 'Headless'}")
    print(f" Execution    : {'[DRY RUN] (Simulated)' if dry_run else '⚡ REAL SEND'}")
    print("=" * 65)
    print("\nStarting live agent loop...\n")

    result = asyncio.run(
        run_agent(
            username=args.user,
            instruction=args.instruction,
            dry_run=dry_run,
            mode=exec_mode
        )
    )

    print("\n" + "=" * 65)
    print(" 🏁 RUN COMPLETED")
    print("=" * 65)
    print(f" Status         : {result.get('status')}")
    print(f" Final Action   : {result.get('final_action')}")
    print(f" Steps Executed : {result.get('steps_executed')}")
    print(f" Reasoning      : {result.get('reasoning')}")
    print("=" * 65)


if __name__ == "__main__":
    main()
