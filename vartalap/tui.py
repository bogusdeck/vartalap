import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Static, RichLog, Label, Switch,
    DataTable, Select, TabbedContent, TabPane, ProgressBar, Digits
)
from textual.binding import Binding
from textual.message import Message

from vartalap.settings import get_settings, reload_settings
from vartalap.agent_loop import run_agent
from vartalap.logger import get_recent_logs, get_messages_sent_today_count
from vartalap.scheduler import start_scheduler, stop_scheduler


class MetricCard(Static):
    """Reusable metric card component for top stats bar."""
    
    def __init__(self, title: str, value: str, subtext: str = "", id: str = None):
        super().__init__(id=id)
        self.card_title = title
        self.card_value = value
        self.card_subtext = subtext

    def compose(self) -> ComposeResult:
        yield Label(self.card_title, classes="metric-title")
        yield Label(self.card_value, classes="metric-value", id=f"{self.id}-val")
        if self.card_subtext:
            yield Label(self.card_subtext, classes="metric-subtext", id=f"{self.id}-sub")

    def update_value(self, value: str, subtext: str = None):
        self.query_one(f"#{self.id}-val", Label).update(value)
        if subtext and self.query(f"#{self.id}-sub"):
            self.query_one(f"#{self.id}-sub", Label).update(subtext)


class VartalapTUI(App):
    """Production-grade Textual Terminal Dashboard for Vartalap Autonomous Reddit DM Agent."""

    TITLE = "VARTALAP CONTROL CENTER"
    SUB_TITLE = "Autonomous Reddit DM Agent v0.1.0"

    CSS = """
    Screen {
        background: $surface-darken-1;
    }
    
    /* Top Metrics Bar */
    #metrics-bar {
        height: 6;
        margin: 0 1 1 1;
    }
    MetricCard {
        background: $panel;
        border: solid $primary-muted;
        padding: 0 1;
        margin-right: 1;
        width: 1fr;
        height: 100%;
    }
    .metric-title {
        text-style: bold;
        color: $text-muted;
        margin-top: 0;
    }
    .metric-value {
        text-style: bold;
        color: $accent;
        font-size: 1;
    }
    .metric-subtext {
        color: $text-muted;
    }

    /* Main Workspace Layout */
    #main-split {
        height: 1fr;
        margin: 0 1;
    }

    /* Left Sidebar Panel */
    #sidebar {
        width: 44;
        background: $panel;
        border: solid $primary;
        padding: 1;
        margin-right: 1;
    }
    .section-header {
        text-style: bold;
        color: $primary-lighten-2;
        background: $primary-darken-3;
        padding: 0 1;
        margin-bottom: 1;
    }
    .field-label {
        text-style: bold;
        color: $text;
        margin-top: 1;
    }
    Input {
        margin-bottom: 1;
        border: tall $secondary-muted;
    }
    Select {
        margin-bottom: 1;
    }
    .toggle-row {
        height: 3;
        margin-bottom: 1;
        align: space-between middle;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
    }

    /* Right Main Content Area */
    #content-area {
        width: 1fr;
        height: 100%;
    }

    TabbedContent {
        height: 100%;
    }

    TabPane {
        padding: 0;
    }

    RichLog {
        height: 100%;
        border: solid $secondary;
        background: $boost;
        padding: 1;
    }

    DataTable {
        height: 100%;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "run_shortcut", "Run Agent", show=True),
        Binding("m", "cycle_mode", "Toggle Mode", show=True),
        Binding("d", "toggle_dry_run", "Toggle DryRun", show=True),
        Binding("l", "refresh_logs", "Refresh Logs", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # Top Stat Metrics Bar
        with Horizontal(id="metrics-bar"):
            yield MetricCard("SYSTEM MODE", "fast_browser", "3x Speed Enabled", id="card-mode")
            yield MetricCard("LLM BACKEND", "cli", "antigravity", id="card-backend")
            yield MetricCard("DAILY MESSAGES", "0 / 20", "Safety Limit Active", id="card-daily")
            yield MetricCard("SCHEDULER", "INTERVAL 10M", "🟢 Active", id="card-scheduler")

        # Main Workspace Split
        with Horizontal(id="main-split"):
            # Left Column Controls
            with Vertical(id="sidebar"):
                yield Label("⚡ AGENT CONTROL PANEL", classes="section-header")

                yield Label("Target User:", classes="field-label")
                yield Input(placeholder="e.g. elonmusk", id="in-user", value="elonmusk")

                yield Label("Instruction Prompt:", classes="field-label")
                yield Input(placeholder="High level instruction...", id="in-instruction", value="Reply matching tone, keep casual")

                yield Label("Execution Speed Mode:", classes="field-label")
                yield Select(
                    options=[
                        ("⚡ Fast Browser (Resource Blocked)", "fast_browser"),
                        ("🚀 Direct HTTP API (<300ms)", "direct_api"),
                        ("🌐 Full Browser (Headed / Visual)", "browser"),
                    ],
                    value="fast_browser",
                    id="sel-mode"
                )

                with Horizontal(classes="toggle-row"):
                    yield Label("Dry Run (Simulate Sends):")
                    yield Switch(value=True, id="sw-dryrun")

                yield Button("🚀 RUN AGENT NOW", id="btn-run-agent", variant="primary")
                yield Button("🔄 HOT RELOAD CONFIG", id="btn-reload-config", variant="secondary")
                yield Button("📊 FETCH RECENT LOGS", id="btn-fetch-logs", variant="default")

            # Right Column Tabbed Display
            with Vertical(id="content-area"):
                with TabbedContent(initial="tab-terminal"):
                    with TabPane("🖥️ Terminal Execution Stream", id="tab-terminal"):
                        yield RichLog(id="rich-log", wrap=True, highlight=True, markup=True)

                    with TabPane("📜 Audit Trail Database", id="tab-audit"):
                        yield DataTable(id="dt-audit")

                    with TabPane("⚙️ Active Configuration", id="tab-config"):
                        yield RichLog(id="config-log", wrap=True, highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize UI data tables, metrics, and startup notifications."""
        self.update_metrics_and_config()

        log_widget = self.query_one("#rich-log", RichLog)
        log_widget.write("[bold green]======================================================[/bold green]")
        log_widget.write("[bold green] 🤖 VARTALAP AUTONOMOUS AGENT CONTROL CENTER ONLINE [/bold green]")
        log_widget.write("[bold green]======================================================[/bold green]")
        log_widget.write("[dim]Press R to trigger run, M to cycle mode, D to toggle dry run, Q to quit.[/dim]\n")

        # Setup Audit Data Table
        table = self.query_one("#dt-audit", DataTable)
        table.add_columns("Timestamp (UTC)", "User", "Action", "Mode", "DryRun", "Details")
        self.load_audit_logs()

    def update_metrics_and_config(self) -> None:
        """Refresh top metric cards and config display."""
        settings = get_settings()
        sent_today = get_messages_sent_today_count()
        max_daily = settings.agent.max_messages_per_day

        # Update Top Cards
        self.query_one("#card-mode", MetricCard).update_value(
            settings.agent.mode,
            "Resource Blocked" if settings.agent.mode == "fast_browser" else ("Direct HTTP" if settings.agent.mode == "direct_api" else "Full Visual")
        )
        self.query_one("#card-backend", MetricCard).update_value(
            settings.llm.backend,
            f"Command: {settings.llm.cli.command[:20]}..." if settings.llm.backend == "cli" else settings.llm.api.provider
        )
        self.query_one("#card-daily", MetricCard).update_value(
            f"{sent_today} / {max_daily}",
            "Limit Normal" if sent_today < max_daily else "[bold red]CAP REACHED[/bold red]"
        )

        # Update Config Display Tab
        cfg_log = self.query_one("#config-log", RichLog)
        cfg_log.clear()
        cfg_log.write("[bold cyan]ACTIVE CONFIGURATION SETTINGS[/bold cyan]\n")
        cfg_log.write(f"[bold]LLM Backend:[/bold] {settings.llm.backend}")
        cfg_log.write(f"[bold]Agent Mode:[/bold] {settings.agent.mode}")
        cfg_log.write(f"[bold]Storage State:[/bold] {settings.reddit.storage_state_path}")
        cfg_log.write(f"[bold]Inbox URL:[/bold] {settings.reddit.inbox_url}")
        cfg_log.write(f"[bold]Max Steps / Conversation:[/bold] {settings.agent.max_steps_per_conversation}")
        cfg_log.write(f"[bold]Max Daily Messages:[/bold] {settings.agent.max_messages_per_day}")
        cfg_log.write(f"[bold]Polling Interval:[/bold] {settings.scheduler.polling_interval_minutes} minutes")

    def action_run_shortcut(self) -> None:
        self.trigger_agent_run()

    def action_cycle_mode(self) -> None:
        select = self.query_one("#sel-mode", Select)
        modes = ["fast_browser", "direct_api", "browser"]
        curr_idx = modes.index(select.value) if select.value in modes else 0
        next_mode = modes[(curr_idx + 1) % len(modes)]
        select.value = next_mode
        self.notify(f"Execution mode set to: {next_mode}", title="Mode Change")

    def action_toggle_dry_run(self) -> None:
        sw = self.query_one("#sw-dryrun", Switch)
        sw.value = not sw.value
        state_str = "ENABLED (Simulated)" if sw.value else "DISABLED (REAL SEND)"
        self.notify(f"Dry Run {state_str}", title="Safety Toggle")

    def action_refresh_logs(self) -> None:
        self.load_audit_logs()
        self.notify("Audit logs refreshed from SQLite database", title="Logs Updated")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-agent":
            self.trigger_agent_run()
        elif event.button.id == "btn-reload-config":
            reload_settings()
            self.update_metrics_and_config()
            self.notify("Configuration reloaded from config.yaml and .env", title="Hot Reload")
        elif event.button.id == "btn-fetch-logs":
            self.load_audit_logs()
            self.notify("Fetched recent audit logs", title="Audit Trail")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel-mode":
            settings = get_settings()
            settings.agent.mode = str(event.value)
            self.update_metrics_and_config()

    def trigger_agent_run(self) -> None:
        username = self.query_one("#in-user", Input).value.strip()
        instruction = self.query_one("#in-instruction", Input).value.strip()
        mode = str(self.query_one("#sel-mode", Select).value)
        dry_run = self.query_one("#sw-dryrun", Switch).value

        log_widget = self.query_one("#rich-log", RichLog)

        if not username:
            self.notify("Target username cannot be empty!", title="Error", severity="error")
            return

        log_widget.write(f"\n[bold yellow]------------------------------------------------------[/bold yellow]")
        log_widget.write(f"[bold yellow]▶ STARTING AGENT RUN | User: u/{username} | Mode: {mode}[/bold yellow]")
        log_widget.write(f"[dim]Instruction: {instruction} | Dry Run: {dry_run}[/dim]\n")

        self.notify(f"Running agent for u/{username}...", title="Agent Execution Started")
        self.run_worker(self._async_run_agent(username, instruction, dry_run, mode))

    async def _async_run_agent(self, username: str, instruction: str, dry_run: bool, mode: str) -> None:
        log_widget = self.query_one("#rich-log", RichLog)
        try:
            result = await run_agent(
                username=username,
                instruction=instruction,
                dry_run=dry_run,
                mode=mode
            )
            status = result.get("status")
            final_action = result.get("final_action", "N/A")
            reasoning = result.get("reasoning", "")

            if status == "completed":
                log_widget.write(f"[bold green]✔ RUN SUCCESSFUL![/bold green] Final Action: [bold cyan]{final_action}[/bold cyan]")
                if reasoning:
                    log_widget.write(f"[italic]LLM Reasoning: {reasoning}[/italic]")
                self.notify(f"Run completed for u/{username} ({final_action})", title="Run Success")
            else:
                log_widget.write(f"[bold red]✖ RUN FAILED / STATUS: {status}[/bold red]")
                log_widget.write(f"[dim]Details: {result}[/dim]")
                self.notify(f"Run ended with status: {status}", title="Run Warning", severity="warning")

        except Exception as e:
            log_widget.write(f"[bold red]CRITICAL ERROR during execution: {e}[/bold red]")
            self.notify(f"Execution Error: {e}", title="Run Failure", severity="error")

        self.update_metrics_and_config()
        self.load_audit_logs()

    def load_audit_logs(self) -> None:
        table = self.query_one("#dt-audit", DataTable)
        table.clear()
        logs = get_recent_logs(limit=50)
        for row in logs:
            ts = row.get("timestamp", "")[:19].replace("T", " ")
            user = row.get("thread_username", "")
            action = row.get("action", "")
            details = row.get("details", "")
            dry_run = "TRUE" if row.get("dry_run") else "FALSE"
            table.add_row(ts, user, action, "N/A", dry_run, details[:60])


def main():
    app = VartalapTUI()
    app.run()


if __name__ == "__main__":
    main()
