"""
ICT FVG Scoring System
-----------------------
Implements the full scoring matrix from Steps 4B / 4C / 4D
including all additions (C1âC15) and deductions (D1âD14).

Also implements:
  â¢ The 16-Gate Risk Assessment (Step 8)
  â¢ Position sizing (Step 7)
  â¢ Trade mode verdict
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import config
from analysis.liquidity import FVG, LiquidityLevel

log = logging.getLogger(__name__)


@dataclass
class ScoredFVG:
    fvg: FVG
    score: int
    additions: dict = field(default_factory=dict)
    deductions: dict = field(default_factory=dict)
    breakdown: list[str] = field(default_factory=list)
    qualifies: bool = False
    track: str = ""
    hard_sl: float = 0.0
    sl_distance: float = 0.0
    rr_part_b: float = 0.0
    rr_passes: bool = False


@dataclass
class GateResult:
    gate_id: int
    label: str
    passed: bool
    reason: str = ""


def score_fvg(fvg: FVG, context: dict) -> ScoredFVG:
    scored = ScoredFVG(fvg=fvg, score=0)
    tf = fvg.timeframe
    if tf in ("4h", "1day"):
        track = "SWING"
        threshold = config.SWING_SCORE_THRESHOLD
    else:
        track = "INTRADAY"
        threshold = config.INTRADAY_SCORE_THRESHOLD
    scored.track = track
    macro_bias = context.get("macro_bias", "ranging")
    fvg_direction = fvg.direction
    fvg_matches_macro = (
        (fvg_direction == "bullish" and macro_bias == "bullish") or
        (fvg_direction == "bearish" and macro_bias == "bearish")
    )
    additions = {}
    session_bias = context.get("session_bias", "ranging")
    if track == "INTRADAY":
        session_matches = (
            (fvg_direction == "bullish" and session_bias == "bullish") or
            (fvg_direction == "bearish" and session_bias == "bearish")
        )
        if session_matches:
            additions["C1_session_bias"] = 2
    else:
        if fvg_matches_macro:
            additions["C1_macro_bias"] = 2
    if context.get("has_ob_overlap", False):
        additions["C2_ob_overlap"] = 2
    if context.get("ce_at_range_midpoint", False):
        additions["C3_ce_midpoint"] = 1
    if context.get("higher_tf_confirms", False):
        additions["C4_higher_tf"] = 1
    if context.get("at_itl_ith", False):
        additions["C5_itl_ith"] = 1
    if context.get("inside_ote", False):
        additions["C6_ote"] = 1
    if fvg.formed_in_killzone:
        additions["C7_killzone"] = 1
    if fvg.fresh:
        additions["C8_fresh"] = 1
    entry_type = context.get("entry_type", "WAIT")
    if fvg.formed_phase_b or entry_type == "PHASE_B":
        additions["C9_phase_b_formed"] = 2
    dol_direction = context.get("dol_direction", "AGAINST")
    if dol_direction == "WITH":
        additions["C10_toward_dol"] = 1
    if context.get("itl_ith_swept_to_create", False):
        additions["C11_swept_to_create"] = 1
    weekly_bias = context.get("weekly_bias", "ranging")
    weekly_matches = (
        (fvg_direction == "bullish" and weekly_bias == "bullish") or
        (fvg_direction == "bearish" and weekly_bias == "bearish")
    )
    if weekly_matches:
        additions["C12_weekly_structure"] = 1
    if track == "SWING" and not context.get("ceasefire_risk", False):
        additions["C13_no_geo_premium"] = 1
    if context.get("hard_sl_clears_clusters", False):
        additions["C14_sl_beyond_clusters"] = 2
    if entry_type == "PHASE_B":
        additions["C15_phase_b_entry"] = 2
    deductions = {}
    if not fvg_matches_macro and macro_bias != "ranging":
        deductions["D1_opposes_macro"] = -3
    if fvg.mitigated:
        deductions["D2_mitigated"] = -1
    if context.get("between_opposing_fvgs", False):
        deductions["D3_trapped"] = -1
    if context.get("news_within_2h", False):
        deductions["D4_news_2h"] = -2
    if tf not in ("15min", "1h", "4h", "1day"):
        deductions["D5_low_tf"] = -2
    if context.get("fvg_edge_at_stop_cluster", False):
        deductions["D6_edge_at_cluster"] = -1
    phase = context.get("phase", "UNKNOWN")
    if phase == "UNKNOWN":
        deductions["D7_phase_ambiguous"] = -2
    if not context.get("macro_algorithm_aligned", True):
        deductions["D8_macro_conflicted"] = -2
    if dol_direction == "AGAINST":
        deductions["D9_away_from_dol"] = -5
    if not weekly_matches and weekly_bias != "ranging":
        deductions["D10_weekly_opposes"] = -2
    if track == "SWING" and context.get("ceasefire_risk", False):
        deductions["D11_ceasefire"] = -3
    if track == "SWING" and context.get("nfp_fomc_within_48h", False):
        deductions["D12_nfp_48h"] = -2
    if entry_type == "PHASE_D":
        deductions["D13_phase_d"] = -2
    if not context.get("rr_check_passes", True):
        deductions["D14_rr_fails"] = -5
    total_add = sum(additions.values())
    total_ded = sum(deductions.values())
    score = total_add + total_ded
    scored.score = score
    scored.additions = additions
    scored.deductions = deductions
    scored.qualifies = score >= threshold
    breakdown = [f"Track: {track} | Threshold: {threshold} | Score: {score}"]
    for k, v in additions.items():
        breakdown.append(f"  +{v} {k}")
    for k, v in deductions.items():
        breakdown.append(f"   {v} {k}")
    breakdown.append(f"  â QUALIFIES: {scored.qualifies}")
    scored.breakdown = breakdown
    log.debug(f"FVG score [{tf}] {fvg.direction}: {score}")
    return scored


def rank_fvgs(scored_fvgs: list[ScoredFVG]) -> list[ScoredFVG]:
    return sorted(scored_fvgs, key=lambda s: s.score, reverse=True)


def run_risk_gates(context: dict) -> tuple[int, list[GateResult], str]:
    gates_config = [
        (1,  "DOL clearly identified?",                        "dol_identified"),
        (2,  "FVG points TOWARD the DOL?",                     "fvg_toward_dol"),
        (3,  "Phase B sweep confirmed?",                       "phase_b_confirmed"),
        (4,  "3-candle confirmation available?",               "three_candle_avail"),
        (5,  "FVG score: swing 9+ / intraday 8+?",             "fvg_score_ok"),
        (6,  "Session/weekly bias aligned?",                    "session_weekly_aligned"),
        (7,  "Part B R:R â¥ 3:1 intraday / â¥ 5:1 swing?",       "rr_ok"),
        (8,  "200-day MA on correct side?",                     "ma200_ok"),
        (9,  "No NFP/FOMC/CPI within 4h (intraday) / 48h (swing)?", "no_news_conflict"),
        (10, "Stop hunt protection assessed?",                  "stop_hunt_assessed"),
        (11, "Algorithm phase CONFIRMED?",                      "phase_confirmed"),
        (12, "Within Kill Zone / 4H candle available?",         "killzone_ok"),
        (13, "Geopolitical premium stable?",                    "geo_stable"),
        (14, "Combined risk â¤ 2.5%?",                         "combined_risk_ok"),
        (15, "ALL BSL/SSL clusters mapped + hard SL beyond farthest?", "bsl_ssl_mapped"),
        (16, "Phase D entry: size reduced to 50%?",             "phase_d_size_ok"),
    ]
    results: list[GateResult] = []
    passed = 0
    for gate_id, label, key in gates_config:
        val = context.get(key, False)
        results.append(GateResult(gate_id=gate_id, label=label, passed=bool(val)))
        if val:
            passed += 1
    g15_ok = context.get("bsl_ssl_mapped", False)
    g16_ok = context.get("phase_d_size_ok", True)
    if not g15_ok or not g16_ok:
        return passed, results, "NO_TRADE"
    if passed == 16:
        verdict = "EXECUTE_FULL"
    elif passed == 15:
        verdict = "EXECUTE_REDUCE_10"
    elif passed == 14:
        verdict = "EXECUTE_REDUCE_25"
    elif passed == 13:
        verdict = "EXECUTE_REDUCE_50"
    elif passed == 12:
        rr = context.get("rr_part_b", 0.0)
        verdict = "BORDERLINE" if rr > 5.0 else "NO_TRADE"
    else:
        verdict = "NO_TRADE"
    return passed, results, verdict


def calculate_position(
    entry: float,
    hard_sl: float,
    part_b_target: float,
    entry_type: str,
    trade_mode: str,
    account_size: float = config.ACCOUNT_SIZE,
) -> dict:
    if entry_type == "PHASE_B":
        risk_pct = min(config.MAX_RISK_PHASE_B, 0.02)
    else:
        risk_pct = min(config.MAX_RISK_PHASE_D, 0.01)
    risk_dollars = account_size * risk_pct
    sl_distance = abs(entry - hard_sl)
    if sl_distance == 0:
        return {"lots": 0, "risk_dollars": 0, "rr_part_b": 0, "error": "Zero SL distance"}
    lots = risk_dollars / sl_distance
    lots = round(max(lots, 0.01), 2)
    part_b_distance = abs(part_b_target - entry)
    rr_part_b = round(part_b_distance / sl_distance, 2) if sl_distance > 0 else 0.0
    return {
        "lots": lots,
        "risk_dollars": round(risk_dollars, 2),
        "risk_pct": risk_pct,
        "sl_distance_pts": round(sl_distance, 2),
        "rr_part_b": rr_part_b,
    }


def calculate_targets(
    entry: float,
    direction: str,
    trade_mode: str,
    bsl_levels: list,
    ssl_levels: list,
    hard_sl: float,
) -> dict:
    sl_dist = abs(entry - hard_sl)
    if direction == "buy":
        sorted_bsl = sorted([l for l in bsl_levels if l.price > entry], key=lambda x: x.price)
        part_a = entry + sl_dist * 1.5
        part_b = sorted_bsl[0].price if sorted_bsl else entry + sl_dist * 3.0
        part_c = sorted_bsl[1].price if len(sorted_bsl) > 1 else entry + sl_dist * 6.0
    else:
        sorted_ssl = sorted([l for l in ssl_levels if l.price < entry], key=lambda x: x.price, reverse=True)
        part_a = entry - sl_dist * 1.5
        part_b = sorted_ssl[0].price if sorted_ssl else entry - sl_dist * 3.0
        part_c = sorted_ssl[1].price if len(sorted_ssl) > 1 else entry - sl_dist * 6.0
    return {
        "part_a": round(part_a, 2),
        "part_b": round(part_b, 2),
        "part_c": round(part_c, 2),
    }
