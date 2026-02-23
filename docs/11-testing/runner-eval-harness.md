---
title: "RLM Runner Eval Harness"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["rlm", "runner", "testing", "eval", "golden-cases", "popia", "redaction"]
related: ["../04-features/113-rlm-runner-service.md", "../03-api-reference/rlm-api.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# RLM Runner Eval Harness

Lightweight evaluation framework for validating the RLM runner's analysis quality against golden-case fixtures. Runs 6 curated BMS evidence cases through the runner and checks outputs against assertion-based `expected.json` files.

## Purpose

Run this harness when you change: prompts, recursion logic, models, budgets, or infrastructure. It catches regressions in analysis quality, structural completeness, and POPIA redaction compliance.

## Quick Start

```bash
# Dry-run: validate fixture structure only (no runner needed)
python3 runner/tests/run_evals.py --dry-run

# Live run against local runner
python3 runner/tests/run_evals.py

# Custom runner URL and model override
python3 runner/tests/run_evals.py --runner-url http://10.0.0.5:8010 --model llama3.2:1b

# Keep eval case folders after run (for debugging)
python3 runner/tests/run_evals.py --keep-cases
```

## Fixture Structure

Each golden case lives under `runner/tests/fixtures/`:

```
runner/tests/fixtures/
  CASE001/                     # Chiller condenser fouling
    manifest.json              # Case metadata (case_id, description, evidence_files)
    expected.json              # Assertions for output validation
    evidence/
      alarm_history.jsonl      # BMS alarms
      sensor_readings.csv      # Time-series sensor data
      maintenance_log.json     # Service history
  CASE002/                     # UPS battery degradation
  CASE003/                     # VAV damper stuck open
  CASE004/                     # Fire panel RS-485 comm failure
  CASE005/                     # Generator start fail + POPIA redaction
  CASE006/                     # Multi-system cascade + budget exhaustion
```

## Golden Cases

| Case | Scenario | Key Assertions |
|------|----------|----------------|
| **CASE001** | Chiller condenser fouling -- CWT climbing, delta-T narrowing, alarms escalating | Must mention condenser/fouling/CWT; >= 2 actions; confidence >= 0.5 |
| **CASE002** | UPS battery degradation -- voltage dropping, autonomy shrinking, cell #8 failing | Must mention battery/UPS/voltage; >= 2 actions; confidence >= 0.4 |
| **CASE003** | VAV damper stuck open -- zone overcooling, damper fixed at 100%, comfort complaints | Must mention damper/stuck/overcool; >= 1 action; confidence >= 0.4 |
| **CASE004** | Fire panel RS-485 comm failure -- 67% packet loss, escalating dropouts (safety-critical) | Must mention fire/panel/RS-485/communication; >= 2 actions; confidence >= 0.5 |
| **CASE005** | Generator crank failure + embedded PII in evidence -- tests both analysis AND redaction | Must mention generator/battery/crank; must NOT leak SA ID numbers, emails, or phone numbers |
| **CASE006** | Multi-system cascading failure (3MB, 10 evidence files) -- designed to exhaust analysis budget | Must mention chiller/condenser/cascade; `needs_deeper_run` must be `true`; >= 3 actions |

## expected.json Format

Each fixture's `expected.json` defines assertions checked against the runner's output:

```json
{
  "must_include_any": ["keyword1", "keyword2"],
  "must_include_all": ["findings", "recommended_actions"],
  "must_not_include": ["leaked-pii@example.com", "0821234567"],
  "redaction_patterns": [
    {
      "label": "SA ID number (13 digits)",
      "regex": "\\b\\d{6}[05]\\d{6}\\b"
    },
    {
      "label": "Email address",
      "regex": "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
    }
  ],
  "min_actions": 2,
  "min_confidence": 0.5,
  "max_anomalies": 20
}
```

### Assertion Types

| Assertion | Type | Description |
|-----------|------|-------------|
| `must_include_any` | string[] | At least one keyword must appear in flattened output text |
| `must_include_all` | string[] | All listed keys must be present in result dict (structural check) |
| `must_not_include` | string[] | Forbidden strings that must NOT appear (PII leak check) |
| `redaction_patterns` | object[] | Regex patterns that must NOT match output (catches unknown PII) |
| `min_actions` | int | Minimum `recommended_actions` count |
| `min_confidence` | float | Minimum `confidence` score (0.0-1.0) |
| `max_anomalies` | int | Upper bound on `anomalies` count (catches hallucination) |
| `expect_needs_deeper_run` | bool | If `true`, asserts `needs_deeper_run=true` (budget exhaustion test) |

## How It Works

1. **Fixture validation**: Checks each fixture has `manifest.json`, `expected.json`, and non-empty `evidence/` directory.
2. **Copy to runner**: Copies fixture into runner's `CASES_DIR` with `EVAL-` prefix (e.g., `EVAL-CASE001`).
3. **Submit run**: `POST /run` with the eval case ID and default analysis question.
4. **Poll for completion**: `GET /runs/{run_id}` every 3 seconds until terminal status.
5. **Validate assertions**: Check all `expected.json` assertions against the result.
6. **Cleanup**: Remove `EVAL-` prefixed case folders (unless `--keep-cases`).

## Safety Guards

The eval script includes safety measures to prevent accidental data loss:

- **Safe path allowlist**: Only allows `cases_root` under `/var/lib/sentinel/` or `/tmp/sentinel-evals-*`. All other paths are rejected.
- **Writable check**: Verifies the `cases_root` exists and is writable (or parent is writable for creation) before copying any files.
- **EVAL- prefix**: Only copies fixtures with `EVAL-` prefix. Cleanup only deletes `EVAL-` prefixed folders.
- **No non-eval deletion**: `_cleanup_eval_case()` returns immediately if the case ID doesn't start with `EVAL-`.

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--runner-url` | `http://127.0.0.1:8010` | Runner service URL |
| `--cases-root` | `/var/lib/sentinel/cases` | Where to copy fixtures for the runner |
| `--question` | (analysis prompt) | Override the analysis question |
| `--model` | (runner default) | Override the model |
| `--timeout` | `300` | Per-case timeout in seconds |
| `--dry-run` | `false` | Validate fixture structure only, skip runner |
| `--keep-cases` | `false` | Don't clean up eval case folders after running |

## Adding New Cases

1. Create a new directory under `runner/tests/fixtures/` (e.g., `CASE006/`).
2. Add `manifest.json` with case metadata.
3. Add evidence files under `evidence/`.
4. Create `expected.json` with assertions.
5. Validate: `python3 runner/tests/run_evals.py --dry-run`

For POPIA redaction tests, embed realistic (but synthetic) PII in evidence files and add both `must_not_include` entries for known values and `redaction_patterns` regexes for pattern-based detection.

## Related

- [Phase 113: RLM Runner Service](../04-features/113-rlm-runner-service.md) -- feature overview
- [RLM API Reference](../03-api-reference/rlm-api.md) -- endpoint details and schemas
- [Testing Guide](testing-guide.md) -- overall testing strategy
