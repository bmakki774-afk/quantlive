"""
QuantLive Signal Platform â Configuration
All settings pulled from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# âââ Data Source âââââââââââââââââââââââââââââââââââââââââââââââ
TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
SYMBOL: str = os.getenv("SYMBOL", "XAU/USD")
TIMEFRAMES: list[str] = ["15min", "1h", "4h", "1day"]
CANDLE_LOOKBACK: int = int(os.getenv("CANDLE_LOOKBACK", "200"))  # candles per TF

# âââ Database ââââââââââââââââââââââââââââââââââââââââââââââââââ
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# âââ Telegram ââââââââââââââââââââââââââââââââââââââââââââââââââ
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# âââ Trading Account âââââââââââââââââââââââââââââââââââââââââââ
ACCOUNT_SIZE: float = float(os.getenv("ACCOUNT_SIZE", "2500"))
MAX_RISK_PHASE_B: float = float(os.getenv("MAX_RISK_PHASE_B", "0.02"))   # 2%
MAX_RISK_PHASE_D: float = float(os.getenv("MAX_RISK_PHASE_D", "0.01"))   # 1%
MAX_COMBINED_RISK: float = float(os.getenv("MAX_COMBINED_RISK", "0.025")) # 2.5%

# âââ ICT Kill Zones (UTC) ââââââââââââââââââââââââââââââââââââââ
LONDON_KZ_START: int = 3   # 03:00 UTC
LONDON_KZ_END: int = 6     # 06:00 UTC
NEW_YORK_KZ_START: int = 13 # 13:00 UTC
NEW_YORK_KZ_END: int = 16   # 16:00 UTC

# âââ Scoring Thresholds ââââââââââââââââââââââââââââââââââââââââ
SWING_SCORE_THRESHOLD: int = 9
INTRADAY_SCORE_THRESHOLD: int = 8
COUNTER_TREND_SCORE_THRESHOLD: int = 10

# âââ Risk Gate âââââââââââââââââââââââââââââââââââââââââââââââââ
MIN_GATES_PASSED: int = 11   # below this = NO TRADE
MIN_RR_INTRADAY: float = 3.0
MIN_RR_SWING: float = 5.0

# âââ Stop Loss Minimums (points) âââââââââââââââââââââââââââââââ
SL_MIN_PHASE_B_INTRADAY: float = 60.0
SL_MIN_PHASE_D_INTRADAY: float = 100.0
SL_MIN_PHASE_B_SWING: float = 120.0
SL_MIN_PHASE_D_SWING: float = 180.0
BSL_SSL_BUFFER: float = 15.0          # pts added beyond farthest cluster

# âââ Entry Sweep Minimums (points) âââââââââââââââââââââââââââââ
SWEEP_MIN_PHASE_B_INTRADAY: float = 5.0
SWEEP_MIN_PHASE_D_INTRADAY: float = 10.0
SWEEP_MIN_PHASE_B_SWING: float = 15.0
SWEEP_MIN_PHASE_D_SWING: float = 25.0

# âââ Scheduler âââââââââââââââââââââââââââââââââââââââââââââââââ
PIPELINE_CRON_MINUTES: list[int] = [0, 30]  # fire at :00 and :30

# âââ Swing High/Low Detection ââââââââââââââââââââââââââââââââââ
SWING_LOOKBACK: int = int(os.getenv("SWING_LOOKBACK", "10"))  # bars each side

# âââ Logging âââââââââââââââââââââââââââââââââââââââââââââââââââ
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
