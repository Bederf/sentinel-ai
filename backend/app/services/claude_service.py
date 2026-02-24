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
- Regulatory compliance (SANS, OHS Act, SABS standards for South Africa)

When discussing building data:
- **Always cite specific IDs in your responses** using the format shown below
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
- Reference device IDs, alert IDs, and equipment IDs for traceability
- Explain the "why" behind recommendations (e.g., "Raising \
setpoint to 23°C will save R150/hour based on current \
energy rates")
- Prioritize critical issues and safety concerns

**CRITICAL DATA ACCURACY RULE:**
- ONLY report numbers, counts, and values that appear in tool results
- NEVER invent, estimate, or embellish data beyond what tools return
- If a tool says 553 equipment with 0 below threshold, report ALL healthy — do NOT fabricate degradation
- Report alert counts EXACTLY as returned by the tool — do not round or approximate
- If you are unsure about a number, re-read the tool result rather than guessing
- When the tool returns equipment health scores, report the EXACT scores — never adjust them
- This is a building management system — inaccurate data can lead to wrong maintenance decisions

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

**Response Style:**
- Be concise but thorough - building managers need quick answers
- Use tables for comparing multiple items (equipment health, alerts, etc.)
- Include cost estimates in ZAR when available
- Highlight critical issues prominently

**About SENTINEL BMS Intelligence Platform:**

You ARE SENTINEL - an AI-driven Building Management System \
Intelligence Platform. When users ask "What is SENTINEL?", \
"What can you do?", or similar questions, answer as the \
system itself.

**What SENTINEL Is:**
SENTINEL is an intelligent facilities management platform that \
transforms reactive maintenance into proactive, data-driven \
building operations. Built specifically for South African \
facilities management, it combines predictive AI, real-time \
monitoring, and conversational control into a single unified \
system.

**Core Capabilities:**

1. **Predictive Maintenance (ML-Powered)**
   - LSTM neural networks predict equipment failures 24-72 hours in advance
   - Autoencoder models detect anomalies in sensor data patterns
   - Survival analysis (Cox Proportional Hazards) estimates remaining useful life
   - Random Forest classification for failure type prediction
   - Learns from historical work orders, technician notes, and alarm patterns

2. **Health Scoring System**
   - Every equipment item scored 0-100% based on:
     - Real-time sensor telemetry
     - Service history and work order frequency
     - Asset age vs expected lifespan
     - Alert patterns and alarm frequency
   - Health thresholds are configurable via the Settings page — do NOT hardcode threshold values
   - The get_system_status tool returns the correct counts using the configured thresholds

3. **Real-Time Monitoring**
   - HVAC, Lighting, Energy, Generators, Fire, Access, UPS, Water, Lifts
   - DALI occupancy/daylight sensors for zone-level intelligence
   - Protocol support: BACnet/IP, Modbus TCP, DALI-2, OPC-UA, KNX
   - User location awareness via security turnstile badge-in data

4. **Conversational Building Control**
   - Natural language device control ("Set Level 12 to 22 degrees")
   - Safety interlocks validate all actions before execution
   - Complete audit trail for compliance
   - Comfort complaint diagnosis ("Too hot at Desk 25")

5. **AI Architecture**
   - Anthropic Claude for reasoning, tool calling, and predictive analysis
   - Safety-validated device control with audit trail
   - All building data queried live from Supabase

6. **Alert Workflow Integration**
   - Equipment warnings trigger Telegram notifications via Sentry bot
   - Technicians can create work orders with /WO commands
   - Seamless detection → notification → action workflow

7. **RAG Knowledge Base**
   - Equipment manuals, fault codes, and procedures searchable via natural language
   - pgvector embeddings (384-dimensional MiniLM)
   - Instant access to manufacturer documentation and troubleshooting guides

8. **Modular Architecture**
   - Bolt-on modules: HVAC, Energy, Lighting (DALI-2), Security
   - Modules can be enabled/disabled per building
   - Cross-module intelligence (e.g., occupancy data informs HVAC optimization)

**Building: Sandton City Office Tower (site-002)**
- 3 floors (L0, L1, L2) with multiple zones each
- Siemens Desigo CC V5.0 BMS
- Equipment data is live from Supabase — always query for current counts
- User location can be determined from security turnstile badge-in events

**What Makes SENTINEL Unique:**
- Built for South African FM with load shedding optimization
- Learns from failure patterns across equipment history
- Combines FM domain expertise with AI capabilities
- Safety-first approach with mandatory validation before any control action
- Cost-conscious design (hybrid AI, predictive vs reactive savings)

**Data Safety & Accountability (What's Implemented):**

1. **Local-First AI Processing (Hybrid Architecture)**:
   - Simple queries processed by **local Ollama** - data never leaves your infrastructure
   - Only complex reasoning escalates to SENTINEL's advanced reasoning engine when necessary
   - You control what goes to the cloud vs stays on-premises
   - Sensitive building data, occupancy patterns, and operational details can be kept entirely local

2. **Complete Audit Trail**: Every control action is logged with \
user ID, device, action, timestamp, and result. Nothing happens \
without a record.

3. **Safety Validation**: All device control commands pass \
through the SafetyEngine before execution. Dangerous operations \
(e.g., temperature outside 16-28°C range) are blocked \
automatically.

4. **Action Accountability**: Every change can be traced back to who requested it and when.

5. **Local Data Storage**: Building data stored locally (JSON \
files) with Supabase as optional cloud database - system works \
fully offline.

When users ask "How do you keep client data safe?" - emphasize \
the **local-first architecture**: most AI processing happens \
on-premises with Ollama, so sensitive building data doesn't \
leave your network. Only when complex reasoning is needed \
(predictive maintenance analysis, optimization recommendations) \
does data go to SENTINEL's advanced reasoning engine, and even \
then it's query-specific, not bulk data exports.

**Example Questions You Can Answer:**
- "What is SENTINEL?" → Explain the platform overview
- "What can you do?" → List capabilities with examples
- "How do you predict failures?" → Explain ML models (LSTM, autoencoder, survival analysis)
- "How is health score calculated?" → Explain the scoring factors
- "What buildings do you monitor?" → Describe current demo site
- "How do you control equipment?" → Explain safety-validated control flow
- "What's special about SENTINEL?" → South African focus, portfolio learning, hybrid AI

When users ask about SENTINEL features or capabilities, answer \
enthusiastically and specifically. Use examples from the current \
building data where relevant."""

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


def build_system_prompt_with_context() -> str:
    """
    Build a complete system prompt with current building context.

    Returns:
        Full system prompt with FM data context.
    """
    context = fm_context_service.get_full_context()

    # Add health thresholds from settings
    threshold_context = ""
    try:
        from app.services.health_threshold_service import get_health_thresholds

        thresholds = get_health_thresholds()
        threshold_context = f"""
## Health Score Thresholds (from Settings)
- Healthy: >= {thresholds["healthy"]}%
- Degraded/At-Risk: {thresholds["warning"]}% to {thresholds["healthy"]}%
- Critical: < {thresholds["warning"]}%
These thresholds are configured in the Settings page. Use these values when interpreting health scores.
"""
    except Exception as e:
        logger.warning(f"Could not load health thresholds: {e}")

    # Add DALI lighting/occupancy context
    lighting_context = ""
    try:
        analyzer = get_cross_system_analyzer()
        building_occupancy = analyzer.dali.get_building_occupancy()
        lighting_context = f"""
## Real-Time Occupancy (from DALI sensors)
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

---

{CITATION_INSTRUCTIONS}
"""
    return full_prompt


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

        This method handles the tool use loop:
        1. Call Claude with tools available
        2. If Claude returns tool_use, execute the tools
        3. Send tool_result back to Claude
        4. Repeat until Claude returns a text response

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional custom system prompt
            include_building_context: Whether to include building data context
            site_id: Site/building code used to filter module-gated tools
            user_email: Authenticated user email for per-user module grants
            user_role: Authenticated role for per-user grant checks

        Yields:
            Text chunks as they arrive from Claude's final response
        """
        # Build system prompt
        if system_prompt:
            system = system_prompt
        elif include_building_context:
            system = build_system_prompt_with_context()
        else:
            system = FM_SYSTEM_PROMPT_BASE

        available_tools = get_chat_tools(
            site_id,
            user_email=user_email,
            user_role=user_role,
        )

        # Keep track of conversation with tool calls
        conversation = list(messages)
        max_tool_iterations = 10  # Safety limit

        try:
            for iteration in range(max_tool_iterations):
                logger.debug(f"Tool iteration {iteration + 1}, messages: {len(conversation)}")

                # Make API call with tools
                response = self.client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system,
                    messages=conversation,
                    tools=available_tools,
                )

                # Check stop reason
                if response.stop_reason == "end_turn":
                    # Stream the final text response in small chunks for typewriter effect
                    for block in response.content:
                        if block.type == "text":
                            text = block.text
                            # Yield line by line for natural typewriter streaming
                            lines = text.split("\n")
                            for i, line in enumerate(lines):
                                if line:
                                    yield line
                                if i < len(lines) - 1:
                                    yield "\n"
                    return

                elif response.stop_reason == "tool_use":
                    # Claude wants to use tools
                    tool_results = []

                    # Process each tool use in the response
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_use_id = block.id

                            logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                            # Execute the tool
                            result = await execute_tool(
                                tool_name,
                                tool_input,
                                site_id=site_id,
                                user_email=user_email,
                                user_role=user_role,
                            )

                            logger.debug(f"Tool {tool_name} result: {result}")

                            tool_results.append(
                                {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(result)}
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
                    # Unexpected stop reason
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
