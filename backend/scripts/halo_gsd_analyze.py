#!/usr/bin/env python3
"""
HALO Alternative: GSD Master Orchestration Analyzer

Analyzes GSD Master execution traces (JSONL) to identify orchestration patterns
and generate recommendations for GSD Master skill improvements.

Requires: openai package (pip install openai)
Cost: ~$0.50-2.00 per analysis run (GPT-4o pricing)

Usage:
  python backend/scripts/halo_gsd_analyze.py gsd_traces/phase_193_gsd.jsonl
  python backend/scripts/halo_gsd_analyze.py gsd_traces/phase_194_gsd.jsonl gsd_traces/phase_195_gsd.jsonl
  python backend/scripts/halo_gsd_analyze.py gsd_traces/phase_*.jsonl -o findings.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI

client = OpenAI()

ANALYSIS_PROMPT_TEMPLATE = """You are analyzing GSD Master orchestration traces from {phase_count} phase(s).

GSD Master is a phase orchestration system with 6 steps:
0. Validation (structural checks)
1. Task creation
2. Mode selection (Ralph Loop vs Standard)
3. Architecture Challenge (Explore agent identifies blockers)
4. Wave execution + wave reconciliation (plans within waves conflict-checked)
5. Paranoid review (ship-blocking issues caught)
6. Return execution contract

For each execution contract, extract orchestration patterns:

1. VALIDATION FAILURES (Step 0)
   - Which structural issues cause validation to fail?
   - Are there patterns in phase definitions that repeatedly fail?
   - Confidence score (0.0-1.0) based on recurrence across phases.

2. ARCHITECTURE BLOCKERS (Step 3)
   - What types of design blockers appear?
   - Are blockers frequently false-positives or legitimate?
   - Blocker categories and patterns.
   - Confidence: How often is this blocker actually blocking?

3. WAVE RECONCILIATION CONFLICTS (Step 4)
   - What cross-plan conflicts appear?
   - Do conflicts cluster by conflict type (dependency, semantic, ordering)?
   - Per-wave reconciliation pass/fail rates.
   - Confidence: How predictable are conflicts?

4. PARANOID REVIEW ISSUES (Step 5)
   - What ship-blocking issues does paranoid review catch?
   - What issue categories (test gaps, edge cases, security)?
   - Issues found vs missed (paranoid_review_passed vs MUST_FIX).
   - Confidence: Coverage adequacy?

5. PLANS DELTA (Step 6)
   - Gap between plans_attempted and plans_completed.
   - Which plan types fail most often?
   - Confidence: Predictable failure modes?

EXECUTION CONTRACTS:
{traces}

Output ONLY valid JSON (no preamble, no markdown, no explanation):
{{
  "analysis_timestamp": "ISO 8601",
  "phases_analyzed": [list of phase numbers],
  "findings": [
    {{
      "category": "validation|architecture|reconciliation|paranoid_review|plans_delta",
      "pattern": "string (concrete observation)",
      "root_cause": "string (why this happens)",
      "affected_phases": ["193", "194", ...],
      "occurrence_count": number,
      "confidence": number (0.0-1.0),
      "recommendation": "string (specific, actionable improvement)",
      "example": "string (concrete example from traces)"
    }}
  ],
  "summary": {{
    "total_findings": number,
    "high_confidence": number (>= 0.75),
    "critical_path_bottleneck": "string (slowest/most-failed step)",
    "estimated_improvement_potential": "string (if all findings fixed, expected improvement)"
  }}
}}
"""


def load_traces(trace_files: list[str]) -> dict:
    """Load and parse JSONL trace files."""
    traces = {}
    for trace_file in trace_files:
        path = Path(trace_file)
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {trace_file}")

        with open(path) as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    phase = record.get("phase")
                    traces[phase] = record.get("execution_contract", {})

    return traces


def analyze_traces(trace_files: list[str], output_file: str | None = None) -> dict:
    """
    Analyze GSD Master traces using GPT-4o.

    Args:
        trace_files: List of JSONL trace file paths
        output_file: Optional output file for results (default: stdout)

    Returns:
        Parsed JSON findings dict
    """
    print(f"Loading traces from {len(trace_files)} file(s)...", file=sys.stderr)
    traces = load_traces(trace_files)

    if not traces:
        raise ValueError("No traces loaded from provided files")

    phase_count = len(traces)
    phases = sorted(traces.keys())

    print(f"Loaded {phase_count} phase(s): {', '.join(phases)}", file=sys.stderr)

    traces_json = json.dumps(traces, indent=2)

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(phase_count=phase_count, traces=traces_json)

    print("Sending analysis to GPT-4o...", file=sys.stderr)

    response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=4000
    )

    response_text = response.choices[0].message.content

    try:
        findings = json.loads(response_text)
    except json.JSONDecodeError:
        print("Failed to parse response as JSON:", file=sys.stderr)
        print(response_text[:500], file=sys.stderr)
        raise

    # Add cost metadata (GPT-4o: $5/1M input, $15/1M output)
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    cost_usd = (prompt_tokens / 1_000_000 * 5.0) + (completion_tokens / 1_000_000 * 15.0)

    findings["metadata"] = {
        "analyzed_at": datetime.utcnow().isoformat(),
        "trace_files": trace_files,
        "phases_analyzed": phases,
        "trace_count": phase_count,
        "model": "gpt-4o",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost_usd, 4),
    }

    output_json = json.dumps(findings, indent=2)

    if output_file:
        Path(output_file).write_text(output_json)
        print(f"Results written to: {output_file}", file=sys.stderr)
    else:
        print(output_json)

    return findings


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python halo_gsd_analyze.py <trace_file> [trace_file2 ...] [-o output_file]", file=sys.stderr)
        print("Example: python halo_gsd_analyze.py gsd_traces/phase_193_gsd.jsonl", file=sys.stderr)
        print(
            "Example: python halo_gsd_analyze.py gsd_traces/phase_193_gsd.jsonl gsd_traces/phase_194_gsd.jsonl -o findings.json",
            file=sys.stderr,
        )
        sys.exit(1)

    trace_files = []
    output_file = None

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "-o" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        else:
            trace_files.append(sys.argv[i])
            i += 1

    if not trace_files:
        print("Error: No trace files specified", file=sys.stderr)
        sys.exit(1)

    try:
        findings = analyze_traces(trace_files, output_file)
        print(f"\nAnalysis complete. {len(findings.get('findings', []))} findings identified.", file=sys.stderr)
        print(f"Cost: ${findings['metadata']['cost_usd']:.2f}", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
