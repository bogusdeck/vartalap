import os
import shutil
import sys
import subprocess


def launch_split_session(target_url: str = "https://www.reddit.com/message/messages"):
    """Launches side-by-side split panels with TUI on left and terminal-browser on right."""
    
    tb_bin = shutil.which("terminal-browser")
    tb_cmd = f"{tb_bin} {target_url}" if tb_bin else f"npx @zenbu-labs/terminal-browser {target_url}"

    # Check active terminal multiplexer environment
    in_tmux = "TMUX" in os.environ
    in_kitty = "KITTY_WINDOW_ID" in os.environ
    in_wezterm = "WEZTERM_PANE" in os.environ

    print("=" * 65)
    print(" 🚀 VARTALAP SPLIT TERMINAL LAUNCHER")
    print("=" * 65)
    print(f" Environment : TMUX={in_tmux} | Kitty={in_kitty} | WezTerm={in_wezterm}")
    print(f" Target URL   : {target_url}")
    print(f" Browser Cmd  : {tb_cmd}")
    print("=" * 65)

    if in_tmux:
        print("[SPLIT-LAUNCHER] Splitting Tmux window...")
        subprocess.run(["tmux", "split-window", "-h", tb_cmd])
        os.execvp(sys.executable, [sys.executable, "-m", "vartalap.tui"])

    elif in_kitty:
        print("[SPLIT-LAUNCHER] Launching Kitty split pane...")
        subprocess.run(["kitty", "@", "launch", "--location=vsplit", "sh", "-c", tb_cmd])
        os.execvp(sys.executable, [sys.executable, "-m", "vartalap.tui"])

    elif in_wezterm:
        print("[SPLIT-LAUNCHER] Splitting WezTerm pane...")
        subprocess.run(["wezterm", "cli", "split-pane", "--horizontal", "--", "sh", "-c", tb_cmd])
        os.execvp(sys.executable, [sys.executable, "-m", "vartalap.tui"])

    else:
        print("[SPLIT-LAUNCHER] No multiplexer detected. Spawning background browser session...")
        try:
            subprocess.Popen([sys.executable, "-c", f"import os; os.system('{tb_cmd}')"])
        except Exception as e:
            print(f"[SPLIT-LAUNCHER] Could not spawn background terminal-browser: {e}")

        # Launch TUI dashboard
        os.execvp(sys.executable, [sys.executable, "-m", "vartalap.tui"])


if __name__ == "__main__":
    launch_split_session()
