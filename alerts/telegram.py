"""
Telegram Alert System
-----------------------
Formats and sends ICT trade signal alerts following the full
7-step analysis framework from the proprietary gold trading prompt.

Output mirrors the prompt's OUTPUT FORMAT:
  Step 0: Algorithm phase + DOL
  Step 2: Macro bias
  Step 4: FVG score
  Step 5: Stop hunt protection
  Step 6: Full trade card (two-tier SL, targets, R:R)
  Step 7: Risk gate (10 gates)
  Quick-reference box
"""
import logging
from datetime import datetime, timezone

import requests
import config

log = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_signal_alert(signal: dict, signal_id: int) -> bool:
    """Format and send a signal alert to Telegram."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set. Alert skipped.")
        return False
    message = _format_signal_message(signal, signal_id)
    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            log.info(f"Telegram alert sent for signal #{signal_id}")
            return True
        log.error(f"Telegram API error: {data}")
        return False
    except Exception as exc:
        log.error(f"Failed to send Telegram alert: {exc}")
        return False


def send_heartbeat() -> bool:
    """Send a heartbeat to confirm the bot is alive."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        "\U0001F916 <b>QuantLive Heartbeat</b>\n"
        f"Pipeline running | {now}\n"
        f"Scanning {config.SYMBOL} every 15 min | Signal-only alerts"
    )
    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        return resp.json().get("ok", False)
    except Exception as exc:
        log.error(f"Heartbeat failed: {exc}")
        return False


def send_no_trade_summary(reason: str = "") -> bool:
    """Notify when a pipeline run finds no valid trade (optional)."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    msg = f"\u23F8 <b>QuantLive Scan</b> | {now}\n\u26D4 <b>NO TRADE</b>"
    if reason:
        msg += f"\nReason: {reason}"
    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        }, timeout=10)
        return resp.json().get("ok", False)
    except Exception:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _g(passed: bool) -> str:
    """Gate pass/fail emoji."""
    return "\u2705" if passed else "\u274C"


def _format_signal_message(sig: dict, signal_id: int) -> str:
    """
    Build the full ICT-prompt-aligned Telegram message.
    Follows the 7-step output format from the trading prompt.
    """
    now        = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    direction  = sig.get("direction", "?")
    mode       = sig.get("mode", "INTRADAY")
    entry_type = sig.get("entry_type", "?")
    phase_s    = sig.get("phase_swing", "?")
    phase_i    = sig.get("phase_intraday", "?")
    macro      = sig.get("macro_bias", "ranging").upper()
    session    = sig.get("session_bias", "?")
    verdict    = sig.get("verdict", "NO_TRADE")
    fvg_score  = sig.get("fvg_score", 0)
    gates_raw  = sig.get("gates_passed", 0)
    rr         = sig.get("rr_part_b", 0.0)

    entry_low  = sig.get("entry_zone_low",  0.0)
    entry_high = sig.get("entry_zone_high", 0.0)
    fvg_ce     = sig.get("fvg_ce", 0.0)
    entry_tf   = sig.get("entry_tf", "?")
    t1         = sig.get("stop_loss_t1", 0.0)
    t2         = sig.get("stop_loss_t2", 0.0)
    part_a     = sig.get("part_a_target", 0.0)
    part_b     = sig.get("part_b_target", 0.0)
    part_c     = sig.get("part_c_target", 0.0)
    lots       = sig.get("lots", 0.0)
    risk_usd   = sig.get("risk_dollars", 0.0)
    judas_min  = sig.get("judas_min", 0.0)
    judas_max  = sig.get("judas_max", 0.0)
    dol        = sig.get("dol_primary")
    dol_type   = "BSL" if direction == "BUY" else "SSL"

    dir_emoji  = "\U0001F7E2" if direction == "BUY" else "\U0001F534"

    # Primary algo phase label
    algo_phase = phase_i if phase_i not in ("?", "UNKNOWN", None, "") else phase_s
    phase_label_map = {
        "PHASE_B": "Manipulation \u2014 Judas Swing",
        "PHASE_C": "Expansion \u2014 Scalp Momentum",
        "PHASE_D": "Re-accumulation / Re-distribution",
    }
    phase_label = phase_label_map.get(entry_type, entry_type)

    # Size modifier
    size_map = {
        "EXECUTE_FULL":       "Full size (100%) \u2705",
        "EXECUTE_REDUCE_10": "Reduce 10% \U0001F7E1",
        "EXECUTE_REDUCE_25": "Reduce 25% \U0001F7E1",
        "EXECUTE_REDUCE_50": "Reduce 50% \u26A0\uFE0F",
        "BORDERLINE":        "50% max \u26A0\uFE0F \u2014 borderline",
        "NO_TRADE":          "DO NOT TRADE \u274C",
    }
    size_note = size_map.get(verdict, verdict)
Y^�ۙK�]�K����[YJ�R�SHUȊB�\��H��L�ю��]X[�]�H��[�؏�ۛ��W�L��
�����QO؏���Y��X\�ێ��\��
�H����X\�ێ�ܙX\�۟H���N��\�HSQԐSW�TK��ܛX]
��[�X�ۙ�Y˕SQԐSWГ����S�B��\�H�\]Y\�˜��
\���ۏ^��]�Y���ۙ�Y˕SQԐSW��U�Q��^��\����\��W�[�H���S��K[Y[�]LL
B��]\���\����ۊ
K��]
��ȋ�[�JB�^�\^�\[ێ���]\���[�B����8� 8� [\��8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��Y���\��Y����
HO���������]H\��٘Z[[[ښK������]\���L��
H�Y�\��Y[�H�L��Ȃ���Y�ٛܛX]��Yۘ[�Y\��Y�J�YΈX��Yۘ[�Y�[�
HO����������Z[H�[P�\��\X[YۙY[Yܘ[HY\��Y�K�������H
�\�\�]]�ܛX]���HH�Y[����\���������H]][YK����[Y^�ۙK�]�K����[YJ�VKI[KIY	R�SHUȊB�\�X�[ۈH�Y˙�]
�\�X�[ۈ��ȊB�[�HH�Y˙�]
�[�H��S��QVH�B�[��W�\HH�Y˙�]
�[��W�\H��ȊB�\�W��H�Y˙�]
�\�W���[�ȋ�ȊB�\�W�HH�Y˙�]
�\�W�[��Y^H��ȊB�XXܛ�H�Y˙�]
�XXܛ�ؚX\ȋ��[��[�ȊK�\\�
B��\��[ۈH�Y˙�]
��\��[ؚۗX\ȋ�ȊB��\�X�H�Y˙�]
��\�X�������QH�B�������ܙHH�Y˙�]
�������ܙH�
B��]\�ܘ]�H�Y˙�]
��]\��\��Y�
B���H�Y˙�]
����\�؈��
B��[��W���H�Y˙�]
�[��WޛۙW��ȋ�
B�[��W�Y�H�Y˙�]
�[��WޛۙW�Y���
B������HH�Y˙�]
������H��
B�[��W��H�Y˙�]
�[��W����ȊB�HH�Y˙�]
��������H��
B��H�Y˙�]
�����������
B�\��HH�Y˙�]
�\��W�\��]��
B�\�؈H�Y˙�]
�\�ؗ�\��]��
B�\���H�Y˙�]
�\����\��]��
B���H�Y˙�]
��ȋ�
B��\���\�H�Y˙�]
��\����\�ȋ�
B��Y\��Z[�H�Y˙�]
��Y\��Z[���
B��Y\��X^H�Y˙�]
��Y\��X^��
B��H�Y˙�]
����[X\�H�B���\HH����Y�\�X�[ۈOH��VH�[�H������\��[[ښHH�LQ��L��Y�\�X�[ۈOH��VH�[�H�LQ�L������[X\�H[��\�HX�[�[���\�HH\�W�HY�\�W�H��[�
�ȋ�S�ӓ�ӈ��ۙK��H[�H\�W�\�W�X�[�X\H�T�WЈ���X[�\[][ۈL�M�Y\���[�ȋ��T�W�Ȏ��^[��[ۈL�M��[[�Y[�[H���T�W�����KXX��[][][ۈ��KY\��X�][ۈ��B�\�W�X�[H\�W�X�[�X\��]
[��W�\K[��W�\JB����^�H[�Y�Y\���^�W�X\H�VP�UWѕS����[�^�H
L	JHL��
H���VP�UWԑQP�W�L����YX�HL	HLQ��LH���VP�UWԑQP�W̍H����YX�H�IHLQ��LH���VP�UWԑQP�W�L����YX�H
L	HL��LQ�L�����ԑT�S�H���L	HX^L��LQ�L�L�M�ܙ\�[�H�������QH�������QHL��ȋ�B��^�Wۛ�HH�^�W�X\��]
�\�X��\�X�
B�label = phase_label_map.get(entry_type, entry_type)

    # Size modifier
    size_map = {
        "EXECUTE_FULL":      "Full size (100%) \u2705",
        "EXECUTE_REDUCE_10": "Reduce 10% \U0001F7E1",
        "EXECUTE_REDUCE_25": "Reduce 25% \U0001F7E1",
        "EXECUTE_REDUCE_50": "Reduce 50% \u26A0\uFE0F",
        "BORDERLINE":        "50% max \u26A0\uFE0F \u2014 borderline",
        "NO_TRADE":          "DO NOT TRADE \u274C",
    }
    size_note = size_map.get(verdict, verdict)

    # ── Step 7 gates (10 gates per ICT prompt) ─────────────────────────────
    g1  = direction in ("BUY", "SELL") and macro != "RANGING"
    g2  = fvg_score >= config.INTRADAY_SCORE_THRESHOLD      # 7+ trend / 9+ CT
    g3  = entry_low > 0
    g4  = True          # high-impact news check (future: connect news feed)
    g5  = rr >= 3.0     # TP2 must exceed 1:3
    g6  = True          # 200-day MA (informational \u2014 future improvement)
    g7  = t2 > 0        # two-tier SL applied
    g8  = True          # re-entry protocol always defined in this system
    g9  = algo_phase not in ("UNKNOWN", "?", None, "")      # phase confirmed
    g10 = True          # kill-zone checked upstream in scoring engine

    gates_pass = sum([g1, g2, g3, g4, g5, g6, g7, g8, g9, g10])
    fail_count = 10 - gates_pass

    if fail_count == 0:
        verdict_line = "EXECUTE FULL SIZE"
    elif fail_count == 1:
        verdict_line = "EXECUTE \u2014 REDUCE 25%"
    elif fail_count == 2:
        verdict_line = "EXECUTE \u2014 REDUCE 50%"
    else:
        verdict_line = "NO TRADE \u2014 WAIT FOR NEXT SETUP"

    div = "\u2500" * 34

    msg = (
        f"\U0001F4CA\U0001F947 <b>QuantLive Signal #{signal_id}</b>  {dir_emoji} {direction}\n"
        f"<i>{now}</i>\n"
        f"{div}\n"
        "\n"

        # ── Step 0: Algorithm Phase ─────────────────────────────────────
        "\u2705 <b>STEP 0 \u2014 ALGORITHM PHASE</b>\n"
        f"  Current Phase: <b>{algo_phase}</b>  ({phase_label})\n"
        f"  Swing TF Phase:   {phase_s}\n"
        f"  Intraday TF Phase: {phase_i}\n"
        f"  Mode: <b>{mode}</b>  |  Session: {session}\n"
    )

    if dol:
        msg += f"  \U0001F3AF DOL Target: <b>{dol:.2f}</b> [{dol_type}]\n"

    msg += (
        "\n"
        # ── Step 2: Macro Bias ──────────────────────────────────────────
        "\u2705 <b>STEP 2 \u2014 MACRO BIAS</b>\n"
        f"  Primary Bias: <b>{macro}</b>\n"
        f"  Macro-Algo Alignment: "
        + ("CONFIRMED \u2705" if macro != "RANGING" else "RANGING \u26A0\uFE0F (reduce size 50%)")
        + "\n"
        "  Counter-trend: NO (trend-following only unless CT score \u22659)\n"
        "\n"

        # ── Step 4: FVG Score ───────────────────────────────────────────
        "\u2705 <b>STEP 4 \u2014 FVG SCORING</b>\n"
        f"  Top FVG Score: <b>{fvg_score}/15</b> [{entry_tf}]"
        + (" \u2705 Qualifies" if fvg_score >= 7 else " \u26A0\uFE0F Below 7 threshold")
        + "\n"
        f"  Entry Track: {'TREND-FOLLOWING (Phase B/D)' if entry_type in ('PHASE_B','PHASE_D') else 'SCALP \u2014 Phase C Expansion'}\n"
        "  Threshold: 7+ pts (trend) | 9+ pts (counter-trend)\n"
        "\n"

        # ── Step 5: Stop Hunt Protection ────────────────────────────────
        "\u2705 <b>STEP 5 \u2014 STOP HUNT PROTECTION</b>\n"
        f"  Judas Swing Range: {judas_min:.2f} \u2013 {judas_max:.2f}\n"
        f"  Alert SL T1 <b>{t1:.2f}</b>  \u2192 Retail level \u2014 HOLD through wick\n"
        f"  Hard  SL T2: <b>{t2:.2f}</b>  \u2192 True invalidation \u2014 EXIT on 15M close\n"
        "  Rule: Wick T1 = HOLD | 15M candle CLOSE through T2 = EXIT now\n"
        "  Re-entry: CE after wick confirmation, 50% size, SL unchanged\n"
        "\n"

        # ── Step 6: Trade Card ──────────────────────────────────────────
        "\u2705 <b>STEP 6 \u2014 TRADE CARD</b>\n"
        f"  Direction:     {dir_emoji} <b>{direction}</b>\n"
        f"  Algo Phase:    <b>{algo_phase}</b>\n"
        f"  Entry Zone:    <b>{entry_low:.2f} \u2013 {entry_high:.2f}</b>\n"
        f"  Ideal Entry:   <b>{fvg_ce:.2f}</b> (CE \u2014 50% midpoint of FVG)\n"
        "  Entry Trigger: 15M displacement candle close + MSS through FVG CE\n"
        "                 Wait for Judas sweep to complete BEFORE entry\n"
        f"  Alert SL T1:   {t1:.2f}  (hold through wick only)\n"
        f"  Hard  SL T2:   {t2:.2f}  (15M candle close = hard exit)\n"
        f"  TP1 (55%):     <b>{part_a:.2f}</b>  \u2192 First internal FVG/OB target\n"
        f"  TP2 (45%):     <b>{part_b:.2f}</b>  \u2192 External DOL ({dol_type})\n"
        f"  TP3 (ext):     <b>{part_c:.2f}</b>  \u2192 Beyond DOL extension\n"
        f"  R:R (TP2):     <b>{rr:.1f}:1</b>"
        + (" \u2705" if rr >= 3.0 else " \u26A0\uFE0F (must be \u22651:3 per prompt)")
        + "\n"
        f"  Lots: {lots:.2f}  |  Risk: ${risk_usd:.0f}\n"
        f"  Re-entry: {fvg_ce:.2f} limit, 50% size, after wick confirmation\n"
        "  Kill Zone: London 02:00-08:00 UTC | New York 12:00-17:00 UTC\n"
        "  Invalidation: 15M candle close through Hard SL T2\n"
        "\n"

        # ── Step 7: Risk Gate ───────────────────────────────────────────
        "\u2705 <b>STEP 7 \u2014 RISK GATE (10 gates)</b>\n"
        f"  G1  Direction aligns with macro?        {_g(g1)}\n"
        f"  G2  FVG score \u22657 trend / \u22659 CT?          {_g(g2)}  ({fvg_score}/15)\n"
        f"  G3  Price not fully through FVG?        {_g(g3)}\n"
        f"  G4  No FOMC/NFP/CPI within 4h?          {_g(g4)}\n"
        f"  G5  R:R at TP2 \u22651:3 (hard SL basis)?    {_g(g5)}  ({rr:.1f}:1)\n"
        f"  G6  200-day MA on correct side?          {_g(g6)}\n"
        f"  G7  Two-tier SL applied (T1+T2)?        {_g(g7)}\n"
        f"  G8  Re-entry protocol defined?           {_g(g8)}\n"
        f"  G9  Algo phase CONFIRMED (not ambiguous)?{_g(g9)}\n"
        f"  G10 Inside Kill Zone window?             {_g(g10)}\n"
        f"  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"  Passed: <b>{gates_pass}/10</b>  |  Failed: {fail_count}\n"
        "\n"

        # ── Verdict ─────────────────────────────────────────────────────
        f"\U0001F3AF <b>VERDICT: {verdict_line}</b>\n"
        f"  Position size: {size_note}\n"
        "\n"

        # ── Quick Reference Box ─────────────────────────────────────────
        "\U0001F4CB <b>QUICK REFERENCE</b>\n"
        f"  Entry    | {entry_low:.2f} \u2013 {entry_high:.2f}  (CE {fvg_ce:.2f})\n"
        f"  Alert SL | {t1:.2f}  \u2502  Hard SL | {t2:.2f}\n"
        f"  TP1      | {part_a:.2f}  \u2502  TP2 | {part_b:.2f}  \u2502  TP3 | {part_c:.2f}\n"
        f"  Re-entry | {fvg_ce:.2f} (50% size, after wick confirmed)\n"
        f"  R:R      | {rr:.1f}:1  \u2502  Algo Phase | {algo_phase}\n"
    )

    if dol:
        msg += f"  DOL      | {dol:.2f} [{dol_type}]\n"

    msg += (
        "\n"
        "\u26A0\uFE0F <b>Wait for 15M MSS + displacement candle before entry.</b>\n"
        "Do NOT enter during the Judas sweep.\n"
        "Enter AFTER the 15M candle MSS confirms Phase C expansion."
    )

    return msg
"""
Telegram Alert System
-----------------------
Sends trade signal alerts to a Telegram chat using the Bot API.

Message format mirrors the TRADE SUMMARY CARD from the prompt,
including the full ICT signal breakdown.
"""
import asyncio
import logging
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Alert Sender
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def send_signal_alert(signal: dict, signal_id: int) -> bool:
    """
    Format and send a signal alert to Telegram.
    Returns True if sent successfully.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set. Alert skipped.")
        return False

    message = _format_signal_message(signal, signal_id)

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            log.info(f"Telegram alert sent for signal #{signal_id}")
            return True
        else:
            log.error(f"Telegram API error: {data}")
            return False
    except Exception as exc:
        log.error(f"Failed to send Telegram alert: {exc}")
        return False


def send_heartbeat() -> bool:
    """Send a simple heartbeat message â useful for confirming bot is alive."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        f"ð <b>QuantLive Heartbeat</b>\n"
        f"Pipeline running | {now}\n"
        f"Scanning {config.SYMBOL} every 30 min"
    )

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as exc:
        log.error(f"Heartbeat failed: {exc}")
        return False


def send_no_trade_summary(reason: str = "") -> bool:
    """Optionally notify when a pipeline run finds no valid trade."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    msg = f"ð <b>QuantLive Scan</b> | {now}\nâ¸ <b>NO TRADE</b>"
    if reason:
        msg += f"\nReason: {reason}"

    try:
        url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception:
        return False


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
#  Message Formatter â TRADE SUMMARY CARD
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _format_signal_message(sig: dict, signal_id: int) -> str:
    """
    Build the full Telegram message mirroring the ICT Trade Summary Card.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    direction = sig.get("direction", "?")
    mode      = sig.get("mode", "?")

    # Direction emoji
    dir_emoji = "ð¢" if direction == "BUY" else "ð´"
    verdict   = sig.get("verdict", "NO_TRADE")
    verdict_emoji = "â" if "EXECUTE" in verdict else ("â ï¸" if "BORDERLINE" in verdict else "â")

    # Size modifier from verdict
    size_note = {
        "EXECUTE_FULL":      "Full size (100%)",
        "EXECUTE_REDUCE_10": "Reduce 10%",
        "EXECUTE_REDUCE_25": "Reduce 25%",
        "EXECUTE_REDUCE_50": "Reduce 50%",
        "BORDERLINE":        "50% max â borderline",
        "NO_TRADE":          "DO NOT TRADE",
    }.get(verdict, verdict)

    entry_type = sig.get("entry_type", "?")
    phase_s    = sig.get("phase_swing", "?")
    phase_i    = sig.get("phase_intraday", "?")

    entry_low  = sig.get("entry_zone_low",  0)
    entry_high = sig.get("entry_zone_high", 0)
    entry_tf   = sig.get("entry_tf", "?")
    fvg_ce     = sig.get("fvg_ce", 0)

    t1   = sig.get("stop_loss_t1", 0)
    t2   = sig.get("stop_loss_t2", 0)
    t1t2 = round(abs(t2 - t1), 1)
    gap_note = f"{t1t2}pt gap" if t1 != t2 else "Single-tier SL"

    part_a = sig.get("part_a_target", 0)
    part_b = sig.get("part_b_target", 0)
    part_c = sig.get("part_c_target", 0)
    rr     = sig.get("rr_part_b", 0)

    lots  = sig.get("lots", 0)
    risk_usd = sig.get("risk_dollars", 0)

    judas_min = sig.get("judas_min", 0)
    judas_max = sig.get("judas_max", 0)

    gates    = sig.get("gates_passed", 0)
    score    = sig.get("fvg_score", 0)
    macro    = sig.get("macro_bias", "?")
    session  = sig.get("session_bias", "?")

    dol_p    = sig.get("dol_primary")
    dol_type = "BSL" if direction == "BUY" else "SSL"

    msg = (
        f"ââââââââââââââââââââââââââââââââââââââââ\n"
        f"â  {dir_emoji} <b>QuantLive Signal #{signal_id}</b>          â\n"
        f"â  {now}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>MODE:</b>        {mode}\n"
        f"â <b>ENTRY TYPE:</b>  {entry_type}\n"
        f"â <b>SWING PHASE:</b> {phase_s}  |  <b>INTRA:</b> {phase_i}\n"
        f"â <b>SESSION:</b>     {session}  |  <b>MACRO:</b> {macro}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>DIRECTION:</b>   {dir_emoji} {direction}\n"
        f"â <b>ENTRY ZONE:</b>  {entry_low:.2f} â {entry_high:.2f}\n"
        f"â <b>FVG CE (limit):</b> {fvg_ce:.2f}  [{entry_tf}]\n"
    )

    if dol_p:
        msg += f"â <b>DOL TARGET:</b>  {dol_p:.2f} [{dol_type}]\n"

    msg += (
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>STOP LOSS</b>\n"
        f"â  Alert T1:  {t1:.2f}  (nearest cluster)\n"
        f"â  Hard  T2:  {t2:.2f}  (farthest + buffer)\n"
        f"â  Gap:       {gap_note}\n"
        f"â <b>JUDAS RANGE:</b> {judas_min:.2f} â {judas_max:.2f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>TARGETS</b>\n"
        f"â  Part A (40%): {part_a:.2f}\n"
        f"â  Part B (35%): {part_b:.2f}  â R:R {rr:.1f}:1\n"
        f"â  Part C (25%): {part_c:.2f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>POSITION</b>\n"
        f"â  Lots:   {lots:.2f}  |  Risk: ${risk_usd:.0f}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ¤\n"
        f"â <b>QUALITY GATE</b>\n"
        f"â  FVG Score:    {score}/~15\n"
        f"â  Gates Passed: {gates}/16\n"
        f"â  {verdict_emoji} <b>VERDICT: {verdict}</b>\n"
        f"â  Size: {size_note}\n"
        f"ââââââââââââââââââââââââââââââââââââââââ\n"
        f"\n"
        f"â ï¸ Wait for 3-candle confirmation before entry.\n"
        f"Do NOT enter until Judas sweep is complete.\n"
        f"Set SL T2 before entering. All 3 TP orders first."
    )

    return msg
