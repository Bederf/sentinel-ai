"""
Technician Chat Service - Guided Diagnosis Flow Engine

Provides conversational AI guidance for technicians through step-by-step
fault diagnosis, checkpoint tracking, and repair procedure recommendations.

Usage:
    from app.services.technician_chat import DiagnosisFlowEngine

    engine = DiagnosisFlowEngine()
    result = engine.start_diagnosis("session-123", "Carrier chiller showing E4")
    response = engine.process_response("session-123", "Oil level is low")
"""

import re
import logging
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field

from app.services.equipment_lookup import EquipmentLookup

logger = logging.getLogger(__name__)


class DiagnosisState(Enum):
    """States in the diagnosis flow"""
    IDENTIFYING = "identifying"      # Gathering equipment/fault info
    CHECKING = "checking"            # Running diagnostic checks
    ANALYZING = "analyzing"          # Analyzing collected data
    RESOLVING = "resolving"          # Providing resolution plan
    COMPLETE = "complete"            # Diagnosis finished


@dataclass
class Checkpoint:
    """Record of a checkpoint in the diagnosis flow"""
    step_id: str
    question: str
    response: Optional[str]
    timestamp: datetime
    state: DiagnosisState


@dataclass
class DiagnosisFlow:
    """State container for an active diagnosis session"""
    session_id: str
    state: DiagnosisState = DiagnosisState.IDENTIFYING
    equipment: Dict[str, Any] = field(default_factory=dict)
    fault_code: Optional[str] = None
    fault_info: Optional[Dict] = None
    checkpoints: List[Checkpoint] = field(default_factory=list)
    collected_info: Dict[str, Any] = field(default_factory=dict)
    current_step_index: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_checkpoint(self, step_id: str, question: str, response: Optional[str] = None) -> Checkpoint:
        """Add a checkpoint to the flow"""
        checkpoint = Checkpoint(
            step_id=step_id,
            question=question,
            response=response,
            timestamp=datetime.now(),
            state=self.state
        )
        self.checkpoints.append(checkpoint)
        self.updated_at = datetime.now()
        return checkpoint

    def update_checkpoint(self, step_id: str, response: str):
        """Update a checkpoint with the technician's response"""
        for checkpoint in self.checkpoints:
            if checkpoint.step_id == step_id:
                checkpoint.response = response
                checkpoint.timestamp = datetime.now()
                self.updated_at = datetime.now()
                return
        raise ValueError(f"Checkpoint not found: {step_id}")

    def advance_state(self, new_state: DiagnosisState):
        """Advance to the next diagnosis state"""
        self.state = new_state
        self.updated_at = datetime.now()

    def get_completed_checkpoints(self) -> List[Checkpoint]:
        """Get all checkpoints with responses"""
        return [cp for cp in self.checkpoints if cp.response is not None]

    def to_dict(self) -> Dict:
        """Serialize flow state for API response"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "equipment": self.equipment,
            "fault_code": self.fault_code,
            "current_step_index": self.current_step_index,
            "checkpoints": [
                {
                    "step_id": cp.step_id,
                    "question": cp.question,
                    "response": cp.response,
                    "timestamp": cp.timestamp.isoformat(),
                    "state": cp.state.value
                }
                for cp in self.checkpoints
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class DiagnosisFlowEngine:
    """
    Guided diagnosis flow engine for HVAC technicians.

    Manages conversational diagnosis sessions with:
    - Equipment identification
    - Fault code-specific diagnostic questions
    - Checkpoint tracking
    - Resolution recommendations
    """

    # Pre-defined diagnostic checklists for common faults
    FAULT_CHECKLISTS: Dict[str, List[Dict[str, Any]]] = {
        "E4": [
            {
                "id": "oil_level",
                "question": "Check the oil sight glass - what level do you see?",
                "options": ["Full", "3/4", "1/2", "1/4 or less", "Can't see - dirty glass"],
                "critical_responses": ["1/4 or less"]
            },
            {
                "id": "chiller_state",
                "question": "Is the chiller currently running or has it shut down?",
                "options": ["Running", "Shut down on fault", "Won't start"],
                "critical_responses": ["Shut down on fault"]
            },
            {
                "id": "oil_leaks",
                "question": "Any visible oil leaks around the compressor area?",
                "options": ["No leaks visible", "Minor seepage", "Active leak"],
                "critical_responses": ["Active leak"]
            },
            {
                "id": "oil_pressure",
                "question": "If you can access the oil pressure gauge, what's the reading?",
                "options": ["Normal (40-60 psi)", "Low (below 40 psi)", "No gauge available"],
                "critical_responses": ["Low (below 40 psi)"]
            }
        ],
        "E1": [
            {
                "id": "eev_position",
                "question": "Can you check the EEV position indicator?",
                "options": ["Moving normally", "Stuck fully open", "Stuck fully closed", "Erratic movement"],
                "critical_responses": ["Stuck fully closed", "Stuck fully open"]
            },
            {
                "id": "superheat",
                "question": "What's the current superheat reading?",
                "options": ["Normal (8-12°F)", "High (above 15°F)", "Low (below 5°F)", "Can't measure"],
                "critical_responses": ["High (above 15°F)", "Low (below 5°F)"]
            }
        ],
        "E3": [
            {
                "id": "discharge_temp",
                "question": "What's the discharge temperature reading?",
                "options": ["Normal (below 200°F)", "High (200-230°F)", "Critical (above 230°F)"],
                "critical_responses": ["Critical (above 230°F)"]
            },
            {
                "id": "condenser_airflow",
                "question": "Is the condenser fan running and airflow clear?",
                "options": ["Fan running, airflow good", "Fan running but restricted", "Fan not running"],
                "critical_responses": ["Fan not running", "Fan running but restricted"]
            },
            {
                "id": "coil_condition",
                "question": "What's the condition of the condenser coils?",
                "options": ["Clean", "Slightly dirty", "Heavy fouling", "Damaged fins"],
                "critical_responses": ["Heavy fouling", "Damaged fins"]
            }
        ],
        "FAULT_001": [
            {
                "id": "motor_connected",
                "question": "Is the motor connected to a load (pump, fan, belt)?",
                "options": ["Yes - connected", "No - disconnected/open shaft"],
                "critical_responses": ["No - disconnected/open shaft"]
            },
            {
                "id": "fault_timing",
                "question": "When did this fault occur?",
                "options": ["During startup", "While running at load", "After parameter change"],
                "critical_responses": []
            },
            {
                "id": "motor_rotation",
                "question": "Can you safely check if the motor shaft rotates freely?",
                "options": ["Rotates freely", "Stiff/binding", "Completely seized", "Can't safely check"],
                "critical_responses": ["Stiff/binding", "Completely seized"]
            }
        ],
        "U4": [
            {
                "id": "power_led",
                "question": "Check the outdoor unit PCB - is the power LED on?",
                "options": ["LED on solid", "LED blinking", "LED off"],
                "critical_responses": ["LED off"]
            },
            {
                "id": "comm_wiring",
                "question": "Check communication wiring between indoor and outdoor units - any damage?",
                "options": ["Wiring intact", "Loose connection found", "Damaged wiring"],
                "critical_responses": ["Loose connection found", "Damaged wiring"]
            },
            {
                "id": "terminal_voltage",
                "question": "Measure voltage at F1/F2 terminals (should be 12-20V DC)",
                "options": ["Voltage OK (12-20V)", "Low voltage", "No voltage", "Can't measure"],
                "critical_responses": ["Low voltage", "No voltage"]
            }
        ]
    }

    # Default checklist for unknown fault codes
    DEFAULT_CHECKLIST = [
        {
            "id": "describe_symptoms",
            "question": "Can you describe the main symptoms you're observing?",
            "options": None,  # Free text
            "critical_responses": []
        },
        {
            "id": "when_started",
            "question": "When did this issue start?",
            "options": ["Just now", "Today", "This week", "Ongoing issue"],
            "critical_responses": []
        },
        {
            "id": "recent_changes",
            "question": "Any recent maintenance or changes to the equipment?",
            "options": ["No recent changes", "Recent service", "Parts replaced", "Settings changed"],
            "critical_responses": []
        }
    ]

    def __init__(self):
        """Initialize the diagnosis flow engine"""
        self.flows: Dict[str, DiagnosisFlow] = {}
        self.equipment_lookup = EquipmentLookup()

    def start_diagnosis(self, session_id: str, initial_query: str) -> Dict:
        """
        Start a new diagnosis flow from natural language query.

        Args:
            session_id: Unique session identifier
            initial_query: Initial problem description from technician

        Returns:
            Dict with flow state and first questions
        """
        # Create new flow
        flow = DiagnosisFlow(session_id=session_id)
        self.flows[session_id] = flow

        # Parse the initial query to extract equipment info
        equipment_info = self._parse_equipment_query(initial_query)
        flow.equipment = equipment_info
        flow.fault_code = equipment_info.get("fault_code")

        logger.info(f"Started diagnosis flow {session_id}: {equipment_info}")

        # If we have a fault code, try to look it up
        if flow.fault_code and equipment_info.get("manufacturer"):
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                fault_result = loop.run_until_complete(
                    self.equipment_lookup.lookup_fault_code(
                        manufacturer=equipment_info["manufacturer"],
                        fault_code=flow.fault_code,
                        model=equipment_info.get("model")
                    )
                )
                loop.close()
                flow.fault_info = fault_result.get("fault")
            except Exception as e:
                logger.warning(f"Fault code lookup failed: {e}")

        # Generate first questions
        return self._get_next_step(flow)

    def process_response(self, session_id: str, step_id: str, response: str) -> Dict:
        """
        Process technician's response and return next step.

        Args:
            session_id: Session identifier
            step_id: ID of the checkpoint being answered
            response: Technician's response

        Returns:
            Dict with next step or resolution
        """
        flow = self.flows.get(session_id)
        if not flow:
            return {
                "error": True,
                "message": "No active diagnosis session found. Please start a new diagnosis.",
                "session_id": session_id
            }

        # Update the checkpoint with response
        try:
            flow.update_checkpoint(step_id, response)
        except ValueError:
            # Checkpoint doesn't exist, create it
            flow.add_checkpoint(step_id, "User response", response)

        flow.current_step_index += 1

        # Store response in collected info
        flow.collected_info[step_id] = response

        # Check if we should advance state
        self._evaluate_state_transition(flow)

        # Get next step
        return self._get_next_step(flow)

    def get_flow_state(self, session_id: str) -> Optional[Dict]:
        """Get current state of a diagnosis flow"""
        flow = self.flows.get(session_id)
        if flow:
            return flow.to_dict()
        return None

    def end_diagnosis(self, session_id: str) -> Dict:
        """End a diagnosis session and return summary"""
        flow = self.flows.get(session_id)
        if not flow:
            return {"error": True, "message": "Session not found"}

        summary = {
            "session_id": session_id,
            "equipment": flow.equipment,
            "fault_code": flow.fault_code,
            "checkpoints_completed": len(flow.get_completed_checkpoints()),
            "diagnosis_complete": flow.state == DiagnosisState.COMPLETE,
            "collected_info": flow.collected_info,
            "duration_seconds": (flow.updated_at - flow.created_at).total_seconds()
        }

        # Clean up
        del self.flows[session_id]

        return summary

    def _parse_equipment_query(self, query: str) -> Dict:
        """Extract equipment and fault info from natural language query"""
        query_lower = query.lower()

        # Extract manufacturer
        manufacturers = {
            "carrier": ["carrier"],
            "trane": ["trane"],
            "daikin": ["daikin"],
            "abb": ["abb"],
            "danfoss": ["danfoss"],
            "york": ["york"],
            "honeywell": ["honeywell"],
            "siemens": ["siemens"]
        }
        manufacturer = None
        for mfr, keywords in manufacturers.items():
            if any(kw in query_lower for kw in keywords):
                manufacturer = mfr
                break

        # Extract fault code patterns
        fault_patterns = [
            r'(?:fault|error|code|alarm)\s*[:#]?\s*([a-zA-Z0-9_-]+)',
            r'\b([EFAUHLueh]\d+)\b',
            r'\b(FAULT_\d+)\b',
            r'\b(ALARM_\d+)\b',
            r'\b(AL\d+)\b'
        ]
        fault_code = None
        for pattern in fault_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                fault_code = match.group(1).upper()
                break

        # Extract equipment type
        equipment_types = {
            "chiller": ["chiller", "chill", "30xa", "rtac"],
            "ahu": ["ahu", "air handling", "air handler"],
            "vsd": ["vsd", "vfd", "drive", "inverter", "variable speed", "acs580", "acs880"],
            "split": ["split", "daikin", "vrv", "vrf"],
            "pump": ["pump"],
            "compressor": ["compressor"]
        }
        equipment_type = None
        for eq_type, keywords in equipment_types.items():
            if any(kw in query_lower for kw in keywords):
                equipment_type = eq_type
                break

        # Extract model number patterns
        model_patterns = [
            r'\b(30XA[A-Z0-9-]*)\b',
            r'\b(RTAC[A-Z0-9-]*)\b',
            r'\b(ACS\d{3,4}[A-Z0-9-]*)\b',
            r'\b(VRV[A-Z0-9\s-]*)\b'
        ]
        model = None
        for pattern in model_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                model = match.group(1).upper()
                break

        return {
            "manufacturer": manufacturer,
            "fault_code": fault_code,
            "equipment_type": equipment_type,
            "model": model,
            "raw_query": query
        }

    def _get_next_step(self, flow: DiagnosisFlow) -> Dict:
        """Generate the next step in the diagnosis flow"""
        if flow.state == DiagnosisState.IDENTIFYING:
            return self._get_identifying_step(flow)
        elif flow.state == DiagnosisState.CHECKING:
            return self._get_checking_step(flow)
        elif flow.state == DiagnosisState.ANALYZING:
            return self._get_analysis_step(flow)
        elif flow.state == DiagnosisState.RESOLVING:
            return self._get_resolution_step(flow)
        else:
            return self._get_completion_step(flow)

    def _get_identifying_step(self, flow: DiagnosisFlow) -> Dict:
        """Generate questions to identify the equipment and problem"""
        questions = []

        # Check what info we're missing
        if not flow.equipment.get("manufacturer"):
            questions.append({
                "id": "manufacturer",
                "question": "What's the equipment manufacturer?",
                "options": ["Carrier", "Trane", "Daikin", "ABB", "Danfoss", "York", "Other"],
                "type": "select"
            })

        if not flow.fault_code:
            questions.append({
                "id": "fault_code",
                "question": "What fault code is displaying? (e.g., E4, F0001, AL01)",
                "options": None,
                "type": "text",
                "placeholder": "Enter fault code"
            })

        if not flow.equipment.get("model"):
            questions.append({
                "id": "model",
                "question": "What's the model number? (check the nameplate)",
                "options": None,
                "type": "text",
                "placeholder": "e.g., 30XA-150, ACS580"
            })

        if not flow.equipment.get("equipment_type"):
            questions.append({
                "id": "equipment_type",
                "question": "What type of equipment is this?",
                "options": ["Chiller", "AHU", "VSD/VFD", "Split System", "Pump", "Other"],
                "type": "select"
            })

        # If we have enough info, advance to checking state
        if not questions:
            flow.advance_state(DiagnosisState.CHECKING)
            return self._get_checking_step(flow)

        # Add checkpoint for first question
        first_q = questions[0]
        flow.add_checkpoint(first_q["id"], first_q["question"])

        return {
            "type": "questions",
            "state": flow.state.value,
            "message": "I need a bit more information to help diagnose this:",
            "questions": questions,
            "flow": flow.to_dict()
        }

    def _get_checking_step(self, flow: DiagnosisFlow) -> Dict:
        """Generate diagnostic checks based on fault code"""
        # Get checklist for this fault code
        checklist = self.FAULT_CHECKLISTS.get(
            flow.fault_code,
            self.DEFAULT_CHECKLIST
        )

        # Find next unanswered check
        answered_ids = set(flow.collected_info.keys())
        next_check = None
        for check in checklist:
            if check["id"] not in answered_ids:
                next_check = check
                break

        if not next_check:
            # All checks complete, move to analyzing
            flow.advance_state(DiagnosisState.ANALYZING)
            return self._get_analysis_step(flow)

        # Add checkpoint
        flow.add_checkpoint(next_check["id"], next_check["question"])

        # Calculate progress
        total_checks = len(checklist)
        completed_checks = len([c for c in checklist if c["id"] in answered_ids])

        return {
            "type": "checkpoint",
            "state": flow.state.value,
            "message": f"Diagnostic check {completed_checks + 1} of {total_checks}:",
            "check": {
                "id": next_check["id"],
                "question": next_check["question"],
                "options": next_check.get("options"),
                "type": "select" if next_check.get("options") else "text"
            },
            "progress": {
                "current": completed_checks + 1,
                "total": total_checks,
                "percent": int((completed_checks / total_checks) * 100)
            },
            "flow": flow.to_dict()
        }

    def _get_analysis_step(self, flow: DiagnosisFlow) -> Dict:
        """Analyze collected data and provide diagnosis"""
        # Analyze responses for critical findings
        critical_findings = []
        checklist = self.FAULT_CHECKLISTS.get(flow.fault_code, self.DEFAULT_CHECKLIST)

        for check in checklist:
            response = flow.collected_info.get(check["id"])
            if response and check.get("critical_responses"):
                if response in check["critical_responses"]:
                    critical_findings.append({
                        "check": check["question"],
                        "response": response,
                        "severity": "high"
                    })

        # Generate diagnosis based on findings
        diagnosis = self._generate_diagnosis(flow, critical_findings)

        # Move to resolving
        flow.advance_state(DiagnosisState.RESOLVING)
        flow.collected_info["diagnosis"] = diagnosis
        flow.collected_info["critical_findings"] = critical_findings

        return {
            "type": "analysis",
            "state": flow.state.value,
            "message": "Based on your responses, here's what I've found:",
            "diagnosis": diagnosis,
            "critical_findings": critical_findings,
            "confidence": "high" if len(critical_findings) > 0 else "medium",
            "flow": flow.to_dict()
        }

    def _get_resolution_step(self, flow: DiagnosisFlow) -> Dict:
        """Generate resolution plan with repair steps"""
        diagnosis = flow.collected_info.get("diagnosis", {})
        critical_findings = flow.collected_info.get("critical_findings", [])

        # Get repair steps from fault info or generate generic ones
        repair_steps = []
        parts_needed = []
        safety_notes = []

        if flow.fault_info:
            # Use recommended fix from fault lookup
            rec_fix = flow.fault_info.get("recommended_fix", {})
            if isinstance(rec_fix, dict):
                repair_steps = rec_fix.get("immediate", [])
            elif isinstance(rec_fix, str):
                repair_steps = [rec_fix]

            # Get parts from fault lookup
            if flow.fault_info.get("parts_suggested"):
                parts_needed = [p.get("part_name") for p in flow.fault_info.get("parts_suggested", [])]

            safety_notes = [flow.fault_info.get("safety_notes")] if flow.fault_info.get("safety_notes") else []

        # Add generic safety notes
        if not safety_notes:
            safety_notes = [
                "Always follow LOTO (Lock Out Tag Out) procedures",
                "Ensure proper PPE is worn",
                "Verify equipment is de-energized before service"
            ]

        # Generate repair steps if not available from fault lookup
        if not repair_steps:
            repair_steps = self._generate_repair_steps(flow, critical_findings)

        # Move to complete
        flow.advance_state(DiagnosisState.COMPLETE)

        return {
            "type": "resolution",
            "state": flow.state.value,
            "message": "Here's your repair plan:",
            "diagnosis_summary": diagnosis.get("summary", "Issue identified - see repair steps"),
            "repair_steps": repair_steps,
            "parts_needed": parts_needed,
            "estimated_time": self._estimate_repair_time(critical_findings),
            "safety_notes": safety_notes,
            "next_actions": [
                "Document findings in job card",
                "Order required parts if needed",
                "Schedule follow-up visit if parts required"
            ],
            "flow": flow.to_dict()
        }

    def _get_completion_step(self, flow: DiagnosisFlow) -> Dict:
        """Generate completion summary"""
        return {
            "type": "complete",
            "state": flow.state.value,
            "message": "Diagnosis complete!",
            "summary": {
                "equipment": flow.equipment,
                "fault_code": flow.fault_code,
                "checkpoints_completed": len(flow.get_completed_checkpoints()),
                "duration_seconds": (flow.updated_at - flow.created_at).total_seconds()
            },
            "flow": flow.to_dict()
        }

    def _evaluate_state_transition(self, flow: DiagnosisFlow):
        """Evaluate if flow should transition to next state"""
        if flow.state == DiagnosisState.IDENTIFYING:
            # Move to checking if we have manufacturer, fault code, and type
            if (flow.equipment.get("manufacturer") and
                flow.fault_code and
                flow.equipment.get("equipment_type")):
                flow.advance_state(DiagnosisState.CHECKING)

        elif flow.state == DiagnosisState.CHECKING:
            # Move to analyzing after minimum checkpoints
            checklist = self.FAULT_CHECKLISTS.get(flow.fault_code, self.DEFAULT_CHECKLIST)
            answered = len([c for c in checklist if c["id"] in flow.collected_info])
            if answered >= len(checklist):
                flow.advance_state(DiagnosisState.ANALYZING)

    def _generate_diagnosis(self, flow: DiagnosisFlow, critical_findings: List[Dict]) -> Dict:
        """Generate diagnosis summary from collected info"""
        fault_name = "Unknown fault"
        if flow.fault_info:
            fault_name = flow.fault_info.get("name", fault_name)

        probable_cause = "Unable to determine"
        if critical_findings:
            # Use the most critical finding
            probable_cause = critical_findings[0].get("response", probable_cause)
        elif flow.fault_info and flow.fault_info.get("probable_causes"):
            # Use first probable cause from fault lookup
            causes = flow.fault_info["probable_causes"]
            if causes:
                probable_cause = causes[0].get("cause", probable_cause)

        return {
            "fault_code": flow.fault_code,
            "fault_name": fault_name,
            "probable_cause": probable_cause,
            "summary": f"{flow.fault_code}: {fault_name} - Likely cause: {probable_cause}",
            "confidence": "high" if len(critical_findings) > 0 else "medium"
        }

    def _generate_repair_steps(self, flow: DiagnosisFlow, critical_findings: List[Dict]) -> List[str]:
        """Generate generic repair steps based on findings"""
        steps = [
            f"1. Isolate power supply to the {flow.equipment.get('equipment_type', 'equipment')} (LOTO required)",
            "2. Verify all isolation points are secure"
        ]

        if critical_findings:
            for i, finding in enumerate(critical_findings, start=3):
                steps.append(f"{i}. Address: {finding.get('response', 'Issue found')}")

        steps.extend([
            f"{len(steps) + 1}. Follow manufacturer repair procedure for {flow.fault_code or 'this fault'}",
            f"{len(steps) + 2}. Test operation after repair",
            f"{len(steps) + 3}. Document all findings and actions in job card"
        ])

        return steps

    def _estimate_repair_time(self, critical_findings: List[Dict]) -> str:
        """Estimate repair time based on findings"""
        if not critical_findings:
            return "1-2 hours (investigation)"
        elif len(critical_findings) == 1:
            return "2-4 hours"
        else:
            return "4-8 hours (multiple issues)"


# Singleton instance
_engine_instance: Optional[DiagnosisFlowEngine] = None


def get_diagnosis_engine() -> DiagnosisFlowEngine:
    """Get or create the singleton diagnosis engine"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DiagnosisFlowEngine()
    return _engine_instance
