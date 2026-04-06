"""
Telegram Alert System
-----------------------
Sends trade signal alerts to a Telegram chat using the Bot API.

Message format mirrors the TRADE SUMMARY CARD from the prompt,
including the full ICT signal breakdown.
"""
import asyncio
import logging
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Alert Sender
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def send_signal_alert(signal: dict, signal_id: int) -> bool:
    """
    Format and send a signal alert to Telegram.
    Returns True if sent successfully.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set. Alert skipped.")
        return False

    message = _format_signal_message(signal, signal_id)

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            log.info(f"Telegram alert sent for signal #{signal_id}")
            return True
        else:
            log.error(f"Telegram API error: {data}")
            return False
    except Exception as exc:
        log.error(f"Failed to send Telegram alert: {exc}")
        return False


def send_heartbeat() -> bool:
    """Send a simple heartbeat message â useful for confirming bot is alive."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        f"ð <b>QuantLive Heartbeat</b>\n"
        f"Pipeline running | {now}\n"
        f"Scanning {config.SYMBOL} every 30 min"
    )

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as exc:
        log.error(f"Heartbeat failed: {exc}")
        return False


def send_no_trade_summary(reason: str = "") -> bool:
    """Optionally notify when a pipeline run finds no valid trade."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    msg = f"ð <b>QuantLive Scan</b> | {now}\nâ¸ <b>NO TRADE</b>"
    if reason:
        msg += f"\nReason: {reason}"

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception:
        return False


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Message Formatter â TRADE SUMMARY CARD
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _format_signal_message(sig: dict, signal_id: int) -> str:
    """
    Build the full Telegram message mirroring the ICT Trade Summary Card.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    direction = sig.get("direction", "?")
    mode      = sig.get("mode", "?")

    # Direction emoji
    dir_emoji = "ð¢" if direction == "BUY" else "ð´"
    verdict   = sig.get("verdict", "NO_TRADE")
    verdict_emoji = "â" if "EXECUTE" in verdict else ("â ï¸" if "BORDERLINE" in verdict else "â")

    # Size modifier from verdict
    size_note = {
        "EXECUTE_FULL":      "Full size (100%)",
        "EXECUTE_REDUCE_10": "Reduce 10%",
        "EXECUTE_REDUCE_25": "Reduce 25%",
        "EXECUTE_REDUCE_50": "Reduce 50%",
        "BORDERLINE":        "50% max â borderline",
        "NO_TRADE":          "DO NOT TRADE",
    }.get(verdict, verdict)

    entry_type = sig.get("entry_type", "?")
    phase_s    = sig.get("phase_swing", "?")
    phase_i    = sig.get("phase_intraday", "?")

    entry_low  = sig.get("entry_zone_low",  0)
    entry_high = sig.get("entry_zone_high", 0)
    entry_tf   = sig.get("entry_tf", "?")
    fvg_ce     = sig.get("fvg_ce", 0)

    t1   = sig.get("stop_loss_t1", 0)
    t2   = sig.get("stop_loss_t2", 0)
    t1t2 = round(abs(t2 - t1), 1)
    gap_note = f"{t1t2}pt gap" if t1 != t2 else "Single-tier SL"

    part_a = sig.get("part_a_target", 0)
    part_b = sig.get("part_b_target", 0)
    part_c = sig.get("part_c_target", 0)
    rr     = sig.get("rr_part_b", 0)

    lots  = sig.get("lots", 0)
    risk_usd = sig.get("risk_dollars", 0)

    judas_min = sig.get("judas_min", 0)
    judas_max = sig.get("judas_max", 0)

    gates    = sig.get("gates_passed", 0)
    score    = sig.get("fvg_score", 0)
    macro    = sig.get("macro_bias", "?")
    session  = sig.get("session_bias", "?")

    dol_p    = sig.get("dol_primary")
    dol_type = "BSL" if direction == "BUY" else "SSL"

    msg = (
        f"ââââââââââââââââââââââââââââââââââââââââ\n"
        f"â  {dir_emoji} <b>QuantLive Signal #{signal_id}</b>          â\n"
        f"â  {now}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>MODE:</b>        {mode}\n"
        f"â <b>ENTRY TYPE:</b>  {entry_type}\n"
        f"â <b>SWING PHASE:</b> {phase_s}  |  <b>INTRA:</b> {phase_i}\n"
        f"â <b>SESSION:</b>     {session}  |  <b>MACRO:</b> {macro}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>DIRECTION:</b>   {dir_emoji} {direction}\n"
        f"â <b>ENTRY ZONE:</b>  {entry_low:.2f} â {entry_high:.2f}\n"
        f"â <b>FVG CE (limit):</b> {fvg_ce:.2f}  [{entry_tf}]\n"
    )

    if dol_p:
        msg += f"â <b>DOL TARGET:</b>  {dol_p:.2f} [{dol_type}]\n"

    msg += (
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>STOP LOSS</b>\n"
        f"â  Alert T1:  {t1:.2f}  (nearest cluster)\n"
        f"â  Hard  T2:  {t2:.2f}  (farthest + buffer)\n"
        f"â  Gap:       {gap_note}\n"
        f"â <b>JUDAS RANGE:</b> {judas_min:.2f} â {judas_max:.2f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>TARGETS</b>\n"
        f"â  Part A (40%): {part_a:.2f}\n"
        f"â  Part B (35%): {part_b:.2f}  â R:R {rr:.1f}:1\n"
        f"â  Part C (25%): {part_c:.2f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>POSITION</b>\n"
        f"â  Lots:   {lots:.2f}  |  Risk: ${risk_usd:.0f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>QUALITY GATE</b>\n"
        f"â  FVG Score:    {score}/~15\n"
        f"â  Gates Passed: {gates}/16\n"
        f"â  {verdict_emoji} <b>VERDICT: {verdict}</b>\n"
        f"â  Size: {size_note}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ\n"
        f"\n"
        f"â ï¸ Wait for 3-candle confirmation before entry.\n"
        f"Do NOT enter until Judas sweep is complete.\n"
        f"Set SL T2 before entering. All 3 TP orders first."
    )

    return msg
