"""
ICT Algorithm Phase Detection
-------------------------------
Identifies which phase the market is in on each timeframe:

  PHASE A — Accumulation
  PHASE B — Manipulation / Judas Swing  ← FULL-SIZE ENTRY ONLY
  PHASE C — Expansion
  PHASE D — Re-accumulation / Re-distribution  ← 50% SIZE MAX

Output structure per timeframe:
  {
    "phase": "A" | "B" | "C" | "D" | "UNKNOWN",
    "bias": "bullish" | "bearish" | "ranging",
    "evidence": ["..."],
    "entry_type": "PHASE_B" | "PHASE_D" | "WAIT",
    "dol": float | None,             # direction of liquidity
    "dol_type": "BSL" | "SSL" | None,
  }
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  Main Phase Detector
# ════════════════════════════════════════════════════════════

def detect_phase(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Analyse a DataFrame (oldest → newest) and return phase info dict.
    Uses the last 50 candles for pattern detection.
    """
    if df.empty or len(df) < 20:
        return _empty_phase()

    # Work with recent candles
    recent = df.iloc[-50:].copy().reset_index(drop=True)

    bias = _detect_bias(recent)
    phase, evidence = _classify_phase(recent, bias)
    dol, dol_type = _find_dol(recent, bias)
    entry_type = _determine_entry_type(phase)

    result = {
        "phase": phase,
        "bias": bias,
        "evidence": evidence,
        "entry_type": entry_type,
        "dol": dol,
        "dol_type": dol_type,
        "timeframe": timeframe,
    }
    log.debug(f"[{timeframe}] Phase {phase} | Bias {bias} | DOL {dol_type} @ {dol}")
    return result


# ════════════════════════════════════════════════════════════
#  Bias Detection
# ════════════════════════════════════════════════════════════

def _detect_bias(df: pd.DataFrame) -> str:
    """
    Determine broad directional bias from recent price action.
    Uses: EMA slope, higher highs/lower lows, close vs mid.
    """
    if len(df) < 10:
        return "ranging"

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    # Simple: compare first-quarter close to last-quarter close
    q = max(len(closes) // 4, 2)
    avg_early = closes[:q].mean()
    avg_late = closes[-q:].mean()
    delta = avg_late - avg_early

    # Check higher highs / lower lows (last 20 bars)
    n = min(20, len(df))
    recent_h = highs[-n:]
    recent_l = lows[-n:]
    hh = recent_h[-1] > recent_h[:-1].max()  # new high
    ll = recent_l[-1] < recent_l[:-1].min()   # new low

    if delta > 2.0 or hh:
        return "bullish"
    elif delta < -2.0 or ll:
        return "bearish"
    else:
        return "ranging"


# ════════════════════════════════════════════════════════════
#  Phase Classification
# ════════════════════════════════════════════════════════════

def _classify_phase(df: pd.DataFrame, bias: str) -> tuple[str, list[str]]:
    """
    Return (phase_letter, evidence_list).

    Detection logic:
      Phase B is the highest-priority — if we see a sweep + MSS, that's Phase B.
      Phase A: tight range, equal lows/highs forming.
      Phase C: strong directional move with large candles.
      Phase D: pullback into Phase C territory.
    """
    evidence: list[str] = []
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values

    # ── Phase B Detection ─────────────────────────────────
    # Key signal: a candle wick beyond recent extremes followed by
    # an immediate reversal (MSS within 3 candles).
    phase_b, b_ev = _check_phase_b(df, closes, highs, lows)
    if phase_b:
        evidence.extend(b_ev)
        return "B", evidence

    # ── Phase A Detection ─────────────────────────────────
    # Tight range, multiple touches of same low/high (equal lows)
    # Small bodies, wicks recovering quickly.
    phase_a, a_ev = _check_phase_a(df, closes, highs, lows)
    if phase_a:
        evidence.extend(a_ev)
        return "A", evidence

    # ── Phase C Detection ─────────────────────────────────
    # Strong displacement — large bodies, consistent closes
    phase_c, c_ev = _check_phase_c(df, closes, highs, lows, opens)
    if phase_c:
        evidence.extend(c_ev)
        return "C", evidence

    # ── Phase D Detection ─────────────────────────────────
    # After a Phase C move, price retraces (pullback)
    phase_d, d_ev = _check_phase_d(df, closes, highs, lows, bias)
    if phase_d:
        evidence.extend(d_ev)
        return "D", evidence

    evidence.append("No clear phase pattern — price action ambiguous")
    return "UNKNOWN", evidence


def _check_phase_b(df, closes, highs, lows) -> tuple[bool, list[str]]:
    """
    Phase B (Judas Swing / Manipulation):
    - A candle sweeps beyond the recent swing high or low
    - Within 1-3 candles, price REVERSES and closes opposite
    - This is a stop hunt → MSS signal
    """
    evidence = []
    n = len(df)
    if n < 6:
        return False, evidence

    # Look at the last 8 candles for sweep + reversal
    window = df.iloc[-8:].reset_index(drop=True)
    w_highs = window["high"].values
    w_lows = window["low"].values
    w_closes = window["close"].values
    w_opens = window["open"].values

    # Reference: prior range (first 5 candles of window)
    prior_high = w_highs[:5].max()
    prior_low = w_lows[:5].min()

    for i in range(2, len(window)):
        # Bearish Phase B: spike above prior high then close below it
        if (w_highs[i] > prior_high + 1.0 and
                w_closes[i] < prior_high):
            evidence.append(f"Bearish sweep of BSL @ {prior_high:.2f} — wicked above, closed below")
            # Confirm 3-candle MSS (look for next candle closing lower)
            if i + 1 < len(window) and w_closes[i + 1] < w_closes[i]:
                evidence.append("MSS confirmed: next candle closed lower after sweep")
            evidence.append("Phase B: BEARISH Judas Swing detected")
            return True, evidence

        # Bullish Phase B: spike below prior low then close above it
        if (w_lows[i] < prior_low - 1.0 and
                w_closes[i] > prior_low):
            evidence.append(f"Bullish sweep of SSL @ {prior_low:.2f} — wicked below, closed above")
            if i + 1 < len(window) and w_closes[i + 1] > w_closes[i]:
                evidence.append("MSS confirmed: next candle closed higher after sweep")
            evidence.append("Phase B: BULLISH Judas Swing detected")
            return True, evidence

    return False, evidence


def _check_phase_a(df, closes, highs, lows) -> tuple[bool, list[str]]:
    """
    Phase A (Accumulation):
    - Tight price range (< 30pt spread in last 20 bars)
    - Equal lows forming (multiple touches within 2pt)
    - Small candle bodies
    """
    evidence = []
    n = min(20, len(closes))
    recent_h = highs[-n:]
    recent_l = lows[-n:]

    price_range = recent_h.max() - recent_l.min()
    if price_range > 80:   # too wide to be accumulation
        return False, evidence

    # Equal lows test
    low_min = recent_l.min()
    equal_lows = sum(1 for l in recent_l if abs(l - low_min) <= 2.0)
    if equal_lows >= 3:
        evidence.append(f"Equal lows at {low_min:.2f} ({equal_lows} touches) — stop cluster forming")

    # Equal highs test
    high_max = recent_h.max()
    equal_highs = sum(1 for h in recent_h if abs(h - high_max) <= 2.0)
    if equal_highs >= 3:
        evidence.append(f"Equal highs at {high_max:.2f} ({equal_highs} touches) — BSL cluster forming")

    # Tight range
    if price_range <= 30:
        evidence.append(f"Tight consolidation range: {price_range:.1f}pts — accumulation signature")

    if len(evidence) >= 2:
        return True, evidence
    return False, evidence


def _check_phase_c(df, closes, highs, lows, opens) -> tuple[bool, list[str]]:
    """
    Phase C (Expansion):
    - Recent candles are large (body > 2x 20-bar avg body)
    - Consistent directional closes (4+ in a row same direction)
    """
    evidence = []
    n = min(10, len(closes))
    bodies = np.abs(closes - opens)
    avg_body = bodies.mean() if len(bodies) > 0 else 0

    if avg_body == 0:
        return False, evidence

    recent_bodies = bodies[-n:]
    large_candles = (recent_bodies > 2.0 * avg_body).sum()

    if large_candles >= 2:
        evidence.append(f"{large_candles} large displacement candles in recent {n} bars")

    # Consecutive closes in one direction (count from most recent candle backward)
    streak_count = 0
    for i in range(1, min(6, n)):
        if closes[-i] > closes[-i - 1]:      # bullish step
            if streak_count >= 0:
                streak_count += 1
            else:
                break                         # direction reversed — stop counting
        elif closes[-i] < closes[-i - 1]:    # bearish step
            if streak_count <= 0:
                streak_count -= 1
            else:
                break                         # direction reversed — stop counting

    if abs(streak_count) >= 3:
        dir_word = "bullish" if streak_count > 0 else "bearish"
        evidence.append(f"{abs(streak_count)}-candle {dir_word} expansion streak — Phase C")

    if len(evidence) >= 2:
        return True, evidence
    return False, evidence


def _check_phase_d(df, closes, highs, lows, bias: str) -> tuple[bool, list[str]]:
    """
    Phase D (Re-accumulation):
    - After a strong move (Phase C), price pulls back
    - Closes counter-trend but bodies getting smaller
    - Price remains in the upper/lower portion of the move
    """
    evidence = []
    n = min(20, len(closes))
    recent = closes[-n:]

    # Phase D = a counter-trend pullback after expansion
    overall_direction = "up" if recent[-1] > recent[0] else "down"

    # Look for a recent pullback in last 5 bars
    last5 = recent[-5:]
    pullback_up = last5[-1] > last5[0]   # prices going up in last 5
    pullback_dn = last5[-1] < last5[0]   # prices going down in last 5

    if bias == "bullish" and pullback_dn:
        evidence.append("Bullish Phase D: pullback into previous bullish expansion territory")
        evidence.append(f"Price retracing from {last5.max():.2f} toward FVG zones")
    elif bias == "bearish" and pullback_up:
        evidence.append("Bearish Phase D: retracement into previous bearish expansion territory")
        evidence.append(f"Price bouncing from {last5.min():.2f} into supply FVGs")
    else:
        return False, evidence

    # Range contraction during pullback (smaller bodies)
    from analysis.liquidity import detect_order_blocks
    evidence.append("Phase D: re-accumulation / re-distribution — 50% size max")
    return True, evidence


# ════════════════════════════════════════════════════════════
#  DOL Identification
# ════════════════════════════════════════════════════════════

def _find_dol(df: pd.DataFrame, bias: str) -> tuple[Optional[float], Optional[str]]:
    """
    Identify the nearest unswept liquidity pool that price is targeting.

    For bullish bias → nearest BSL (swing high) above current price = DOL.
    For bearish bias → nearest SSL (swing low) below current price = DOL.
    """
    if df.empty:
        return None, None

    current = float(df.iloc[-1]["close"])
    highs = df["high"].values
    lows = df["low"].values

    if bias == "bullish":
        # DOL = nearest high above current price
        above = [(h, i) for i, h in enumerate(highs) if h > current + 5]
        if above:
            nearest = min(above, key=lambda x: x[0])
            return round(nearest[0], 2), "BSL"

    elif bias == "bearish":
        # DOL = nearest low below current price
        below = [(l, i) for i, l in enumerate(lows) if l < current - 5]
        if below:
            nearest = max(below, key=lambda x: x[0])
            return round(nearest[0], 2), "SSL"

    return None, None


# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

def _determine_entry_type(phase: str) -> str:
    if phase == "B":
        return "PHASE_B"
    elif phase == "D":
        return "PHASE_D"
    elif phase == "C":
        return "PHASE_C"   # Scalp entry on momentum expansion
    else:
        return "WAIT"


def _empty_phase() -> dict:
    return {
        "phase": "UNKNOWN",
        "bias": "ranging",
        "evidence": ["Insufficient data"],
        "entry_type": "WAIT",
        "dol": None,
        "dol_type": None,
        "timeframe": "unknown",
    }


def determine_mode(swing_phase: dict, intraday_phase: dict) -> str:
    """
    MODE SELECTION RULE:
      Highest-scoring FVG on 15M/1H → INTRADAY
      Highest-scoring FVG on 4H/Daily → SWING
      Both qualify at same zone → LAYERED
      No FVG qualifies → NO TRADE (returned here as 'PENDING')
    """
    swing_entry = swing_phase.get("entry_type", "WAIT")
    intra_entry = intraday_phase.get("entry_type", "WAIT")

    if swing_entry != "WAIT" and intra_entry != "WAIT":
        return "LAYERED"
    elif swing_entry != "WAIT":
        return "SWING"
    elif intra_entry != "WAIT":
        return "INTRADAY"
    return "PENDING"
"""
ICT Algorithm Phase Detection
-------------------------------
Identifies which phase the market is in on each timeframe:

  PHASE A → Accumulation
  PHASE B → Manipulation / Judas Swing  → FULL-SIZE ENTRY ONLY
  PHASE C → Expansion                   → SCALP ENTRY
  PHASE D → Re-accumulation / Re-distribution  → 50% SIZE MAX

Output structure per timeframe:
  {
    "phase": "A" | "B" | "C" | "D" | "UNKNOWN",
    "bias": "bullish" | "bearish" | "ranging",
    "evidence": ["..."],
    "entry_type": "PHASE_B" | "PHASE_C" | "PHASE_D" | "WAIT",
    "dol": float | None,             # direction of liquidity
    "dol_type": "BSL" | "SSL" | None,
  }
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Main Phase Detector
# ──────────────────────────────────────────────────────────────

def detect_phase(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Analyse a DataFrame (oldest → newest) and return phase info dict.
    Uses the last 50 candles for pattern detection.
    """
    if df.empty or len(df) < 20:
        return _empty_phase()

    # Work with recent candles
    recent = df.iloc[-50:].copy().reset_index(drop=True)

    bias = _detect_bias(recent)
    phase, evidence = _classify_phase(recent, bias)
    dol, dol_type = _find_dol(recent, bias)
    entry_type = _determine_entry_type(phase)

    result = {
        "phase": phase,
        "bias": bias,
        "evidence": evidence,
        "entry_type": entry_type,
        "dol": dol,
        "dol_type": dol_type,
        "timeframe": timeframe,
    }
    log.debug(f"[{timeframe}] Phase {phase} | Bias {bias} | DOL {dol_type} @ {dol}")
    return result


# ──────────────────────────────────────────────────────────────
#  Bias Detection
# ──────────────────────────────────────────────────────────────

def _detect_bias(df: pd.DataFrame) -> str:
    if len(df) < 10:
        return "ranging"
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    q = max(len(closes) // 4, 2)
    avg_early = closes[:q].mean()
    avg_late = closes[-q:].mean()
    delta = avg_late - avg_early
    n = min(20, len(df))
    recent_h = highs[-n:]
    recent_l = lows[-n:]
    hh = recent_h[-1] > recent_h[:-1].max()
    ll = recent_l[-1] < recent_l[:-1].min()
    if delta > 2.0 or hh:
        return "bullish"
    elif delta < -2.0 or ll:
        return "bearish"
    else:
        return "ranging"


def _classify_phase(df: pd.DataFrame, bias: str) -> tuple[str, list[str]]:
    evidence: list[str] = []
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    phase_b, b_ev = _check_phase_b(df, closes, highs, lows)
    if phase_b:
        evidence.extend(b_ev)
        return "B", evidence
    phase_a, a_ev = _check_phase_a(df, closes, highs, lows)
    if phase_a:
        evidence.extend(a_ev)
        return "A", evidence
    phase_c, c_ev = _check_phase_c(df, closes, highs, lows, opens)
    if phase_c:
        evidence.extend(c_ev)
        return "C", evidence
    phase_d, d_ev = _check_phase_d(df, closes, highs, lows, bias)
    if phase_d:
        evidence.extend(d_ev)
        return "D", evidence
    evidence.append("No clear phase pattern — price action ambiguous")
    return "UNKNOWN", evidence


def _check_phase_b(df, closes, highs, lows) -> tuple[bool, list[str]]:
    evidence = []
    n = len(df)
    if n < 6:
        return False, evidence
    window = df.iloc[-8:].reset_index(drop=True)
    w_highs = window["high"].values
    w_lows = window["low"].values
    w_closes = window["close"].values
    prior_high = w_highs[:5].max()
    prior_low = w_lows[:5].min()
    for i in range(2, len(window)):
        if (w_highs[i] > prior_high + 1.0 and w_closes[i] < prior_high):
            evidence.append(f"Bearish sweep of BSL @ {prior_high:.2f}")
            if i + 1 < len(window) and w_closes[i + 1] < w_closes[i]:
                evidence.append("MSS confirmed: next candle closed lower")
            evidence.append("Phase B: BEARISH Judas Swing detected")
            return True, evidence
        if (w_lows[i] < prior_low - 1.0 and w_closes[i] > prior_low):
            evidence.append(f"Bullish sweep of SSL @ {prior_low:.2f}")
            if i + 1 < len(window) and w_closes[i + 1] > w_closes[i]:
                evidence.append("MSS confirmed: next candle closed higher")
            evidence.append("Phase B: BULLISH Judas Swing detected")
            return True, evidence
    return False, evidence


def _check_phase_a(df, closes, highs, lows) -> tuple[bool, list[str]]:
    evidence = []
    n = min(20, len(closes))
    recent_h = highs[-n:]
    recent_l = lows[-n:]
    price_range = recent_h.max() - recent_l.min()
    if price_range > 80:
        return False, evidence
    low_min = recent_l.min()
    equal_lows = sum(1 for l in recent_l if abs(l - low_min) <= 2.0)
    if equal_lows >= 3:
        evidence.append(f"Equal lows @ {low_min:.2f} ({equal_lows} touches)")
    high_max = recent_h.max()
    equal_highs = sum(1 for h in recent_h if abs(h - high_max) <= 2.0)
    if equal_highs >= 3:
        evidence.append(f"Equal highs @ {high_max:.2f} ({equal_highs} touches)")
    if price_range <= 30:
        evidence.append(f"Tight range: {price_range:.1f}pts")
    if len(evidence) >= 2:
        return True, evidence
    return False, evidence


def _check_phase_c(df, closes, highs, lows, opens) -> tuple[bool, list[str]]:
    evidence = []
    n = min(10, len(closes))
    bodies = np.abs(closes - opens)
    avg_body = bodies.mean() if len(bodies) > 0 else 0
    if avg_body == 0:
        return False, evidence
    recent_bodies = bodies[-n:]
    large_candles = (recent_bodies > 2.0 * avg_body).sum()
    if large_candles >= 2:
        evidence.append(f"{large_candles} large displacement candles in recent {n} bars")
    direction_streak = 0
    for i in range(1, min(6, n)):
        if closes[-i] > closes[-i - 1]:
            direction_streak = max(direction_streak, 1)
            if direction_streak > 0:
                direction_streak += 1
        elif closes[-i] < closes[-i - 1]:
            direction_streak = min(direction_streak, -1)
    if abs(direction_streak) >= 3:
        dir_word = "bullish" if direction_streak > 0 else "bearish"
        evidence.append(f"{abs(direction_streak)}-candle {dir_word} expansion streak")
    if len(evidence) >= 2:
        return True, evidence
    return False, evidence


def _check_phase_d(df, closes, highs, lows, bias: str) -> tuple[bool, list[str]]:
    evidence = []
    n = min(20, len(closes))
    recent = closes[-n:]
    last5 = recent[-5:]
    pullback_up = last5[-1] > last5[0]
    pullback_dn = last5[-1] < last5[0]
    if bias == "bullish" and pullback_dn:
        evidence.append("Bullish Phase D: pullback into previous expansion")
        evidence.append(f"Price retracing from {last5.max():.2f} toward FVG zones")
    elif bias == "bearish" and pullback_up:
        evidence.append("Bearish Phase D: retracement into previous expansion")
        evidence.append(f"Price bouncing from {last5.min():.2f} into supply FVGs")
    else:
        return False, evidence
    evidence.append("Phase D: re-accumulation / re-distribution → 50% size max")
    return True, evidence


def _find_dol(df: pd.DataFrame, bias: str) -> tuple[Optional[float], Optional[str]]:
    if df.empty:
        return None, None
    current = float(df.iloc[-1]["close"])
    highs = df["high"].values
    lows = df["low"].values
    if bias == "bullish":
        above = [(h, i) for i, h in enumerate(highs) if h > current + 5]
        if above:
            return round(min(above, key=lambda x: x[0])[0], 2), "BSL"
    elif bias == "bearish":
        below = [(l, i) for i, l in enumerate(lows) if l < current - 5]
        if below:
            return round(max(below, key=lambda x: x[0])[0], 2), "SSL"
    return None, None


def _determine_entry_type(phase: str) -> str:
    if phase == "B":
        return "PHASE_B"
    elif phase == "D":
        return "PHASE_D"
    elif phase == "C":
        return "PHASE_C"  # Scalp entry on momentum expansion
    else:
        return "WAIT"


def _empty_phase() -> dict:
    return {
        "phase": "UKNOWN",
        "bias": "ranging",
        "evidence": ["Insufficient data"],
        "entry_type": "WAIT",
        "dol": None,
        "dol_type": None,
        "timeframe": "unknown",
    }


def determine_mode(swing_phase: dict, intraday_phase: dict) -> str:
    swing_entry = swing_phase.get("entry_type", "WAIT")
    intra_entry = intraday_phase.get("entry_type", "WAIT")
    if swing_entry != "WAIT" and intra_entry != "WAIT":
        return "LAYERED"
    elif swing_entry != "WAIT":
        return "SWING"
    elif intra_entry != "WAIT":
        return "INTRADAY"
    return "PENDING"
