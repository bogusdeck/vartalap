import json
import asyncio
from typing import Optional, List, Dict, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Static, RichLog, Label, Switch,
    DataTable, Select, TabbedContent, TabPane, OptionList
)
from textual.widgets.option_list import Option
from textual.binding import Binding

from vartalap.settings import get_settings, reload_settings
from vartalap.agent_loop import run_agent
from vartalap.logger import get_recent_logs, get_messages_sent_today_count


class VartalapTUI(App):
    """Production Textual TUI with Posting aesthetic for Vartalap Autonomous Reddit DM Agent."""

    TITLE = "Vartalap"
    SUB_TITLE = "0.1.0"

    CSS = """
    Screen {
        background: #0b0f19;
        color: #e2e8f0;
    }

    /* Top Brand & Request Bar */
    #top-bar {
        height: 3;
        margin: 1 1 0 1;
    }

    #brand-title {
        color: #10b981;
        text-style: bold;
        width: 16;
        content-align: left middle;
    }

    #target-input {
        width: 1fr;
        background: #171e2e;
        color: #38bdf8;
        border: none;
        height: 3;
    }

    #btn-send {
        background: #8b5cf6;
        color: #ffffff;
        text-style: bold;
        border: none;
        width: 12;
        height: 3;
        margin-left: 1;
    }

    #btn-send:hover {
        background: #a855f7;
    }

    /* Main Workspace Layout */
    #main-split {
        height: 1fr;
        margin: 0 1;
    }

    /* Sidebar Collection Box */
    #sidebar-box {
        width: 36;
        border: round #8b5cf6;
        background: #111726;
        margin-right: 1;
        padding: 0 1;
    }

    .box-header {
        color: #c084fc;
        text-style: bold;
        padding: 0 1;
    }

    OptionList {
        background: transparent;
        border: none;
        height: 1fr;
    }

    /* Right Side Panels */
    #right-panel {
        width: 1fr;
        height: 100%;
    }

    #request-box {
        height: 13;
        border: round #8b5cf6;
        background: #111726;
        margin-bottom: 1;
        padding: 0 1;
    }

    #response-box {
        height: 1fr;
        border: round #8b5cf6;
        background: #111726;
        padding: 0 1;
    }

    .field-row {
        height: 3;
        margin-bottom: 0;
        align: left middle;
    }

    .field-label {
        width: 14;
        color: #94a3b8;
        text-style: bold;
    }

    .field-input {
        width: 1fr;
        background: #171e2e;
        color: #f1f5f9;
        border: none;
        height: 3;
    }

    Select {
        width: 1fr;
        background: #171e2e;
        border: none;
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
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+j", "trigger_send", "Send", show=True),
        Binding("ctrl+m", "cycle_mode", "Method", show=True),
        Binding("ctrl+d", "toggle_dry_run", "DryRun", show=True),
        Binding("ctrl+l", "refresh_logs", "Logs", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        # Top Bar
        with Horizontal(id="top-bar"):
            yield Label("Vartalap [dim]0.1.0[/dim]", id="brand-title")
            yield Input(placeholder="u/username (e.g. elonmusk)", id="target-input", value="elonmusk")
            yield Button("Send ▶", id="btn-send")

        # Main Workspace Split
        with Horizontal(id="main-split"):
            # Left Sidebar: Watchlist / Target Threads
            with Vertical(id="sidebar-box"):
                yield Label("Target Watchlist", classes="box-header")
                yield OptionList(
                    Option("🟢 u/elonmusk [dim](latest)[/dim]", id="opt-elon"),
                    Option("💬 u/samaltman", id="opt-sam"),
                    Option("💬 u/lexfridman", id="opt-lex"),
                    Option("💬 u/sundarpichai", id="opt-sundar"),
                    id="opt-watchlist"
                )
                yield Label("Status: [bold green]ONLINE[/bold green]", classes="box-header")

            # Right Side Panel: Request Configuration & Response Logs
            with Vertical(id="right-panel"):
                # Top Request / Agent Setup Box
                with Vertical(id="request-box"):
                    yield Label("Agent Setup", classes="box-header")
                    
                    with Horizontal(classes="field-row"):
                        yield Label("Instruction:", classes="field-label")
                        yield Input(placeholder="Prompt for LLM...", id="in-instruction", value="Reply matching tone, keep casual", classes="field-input")

                    with Horizontal(classes="field-row"):
                        yield Label("Exec Mode:", classes="field-label")
                        yield Select(
                            options=[
                                ("⚡ Fast Browser (Resource Blocked)", "fast_browser"),
                                ("🚀 Direct HTTP API (<300ms)", "direct_api"),
                                ("🌐 Full Visual Browser", "browser"),
                            ],
                            value="fast_browser",
                            id="sel-mode"
                        )

                    with Horizontal(classes="field-row"):
                        yield Label("Dry Run:", classes="field-label")
                        yield Switch(value=True, id="sw-dryrun")

                # Bottom Response / Execution Stream Box
                with Vertical(id="response-box"):
                    with Horizontal():
                        yield Label("Execution Response", classes="box-header")
                        yield Label("200 OK", classes="status-pill", id="pill-status")

                    with TabbedContent(initial="tab-log"):
                        with TabPane("Console Output", id="tab-log"):
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
        log.write("[bold green]✓ Vartalap Engine Initialized (Posting Theme)[/bold green]")
        log.write("[dim]Press Ctrl+J or click Send to execute agent run.[/dim]\n")
        self.load_audit_logs()

    def action_trigger_send(self) -> None:
        self.run_agent_execution()

    def action_cycle_mode(self) -> None:
        select = self.query_one("#sel-mode", Select)
        modes = ["fast_browser", "direct_api", "browser"]
        curr_idx = modes.index(select.value) if select.value in modes else 0
        next_mode = modes[(curr_idx + 1) % len(modes)]
        select.value = next_mode
        self.notify(f"Method set to {next_mode}", title="Mode Updated")

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

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option_id
        user_map = {
            "opt-elon": "elonmusk",
            "opt-sam": "samaltman",
            "opt-lex": "lexfridman",
            "opt-sundar": "sundarpichai"
        }
        if opt_id in user_map:
            self.query_one("#target-input", Input).value = user_map[opt_id]

    def run_agent_execution(self) -> None:
        username = self.query_one("#target-input", Input).value.strip().lstrip("u/").lstrip("/u/")
        instruction = self.query_one("#in-instruction", Input).value.strip()
        mode = str(self.query_one("#sel-mode", Select).value)
        dry_run = self.query_one("#sw-dryrun", Switch).value

        log = self.query_one("#rich-log", RichLog)

        if not username:
            self.notify("Target username cannot be empty!", title="Validation Error", severity="error")
            return

        log.write(f"\n[bold magenta]PUT /messages/{username}[/bold magenta]")
        log.write(f"[dim]Executing run (mode={mode}, dry_run={dry_run})...[/dim]")

        self.notify(f"Sending agent to u/{username}...", title="Request Sent")
        self.run_worker(self._async_agent_run(username, instruction, dry_run, mode))

    async def _async_agent_run(self, username: str, instruction: str, dry_run: bool, mode: str) -> None:
        log = self.query_one("#rich-log", RichLog)
        json_log = self.query_one("#json-log", RichLog)
        pill = self.query_one("#pill-status", Label)

        try:
            result = await run_agent(
                username=username,
                instruction=instruction,
                dry_run=dry_run,
                mode=mode
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
        logs = get_recent_logs(limit=40)
        for row in logs:
            ts = row.get("timestamp", "")[:19].replace("T", " ")
            user = row.get("thread_username", "")
            action = row.get("action", "")
            dry_run = "TRUE" if row.get("dry_run") else "FALSE"
            table.add_row(ts, user, action, dry_run, row.get("details", "")[:50])


def main():
    app = VartalapTUI()
    app.run()


if __name__ == "__main__":
    main()
