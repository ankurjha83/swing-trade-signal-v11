"""
scorer.py — Swing Signal Scorer (v1.1)
=======================================
Computes a composite SWING_SCORE (0–100) for a ticker given its OHLCV data
and auxiliary signals.

Score components (IDENTICAL weights to v1.0):
  rsi             : 15 pts   Momentum zone 50–70 (CHANGE 6: upper was 65)
                             Oversold bounce zone 30–45
  ema_alignment   : 20 pts   Price > 20EMA > 50EMA > 200EMA
  volume          : 12 pts   Vol ratio vs 20-day avg (scoring unchanged)
  breakout        : 15 pts   Close above recent resistance / consolidation break
  macd            : 10 pts   MACD line above signal, histogram expanding
  relative_strength:  8 pts  Ticker outperforming SPY over last 10 days
  atr_volatility  :  5 pts   ATR in healthy range (not too low, not spiking)
  sentiment       :  8 pts   News sentiment score contribution
  key_levels      :  5 pts   Close above prior swing high / key pivot
  geo_risk_raw    :  2 pts   Geo-risk absent = 2 pts, present = 0 pts
                             (separately, a geo risk penalty of -8 pts is
                              applied AFTER raw scoring — see score_ticker)
  TOTAL           : 100 pts raw; 92 pts max if geo risk detected

Post-scoring adjustment (CHANGE 4):
  Final score = raw_score - geo_penalty
  geo_penalty = 8 if geo_risk_detected else 0
  Score floor = 0 (cannot go below zero)
  Max possible with geo risk: 92.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import (
    GEO_RISK_PENALTY,
    RSI_MOMENTUM_LOWER,
    RSI_MOMENTUM_UPPER,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD_LOWER,
    RSI_OVERSOLD_UPPER,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Per-factor score breakdown plus metadata used by the alerting layer."""
    ticker: str
    raw_score: int = 0              # sum of 10 factors (0–100)
    final_score: int = 0            # raw_score minus geo_penalty, floor 0
    geo_risk_detected: bool = False
    geo_risk_penalty: int = 0       # 0 or GEO_RISK_PENALTY
    sentiment_score: float = 0.0    # raw sentiment value (e.g. -0.038)
    volume_ratio: float = 0.0       # latest vol / 20-day avg vol
    price: float = 0.0
    # Individual factor contributions
    factors: dict = field(default_factory=dict)
    # Debug info
    notes: list[str] = field(default_factory=list)


@dataclass
class SentimentResult:
    score: float = 0.0      # positive = bullish, negative = bearish
    label: str = "neutral"
    source: str = "news_api"


# ---------------------------------------------------------------------------
# Technical indicator helpers (IDENTICAL to v1.0)
# ---------------------------------------------------------------------------

def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = _compute_ema(close, fast)
    ema_slow = _compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def _compute_volume_ratio(df: pd.DataFrame, avg_period: int = 20) -> float:
    """Latest volume divided by 20-day average volume."""
    if len(df) < avg_period + 1:
        return 0.0
    avg_vol = df["Volume"].iloc[-avg_period - 1 : -1].mean()
    if avg_vol == 0:
        return 0.0
    return float(df["Volume"].iloc[-1]) / avg_vol


# ---------------------------------------------------------------------------
# Scoring functions (IDENTICAL factor logic to v1.0; only RSI ceiling changed)
# ---------------------------------------------------------------------------

def _score_rsi(close: pd.Series) -> tuple[int, str]:
    """
    15 pts total.
    Momentum zone [RSI_MOMENTUM_LOWER, RSI_MOMENTUM_UPPER]: full 15 pts.
    Oversold bounce [RSI_OVERSOLD_LOWER, RSI_OVERSOLD_UPPER] + recent cross: 12 pts.
    Neutral (not in either zone): 5 pts.
    Overbought (> RSI_OVERBOUGHT): 0 pts.

    CHANGE 6: RSI_MOMENTUM_UPPER is now 70 (was 65 in v1.0).
    """
    rsi_series = _compute_rsi(close)
    if rsi_series.isna().all():
        return 0, "RSI unavailable"
    rsi = float(rsi_series.iloc[-1])
    rsi_3d_ago = float(rsi_series.iloc[-4]) if len(rsi_series) >= 4 else rsi

    if rsi > RSI_OVERBOUGHT:
        return 0, f"RSI {rsi:.1f} — overbought (>{RSI_OVERBOUGHT})"
    if RSI_MOMENTUM_LOWER <= rsi <= RSI_MOMENTUM_UPPER:
        return 15, f"RSI {rsi:.1f} — in momentum zone [{RSI_MOMENTUM_LOWER}–{RSI_MOMENTUM_UPPER}]"
    if RSI_OVERSOLD_LOWER <= rsi <= RSI_OVERSOLD_UPPER:
        # Check if RSI crossed above 30 in last 3 days
        crossed_up = rsi_3d_ago < RSI_OVERSOLD_LOWER <= rsi or rsi_3d_ago <= rsi
        if crossed_up:
            return 12, f"RSI {rsi:.1f} — oversold bounce (crossed above {RSI_OVERSOLD_LOWER})"
        return 8, f"RSI {rsi:.1f} — in oversold zone (no recent cross)"
    return 5, f"RSI {rsi:.1f} — neutral zone"


def _score_ema_alignment(close: pd.Series) -> tuple[int, str]:
    """20 pts. Price > 20EMA > 50EMA > 200EMA = full marks."""
    if len(close) < 200:
        return 0, "Insufficient data for 200 EMA"
    ema20 = float(_compute_ema(close, 20).iloc[-1])
    ema50 = float(_compute_ema(close, 50).iloc[-1])
    ema200 = float(_compute_ema(close, 200).iloc[-1])
    price = float(close.iloc[-1])

    pts = 0
    notes = []
    if price > ema20:
        pts += 5
        notes.append("P>20EMA")
    if ema20 > ema50:
        pts += 5
        notes.append("20>50EMA")
    if ema50 > ema200:
        pts += 5
        notes.append("50>200EMA")
    if price > ema200:
        pts += 5
        notes.append("P>200EMA")
    score = min(pts, 20)
    return score, f"EMA alignment: {', '.join(notes)} → {score}/20"


def _score_volume(df: pd.DataFrame) -> tuple[int, float, str]:
    """12 pts. Returns (score, volume_ratio, note). Scoring unchanged from v1.0."""
    vol_ratio = _compute_volume_ratio(df)
    if vol_ratio >= 2.0:
        return 12, vol_ratio, f"Vol {vol_ratio:.2f}x — very strong"
    if vol_ratio >= 1.5:
        return 10, vol_ratio, f"Vol {vol_ratio:.2f}x — strong"
    if vol_ratio >= 1.3:
        return 8, vol_ratio, f"Vol {vol_ratio:.2f}x — above average"
    if vol_ratio >= 1.0:
        return 5, vol_ratio, f"Vol {vol_ratio:.2f}x — average"
    if vol_ratio >= 0.5:
        return 2, vol_ratio, f"Vol {vol_ratio:.2f}x — below average"
    return 0, vol_ratio, f"Vol {vol_ratio:.2f}x — very low (dead)"


def _score_breakout(df: pd.DataFrame) -> tuple[int, str]:
    """
    15 pts. Checks if price is breaking out above a recent consolidation range.
    Uses 20-day high/low to define the consolidation box.
    """
    if len(df) < 25:
        return 0, "Insufficient data for breakout check"
    # Consolidation box = high/low of days -25 to -5
    consolidation = df.iloc[-25:-5]
    box_high = float(consolidation["High"].max())
    box_low = float(consolidation["Low"].min())
    latest_close = float(df["Close"].iloc[-1])
    latest_high = float(df["High"].iloc[-1])

    box_range = box_high - box_low
    if box_range == 0:
        return 0, "Zero-range consolidation — skipping breakout"

    # Price is above the box AND within 3% of it (fresh breakout)
    if latest_close > box_high and (latest_close - box_high) / box_high <= 0.03:
        return 15, f"Fresh breakout above ${box_high:.2f} consolidation"
    if latest_close > box_high:
        return 10, f"Extended breakout above ${box_high:.2f} (>{3}% above box)"
    # Inside the box but in upper 30%
    pct_in_box = (latest_close - box_low) / box_range
    if pct_in_box >= 0.70:
        return 7, f"Near top of consolidation box (${box_low:.2f}–${box_high:.2f})"
    return 3, f"Inside consolidation box ({pct_in_box*100:.0f}% from bottom)"


def _score_macd(close: pd.Series) -> tuple[int, str]:
    """10 pts. MACD line above signal, histogram expanding."""
    if len(close) < 35:
        return 0, "Insufficient data for MACD"
    macd_line, signal_line, histogram = _compute_macd(close)
    m = float(macd_line.iloc[-1])
    s = float(signal_line.iloc[-1])
    h = float(histogram.iloc[-1])
    h_prev = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0.0

    if m > s and h > 0 and h > h_prev:
        return 10, f"MACD bullish + expanding histogram"
    if m > s and h > 0:
        return 7, "MACD above signal, histogram positive"
    if m > s:
        return 5, "MACD above signal (histogram negative)"
    return 0, "MACD bearish"


def _score_relative_strength(ticker_close: pd.Series, spy_close: pd.Series) -> tuple[int, str]:
    """8 pts. Ticker return vs SPY over last 10 days."""
    if len(ticker_close) < 11 or len(spy_close) < 11:
        return 4, "Insufficient data for RS calculation (neutral)"
    t_ret = (float(ticker_close.iloc[-1]) / float(ticker_close.iloc[-11]) - 1) * 100
    s_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-11]) - 1) * 100
    rs = t_ret - s_ret
    if rs >= 5:
        return 8, f"RS +{rs:.1f}% vs SPY — strong outperformance"
    if rs >= 2:
        return 6, f"RS +{rs:.1f}% vs SPY — moderate outperformance"
    if rs >= 0:
        return 4, f"RS +{rs:.1f}% vs SPY — slight outperformance"
    return 2, f"RS {rs:.1f}% vs SPY — underperforming"


def _score_atr_volatility(df: pd.DataFrame) -> tuple[int, str]:
    """5 pts. Healthy ATR = not suppressed, not spiking."""
    if len(df) < 20:
        return 2, "Insufficient data for ATR"
    atr = _compute_atr(df)
    atr_pct = float(atr.iloc[-1]) / float(df["Close"].iloc[-1]) * 100
    if 1.5 <= atr_pct <= 5.0:
        return 5, f"ATR {atr_pct:.1f}% — healthy volatility"
    if 0.8 <= atr_pct < 1.5:
        return 3, f"ATR {atr_pct:.1f}% — low volatility"
    if 5.0 < atr_pct <= 8.0:
        return 2, f"ATR {atr_pct:.1f}% — elevated volatility"
    return 0, f"ATR {atr_pct:.1f}% — extreme or suppressed"


def _score_sentiment(sentiment: Optional[SentimentResult]) -> tuple[int, float, str]:
    """8 pts. Returns (score, raw_sentiment_value, note)."""
    if sentiment is None:
        return 4, 0.0, "Sentiment unavailable (neutral default)"
    val = sentiment.score
    if val >= 0.5:
        return 8, val, f"Sentiment {val:.3f} — strongly positive"
    if val >= 0.1:
        return 6, val, f"Sentiment {val:.3f} — positive"
    if val >= 0:
        return 4, val, f"Sentiment {val:.3f} — neutral"
    if val >= -0.2:
        return 2, val, f"Sentiment {val:.3f} — slightly negative"
    return 0, val, f"Sentiment {val:.3f} — negative"


def _score_key_levels(df: pd.DataFrame) -> tuple[int, str]:
    """5 pts. Close above prior 5-day swing high."""
    if len(df) < 15:
        return 2, "Insufficient data for key levels"
    prior_swing_high = float(df["High"].iloc[-15:-5].max())
    latest_close = float(df["Close"].iloc[-1])
    if latest_close > prior_swing_high:
        return 5, f"Above prior swing high ${prior_swing_high:.2f}"
    gap_pct = (prior_swing_high - latest_close) / prior_swing_high * 100
    if gap_pct <= 1.5:
        return 3, f"Within {gap_pct:.1f}% of swing high ${prior_swing_high:.2f}"
    return 1, f"Below swing high ${prior_swing_high:.2f} by {gap_pct:.1f}%"


def _score_geo_risk_raw(geo_risk_detected: bool) -> tuple[int, str]:
    """
    2 pts raw component.
    Note: geo_risk_detected=True also triggers a separate -8 penalty applied
    after all factors are summed (see score_ticker).
    """
    if geo_risk_detected:
        return 0, "Geopolitical risk present (raw factor: 0/2)"
    return 2, "No geopolitical risk detected (2/2)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_ticker(
    ticker: str,
    df: pd.DataFrame,
    spy_df: Optional[pd.DataFrame] = None,
    sentiment: Optional[SentimentResult] = None,
    geo_risk_detected: bool = False,
) -> ScoreBreakdown:
    """
    Compute the full swing score for a ticker.

    Scoring flow:
      1. Compute all 10 factor scores (unchanged weights from v1.0).
      2. Sum to raw_score (0–100).
      3. If geo_risk_detected:
           final_score = max(0, raw_score - GEO_RISK_PENALTY)
         else:
           final_score = raw_score

    Parameters
    ----------
    ticker : str
    df     : OHLCV DataFrame (daily, at least 60 days recommended)
    spy_df : SPY OHLCV for relative-strength calculation
    sentiment : SentimentResult or None
    geo_risk_detected : bool

    Returns
    -------
    ScoreBreakdown with raw_score, final_score, and per-factor breakdown.

    Notes
    -----
    Final score = raw_score - geo_penalty. Max possible with geo risk: 92.
    """
    breakdown = ScoreBreakdown(ticker=ticker)
    close = df["Close"]

    # --- RSI (CHANGE 6: upper ceiling 70) ---
    rsi_pts, rsi_note = _score_rsi(close)
    breakdown.factors["rsi"] = {"score": rsi_pts, "note": rsi_note}

    # --- EMA alignment ---
    ema_pts, ema_note = _score_ema_alignment(close)
    breakdown.factors["ema_alignment"] = {"score": ema_pts, "note": ema_note}

    # --- Volume (scoring unchanged, tier dispatch happens in main.py) ---
    vol_pts, vol_ratio, vol_note = _score_volume(df)
    breakdown.factors["volume"] = {"score": vol_pts, "note": vol_note}
    breakdown.volume_ratio = vol_ratio

    # --- Breakout ---
    brk_pts, brk_note = _score_breakout(df)
    breakdown.factors["breakout"] = {"score": brk_pts, "note": brk_note}

    # --- MACD ---
    macd_pts, macd_note = _score_macd(close)
    breakdown.factors["macd"] = {"score": macd_pts, "note": macd_note}

    # --- Relative strength ---
    if spy_df is not None:
        rs_pts, rs_note = _score_relative_strength(close, spy_df["Close"])
    else:
        rs_pts, rs_note = 4, "SPY data unavailable (neutral default)"
    breakdown.factors["relative_strength"] = {"score": rs_pts, "note": rs_note}

    # --- ATR ---
    atr_pts, atr_note = _score_atr_volatility(df)
    breakdown.factors["atr_volatility"] = {"score": atr_pts, "note": atr_note}

    # --- Sentiment ---
    sent_pts, sent_val, sent_note = _score_sentiment(sentiment)
    breakdown.factors["sentiment"] = {"score": sent_pts, "note": sent_note}
    breakdown.sentiment_score = sent_val

    # --- Key levels ---
    kl_pts, kl_note = _score_key_levels(df)
    breakdown.factors["key_levels"] = {"score": kl_pts, "note": kl_note}

    # --- Geo risk raw ---
    geo_pts, geo_note = _score_geo_risk_raw(geo_risk_detected)
    breakdown.factors["geo_risk_raw"] = {"score": geo_pts, "note": geo_note}

    # --- Sum raw score ---
    raw = sum(f["score"] for f in breakdown.factors.values())
    breakdown.raw_score = min(raw, 100)

    # --- Apply geo penalty (CHANGE 4) ---
    breakdown.geo_risk_detected = geo_risk_detected
    if geo_risk_detected:
        breakdown.geo_risk_penalty = GEO_RISK_PENALTY
        breakdown.final_score = max(0, breakdown.raw_score - GEO_RISK_PENALTY)
        breakdown.notes.append(
            f"🌍 Geopolitical risk penalty applied: -{GEO_RISK_PENALTY}pts"
        )
    else:
        breakdown.geo_risk_penalty = 0
        breakdown.final_score = breakdown.raw_score

    # --- Price ---
    breakdown.price = float(close.iloc[-1])

    logger.debug(
        f"{ticker}: raw={breakdown.raw_score}, final={breakdown.final_score}, "
        f"vol={vol_ratio:.2f}x, sentiment={sent_val:.3f}, "
        f"geo_risk={geo_risk_detected}"
    )
    return breakdown
