import logging

import config
import database

logger = logging.getLogger(__name__)

PMU_KEY = "pmu_fr"


def calc_no_vig_prob(odds_dict):
    """Remove bookmaker margin to get fair probabilities.

    Args:
        odds_dict: {horse_name: odds} for a single bookmaker

    Returns:
        {horse_name: fair_probability}
    """
    if not odds_dict:
        return {}

    raw_probs = {name: 1.0 / odds for name, odds in odds_dict.items() if odds > 1.0}
    overround = sum(raw_probs.values())

    if overround == 0:
        return {}

    return {name: prob / overround for name, prob in raw_probs.items()}


def calc_edge(pmu_odds, fair_prob):
    """Calculate value edge: edge = (fair_prob * pmu_odds) - 1"""
    return (fair_prob * pmu_odds) - 1.0


def detect_odds_movement(event_id, horse_name):
    """Check if odds have dropped significantly (smart money signal).

    Compares current PMU odds vs snapshot from MOVEMENT_WINDOW_MINUTES ago.
    A drop > MOVEMENT_THRESHOLD indicates smart money.
    """
    historical = database.get_historical_odds(
        event_id, horse_name, minutes_ago=config.MOVEMENT_WINDOW_MINUTES
    )

    # Get only PMU historical odds
    pmu_historical = [r for r in historical if r["bookmaker"] == PMU_KEY]
    if not pmu_historical:
        return False, 0.0

    old_odds = pmu_historical[0]["odds"]

    # Get current PMU odds (most recent snapshot without time filter)
    current = database.get_historical_odds(event_id, horse_name)
    pmu_current = [r for r in current if r["bookmaker"] == PMU_KEY]
    if not pmu_current:
        return False, 0.0

    current_odds = pmu_current[0]["odds"]

    if old_odds <= 1.0:
        return False, 0.0

    movement = (old_odds - current_odds) / old_odds
    is_smart_money = movement >= config.MOVEMENT_THRESHOLD

    if is_smart_money:
        logger.info(
            "Smart money detected: %s — odds dropped %.1f%% (%s → %s)",
            horse_name, movement * 100, old_odds, current_odds,
        )

    return is_smart_money, movement


def _build_fair_probs_from_non_pmu(bookmakers_data):
    """Build fair probabilities by averaging non-PMU bookmaker odds,
    then removing the vig.

    Args:
        bookmakers_data: {horse_name: {bookmaker_key: odds}}

    Returns:
        {horse_name: fair_probability}
    """
    # Collect non-PMU odds per horse
    non_pmu_avg = {}
    for horse_name, bk_odds in bookmakers_data.items():
        non_pmu = [odds for bk, odds in bk_odds.items() if bk != PMU_KEY and odds > 1.0]
        if non_pmu:
            non_pmu_avg[horse_name] = sum(non_pmu) / len(non_pmu)

    if not non_pmu_avg:
        return {}

    return calc_no_vig_prob(non_pmu_avg)


def find_value_bets(events):
    """Find value bets across all events.

    For each horse in each event:
    1. Calculate fair prob using average of non-PMU bookmakers
    2. Calculate edge vs PMU odds
    3. Return list of value bets above MIN_EDGE threshold

    Args:
        events: list of parsed event dicts from scraper.parse_and_store()

    Returns:
        list of dicts with bet signal details
    """
    value_bets = []

    for event in events:
        event_id = event["event_id"]
        bookmakers_data = event["bookmakers"]

        fair_probs = _build_fair_probs_from_non_pmu(bookmakers_data)
        if not fair_probs:
            continue

        for horse_name, fair_prob in fair_probs.items():
            pmu_odds = bookmakers_data.get(horse_name, {}).get(PMU_KEY)
            if pmu_odds is None or pmu_odds <= 1.0:
                continue

            edge = calc_edge(pmu_odds, fair_prob)
            if edge < config.MIN_EDGE:
                continue

            smart_money, movement = detect_odds_movement(event_id, horse_name)

            value_bets.append({
                "event_id": event_id,
                "sport_key": event.get("sport_key", ""),
                "commence_time": event.get("commence_time", ""),
                "horse_name": horse_name,
                "pmu_odds": pmu_odds,
                "fair_prob": fair_prob,
                "edge": edge,
                "smart_money_signal": smart_money,
                "odds_movement": movement,
            })

            logger.info(
                "Value bet found: %s @ %.2f (edge: %.1f%%, fair_prob: %.3f, smart_money: %s)",
                horse_name, pmu_odds, edge * 100, fair_prob, smart_money,
            )

    # Sort by edge descending
    value_bets.sort(key=lambda x: x["edge"], reverse=True)
    return value_bets
