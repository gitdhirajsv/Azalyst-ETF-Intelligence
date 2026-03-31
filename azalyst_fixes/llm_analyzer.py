"""
llm_analyzer.py — AZALYST LLM Analyzer Stub

Provides the interface expected by azalyst.py without requiring an external
LLM API. Set NVIDIA_API_KEY in .env to enable actual LLM analysis via
NVIDIA NIM (Mistral 7B). Without the key, all methods return neutral/no-op
results and the system operates in rule-based mode only.
"""

import logging
import time
from typing import Dict, List, Optional

log = logging.getLogger("azalyst.llm")


class LLMAnalyzer:
    """
    LLM-powered signal evaluator and portfolio advisor.
    When NVIDIA_API_KEY is not set, all methods are no-ops and
    self.enabled is False — the caller skips LLM paths entirely.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled: bool = False
        self._last_analysis_time: float = 0.0
        self._analysis_interval_hours: float = max(
            float(getattr(cfg, "LLM_ANALYSIS_INTERVAL", 6)), 1.0
        )

        api_key = getattr(cfg, "NVIDIA_API_KEY", "")
        if not api_key:
            log.info("LLM Analyzer disabled — NVIDIA_API_KEY not set")
            return

        try:
            import requests  # already a core dependency
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
            self._base_url = getattr(
                cfg, "NVIDIA_API_BASE",
                "https://integrate.api.nvidia.com/v1"
            )
            self._model = getattr(cfg, "LLM_MODEL", "mistralai/mistral-7b-instruct-v0.3")
            self.enabled = True
            log.info(f"LLM Analyzer enabled — model: {self._model}")
        except Exception as exc:
            log.warning(f"LLM Analyzer init failed: {exc}")

    # ── Public interface ──────────────────────────────────────────────────────

    def evaluate_signal(self, signal: Dict, portfolio_context: Dict) -> Dict:
        """
        Evaluate a signal and return a recommendation dict.
        Returns a neutral no-op recommendation when disabled.
        """
        if not self.enabled:
            return {"action": "PASS", "reason": "LLM disabled", "confidence_adjustment": 0}

        try:
            prompt = self._build_signal_prompt(signal, portfolio_context)
            response = self._query(prompt, max_tokens=300)
            return {"action": "REVIEW", "reason": response, "confidence_adjustment": 0}
        except Exception as exc:
            log.warning(f"LLM signal evaluation error: {exc}")
            return {"action": "PASS", "reason": str(exc), "confidence_adjustment": 0}

    def run_portfolio_analysis(self) -> Dict:
        """
        Run a full portfolio review and return suggestions.
        Returns empty suggestion list when disabled.
        """
        if not self.enabled:
            return {"suggestions": [], "regime": "unknown"}

        try:
            prompt = "Provide 3 concise portfolio risk management suggestions for a macro ETF book."
            response = self._query(prompt, max_tokens=500)
            suggestions = [line.strip() for line in response.split("\n") if line.strip()]
            self._last_analysis_time = time.time()
            return {"suggestions": suggestions, "regime": "unknown", "raw": response}
        except Exception as exc:
            log.warning(f"LLM portfolio analysis error: {exc}")
            return {"suggestions": [], "regime": "unknown"}

    def interpret_macro_regime(self) -> Dict:
        """
        Interpret the current macro regime from available signals.
        Returns unknown regime when disabled.
        """
        if not self.enabled:
            return {"regime": "unknown", "interpretation": ""}

        try:
            prompt = "In one sentence, describe the current global macro regime for ETF investors."
            response = self._query(prompt, max_tokens=150)
            return {"regime": "active", "interpretation": response}
        except Exception as exc:
            log.warning(f"LLM macro regime error: {exc}")
            return {"regime": "unknown", "interpretation": ""}

    def log_trade_outcome(self, exit_data: Dict) -> None:
        """Record a closed trade outcome for feedback learning (stub)."""
        if not self.enabled:
            return
        ticker = exit_data.get("ticker", "?")
        pnl_pct = exit_data.get("realised_pnl_pct", 0)
        log.debug(f"LLM trade outcome logged: {ticker} {pnl_pct:+.1f}%")

    def should_run_analysis(self) -> bool:
        """Return True if enough time has elapsed since last analysis."""
        if not self.enabled:
            return False
        elapsed_hours = (time.time() - self._last_analysis_time) / 3600
        return elapsed_hours >= self._analysis_interval_hours

    # ── Internal ──────────────────────────────────────────────────────────────

    def _query(self, prompt: str, max_tokens: int = 300) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        resp = self._session.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _build_signal_prompt(self, signal: Dict, ctx: Dict) -> str:
        label = signal.get("sector_label", "unknown")
        conf = signal.get("confidence", 0)
        headlines = signal.get("top_headlines", [])[:3]
        cash = ctx.get("cash", 0)
        positions = ctx.get("open_positions_count", 0)
        return (
            f"Macro signal: {label}, confidence {conf}/100.\n"
            f"Headlines: {headlines}\n"
            f"Portfolio: cash INR {cash:,.0f}, {positions} open positions.\n"
            f"In one sentence, should we act on this signal? Reply: BUY, HOLD, or PASS."
        )


def create_llm_analyzer(cfg) -> Optional[LLMAnalyzer]:
    """
    Factory function. Returns LLMAnalyzer instance (may be disabled if no API key).
    Returns None only on unexpected construction failure.
    """
    try:
        return LLMAnalyzer(cfg)
    except Exception as exc:
        log.error(f"Failed to construct LLMAnalyzer: {exc}")
        return None
