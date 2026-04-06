---
title: "Improvement Protocol"
type: "guide"
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

### Improvement protocol integration

Use it with your existing skills, not instead of them. This should not become “another main skill.” It should act like an execution mode or sub-workflow that gets called when a skill needs controlled improvement:

**Simple answer**

**GSD master skill**

Yes. GSD master is the main place it fits because it already handles planning, discovery, coordination, and controlled delivery. It can decide whether a task needs:

- normal implementation  
- discovery only  
- bounded improvement mode  
- debt gate review  

So the improvement protocol should sit closest to GSD master.

---

**Diary skill**

Not mainly. The diary skill should usually stay what it is: record of what happened, decisions made, outcomes, iteration logs, lessons learned. Diary does not run the protocol; it documents it.

Think of it this way:

1. GSD master decides and orchestrates  
2. Domain skill does the actual subsystem work  
3. Improvement protocol controls how the change is attempted  
4. Diary skill records what happened

---

**Best operating model**

1. GSD master = controller  
 - Is this a normal task?  
 - Is this a discovery task?  
 - Is this an optimisation task?  
 - Does this need bounded improvement mode?  
 - Does this need debt gate review?  

2. Domain skills = implementers (graph/map skill, ghost-booking, block-booking, notification, etc.)  
These skills remain domain-specific and, when needed, run using the improvement protocol (scan → bounded improve → debt gate).

3. Diary skill = memory/logbook  
It captures candidate, metric, verify/guard commands, iterations, results, keep/discard decision, and debt observations.

---

**Recommended integration pattern**

A. **GSD master** – orchestrator  
Responsibilities: decide whether improvement protocol is needed, choose subsystem, enforce scope, require metric and guard, call debt gate before acceptance.

B. **Shared improvement protocol** – internal reusable method  
Responsibilities: opportunity scan, bounded improve rules, debt gate checklist, eval output contract. Not user-facing; invoked by domain skills.

C. **Domain skills** – subsystem execution  
Responsibilities: apply the protocol to the actual subsystem while keeping changes within existing architecture.

D. **Diary skill** – continuity and recordkeeping  
Responsibilities: persist the note/outcome and provide historical continuity.


---

**In practice**

Example 1. Graph/map change  
1. GSD master matches it as a focused improvement task  
2. Invokes graph skill in improvement mode  
3. Graph skill runs opportunity scan → bounded improve → debt gate  
4. Diary logs the loop and result

Example 2. Ghost booking tuning  
1. GSD master classifies it as measurable optimisation  
2. Ghost-booking skill runs bounded improvement mode  
3. Eval runner scores precision/recall/F1  
4. Debt gate checks complexity  
5. Diary logs the outcome

Example 3. Big architecture decision  
1. GSD master decides bounded improve is not appropriate  
2. Uses normal planning/discovery mode  
3. Diary records the decision  
4. Improvement protocol is not used

---

**What not to do**

Do not:
- create a separate “autoresearch skill” users must invoke manually  
- have the diary skill decide  
- force every task through bounded improve mode  
- let GSD master be bypassed by ad hoc loops

---

**Practical rule**

Use the improvement protocol only when all are true:
- task is narrow  
- success is measurable  
- there is a clear guard  
- rollback is easy  
- debt risk can be judged  

If not, keep the task in the normal workflow.

---

**Clean one-line model**

“The improvement protocol is governed by GSD master, executed through existing domain skills when a task is measurable and bounded, and recorded through the diary skill for continuity and future learning.”

---

**Plan recommendation**

Structure the comprehensive plan like this:

- **GSD master**: orchestration and decision point  
- **Shared improvement protocol**: internal reusable method  
- **Domain skills**: subsystem execution  
- **Diary skill**: continuity and recordkeeping  

This keeps each skill focused and prevents overlap.

---

**Artifact simplification mode (command wrapper safe)**

Use `/simplify` style command wrappers as a thin trigger for rewriting artifacts only.

Input contract:
- current task, plan, prompt, report, or handoff draft
- explicit constraints that must not be lost
- known next actions (if available)

Transform rules:
- remove repetition and vague language
- collapse branching text into the smallest correct executable form
- preserve intent, hard constraints, and required sequencing
- produce concrete action language

Output contract:
- concise and execution-ready
- constraints preserved
- clear next actions
- no new orchestration policy introduced by the command

Authority rule:
- simplification wrappers are non-authoritative
- if simplified output conflicts with GSD gates, GSD wins

---

**Failure recovery and verification protocol (GSD-native)**

Treat this as a named sub-protocol under GSD master governance.
Do not import manipulative framing or rhetoric from external prompt packs.

1. **No unverified completion**
   - Never mark work complete without evidence.
   - Evidence should come from tests, build/lint/type checks, or observed runtime behavior.

2. **Anti-spin control**
   - After 2 failed attempts, do not repeat the same fix shape.
   - Attempt 3 must materially change method and assumptions.

3. **Root-cause-first discipline**
   - Inspect real errors/logs/source before patching when available.
   - Avoid guess-first patching when direct evidence exists.

4. **Proactive closure checks**
   - After fixing one issue, inspect adjacent modules and duplicate patterns.
   - Record residual risk and required follow-up checks.

5. **Escalation ladder**
   - Attempt 1: direct evidence-based fix
   - Attempt 2: alternate approach
   - Attempt 3: structured diagnosis checklist
   - Attempt 4+: broaden dependency and assumption analysis
