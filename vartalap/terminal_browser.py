import shutil
import asyncio
from typing import Dict, Any, Optional

async def run_terminal_browser_agent(
    url: str = "https://www.reddit.com/login",
    storage_state_path: str = "./storage_state.json"
) -> Dict[str, Any]:
    """Integration handler for zenbu-labs/terminal-browser.
    
    Launches terminal-browser CLI directly in terminal session for interactive
    web browsing and session state dumping.
    """
    tb_path = shutil.which("terminal-browser")
    
    if not tb_path:
        print("[TERMINAL-BROWSER] 'terminal-browser' binary not found in PATH.")
        print("[TERMINAL-BROWSER] Install via: npm install -g @zenbu-labs/terminal-browser OR brew install zenbu-labs/tap/terminal-browser")
        return {
            "success": False,
            "error": "'terminal-browser' binary not installed on system PATH.",
            "install_instruction": "npm install -g @zenbu-labs/terminal-browser"
        }

    cmd = f"{tb_path} {url}"
    print(f"[TERMINAL-BROWSER] Launching terminal browser session: {cmd}")

    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.communicate()

    return {
        "success": proc.returncode == 0,
        "url": url,
        "storage_state": storage_state_path
    }
