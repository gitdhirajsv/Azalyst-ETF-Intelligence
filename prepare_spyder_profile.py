"""
prepare_spyder_profile.py

Creates an isolated Spyder profile that auto-runs a local monitor script.

This is intentionally lightweight and dependency-free so it works even when
Spyder is installed in its own runtime environment.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE_DIR = PROJECT_DIR / ".spyder_azalyst_etf"
PROFILE_DIR = Path(os.environ.get("SPYDER_PROFILE", str(DEFAULT_PROFILE_DIR))).resolve()
RUN_FILE = PROJECT_DIR / "spyder_live_monitor.py"


def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ini_path = PROFILE_DIR / "spyder.ini"

    cfg = configparser.ConfigParser()
    if ini_path.exists():
        cfg.read(ini_path, encoding="utf-8")

    if not cfg.has_section("ipython_console"):
        cfg.add_section("ipython_console")

    # Auto-run a file on startup (Spyder reads this from spyder.ini when using --conf-dir).
    cfg.set("ipython_console", "startup/use_run_file", "True")
    cfg.set("ipython_console", "startup/run_file", str(RUN_FILE))

    # Keep defaults conservative: no pylab autoloading.
    cfg.set("ipython_console", "pylab", "False")
    cfg.set("ipython_console", "pylab/autoload", "False")
    cfg.set("ipython_console", "pylab/backend", "auto")

    with ini_path.open("w", encoding="utf-8") as f:
        cfg.write(f)

    print(f"Prepared Spyder profile: {PROFILE_DIR}")
    print(f"Auto-run file: {RUN_FILE}")


if __name__ == "__main__":
    main()
