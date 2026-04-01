# CLAUDE_LSP.md — LSP-First Enforcement

## Decision Rule (required before every search)

Before picking any search or navigation tool, answer this question:

**Is the target a code symbol?**
- function, method, class, variable, type, interface, API route, decorator

→ **Use LSP. Stop. Do not reach for grep.**

**Is the target literal text?**
- env values, log output, YAML/JSON data, comments, string literals, file names

→ **Use grep / Glob / Read.**

**Unsure?**
→ Try LSP first. Fall back to grep only if LSP returns no results.

---

## Justification Required

Before executing any search or navigation tool, state:

> "Looking for [X] — using [tool] because [symbol/literal/fallback]."

Examples of correct behaviour:

```
"Looking for BESSDispatchEngine definition → using LSP find_symbol (symbol)"
"Tracing callers of execute_dispatch → using LSP find_referencing_symbols (symbol)"
"Checking DATABASE_URL value in .env → using grep (literal string in config)"
"Finding migration files by name → using Glob (file pattern)"
```

Examples of incorrect behaviour (do not do this):

```
"Searching for BESSDispatchEngine..." → grep -r "BESSDispatchEngine"   ✗
"Finding where execute_dispatch is called..." → grep -rn "execute_dispatch"   ✗
```

This step is not optional. If you skip it, you are doing it wrong.

---

## Hard Blocks

**Do not use grep to:**
- find a function, method, or class definition
- find all references to a symbol
- trace call flow or callers
- locate the implementation of a known symbol
- rename a symbol

These are symbol-aware operations. LSP handles them more accurately and faster.
Using grep here is a category error, not a valid fallback.

---

## Escalation Fallback (when LSP fails)

If LSP returns no results for a known symbol:

1. Verify the symbol name — check spelling, casing, module path.
2. Try `get_symbols_overview` on the file where you expect the symbol to live.
3. Try workspace symbol search with a shorter substring.
4. Only after steps 1–3 fail: fall back to grep and explain why LSP could not answer.

Do not skip to grep because it feels faster.

---

## Tool Selection Matrix

| Task | Correct tool | Blocked tool |
|------|-------------|--------------|
| Find function / class definition | `mcp__sr__find_symbol` | grep for `def name` |
| Find all references to a symbol | `mcp__sr__find_referencing_symbols` | grep on symbol name |
| Get all symbols in a file | `mcp__sr__get_symbols_overview` | cat + skim |
| Rename a symbol across codebase | `mcp__sr__rename_symbol` | sed / text replace |
| Read a specific symbol body | `mcp__sr__find_symbol` with body | Read full file |
| Trace callers before editing | `mcp__sr__find_referencing_symbols` | grep |
| Check errors after an edit | `tsc --noEmit` / `ruff check` / Serena diagnostics | manual read |
| Find a file by name pattern | Glob | find / ls |
| Search log files or exports | Grep / Read | LSP |
| Search docs, comments, string literals | Grep | LSP |
| Search YAML / TOML / JSON config | Grep / Read | LSP |
| Search env values | Grep | LSP |

---

## Pre-Edit Protocol

Required before editing any function, class, type, or API endpoint that already has callers:

1. **State intent** — "I am about to edit X. Checking definition and blast radius."
2. **Definition** — `find_symbol` to read current signature and body.
3. **References** — `find_referencing_symbols` to map every caller.
4. **Assess impact** — list files that will need updating before writing any code.

Skip only for: brand-new symbols with no callers, pure config or data additions, doc edits.

---

## Post-Edit Protocol

After any logic, signature, or type change:

1. **Python** — `ruff check <file>` then `mypy <file>`. Fix all errors before continuing.
2. **TypeScript** — `cd frontend && npx tsc --noEmit`. Fix all errors before continuing.
3. **Stale index** — call `restart_language_server` after bulk edits made outside Serena.

Never mark a task complete while diagnostics report errors in files you touched.

---

## Post-Task Audit

After completing a task, answer:

> "Did I use LSP wherever the target was a code symbol? If not, why?"

If the answer is "I used grep because it was faster" — that is the wrong answer.
If the answer is "I used grep because LSP returned no results after escalation steps 1–3" — that is acceptable.

---

## Symbol Rename Rules

- Use `mcp__sr__rename_symbol` whenever the symbol is indexed.
- Never rename a Python function, class, method, TypeScript type, interface, or exported symbol with text replacement.
- Cross-language renames (e.g., a Python route that appears as a string in TypeScript fetch calls): LSP rename on each side, then grep to catch remaining string literals.

---

## When Grep / Glob Is Correct

Use grep or Glob — not LSP — for:

- Log files, exported CSVs, JSON data files
- File discovery by name pattern (Glob)
- Documentation (`.md`, `.txt`, `.rst`)
- YAML / TOML config that is not compiled source
- Literal strings in comments or string values
- Confirming migration or data file content
- Any target that is not a navigable code symbol

---

## Language Coverage

| Language | LSP provider | Key capabilities |
|----------|--------------|-----------------|
| Python | Serena (solidlsp / Pyright) | find_symbol, references, symbols_overview, rename, diagnostics |
| TypeScript / React | Serena (solidlsp typescript) | find_symbol, references, symbols_overview, rename, diagnostics |
| JSON / YAML / TOML | Grep + Read | n/a |
| Shell / Bash | Grep + Read | n/a |

---

## TypeScript-Specific Rules

`verbatimModuleSyntax` is enforced. Always separate type imports:

```typescript
// WRONG
import { devicesApi, type Device } from '@/lib/api'

// CORRECT
import { devicesApi } from '@/lib/api'
import type { Device } from '@/lib/api'
```

Path alias `@/*` maps to `src/*`. Use it consistently.

---

## Python-Specific Rules

- All new functions require type annotations (`disallow_untyped_defs = true`).
- Five legacy modules carry `ignore_errors = true` in `pyproject.toml` — do not add new ones.
- Pyright is the navigation layer. mypy is the strict correctness gate. Both must pass.

---

## Excluded Paths

```
node_modules/   dist/   build/   __pycache__/
.pytest_cache/  coverage/  htmlcov/  *.egg-info/
logs/           exports/
```

Do not exclude paths containing source code, schemas, migrations, or runtime config.

---

**Version:** 2.0 | **Applies to:** all agent sessions in this repo
**Change:** Guidance → enforcement. Decision rule, justification gate, hard blocks, escalation ladder.
