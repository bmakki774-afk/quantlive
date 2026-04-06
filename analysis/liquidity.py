"""
ICT Liquidity Analysis Engine
------------------------------
Detects the building blocks of the ICT methodology:

  â¢ Fair Value Gaps (FVGs) â bullish and bearish
  â¢ Swing Highs / Swing Lows (BSL / SSL)
  â¢ Equal Highs / Equal Lows (high-density stop clusters)
  â¢ Round number levels
  â¢ Order Blocks (simplified â last opposing candle before FVG)
  â¢ Kill Zone detection (London / New York)
  â¢ BSL/SSL sweep detection (price crosses level and returns)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)

EQUAL_LEVEL_TOLERANCE = 0.5   # pts â two levels within this = "equal"
ROUND_NUMBER_GRID = 50.0       # XAU/USD round numbers every $50


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Data Classes
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@dataclass
class FVG:
    """Fair Value Gap (imbalance zone)."""
    direction: str          # 'bullish' or 'bearish'
    timeframe: str
    candle_index: int       # index of the middle (gap) candle
    candle_time: datetime
    zone_low: float
    zone_high: float
    ce: float               # Equilibrium / midpoint
    fresh: bool = True      # True if never been touched
    mitigated: bool = False
    formed_in_killzone: bool = False
    formed_phase_b: bool = False
    score: int = 0

    @property
    def zone_size(self) -> float:
        return self.zone_high - self.zone_low


@dataclass
class LiquidityLevel:
    """A stop cluster / liquidity pool."""
    price: float
    level_type: str     # 'BSL' (buy-side) or 'SSL' (sell-side)
    source: str         # 'swing_high', 'swing_low', 'equal_high', 'equal_low',
                        # 'round_number', 'fvg_edge', 'order_block'
    density: str        # 'light', 'moderate', 'heavy'
    timeframe: str
    swept: bool = False
    candle_time: Optional[datetime] = None


@dataclass
class OrderBlock:
    """Simplified Order Block (last opposing candle before a displacement move)."""
    direction: str          # 'bullish' or 'bearish'
    timeframe: str
    zone_low: float
    zone_high: float
    candle_time: datetime
    fresh: bool = True


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Core Analysis Functions
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def detect_fvgs(df: pd.DataFrame, timeframe: str) -> list[FVG]:
    """
    Scan candle DataFrame for bullish and bearish Fair Value Gaps.

    Bullish FVG: df.loc[i-2, 'high'] < df.loc[i, 'low']
      â gap between candle i-2 upper wick and candle i lower wick
      â zone = [candle[i-2].high, candle[i].low]

    Bearish FVG: df.loc[i-2, 'low'] > df.loc[i, 'high']
      â zone = [candle[i].high, candle[i-2].low]
    """
    fvgs: list[FVG] = []
    if df.empty or len(df) < 3:
        return fvgs

    current_hour = datetime.now(timezone.utc).hour
    in_killzone = _in_killzone(current_hour)

    for i in range(2, len(df)):
        c0 = df.iloc[i - 2]  # two bars ago
        c2 = df.iloc[i]      # current bar

        # Bullish FVG
        if c0["high"] < c2["low"]:
            zone_low = float(c0["high"])
            zone_high = float(c2["low"])
            ce = (zone_low + zone_high) / 2
            # Check if already mitigated (price re-entered the gap)
            mitigated = _is_fvg_mitigated(df, i, zone_low, zone_high, "bullish")
            fvg = FVG(
                direction="bullish",
                timeframe=timeframe,
                candle_index=i,
                candle_time=c2["datetime"].to_pydatetime(),
                zone_low=zone_low,
                zone_high=zone_high,
                ce=ce,
                fresh=not mitigated,
                mitigated=mitigated,
                formed_in_killzone=in_killzone,
            )
            fvgs.append(fvg)

        # Bearish FVG
        elif c0["low"] > c2["high"]:
            zone_high = float(c0["low"])
            zone_low = float(c2["high"])
            ce = (zone_low + zone_high) / 2
            mitigated = _is_fvg_mitigated(df, i, zone_low, zone_high, "bearish")
            fvg = FVG(
                direction="bearish",
                timeframe=timeframe,
                candle_index=i,
                candle_time=c2["datetime"].to_pydatetime(),
                zone_low=zone_low,
                zone_high=zone_high,
                ce=ce,
                fresh=not mitigated,
                mitigated=mitigated,
                formed_in_killzone=in_killzone,
            )
            fvgs.append(fvg)

    log.debug(f"[{timeframe}] Found {len(fvgs)} FVGs ({sum(1 for f in fvgs if not f.mitigated)} unmitigated)")
    return fvgs


def detect_swing_levels(df: pd.DataFrame, timeframe: str, lookback: int = None) -> tuple[list[LiquidityLevel], list[LiquidityLevel]]:
    """
    Detect swing highs (BSL) and swing lows (SSL).
    Returns (bsl_list, ssl_list).

    A swing high requires `lookback` bars on each side to be lower.
    A swing low requires `lookback` bars on each side to be higher.
    """
    if lookback is None:
        lookback = config.SWING_LOOKBACK

    bsl: list[LiquidityLevel] = []
    ssl: list[LiquidityLevel] = []

    if df.empty or len(df) < (2 * lookback + 1):
        return bsl, ssl

    highs = df["high"].values
    lows = df["low"].values

    for i in range(lookback, len(df) - lookback):
        ts = df.iloc[i]["datetime"].to_pydatetime()

        # Swing High (BSL)
        if all(highs[i] > highs[i - j] for j in range(1, lookback + 1)) and \
           all(highs[i] > highs[i + j] for j in range(1, lookback + 1)):
            density = _estimate_density(df, highs[i], "high")
            bsl.append(LiquidityLevel(
                price=float(highs[i]),
                level_type="BSL",
                source="swing_high",
                density=density,
                timeframe=timeframe,
                candle_time=ts,
            ))

        # Swing Low (SSL)
        if all(lows[i] < lows[i - j] for j in range(1, lookback + 1)) and \
           all(lows[i] < lows[i + j] for j in range(1, lookback + 1)):
            density = _estimate_density(df, lows[i], "low")
            ssl.append(LiquidityLevel(
                price=float(lows[i]),
                level_type="SSL",
                source="swing_low",
                density=density,
                timeframe=timeframe,
                candle_time=ts,
            ))

    log.debug(f"[{timeframe}] {len(bsl)} BSL levels, {len(ssl)} SSL levels")
    return bsl, ssl


def detect_equal_levels(
    levels: list[LiquidityLevel],
    tolerance: float = EQUAL_LEVEL_TOLERANCE,
) -> list[LiquidityLevel]:
    """
    Group nearby levels into 'equal highs' or 'equal lows'.
    When 2+ BSL/SSL levels cluster within `tolerance`, upgrade density to 'heavy'.
    """
    if not levels:
        return levels

    result = []
    used = set()

    for i, lv in enumerate(levels):
        if i in used:
            continue
        cluster = [lv]
        for j, other in enumerate(levels):
            if j == i or j in used:
                continue
            if abs(lv.price - other.price) <= tolerance:
                cluster.append(other)
                used.add(j)

        # If clustered â upgrade to equal high/low with heavy density
        if len(cluster) > 1:
            avg_price = sum(c.price for c in cluster) / len(cluster)
            source = "equal_high" if lv.level_type == "BSL" else "equal_low"
            result.append(LiquidityLevel(
                price=avg_price,
                level_type=lv.level_type,
                source=source,
                density="heavy",
                timeframe=lv.timeframe,
                candle_time=lv.candle_time,
            ))
        else:
            result.append(lv)
        used.add(i)

    return result


def detect_round_numbers(
    price: float,
    search_range: float = 300.0,
    grid: float = ROUND_NUMBER_GRID,
) -> list[LiquidityLevel]:
    """
    Return round number levels within `search_range` of `price`.
    For gold: every $50 is a round number ($3,000, $3,050 â¦).
    """
    levels = []
    base = round(price / grid) * grid
    steps = int(search_range / grid) + 1

    for i in range(-steps, steps + 1):
        level = base + i * grid
        distance = abs(level - price)
        if distance <= search_range:
            level_type = "BSL" if level > price else "SSL"
            levels.append(LiquidityLevel(
                price=level,
                level_type=level_type,
                source="round_number",
                density="moderate",
                timeframe="all",
            ))
    return levels


def detect_order_blocks(df: pd.DataFrame, timeframe: str) -> list[OrderBlock]:
    """
    Simplified Order Block detection:
    The last bearish candle before a bullish displacement (bullish OB),
    or the last bullish candle before a bearish displacement (bearish OB).

    Displacement = a candle whose body > 2x average body size.
    """
    obs: list[OrderBlock] = []
    if len(df) < 5:
        return obs

    bodies = (df["close"] - df["open"]).abs()
    avg_body = bodies.rolling(20).mean()

    for i in range(2, len(df)):
        body = bodies.iloc[i]
        avg = avg_body.iloc[i]
        if avg == 0:
            continue

        is_displacement = body > 2.0 * avg

        if is_displacement:
            candle = df.iloc[i]
            prev = df.iloc[i - 1]

            # Bullish displacement â look for last bearish candle before it
            if candle["close"] > candle["open"]:
                if prev["close"] < prev["open"]:
                    obs.append(OrderBlock(
                        direction="bullish",
                        timeframe=timeframe,
                        zone_low=float(prev["low"]),
                        zone_high=float(prev["open"]),  # body high of bearish OB
                        candle_time=prev["datetime"].to_pydatetime(),
                    ))

            # Bearish displacement â look for last bullish candle before it
            elif candle["close"] < candle["open"]:
                if prev["close"] > prev["open"]:
                    obs.append(OrderBlock(
                        direction="bearish",
                        timeframe=timeframe,
                        zone_low=float(prev["close"]),
                        zone_high=float(prev["high"]),
                        candle_time=prev["datetime"].to_pydatetime(),
                    ))

    return obs


def detect_sweep(
    df: pd.DataFrame,
    level: float,
    level_type: str,  # 'BSL' or 'SSL'
    lookback_candles: int = 5,
) -> bool:
    """
    Check if the most recent `lookback_candles` candles swept `level`
    but closed back on the other side (classic stop hunt pattern).

    BSL sweep: a candle wicked above `level` but closed below it.
    SSL sweep: a candle wicked below `level` but closed above it.
    """
    if df.empty or len(df) < lookback_candles:
        return False

    recent = df.iloc[-lookback_candles:]

    for _, c in recent.iterrows():
        if level_type == "BSL":
            if c["high"] > level and c["close"] < level:
                return True
        elif level_type == "SSL":
            if c["low"] < level and c["close"] > level:
                return True
    return False


def check_mss(df: pd.DataFrame, direction: str, lookback: int = 5) -> bool:
    """
    Market Structure Shift detection:
    After a sweep, price closes back through the swept level within 1-3 candles.
    """
    if df.empty or len(df) < lookback:
        return False

    recent_closes = df["close"].iloc[-lookback:].values

    if direction == "bearish":
        bearish_count = sum(1 for i in range(1, len(recent_closes))
                            if recent_closes[i] < recent_closes[i - 1])
        return bearish_count >= 2
    elif direction == "bullish":
        bullish_count = sum(1 for i in range(1, len(recent_closes))
                            if recent_closes[i] > recent_closes[i - 1])
        return bullish_count >= 2
    return False


def map_stop_clusters(
    price: float,
    direction: str,
    bsl_levels: list[LiquidityLevel],
    ssl_levels: list[LiquidityLevel],
    search_range: float = 200.0,
) -> list[LiquidityLevel]:
    """Collect all stop clusters in the SL direction."""
    clusters: list[LiquidityLevel] = []
    if direction == "sell":
        candidates = bsl_levels
        filter_fn = lambda lv: lv.price > price and (lv.price - price) <= search_range
    else:
        candidates = ssl_levels
        filter_fn = lambda lv: lv.price < price and (price - lv.price) <= search_range
    clusters = [lv for lv in candidates if filter_fn(lv)]
    round_lvls = detect_round_numbers(price, search_range=search_range)
    for rl in round_lvls:
        if direction == "sell" and rl.price > price:
            clusters.append(rl)
        elif direction == "buy" and rl.price < price:
            clusters.append(rl)
    clusters.sort(key=lambda lv: abs(lv.price - price))
    return clusters


def calculate_hard_sl(
    entry: float,
    direction: str,
    stop_clusters: list[LiquidityLevel],
    entry_type: str,
    trade_mode: str,
    buffer: float = config.BSL_SSL_BUFFER,
) -> tuple[float, float, str]:
    """Calculate hard SL from farthest stop cluster."""
    min_map = {
        ("PHASE_B", "INTRADAY"): config.SL_MIN_PHASE_B_INTRADAY,
        ("PHASE_D", "INTRADAY"): config.SL_MIN_PHASE_D_INTRADAY,
        ("PHASE_B", "SWING"):    config.SL_MIN_PHASE_B_SWING,
        ("PHASE_D", "SWING"):    config.SL_MIN_PHASE_D_SWING,
    }
    min_sl_dist = min_map.get((entry_type, trade_mode), config.SL_MIN_PHASE_B_INTRADAY)
    extra_buffer = 25.0 if entry_type == "PHASE_D" else 0.0
    total_buffer = buffer + extra_buffer
    if not stop_clusters:
        dist = min_sl_dist
        hard_sl = (entry - dist) if direction == "buy" else (entry + dist)
        return hard_sl, dist, "POSSIBLE"
    if direction == "sell":
        farthest = max(stop_clusters, key=lambda lv: lv.price)
        hard_sl = farthest.price + total_buffer
        dist = hard_sl - entry
    else:
        farthest = min(stop_clusters, key=lambda lv: lv.price)
        hard_sl = farthest.price - total_buffer
        dist = entry - hard_sl
    if dist < min_sl_dist:
        dist = min_sl_dist
        hard_sl = (entry - dist) if direction == "buy" else (entry + dist)
    nearest_dist = abs(stop_clusters[0].price - entry) if stop_clusters else 9999
    if nearest_dist <= 50:
        sweep_prob = "CERTAIN"
    elif nearest_dist <= 100:
        sweep_prob = "LIKELY"
    else:
        sweep_prob = "POSSIBLE"
    return round(hard_sl, 2), round(dist, 2), sweep_prob


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Internal Helpers
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _in_killzone(hour: int) -> bool:
    return (config.LONDON_KZ_START <= hour < config.LONDON_KZ_END or
            config.NEW_YORK_KZ_START <= hour < config.NEW_YORK_KZ_END)


def _is_fvg_mitigated(
    df: pd.DataFrame,
    fvg_idx: int,
    zone_low: float,
    zone_high: float,
    direction: str,
) -> bool:
    future = df.iloc[fvg_idx + 1:]
    if future.empty:
        return False
    if direction == "bullish":
        return bool((future["low"] <= zone_high).any())
    else:
        return bool((future["high"] >= zone_low).any())


def _estimate_density(df: pd.DataFrame, price: float, level: str) -> str:
    tolerance = 2.0
    col = "high" if level == "high" else "low"
    touches = ((df[col] - price).abs() <= tolerance).sum()
    if touches >= 4:
        return "heavy"
    elif touches >= 2:
        return "moderate"
    return "light"
