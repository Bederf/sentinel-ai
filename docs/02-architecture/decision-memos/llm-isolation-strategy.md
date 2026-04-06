---
title: "Decision Memo: Local LLM Migration & Processing Isolation"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Decision Memo: Local LLM Migration & Processing Isolation
**Date**: 2026-03-18
**Status**: DRAFT - Awaiting Stakeholder Review
**Author**: Architecture Review

---

## Executive Summary

Based on comprehensive discovery, our AI architecture is **not** "LLM everywhere". We have:
- **33% deterministic components** (no LLM used, despite misleading abstractions)
- **35% easily migratable** to local small models
- **25% requiring API models** for the foreseeable future

**Recommended Approach**: Two workstreams
1. **Workstream A**: Phased Ollama migration (focus: cost reduction, maintain quality)
2. **Workstream B**: Processing isolation (focus: security, don't over-engineer)

**Decision Required**: Approve Workstream A Phase 1 (2 weeks) before proceeding to Phase 2.

---

## Workstream A: Ollama Local LLM Migration

### Philosophy
- **Keep deterministic parts deterministic** (stop pretending they're AI)
- **Use one small local model first** (prove value before complexity)
- **Define risk classes explicitly** before splitting traffic
- **Narrow vision scope** (OCR-first, not general multimodal)
- **Defer fine-tuning** until baseline proves insufficient

### Current State (Corrected)

**Tier 1: Already Deterministic (33% - Remove from AI tracking)**
```
✅ Telegram Intent Classifier → Regex rules
✅ System Health Service → HTTP health aggregation
✅ Decision Memory Service → JSON pattern matching
✅ AI Recommendation Engine → Formula-based ROI calculations
✅ Document Text Extraction → pdftotext subprocess
✅ Workflow Triggers → Rule/threshold engine
```

**Tier 2: Currently Cloud, Migratable (35%)**
```
⚠️  Concept Document Relevance → GPT-4.1-heavy (API)
⚠️  Maintenance Recommender LLM path → CloudLLMClient (Claude)
⚠️  OCR Stage 3 Enhance/Correct → CloudLLMClient (Claude)
⚠️  RAG Service → CloudLLMClient (Claude)
⚠️  Anomaly Explanation Service → CloudLLMClient (Claude)
```

**Tier 3: API-Only (25%)**
```
🔒 Sentry Bot Chat Replies → Claude (tool use, streaming)
🔒 AI Optimizer Planning → Claude (multi-step reasoning)
🔒 Complex Equipment Queries → Claude (ambiguity resolution)
🔒 OCR Stage 1 Vision → Claude Vision (multimodal)
🔒 Vision-Based Equipment ID → Claude Vision (multimodal)
```

**Key Finding**: All Tier 2/3 components use `get_ollama_client()` but **actually route to CloudLLMClient** unless `USE_OLLAMA=true`. The Ollama architecture exists but is **never activated**.

### Phase 1: Truth & Instrumentation (Week 1)

**Goal**: Establish factual baseline before migration

**Tasks**:
1. **Rename Misleading Abstractions**
   - `get_ollama_client()` → `get_llm_client()`
   - Update docstrings: "Returns cloud API by default, local if USE_OLLAMA=true"

2. **Add Comprehensive Logging**
   ```python
   # For every LLM call site, log:
   {
     "timestamp": "2026-03-18T10:30:00Z",
     "provider": "anthropic|openai|zai|ollama",
     "model": "claude-sonnet|gpt-4.1|phi3:mini",
     "task": "rag_answer|maintenance_rec|ocr_enhance",
     "streaming": true|false,
     "tool_use": true|false,
     "structured_output": true|false,
     "input_tokens": 1234,
     "output_tokens": 567,
     "latency_ms": 2450
   }
   ```

3. **Tag Every Call Site**
   - Add decorator `@llm_task(tier=2, capabilities=["generate"])`
   - Mark safe for local: Yes/No with justification

4. **Remove Tier 1 from AI Tracking**
   - Stop billing/metrics for deterministic components
   - Document as "rule-based" in system architecture

**Deliverable**: Real-time dashboard showing actual model usage by task

**Decision Gate**: Verify X% of "AI features" are actually rules (expected: 33%)

### Phase 2: Single-Model Local Pilot (Weeks 2-3)

**Goal**: Validate local inference with one small model

**Model Selection**: **phi3:mini (3.8B parameters)**
- Reason: General-purpose, fast on Orin, Apache 2.0 license
- Not adding Codestral yet (specialist model premature)

**Migration Tasks**:
1. **Enable Local Inference**
   ```bash
   # On Orin Nano
   export USE_OLLAMA=true
   ollama pull phi3:mini
   ```

2. **Migrate Three Target Tasks**:
   - **Concept Document Relevance**: Rank search results
   - **Maintenance Recommender Fallback**: Enhance default recommendations
   - **OCR Field Normalization**: Clean extracted text

3. **Establish Quality Benchmarks**:
   - Concept relevance: ≥90% match with GPT-4.1 scores
   - Maintenance recs: 80% identical to fallback rules
   - OCR normalization: 85% field accuracy vs. clean data

**Success Criteria**:
- phi3:mini serves requests without OOM
- Latency: <5s for 95th percentile
- User satisfaction: ≥4/5 on migrated features

**Rollback**: One-line config change → `USE_OLLAMA=false`

**Deliverable**: Benchmark report comparing API vs local quality/latency

**Decision Gate**: Proceed if 2/3 tasks pass quality bar

### Phase 3: RAG Risk-Based Routing (Weeks 4-5)

**Goal**: Split RAG traffic by query risk

**Risk Classification (Define Explicitly)**

```python
LOW_STAKES_QUERIES = [
    "What is the filter part number for AHU-104?",
    "When was chiller last serviced?",
    "Summarize the maintenance manual section 5.2",
    "What tools should I bring for split inspection?"
]

HIGH_STAKES_QUERIES = [
    "Should I shut down this equipment?",
    "Is this fault critical?",
    "What is the compliance risk?",
    "Recommend maintenance action for E4 fault"
]

RISK_INDICATORS = {
    "low": ["part number", "date", "summary", "manual", "tool list"],
    "high": ["shut down", "critical", "compliance", "recommend", "action"]
}
```

**Implementation**:
1. Add `classify_query_risk(query: str) → RiskLevel` function
2. Route low-risk → phi3:mini (local)
3. Route high-risk → Claude (API)
4. Log routing decisions and outcomes

**Success Criteria**:
- 60% of RAG queries classified as low-risk
- Local answers rated ≥4/5 quality
- High-risk queries show no quality degradation

**Rollback**: Feature flag → `RAG_SPLIT_ENABLED=false`

**Deliverable**: Risk classification rules + A/B test results

**Decision Gate**: Only proceed if classification is reliable (>90% accuracy)

### Phase 4: Narrow Vision Pipeline (Weeks 6-8)

**Goal**: OCR-first approach for nameplates/service sheets

**Important**: Do NOT start with LLaVA-13B. Too large, too slow, too much upfront investment.

**Pipeline**:
```
Image Upload
  ↓
Preprocessing (deskew, denoise, enhance contrast)
  ↓
OCR (easyocr/paddleocr) - extract raw text
  ↓
Regex/Template Matching - parse fields
  ↓
Validation - check required fields present
  ↓
IF validation fails:
  → phi3:mini for field correction (local)
  → OR Claude Vision for messy images (API) - <10% of cases
```

**Scope Limitation**:
- **Not**: "General vision-based equipment identification"
- **IS**: "Extract nameplate fields from service sheet photos"
- Target: 5 fields (manufacturer, model, serial, capacity, date)

**Benchmark**:
- API-only baseline: 85% field accuracy
- OCR + local cleanup target: ≥80% field accuracy
- Acceptable: 5% degradation vs API

**Success Criteria**:
- OCR-first succeeds on 80% of uploads
- Local phi3:mini handles 15% of edge cases
- API Claude Vision needed for <5% (messy handwriting, poor lighting)

**Rollback**: Backend can revert to full API path with feature flag

**Deliverable**: Vision pipeline architecture + accuracy comparison

**Decision Gate**: Proceed only if local pipeline hits 80%+ accuracy

### Phase 5: Chat Task Decomposition (Months 3-6)

**Goal**: Classify chat requests to identify localizable sub-tasks

**NOT**: Full chat migration or fine-tuning (too complex, too early)

**Approach**:
1. **Collect & Classify** 10,000+ real chat conversations
2. **Identify narrow task buckets**:
   - Equipment lookup by code (deterministic)
   - Fault code explanation (RAG)
   - Parts list query (RAG)
   - Safety procedure ask (RAG)
   - Complex diagnosis (requires API)

3. **Test local models on single buckets**:
   - Deploy phi3:mini specialized for "equipment lookup"
   - Canary: 5% of traffic for this bucket only
   - Measure: user satisfaction, follow-up questions

**Deliverable**: Chat task taxonomy + local model performance by task type

**Decision Gate**: Fine-tuning only considered after base model proves promising on narrow task

---

## Workstream B: Processing Isolation

### Problem Statement

Current processing runs **inside main FastAPI process**:
- File uploads → Async workers → Document scanner → Storage → DB
- This process has broad filesystem and network access
- OCR subprocesses (pdftotext, clamdscan) are isolated but parent isn't

**Risk**: Malicious upload could exploit parser vulnerability, access sensitive files

### Solution Direction

**NOT**: "Deploy OpenShell everywhere" (overkill)

**IS**: "Isolate upload/processing from main API"

### Recommended Approach: Graduated Isolation

#### Level 1: Process Separation (Immediate - Week 1)

**Implementation**:
- Extract upload handling to **dedicated worker service**
- Service runs as `sentinel-upload` user (no shell, limited privileges)
- Only access: `/tmp` (ephemeral), Supabase API (HTTP), stdout logging
- Main API POSTs to worker via localhost HTTP, gets callback on completion

**Benefits**:
- Upload processing crash doesn't affect main API
- Worker can't access main API's config, keys, or filesystem
- Simple implementation (FastAPI background task pattern)

**Code Changes**:
```python
# Instead of:
@router.post("/upload")
async def upload_document(...):
    scan_result = await validate_and_scan_upload(...)  # In process

# Do:
@router.post("/upload")
async def upload_document(...):
    task = await upload_worker.submit(file_content, metadata)  # HTTP to worker
    return {"task_id": task.id, "status": "queued"}
```

**Cost**: ~3 days development

#### Level 2: OS-level Confinement (Month 2)

**If Level 1 proves insufficient**:

**Option A: AppArmor Profile**
```bash
# /etc/apparmor.d/sentinel-upload-worker
profile sentinel-upload-worker {
  # Allow: read /tmp, write to specific log dir
  # Deny: network except localhost:55321 (Supabase)
  # Deny: all file writes outside /tmp/uploads
  # Deny: execution of any binaries except pdftotext, clamdscan
}
```

**Option B: Bubblewrap (Alternative to OpenShell)**
```bash
# Run worker in sandbox
bwrap \
  --ro-bind /usr/bin/pdftotext /usr/bin/pdftotext \
  --ro-bind /usr/bin/clamdscan /usr/bin/clamdscan \
  --tmpdir /tmp \
  --unshare-all \
  --die-with-parent \
  python -m sentinel.upload_worker
```

**Option C: OpenShell**
- Only if AppArmor/bwrap proves too complex
- Evaluate if OpenShell adds value beyond these simpler tools

**Benefits**:
- Even if worker is compromised, attacker can't escape sandbox
- Prevents lateral movement to other services

**Cost**: 1-2 weeks to implement and test

**Decision Gate**: Only proceed to Level 2 if security audit identifies vulnerabilities in upload pipeline

#### Level 3: Full Agent Sandboxing (Future)

**When**: If/when we add autonomous agent workflows that execute untrusted code

**Tools to Evaluate**:
- **OpenShell**: If we need rich agent capabilities with controlled resource access
- **Firecracker/Kata Containers**: If we need VM-level isolation
- **gVisor**: If we need kernel syscall filtering

**Current Position**: **NOT NEEDED YET**
- Sentry bot tools are read-only queries (no execution)
- Tech chat doesn't execute code
- Upload processing uses subprocesses with timeouts

**Recommendation**: Defer OpenShell decision until we have concrete use case requiring it

---

## Resource Requirements

### Workstream A (Ollama Migration)

**Hardware** (Already owned):
- 1x Nvidia Jetson Orin Nano Super (8GB) - R4,500 (one-time)

**Software**:
- Ollama (open source)
- phi3:mini model (open source, Apache 2.0)
- 40GB disk space for models

**Engineering Time**:
- Phase 1: 1 week (1 engineer)
- Phase 2: 2 weeks (1 engineer + QA)
- Phase 3: 2 weeks (1 engineer)
- Phase 4: 3 weeks (1 engineer + QA)
- Phase 5: Ongoing, 20% of AI engineer time

**Total**: ~8 weeks initial, then 20% ongoing

### Workstream B (Isolation)

**Hardware**: None additional

**Engineering Time**:
- Level 1: 3 days (1 engineer)
- Level 2: 1-2 weeks (1 engineer) - *only if needed*
- Level 3: Not estimated (deferred)

---

## Decision Points

### Immediate Decision (This Week)

**Approve Phase 1: Truth & Instrumentation**
- Cost: 1 week, 1 engineer
- Risk: Very low (observability only)
- Benefit: Real usage data, remove false AI dependencies

**Decision Required**: Yes/No

**If No**: We continue flying blind on actual LLM usage

**If Yes**: Proceed to Phase 2 after Phase 1 deliverables complete

### Near-term Decision (Week 3)

**Approve Phase 2: Local Model Pilot**
- Cost: 2 weeks, 1 engineer + QA
- Risk: Medium (quality validation required)
- Benefit: R3k/month savings if successful

**Decision Required**: Yes/No/Modify (different model selection)

**Gating**: Only if Phase 1 shows sufficient Tier 2 usage to justify migration

### Future Decision (Month 3)

**Approve Processing Isolation Level 2**
- Cost: 1-2 weeks
- Risk: Medium (operational complexity)
- Benefit: Security hardening

**Decision Required**: Only if security audit identifies upload pipeline vulnerabilities

---

## Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Phi3:mini quality insufficient** | Medium | Medium | Rollback to API; try larger model (phi3:small) |
| **Orin performance unacceptable** | Low | Medium | Benchmark rigorously in Phase 2; have API fallback |
| **Hidden tool dependencies** | Medium | **High** | Audit all 9 call sites in Phase 1 for tool use |
| **User trust drops** | Medium | **High** | Canary deployments; satisfaction surveys; rapid rollback |
| **OpenShell adds complexity** | Medium | Low | Defer decision; evaluate simpler isolation first |

---

## Recommendation

**Approve Workstream A Phase 1 immediately**.

The cost is low (1 week), risk is minimal, and we cannot make informed decisions without real usage data.

**Defer Workstream B Level 2/3** until Level 1 is proven insufficient or security audit demands it.

**Do not integrate OpenShell** at this time - simpler tools (AppArmor/bwrap) likely sufficient.

---

## Next Steps

1. **This Week**: Stakeholder review and Phase 1 approval
2. **Week 1**: Execute Phase 1 (instrumentation)
3. **Week 2**: Review Phase 1 deliverables
4. **Week 3**: Decision on Phase 2 (local model pilot)
5. **Ongoing**: Workstream B Level 1 (process separation) in parallel

---

**Decision Log**:

| Date | Decision | Made By | Rationale |
|------|----------|---------|-----------|
| (To be filled) | Approve Phase 1 | (To be filled) | (To be filled) |
