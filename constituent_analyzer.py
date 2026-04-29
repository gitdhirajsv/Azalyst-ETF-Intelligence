"""
constituent_analyzer.py — AZALYST ETF Constituent Drill-Down

ETFs are wrappers. SOXX = NVDA + AVGO + TSM + AMD + ... When a sector ETF
moves, ONE or TWO underlying stocks usually drive the bulk of the move.
Catching that single-stock signal early can flag the sector rotation
1-2 days before the ETF's aggregate price shows it.

This module:
  1. Holds top-holdings for each tracked ETF (curated + verified).
  2. Scans all unique underlying stocks for the same momentum/breakout
     signals as the price scanner.
  3. Identifies which constituents are leading the move.
  4. Aggregates: if ≥3 of SOXX's top 5 holdings are flagged bullish on the
     same day, that's high-conviction sector rotation BEFORE SOXX confirms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import pandas as pd
import yfinance as yf

from price_scanner import _rsi, _zscore, _safe_pct

log = logging.getLogger("azalyst.constituents")


# ─────────────────────────────────────────────────────────────────────────────
# Top holdings per tracked ETF (manually curated for accuracy + speed).
# Update quarterly to track index reconstitutions.
# ─────────────────────────────────────────────────────────────────────────────
ETF_HOLDINGS: Dict[str, List[str]] = {
    # Semiconductors
    "SOXX": ["NVDA", "AVGO", "TSM", "AMD", "QCOM", "TXN", "AMAT", "INTC", "MU", "LRCX"],
    "SMH":  ["NVDA", "TSM", "AVGO", "AMD", "ASML", "QCOM", "AMAT", "TXN", "MU", "INTC"],
    "XSD":  ["MU", "ON", "MPWR", "SWKS", "MCHP", "QRVO", "LSCC", "NVDA", "AMD", "WOLF"],
    # Tech / AI
    "QQQ":  ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"],
    "QQQM": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"],
    "AIQ":  ["NVDA", "META", "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "AVGO", "AMD", "CRM"],
    "XLK":  ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN"],
    "BOTZ": ["NVDA", "ABB", "ISRG", "FANUY", "KEYS", "DT", "UPST", "OMRNY", "DSY.PA", "HONGKONG"],
    # Energy
    "XLE":  ["XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "WMB", "OKE", "VLO"],
    "USO":  ["CL=F"],   # crude oil futures proxy
    "OIH":  ["SLB", "BKR", "HAL", "TS", "FTI", "WFRD", "NOV", "RIG", "OII", "VAL"],
    # Defense
    "ITA":  ["RTX", "BA", "LMT", "GE", "TDG", "NOC", "GD", "AXON", "HII", "TXT"],
    "XAR":  ["AXON", "BA", "RTX", "LMT", "NOC", "GD", "HII", "TXT", "HEI", "CW"],
    # Gold miners
    "GDX":  ["NEM", "GOLD", "AEM", "WPM", "FNV", "AU", "KGC", "GFI", "RGLD", "PAAS"],
    "GDXJ": ["PAAS", "AGI", "EQX", "BTG", "HMY", "OGC", "NGD", "MAG", "OR", "FSM"],
    # Financials
    "XLF":  ["BRK.B", "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "AXP", "C"],
    "KBE":  ["JPM", "BAC", "WFC", "C", "USB", "PNC", "TFC", "MTB", "FITB", "RF"],
    # Healthcare
    "XLV":  ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "ISRG", "PFE", "DHR"],
    "XBI":  ["ASND", "VRTX", "MRNA", "REGN", "BMRN", "INCY", "ALNY", "BIIB", "GILD", "EXEL"],
    # Crypto proxies
    "IBIT": ["BTC-USD"],
    "BITQ": ["MSTR", "COIN", "MARA", "RIOT", "CIFR", "CLSK", "HUT", "CORZ", "BITF", "GLXY"],
    # Cybersecurity
    "HACK": ["CRWD", "PANW", "FTNT", "ZS", "OKTA", "S", "QLYS", "TENB", "RPD", "VRNS"],
    "CIBR": ["CRWD", "PANW", "FTNT", "ZS", "CSCO", "BAH", "OKTA", "FFIV", "INFA", "S"],
    # Uranium
    "URNM": ["CCJ", "PDN.AX", "BHP", "DML.TO", "NXE", "URA", "EU", "FCU.TO", "UEC", "DNN"],
    "URA":  ["CCJ", "NXE", "DNN", "UEC", "PDN.AX", "URG", "BHP", "EU", "FCU.TO", "URNM"],
    # Clean energy
    "ICLN": ["FSLR", "ENPH", "SEDG", "PLUG", "BE", "RUN", "NEE", "GEV", "ORSTED.CO", "VWS.CO"],
    "TAN":  ["FSLR", "ENPH", "SEDG", "RUN", "ARRY", "NXT", "MAXN", "SHLS", "NOVA", "JKS"],
    # Real estate
    "VNQ":  ["PLD", "AMT", "EQIX", "WELL", "DLR", "PSA", "O", "SPG", "EXR", "VICI"],
    # Commodities / mining
    "COPX": ["FCX", "BHP", "RIO", "GLEN.L", "TECK", "ANTO.L", "FM.TO", "LUN.TO", "HBM.TO", "ERO"],
    "LIT":  ["ALB", "SQM", "GMEXICOB.MX", "GANFENG", "PILBARA.AX", "MIN.AX", "TLOFY", "LIT", "MP", "TSLA"],
    # Bonds (single instruments, no constituents needed)
    # Emerging markets
    "EEM":  ["TSM", "TCEHY", "SSNLF", "BABA", "MELI", "INFY", "RELIANCE.NS", "PDD", "9988.HK", "HDB"],
    "FXI":  ["BABA", "TCEHY", "JD", "MELI", "PDD", "BIDU", "NTES", "NIO", "LI", "BIDU"],
    "MCHI": ["TCEHY", "BABA", "9988.HK", "MEITUAN", "PDD", "JD", "BIDU", "NTES", "NIO", "LI"],
    "EWZ":  ["VALE", "ITUB", "PBR", "BBD", "B3SA3.SA", "WEGE3.SA", "ABEV3.SA", "BPAC11.SA", "RDOR3.SA", "RAIL3.SA"],
    # Asia Pacific
    "EWJ":  ["7203.T", "8058.T", "8035.T", "9984.T", "6758.T", "6098.T", "8001.T", "6857.T", "8316.T", "9433.T"],
    "EWY":  ["005930.KS", "000660.KS", "035420.KS", "005380.KS", "051910.KS", "207940.KS", "035720.KS"],
    "EWT":  ["TSM", "2317.TW", "2454.TW", "2382.TW", "2308.TW", "2882.TW", "2891.TW"],
    # Europe
    "VGK":  ["NVO", "NESN.SW", "ASML", "SHEL", "AZN", "RHHBY", "LVMHF", "SAP", "TM", "ROG.SW"],
    "EWG":  ["SAP", "SIE.DE", "ALV.DE", "DTE.DE", "MUV2.DE", "BAS.DE", "DBK.DE", "BMW.DE", "MBG.DE"],
}


@dataclass
class ConstituentSignal:
    ticker: str
    parent_etf: str
    sector_id: str
    last_price: float
    ret_1d: float
    ret_5d: float
    ret_20d: float
    z_5d: float
    rsi_14: float
    volume_ratio: float
    direction: str
    flags: List[str] = field(default_factory=list)


@dataclass
class SectorRotationSignal:
    """Aggregated signal: when many constituents of a sector ETF move
    together, that's a higher-conviction rotation signal."""
    sector_id: str
    parent_etf: str
    bullish_count: int
    bearish_count: int
    total_constituents: int
    avg_ret_5d: float
    leaders: List[ConstituentSignal] = field(default_factory=list)
    laggards: List[ConstituentSignal] = field(default_factory=list)
    direction: str = "NEUTRAL"
    conviction: float = 0.0
    asof: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_signal_dict(self) -> Dict:
        return {
            "sector_id": self.sector_id,
            "sectors": [self.sector_id],
            "source_engine": "constituent_rotation",
            "ticker_driver": self.parent_etf,
            "direction": self.direction,
            "direction_score": (self.bullish_count - self.bearish_count) * 1.5,
            "severity": "HIGH" if self.conviction >= 60 else
                        "MEDIUM" if self.conviction >= 40 else "LOW",
            "event_intensity": min(self.conviction / 5.0, 20.0),
            "regions": ["global"],
            "sources": ["yfinance_constituent_rotation"],
            "articles": [],
            "article_count": 0,
            "total_score": self.conviction * 0.4,
            "avg_article_score": 0.0,
            "top_headlines": [
                f"{self.parent_etf} rotation: "
                f"{self.bullish_count}/{self.total_constituents} constituents bullish, "
                f"avg 5D {self.avg_ret_5d:+.2f}%; "
                f"leaders: {', '.join(s.ticker for s in self.leaders[:3])}"
            ],
            "latest_ts": self.asof,
            "constituent_evidence": {
                "leaders": [asdict(s) for s in self.leaders],
                "laggards": [asdict(s) for s in self.laggards],
                "bullish_count": self.bullish_count,
                "bearish_count": self.bearish_count,
                "conviction": self.conviction,
            },
            "ml_sentiment_label": "NEUTRAL",
            "ml_sentiment_score": 0.0,
            "ml_sentiment_model": "n/a",
            "ml_sentiment_mode": "n/a",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Analyzer
# ─────────────────────────────────────────────────────────────────────────────
class ConstituentAnalyzer:
    """
    Drills into top holdings of every tracked ETF and aggregates their
    momentum into sector-rotation signals.
    """

    Z_THRESHOLD = 1.5
    RET_5D_THRESHOLD = 4.0
    MIN_CONVICTION_RATIO = 0.4   # ≥40% of constituents agree → emit signal

    def __init__(self, etf_to_sector: Dict[str, str],
                 holdings: Optional[Dict[str, List[str]]] = None,
                 lookback_days: int = 90):
        self.etf_to_sector = etf_to_sector
        self.holdings = holdings or ETF_HOLDINGS
        self.lookback_days = lookback_days

    def _all_unique_constituents(self, etfs: List[str]) -> Set[str]:
        out: Set[str] = set()
        for etf in etfs:
            out.update(self.holdings.get(etf, []))
        return {t for t in out if t and not t.endswith("=F")}  # skip futures

    def _bulk_history(self, tickers: List[str]) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()
        try:
            return yf.download(
                tickers,
                period=f"{self.lookback_days}d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:
            log.warning("Constituent download failed: %s", exc)
            return pd.DataFrame()

    def _ticker_frame(self, df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if ticker not in df.columns.get_level_values(0):
                    return None
                sub = df[ticker].dropna(how="all")
            else:
                sub = df.dropna(how="all")
            if sub.empty or len(sub) < 25:
                return None
            return sub
        except Exception:
            return None

    def _analyze_stock(self, ticker: str, parent_etf: str,
                       frame: pd.DataFrame) -> Optional[ConstituentSignal]:
        if frame is None or frame.empty or "Close" not in frame:
            return None
        close = frame["Close"].dropna()
        volume = frame["Volume"].dropna() if "Volume" in frame else pd.Series(dtype=float)
        if len(close) < 25:
            return None

        last = float(close.iloc[-1])
        ret_1d = _safe_pct(last, float(close.iloc[-2]))
        ret_5d = _safe_pct(last, float(close.iloc[-6])) if len(close) > 6 else 0.0
        ret_20d = _safe_pct(last, float(close.iloc[-21])) if len(close) > 21 else 0.0

        ret5_series = close.pct_change(5).dropna()
        z_5d = _zscore(ret5_series.iloc[-60:], ret5_series.iloc[-1]) if len(ret5_series) >= 25 else 0.0

        rsi = _rsi(close, 14)

        vol_ratio = 1.0
        if not volume.empty and len(volume) >= 20:
            avg20 = float(volume.iloc[-21:-1].mean())
            today = float(volume.iloc[-1])
            if avg20 > 0:
                vol_ratio = today / avg20

        flags: List[str] = []
        if vol_ratio >= 2.0: flags.append("VOLUME_SPIKE")
        if rsi >= 75: flags.append("RSI_OVERBOUGHT")
        if rsi <= 25: flags.append("RSI_OVERSOLD")
        if abs(z_5d) >= 2.0: flags.append("Z_OUTLIER")

        if z_5d >= 1.0 or ret_5d >= 3.0:
            direction = "BULLISH"
        elif z_5d <= -1.0 or ret_5d <= -3.0:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Threshold: only return if move is meaningful
        if abs(z_5d) < 0.8 and abs(ret_5d) < 2.0 and not flags:
            return None

        return ConstituentSignal(
            ticker=ticker,
            parent_etf=parent_etf,
            sector_id=self.etf_to_sector.get(parent_etf, "unknown"),
            last_price=round(last, 2),
            ret_1d=round(ret_1d, 2),
            ret_5d=round(ret_5d, 2),
            ret_20d=round(ret_20d, 2),
            z_5d=round(z_5d, 2),
            rsi_14=round(rsi, 1),
            volume_ratio=round(vol_ratio, 2),
            direction=direction,
            flags=flags,
        )

    def scan(self) -> List[SectorRotationSignal]:
        """Run constituent scan; return one rotation signal per qualifying sector."""
        etfs_to_scan = [e for e in self.etf_to_sector if e in self.holdings]
        all_stocks = list(self._all_unique_constituents(etfs_to_scan))
        if not all_stocks:
            return []

        log.info("Constituent scan on %d unique stocks across %d ETFs",
                 len(all_stocks), len(etfs_to_scan))
        df = self._bulk_history(all_stocks)
        if df.empty:
            return []

        # First pass: per-stock signal
        per_stock: Dict[str, ConstituentSignal] = {}
        for stock in all_stocks:
            try:
                frame = self._ticker_frame(df, stock)
                if frame is None:
                    continue
                # Pick first parent ETF for tagging (a stock can be in many)
                parent = next(
                    (etf for etf, h in self.holdings.items() if stock in h),
                    "",
                )
                sig = self._analyze_stock(stock, parent, frame)
                if sig is not None:
                    per_stock[stock] = sig
            except Exception as exc:
                log.debug("Constituent analysis failed for %s: %s", stock, exc)

        # Second pass: aggregate per ETF/sector
        rotations: List[SectorRotationSignal] = []
        for etf in etfs_to_scan:
            constituents = self.holdings.get(etf, [])
            if not constituents:
                continue
            group = [per_stock[t] for t in constituents if t in per_stock]
            if not group:
                continue

            bullish = [s for s in group if s.direction == "BULLISH"]
            bearish = [s for s in group if s.direction == "BEARISH"]
            ratio_b = len(bullish) / len(constituents)
            ratio_s = len(bearish) / len(constituents)
            if max(ratio_b, ratio_s) < self.MIN_CONVICTION_RATIO:
                continue

            avg_ret_5d = sum(s.ret_5d for s in group) / len(group)
            leaders = sorted(bullish, key=lambda s: -s.ret_5d)[:5] if ratio_b >= ratio_s else []
            laggards = sorted(bearish, key=lambda s: s.ret_5d)[:5] if ratio_s > ratio_b else []
            direction = "BULLISH" if ratio_b > ratio_s else "BEARISH"

            # Conviction: % of constituents agreeing × avg move strength
            agree_count = max(len(bullish), len(bearish))
            conviction = (
                (agree_count / len(constituents)) * 60
                + min(abs(avg_ret_5d) * 4, 40)
            )

            rotations.append(SectorRotationSignal(
                sector_id=self.etf_to_sector.get(etf, "unknown"),
                parent_etf=etf,
                bullish_count=len(bullish),
                bearish_count=len(bearish),
                total_constituents=len(constituents),
                avg_ret_5d=round(avg_ret_5d, 2),
                leaders=leaders,
                laggards=laggards,
                direction=direction,
                conviction=round(conviction, 1),
            ))

        rotations.sort(key=lambda r: -r.conviction)
        log.info("Constituent scan emitted %d rotation signals", len(rotations))
        return rotations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from price_scanner import ETF_TO_SECTOR
    a = ConstituentAnalyzer(ETF_TO_SECTOR)
    rs = a.scan()
    for r in rs:
        print(f"\n[{r.parent_etf} → {r.sector_id}]  {r.direction}  conviction={r.conviction}")
        print(f"  bull={r.bullish_count}/{r.total_constituents}  "
              f"bear={r.bearish_count}/{r.total_constituents}  "
              f"avg_5d={r.avg_ret_5d:+.2f}%")
        for s in r.leaders[:3]:
            print(f"    LEAD  {s.ticker:<10}  5D {s.ret_5d:+6.2f}%  z {s.z_5d:+.2f}  RSI {s.rsi_14}")
        for s in r.laggards[:3]:
            print(f"    LAG   {s.ticker:<10}  5D {s.ret_5d:+6.2f}%  z {s.z_5d:+.2f}  RSI {s.rsi_14}")
