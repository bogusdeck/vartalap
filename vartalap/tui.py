import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Input, Static, RichLog, Label, Switch, DataTable
from textual.binding import Binding

from vartalap.settings import get_settings
from vartalap.agent_loop import run_agent
from vartalap.logger import get_recent_logs, get_messages_sent_today_count


class VartalapTUI(App):
    """Textual Terminal Dashboard for Vartalap Autonomous Reddit DM Agent."""

    CSS = """
    Screen {
        background: $surface;
    }
    #sidebar {
        width: 42;
        border-right: heavy $primary;
        padding: 1;
        background: $panel;
    }
    #main-content {
        padding: 1;
    }
    .panel-title {
        font-weight: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .status-item {
        margin-bottom: 1;
    }
    Input {
        margin-bottom: 1;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
    }
    RichLog {
        height: 1fr;
        border: solid $secondary;
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "run_agent_shortcut", "Run Agent", show=True),
        Binding("l", "refresh_logs", "Logs", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("⚙️ CONTROL PANEL", classes="panel-title")
                
                yield Label("Target Reddit User:")
                yield Input(placeholder="e.g. elonmusk", id="username-input", value="elonmusk")
                
                yield Label("Instruction:")
                yield Input(placeholder="Instruction for LLM...", id="instruction-input", value="Reply matching tone, keep casual")
                
                yield Label("Dry Run Mode:")
                yield Switch(value=True, id="dryrun-switch")
                
                yield Button("🚀 Run Agent", id="btn-run", variant="primary")
                yield Button("📜 Refresh Logs", id="btn-logs", variant="default")

                yield Label("\n📊 SYSTEM STATUS", classes="panel-title")
                yield Static(id="system-status-box", classes="status-item")

            with Vertical(id="main-content"):
                yield Label("📜 LIVE AGENT LOGS & REASONING", classes="panel-title")
                yield RichLog(id="log-output", wrap=True, highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.update_status_display()
        log_widget = self.query_one("#log-output", RichLog)
        log_widget.write("[bold green]Vartalap TUI Dashboard Initialized.[/bold green]")
        log_widget.write("[dim]Press R or click 'Run Agent' to start an autonomous conversation step.[/dim]\n")

    def update_status_display(self) -> None:
        settings = get_settings()
        sent_today = get_messages_sent_today_count()
        status_text = (
            f"[bold]LLM Backend:[/bold] {settings.llm.backend}\n"
            f"[bold]Agent Mode:[/bold] {settings.agent.mode}\n"
            f"[bold]Headless:[/bold] {settings.reddit.headless}\n"
            f"[bold]Daily Sent:[/bold] {sent_today}/{settings.agent.max_messages_per_day}\n"
        )
        self.query_one("#system-status-box", Static).update(status_text)

    async def action_run_agent_shortcut(self) -> None:
        await self.trigger_agent_run()

    async def action_refresh_logs(self) -> None:
        self.load_logs_into_view()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            await self.trigger_agent_run()
        elif event.button.id == "btn-logs":
            self.load_logs_into_view()

    async def trigger_agent_run(self) -> None:
        username = self.query_one("#username-input", Input).value.strip()
        instruction = self.query_one("#instruction-input", Input).value.strip()
        dry_run = self.query_one("#dryrun-switch", Switch).value

        log_widget = self.query_one("#log-output", RichLog)

        if not username:
            log_widget.write("[bold red]Error: Target username cannot be empty![/bold red]")
            return

        log_widget.write(f"\n[bold yellow]--- Launching Agent Run for u/{username} ---[/bold yellow]")
        log_widget.write(f"[dim]Instruction: {instruction} | Dry Run: {dry_run}[/dim]")

        # Run agent in background task to keep UI responsive
        self.run_worker(self._async_run_agent(username, instruction, dry_run))

    async def _async_run_agent(self, username: str, instruction: str, dry_run: bool) -> None:
        log_widget = self.query_one("#log-output", RichLog)
        try:
            result = await run_agent(username=username, instruction=instruction, dry_run=dry_run)
            status = result.get("status")
            final_action = result.get("final_action", "N/A")
            reasoning = result.get("reasoning", "")
            
            if status == "completed":
                log_widget.write(f"[bold green]✔ Run Completed![/bold green] Final Action: [cyan]{final_action}[/cyan]")
                if reasoning:
                    log_widget.write(f"[italic]LLM Reasoning: {reasoning}[/italic]")
            else:
                log_widget.write(f"[bold red]✖ Run Status: {status}[/bold red] Details: {result}")
        except Exception as e:
            log_widget.write(f"[bold red]Exception during agent run: {e}[/bold red]")

        self.update_status_display()

    def load_logs_into_view(self) -> None:
        log_widget = self.query_one("#log-output", RichLog)
        logs = get_recent_logs(limit=15)
        log_widget.write("\n[bold cyan]--- Recent SQLite Action Logs ---[/bold cyan]")
        for row in logs:
            ts = row.get("timestamp", "")[:19]
            user = row.get("thread_username", "")
            action = row.get("action", "")
            details = row.get("details", "")
            log_widget.write(f"[dim]{ts}[/dim] | [bold]{user}[/bold] | [yellow]{action}[/yellow] | {details}")


def main():
    app = VartalapTUI()
    app.run()


if __name__ == "__main__":
    main()
