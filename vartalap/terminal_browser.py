import os
import shutil
import asyncio
import subprocess
from typing import Dict, Any, Optional


async def run_terminal_browser_agent(
    url: str = "https://chat.reddit.com",
    storage_state_path: str = "./storage_state.json"
) -> Dict[str, Any]:
    """Dynamically splits terminal pane to run terminal-browser on the right side."""
    
    tb_path = shutil.which("terminal-browser")
    if not tb_path:
        # Fallback to npx or default install path
        alt_path = os.path.expanduser("~/.local/bin/terminal-browser")
        if os.path.exists(alt_path):
            tb_path = alt_path
        else:
            tb_path = "npx @zenbu-labs/terminal-browser"

    cmd = f"{tb_path} {url}"
    print(f"[TERMINAL-BROWSER] Spawning terminal browser pane: {cmd}")

    in_tmux = "TMUX" in os.environ
    in_kitty = "KITTY_WINDOW_ID" in os.environ
    in_wezterm = "WEZTERM_PANE" in os.environ

    try:
        if in_kitty:
            print("[TERMINAL-BROWSER] Spawning Kitty right split pane...")
            subprocess.Popen(["kitty", "@", "launch", "--location=vsplit", "sh", "-c", cmd])
        elif in_tmux:
            print("[TERMINAL-BROWSER] Spawning Tmux right split pane...")
            subprocess.Popen(["tmux", "split-window", "-h", cmd])
        elif in_wezterm:
            print("[TERMINAL-BROWSER] Spawning WezTerm right split pane...")
            subprocess.Popen(["wezterm", "cli", "split-pane", "--horizontal", "--", "sh", "-c", cmd])
        else:
            print("[TERMINAL-BROWSER] Spawning background terminal-browser process...")
            subprocess.Popen([sys.executable if 'sys' in globals() else "python3", "-c", f"import os; os.system('{cmd}')"])

        return {
            "success": True,
            "url": url,
            "mode": "split_pane",
            "storage_state": storage_state_path
        }
    except Exception as e:
        print(f"[TERMINAL-BROWSER] Error spawning split pane: {e}")
        return {
            "success": False,
            "error": str(e),
            "url": url
        }
