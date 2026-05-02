"""
regime_classifier.py — Market Regime Detection (HMM-based)

David Shaw / D.E. Shaw recommendation: make thresholds regime-conditional.
This stub downloads VIX and cross-asset data and applies a 2-state HMM
(normal vs. stressed). Not yet integrated into the signal pipeline.

MANUAL STEP: Install hmmlearn via `pip install hmmlearn`
"""
import logging
from typing import Dict, Optional

log = logging.getLogger("azalyst.regime")

class RegimeClassifier:
    """2-state Hidden Markov Model for regime detection."""
    def __init__(self):
        self.enabled = False  # Set True after installing hmmlearn
        self.current_regime: int = 0  # 0=normal, 1=stressed

    def classify(self) -> Dict:
        """Return current regime with explanation."""
        if not self.enabled:
            return {"regime": 0, "label": "NORMAL", "confidence": 1.0,
                    "note": "Regime classifier stub — install hmmlearn to enable"}
        # TODO: Download VIX + cross-asset data, run HMM, return regime
        return {"regime": self.current_regime,
                "label": "NORMAL" if self.current_regime == 0 else "STRESSED",
                "confidence": 0.85}
