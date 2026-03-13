import logging

import config
import database
import scraper
import odds_analyzer
import notifier

logger = logging.getLogger(__name__)


def calculate_kelly_stake(edge, pmu_odds, bankroll):
    """Calculate bet size using fractional Kelly criterion.

    kelly_fraction = (edge / (pmu_odds - 1)) * KELLY_FRACTION
    amount = min(kelly * bankroll, MAX_BET_FRACTION * bankroll)
    """
    if pmu_odds <= 1.0 or edge <= 0:
        return 0.0, 0.0

    kelly = (edge / (pmu_odds - 1.0)) * config.KELLY_FRACTION
    kelly = max(0.0, kelly)
    amount = kelly * bankroll
    max_bet = config.MAX_BET_FRACTION * bankroll
    amount = min(amount, max_bet)

    return kelly, round(amount, 2)


def run_analysis(sport_key):
    """Main analysis cycle: fetch, analyze, signal.

    1. Fetch fresh odds snapshot
    2. Save to DB
    3. Run odds_analyzer.find_value_bets()
    4. For each value bet: calculate Kelly stake, log signal, notify
    """
    # Fetch and store
    events = scraper.fetch_and_store(sport_key)
    if not events:
        logger.info("No events with odds data found")
        return []

    # Find value bets
    value_bets = odds_analyzer.find_value_bets(events)
    if not value_bets:
        logger.info("No value bets found this cycle")
        return []

    bankroll = database.get_current_bankroll()
    signals = []

    for vb in value_bets:
        kelly, amount = calculate_kelly_stake(vb["edge"], vb["pmu_odds"], bankroll)

        if amount <= 0:
            continue

        vb["kelly_fraction"] = kelly
        vb["bet_amount"] = amount

        # Save signal to database
        database.save_bet_signal(
            event_id=vb["event_id"],
            horse_name=vb["horse_name"],
            pmu_odds=vb["pmu_odds"],
            fair_prob=vb["fair_prob"],
            edge=vb["edge"],
            kelly_fraction=kelly,
            bet_amount=amount,
            smart_money_signal=vb["smart_money_signal"],
        )

        if config.PAPER_TRADING:
            logger.info(
                "PAPER BET: %s @ %.2f — stake %.2f EUR (edge %.1f%%)",
                vb["horse_name"], vb["pmu_odds"], amount, vb["edge"] * 100,
            )
        else:
            logger.info(
                "LIVE BET SIGNAL: %s @ %.2f — stake %.2f EUR (edge %.1f%%)",
                vb["horse_name"], vb["pmu_odds"], amount, vb["edge"] * 100,
            )

        # Send Telegram notification
        notifier.notify_bet_signal(vb)
        signals.append(vb)

    logger.info("Cycle complete: %d value bets found", len(signals))
    return signals
