"""
state.py — AZALYST Signal State Manager

Manages:
  - Deduplication of previously sent signals
  - Cooldown periods per sector (prevents alert spam)
  - Update detection (when same signal strengthens)
  - Persistent JSON state file
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List

log = logging.getLogger("azalyst.state")


def _parse_dt(value) -> datetime:
    """
    Parse an ISO-format datetime string into an aware UTC datetime.
    Returns current UTC time on any failure so callers never receive None.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _json_safe(value):
    """Recursively convert runtime objects into JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


class SignalStateManager:
    """
    Tracks sent signals with timestamps and confidence scores.
    Determines whether a new scan result is:
      (a) NEW — never seen before → send alert
      (b) UPDATE — same sector, higher confidence → send update
      (c) DUPLICATE — same sector within cooldown → suppress
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.state_file = cfg.STATE_FILE
        self.cooldown_hours = cfg.SIGNAL_COOLDOWN_HOURS
        self.update_hours = cfg.UPDATE_THRESHOLD_HOURS
        self.update_delta = cfg.UPDATE_CONFIDENCE_DELTA

        self._state: Dict = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> Dict:
        """Load state from disk, deserializing all datetime fields."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                for sector_id, record in raw.items():
                    # FIX: deserialize both sent_at AND latest_ts back to datetime objects.
                    # Previously only sent_at was converted, causing TypeError in recency
                    # scoring when scorer.py called (now - latest_ts) on a string value.
                    if "sent_at" in record:
                        record["sent_at"] = _parse_dt(record["sent_at"])
                    if "latest_ts" in record and record["latest_ts"]:
                        record["latest_ts"] = _parse_dt(record["latest_ts"])

                log.info(f"Loaded state: {len(raw)} sector records")
                return raw
            except Exception as e:
                log.warning(f"Could not load state file: {e}")
        return {}

    def _save(self):
        """Persist state to disk."""
        try:
            serializable = {}
            for sector_id, record in self._state.items():
                serializable[sector_id] = _json_safe(record)

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            log.warning(f"Could not save state: {e}")

    # ── Core Logic ────────────────────────────────────────────────────────────

    def filter_new_or_updated(self, signals: List[Dict]) -> List[Dict]:
        """
        Filter a list of signals — return only those that should be sent.
        Applies cooldown and update logic.
        """
        to_send = []
        now = datetime.now(timezone.utc)

        for signal in signals:
            sector_key = self._sector_key(signal)
            existing = self._state.get(sector_key)

            if existing is None:
                # Brand new sector signal
                log.info(f"NEW signal detected: {signal['sector_label']}")
                to_send.append(signal)

            else:
                sent_at    = existing.get("sent_at", now - timedelta(days=999))
                age        = (now - sent_at).total_seconds() / 3600
                prev_conf  = existing.get("confidence", 0)
                curr_conf  = signal.get("confidence", 0)

                if age >= self.cooldown_hours:
                    # Cooldown expired — this is a fresh signal
                    log.info(
                        f"COOLDOWN EXPIRED signal: {signal['sector_label']} "
                        f"(age={age:.1f}h, prev_conf={prev_conf}, curr_conf={curr_conf})"
                    )
                    to_send.append(signal)

                elif (age >= self.update_hours and
                      curr_conf >= prev_conf + self.update_delta):
                    # Same sector, significantly stronger signal within cooldown
                    log.info(
                        f"UPDATE signal: {signal['sector_label']} "
                        f"conf {prev_conf} → {curr_conf} (+{curr_conf - prev_conf})"
                    )
                    signal["_is_update"]       = True
                    signal["_prev_confidence"] = prev_conf
                    to_send.append(signal)

                else:
                    log.debug(
                        f"SUPPRESSED: {signal['sector_label']} "
                        f"(age={age:.1f}h, cooldown={self.cooldown_hours}h)"
                    )

        return to_send

    def is_update(self, signal: Dict) -> bool:
        """Check if a signal is an update to a previous one."""
        return signal.get("_is_update", False)

    def record_signal(self, signal: Dict):
        """Record that a signal was sent, for future deduplication."""
        sector_key = self._sector_key(signal)
        self._state[sector_key] = {
            "sent_at":              datetime.now(timezone.utc),
            "confidence":           signal.get("confidence", 0),
            "sector_label":         signal.get("sector_label", ""),
            "article_count":        signal.get("article_count", 0),
            "severity":             signal.get("severity", ""),
            "regions":              signal.get("regions", [])[:6],
            "sources":              signal.get("sources", [])[:6],
            "top_headlines":        signal.get("top_headlines", [])[:5],
            "latest_ts":            signal.get("latest_ts"),
            "confidence_breakdown": signal.get("confidence_breakdown", {}),
            "etf_recommendations":  signal.get(
                "etf_recommendations",
                {"india": [], "global": []},
            ),
        }
        self._save()

    def _sector_key(self, signal: Dict) -> str:
        """Generate a stable key for a sector signal."""
        sectors = signal.get("sectors", [])
        return "|".join(sorted(sectors))

    def get_stats(self) -> Dict:
        """Return state statistics."""
        now = datetime.now(timezone.utc)
        stats = {
            "total_tracked":    len(self._state),
            "active_cooldowns": 0,
            "expired_cooldowns": 0,
        }
        for record in self._state.values():
            sent_at = record.get("sent_at", now)
            age = (now - sent_at).total_seconds() / 3600
            if age < self.cooldown_hours:
                stats["active_cooldowns"] += 1
            else:
                stats["expired_cooldowns"] += 1
        return stats
