# Security-Relevant Function Signatures

Reference document for the SENTINEL security module. Documents all function
signatures from the 9 security-relevant source files that the security module
will wrap, extend, or replace.

---

## 1. `backend/app/api/chat.py`

**Main chat endpoint and SSE streaming.**

```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    search_docs: bool = False
    site_id: str | None = None

def format_sse_chunk(chunk: str) -> str:
    """Format a chunk for SSE transmission, handling newlines properly."""

async def generate_sse_stream(
    user_message: str,
    use_tools: bool = True,
    site_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
    data_subject_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE-formatted stream from Claude response."""

@router.post("/chat")
@limiter.limit("20/minute")
async def chat(request: FastAPIRequest, chat_request: ChatRequest) -> StreamingResponse:
    """Chat with Claude AI using Server-Sent Events streaming."""
```

**Security-relevant calling context:**
- `check_query_safety(user_message)` is called before any AI processing (line 294)
- `site_id` is passed from user input directly into context prefix (line 173)
- SSE chunks are emitted without output filtering (lines 213-233)
- Auth context is extracted via `get_current_auth(request)` (line 308)
- Rate limited to 20/minute via slowapi (line 267)

---

## 2. `backend/app/services/chat_tools.py`

**Tool execution for Claude AI -- device control, queries, work orders.**

```python
def get_chat_tools(
    site_id: str | None = None,
    *,
    user_email: Optional[str] = None,
    user_role: Optional[SentinelRole] = None,
) -> list[dict[str, Any]]:
    """Return chat tools filtered by active modules and user role."""

async def execute_tool(
    tool_name: str,
    tool_input: dict,
    site_id: str | None = None,
    user_email: Optional[str] = None,
    user_role: Optional[SentinelRole] = None,
) -> dict[str, Any]:
    """Execute a tool by name with given input."""
```

**Security-relevant calling context:**
- `get_chat_tools()` filters tools by role hierarchy (ROLE_HIERARCHY) and module access
- `execute_tool()` dispatches to individual tool functions -- tool results re-enter the Claude message context
- Tool results are not scanned for secrets before being sent back to Claude
- No per-tool rate limiting; relies on the chat endpoint's 20/min limit

---

## 3. `backend/app/services/claude_service.py`

**Claude API integration -- message sending and tool loop.**

```python
class ClaudeService:
    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        include_building_context: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream a response from Claude (no tools)."""

    async def stream_response_with_tools(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        include_building_context: bool = True,
        site_id: str | None = None,
        user_email: str | None = None,
        user_role: SentinelRole | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response from Claude with tool calling support."""

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
```

**Security-relevant calling context:**
- `stream_response_with_tools()` implements a tool loop: stream -> check stop_reason -> if tool_use: execute tools, append results, loop
- Tool results from `execute_tool()` are appended directly to the messages list and re-sent to Claude
- System prompt includes full building context -- potential for context poisoning if building data is attacker-controlled
- No output filtering on streamed text chunks before they reach the SSE generator

---

## 4. `backend/app/services/prompt_injection_guard.py`

**Prompt injection detection with pattern matching.**

```python
@dataclass
class PromptInjection:
    pattern: str
    severity: str  # "critical", "high", "medium", "low"
    description: str
    matched_text: str

class PromptInjectionDetector:
    MAX_QUERY_LENGTH = 5000
    MAX_REPETITION_RATIO = 0.85

    def detect(self, query: str) -> Tuple[bool, List[PromptInjection]]:
        """Detect prompt injection attempts. Returns (is_malicious, injections)."""

    def sanitize(self, query: str) -> str:
        """Sanitize a query by replacing detected patterns with [REDACTED]."""

def check_query_safety(query: str) -> Tuple[bool, str, List[PromptInjection]]:
    """Check if a query is safe to send to AI. Returns (is_safe, rejection_reason, injections)."""

def validate_and_sanitize_query(query: str) -> Tuple[bool, str, Optional[str]]:
    """Validate a query and return safe version or rejection message."""
```

**Security-relevant calling context:**
- Binary safe/unsafe decision -- no numeric scoring for borderline cases
- Pattern categories: CRITICAL_PATTERNS, HIGH_PATTERNS, MEDIUM_PATTERNS, LOW_PATTERNS, BMS_PATTERNS
- Normalizes query by stripping non-alphanumeric chars before pattern matching
- Called from `chat.py` (line 294) and `schema_validator.py` (line 126) for tool argument scanning
- Any detection (even "low" severity) blocks the entire query

---

## 5. `backend/app/mcp/schema_validator.py`

**MCP tool input/output validation and secret-zero output filter.**

```python
def validate_tool_input(
    tool_name: str,
    arguments: dict,
    schema: dict,
) -> tuple[bool, Optional[str]]:
    """Validate args against JSON schema + size limits."""

def scan_arguments_for_injection(
    tool_name: str,
    arguments: dict,
) -> tuple[bool, Optional[str]]:
    """Scan string arguments for prompt injection patterns."""

def validate_tool_output(
    tool_name: str,
    output: Any,
    max_bytes: int = MAX_OUTPUT_SIZE_BYTES,
) -> tuple[Any, bool]:
    """Truncate oversized output. Returns (output, was_truncated)."""

def scan_output_for_secrets(tool_name: str, output: Any) -> Any:
    """Scan tool output for credential-like fields and redact them."""
```

**Security-relevant calling context:**
- `_SECRET_OUTPUT_KEYS`: 16 key names checked (api_key, token, password, jwt, etc.)
- `_SECRET_VALUE_PATTERNS`: 3 regex patterns for API keys, Bearer tokens, JWTs
- `MAX_STRING_LENGTH = 10_000`, `MAX_ARRAY_ITEMS = 1_000`, `MAX_OUTPUT_SIZE_BYTES = 500_000`
- `scan_output_for_secrets()` only checks dict outputs -- string/list outputs pass through unscanned
- Secret redaction replaces values with `***REDACTED_BY_SECRET_ZERO_FILTER***`

---

## 6. `backend/app/middleware/auth_middleware.py`

**Authentication and authorization for FastAPI endpoints.**

```python
def require_auth(level: AuthLevel = AuthLevel.AUTHENTICATED):
    """FastAPI dependency that requires authentication at a specific level."""
    # Returns async dependency function
    # In DEMO_MODE: creates demo AuthContext (ADMIN role for humans, BOT_AGENT for bots)
    # In production: validates JWT or API key, checks role hierarchy

def require_role(*roles: SentinelRole):
    """FastAPI dependency that requires specific roles."""

def require_module(*required_modules: ModuleType):
    """FastAPI dependency that requires specific modules to be active."""

def get_current_auth(request: Request) -> Optional[AuthContext]:
    """Get current auth context from request state (non-throwing)."""

def create_jwt_token(
    user_id: str, email: str, role: str, full_name: str,
    token_type: str = "access",
) -> str:
    """Create a JWT token (access or refresh)."""

def validate_jwt_token(
    token: str, required_token_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Validate a JWT token and return payload."""
```

**Security-relevant calling context:**
- DEMO_MODE bypasses auth for localhost + configured origins, grants ADMIN role
- Production DEMO_MODE is blocked with 503 (line 643-647)
- API key validation: SHA-256 hash lookup in Supabase `api_keys` table with 5-min cache
- JWT uses HS256, secret from `jwt_secret_key` or `supabase_key` or hardcoded fallback
- Blacklist checking via `token_blacklist_service` (graceful degradation if Redis unavailable)
- Bot agents detected via `X-Agent-Type: bot` header or `sent_bot_` key prefix

---

## 7. `backend/app/middleware/pii_guard.py`

**PII detection and redaction for POPIA/GDPR compliance.**

```python
class PIIGuard:
    def redact(
        self, text: str, preserve_types: Optional[List[str]] = None,
    ) -> RedactionResult:
        """Redact PII from text with reversible mapping."""

    def restore(self, redacted_text: str, redaction_map: Dict[str, str]) -> str:
        """Restore original PII values from redacted text."""

    def scan_for_pii(self, text: str) -> Dict[str, Any]:
        """Scan text for PII without redacting."""

def redact_request_pii(request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Redact PII from request data before LLM processing."""

def restore_response_pii(response_data: Dict[str, Any], redaction_map: Dict[str, str]) -> Dict[str, Any]:
    """Restore PII in response data after LLM processing."""

def validate_pii_compliance(text: str, raise_on_pii: bool = False) -> bool:
    """Check if text is PII-compliant (no sensitive data)."""
```

**Security-relevant calling context:**
- NOT registered as middleware -- utility service, never imported by chat pipeline
- Detects: SA ID numbers (Luhn validated), phone (+27 format), email, credit cards,
  Anthropic API keys, SENTINEL API keys, JWT tokens, SSH private keys
- Reversible redaction via placeholder mapping (`[SA_ID_abc12345]`)
- `pii_guard` singleton instance available for import
- Dead code risk: never called in the chat flow despite being security-critical

---

## 8. `backend/app/api/rag.py`

**RAG API endpoints for documentation search.**

```python
@router.post("/query")
async def query_rag(request: QueryRequest):
    """Query the RAG system with natural language."""

@router.get("/search")
async def search_documents(query: str, ...):
    """Search documents by semantic similarity."""

@router.get("/search/knowledge")
async def search_knowledge(query: str, ...):
    """Search equipment knowledge base."""

@router.get("/search/hybrid")
async def hybrid_search(query: str, ...):
    """Hybrid search combining keyword and semantic matching."""

@router.post("/documents")
async def add_document(request: DocumentRequest):
    """Add a new document to the RAG system."""

@router.post("/knowledge")
async def add_knowledge(request: KnowledgeRequest):
    """Add a new knowledge entry to the RAG system."""
```

**Security-relevant calling context:**
- NO authentication on any endpoint (no `Depends(require_auth(...))`)
- POST `/documents` and POST `/knowledge` allow unauthenticated writes to the RAG index
- `query` parameter flows directly into vector search without prompt injection scanning
- POST `/documents/{id}/reindex` allows unauthenticated re-indexing
- All endpoints accessible in production without credentials

---

## 9. `backend/app/api/documents.py`

**Document upload handler for RAG indexing.**

```python
@router.post("/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    building_id: str = Form(...),
    title: Optional[str] = Form(None),
    document_type: str = Form("building_manual"),
) -> dict:
    """Upload a building-scoped document for RAG indexing."""
```

**Security-relevant calling context:**
- Rate limited to 10/minute but NO authentication required
- File type validated against `settings.allowed_document_types` (extension check only, no magic byte verification)
- No file size limit enforced before reading (relies on framework defaults)
- `building_id` is user-provided and used in storage path without sanitization
- `title` is user-provided and stored directly in database
- Extracted text stored as `full_text` in Supabase without PII scanning
- TODO comment acknowledges missing user access check (line 86)
