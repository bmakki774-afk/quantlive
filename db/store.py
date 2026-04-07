"""
Database read/write helpers for the signal platform.
"""
import logging
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from db.connection import get_engine

log = logging.getLogger(__name__)

def upsert_candles(symbol: str, timeframe: str, rows: list[dict]):
    """Insert candle rows, ignoring duplicates."""
    if not rows:
        return
    engine = get_engine()
    sql = text("""
        INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
        VALUES (:symbol, :timeframe, :ts, :open, :high, :low, :close, :volume)
        ON CONFLICT (symbol, timeframe, ts) DO NOTHING
    """)
    with engine.connect() as conn:
        conn.execute(sql, [
            {
                "symbol": symbol, "timeframe": timeframe,
                "ts": r["datetime"], "open": r["open"],
                "high": r["high"], "low": r["low"],
                "close": r["close"], "volume": r.get("volume", 0),
            }
            for r in rows
        ])
        conn.commit()
    log.debug(f"Upserted {len(rows)} candles for {symbol} {timeframe}.")

def save_signal(signal: dict) -> int:
    """Persist a generated signal. Returns the new signal ID."""
    engine = get_engine()
    raw = signal.get("raw_analysis")
    if raw and not isinstance(raw, str):
        raw = json.dumps(raw, default=str)
    sql = text("""
        INSERT INTO signals (
            strategy_id, symbol, direction, mode, entry_type,
            phase_swing, phase_intraday,
            entry_zone_low, entry_zone_high, entry_tf,
            stop_loss_t1, stop_loss_t2, sl_distance_pts,
            part_a_target, part_b_target, part_c_target,
            rr_part_b, fvg_score, gates_passed, verdict,
            lots, risk_dollars,
            judas_min, judas_max,
            macro_bias, session_bias,
            dol_primary, dol_secondary,
            fvg_zone_low, fvg_zone_high, fvg_ce,
            raw_analysis
        ) VALUES (
            :strategy_id, :symbol, :direction, :mode, :entry_type,
            :phase_swing, :phase_intraday,
            :entry_zone_low, :entry_zone_high, :entry_tf,
            :stop_loss_t1, :stop_loss_t2, :sl_distance_pts,
            :part_a_target, :part_b_target, :part_c_target,
            :rr_part_b, :fvg_score, :gates_passed, :verdict,
            :lots, :risk_dollars,
            :judas_min, :judas_max,
            :macro_bias, :session_bias,
            :dol_primary, :dol_secondary,
            :fvg_zone_low, :fvg_zone_high, :fvg_ce,
            :raw_analysis
        )
        RETURNING id
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {**signal, "raw_analysis": raw})
        signal_id = result.scalar()
        conn.commit()
    log.info(f"Signal saved - ID {signal_id} | {signal['direction']} | {signal['verdict']}")
    return signal_id

def mark_alert_sent(signal_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE signals SET alert_sent = TRUE WHERE id = :id"),
            {"id": signal_id}
        )
        conn.commit()

def get_strategy_id(name: str = "ICT_XAUUSD_v1") -> int:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM strategies WHERE name = :name"),
            {"name": name}
        ).fetchone()
    return row[0] if row else 1

def get_recent_signals(limit: int = 10) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, direction, mode, verdict, fvg_score, gates_passed,
                       rr_part_b, created_at
                FROM signals
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        ).fetchall()
    return [dict(r._mapping) for r in rows]

def is_duplicate_signal(direction: str, mode: str, hours: int = 4) -> bool:
    """
    Returns True if same direction+mode signal was already alert-sent
    within the cooldown window. Blocks Telegram spam on every 15-min scan.
    Caller sets hours: INTRADAY=4, SWING=8.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id FROM signals
                    WHERE direction = :direction
                      AND mode = :mode
                      AND alert_sent = TRUE
                      AND created_at > :cutoff
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"direction": direction, "mode": mode, "cutoff": cutoff}
            ).fetchone()
        return row is not None
    except Exception as exc:
        log.warning(f"Dedup check failed (allowing signal): {exc}")
        return False
"""
Database read/write helpers for the signal platform.
"""
import logging
import json
from datetime import datetime
from sqlalchemy import text
from db.connection import get_engine

log = logging.getLogger(__name__)


# âââ Candles ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def upsert_candles(symbol: str, timeframe: str, rows: list[dict]):
    """Insert candle rows, ignoring duplicates."""
    if not rows:
        return
    engine = get_engine()
    sql = text("""
        INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
        VALUES (:symbol, :timeframe, :ts, :open, :high, :low, :close, :volume)
        ON CONFLICT (symbol, timeframe, ts) DO NOTHING
    """)
    with engine.connect() as conn:
        conn.execute(sql, [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "ts": r["datetime"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r.get("volume", 0),
            }
            for r in rows
        ])
        conn.commit()
    log.debug(f"Upserted {len(rows)} candles for {symbol} {timeframe}.")


# âââ Signals ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def save_signal(signal: dict) -> int:
    """
    Persist a generated signal. Returns the new signal ID.
    signal dict keys match the signals table columns.
    """
    engine = get_engine()

    # Serialise raw_analysis to JSON string
    raw = signal.get("raw_analysis")
    if raw and not isinstance(raw, str):
        raw = json.dumps(raw, default=str)

    sql = text("""
        INSERT INTO signals (
            strategy_id, symbol, direction, mode, entry_type,
            phase_swing, phase_intraday,
            entry_zone_low, entry_zone_high, entry_tf,
            stop_loss_t1, stop_loss_t2, sl_distance_pts,
            part_a_target, part_b_target, part_c_target,
            rr_part_b, fvg_score, gates_passed, verdict,
            lots, risk_dollars,
            judas_min, judas_max,
            macro_bias, session_bias,
            dol_primary, dol_secondary,
            fvg_zone_low, fvg_zone_high, fvg_ce,
            raw_analysis
        ) VALUES (
            :strategy_id, :symbol, :direction, :mode, :entry_type,
            :phase_swing, :phase_intraday,
            :entry_zone_low, :entry_zone_high, :entry_tf,
            :stop_loss_t1, :stop_loss_t2, :sl_distance_pts,
            :part_a_target, :part_b_target, :part_c_target,
            :rr_part_b, :fvg_score, :gates_passed, :verdict,
            :lots, :risk_dollars,
            :judas_min, :judas_max,
            :macro_bias, :session_bias,
            :dol_primary, :dol_secondary,
            :fvg_zone_low, :fvg_zone_high, :fvg_ce,
            :raw_analysis
        )
        RETURNING id
    """)

    with engine.connect() as conn:
        result = conn.execute(sql, {**signal, "raw_analysis": raw})
        signal_id = result.scalar()
        conn.commit()

    log.info(f"Signal saved â ID {signal_id} | {signal['direction']} | {signal['verdict']}")
    return signal_id


def mark_alert_sent(signal_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE signals SET alert_sent = TRUE WHERE id = :id"),
            {"id": signal_id}
        )
        conn.commit()


def get_strategy_id(name: str = "ICT_XAUUSD_v1") -> int:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM strategies WHERE name = :name"),
            {"name": name}
        ).fetchone()
    return row[0] if row else 1


def get_recent_signals(limit: int = 10) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, direction, mode, verdict, fvg_score, gates_passed,
                       rr_part_b, created_at
                FROM signals
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        ).fetchall()
    return [dict(r._mapping) for r in rows]
