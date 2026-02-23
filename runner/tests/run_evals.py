"""
Runner eval harness — runs golden-case fixtures against a live runner service.

Usage:
    # Default: local runner on port 8010, copies fixtures into /var/lib/sentinel/cases
    python runner/tests/run_evals.py

    # Custom runner URL and cases root
    python runner/tests/run_evals.py --runner-url http://10.0.0.5:8010 --cases-root /tmp/eval-cases

    # Override model (must be allowlisted by runner)
    python runner/tests/run_evals.py --model llama3.2:1b

    # Dry-run: validate expected.json without calling runner
    python runner/tests/run_evals.py --dry-run

Run this when you change: prompts, recursion logic, models, budgets, or infrastructure.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_RUNNER_URL = os.environ.get("RUNNER_URL", "http://127.0.0.1:8010")
FIXTURES_DIR = Path(__file__).parent / "fixtures"

DEFAULT_QUESTION = (
    "Analyse this case and return findings, anomalies, timeline, "
    "and recommended actions."
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_text(result: dict[str, Any]) -> str:
    """Combine all user-visible text fields for keyword checks."""
    parts: list[str] = []

    for key in ("summary",):
        v = result.get(key)
        if isinstance(v, str):
            parts.append(v)

    for list_key in ("findings", "recommended_actions"):
        v = result.get(list_key)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)

    for list_key in ("anomalies", "timeline"):
        v = result.get(list_key)
        if isinstance(v, list):
            parts.extend(json.dumps(x, ensure_ascii=False) for x in v)

    return "\n".join(parts).lower()


def _check_expected(
    case_id: str, result: dict[str, Any], expected: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Validate result against expected.json assertions. Returns (ok, errors)."""
    errors: list[str] = []
    text = _flatten_text(result)

    # --- must_include_any: at least one keyword found in output text ---
    must_any = [s.lower() for s in expected.get("must_include_any", [])]
    if must_any and not any(s in text for s in must_any):
        errors.append(
            f"must_include_any: none of {must_any} found in output"
        )

    # --- must_include_all: structural keys present in result dict ---
    for key in expected.get("must_include_all", []):
        if key not in result:
            errors.append(f"must_include_all: missing key '{key}' in result")

    # --- must_not_include: forbidden strings (PII, redaction leaks) ---
    for s in expected.get("must_not_include", []):
        if s and s.lower() in text:
            errors.append(f"must_not_include: found forbidden '{s}' in output")

    # --- min_actions: at least N recommended actions ---
    min_actions = expected.get("min_actions")
    if isinstance(min_actions, int):
        actions = result.get("recommended_actions", [])
        n = len(actions) if isinstance(actions, list) else 0
        if n < min_actions:
            errors.append(f"min_actions: got {n}, expected >= {min_actions}")

    # --- min_confidence: confidence float >= threshold ---
    min_conf = expected.get("min_confidence")
    if isinstance(min_conf, (int, float)):
        conf = result.get("confidence", 0.0)
        if not isinstance(conf, (int, float)) or conf < min_conf:
            errors.append(
                f"min_confidence: got {conf}, expected >= {min_conf}"
            )

    # --- max_anomalies: upper bound on anomaly count ---
    max_anom = expected.get("max_anomalies")
    if isinstance(max_anom, int):
        anomalies = result.get("anomalies", [])
        n = len(anomalies) if isinstance(anomalies, list) else 0
        if n > max_anom:
            errors.append(f"max_anomalies: got {n}, expected <= {max_anom}")

    # --- redaction_patterns: regex patterns that must NOT appear in output ---
    # Catches PII leakage even for synthetic/unknown values
    for pat_entry in expected.get("redaction_patterns", []):
        label = pat_entry.get("label", "pattern")
        pattern = pat_entry.get("regex", "")
        if pattern and re.search(pattern, text):
            errors.append(
                f"redaction_patterns: '{label}' matched in output (regex: {pattern})"
            )

    # --- expect_needs_deeper_run: budget exhaustion test ---
    expect_deeper = expected.get("expect_needs_deeper_run")
    if expect_deeper is True:
        if not result.get("needs_deeper_run"):
            errors.append(
                "expect_needs_deeper_run: expected needs_deeper_run=true "
                "(budget exhaustion test)"
            )

    # --- expect_status: check specific status value ---
    expect_status = expected.get("expect_status")
    if isinstance(expect_status, str):
        actual_status = result.get("status", "")
        if actual_status != expect_status:
            errors.append(
                f"expect_status: got '{actual_status}', expected '{expect_status}'"
            )

    # --- summary_must_include_any: at least one keyword in summary ---
    summary_any = [s.lower() for s in expected.get("summary_must_include_any", [])]
    if summary_any:
        summary_text = (result.get("summary") or "").lower()
        if not any(s in summary_text for s in summary_any):
            errors.append(
                f"summary_must_include_any: none of {summary_any} found in summary"
            )

    return len(errors) == 0, errors


def _poll_run(
    client: httpx.Client, runner_url: str, run_id: str, timeout_s: int
) -> dict[str, Any]:
    """Poll GET /runs/{run_id} until terminal status or timeout."""
    deadline = time.time() + timeout_s
    last_status = None

    while time.time() < deadline:
        r = client.get(f"{runner_url}/runs/{run_id}")
        r.raise_for_status()
        data = r.json()
        status = data.get("status")

        if status != last_status:
            last_status = status
            print(f"  status={status}")

        if status in ("complete", "error", "timeout"):
            return data

        time.sleep(3)

    raise TimeoutError(f"Timed out waiting for run {run_id} after {timeout_s}s")


def _copy_fixture_to_cases(fixture_dir: Path, cases_root: Path) -> str:
    """Copy fixture into runner's cases directory. Returns case_id."""
    case_id = f"EVAL-{fixture_dir.name}"
    target = cases_root / case_id

    # Clean up previous eval run if exists
    if target.exists():
        shutil.rmtree(target)

    # Copy manifest.json and evidence/ (skip expected.json and metadata/)
    target.mkdir(parents=True, exist_ok=True)

    manifest_src = fixture_dir / "manifest.json"
    if manifest_src.exists():
        # Rewrite case_id in manifest to match eval prefix
        manifest = _read_json(manifest_src)
        manifest["case_id"] = case_id
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    evidence_src = fixture_dir / "evidence"
    if evidence_src.is_dir():
        evidence_dst = target / "evidence"
        shutil.copytree(evidence_src, evidence_dst)

    return case_id


def _cleanup_eval_case(cases_root: Path, case_id: str) -> None:
    """Remove eval case folder after test. Safety: only deletes EVAL- prefixed folders."""
    if not case_id.startswith("EVAL-"):
        return  # Never delete non-eval cases
    target = cases_root / case_id
    if target.exists() and target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


_SAFE_PATH_PATTERNS = (
    "/var/lib/sentinel/",
    "/tmp/sentinel-evals-",
)


def _validate_cases_root(cases_root: Path) -> None:
    """Safety guard: refuse dangerous cases_root paths.

    Allowed:
      - /var/lib/sentinel/cases (or any subdir of /var/lib/sentinel/)
      - /tmp/sentinel-evals-* (dev convenience)
    Blocked:
      - /, /tmp, /var, /etc, /home, or anything else too broad
    """
    resolved = str(cases_root.resolve())
    if not resolved:
        raise ValueError("cases_root cannot be empty")

    # Allow known-safe prefixes
    if any(resolved.startswith(prefix) for prefix in _SAFE_PATH_PATTERNS):
        # Still check it exists and is writable
        _check_writable(cases_root)
        return

    # Block everything else
    raise ValueError(
        f"Refusing to use '{resolved}' as cases_root — not in safe list. "
        f"Use /var/lib/sentinel/cases or /tmp/sentinel-evals-<name>"
    )


def _check_writable(cases_root: Path) -> None:
    """Verify cases_root exists (or can be created) and is writable."""
    if cases_root.exists():
        if not cases_root.is_dir():
            raise ValueError(f"cases_root '{cases_root}' exists but is not a directory")
        if not os.access(cases_root, os.W_OK):
            raise ValueError(f"cases_root '{cases_root}' is not writable")
    else:
        # Check parent is writable so we can mkdir
        parent = cases_root.parent
        if not parent.exists():
            raise ValueError(
                f"cases_root '{cases_root}' does not exist and parent "
                f"'{parent}' also does not exist"
            )
        if not os.access(parent, os.W_OK):
            raise ValueError(
                f"cases_root '{cases_root}' does not exist and parent "
                f"'{parent}' is not writable"
            )


def _validate_fixture(fixture_dir: Path) -> list[str]:
    """Validate fixture structure without running against the runner."""
    issues: list[str] = []

    if not (fixture_dir / "manifest.json").exists():
        issues.append("missing manifest.json")
    if not (fixture_dir / "expected.json").exists():
        issues.append("missing expected.json")
    if not (fixture_dir / "evidence").is_dir():
        issues.append("missing evidence/ directory")
    else:
        evidence_files = list((fixture_dir / "evidence").iterdir())
        if not evidence_files:
            issues.append("evidence/ directory is empty")

    if (fixture_dir / "expected.json").exists():
        try:
            expected = _read_json(fixture_dir / "expected.json")
            if not isinstance(expected, dict):
                issues.append("expected.json is not a JSON object")
        except json.JSONDecodeError as e:
            issues.append(f"expected.json parse error: {e}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run runner eval fixtures against a live runner service."
    )
    parser.add_argument("--runner-url", default=DEFAULT_RUNNER_URL)
    parser.add_argument(
        "--cases-root",
        default="/var/lib/sentinel/cases",
        help="Where to copy fixtures for the runner to read.",
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--model", default=None, help="Model override.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixture structure only, don't call runner.",
    )
    parser.add_argument(
        "--keep-cases",
        action="store_true",
        help="Don't clean up eval case folders after running.",
    )
    args = parser.parse_args()

    runner_url = args.runner_url.rstrip("/")
    cases_root = Path(args.cases_root)

    if not FIXTURES_DIR.is_dir():
        print(f"No fixtures directory at {FIXTURES_DIR}", file=sys.stderr)
        return 2

    fixture_dirs = sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())
    if not fixture_dirs:
        print(f"No fixture folders found in {FIXTURES_DIR}", file=sys.stderr)
        return 2

    print(f"Found {len(fixture_dirs)} fixtures in {FIXTURES_DIR}")

    # Safety guard for cases_root
    if not args.dry_run:
        _validate_cases_root(cases_root)

    # --- Dry run: just validate structure ---
    if args.dry_run:
        ok_count = 0
        for fixture_dir in fixture_dirs:
            issues = _validate_fixture(fixture_dir)
            if issues:
                print(f"  {fixture_dir.name}: INVALID — {', '.join(issues)}")
            else:
                print(f"  {fixture_dir.name}: OK")
                ok_count += 1
        print(f"\nValidated: {ok_count}/{len(fixture_dirs)} OK")
        return 0 if ok_count == len(fixture_dirs) else 1

    # --- Live run ---
    passed = 0
    failed = 0
    skipped = 0

    with httpx.Client(timeout=30) as client:
        # Health check
        try:
            h = client.get(f"{runner_url}/health")
            h.raise_for_status()
            health = h.json()
            print(
                f"Runner: {runner_url} — v{health.get('version', '?')}, "
                f"ollama={'yes' if health.get('ollama_available') else 'NO'}"
            )
            if not health.get("ollama_available"):
                print("WARNING: Ollama not available — runs will likely fail\n")
        except Exception as e:
            print(f"ERROR: Cannot reach runner at {runner_url}: {e}")
            return 2

        for fixture_dir in fixture_dirs:
            expected_path = fixture_dir / "expected.json"
            if not expected_path.exists():
                print(f"\nSKIP {fixture_dir.name}: no expected.json")
                skipped += 1
                continue

            issues = _validate_fixture(fixture_dir)
            if issues:
                print(f"\nSKIP {fixture_dir.name}: {', '.join(issues)}")
                skipped += 1
                continue

            print(f"\n{'='*60}")
            print(f"  {fixture_dir.name}")
            print(f"{'='*60}")

            case_id = None
            try:
                # Copy fixture to runner's cases dir
                case_id = _copy_fixture_to_cases(fixture_dir, cases_root)
                expected = _read_json(expected_path)

                # Submit run
                payload: dict[str, Any] = {
                    "case_id": case_id,
                    "question": args.question,
                }
                if args.model:
                    payload["model"] = args.model

                r = client.post(f"{runner_url}/run", json=payload)
                r.raise_for_status()
                run = r.json()
                run_id = run["run_id"]
                print(f"  run_id={run_id}")

                # Poll for completion
                result = _poll_run(client, runner_url, run_id, args.timeout)

                # Check if run itself errored
                if result.get("status") == "error":
                    print(f"  FAIL (runner error): {result.get('summary', 'unknown')}")
                    failed += 1
                    continue

                # Validate against expected
                ok, errors = _check_expected(case_id, result, expected)
                if ok:
                    print("  PASS")
                    conf = result.get("confidence", "?")
                    actions = len(result.get("recommended_actions", []))
                    anomalies = len(result.get("anomalies", []))
                    print(
                        f"    confidence={conf}  actions={actions}  anomalies={anomalies}"
                    )
                    passed += 1
                else:
                    print("  FAIL")
                    for e in errors:
                        print(f"    - {e}")
                    failed += 1

            except TimeoutError as e:
                print(f"  FAIL (timeout): {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                failed += 1
            finally:
                # Cleanup unless --keep-cases
                if case_id and not args.keep_cases:
                    _cleanup_eval_case(cases_root, case_id)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
