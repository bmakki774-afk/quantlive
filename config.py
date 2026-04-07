"""
QuantLive Signal Platform — Configuration
All settings pulled from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Data Source ────────────────────────────────────────────
TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
SYMBOL: str = os.getenv("SYMBOL", "XAU/USD")
TIMEFRAMES: list[str] = ["15min", "1h", "4h", "1day"]
CANDLE_LOOKBACK: int = int(os.getenv("CANDLE_LOOKBACK", "200"))  # candles per TF

# ─── Database ────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ─── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Trading Account ─────────────────────────────────────────
ACCOUNT_SIZE: float = float(os.getenv("ACCOUNT_SIZE", "2500"))
MAX_RISK_PHASE_B: float = float(os.getenv("MAX_RISK_PHASE_B", "0.02"))   # 2%
MAX_RISK_PHASE_D: float = float(os.getenv("MAX_RISK_PHASE_D", "0.01"))   # 1%
MAX_COMBINED_RISK: float = float(os.getenv("MAX_COMBINED_RISK", "0.025")) # 2.5%

# ─── ICT Kill Zones (UTC) ────────────────────────────────────────
LONDON_KZ_START: int = 2   # 02:00 UTC (expanded from 03:00)
LONDON_KZ_END: int = 8     # 08:00 UTC (expanded from 06:00)
NEW_YORK_KZ_START: int = 12 # 12:00 UTC (expanded from 13:00)
NEW_YORK_KZ_END: int = 17   # 17:00 UTC (expanded from 16:00)

# ─── Scoring Thresholds ──────────────────────────────────────────
SWING_SCORE_THRESHOLD: int = 6       # was 9 - relaxed for more signals
INTRADAY_SCORE_THRESHOLD: int = 5    # was 8 - relaxed for scalping
COUNTER_TREND_SCORE_THRESHOLD: int = 8  # was 10

# ─── Risk Gate ──────────────────────────────────────────────────────
MIN_GATES_PASSED: int = 9    # was 11 - relaxed threshold
MIN_RR_INTRADAY: float = 1.5  # was 3.0 - realistic for gold scalping
MIN_RR_SWING: float = 2.5     # was 5.0 - relaxed for swing trades

# ─── Stop Loss Minimums (points) ──────────────────────────────────────────
SL_MIN_PHASE_B_INTRADAY: float = 60.0
SL_MIN_PHASE_D_INTRADAY: float = 100.0
SL_MIN_PHASE_B_SWING: float = 120.0
SL_MIN_PHASE_D_SWING: float = 180.0
BSL_SSL_BUFFER: float = 15.0          # pts added beyond farthest cluster

# ─── Entry Sweep Minimums (points) ────────────────────────────────────────────
SWEEP_MIN_PHASE_B_INTRADAY: float = 5.0
SWEEP_MIN_PHASE_D_INTRADAY: float = 10.0
SWEEP_MIN_PHASE_B_SWING: float = 15.0
SWEEP_MIN_PHASE_D_SWING: float = 25.0

# ─── Scheduler ──────────────────────────────────────────────────────────
PIPELINE_CRON_MINUTES: list[int] = [0, 30]  # fire at :00 and :30

# ─── Swing High/Low Detection ────────────────────────────────────────────
SWING_LOOKBACK: int = int(os.getenv("SWING_LOOKBACK", "10"))  # bars each side

# ─── Logging ────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
