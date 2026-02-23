"""RecursiveAnalyzer — multi-pass evidence analysis with budget enforcement.

Core analysis engine: loads case evidence, sends to LLM in recursive passes,
tracks budget (time + depth), applies POPIA redaction, and builds result.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import ResultSchema, TrajectoryData
from app.services.case_loader import CaseLoader
from app.services.inference_client import ChatResult, InferenceClient, get_inference_client
from app.services.redaction_service import RedactionService, redaction_service
from app.services.trace_builder import TraceBuilder, trace_builder

logger = logging.getLogger(__name__)

# Text-based file extensions the analyzer can read directly
READABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".json", ".jsonl", ".csv", ".txt", ".md", ".log", ".syslog",
})

# System prompt for evidence analysis
SYSTEM_PROMPT = (
    "You are an evidence analyst for a building management system (BMS). "
    "You analyze equipment logs, sensor data, maintenance records, and operational "
    "events to identify anomalies, root causes, and recommended actions. "
    "Respond in JSON format with the following fields: "
    '"findings" (list of strings), "anomalies" (list of objects with "description" '
    'and "severity"), "timeline" (list of objects with "time" and "description"), '
    '"recommended_actions" (list of strings), "confidence" (float 0-1), '
    '"needs_deeper" (boolean — true if you need more passes to be confident). '
    "Be precise, factual, and concise."
)


class BudgetState:
    """Tracks resource budget for a single analysis run."""

    def __init__(self, max_runtime: float, max_depth: int) -> None:
        self.start_time = time.monotonic()
        self.max_runtime = max_runtime
        self.max_depth = max_depth
        self.current_depth = 0
        self.files_read = 0
        self.bytes_read = 0

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def remaining_s(self) -> float:
        return self.max_runtime - self.elapsed_s

    def can_continue(self) -> bool:
        """Check if budget allows another pass (time + depth)."""
        return (
            self.current_depth < self.max_depth
            and self.remaining_s > 15.0  # Need at least 15s for an LLM call
        )


class RecursiveAnalyzer:
    """Performs multi-pass LLM analysis of case evidence with budget enforcement."""

    def __init__(
        self,
        inference_client: InferenceClient | None = None,
        case_loader: CaseLoader | None = None,
        redaction_svc: RedactionService | None = None,
        trace: TraceBuilder | None = None,
    ) -> None:
        self._client = inference_client or get_inference_client()
        self._case_loader = case_loader or CaseLoader()
        self._redaction = redaction_svc or redaction_service
        self._trace = trace or trace_builder

    async def analyze(
        self,
        case_id: str,
        question: str,
        model: str,
        run_id: str,
    ) -> ResultSchema:
        """Run full analysis pipeline.

        Flow:
        1. Load case via CaseLoader
        2. Read text-based evidence files
        3. Recursive LLM passes with budget enforcement
        4. Redact PII from output
        5. Return ResultSchema
        """
        budget = BudgetState(
            max_runtime=settings.max_runtime_seconds,
            max_depth=settings.max_recursion_depth,
        )

        # 1. Load case
        case_data = self._case_loader.load_case(case_id)
        evidence_files = case_data["evidence_files"]
        blocked_files = case_data.get("blocked_files", [])

        # Log blocked files in trace
        for bf in blocked_files:
            self._trace.capture_step(
                run_id, 0, "file_blocked", f"Blocked file type: {bf}"
            )

        # 2. Read evidence files (text-based only)
        evidence_text = await self._read_evidence(
            run_id, evidence_files, budget
        )

        if not evidence_text.strip():
            # No readable evidence — return empty result
            return ResultSchema(
                status="complete",
                summary="No readable evidence files found in case.",
                confidence=0.0,
                trajectory=TrajectoryData(
                    steps=0,
                    files_read=budget.files_read,
                    bytes_read=budget.bytes_read,
                    elapsed_s=round(budget.elapsed_s, 2),
                ),
            )

        # 3. Recursive analysis loop
        all_findings: list[str] = []
        all_anomalies: list[dict[str, Any]] = []
        all_timeline: list[dict[str, Any]] = []
        all_actions: list[str] = []
        confidence = 0.0
        needs_deeper = False
        summary = ""

        previous_findings: str = ""

        # If budget is already exhausted before first pass, flag needs_deeper
        if not budget.can_continue():
            needs_deeper = True

        while budget.can_continue():
            budget.current_depth += 1

            # Build messages for this pass
            user_content = self._build_user_message(
                question, evidence_text, previous_findings, budget.current_depth
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            # Budget check: enough time remaining?
            if budget.remaining_s < 15.0:
                needs_deeper = True
                break

            # Call LLM
            call_start = time.monotonic()
            try:
                chat_result: ChatResult = await self._client.chat(
                    messages=messages,
                    model=model,
                    max_tokens=settings.max_tokens_per_call,
                )
            except Exception as exc:
                logger.error("LLM call failed at depth %d: %s", budget.current_depth, exc)
                return ResultSchema(
                    status="error",
                    summary=f"LLM inference error: {exc}",
                    findings=all_findings,
                    anomalies=all_anomalies,
                    timeline=all_timeline,
                    recommended_actions=all_actions,
                    confidence=confidence,
                    trajectory=TrajectoryData(
                        steps=budget.current_depth,
                        files_read=budget.files_read,
                        bytes_read=budget.bytes_read,
                        elapsed_s=round(budget.elapsed_s, 2),
                    ),
                )

            call_elapsed_ms = (time.monotonic() - call_start) * 1000

            # Trace model call (hashes only, no raw text)
            prompt_text = json.dumps(messages)
            self._trace.capture_model_call(
                run_id=run_id,
                model=model,
                input_tokens=chat_result.input_tokens,
                output_tokens=chat_result.output_tokens,
                prompt_hash=TraceBuilder.hash_text(prompt_text),
                response_hash=TraceBuilder.hash_text(chat_result.text),
                elapsed_ms=call_elapsed_ms,
            )

            # Parse response
            parsed = self._parse_response(chat_result.text)

            # Accumulate findings
            all_findings.extend(parsed.get("findings", []))
            all_anomalies.extend(parsed.get("anomalies", []))
            all_timeline.extend(parsed.get("timeline", []))
            all_actions.extend(parsed.get("recommended_actions", []))
            confidence = max(confidence, parsed.get("confidence", 0.0))
            summary = parsed.get("summary", summary)
            wants_deeper = parsed.get("needs_deeper", False)

            # Log step
            self._trace.capture_step(
                run_id=run_id,
                step_number=budget.current_depth,
                action=f"llm_pass_depth_{budget.current_depth}",
                result_summary=f"findings={len(parsed.get('findings', []))}, "
                               f"confidence={parsed.get('confidence', 0.0)}",
            )

            # Build previous findings for next pass
            previous_findings = json.dumps({
                "findings": all_findings,
                "anomalies": all_anomalies,
                "confidence": confidence,
            })

            # Decision: continue or stop
            if not wants_deeper:
                break  # LLM is satisfied

            if not budget.can_continue():
                needs_deeper = True
                break

        # Check if we hit limits
        if budget.current_depth >= budget.max_depth:
            needs_deeper = True
        if budget.remaining_s <= 0:
            needs_deeper = True

        # Build summary if not provided by LLM
        if not summary:
            summary = (
                f"Analysis completed in {budget.current_depth} pass(es). "
                f"Found {len(all_findings)} findings, "
                f"{len(all_anomalies)} anomalies. "
                f"Confidence: {confidence:.2f}."
            )

        # 4. Build result
        result = ResultSchema(
            status="complete",
            summary=summary,
            findings=all_findings,
            anomalies=all_anomalies,
            timeline=all_timeline,
            recommended_actions=all_actions,
            confidence=confidence,
            needs_deeper_run=needs_deeper,
            trajectory=TrajectoryData(
                steps=budget.current_depth,
                files_read=budget.files_read,
                bytes_read=budget.bytes_read,
                elapsed_s=round(budget.elapsed_s, 2),
            ),
        )

        # 5. Redact PII from output
        redacted_dict = self._redaction.redact_result(result.model_dump())

        return ResultSchema(**redacted_dict)

    async def _read_evidence(
        self,
        run_id: str,
        evidence_files: list[str],
        budget: BudgetState,
    ) -> str:
        """Read text-based evidence files and concatenate their contents.

        Tracks bytes read and files read in budget.
        Computes SHA256 for each file via TraceBuilder.
        """
        parts: list[str] = []

        for file_str in evidence_files:
            file_path = Path(file_str)
            ext = file_path.suffix.lower()

            if ext not in READABLE_EXTENSIONS:
                continue

            if not file_path.is_file():
                continue

            try:
                size = file_path.stat().st_size
                sha256 = TraceBuilder.compute_sha256(file_path)

                content = file_path.read_text(errors="replace")
                budget.files_read += 1
                budget.bytes_read += size

                self._trace.capture_file_access(
                    run_id=run_id,
                    file_path=file_path,
                    sha256=sha256,
                    size_bytes=size,
                )

                parts.append(f"--- FILE: {file_path.name} ---\n{content}\n")

            except Exception as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)

        return "\n".join(parts)

    def _build_user_message(
        self,
        question: str,
        evidence_text: str,
        previous_findings: str,
        depth: int,
    ) -> str:
        """Construct the user message for a given pass depth."""
        parts = [f"Question: {question}\n"]

        if depth == 1:
            parts.append(f"Evidence:\n{evidence_text}\n")
            parts.append(
                "Analyze the evidence above. Return JSON with findings, anomalies, "
                "timeline, recommended_actions, confidence (0-1), and needs_deeper (bool)."
            )
        else:
            parts.append(f"Previous analysis (depth {depth - 1}):\n{previous_findings}\n")
            parts.append(f"Evidence (for reference):\n{evidence_text[:2000]}\n")  # Truncate for deeper passes
            parts.append(
                "Review your previous analysis. Refine findings, update confidence, "
                "and set needs_deeper=false if analysis is complete."
            )

        return "\n".join(parts)

    def _parse_response(self, text: str) -> dict[str, Any]:
        """Parse LLM response — try JSON first, fall back to string extraction."""
        # Try direct JSON parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return self._normalize_parsed(data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try extracting JSON from markdown code block
        try:
            if "```json" in text:
                start = text.index("```json") + 7
                end = text.index("```", start)
                data = json.loads(text[start:end].strip())
                if isinstance(data, dict):
                    return self._normalize_parsed(data)
            elif "```" in text:
                start = text.index("```") + 3
                end = text.index("```", start)
                data = json.loads(text[start:end].strip())
                if isinstance(data, dict):
                    return self._normalize_parsed(data)
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

        # Fallback: treat entire response as a single finding
        return {
            "summary": text[:200],
            "findings": [text[:500]] if text.strip() else [],
            "anomalies": [],
            "timeline": [],
            "recommended_actions": [],
            "confidence": 0.3,  # Low confidence for unparsed responses
            "needs_deeper": False,
        }

    def _normalize_parsed(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize parsed LLM response to expected schema fields."""
        # Ensure summary is a string (some models return it as a dict)
        raw_summary = data.get("summary", "")
        if not isinstance(raw_summary, str):
            raw_summary = json.dumps(raw_summary, indent=2) if raw_summary else ""

        # Ensure findings are strings
        raw_findings = data.get("findings", [])
        findings = [str(f) if not isinstance(f, str) else f for f in raw_findings] if isinstance(raw_findings, list) else []

        return {
            "summary": raw_summary,
            "findings": findings,
            "anomalies": data.get("anomalies", []),
            "timeline": data.get("timeline", []),
            "recommended_actions": data.get("recommended_actions", []),
            "confidence": float(data.get("confidence", 0.0)),
            "needs_deeper": bool(data.get("needs_deeper", False)),
        }
