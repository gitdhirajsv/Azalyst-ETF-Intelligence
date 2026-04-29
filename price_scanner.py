"""
price_scanner.py — AZALYST Price-Action Scanner (LEADING ENGINE)

The news engine is LAGGING — by the time RSS feeds publish "tariff exemption
on chips," SOXX is already up 4%. The price scanner inverts the flow:

    1. Scan the entire ETF universe daily (1D / 5D / 20D / 60D returns).
    2. Z-score returns vs trailing 60-day distribution.
    3. Flag abnormal movers (|z| ≥ 1.8) BEFORE news catches up.
    4. Detect technical regimes: breakouts, breakdowns, volume spikes,
       relative strength vs SPY, RSI extremes.
    5. Emit price-derived sector signals that feed the classifier.

This module catches moves 1-3 days BEFORE the news-only scanner does.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger("azalyst.price_scanner")


# ─────────────────────────────────────────────────────────────────────────────
# ETF universe → sector_id mapping (kept here for fast scanning).
# Keep in sync with etf_mapper.py SECTOR_TO_ETFS.
# ─────────────────────────────────────────────────────────────────────────────
ETF_TO_SECTOR: Dict[str, str] = {
    # Energy / Oil & Gas
    "XLE": "energy_oil", "USO": "energy_oil", "IXC": "energy_oil",
    "OIH": "energy_oil", "AMLP": "energy_oil", "XOP": "energy_oil",
    # Defense & Aerospace
    "ITA": "defense", "XAR": "defense", "PPA": "defense",
    "DEFENCEETF": "defense",
    # Gold & Precious Metals
    "GDX": "gold_precious_metals", "GDXJ": "gold_precious_metals",
    "GLDM": "gold_precious_metals", "GOLDBEES": "gold_precious_metals",
    "HDFCGOLD": "gold_precious_metals", "SLV": "gold_precious_metals",
    "PHYS": "gold_precious_metals",
    # Technology & AI / Semiconductors
    "SOXX": "technology_ai", "SMH": "technology_ai", "QQQ": "technology_ai",
    "QQQM": "technology_ai", "AIQ": "technology_ai", "MAFANG": "technology_ai",
    "BOTZ": "technology_ai", "ROBO": "technology_ai", "XLK": "technology_ai",
    "VGT": "technology_ai", "FTEC": "technology_ai", "IGV": "technology_ai",
    "XSD": "technology_ai", "PSI": "technology_ai",
    # Nuclear & Uranium
    "URA": "nuclear_uranium", "URNM": "nuclear_uranium", "SRUUF": "nuclear_uranium",
    "NLR": "nuclear_uranium", "CPSEETF": "nuclear_uranium",
    # Cybersecurity
    "HACK": "cybersecurity", "CIBR": "cybersecurity", "BUG": "cybersecurity",
    "WCBR": "cybersecurity",
    # India Equity
    "INDA": "india_equity", "NIFTYBEES": "india_equity",
    "MIDCAPETF": "india_equity", "BANKBEES": "india_equity",
    "PSUBNKBEES": "india_equity", "FLAX": "india_equity", "EPI": "india_equity",
    "INDY": "india_equity",
    # Crypto & Digital Assets
    "IBIT": "crypto_digital", "BITQ": "crypto_digital", "GBTC": "crypto_digital",
    "ETHE": "crypto_digital", "ETHA": "crypto_digital", "FBTC": "crypto_digital",
    # Banking & Financial
    "XLF": "banking_financial", "KBE": "banking_financial",
    "KRE": "banking_financial", "VFH": "banking_financial",
    # Commodities & Mining
    "COPP": "commodities_mining", "DBC": "commodities_mining",
    "COPX": "commodities_mining", "PICK": "commodities_mining",
    "REMX": "commodities_mining", "LIT": "commodities_mining",
    # Emerging Markets
    "EEM": "emerging_markets", "SPEM": "emerging_markets",
    "FXI": "emerging_markets", "VWO": "emerging_markets",
    "MCHI": "emerging_markets", "EWZ": "emerging_markets",
    # Healthcare & Pharma
    "XLV": "healthcare_pharma", "IXJ": "healthcare_pharma",
    "XBI": "healthcare_pharma", "IBB": "healthcare_pharma",
    "PHARMABEES": "healthcare_pharma", "HEALTHCARE": "healthcare_pharma",
    # Clean Energy & Renewables
    "ICLN": "clean_energy_renewables", "QCLN": "clean_energy_renewables",
    "PBW": "clean_energy_renewables", "TAN": "clean_energy_renewables",
    "FAN": "clean_energy_renewables", "NEWENERGY": "clean_energy_renewables",
    # Real Estate & REITs
    "VNQ": "real_estate_reit", "REET": "real_estate_reit",
    "REALTY": "real_estate_reit", "XLRE": "real_estate_reit",
    "IYR": "real_estate_reit",
    # Bonds & Fixed Income
    "BND": "bonds_fixed_income", "TLT": "bonds_fixed_income",
    "TIP": "bonds_fixed_income", "BHARATBOND": "bonds_fixed_income",
    "AGG": "bonds_fixed_income", "LQD": "bonds_fixed_income",
    "HYG": "bonds_fixed_income", "JNK": "bonds_fixed_income",
    # Asia Pacific Equity
    "EWJ": "asia_pacific", "EWY": "asia_pacific", "EWA": "asia_pacific",
    "EWT": "asia_pacific", "EWS": "asia_pacific",
    # Europe Equity
    "VGK": "europe_equity", "EWG": "europe_equity", "EWU": "europe_equity",
    "IEV": "europe_equity", "EZU": "europe_equity",
}

BENCHMARK_TICKER = "SPY"   # for relative strength
VIX_TICKER = "^VIX"         # market regime gauge


# ─────────────────────────────────────────────────────────────────────────────
# Data containers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PriceSignal:
    """A single price-derived signal for one ETF."""
    ticker: str
    sector_id: str
    last_price: float
    ret_1d: float
    ret_5d: float
    ret_20d: float
    ret_60d: float
    z_1d: float
    z_5d: float
    z_20d: float
    rs_vs_spy_20d: float           # relative strength vs SPY
    above_50ma: bool
    above_200ma: bool
    breakout_20d_high: bool         # closed above 20-day high
    breakdown_20d_low: bool         # closed below 20-day low
    rsi_14: float
    volume_ratio: float             # today's vol / 20D avg
    direction: str                  # BULLISH / BEARISH / NEUTRAL
    strength: float                 # 0-100 composite strength
    flags: List[str] = field(default_factory=list)
    asof: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_signal_dict(self) -> Dict:
        """Convert into the same dict shape the news classifier emits, so it
        can flow through the existing scorer/state/reporter pipeline."""
        return {
            "sector_id": self.sector_id,
            "sectors": [self.sector_id],
            "source_engine": "price_action",
            "ticker_driver": self.ticker,
            "price_signal": asdict(self),
            "direction": self.direction,
            "direction_score": self._direction_score(),
            "severity": self._severity(),
            "event_intensity": self.strength / 5.0,
            "regions": ["global"],
            "sources": ["yfinance_price_action"],
            "articles": [],
            "article_count": 0,
            "total_score": self.strength * 0.35,   # comparable to news total_score
            "avg_article_score": self.strength * 0.05,
            "top_headlines": [
                f"{self.ticker} {self.direction.lower()} momentum: "
                f"{self.ret_1d:+.2f}% 1D / {self.ret_5d:+.2f}% 5D / "
                f"{self.ret_20d:+.2f}% 20D, z={self.z_5d:+.2f}σ"
            ],
            "latest_ts": self.asof,
            "ml_sentiment_label": "NEUTRAL",
            "ml_sentiment_score": 0.0,
            "ml_sentiment_model": "n/a",
            "ml_sentiment_mode": "n/a",
        }

    def _direction_score(self) -> float:
        """Convert to the same direction_score scale the classifier uses."""
        score = self.z_5d * 1.5 + self.z_20d * 0.8
        if self.breakout_20d_high:
            score += 3
        if self.breakdown_20d_low:
            score -= 3
        if self.rsi_14 >= 70:
            score += 1
        if self.rsi_14 <= 30:
            score -= 1
        return round(score, 2)

    def _severity(self) -> str:
        s = abs(self.z_5d)
        if s >= 2.5 or self.strength >= 75:
            return "CRITICAL"
        if s >= 1.8 or self.strength >= 60:
            return "HIGH"
        if s >= 1.2 or self.strength >= 40:
            return "MEDIUM"
        return "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Indicators
# ─────────────────────────────────────────────────────────────────────────────
def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    if len(delta) < period:
        return 50.0
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.rolling(period).mean().iloc[-1]
    avg_loss = losses.rolling(period).mean().iloc[-1]
    if avg_loss == 0 or pd.isna(avg_loss):
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _zscore(series: pd.Series, value: float) -> float:
    """Z-score of `value` against the distribution of `series`."""
    s = series.dropna()
    if len(s) < 5:
        return 0.0
    std = s.std()
    if std == 0 or pd.isna(std):
        return 0.0
    return float((value - s.mean()) / std)


def _safe_pct(curr: float, prev: float) -> float:
    if prev is None or prev == 0 or pd.isna(prev):
        return 0.0
    return float((curr - prev) / prev * 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# Price Scanner
# ─────────────────────────────────────────────────────────────────────────────
class PriceScanner:
    """
    Scan the ETF universe and emit price-derived signals.

    Signals are emitted only when at least one abnormal-move criterion is met,
    keeping signal-to-noise high. The downstream classifier will fuse these
    with news-derived signals.
    """

    # Strength thresholds for emitting a signal
    Z_THRESHOLD = 1.8        # |5D z-score| ≥ 1.8 → flagged
    RET_5D_THRESHOLD = 3.0   # |5D return| ≥ 3.0% → flagged
    BREAKOUT_BUFFER_BPS = 5  # within 5bps of 20D high counts as breakout

    def __init__(self, tickers: Optional[List[str]] = None,
                 lookback_days: int = 260):
        self.tickers = tickers or list(ETF_TO_SECTOR.keys())
        self.lookback_days = lookback_days
        self._spy_returns: Optional[pd.Series] = None

    # ── Data fetch ─────────────────────────────────────────────────────────
    def _fetch_history(self, tickers: List[str]) -> pd.DataFrame:
        """Bulk-download history for many tickers in one call (fast)."""
        try:
            df = yf.download(
                tickers + [BENCHMARK_TICKER],
                period=f"{self.lookback_days}d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
            return df
        except Exception as exc:
            log.warning("Bulk download failed (%s); falling back to per-ticker.", exc)
            return pd.DataFrame()

    def _ticker_frame(self, df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
        """Extract a clean OHLCV frame for one ticker from the multiindex bulk df."""
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if ticker not in df.columns.get_level_values(0):
                    return None
                sub = df[ticker].dropna(how="all")
            else:
                sub = df.dropna(how="all")
            if sub.empty or len(sub) < 30:
                return None
            return sub
        except Exception:
            return None

    # ── Per-ticker analysis ────────────────────────────────────────────────
    def _analyze(self, ticker: str, frame: pd.DataFrame,
                 spy_close: Optional[pd.Series]) -> Optional[PriceSignal]:
        if frame is None or frame.empty or "Close" not in frame:
            return None
        close = frame["Close"].dropna()
        volume = frame["Volume"].dropna() if "Volume" in frame else pd.Series(dtype=float)
        if len(close) < 60:
            return None

        last = float(close.iloc[-1])
        ret_1d = _safe_pct(last, float(close.iloc[-2]))
        ret_5d = _safe_pct(last, float(close.iloc[-6])) if len(close) > 6 else 0.0
        ret_20d = _safe_pct(last, float(close.iloc[-21])) if len(close) > 21 else 0.0
        ret_60d = _safe_pct(last, float(close.iloc[-61])) if len(close) > 61 else 0.0

        # Daily return distribution → z-scores
        daily = close.pct_change().dropna()
        z_1d = _zscore(daily.iloc[-60:], daily.iloc[-1]) if len(daily) >= 60 else 0.0
        ret5_series = close.pct_change(5).dropna()
        z_5d = _zscore(ret5_series.iloc[-60:], ret5_series.iloc[-1]) if len(ret5_series) >= 30 else 0.0
        ret20_series = close.pct_change(20).dropna()
        z_20d = _zscore(ret20_series.iloc[-60:], ret20_series.iloc[-1]) if len(ret20_series) >= 30 else 0.0

        # Moving averages
        ma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else last
        ma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else last
        above_50 = last > ma_50
        above_200 = last > ma_200

        # 20D breakout / breakdown
        h20 = float(close.iloc[-21:-1].max()) if len(close) > 21 else last
        l20 = float(close.iloc[-21:-1].min()) if len(close) > 21 else last
        buf = 1 - self.BREAKOUT_BUFFER_BPS / 10000
        breakout = last >= h20 * (1 + self.BREAKOUT_BUFFER_BPS / 10000)
        breakdown = last <= l20 * buf

        # RSI(14)
        rsi = _rsi(close, 14)

        # Volume ratio
        vol_ratio = 1.0
        if not volume.empty and len(volume) >= 20:
            avg20 = float(volume.iloc[-21:-1].mean())
            today = float(volume.iloc[-1])
            if avg20 > 0:
                vol_ratio = today / avg20

        # Relative strength vs SPY (20D excess return)
        rs_vs_spy = 0.0
        if spy_close is not None and len(spy_close) > 21:
            spy_20 = _safe_pct(float(spy_close.iloc[-1]), float(spy_close.iloc[-21]))
            rs_vs_spy = ret_20d - spy_20

        # ── Direction + composite strength ────────────────────────────────
        flags: List[str] = []
        if breakout: flags.append("20D_BREAKOUT")
        if breakdown: flags.append("20D_BREAKDOWN")
        if vol_ratio >= 1.8: flags.append("VOLUME_SPIKE")
        if rsi >= 70: flags.append("RSI_OVERBOUGHT")
        if rsi <= 30: flags.append("RSI_OVERSOLD")
        if rs_vs_spy >= 3.0: flags.append("RS_LEADER")
        if rs_vs_spy <= -3.0: flags.append("RS_LAGGARD")
        if above_50 and above_200 and ret_60d > 5: flags.append("UPTREND")
        if not above_50 and not above_200 and ret_60d < -5: flags.append("DOWNTREND")

        # Composite strength: combine z-scores, breakouts, volume, RS
        bull_pts = (
            max(z_5d, 0) * 12
            + max(z_20d, 0) * 6
            + (10 if breakout else 0)
            + (8 if vol_ratio >= 1.8 else 0)
            + max(rs_vs_spy, 0) * 1.5
            + (5 if above_50 and above_200 else 0)
        )
        bear_pts = (
            max(-z_5d, 0) * 12
            + max(-z_20d, 0) * 6
            + (10 if breakdown else 0)
            + max(-rs_vs_spy, 0) * 1.5
            + (5 if not above_50 and not above_200 else 0)
        )
        net = bull_pts - bear_pts
        strength = min(abs(net), 100.0)

        if net >= 8:
            direction = "BULLISH"
        elif net <= -8:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Threshold gate: only emit signal if abnormal
        if (
            abs(z_5d) < self.Z_THRESHOLD
            and abs(ret_5d) < self.RET_5D_THRESHOLD
            and not breakout and not breakdown
            and abs(rs_vs_spy) < 4.0
        ):
            return None

        return PriceSignal(
            ticker=ticker,
            sector_id=ETF_TO_SECTOR.get(ticker, "unknown"),
            last_price=round(last, 2),
            ret_1d=round(ret_1d, 2),
            ret_5d=round(ret_5d, 2),
            ret_20d=round(ret_20d, 2),
            ret_60d=round(ret_60d, 2),
            z_1d=round(z_1d, 2),
            z_5d=round(z_5d, 2),
            z_20d=round(z_20d, 2),
            rs_vs_spy_20d=round(rs_vs_spy, 2),
            above_50ma=bool(above_50),
            above_200ma=bool(above_200),
            breakout_20d_high=bool(breakout),
            breakdown_20d_low=bool(breakdown),
            rsi_14=round(rsi, 1),
            volume_ratio=round(vol_ratio, 2),
            direction=direction,
            strength=round(strength, 1),
            flags=flags,
        )

    # ── Public API ─────────────────────────────────────────────────────────
    def scan(self) -> List[PriceSignal]:
        """Run a full scan and return ranked PriceSignal objects."""
        log.info("Price scan starting on %d tickers...", len(self.tickers))
        df = self._fetch_history(self.tickers)
        if df.empty:
            log.warning("No price data fetched — skipping price scan.")
            return []

        # Pull SPY series for relative strength
        spy_frame = self._ticker_frame(df, BENCHMARK_TICKER)
        spy_close = spy_frame["Close"].dropna() if spy_frame is not None else None

        signals: List[PriceSignal] = []
        for tk in self.tickers:
            try:
                frame = self._ticker_frame(df, tk)
                if frame is None:
                    continue
                sig = self._analyze(tk, frame, spy_close)
                if sig is not None:
                    signals.append(sig)
            except Exception as exc:
                log.warning("Price analysis failed for %s: %s", tk, exc)

        # Sort: strongest abnormal moves first
        signals.sort(key=lambda s: (-abs(s.z_5d), -s.strength))
        log.info("Price scan done: %d abnormal-move signals from %d ETFs.",
                 len(signals), len(self.tickers))
        return signals

    def aggregate_by_sector(self, signals: List[PriceSignal]) -> List[Dict]:
        """
        Roll per-ETF signals up to one signal per sector (the leader inside
        the sector). Returns dicts compatible with the news-signal pipeline.
        """
        by_sector: Dict[str, List[PriceSignal]] = {}
        for s in signals:
            by_sector.setdefault(s.sector_id, []).append(s)

        merged: List[Dict] = []
        for sector_id, group in by_sector.items():
            # Pick leader by absolute strength
            group.sort(key=lambda s: -s.strength)
            leader = group[0]
            sig_dict = leader.to_signal_dict()
            # Surface the full leaderboard as supporting evidence
            sig_dict["price_supporters"] = [
                {"ticker": s.ticker, "ret_5d": s.ret_5d, "z_5d": s.z_5d,
                 "direction": s.direction, "flags": s.flags}
                for s in group
            ]
            sig_dict["sector_label"] = self._sector_label(sector_id)
            sig_dict["sector_emoji"] = "📈" if leader.direction == "BULLISH" else "📉"
            merged.append(sig_dict)

        # Strongest first
        merged.sort(key=lambda d: -d.get("event_intensity", 0))
        return merged

    @staticmethod
    def _sector_label(sector_id: str) -> str:
        labels = {
            "energy_oil": "Energy / Oil & Gas",
            "defense": "Defense & Aerospace",
            "gold_precious_metals": "Gold & Precious Metals",
            "technology_ai": "Technology & AI / Semiconductors",
            "nuclear_uranium": "Nuclear Energy & Uranium",
            "cybersecurity": "Cybersecurity",
            "india_equity": "India Equity Markets",
            "crypto_digital": "Crypto & Digital Assets",
            "banking_financial": "Banking & Financial Sector",
            "commodities_mining": "Commodities & Mining",
            "emerging_markets": "Emerging Markets",
            "healthcare_pharma": "Healthcare & Pharma",
            "clean_energy_renewables": "Clean Energy & Renewables",
            "real_estate_reit": "Real Estate & REITs",
            "bonds_fixed_income": "Bonds & Fixed Income",
            "asia_pacific": "Asia Pacific Equity",
            "europe_equity": "Europe Equity",
        }
        return labels.get(sector_id, sector_id.title())


# ─────────────────────────────────────────────────────────────────────────────
# CLI for ad-hoc runs (debugging / GitHub Actions)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    scanner = PriceScanner()
    sigs = scanner.scan()
    print(f"\n{'TICKER':<8} {'SEC':<26} {'1D%':>7} {'5D%':>7} {'20D%':>7} "
          f"{'z5d':>6} {'RSvSPY':>7} {'RSI':>5} {'DIR':<8} {'STR':>5} FLAGS")
    print("─" * 130)
    for s in sigs[:40]:
        print(f"{s.ticker:<8} {s.sector_id:<26} {s.ret_1d:>+7.2f} "
              f"{s.ret_5d:>+7.2f} {s.ret_20d:>+7.2f} {s.z_5d:>+6.2f} "
              f"{s.rs_vs_spy_20d:>+7.2f} {s.rsi_14:>5.1f} "
              f"{s.direction:<8} {s.strength:>5.1f} {','.join(s.flags)}")
