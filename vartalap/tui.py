import io
import json
import asyncio
import contextlib
from typing import Optional, List, Dict, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Static, RichLog, Label, Switch,
    DataTable, Select, TabbedContent, TabPane, TextArea
)
from textual.binding import Binding

from vartalap.settings import get_settings, reload_settings
from vartalap.agent_loop import run_agent
from vartalap.logger import get_recent_logs, get_recent_llm_logs, get_messages_sent_today_count


class TUIStream(io.TextIOBase):
    """Redirects standard print output live into Textual RichLog widget."""

    def __init__(self, log_widget: RichLog):
        self.log_widget = log_widget
        self.buffer = ""

    def write(self, s: str) -> int:
        self.buffer += s
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line_clean = line.strip()
            if line_clean:
                self.log_widget.write(line_clean)
        return len(s)

    def flush(self):
        if self.buffer.strip():
            self.log_widget.write(self.buffer.strip())
            self.buffer = ""


class VartalapTUI(App):
    """Clean 2-Section Textual TUI (Agent Setup on Left | Execution Response on Right)."""

    TITLE = "Vartalap"
    SUB_TITLE = "0.1.0"

    CSS = """
    Screen {
        background: #0b0f19;
        color: #e2e8f0;
    }

    /* Top Brand Bar */
    #top-bar {
        height: 3;
        margin: 1 1 0 1;
    }

    #brand-title {
        color: #10b981;
        text-style: bold;
        width: auto;
        content-align: left middle;
    }

    #top-status {
        width: 1fr;
        content-align: right middle;
        color: #94a3b8;
    }

    /* Main Workspace Split - 2 Sections */
    #main-split {
        height: 1fr;
        margin: 0 1;
    }

    /* SECTION 1: AGENT SETUP (Left Side) */
    #setup-box {
        width: 48;
        border: round #8b5cf6;
        background: #111726;
        margin-right: 1;
        padding: 0 1;
    }

    .section-header {
        color: #c084fc;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }

    .field-label {
        color: #94a3b8;
        text-style: bold;
        margin-top: 1;
    }

    Input {
        background: #171e2e;
        color: #38bdf8;
        border: none;
        height: 3;
        margin-bottom: 1;
    }

    TextArea {
        height: 6;
        background: #171e2e;
        color: #38bdf8;
        border: none;
        margin-bottom: 1;
    }

    Select {
        background: #171e2e;
        color: #38bdf8;
        margin-bottom: 1;
    }

    .switch-row {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    #btn-send {
        background: #8b5cf6;
        color: #ffffff;
        text-style: bold;
        border: none;
        width: 100%;
        height: 3;
        margin-top: 1;
    }

    #btn-send:hover {
        background: #a855f7;
    }

    /* SECTION 2: EXECUTION RESPONSE (Right Side) */
    #response-box {
        width: 1fr;
        height: 100%;
        border: round #8b5cf6;
        background: #111726;
        padding: 0 1;
    }

    TabbedContent {
        height: 100%;
    }

    TabPane {
        padding: 0;
    }

    RichLog {
        height: 100%;
        background: #0b0f19;
        color: #38bdf8;
        border: none;
        padding: 1;
    }

    DataTable {
        height: 100%;
        background: #0b0f19;
        border: none;
    }

    .status-pill {
        background: #0d9488;
        color: #ffffff;
        text-style: bold;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+j", "trigger_send", "Send", show=True),
        Binding("ctrl+m", "cycle_mode", "Exec Mode", show=True),
        Binding("ctrl+d", "toggle_dry_run", "DryRun", show=True),
        Binding("ctrl+l", "refresh_logs", "Logs", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    PLATFORM_OPTIONS = [
        ("Reddit (Supported)", "reddit"),
        ("Telegram (Upcoming)", "telegram"),
        ("WhatsApp (Upcoming)", "whatsapp"),
        ("Twitter / X (Upcoming)", "twitter"),
        ("Slack (Upcoming)", "slack"),
        ("Discord (Upcoming)", "discord"),
    ]

    MODE_OPTIONS = [
        ("Fast Browser (Resource Blocked)", "fast_browser"),
        ("Direct HTTP API (<300ms)", "direct_api"),
        ("Terminal Browser (In-Terminal)", "terminal_browser"),
        ("Full Visual Browser", "browser"),
    ]

    def compose(self) -> ComposeResult:
        # Top Bar
        with Horizontal(id="top-bar"):
            yield Label("🤖 Vartalap Agent [dim]v0.1.0[/dim]", id="brand-title")
            yield Label("System: [bold green]ONLINE[/bold green] | Active Backend: [cyan]cli[/cyan]", id="top-status")

        # Main 2-Section Workspace Split
        with Horizontal(id="main-split"):
            # SECTION 1: AGENT SETUP (Left Side)
            with Vertical(id="setup-box"):
                yield Label("⚙️ AGENT SETUP", classes="section-header")

                yield Label("Target Username:", classes="field-label")
                yield Input(placeholder="e.g. elonmusk", id="target-input", value="elonmusk")

                yield Label("Platform:", classes="field-label")
                yield Select(
                    options=self.PLATFORM_OPTIONS,
                    value="reddit",
                    allow_blank=False,
                    id="sel-platform"
                )

                yield Label("Instruction Prompt (Wrapped Text):", classes="field-label")
                yield TextArea(
                    "Reply matching tone, keep casual",
                    soft_wrap=True,
                    id="in-instruction"
                )

                yield Label("Exec Mode:", classes="field-label")
                yield Select(
                    options=self.MODE_OPTIONS,
                    value="fast_browser",
                    allow_blank=False,
                    id="sel-mode"
                )

                with Horizontal(classes="switch-row"):
                    yield Label("Dry Run (Simulated Send):")
                    yield Switch(value=True, id="sw-dryrun")

                yield Button("🚀 EXECUTE AGENT (Ctrl+J)", id="btn-send")

            # SECTION 2: EXECUTION RESPONSE (Right Side)
            with Vertical(id="response-box"):
                with Horizontal():
                    yield Label("📊 EXECUTION RESPONSE", classes="section-header")
                    yield Label("200 OK", classes="status-pill", id="pill-status")

                with TabbedContent(initial="tab-log"):
                    with TabPane("Console Stream", id="tab-log"):
                        yield RichLog(id="rich-log", wrap=True, highlight=True, markup=True)

                    with TabPane("Audit Database", id="tab-audit"):
                        yield DataTable(id="dt-audit")

                    with TabPane("Raw Response JSON", id="tab-json"):
                        yield RichLog(id="json-log", wrap=True, highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#dt-audit", DataTable)
        table.add_columns("Timestamp", "User", "Action", "DryRun", "Details")

        log = self.query_one("#rich-log", RichLog)
        log.write("[bold green]✓ Vartalap Autonomous Engine Ready.[/bold green]")
        log.write("[dim]Setup agent parameters on the left and click Execute or press Ctrl+J.[/dim]\n")
        self.load_audit_logs()

    def action_trigger_send(self) -> None:
        self.run_agent_execution()

    def action_cycle_mode(self) -> None:
        select = self.query_one("#sel-mode", Select)
        modes = ["fast_browser", "direct_api", "terminal_browser", "browser"]
        curr_idx = modes.index(select.value) if select.value in modes else 0
        next_mode = modes[(curr_idx + 1) % len(modes)]
        select.value = next_mode
        self.notify(f"Exec Mode set to {next_mode}", title="Mode Updated")

    def action_toggle_dry_run(self) -> None:
        sw = self.query_one("#sw-dryrun", Switch)
        sw.value = not sw.value
        state = "ENABLED (Simulated)" if sw.value else "DISABLED (REAL SEND)"
        self.notify(f"Dry Run {state}", title="Safety Toggle")

    def action_refresh_logs(self) -> None:
        self.load_audit_logs()
        self.notify("Audit logs reloaded", title="Logs Refreshed")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-send":
            self.run_agent_execution()

    def run_agent_execution(self) -> None:
        username = self.query_one("#target-input", Input).value.strip().lstrip("u/").lstrip("/u/")
        platform = str(self.query_one("#sel-platform", Select).value)
        instruction = self.query_one("#in-instruction", TextArea).text.strip()
        mode = str(self.query_one("#sel-mode", Select).value)
        dry_run = self.query_one("#sw-dryrun", Switch).value

        log = self.query_one("#rich-log", RichLog)

        if not username:
            self.notify("Target username cannot be empty!", title="Validation Error", severity="error")
            return

        if platform != "reddit":
            self.notify(f"{platform.capitalize()} integration coming soon! Defaulting to Reddit.", title="Platform Note")

        log.write(f"\n[bold magenta]POST /run ({platform.upper()}) -> u/{username}[/bold magenta]")
        log.write(f"[dim]Executing run (mode={mode}, dry_run={dry_run})...[/dim]")

        self.notify(f"Executing agent for u/{username}...", title="Execution Started")
        self.run_worker(self._async_agent_run(username, instruction, dry_run, mode))

    async def _async_agent_run(self, username: str, instruction: str, dry_run: bool, mode: str) -> None:
        log = self.query_one("#rich-log", RichLog)
        json_log = self.query_one("#json-log", RichLog)
        pill = self.query_one("#pill-status", Label)

        def log_to_tui(msg: str):
            formatted_msg = (
                msg.replace("[AGENT]", "[bold green][AGENT][/bold green]")
                   .replace("[PERCEPTION]", "[bold cyan][PERCEPTION][/bold cyan]")
                   .replace("[EXECUTOR]", "[bold magenta][EXECUTOR][/bold magenta]")
                   .replace("[LLM]", "[bold yellow][LLM][/bold yellow]")
                   .replace("[FAST-API]", "[bold teal][FAST-API][/bold teal]")
                   .replace("[SAFETY]", "[bold red][SAFETY][/bold red]")
            )
            log.write(formatted_msg)

        stream = TUIStream(log)

        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                result = await run_agent(
                    username=username,
                    instruction=instruction,
                    dry_run=dry_run,
                    mode=mode,
                    log_callback=log_to_tui
                )
            status = result.get("status")
            final_action = result.get("final_action", "N/A")

            if status == "completed":
                pill.update("200 OK")
                pill.styles.background = "#0d9488"
                log.write(f"[bold green]200 OK[/bold green] - Final Action: [cyan]{final_action}[/cyan]")
                if result.get("reasoning"):
                    log.write(f"[italic]LLM Reasoning: {result.get('reasoning')}[/italic]")
            else:
                pill.update("400 FAIL")
                pill.styles.background = "#e11d48"
                log.write(f"[bold red]Execution status: {status}[/bold red]")

            json_log.clear()
            json_log.write(json.dumps(result, indent=2))

        except Exception as e:
            pill.update("500 ERR")
            pill.styles.background = "#e11d48"
            log.write(f"[bold red]Exception: {e}[/bold red]")

        self.load_audit_logs()

    def load_audit_logs(self) -> None:
        table = self.query_one("#dt-audit", DataTable)
        table.clear()
        
        # Load Action Logs
        logs = get_recent_logs(limit=30)
        for row in logs:
            ts = row.get("timestamp", "")[:19].replace("T", " ")
            user = row.get("thread_username", "")
            action = row.get("action", "")
            dry_run = "TRUE" if row.get("dry_run") else "FALSE"
            table.add_row(ts, user, action, dry_run, row.get("details", "")[:50])

        # Load LLM Logs
        llm_logs = get_recent_llm_logs(limit=20)
        for row in llm_logs:
            ts = row.get("timestamp", "")[:19].replace("T", " ")
            backend = row.get("backend", "")
            resp_preview = row.get("response", "").replace("\n", " ")[:40]
            table.add_row(ts, "LLM-CALL", backend, "N/A", f"Resp: {resp_preview}")


def main():
    app = VartalapTUI()
    app.run()


if __name__ == "__main__":
    main()
