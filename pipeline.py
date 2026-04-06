"""
Main Pipeline Orchestrator
----------------------------
Called by the scheduler every :00 and :30.

Flow:
  1. Fetch candles (all timeframes)
  2. Get current price
  3. Run signal generator
  4. Quality gate check
  5. Save to DB
  6. Send Telegram alert if verdict != NO_TRADE
"""
import logging
from datetime import datetime, timezone

import config
from data.fetcher import TwelveDataFetcher
from signals.generator import generate_signal
from db.store import save_signal, mark_alert_sent, get_strategy_id
from alerts.telegram import send_signal_alert, send_no_trade_summary

log = logging.getLogger(__name__)


def run_pipeline(silent_no_trade: bool = True) -> dict | None:
    """
    Execute one full pipeline run.

    Returns the signal dict if a trade setup was found, else None.
    silent_no_trade: if True, don't send Telegram for NO_TRADE outcomes
                     (reduces noise during low-volatility periods).
    """
    now = datetime.now(timezone.utc)
    log.info(f"âââ Pipeline run starting | {now.strftime('%Y-%m-%d %H:%M UTC')} âââ")

    # ââ 1. Fetch candles ââââââââââââââââââââââââââââââââââââ
    try:
        fetcher = TwelveDataFetcher()
        candles = fetcher.fetch_all_timeframes(persist=True)
        current_price = fetcher.get_current_price()
        session = fetcher.get_current_session()
    except Exception as exc:
        log.error(f"Data fetch failed: {exc}")
        return None

    if current_price is None:
        log.warning("Could not obtain current price. Skipping pipeline run.")
        return None

    log.info(f"Current price: {current_price:.2f} | Session: {session}")

    # ââ 2. Build extra context âââââââââââââââââââââââââââââââ
    # In a full implementation these would come from news feeds / DXY API.
    # For now we use sensible defaults and let the user configure if needed.
    extra_context = {
        "macro_bias":        "ranging",   # override via env or news adapter
        "news_within_2h":    False,
        "news_within_48h":   False,
        "ceasefire_risk":    False,
        "nfp_fomc_within_48h": False,
    }

    # ââ 3. Generate signal âââââââââââââââââââââââââââââââââââ
    try:
        signal = generate_signal(
            candles=candles,
            current_price=current_price,
            account_size=config.ACCOUNT_SIZE,
            extra_context=extra_context,
        )
    except Exception as exc:
        log.error(f"Signal generation error: {exc}", exc_info=True)
        return None

    if signal is None:
        log.info("No valid signal this run.")
        if not silent_no_trade:
            send_no_trade_summary("No qualifying ICT setup found.")
        return None

    # ââ 4. Quality gate check ââââââââââââââââââââââââââââââââ
    verdict = signal.get("verdict", "NO_TRADE")
    if verdict == "NO_TRADE":
        log.info(f"Signal generated but verdict = NO_TRADE. Not alerting.")
        if not silent_no_trade:
            send_no_trade_summary(f"Signal blocked at quality gate ({signal.get('gates_passed', 0)}/16 gates).")
        return None

    # ââ 5. Save to database ââââââââââââââââââââââââââââââââââ
    try:
        signal_id = save_signal(signal)
    except Exception as exc:
        log.error(f"DB save failed: {exc}", exc_info=True)
        # Still alert even if DB fails
        signal_id = 0

    # ââ 6. Send Telegram alert âââââââââââââââââââââââââââââââ
    try:
        sent = send_signal_alert(signal, signal_id)
        if sent and signal_id > 0:
            mark_alert_sent(signal_id)
    except Exception as exc:
        log.error(f"Telegram alert failed: {exc}")

    log.info(f"âââ Pipeline run complete | Signal #{signal_id} | {verdict} âââ")
    return signal


if __name__ == "__main__":
    # Allow running a single pipeline cycle manually for testing
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = run_pipeline(silent_no_trade=False)
    if result:
        print(f"\nSignal generated: {result['direction']} | Verdict: {result['verdict']}")
    else:
        print("\nNo trade signal generated this run.")
    sys.exit(0 if result else 1)
