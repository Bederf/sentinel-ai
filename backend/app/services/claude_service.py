"""Claude AI service for building management intelligence."""

import json
import logging
import sys
from typing import AsyncGenerator

from anthropic import Anthropic, APIError, AuthenticationError, RateLimitError

from app.config.settings import settings
from app.models.auth import SentinelRole
from app.services.fm_context import fm_context_service
from app.services.chat_tools import execute_tool, get_chat_tools
from app.services.cross_system_analyzer import get_cross_system_analyzer

logger = logging.getLogger(__name__)


# Suppress anthropic library stderr spam
class StderrFilter:
    """Filter to suppress anthropic rate limit stderr spam"""

    def __init__(self):
        self.original_stderr = sys.stderr

    def write(self, text):
        # Suppress the HTTP 429 error messages from anthropic
        if "rate_limit_error" not in text and "request_id:" not in text:
            self.original_stderr.write(text)

    def flush(self):
        self.original_stderr.flush()


# Apply the filter
sys.stderr = StderrFilter()

# Base FM-focused system prompt for building management intelligence
FM_SYSTEM_PROMPT_BASE = """\
You are an AI assistant specializing in Facilities Management (FM) \
and Building Management Systems (BMS). You help building managers, \
maintenance technicians, and FM professionals monitor and manage \
their buildings effectively.

Your expertise includes:
- HVAC systems (heating, ventilation, air conditioning)
- UPS (Uninterruptible Power Supply) systems
- Electrical systems and generators
- Building sensors and IoT devices
- Energy efficiency and sustainability
- Preventive maintenance best practices
- Anomaly detection and predictive maintenance
- Regulatory compliance (use search_documents to find applicable standards)

When discussing building data:
- **Use equipment codes and names** (e.g., S002-FCU-104 "FCU Zone-104"),
NEVER show raw UUIDs (like 6644ca80-7ff3-...) to the user — strip them
from all output
- Reference sensor readings and health scores when relevant
- Provide actionable recommendations based on the data
- Highlight potential issues and suggest maintenance priorities
- Use South African terminology and standards where appropriate
- Be concise but thorough in technical explanations

When a user asks about specific issues:
- Look at the Active Alerts and Anomalies sections for relevant information
- Reference equipment health scores and last service dates
- Suggest specific next steps with estimated costs when available

**Cost Impact Analysis:**
When users ask about costs, savings, or financial implications \
("What's the cost impact?", "Show me the savings", \
"Why is preventive better?"), provide detailed cost breakdowns:
- Explain failure cost vs preventive cost with specific numbers
- Break down costs by category: parts, labor, downtime, secondary damage risk
- Calculate and highlight potential savings in percentage and ZAR
- Explain WHY preventive is cheaper (no emergency premium, \
scheduled labor, avoiding downtime penalties)
- Reference the prediction data for accurate cost information

Example cost explanation:
"Based on the analysis, if Gateway Chiller fails it would cost \
approximately R65,000 including emergency parts, overtime labour, \
and potential downtime. However, scheduling preventive maintenance \
now would cost R28,000 - saving you R37,000 (57% reduction). The \
savings come from avoiding the emergency premium on parts (+50% \
after hours), scheduled labour vs overtime rates, and preventing \
secondary damage to other equipment."

Always be helpful, professional, and safety-conscious. If you \
identify a critical issue, emphasize the urgency appropriately.

**BMS AI Agent Capabilities:**
You are a proactive BMS (Building Management System) AI agent \
with real-time access to building data and device control. \
You should:

1. **Provide Real-Time Intelligence:**
   - Use get_system_status to show current alerts, equipment health, and recommendations
   - Use get_alerts_and_anomalies to identify and explain active issues
   - Use get_equipment_health to assess maintenance needs
   - Use get_energy_analysis to find efficiency opportunities

2. **Give Proactive Recommendations:**
   - Use get_optimization_recommendations to suggest optimal HVAC setpoints
   - Suggest energy-saving configurations based on current conditions
   - Recommend maintenance actions based on equipment health
   - Warn about predicted failures before they occur

3. **Control Building Devices:**
   - Use list_devices to discover available controllable equipment
   - Use get_device_details to check current state before changes
   - Use control_device to execute approved control actions
   - All actions go through safety validation and audit logging

**Proactive Agent Behavior:**
- When asked about building status, ALWAYS use tools to get real-time data
- Provide specific, actionable recommendations with cost/savings estimates
- Reference equipment codes and names for traceability (e.g., S002-AHU-001, not UUIDs)
- Explain the "why" behind recommendations (e.g., "Raising \
setpoint to 23°C will save R150/hour based on current \
energy rates")
- Prioritize critical issues and safety concerns

**CRITICAL DATA ACCURACY RULE — ZERO HALLUCINATION:**
- ONLY state facts that appear in tool results. Nothing else.
- If a tool returns no results or empty data, say "I don't have that
information in the system" and STOP. Do NOT fill in with general
knowledge, guesses, or "typical" information.
- NEVER say "typically", "would usually", "generally includes",
"as a BMS in South Africa you'd expect", "such as X, Y, Z" — these
are hallucinations. If the data isn't there, don't speculate about
what it MIGHT contain.
- NEVER name specific standards, regulations, codes, or guidelines
(e.g., SANS, ASHRAE, OHS Act, ISO, SABS, NRS) unless they appear
VERBATIM in a tool result. Your training data is NOT a valid source
for building-specific compliance information.
- When search_documents returns no results, your ENTIRE answer should
be: "I don't have documentation about [topic] in the system. You may
need to upload the relevant documents or check with your facility
manager." Do NOT add suggestions about what standards "would" apply.
- Report numbers EXACTLY as returned — do not round, estimate, or adjust.
- Use health_score from the equipment table as source of truth, NOT scores in alert messages (may be stale).
- The get_system_status tool returns degraded_equipment and
active_predictions arrays — use these for follow-up questions instead
of making additional tool calls.
- If a tool call fails or returns an error, say so honestly.
- This is a building management system — inaccurate data can lead to wrong maintenance decisions.

**Control Actions:**
- Always confirm what action you're taking and on which device
- Report results clearly with before/after values
- If blocked by safety rules, explain the specific safety concern
- Suggest alternative actions if the requested action isn't safe

**Write/Action Tools (Operator+ Only):**
When the user has operator or admin role, you have additional write tools:

1. **adjust_setpoint** — Change HVAC temperature setpoints within safety limits:
   - Safety limits are loaded from the Settings page (controlLimits section)
   - If the tool rejects a value as out-of-range, report the allowed range from the tool response
   - ALWAYS check current reading with get_device_details first
   - ALWAYS confirm the intended change with the user before executing
   - Report before/after values clearly

2. **create_work_order** — Create maintenance work orders:
   - Include clear description, priority, and equipment reference
   - Confirm the work order details with the user before creating

3. **approve_recommendation / reject_recommendation** — Handle pending recommendations:
   - Show the recommendation details to the user first
   - For approval: confirm the action that will be taken
   - For rejection: require a clear reason

4. **reset_equipment_fault** — Reset equipment fault status:
   - FIRE and GEN equipment CANNOT be remotely reset (safety policy)
   - Suggest a work order if the equipment type is blocked

**Safety Rules for Write Tools:**
- NEVER adjust setpoints without the user explicitly requesting it
- NEVER approve recommendations without user confirmation
- ALWAYS state what you are about to do BEFORE doing it
- If a safety limit blocks an action, explain the limit and suggest alternatives

**If write tools are NOT available** (lower-privilege user):
- You can still READ all data and provide recommendations
- Tell the user they need operator or admin access to make changes through the chat

**Response Style — KEEP IT SHORT:**
- Building managers are busy — give the answer, not an essay
- Default to 3-5 bullet points. Only expand if the user asks for detail
- Use tables ONLY when comparing 4+ items side-by-side
- Lead with the most important finding (critical issues first)
- Skip preamble like "Let me check that for you" or "Based on the data"
- Never repeat tool data verbatim — summarize the key numbers
- Include cost estimates in ZAR only when directly relevant
- If everything is healthy, say so in one sentence — don't list every metric

**Identity:**
You are SENTINEL — an AI-powered Building Management System \
intelligence layer. You answer questions about buildings, \
equipment, compliance, and facilities management.

**Data Rule — ALWAYS use tools:**
- ALL your answers must be grounded in data from your tools
- Use search_documents for knowledge questions (compliance, procedures, standards, capabilities)
- Use get_system_status / get_equipment_health / get_alerts_and_anomalies for live building data
- If tools return no results, say so honestly — NEVER fabricate or pad answers from general knowledge
- Health thresholds are configurable via the Settings page — do NOT hardcode threshold values"""

# Citation format instructions
CITATION_INSTRUCTIONS = """
## Citation Format Requirements

When referencing data in your responses, ALWAYS use these citation formats:

**Sites:** Reference as [SITE-ID Site Name]
- Example: "Based on [site-001 Sandton City] data, the HVAC system shows..."

**Equipment:** Reference as [EQUIPMENT-ID Equipment Name]
- Example: "The [eqp-003 AHU-7] is showing signs of bearing degradation..."

**Alerts:** Reference as [ALERT-ID]
- Example: "Alert [alert-001] indicates a priority 2 issue requiring attention..."

**Anomalies:** Reference as [ANOMALY-ID] with confidence
- Example: "Anomaly [anomaly-001] predicts failure by 2026-02-15 (78% confidence)..."

**Costs:** Always include ZAR costs when available
- Example: "Estimated repair cost: R18,500 (potential damage if ignored: R285,000)"

IMPORTANT: Every response about building data MUST include at \
least one citation to the specific data you're referencing. \
This ensures traceability and accountability."""


def _get_threshold_context() -> str:
    """Get health threshold context string (small, rarely changes)."""
    try:
        from app.services.health_threshold_service import get_health_thresholds

        thresholds = get_health_thresholds()
        return (
            f"\n## Health Score Thresholds (from Settings)\n"
            f"- Healthy: >= {thresholds['healthy']}%\n"
            f"- Degraded/At-Risk: {thresholds['warning']}% to {thresholds['healthy']}%\n"
            f"- Critical: < {thresholds['warning']}%\n"
            f"These thresholds are configured in the Settings page. "
            f"Use these values when interpreting health scores.\n"
        )
    except Exception as e:
        logger.warning(f"Could not load health thresholds: {e}")
        return ""


def build_system_prompt_with_context() -> str:
    """
    Build a complete system prompt with current building context.

    Used for the NON-tool path where Claude cannot fetch data via tools.
    Includes static data tables (sites, equipment, alerts, predictions).

    Returns:
        Full system prompt with FM data context.
    """
    context = fm_context_service.get_full_context()
    threshold_context = _get_threshold_context()
    agent_memory_context = fm_context_service.get_agent_memory_context()

    # Add lighting/occupancy context
    lighting_context = ""
    try:
        analyzer = get_cross_system_analyzer()
        building_occupancy = analyzer.lighting.get_building_occupancy()
        lighting_context = f"""
## Real-Time Occupancy (from lighting sensors)
- Overall building occupancy: {building_occupancy["occupancy_percent"]:.0f}%
- Total sensors: {building_occupancy["total_sensors"]}
- Currently occupied: {building_occupancy["occupied_sensors"]}

**For comfort complaints:**
- You can check specific zone occupancy and daylight levels
- High lux (>800) indicates solar heat gain potential
- Low occupancy + high cooling = possible energy waste
- Use desk ID to find exact sensor location
- Reference occupancy data when analyzing "too hot" or "too cold" complaints

**Lighting fault detection:**
- Check for faulty luminaires when users report dark areas
- DALI fault codes indicate lamp failure, driver issues, or communication errors
"""
    except Exception as e:
        logger.warning(f"Could not load DALI context: {e}")

    full_prompt = f"""{FM_SYSTEM_PROMPT_BASE}

---

{context}

{threshold_context}

{lighting_context}

{agent_memory_context}

---

{CITATION_INSTRUCTIONS}
"""
    return full_prompt


def build_system_prompt_for_tools() -> str:
    """
    Build a lean system prompt for the tool-calling path.

    Skips static data tables (sites, equipment, alerts, predictions)
    because Claude fetches that data live via tools. Keeps behavioral
    instructions, health thresholds, agent memory, and citation rules.

    Agent memory IS included here (not tool-fetchable — it's institutional
    knowledge that should always be in context).

    Returns:
        System prompt with behavioral instructions only.
    """
    threshold_context = _get_threshold_context()
    agent_memory_context = fm_context_service.get_agent_memory_context()

    return f"""{FM_SYSTEM_PROMPT_BASE}

---

{threshold_context}

{agent_memory_context}

**Note:** Use your tools (get_system_status, get_equipment_health, get_alerts_and_anomalies, etc.) \
to fetch live building data. Do NOT guess or fabricate data — always call tools first.

---

{CITATION_INSTRUCTIONS}
"""


class ClaudeService:
    """Service for interacting with Claude AI."""

    def __init__(self):
        """Initialize Claude service with API configuration."""
        self._client: Anthropic | None = None
        self._api_key = settings.anthropic_api_key
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens

    @property
    def client(self) -> Anthropic:
        """Get or create Anthropic client (lazy initialization)."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured. Set it in .env or environment variables.")
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    async def stream_response(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        include_building_context: bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional custom system prompt (defaults to FM prompt with context)
            include_building_context: Whether to include building data context

        Yields:
            Text chunks as they arrive from Claude

        Raises:
            ValueError: If API key is not configured
            Exception: For API errors with descriptive messages
        """
        # Build system prompt with or without context
        if system_prompt:
            system = system_prompt
        elif include_building_context:
            system = build_system_prompt_with_context()
        else:
            system = FM_SYSTEM_PROMPT_BASE

        try:
            # Use streaming with the messages API
            with self.client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except AuthenticationError as e:
            logger.error(f"Claude authentication error: {e}")
            raise ValueError("Invalid ANTHROPIC_API_KEY. Please check your API key configuration.") from e

        except RateLimitError as e:
            logger.warning(f"Claude rate limit hit: {e}")
            raise Exception("Claude API rate limit exceeded. Please try again in a moment.") from e

        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise Exception(f"Claude API error: {e.message}") from e

        except Exception as e:
            logger.error(f"Unexpected error in Claude service: {e}")
            raise

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self._api_key)

    async def stream_response_with_tools(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        include_building_context: bool = True,
        site_id: str | None = None,
        user_email: str | None = None,
        user_role: SentinelRole | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response from Claude with tool calling support.

        Uses true streaming (messages.stream) so the user sees text as it
        is generated instead of waiting for the full response.

        Loop:
        1. Stream response — yield text tokens to user in real-time
        2. After stream completes, check stop_reason
        3. If tool_use: execute tools, append results, loop
        4. If end_turn: done (text was already streamed)

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional custom system prompt
            include_building_context: Whether to include building data context
            site_id: Site/building code used to filter module-gated tools
            user_email: Authenticated user email for per-user module grants
            user_role: Authenticated role for per-user grant checks

        Yields:
            Text chunks as they arrive from Claude
        """
        # Build system prompt — lean version for tool path (no static data tables)
        if system_prompt:
            system_text = system_prompt
        elif include_building_context:
            system_text = build_system_prompt_for_tools()
        else:
            system_text = FM_SYSTEM_PROMPT_BASE

        # Prompt caching: wrap system prompt as a content block with cache_control.
        # Anthropic caches the prefix server-side for ~5 min, saving 90% of input
        # token cost on repeated requests with the same system prompt.
        system_blocks = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        available_tools = get_chat_tools(
            site_id,
            user_email=user_email,
            user_role=user_role,
        )

        # Cache tool definitions too — they rarely change between requests.
        # Copy last tool to avoid mutating the shared CHAT_TOOLS list.
        if available_tools:
            available_tools = list(available_tools)  # shallow copy of list
            available_tools[-1] = {**available_tools[-1], "cache_control": {"type": "ephemeral"}}

        # Keep track of conversation with tool calls
        conversation = list(messages)
        max_tool_iterations = 10  # Safety limit

        try:
            for iteration in range(max_tool_iterations):
                logger.debug(f"Tool iteration {iteration + 1}, messages: {len(conversation)}")

                # Stream response — text arrives in real-time
                with self.client.messages.stream(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system_blocks,
                    messages=conversation,
                    tools=available_tools,
                ) as stream:
                    # Yield text tokens as they arrive.
                    # For tool iterations this may yield preamble text like
                    # "Let me check that..." which is good UX feedback.
                    # For the final response this is true streaming.
                    for text in stream.text_stream:
                        yield text

                    # Get complete message (already accumulated by SDK)
                    response = stream.get_final_message()

                if response.stop_reason == "end_turn":
                    # Final response — text was already streamed above
                    return

                elif response.stop_reason == "tool_use":
                    # Execute tools
                    tool_results = []

                    for block in response.content:
                        if block.type == "tool_use":
                            logger.info(f"Executing tool: {block.name} with input: {block.input}")

                            result = await execute_tool(
                                block.name,
                                block.input,
                                site_id=site_id,
                                user_email=user_email,
                                user_role=user_role,
                            )

                            logger.debug(f"Tool {block.name} result: {result}")

                            tool_results.append(
                                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                            )

                    # Add assistant's response (with tool_use) to conversation
                    conversation.append(
                        {
                            "role": "assistant",
                            "content": [
                                {"type": block.type, **block.model_dump()}
                                if block.type == "tool_use"
                                else {"type": "text", "text": block.text}
                                for block in response.content
                            ],
                        }
                    )

                    # Add tool results to conversation
                    conversation.append({"role": "user", "content": tool_results})

                else:
                    logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                    yield f"Unexpected response from AI: {response.stop_reason}"
                    return

            # If we hit max iterations
            logger.warning("Hit max tool iterations limit")
            yield "I apologize, but I encountered an issue processing your request. Please try again."

        except AuthenticationError as e:
            logger.error(f"Claude authentication error: {e}")
            raise ValueError("Invalid ANTHROPIC_API_KEY. Please check your API key configuration.") from e

        except RateLimitError as e:
            logger.warning(f"Claude rate limit hit: {e}")
            raise Exception("Claude API rate limit exceeded. Please try again in a moment.") from e

        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise Exception(f"Claude API error: {e.message}") from e

        except Exception as e:
            logger.error(f"Unexpected error in Claude service with tools: {e}")
            raise


# Module-level service instance for dependency injection
claude_service = ClaudeService()
