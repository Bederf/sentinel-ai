"""
BMS Intelligence Agents Package
================================
LangGraph-based stateful agents for multi-turn conversations.

Provides:
  - Desk Complaint Agent: comfort complaint diagnosis via StateGraph
  - Recommendation Agent: proactive recommendation validation & execution
"""

from app.agents.desk_complaint_graph import get_desk_complaint_graph
from app.agents.recommendation_graph import get_recommendation_graph

__all__ = ["get_desk_complaint_graph", "get_recommendation_graph"]
