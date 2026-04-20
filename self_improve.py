"""
self_improve.py — AZALYST AUTONOMOUS IMPROVEMENT ENGINE

Runs once daily via GitHub Actions.
Reads performance data + source code, calls Qwen3 Coder 480B on NVIDIA NIM,
receives a targeted code change, validates it, applies it.
Next GitHub Actions run automatically uses the improved code.

No manual intervention needed.
"""

import json
import os
import py_compile
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent

# ── What the AI is ALLOWED to edit ──────────────────────────────────────────
MUTABLE_FILES = {
    "scorer.py",
    "classifier.py",
    "paper_trader.py",
    "etf_mapper.py",
    "news_fetcher.py",
    "reporter.py",
}

# ── What the AI reads as context (includes read-only files) ─────────────────
SOURCE_FILES = [
    "scorer.py",
    "classifier.py",
    "paper_trader.py",
    "etf_mapper.py",
    "risk_engine.py",
    "state.py",
    "azalyst.py",
]

# FIX: Added improvement_log.jsonl so Qwen reads its own history before
# proposing a change — prevents re-proposing fixes that were already applied.
DATA_FILES = [
    "status.json",
    "azalyst_portfolio.json",
    "azalyst_state.json",
    "improvement_log.jsonl",
]

# ── NVIDIA NIM ───────────────────────────────────────────────────────────────
NIM_URL   = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "qwen/qwen3-coder-480b-a35b-instruct"

# ── Prompt ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous improvement agent for Azalyst, a Python-based
macro ETF intelligence and paper-trading system.

Your job each day:
1. Read the performance data (portfolio P&L, alpha vs SPY, signal accuracy)
2. Read the improvement_log.jsonl to see what has ALREADY been applied — never re-propose these
3. Read the source code
4. Identify the SINGLE highest-impact improvement you can make TODAY that has NOT been applied before
5. Output it as a precise, safe, syntactically valid code change

HARD RULES — violating any of these makes your output unusable:
- Output ONLY raw JSON. No markdown, no triple backticks, no prose outside the JSON.
- Propose exactly ONE change per run — the best one.
- Check improvement_log.jsonl first. If your proposed change_description closely matches
  any entry where applied=true, pick a DIFFERENT improvement instead.
- old_code must be a VERBATIM exact match of text currently in the file (including
  all whitespace, indentation, and comments). Copy it character-for-character.
- Only edit files in this allowed set: scorer.py, classifier.py, paper_trader.py,
  etf_mapper.py, news_fetcher.py, reporter.py
- Never change public function signatures that azalyst.py calls directly.
- new_code must be syntactically valid Python.
- Keep changes focused and minimal — fix one thing cleanly.

WHAT TO LOOK FOR (priority order):
1. Check improvement_log.jsonl — skip anything already marked applied=true.
2. The _best_existing_for_topup function routing new sector signals into existing
   positions in DIFFERENT sectors — it should only redirect within the same sector.
3. bonds_fixed_income sector missing from SECTOR_DEFINITIONS in classifier.py entirely
   — rate headlines are being misrouted into banking/equity ETFs.
4. Recency scoring — articles older than 48h should decay more aggressively.
5. Any other genuine improvement you identify from the performance data.

OUTPUT FORMAT (strict — no deviations):
{
  "analysis": "1-2 sentences: what is the problem and how does this fix it",
  "target_metric": "which metric this improves: alpha / signal_quality / capital_deployment / risk",
  "confidence": <integer 0-100>,
  "change": {
    "file": "filename.py",
    "description": "one line: what this change does",
    "old_code": "exact verbatim code to replace",
    "new_code": "replacement code"
  }
}

If the system is already performing well and no safe improvement exists, output:
{"analysis": "no safe improvement identified today", "confidence": 0, "change": null}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def build_context() -> str:
    """Assemble all performance data and source code into one context string."""
    parts = []

    parts.append("=" * 60)
    parts.append("PERFORMANCE DATA & IMPROVEMENT HISTORY")
    parts.append("=" * 60)
    for fname in DATA_FILES:
        content = _read(ROOT / fname)
        if content:
            parts.append(f"\n--- {fname} ---")
            parts.append(content)

    parts.append("\n" + "=" * 60)
    parts.append("SOURCE CODE (read-only files shown for context)")
    parts.append("=" * 60)
    for fname in SOURCE_FILES:
        content = _read(ROOT / fname)
        if content:
            parts.append(f"\n--- {fname} ---")
            parts.append(content)

    return "\n".join(parts)


def call_nim(context: str, api_key: str) -> dict:
    """Call Qwen3 Coder 480B on NVIDIA NIM and return parsed JSON response."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze and improve Azalyst:\n\n{context}"},
        ],
        "max_tokens": 4096,
        "temperature": 0.15,
        "top_p": 0.7,
    }

    print(f"  Calling {NIM_MODEL} ...")
    resp = requests.post(NIM_URL, headers=headers, json=payload, timeout=600)
    resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if the model wrapped output anyway
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:] if lines[-1] != "```" else lines[1:-1])

    return json.loads(raw)


def validate_syntax(filepath: Path) -> tuple[bool, str]:
    """Return (ok, error_message). Compiles file without executing it."""
    try:
        py_compile.compile(str(filepath), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def apply_change(change: dict) -> bool:
    """
    Apply a single str-replace change to a source file.
    Validates syntax in a temp file before touching the real file.
    Returns True on success.
    """
    filename    = (change.get("file") or "").strip()
    old_code    = change.get("old_code", "")
    new_code    = change.get("new_code", "")
    description = change.get("description", "")

    if filename not in MUTABLE_FILES:
        print(f"  BLOCKED: {filename} is not in the mutable file set")
        return False

    filepath = ROOT / filename
    if not filepath.exists():
        print(f"  BLOCKED: {filepath} does not exist")
        return False

    if not old_code:
        print("  BLOCKED: old_code is empty")
        return False

    content = filepath.read_text(encoding="utf-8")

    occurrences = content.count(old_code)
    if occurrences == 0:
        print(f"  BLOCKED: old_code not found verbatim in {filename}")
        print(f"  First 120 chars of old_code: {old_code[:120]!r}")
        return False
    if occurrences > 1:
        print(f"  BLOCKED: old_code found {occurrences} times in {filename} — too ambiguous")
        return False

    new_content = content.replace(old_code, new_code, 1)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(new_content)
        tmp_path = Path(tmp.name)

    try:
        ok, err = validate_syntax(tmp_path)
        if not ok:
            print(f"  BLOCKED: syntax error in proposed change — {err}")
            return False
    finally:
        tmp_path.unlink(missing_ok=True)

    filepath.write_text(new_content, encoding="utf-8")
    print(f"  APPLIED: {description}  →  {filename}")
    return True


def write_log(result: dict, applied: bool):
    """Append one line to improvement_log.jsonl for audit trail."""
    log_path = ROOT / "improvement_log.jsonl"
    change = result.get("change") or {}
    entry = {
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "analysis":          result.get("analysis", ""),
        "target_metric":     result.get("target_metric", ""),
        "confidence":        result.get("confidence", 0),
        "change_file":       change.get("file"),
        "change_description": change.get("description"),
        "applied":           applied,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"  Logged to improvement_log.jsonl (applied={applied})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        print("ERROR: NVIDIA_API_KEY environment variable not set")
        print("Add it as a repository secret: Settings -> Secrets -> NVIDIA_API_KEY")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 60}")
    print(f"  AZALYST SELF-IMPROVEMENT ENGINE  |  {ts}")
    print(f"{'=' * 60}\n")

    print("Step 1: Building context from source files and performance data ...")
    context = build_context()
    print(f"  Context size: {len(context):,} characters\n")

    print("Step 2: Calling Qwen3 Coder 480B on NVIDIA NIM ...")
    try:
        result = call_nim(context, api_key)
    except requests.exceptions.HTTPError as exc:
        print(f"  API HTTP error: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"  Could not parse model response as JSON: {exc}")
        return 1
    except Exception as exc:
        print(f"  Unexpected error calling NIM: {exc}")
        traceback.print_exc()
        return 1

    print(f"  Analysis: {result.get('analysis', '')}")
    print(f"  Confidence: {result.get('confidence', 0)}/100")
    print(f"  Target metric: {result.get('target_metric', 'n/a')}\n")

    print("Step 3: Applying change ...")
    change = result.get("change")
    applied = False

    if change:
        print(f"  Proposed: [{change.get('file')}] {change.get('description')}")
        applied = apply_change(change)
        if not applied:
            print("  No files were modified — change was blocked for safety")
    else:
        print("  No change proposed this cycle — system is performing well")

    print("\nStep 4: Writing audit log ...")
    write_log(result, applied)

    print(f"\n{'=' * 60}")
    if applied:
        print("  RESULT: Change applied. GitHub Actions will commit and re-run.")
    else:
        print("  RESULT: No change this cycle.")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
