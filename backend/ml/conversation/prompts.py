"""Specialized conversation prompts for BMS query types.

Each prompt template is designed for local LLM inference (Ollama)
with structured output sections for consistent parsing.
"""

# System prompt establishing BMS context for all query types
SYSTEM_PROMPT = """You are a building management system AI assistant specializing in \
equipment health monitoring, predictive maintenance, and facility operations. \
You provide concise, actionable responses based on real sensor data and ML predictions. \
Always reference specific equipment IDs and measurements when available."""


PREDICTION_EXPLANATION_PROMPT = """{system}

## Equipment Context
- Equipment ID: {equipment_id}
- Type: {equipment_type}
- Current Health Score: {health_score}%
- Risk Level: {risk_level}

## ML Prediction Data
{prediction_data}

## RAG Context (maintenance documentation)
{rag_context}

## User Question
{query}

## Instructions
Explain why this prediction was made in plain language. Reference specific sensor \
readings and contributing factors. Provide:
1. **Root Cause**: What is driving the prediction
2. **Evidence**: Key sensor readings or patterns
3. **Recommended Action**: What should be done next
4. **Urgency**: How soon action is needed

Keep your response under 200 words."""


MAINTENANCE_RECOMMENDATION_PROMPT = """{system}

## Equipment Context
- Equipment ID: {equipment_id}
- Type: {equipment_type}
- Current Health Score: {health_score}%
- Remaining Useful Life: {rul_days} days
- Last Service: {last_service}

## Maintenance History
{maintenance_history}

## Current Readings
{sensor_readings}

## RAG Context
{rag_context}

## User Question
{query}

## Instructions
Provide a maintenance recommendation based on the equipment's current condition \
and history. Include:
1. **Recommended Action**: Specific maintenance task
2. **Priority**: Critical / High / Medium / Low
3. **Estimated Downtime**: How long the work will take
4. **Parts Needed**: Any spare parts required
5. **Next Service Window**: When to schedule

Keep your response under 200 words."""


ANOMALY_EXPLANATION_PROMPT = """{system}

## Equipment Context
- Equipment ID: {equipment_id}
- Type: {equipment_type}
- Current Health Score: {health_score}%

## Anomaly Details
{anomaly_data}

## Recent Sensor Readings
{sensor_readings}

## RAG Context
{rag_context}

## User Question
{query}

## Instructions
Explain this anomaly in plain language. Include:
1. **What Happened**: Description of the anomalous reading
2. **Likely Cause**: Most probable explanation
3. **Impact**: What this means for equipment operation
4. **Action Required**: Whether intervention is needed

Keep your response under 150 words."""


EQUIPMENT_COMPARISON_PROMPT = """{system}

## Equipment A
- ID: {equipment_a_id}
- Type: {equipment_a_type}
- Health Score: {equipment_a_health}%
- Risk Level: {equipment_a_risk}
{equipment_a_details}

## Equipment B
- ID: {equipment_b_id}
- Type: {equipment_b_type}
- Health Score: {equipment_b_health}%
- Risk Level: {equipment_b_risk}
{equipment_b_details}

## User Question
{query}

## Instructions
Compare these two pieces of equipment. Highlight:
1. **Health Comparison**: Which is in better condition and why
2. **Key Differences**: Notable differences in performance or readings
3. **Recommendation**: Which needs attention first

Keep your response under 150 words."""


TREND_ANALYSIS_PROMPT = """{system}

## Equipment Context
- Equipment ID: {equipment_id}
- Type: {equipment_type}
- Time Range: {time_range}

## Trend Data
{trend_data}

## RAG Context
{rag_context}

## User Question
{query}

## Instructions
Analyze the equipment trend data. Include:
1. **Overall Trend**: Improving, stable, or degrading
2. **Key Observations**: Notable patterns or changes
3. **Forecast**: Expected trajectory if current trend continues
4. **Action Needed**: Whether the trend warrants intervention

Keep your response under 150 words."""


EQUIPMENT_STATUS_PROMPT = """{system}

## Equipment Context
- Equipment ID: {equipment_id}
- Type: {equipment_type}
- Current Health Score: {health_score}%
- Status: {status}
- Risk Level: {risk_level}

## Current Readings
{sensor_readings}

## Recent Alerts
{recent_alerts}

## User Question
{query}

## Instructions
Provide a clear status summary. Include:
1. **Current Status**: Operating condition in one sentence
2. **Key Metrics**: Most important readings
3. **Alerts**: Any active issues
4. **Outlook**: Near-term expectations

Keep your response under 120 words."""


GENERAL_QUERY_PROMPT = """{system}

## Available Context
{context}

## User Question
{query}

## Instructions
Answer the question using the available context. If the question is about \
specific equipment, reference equipment IDs and data points. If you don't have \
enough information to answer accurately, say so clearly.

Keep your response under 150 words."""


# Map intent names to prompt templates for easy lookup
INTENT_PROMPTS = {
    "why_prediction": PREDICTION_EXPLANATION_PROMPT,
    "maintenance_due": MAINTENANCE_RECOMMENDATION_PROMPT,
    "explain_anomaly": ANOMALY_EXPLANATION_PROMPT,
    "compare_equipment": EQUIPMENT_COMPARISON_PROMPT,
    "show_trends": TREND_ANALYSIS_PROMPT,
    "equipment_status": EQUIPMENT_STATUS_PROMPT,
    "general_query": GENERAL_QUERY_PROMPT,
}
