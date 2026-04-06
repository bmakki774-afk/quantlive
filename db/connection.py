"""
Database connection and table initialisation.
Uses SQLAlchemy Core (no ORM) for simplicity.
"""
import logging
from sqlalchemy import create_engine, text
from config import DATABASE_URL

log = logging.getLogger(__name__)

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set in environment variables.")
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
        log.info("Database engine created.")
    return _engine


def init_db():
    """Create all tables if they don't exist."""
    engine = get_engine()
    schema_sql = _get_schema()
    with engine.connect() as conn:
        conn.execute(text(schema_sql))
        conn.commit()
    log.info("Database schema initialised.")


def _get_schema() -> str:
    return """
-- âââ Candles âââââââââââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS candles (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20)  NOT NULL,
    timeframe   VARCHAR(10)  NOT NULL,
    ts          TIMESTAMPTZ  NOT NULL,
    open        NUMERIC(12,4) NOT NULL,
    high        NUMERIC(12,4) NOT NULL,
    low         NUMERIC(12,4) NOT NULL,
    close       NUMERIC(12,4) NOT NULL,
    volume      NUMERIC(20,2),
    fetched_at  TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (symbol, timeframe, ts)
);

-- âââ Strategies ââââââââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS strategies (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Signals âââââââââââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS signals (
    id              SERIAL PRIMARY KEY,
    strategy_id     INT REFERENCES strategies(id),
    symbol          VARCHAR(20)  NOT NULL,
    direction       VARCHAR(10)  NOT NULL,   -- BUY / SELL
    mode            VARCHAR(20)  NOT NULL,   -- INTRADAY / SWING / LAYERED
    entry_type      VARCHAR(20)  NOT NULL,   -- PHASE_B / PHASE_D
    phase_swing     VARCHAR(20),
    phase_intraday  VARCHAR(20),
    entry_zone_low  NUMERIC(12,4),
    entry_zone_high NUMERIC(12,4),
    entry_tf        VARCHAR(10),
    stop_loss_t1    NUMERIC(12,4),
    stop_loss_t2    NUMERIC(12,4),
    sl_distance_pts NUMERIC(10,2),
    part_a_target   NUMERIC(12,4),
    part_b_target   NUMERIC(12,4),
    part_c_target   NUMERIC(12,4),
    rr_part_b       NUMERIC(6,2),
    fvg_score       INT,
    gates_passed    INT,
    verdict         VARCHAR(20),             -- EXECUTE / REDUCE_10 / NO_TRADE etc.
    lots            NUMERIC(8,4),
    risk_dollars    NUMERIC(10,2),
    judas_min       NUMERIC(12,4),
    judas_max       NUMERIC(12,4),
    macro_bias      VARCHAR(20),
    session_bias    VARCHAR(20),
    dol_primary     NUMERIC(12,4),
    dol_secondary   NUMERIC(12,4),
    fvg_zone_low    NUMERIC(12,4),
    fvg_zone_high   NUMERIC(12,4),
    fvg_ce          NUMERIC(12,4),
    raw_analysis    JSONB,
    alert_sent      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Backtest Results ââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS backtest_results (
    id              SERIAL PRIMARY KEY,
    strategy_id     INT REFERENCES strategies(id),
    period_start    TIMESTAMPTZ,
    period_end      TIMESTAMPTZ,
    total_trades    INT,
    wins            INT,
    losses          INT,
    win_rate        NUMERIC(5,2),
    total_pnl_pts   NUMERIC(12,2),
    max_drawdown    NUMERIC(12,2),
    avg_rr          NUMERIC(6,2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Outcomes ââââââââââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS outcomes (
    id              SERIAL PRIMARY KEY,
    signal_id       INT REFERENCES signals(id),
    result          VARCHAR(10),   -- WIN / LOSS / BREAKEVEN / OPEN
    pnl_pts         NUMERIC(10,2),
    pnl_dollars     NUMERIC(10,2),
    closed_at       TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Optimized Params ââââââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS optimized_params (
    id              SERIAL PRIMARY KEY,
    strategy_id     INT REFERENCES strategies(id),
    param_name      VARCHAR(100),
    param_value     TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Strategy Performance ââââââââââââââââââââââââââââââââââââââ
CREATE TABLE IF NOT EXISTS strategy_performance (
    id              SERIAL PRIMARY KEY,
    strategy_id     INT REFERENCES strategies(id),
    period          VARCHAR(20),   -- daily / weekly / monthly
    period_date     DATE,
    total_signals   INT,
    executed        INT,
    passed_gate     INT,
    win_rate        NUMERIC(5,2),
    avg_rr          NUMERIC(6,2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- âââ Seed default strategy âââââââââââââââââââââââââââââââââââââ
INSERT INTO strategies (name, description, active)
VALUES ('ICT_XAUUSD_v1', 'ICT Gold Signal Pipeline â 7 Rules, 16 Gates', TRUE)
ON CONFLICT (name) DO NOTHING;
"""
