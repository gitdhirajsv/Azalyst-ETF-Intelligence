"""
spyder_live_monitor.py

Live status monitor for Azalyst ETF Intelligence, designed to be auto-run
inside Spyder. It reads local state/log artifacts and prints a compact status
view that refreshes periodically.

This file uses only the Python standard library so it can run in Spyder's
runtime environment without requiring project dependencies to be installed
into that same environment.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "azalyst.log"
STATE_PATH = ROOT / "azalyst_state.json"
PORTFOLIO_PATH = ROOT / "azalyst_portfolio.json"

REFRESH_SECONDS = int(os.environ.get("AZALYST_MONITOR_REFRESH", "10"))
TAIL_LINES = int(os.environ.get("AZALYST_MONITOR_TAIL_LINES", "25"))


def _safe_import_cfg() -> Dict[str, Any]:
    """Best-effort import of config values; keeps monitor dependency-free."""
    try:
        from config import Config  # local module, stdlib-only even without python-dotenv

        return {
            "interval_min": int(getattr(Config, "POLL_INTERVAL_MINUTES", 30)),
            "threshold": int(getattr(Config, "CONFIDENCE_THRESHOLD", 62)),
            "cooldown_h": int(getattr(Config, "SIGNAL_COOLDOWN_HOURS", 4)),
        }
    except Exception:
        return {"interval_min": 30, "threshold": 62, "cooldown_h": 4}


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _file_mtime(path: Path) -> Optional[datetime]:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _tail_text(path: Path, max_lines: int) -> str:
    if max_lines <= 0:
        return ""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            remaining = f.tell()
            block = 8192
            buf = b""
            lines = []

            while remaining > 0 and len(lines) <= max_lines:
                read_size = min(block, remaining)
                remaining -= read_size
                f.seek(remaining)
                buf = f.read(read_size) + buf
                lines = buf.splitlines()

            tail = lines[-max_lines:]
            return b"\n".join(tail).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return "(azalyst.log not found yet)"
    except Exception as e:
        return f"(unable to read log: {e})"


def _clear_output() -> None:
    # Spyder uses IPython; clear_output keeps the pane readable.
    try:
        from IPython.display import clear_output  # type: ignore

        clear_output(wait=True)
    except Exception:
        pass


def _fmt_mtime(dt: Optional[datetime]) -> str:
    if not dt:
        return "missing"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _summarize_state(state: Dict[str, Any], cooldown_hours: int) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    tracked = len(state)
    active = 0
    latest = None

    for rec in state.values():
        sent_at = rec.get("sent_at")
        if not sent_at:
            continue
        if isinstance(sent_at, str):
            try:
                dt = datetime.fromisoformat(sent_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        else:
            continue

        age_h = (now - dt).total_seconds() / 3600.0
        if age_h < cooldown_hours:
            active += 1
        if latest is None or dt > latest:
            latest = dt

    return {"tracked": tracked, "active_cooldowns": active, "latest_sent_at": latest}


def _summarize_portfolio(pf: Dict[str, Any]) -> Dict[str, Any]:
    cash = float(pf.get("cash_inr", 0.0) or 0.0)
    open_positions = pf.get("open_positions") or []
    closed_trades = pf.get("closed_trades") or []
    last_saved = pf.get("last_saved")
    return {
        "cash_inr": cash,
        "open_count": len(open_positions),
        "closed_count": len(closed_trades),
        "last_saved": last_saved,
    }


def main() -> None:
    cfg = _safe_import_cfg()
    cooldown_h = int(cfg.get("cooldown_h", 4))

    print("Azalyst ETF Intelligence - Spyder live monitor")
    print(f"Workspace: {ROOT}")
    print("")

    while True:
        _clear_output()

        print("AZALYST ETF Intelligence - Live Monitor")
        print(f"Now (UTC):        {_utc_now_str()}")
        print(f"Interval:         {cfg.get('interval_min', 30)} min")
        print(f"Threshold:        {cfg.get('threshold', 62)} / 100")
        print(f"Cooldown:         {cooldown_h} hours")
        print("")
        print(f"Log:              {LOG_PATH.name:<22} updated: {_fmt_mtime(_file_mtime(LOG_PATH))}")
        print(f"State:            {STATE_PATH.name:<22} updated: {_fmt_mtime(_file_mtime(STATE_PATH))}")
        print(f"Portfolio:         {PORTFOLIO_PATH.name:<21} updated: {_fmt_mtime(_file_mtime(PORTFOLIO_PATH))}")
        print("")

        state = _load_json(STATE_PATH)
        if state is not None:
            s = _summarize_state(state, cooldown_h)
            latest = s["latest_sent_at"]
            latest_str = latest.strftime("%Y-%m-%d %H:%M:%S UTC") if latest else "unknown"
            print(
                f"Signals tracked:  {s['tracked']}  |  active cooldowns: {s['active_cooldowns']}  |  last sent: {latest_str}"
            )
        else:
            print("Signals tracked:  (state file not found yet)")

        pf = _load_json(PORTFOLIO_PATH)
        if pf is not None:
            p = _summarize_portfolio(pf)
            print(
                f"Paper portfolio:  cash INR {p['cash_inr']:,.0f}  |  open {p['open_count']}  |  closed {p['closed_count']}  |  last_saved: {p['last_saved'] or 'unknown'}"
            )
        else:
            print("Paper portfolio:  (portfolio file not found yet)")

        print("")
        print(f"Last {TAIL_LINES} log lines:")
        print("-" * 72)
        print(_tail_text(LOG_PATH, TAIL_LINES))

        time.sleep(max(1, REFRESH_SECONDS))


if __name__ == "__main__":
    main()
