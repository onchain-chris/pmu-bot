import time
import logging

import requests

import config
import database

logger = logging.getLogger(__name__)

# Track API quota from response headers
quota_info = {
    "requests_remaining": None,
    "requests_used": None,
    "requests_last": None,
}


def _update_quota(response):
    quota_info["requests_remaining"] = response.headers.get("x-requests-remaining")
    quota_info["requests_used"] = response.headers.get("x-requests-used")
    quota_info["requests_last"] = response.headers.get("x-requests-last")
    logger.info(
        "API quota — remaining: %s, used: %s, last: %s",
        quota_info["requests_remaining"],
        quota_info["requests_used"],
        quota_info["requests_last"],
    )


def get_quota():
    return quota_info.copy()


def fetch_sports(all_sports=True):
    """Fetch all available sports from The Odds API.
    Returns list of sport dicts, filtered for horse racing keys."""
    params = {"apiKey": config.API_KEY}
    if all_sports:
        params["all"] = "true"

    resp = requests.get(f"{config.BASE_URL}/sports", params=params, timeout=30)
    resp.raise_for_status()
    _update_quota(resp)

    sports = resp.json()
    horse_racing = [
        s for s in sports
        if "horse" in s.get("key", "").lower()
        or "horse" in s.get("title", "").lower()
        or "racing" in s.get("key", "").lower()
        or "racing" in s.get("title", "").lower()
    ]
    return horse_racing, sports


def fetch_odds(sport_key):
    """Fetch current odds for a sport key from The Odds API.
    Returns list of event dicts with bookmaker odds."""
    params = {
        "apiKey": config.API_KEY,
        "regions": config.REGIONS,
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": config.BOOKMAKERS,
    }

    resp = requests.get(
        f"{config.BASE_URL}/sports/{sport_key}/odds",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    _update_quota(resp)
    return resp.json()


def parse_and_store(events, sport_key):
    """Parse event odds data and store snapshots in the database.
    Returns a structured list of events with their odds for analysis."""
    rows = []
    parsed_events = []

    for event in events:
        event_id = event.get("id", "")
        commence_time = event.get("commence_time", "")
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")

        event_data = {
            "event_id": event_id,
            "sport_key": sport_key,
            "commence_time": commence_time,
            "home_team": home_team,
            "away_team": away_team,
            "bookmakers": {},
        }

        for bookmaker in event.get("bookmakers", []):
            bk_key = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    horse_name = outcome.get("name", "")
                    odds = outcome.get("price", 0.0)
                    if odds <= 1.0:
                        continue
                    rows.append((
                        event_id, sport_key, commence_time,
                        horse_name, bk_key, odds,
                    ))
                    if horse_name not in event_data["bookmakers"]:
                        event_data["bookmakers"][horse_name] = {}
                    event_data["bookmakers"][horse_name][bk_key] = odds

        if event_data["bookmakers"]:
            parsed_events.append(event_data)

    if rows:
        database.save_snapshots_batch(rows)
        logger.info("Stored %d odds snapshots across %d events", len(rows), len(parsed_events))

    return parsed_events


def fetch_and_store(sport_key):
    """Full pipeline: fetch odds, parse, and store. Returns parsed events."""
    logger.info("Fetching odds for %s ...", sport_key)
    events = fetch_odds(sport_key)
    time.sleep(1)  # respect rate limits
    parsed = parse_and_store(events, sport_key)
    logger.info("Fetched %d events with odds data", len(parsed))
    return parsed
