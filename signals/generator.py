"""
Signal Generation Pipeline
----------------------------
Orchestrates the full ICT analysis flow:

  1. Receive candle data for all timeframes
  2. Detect FVGs, BSL/SSL, Order Blocks
  3. Detect algorithm phase (swing + intraday)
  4. Score all FVGs
  5. Run Step 0C (BSL/SSL sweep range + hard SL)
  6. Run 16-gate risk assessment
  7. Build the signal dict for DB + Telegram
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

import config
from analysis.liquidity import (
    detect_fvgs,
    detect_swing_levels,
    detect_equal_levels,
    detect_order_blocks,
    map_stop_clusters,
    calculate_hard_sl,
    detect_round_numbers,
    LiquidityLevel,
)
from analysis.phases import detect_phase, determine_mode
from analysis.scoring import (
    score_fvg,
    rank_fvgs,
    run_risk_gates,
    calculate_position,
    calculate_targets,
    ScoredFVG,
)

log = logging.getLogger(__name__)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Main Entry Point
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def generate_signal(
    candles: dict[str, pd.DataFrame],
    current_price: float,
    account_size: float = config.ACCOUNT_SIZE,
    extra_context: Optional[dict] = None,
) -> Optional[dict]:
    """
    Run the full ICT pipeline on the provided candle data.

    Returns a signal dict ready for DB storage and alerting,
    or None if no valid trade setup is found.

    candles: { "15min": df, "1h": df, "4h": df, "1day": df }
    """
    if extra_context is None:
        extra_context = {}

    log.info(f"Running signal pipeline | Price: {current_price:.2f}")

    # ââ Step 1: Liquidity Framework ââââââââââââââââââââââââââ
    all_fvgs: list = []
    all_bsl: list[LiquidityLevel] = []
    all_ssl: list[LiquidityLevel] = []
    all_obs: list = []

    for tf, df in candles.items():
        if df.empty:
            continue
        fvgs = detect_fvgs(df, tf)
        bsl, ssl = detect_swing_levels(df, tf)
        obs = detect_order_blocks(df, tf)

        # Enrich equal levels
        bsl = detect_equal_levels(bsl)
        ssl = detect_equal_levels(ssl)

        all_fvgs.extend(fvgs)
        all_bsl.extend(bsl)
        all_ssl.extend(ssl)
        all_obs.extend(obs)

    # Add round numbers
    round_levels = detect_round_numbers(current_price, search_range=400)
    for rl in round_levels:
        if rl.level_type == "BSL":
            all_bsl.append(rl)
        else:
            all_ssl.append(rl)

    log.info(f"Liquidity: {len(all_fvgs)} FVGs, {len(all_bsl)} BSL, {len(all_ssl)} SSL")

    # ââ Step 0A: Phase Detection âââââââââââââââââââââââââââââ
    df_15m = candles.get("15min", pd.DataFrame())
    df_1h  = candles.get("1h",   pd.DataFrame())
    df_4h  = candles.get("4h",   pd.DataFrame())
    df_1d  = candles.get("1day", pd.DataFrame())

    intraday_phase = detect_phase(df_1h if not df_1h.empty else df_15m, "1h")
    swing_phase    = detect_phase(df_4h if not df_4h.empty else df_1d,  "4h")

    mode = determine_mode(swing_phase, intraday_phase)
    log.info(f"Phase â Swing: {swing_phase['phase']} | Intraday: {intraday_phase['phase']} | Mode: {mode}")

    if mode == "PENDING":
        log.info("No qualifying phase for entry. Skipping signal.")
        return None

    # ââ Determine primary context ââââââââââââââââââââââââââââ
    # Use whichever phase has a confirmed entry
    if mode in ("INTRADAY", "LAYERED"):
        primary_phase = intraday_phase
        primary_tfs = ["15min", "1h"]
        trade_mode_str = "INTRADAY"
    else:
        primary_phase = swing_phase
        primary_tfs = ["4h", "1day"]
        trade_mode_str = "SWING"

    entry_type = primary_phase["entry_type"]
    direction = _phase_to_direction(primary_phase)

    if direction is None:
        log.info("Cannot determine trade direction from phase. Skipping.")
        return None

    # ââ Step 4: Score all unmitigated FVGs âââââââââââââââââââ
    unmitigated = [f for f in all_fvgs if not f.mitigated]
    intraday_unmitigated = [f for f in unmitigated if f.timeframe in ("15min", "1h")]
    swing_unmitigated = [f for f in unmitigated if f.timeframe in ("4h", "1day")]

    # Select FVGs on the correct timeframes for the mode
    candidate_fvgs = intraday_unmitigated if trade_mode_str == "INTRADAY" else swing_unmitigated

    # Filter: direction-aligned only
    if direction == "buy":
        candidate_fvgs = [f for f in candidate_fvgs if f.direction == "bullish"]
    else:
        candidate_fvgs = [f for f in candidate_fvgs if f.direction == "bearish"]

    if not candidate_fvgs:
        log.info(f"No unmitigated {direction} FVGs found for {trade_mode_str} mode. Skipping.")
        return None

    # Build scoring context
    dol_price = primary_phase.get("dol")
    dol_type  = primary_phase.get("dol_type")

    macro_bias = extra_context.get("macro_bias", primary_phase.get("bias", "ranging"))
    session_bias = _current_session_bias(df_1h)
    weekly_bias = _weekly_bias(df_1d)

    # Detect kill zone
    hour_utc = datetime.now(timezone.utc).hour
    in_killzone = (config.LONDON_KZ_START <= hour_utc < config.LONDON_KZ_END or
                   config.NEW_YORK_KZ_START <= hour_utc < config.NEW_YORK_KZ_END)

    scored_list: list[ScoredFVG] = []

    for fvg in candidate_fvgs:
        # Map stop clusters for this FVG (Step 0C preliminary)
        sl_clusters = map_stop_clusters(fvg.ce, direction, all_bsl, all_ssl)

        hard_sl, sl_dist, sweep_prob = calculate_hard_sl(
            entry=fvg.ce,
            direction=direction,
            stop_clusters=sl_clusters,
            entry_type=entry_type,
            trade_mode=trade_mode_str,
        )

        # Calculate targets for R:R check
        targets = calculate_targets(fvg.ce, direction, trade_mode_str, all_bsl, all_ssl, hard_sl)

        # R:R check
        sl_distance = abs(fvg.ce - hard_sl)
        part_b_dist = abs(targets["part_b"] - fvg.ce)
        rr = part_b_dist / sl_distance if sl_distance > 0 else 0

        min_rr = config.MIN_RR_INTRADAY if trade_mode_str == "INTRADAY" else config.MIN_RR_SWING
        rr_passes = rr >= min_rr

        # Does FVG point toward DOL?
        if dol_price is not None:
            if direction == "buy" and fvg.ce < dol_price:
                dol_dir = "WITH"
            elif direction == "sell" and fvg.ce > dol_price:
                dol_dir = "WITH"
            else:
                dol_dir = "AGAINST"
        else:
            dol_dir = "WITH"  # benefit of doubt if no DOL

        # Check OB overlap
        ob_overlap = any(
            ob.direction == fvg.direction and
            ob.zone_low <= fvg.ce <= ob.zone_high
            for ob in all_obs
        )

        # Higher TF confirmation
        if trade_mode_str == "INTRADAY":
            higher_confirms = any(
                f.direction == fvg.direction and
                f.zone_low <= fvg.ce <= f.zone_high
                for f in swing_unmitigated
            )
        else:
            higher_confirms = False

        ctx = {
            "macro_bias":             macro_bias,
            "session_bias":           session_bias,
            "weekly_bias":            weekly_bias,
            "has_ob_overlap":         ob_overlap,
            "at_itl_ith":             False,     # simplified â no DB of prior highs/lows
            "inside_ote":             _check_ote(fvg.ce, all_ssl, all_bsl, direction),
            "higher_tf_confirms":     higher_confirms,
            "itl_ith_swept_to_create": sweep_prob in ("CERTAIN", "LIKELY"),
            "dol_direction":          dol_dir,
            "phase":                  primary_phase.get("phase", "UNKNOWN"),
            "entry_type":             entry_type,
            "macro_algorithm_aligned": macro_bias != "ranging",
            "news_within_2h":         extra_context.get("news_within_2h", False),
            "news_within_48h":        extra_context.get("news_within_48h", False),
            "ceasefire_risk":         extra_context.get("ceasefire_risk", False),
            "nfp_fomc_within_48h":    extra_context.get("nfp_fomc_within_48h", False),
            "hard_sl_clears_clusters": len(sl_clusters) > 0,
            "rr_check_passes":        rr_passes,
            "rr_part_b":              round(rr, 2),
            "fvg_edge_at_stop_cluster": False,
            "between_opposing_fvgs":  False,
            "ce_at_range_midpoint":   False,
        }

        s = score_fvg(fvg, ctx)
        s.hard_sl = hard_sl
        s.sl_distance = sl_dist
        s.rr_part_b = round(rr, 2)
        s.rr_passes = rr_passes
        scored_list.append(s)

    # Rank and pick #1
    ranked = rank_fvgs(scored_list)
    if not ranked:
        log.info("No scored FVGs after ranking. Skipping.")
        return None

    best: ScoredFVG = ranked[0]

    if not best.qualifies:
        log.info(f"Top FVG score {best.score} below threshold. No trade.")
        return None

    log.info(f"Top FVG: {best.fvg.direction} {best.fvg.timeframe} | Score: {best.score} | R:R: {best.rr_part_b}")

    # ââ Step 6: Stop Hunt Protection âââââââââââââââââââââââââ
    entry_price = best.fvg.ce
    stop_clusters = map_stop_clusters(entry_price, direction, all_bsl, all_ssl)

    # Alert SL T1 = nearest cluster
    if direction == "sell":
        t1_clusters = sorted([c for c in stop_clusters if c.price > entry_price], key=lambda x: x.price)
        hard_sl = best.hard_sl
        t1_sl = t1_clusters[0].price if t1_clusters else entry_price + 30
        judas_min = t1_clusters[0].price if t1_clusters else entry_price + 20
        judas_max = t1_clusters[-1].price if t1_clusters else entry_price + 80
    else:
        t1_clusters = sorted([c for c in stop_clusters if c.price < entry_price], key=lambda x: x.price, reverse=True)
        hard_sl = best.hard_sl
        t1_sl = t1_clusters[0].price if t1_clusters else entry_price - 30
        judas_min = t1_clusters[0].price if t1_clusters else entry_price - 20
        judas_max = t1_clusters[-1].price if t1_clusters else entry_price - 80

    # Ensure T1-T2 gap min 30pt intraday / 50pt swing
    min_gap = 30 if trade_mode_str == "INTRADAY" else 50
    t1_t2_gap = abs(hard_sl - t1_sl)
    if t1_t2_gap < min_gap:
        t1_sl = hard_sl  # collapse to single tier

    # ââ Step 7: Position Sizing ââââââââââââââââââââââââââââââ
    targets = calculate_targets(entry_price, direction, trade_mode_str, all_bsl, all_ssl, hard_sl)
    position = calculate_position(
        entry=entry_price,
        hard_sl=hard_sl,
        part_b_target=targets["part_b"],
        entry_type=entry_type,
        trade_mode=trade_mode_str,
        account_size=account_size,
    )

    # ââ Step 8: 16-Gate Risk Assessment ââââââââââââââââââââââ
    phase_confirmed = primary_phase.get("phase") in ("A", "B", "C", "D")
    killzone_ok = in_killzone if trade_mode_str == "INTRADAY" else True

    gate_ctx = {
        "dol_identified":          dol_price is not None,
        "fvg_toward_dol":          best.fvg.direction == ("bullish" if direction == "buy" else "bearish"),
        "phase_b_confirmed":       entry_type == "PHASE_B",
        "three_candle_avail":      True,   # pipeline fires at candle close
        "fvg_score_ok":            best.qualifies,
        "session_weekly_aligned":  session_bias == macro_bias or macro_bias == "ranging",
        "rr_ok":                   best.rr_passes,
        "ma200_ok":                _check_ma200(df_1d, direction, current_price),
        "no_news_conflict":        not extra_context.get("news_within_2h", False),
        "stop_hunt_assessed":      True,
        "phase_confirmed":         phase_confirmed,
        "killzone_ok":             killzone_ok,
        "geo_stable":              not extra_context.get("ceasefire_risk", False),
        "combined_risk_ok":        position["risk_pct"] <= config.MAX_COMBINED_RISK,
        "bsl_ssl_mapped":          len(stop_clusters) > 0,
        "phase_d_size_ok":         True if entry_type == "PHASE_B" else (position["risk_pct"] <= 0.01),
        "rr_part_b":               best.rr_part_b,
    }

    gates_passed, gate_results, verdict = run_risk_gates(gate_ctx)
    log.info(f"Gates: {gates_passed}/16 | Verdict: {verdict}")

    # ââ Build Signal Dict âââââââââââââââââââââââââââââââââââââ
    signal = {
        "strategy_id":   1,
        "symbol":        config.SYMBOL,
        "direction":     direction.upper(),
        "mode":          mode if mode != "PENDING" else trade_mode_str,
        "entry_type":    entry_type,
        "phase_swing":   swing_phase.get("phase", "UNKNOWN"),
        "phase_intraday":intraday_phase.get("phase", "UNKNOWN"),
        "entry_zone_low": round(best.fvg.zone_low, 2),
        "entry_zone_high":round(best.fvg.zone_high, 2),
        "entry_tf":      best.fvg.timeframe,
        "stop_loss_t1":  round(t1_sl, 2),
        "stop_loss_t2":  round(hard_sl, 2),
        "sl_distance_pts": position["sl_distance_pts"],
        "part_a_target": targets["part_a"],
        "part_b_target": targets["part_b"],
        "part_c_target": targets["part_c"],
        "rr_part_b":     best.rr_part_b,
        "fvg_score":     best.score,
        "gates_passed":  gates_passed,
        "verdict":       verdict,
        "lots":          position["lots"],
        "risk_dollars":  position["risk_dollars"],
        "judas_min":     round(judas_min, 2),
        "judas_max":     round(judas_max, 2),
        "macro_bias":    macro_bias.upper(),
        "session_bias":  session_bias.upper(),
        "dol_primary":   dol_price,
        "dol_secondary": None,
        "fvg_zone_low":  round(best.fvg.zone_low, 2),
        "fvg_zone_high": round(best.fvg.zone_high, 2),
        "fvg_ce":        round(best.fvg.ce, 2),
        "raw_analysis": {
            "swing_phase":     swing_phase,
            "intraday_phase":  intraday_phase,
            "fvg_breakdown":   best.breakdown,
            "gate_results":    [{"id": g.gate_id, "label": g.label, "passed": g.passed} for g in gate_results],
            "stop_clusters":   [{"price": c.price, "type": c.level_type, "density": c.density, "source": c.source}
                                 for c in stop_clusters[:10]],
        },
    }

    return signal


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Helper Functions
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _phase_to_direction(phase_info: dict) -> Optional[str]:
    """
    Infer trade direction from phase bias.
    Phase B bearish = SELL. Phase B bullish = BUY.
    """
    bias = phase_info.get("bias", "ranging")
    evidence = " ".join(phase_info.get("evidence", []))

    if "bearish" in evidence.lower() or bias == "bearish":
        return "sell"
    elif "bullish" in evidence.lower() or bias == "bullish":
        return "buy"
    return None


def _current_session_bias(df_1h: pd.DataFrame) -> str:
    """
    Session open bias: compare today's open to prior H/L midpoint.
    """
    if df_1h.empty or len(df_1h) < 10:
        return "ranging"

    yesterday = df_1h.iloc[-25:-1]  # ~24h ago
    if yesterday.empty:
        return "ranging"

    prev_h = yesterday["high"].max()
    prev_l = yesterday["low"].min()
    prev_mid = (prev_h + prev_l) / 2
    today_open = float(df_1h.iloc[-1]["open"])

    if today_open > prev_mid:
        return "bullish"
    elif today_open < prev_mid:
        return "bearish"
    return "ranging"


def _weekly_bias(df_1d: pd.DataFrame) -> str:
    """
    Weekly bias: is last week's close in the upper, middle, or lower quartile?
    """
    if df_1d.empty or len(df_1d) < 5:
        return "ranging"

    last_week = df_1d.iloc[-5:]
    week_h = last_week["high"].max()
    week_l = last_week["low"].min()
    week_close = float(last_week.iloc[-1]["close"])
    week_range = week_h - week_l

    if week_range == 0:
        return "ranging"

    position = (week_close - week_l) / week_range

    if position >= 0.75:
        return "bullish"
    elif position <= 0.25:
        return "bearish"
    return "ranging"


def _check_ote(price: float, ssl: list, bsl: list, direction: str) -> bool:
    """
    Check if price is in the OTE zone (61.8%â79% Fibonacci retracement).
    Simplified: check if price is between 61.8% and 79% of the recent swing range.
    """
    if direction == "buy" and ssl and bsl:
        relevant_ssl = [l for l in ssl if l.price < price]
        relevant_bsl = [l for l in bsl if l.price > price]
        if relevant_ssl and relevant_bsl:
            low = min(relevant_ssl, key=lambda x: x.price).price
            high = max(relevant_bsl, key=lambda x: x.price).price
            rng = high - low
            if rng > 0:
                pos = (price - low) / rng
                return 0.618 <= pos <= 0.79
    return False


def _check_ma200(df_1d: pd.DataFrame, direction: str, current_price: float) -> bool:
    """
    Check if current price is on the correct side of the 200-day MA.
    Buy: price > MA200. Sell: price < MA200.
    """
    if df_1d.empty or len(df_1d) < 200:
        return True  # benefit of doubt if insufficient data

    ma200 = df_1d["close"].iloc[-200:].mean()

    if direction == "buy":
        return current_price > ma200
    else:
        return current_price < ma200
