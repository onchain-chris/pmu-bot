import logging

import requests

import config

logger = logging.getLogger(__name__)


def send_telegram(message):
    """Send a message via Telegram bot API. Silently skips if not configured."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured, skipping notification")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Telegram notification sent")
        return True
    except requests.RequestException as e:
        logger.warning("Failed to send Telegram notification: %s", e)
        return False


def format_bet_signal(signal):
    """Format a bet signal dict into a readable Telegram message."""
    smart = "YES" if signal.get("smart_money_signal") else "no"
    lines = [
        f"*PMU Value Bet Signal*",
        f"Horse: `{signal['horse_name']}`",
        f"Event: `{signal['event_id']}`",
        f"Time: {signal.get('commence_time', 'N/A')}",
        f"PMU Odds: *{signal['pmu_odds']:.2f}*",
        f"Fair Prob: {signal['fair_prob']:.3f}",
        f"Edge: *{signal['edge'] * 100:.1f}%*",
        f"Smart Money: {smart}",
        f"Kelly Stake: {signal.get('bet_amount', 0):.2f} EUR",
    ]
    if config.PAPER_TRADING:
        lines.append("Mode: PAPER TRADING")
    return "\n".join(lines)


def notify_bet_signal(signal):
    """Format and send a bet signal notification."""
    message = format_bet_signal(signal)
    return send_telegram(message)
