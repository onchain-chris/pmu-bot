#!/usr/bin/env python3
"""PMU Horse Racing Value Betting Bot — Main entry point.

Startup flow:
1. Call /v4/sports?all=true, print all horse racing keys
2. Ask user to confirm which sport key to use
3. Start polling loop with APScheduler
4. Launch Flask web dashboard
"""

import signal
import sys
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

import config
import database
import scraper
import bot
from web import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pmu-bot")


def discover_sport_key():
    """Discover horse racing sport keys and let the user choose one."""
    if not config.API_KEY:
        print("ERROR: ODDS_API_KEY not set in .env")
        sys.exit(1)

    print("\nDiscovering horse racing sports...\n")

    try:
        horse_sports, all_sports = scraper.fetch_sports(all_sports=True)
    except Exception as e:
        print(f"Failed to fetch sports: {e}")
        sys.exit(1)

    quota = scraper.get_quota()
    print(f"API quota remaining: {quota['requests_remaining']}\n")

    if not horse_sports:
        print("No horse racing sports found. All available sports:\n")
        for s in all_sports:
            active = "(active)" if s.get("active") else ""
            print(f"  {s['key']:40s} {s.get('title', '')} {active}")
        print("\nEnter a sport key manually:")
        return input("> ").strip()

    print("Horse racing sports found:\n")
    for i, s in enumerate(horse_sports, 1):
        active = "(active)" if s.get("active") else "(inactive)"
        print(f"  [{i}] {s['key']:40s} {s.get('title', '')} {active}")

    print(f"\nSelect sport key (1-{len(horse_sports)}) or type a custom key:")
    choice = input("> ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(horse_sports):
            return horse_sports[idx]["key"]
    except ValueError:
        pass

    return choice


def main():
    database.init_db()
    database.log_bankroll(config.BANKROLL)

    sport_key = discover_sport_key()
    print(f"\nUsing sport key: {sport_key}\n")

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

    # Run first analysis in background thread
    def initial_run():
        try:
            bot.run_analysis(sport_key)
        except Exception as e:
            logger.error("Initial analysis error: %s", e)

    threading.Thread(target=initial_run, daemon=True).start()

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start web interface
    print(f"Dashboard running at http://{config.WEB_HOST}:{config.WEB_PORT}\n")
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)


if __name__ == "__main__":
    main()
