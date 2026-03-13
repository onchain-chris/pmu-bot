#!/usr/bin/env python3
"""PMU Horse Racing Value Betting Bot — Main entry point.

Startup flow:
1. Call /v4/sports?all=true, print all horse racing keys
2. Ask user to confirm which sport key to use
3. Start polling loop with APScheduler
4. Display terminal dashboard with Rich
"""

import signal
import sys
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

import config
import database
import scraper
import bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pmu-bot")
console = Console()


def discover_sport_key():
    """Discover horse racing sport keys and let the user choose one."""
    if not config.API_KEY:
        console.print("[bold red]ERROR: ODDS_API_KEY not set in .env[/bold red]")
        sys.exit(1)

    console.print("\n[bold cyan]Discovering horse racing sports...[/bold cyan]\n")

    try:
        horse_sports, all_sports = scraper.fetch_sports(all_sports=True)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch sports: {e}[/bold red]")
        sys.exit(1)

    quota = scraper.get_quota()
    console.print(f"API quota — remaining: {quota['requests_remaining']}\n")

    if not horse_sports:
        console.print("[yellow]No horse racing sports found. All available sports:[/yellow]\n")
        for s in all_sports:
            console.print(f"  {s['key']:40s} {s.get('title', '')} {'(active)' if s.get('active') else ''}")
        console.print("\n[yellow]Enter a sport key manually:[/yellow]")
        return input("> ").strip()

    console.print("[bold green]Horse racing sports found:[/bold green]\n")
    for i, s in enumerate(horse_sports, 1):
        active = "[green](active)[/green]" if s.get("active") else "[red](inactive)[/red]"
        console.print(f"  [{i}] {s['key']:40s} {s.get('title', '')} {active}")

    console.print(f"\n[cyan]Select sport key (1-{len(horse_sports)}) or type a custom key:[/cyan]")
    choice = input("> ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(horse_sports):
            return horse_sports[idx]["key"]
    except ValueError:
        pass

    return choice


def build_dashboard():
    """Build a Rich renderable dashboard."""
    quota = scraper.get_quota()
    signals_today = database.get_todays_signals()
    events_count = database.get_events_tracked_today()
    bankroll = database.get_current_bankroll()

    # Status panel
    status_lines = [
        f"Mode:            {'PAPER TRADING' if config.PAPER_TRADING else 'LIVE'}",
        f"Bankroll:        {bankroll:.2f} EUR",
        f"Poll interval:   {config.POLL_INTERVAL_SECONDS}s",
        f"Min edge:        {config.MIN_EDGE * 100:.0f}%",
        f"Kelly fraction:  {config.KELLY_FRACTION}",
    ]
    status_panel = Panel("\n".join(status_lines), title="Bot Status", border_style="cyan")

    # Quota panel
    quota_lines = [
        f"Remaining: {quota.get('requests_remaining', 'N/A')}",
        f"Used:      {quota.get('requests_used', 'N/A')}",
        f"Last cost: {quota.get('requests_last', 'N/A')}",
    ]
    quota_panel = Panel("\n".join(quota_lines), title="API Quota", border_style="yellow")

    # Stats panel
    stats_lines = [
        f"Events tracked today: {events_count}",
        f"Bet signals today:    {len(signals_today)}",
        f"Last update:          {datetime.utcnow().strftime('%H:%M:%S')} UTC",
    ]
    stats_panel = Panel("\n".join(stats_lines), title="Statistics", border_style="green")

    # Signals table
    table = Table(title="Today's Bet Signals", expand=True)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Horse", style="bold")
    table.add_column("PMU Odds", justify="right")
    table.add_column("Edge %", justify="right", style="green")
    table.add_column("Stake", justify="right")
    table.add_column("Smart $", justify="center")
    table.add_column("Status", justify="center")

    for s in signals_today[:15]:  # show last 15
        created = s.get("created_at", "")
        if isinstance(created, str) and len(created) >= 19:
            time_str = created[11:19]
        else:
            time_str = str(created)

        smart = "[bold red]YES[/bold red]" if s.get("smart_money_signal") else "-"
        result = s.get("result", "pending")
        if result == "won":
            result_style = "[bold green]WON[/bold green]"
        elif result == "lost":
            result_style = "[bold red]LOST[/bold red]"
        else:
            result_style = "[dim]pending[/dim]"

        table.add_row(
            time_str,
            str(s.get("horse_name", "")),
            f"{s.get('pmu_odds', 0):.2f}",
            f"{s.get('edge', 0) * 100:.1f}%",
            f"{s.get('bet_amount', 0):.2f}",
            smart,
            result_style,
        )

    layout = Layout()
    layout.split_column(
        Layout(name="top", size=7),
        Layout(name="bottom"),
    )
    layout["top"].split_row(
        Layout(status_panel),
        Layout(quota_panel),
        Layout(stats_panel),
    )
    layout["bottom"].update(table)

    return layout


def main():
    database.init_db()
    database.log_bankroll(config.BANKROLL)

    sport_key = discover_sport_key()
    console.print(f"\n[bold green]Using sport key: {sport_key}[/bold green]\n")

    # Set up scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        bot.run_analysis,
        "interval",
        seconds=config.POLL_INTERVAL_SECONDS,
        args=[sport_key],
        id="analysis",
        max_instances=1,
    )
    scheduler.start()

    # Run first analysis immediately
    console.print("[cyan]Running initial analysis...[/cyan]\n")
    try:
        bot.run_analysis(sport_key)
    except Exception as e:
        console.print(f"[yellow]Initial analysis error: {e}[/yellow]")

    # Graceful shutdown
    def shutdown(signum, frame):
        console.print("\n[bold yellow]Shutting down...[/bold yellow]")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Live dashboard
    console.print("[bold cyan]Dashboard active. Press Ctrl+C to stop.[/bold cyan]\n")
    try:
        with Live(build_dashboard(), console=console, refresh_per_second=0.2) as live:
            while True:
                live.update(build_dashboard())
                import time
                time.sleep(5)
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        console.print("\n[bold yellow]Stopped.[/bold yellow]")


if __name__ == "__main__":
    main()
