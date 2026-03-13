"""Flask web interface for the PMU betting bot."""

import os
from datetime import datetime

from flask import Flask, render_template, jsonify, request

import config
import database
import scraper

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/status")
def api_status():
    quota = scraper.get_quota()
    return jsonify({
        "bankroll": database.get_current_bankroll(),
        "events_today": database.get_events_tracked_today(),
        "signals_today": len(database.get_todays_signals()),
        "poll_interval": config.POLL_INTERVAL_SECONDS,
        "min_edge": config.MIN_EDGE,
        "kelly_fraction": config.KELLY_FRACTION,
        "quota": quota,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/signals")
def api_signals():
    signals = database.get_all_signals(limit=200)
    return jsonify(signals)


@app.route("/api/signals/today")
def api_signals_today():
    signals = database.get_todays_signals()
    return jsonify(signals)


@app.route("/api/bankroll")
def api_bankroll():
    history = database.get_bankroll_history(limit=50)
    return jsonify({
        "current": database.get_current_bankroll(),
        "history": history,
    })


@app.route("/api/bankroll", methods=["POST"])
def api_update_bankroll():
    data = request.get_json()
    if not data or "balance" not in data:
        return jsonify({"error": "balance required"}), 400
    try:
        balance = float(data["balance"])
    except (ValueError, TypeError):
        return jsonify({"error": "invalid balance"}), 400
    database.update_bankroll(balance)
    return jsonify({"balance": balance})


@app.route("/api/signals/<int:signal_id>/result", methods=["POST"])
def api_update_result(signal_id):
    data = request.get_json()
    if not data or "result" not in data:
        return jsonify({"error": "result required"}), 400
    result = data["result"]
    if result not in ("won", "lost"):
        return jsonify({"error": "result must be 'won' or 'lost'"}), 400
    profit = data.get("profit", 0.0)
    try:
        profit = float(profit)
    except (ValueError, TypeError):
        profit = 0.0
    database.update_signal_result(signal_id, result, profit)
    return jsonify({"ok": True})


@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify({
        "min_edge": config.MIN_EDGE,
        "max_bet_fraction": config.MAX_BET_FRACTION,
        "kelly_fraction": config.KELLY_FRACTION,
        "poll_interval": config.POLL_INTERVAL_SECONDS,
        "bankroll": config.BANKROLL,
        "bookmakers": config.BOOKMAKERS,
        "regions": config.REGIONS,
    })


@app.route("/api/config", methods=["POST"])
def api_update_config():
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    if "min_edge" in data:
        config.MIN_EDGE = float(data["min_edge"])
    if "max_bet_fraction" in data:
        config.MAX_BET_FRACTION = float(data["max_bet_fraction"])
    if "kelly_fraction" in data:
        config.KELLY_FRACTION = float(data["kelly_fraction"])
    if "poll_interval" in data:
        config.POLL_INTERVAL_SECONDS = int(data["poll_interval"])
    return jsonify({"ok": True})
