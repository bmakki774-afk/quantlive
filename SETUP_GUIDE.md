# QuantLive Signal Platform â Setup Guide

Complete step-by-step setup: Twelve Data â Telegram â Railway â Go live.

---

## Step 1 â Get Your Twelve Data API Key

1. Go to [https://twelvedata.com](https://twelvedata.com) and create a free account.
2. In your dashboard, copy your **API Key**.
3. Free tier gives you **800 API credits/day** with 8 requests/minute.
   - Our platform uses 4 requests per cycle (one per timeframe).
   - At 48 cycles/day (every 30 min) Ã 4 requests = 192 req/day â well within free tier.

---

## Step 2 â Create Your Telegram Bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts.
3. Give your bot a name (e.g. `QuantLive Signals`) and username (e.g. `quantlive_bot`).
4. BotFather will give you a **token** â copy it. Looks like: `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`

**Get your Chat ID:**
1. Start your bot (click the link BotFather gives you â press Start).
2. Send any message to your bot (e.g. "hello").
3. Open this URL in a browser (replace YOUR_TOKEN):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
4. Find `"chat":{"id":XXXXXXXXX}` in the JSON â that number is your **Chat ID**.

---

## Step 3 â Set Up Railway

### 3a. Create a Railway Account
Go to [https://railway.com](https://railway.com) and sign up (free tier available).

### 3b. Create a New Project
1. Click **New Project** â **Deploy from GitHub repo**.
2. Push your code to a GitHub repo first (see Step 4).
3. Select your repo â Railway will auto-detect the Dockerfile.

### 3c. Add PostgreSQL Database
1. Inside your Railway project, click **+ Add** â **Database** â **PostgreSQL**.
2. Railway will automatically add a `DATABASE_URL` environment variable to your project.
   - You do NOT need to set this manually â Railway handles it.

### 3d. Set Environment Variables
In your Railway project â **Variables** tab, add:

```
TWELVE_DATA_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ACCOUNT_SIZE=2500
LOG_LEVEL=INFO
```

The `DATABASE_URL` will be set automatically by Railway when you add Postgres.

---

## Step 4 â Push to GitHub and Deploy

```bash
# Inside the "SIgnal Framework" folder:
git init
git add .
git commit -m "Initial QuantLive platform"
git remote add origin https://github.com/YOUR_USERNAME/quantlive.git
git push -u origin main
```

Railway will automatically detect the push and deploy.

---

## Step 5 â Verify Deployment

1. In Railway, click on your service â **Logs** tab.
2. You should see startup logs like:
   ```
   QuantLive Signal Platform â Starting Up
   Symbol:  XAU/USD
   Account: $2,500
   Database ready.
   Running initial pipeline cycle on startupâ¦
   ```
3. Check your Telegram â you should receive a **heartbeat message** immediately.

---

## Step 6 â Monitor Signals

The platform will:
- Scan XAU/USD **every 30 minutes** (:00 and :30 past every hour, UTC)
- Send a **Telegram alert** when a qualifying ICT setup is found
- Send an hourly **heartbeat** at :05 past every hour to confirm it's running
- Store all signals in the PostgreSQL database

### Understanding the Telegram Alert

```
ð¢ QuantLive Signal #42
2026-04-06 03:00 UTC

MODE:        INTRADAY
ENTRY TYPE:  PHASE_B
DIRECTION:   ð¢ BUY
ENTRY ZONE:  3,285.50 â 3,292.00
FVG CE:      3,288.75  [1h]
DOL TARGET:  3,340.00 [BSL]

STOP LOSS
  Alert T1:  3,270.00  (nearest cluster)
  Hard  T2:  3,255.00  (farthest + buffer)
  Gap:       15pt gap

JUDAS RANGE: 3,270.00 â 3,260.00

TARGETS
  Part A (40%): 3,308.00
  Part B (35%): 3,325.00  â R:R 4.2:1
  Part C (25%): 3,340.00

POSITION
  Lots: 0.18  |  Risk: $50

QUALITY GATE
  FVG Score:    11/~15
  Gates Passed: 14/16
  â VERDICT: EXECUTE_REDUCE_25
  Size: Reduce 25%
```

### Three-Candle Confirmation Rule
**Do not enter immediately on receiving the alert.** Wait for:
- **C1**: A candle wicks BEYOND the FVG zone (the Judas sweep)
- **C2**: Next candle closes OPPOSITE to the sweep (MSS confirmation)
- **C3**: Next candle continues in C2's direction
- **Entry**: Market order at C4 open, OR limit at the FVG CE if C4 opens past it

---

## Step 7 â The 7 Rules (Never Break These)

| Rule | Condition | Action |
|------|-----------|--------|
| RULE 1 | Cannot identify DOL clearly | NO TRADE |
| RULE 2 | No Phase B sweep confirmed | NO TRADE |
| RULE 3 | Outside Kill Zone (intraday) | NO TRADE |
| RULE 4 | R:R < 3:1 intraday / 5:1 swing | NO TRADE |
| RULE 5 | NFP/FOMC/CPI within 30 min | NO NEW ENTRY |
| RULE 6 | 2 losing intraday trades today | STOP TRADING |
| RULE 7 | SL not beyond full BSL/SSL range | RECALCULATE |

---

## Customisation

### Adjust Risk Per Trade
In your Railway environment variables:
```
MAX_RISK_PHASE_B=0.01   # 1% (default 2%)
MAX_RISK_PHASE_D=0.005  # 0.5% (default 1%)
```

### Disable Heartbeat Messages
Edit `main.py` and comment out the `hourly_heartbeat` scheduler job.

### Add News Events
In `pipeline.py`, update `extra_context` with real news data:
```python
extra_context = {
    "news_within_2h":  True,   # Set to True before NFP/FOMC
    "nfp_fomc_within_48h": True,
}
```

---

## Database Tables Reference

| Table | Purpose |
|-------|---------|
| `candles` | All OHLCV data fetched from Twelve Data |
| `signals` | Every generated signal with full analysis |
| `strategies` | Strategy configurations |
| `outcomes` | Trade results (manually updated) |
| `backtest_results` | Backtesting summary stats |
| `strategy_performance` | Win rate / R:R tracking |

Connect to your Railway Postgres with any client using the `DATABASE_URL` from your Railway Variables tab.

---

## Troubleshooting

**No signals being generated:**
- Check Railway logs for errors
- Verify `TWELVE_DATA_API_KEY` is correct
- Free tier rate limits: wait 12 seconds between requests (already handled)
- Phase detection needs 50+ candles â wait for first few runs

**Telegram not receiving messages:**
- Verify the bot token and chat ID are correct
- Make sure you sent at least one message TO the bot before checking getUpdates
- Check that `DATABASE_URL` is set (Railway adds this automatically)

**Database errors:**
- The database schema is created automatically on startup
- If you see `DATABASE_URL not set`, add it to Railway Variables

---

*QuantLive Signal Platform â Built on the ICT methodology. Trade at your own risk.*
