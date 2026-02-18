#!/usr/bin/env python3
"""Ingest equipment knowledge into RAG system with embeddings.

This script:
1. Updates existing documents/knowledge with embeddings
2. Adds sample equipment knowledge for common BMS equipment types
3. Chunks and embeds documents

Usage:
    cd backend && source venv/bin/activate
    python scripts/ingest_rag_knowledge.py
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client
from app.services.embedding_service import get_embedding_service
from app.services.vector_db import get_vector_db_service


# Equipment knowledge entries to ingest
EQUIPMENT_KNOWLEDGE = [
    # Chiller knowledge
    {
        "equipment_type": "chiller",
        "manufacturer": "York",
        "model": "YCIV",
        "component": "compressor",
        "knowledge_type": "fault_code",
        "code": "E02",
        "title": "Low Pressure Shutdown",
        "description": "Compressor shutdown due to low suction pressure",
        "symptoms": ["Compressor stopped", "Low pressure alarm", "E02 fault code"],
        "possible_causes": ["Refrigerant leak", "Blocked expansion valve", "Dirty evaporator", "Low ambient temperature"],
        "diagnostic_steps": ["Check suction pressure", "Inspect for refrigerant leaks", "Check evaporator condition", "Verify expansion valve operation"],
        "solution": "Check for refrigerant leaks, clean evaporator if dirty. May need to add refrigerant if system is low.",
        "parts_required": {"items": [{"part_number": "026-35389-000", "description": "Low pressure switch", "quantity": 1}]},
        "estimated_labor_hours": 2.5,
        "priority": "high"
    },
    {
        "equipment_type": "chiller",
        "manufacturer": "York",
        "model": "YCIV",
        "component": "condenser",
        "knowledge_type": "maintenance_procedure",
        "code": "PM-COND-001",
        "title": "Condenser Coil Cleaning Procedure",
        "description": "Monthly condenser coil cleaning for optimal heat rejection",
        "symptoms": [],
        "possible_causes": [],
        "diagnostic_steps": [],
        "solution": "1. De-energize unit. 2. Apply coil cleaner to condenser fins. 3. Allow 15 minutes to soak. 4. Rinse with low-pressure water. 5. Verify fin condition.",
        "parts_required": {"items": [{"part_number": "CON-CLN-01", "description": "Coil cleaner solution", "quantity": 1}]},
        "estimated_labor_hours": 1.0,
        "priority": "medium"
    },
    {
        "equipment_type": "chiller",
        "manufacturer": "Carrier",
        "model": "30XA",
        "component": "compressor",
        "knowledge_type": "fault_code",
        "code": "A1",
        "title": "Motor Overload Trip",
        "description": "Compressor motor thermal overload protection activated",
        "symptoms": ["Compressor stopped", "Motor overload indicator", "A1 alarm code"],
        "possible_causes": ["Low voltage supply", "High ambient temperature", "Dirty motor windings", "Mechanical binding"],
        "diagnostic_steps": ["Check supply voltage", "Measure motor current", "Inspect motor windings", "Check bearing condition"],
        "solution": "Allow motor to cool, check voltage supply, clean motor if dirty. If recurring, check bearings.",
        "parts_required": {"items": [{"part_number": "HH79NZ070", "description": "Motor overload relay", "quantity": 1}]},
        "estimated_labor_hours": 3.0,
        "priority": "high"
    },

    # AHU knowledge
    {
        "equipment_type": "ahu",
        "manufacturer": "Carrier",
        "model": "39M",
        "component": "fan",
        "knowledge_type": "fault_code",
        "code": "FAN-01",
        "title": "Supply Fan Failure",
        "description": "Supply fan motor failure or VFD fault",
        "symptoms": ["No airflow", "Fan status alarm", "High static pressure"],
        "possible_causes": ["VFD fault", "Motor failure", "Belt broken", "Overload trip"],
        "diagnostic_steps": ["Check VFD status", "Verify motor rotation", "Inspect belt condition", "Measure motor current"],
        "solution": "Check VFD for fault codes, reset if transient. Replace belt if broken. Check motor bearings if overheating.",
        "parts_required": {"items": [{"part_number": "V-BELT-A68", "description": "V-Belt A68", "quantity": 2}]},
        "estimated_labor_hours": 1.5,
        "priority": "critical"
    },
    {
        "equipment_type": "ahu",
        "manufacturer": "Carrier",
        "model": "39M",
        "component": "filter",
        "knowledge_type": "maintenance_procedure",
        "code": "PM-FILT-001",
        "title": "Filter Replacement Procedure",
        "description": "Quarterly air filter replacement for optimal air quality",
        "symptoms": [],
        "possible_causes": [],
        "diagnostic_steps": [],
        "solution": "1. Isolate unit. 2. Remove access panel. 3. Remove dirty filters. 4. Install new filters (arrow direction matches airflow). 5. Record filter change.",
        "parts_required": {"items": [{"part_number": "MERV13-24x24x2", "description": "MERV 13 Filter 24x24x2", "quantity": 8}]},
        "estimated_labor_hours": 0.5,
        "priority": "medium"
    },
    {
        "equipment_type": "ahu",
        "manufacturer": "Trane",
        "model": "M-Series",
        "component": "coil",
        "knowledge_type": "troubleshooting_guide",
        "code": "TS-COIL-001",
        "title": "Low Cooling Capacity Diagnosis",
        "description": "Step-by-step diagnosis for inadequate cooling from AHU",
        "symptoms": ["High supply air temperature", "Space too warm", "Coil not cold"],
        "possible_causes": ["Low chilled water flow", "Air in coil", "Dirty coil", "Control valve stuck"],
        "diagnostic_steps": ["Check CHW supply temp", "Verify control valve position", "Measure delta-T across coil", "Inspect coil surface"],
        "solution": "Verify CHW system operation, bleed air from coil if needed, clean coil if dirty, check valve actuator.",
        "parts_required": {},
        "estimated_labor_hours": 2.0,
        "priority": "medium"
    },

    # Boiler knowledge
    {
        "equipment_type": "boiler",
        "manufacturer": "Cleaver-Brooks",
        "model": "CB",
        "component": "burner",
        "knowledge_type": "fault_code",
        "code": "LF",
        "title": "Lockout - Flame Failure",
        "description": "Burner lockout due to flame failure during operation",
        "symptoms": ["Burner off", "Lockout light on", "No heat"],
        "possible_causes": ["Gas supply interrupted", "Flame sensor dirty", "Igniter failure", "Control malfunction"],
        "diagnostic_steps": ["Check gas supply pressure", "Inspect flame sensor", "Verify igniter spark", "Check flame signal strength"],
        "solution": "Clean flame sensor with emery cloth. Verify gas pressure. Check igniter gap. Reset lockout after addressing cause.",
        "parts_required": {"items": [{"part_number": "FS-UV-01", "description": "UV Flame sensor", "quantity": 1}]},
        "estimated_labor_hours": 1.5,
        "priority": "critical"
    },
    {
        "equipment_type": "boiler",
        "manufacturer": "Cleaver-Brooks",
        "model": "CB",
        "component": "safety",
        "knowledge_type": "maintenance_procedure",
        "code": "PM-SAFE-001",
        "title": "Low Water Cutoff Test",
        "description": "Weekly low water cutoff safety test procedure",
        "symptoms": [],
        "possible_causes": [],
        "diagnostic_steps": [],
        "solution": "1. Slowly drain water using blowdown valve. 2. Verify burner shuts off before water drops below safe level. 3. Refill and verify normal operation. 4. Document test.",
        "parts_required": {},
        "estimated_labor_hours": 0.25,
        "priority": "critical"
    },

    # Cooling tower knowledge
    {
        "equipment_type": "cooling_tower",
        "manufacturer": "Marley",
        "model": "NC",
        "component": "fan",
        "knowledge_type": "troubleshooting_guide",
        "code": "TS-FAN-001",
        "title": "Fan Vibration Diagnosis",
        "description": "Diagnosis and correction of cooling tower fan vibration",
        "symptoms": ["Excessive vibration", "Unusual noise", "Vibration alarm"],
        "possible_causes": ["Fan blade damage", "Blade imbalance", "Bearing wear", "Loose hub"],
        "diagnostic_steps": ["Visually inspect blades", "Check blade pitch", "Measure vibration levels", "Inspect bearings"],
        "solution": "Balance fan blades, replace damaged blades, check and replace bearings if worn. Verify blade pitch settings.",
        "parts_required": {"items": [{"part_number": "BLADE-36-FRP", "description": "FRP Fan blade 36 inch", "quantity": 1}]},
        "estimated_labor_hours": 4.0,
        "priority": "high"
    },
    {
        "equipment_type": "cooling_tower",
        "manufacturer": "Marley",
        "model": "NC",
        "component": "water_treatment",
        "knowledge_type": "maintenance_procedure",
        "code": "PM-WT-001",
        "title": "Water Treatment and Blowdown",
        "description": "Weekly water treatment verification and blowdown procedure",
        "symptoms": [],
        "possible_causes": [],
        "diagnostic_steps": [],
        "solution": "1. Test conductivity. 2. Adjust blowdown to maintain cycles. 3. Check chemical feed rates. 4. Inspect basin for debris. 5. Document readings.",
        "parts_required": {},
        "estimated_labor_hours": 0.5,
        "priority": "medium"
    },

    # Pump knowledge
    {
        "equipment_type": "pump",
        "manufacturer": "Armstrong",
        "model": "4300",
        "component": "seal",
        "knowledge_type": "fault_code",
        "code": "SEAL-LEAK",
        "title": "Mechanical Seal Leak",
        "description": "Water leaking from pump mechanical seal",
        "symptoms": ["Water dripping from pump", "Wet pump base", "Low system pressure"],
        "possible_causes": ["Seal wear", "Dry running damage", "Misalignment", "Cavitation damage"],
        "diagnostic_steps": ["Verify leak location", "Check pump alignment", "Measure vibration", "Inspect coupling"],
        "solution": "Replace mechanical seal. Check alignment and correct if needed. Verify proper venting to prevent dry running.",
        "parts_required": {"items": [{"part_number": "SEAL-4300-1.5", "description": "Mechanical seal kit 1.5 inch", "quantity": 1}]},
        "estimated_labor_hours": 3.0,
        "priority": "high"
    },
    {
        "equipment_type": "pump",
        "manufacturer": "Armstrong",
        "model": "4300",
        "component": "motor",
        "knowledge_type": "troubleshooting_guide",
        "code": "TS-PUMP-001",
        "title": "Pump Not Starting Diagnosis",
        "description": "Step-by-step diagnosis for pump that won't start",
        "symptoms": ["Pump not running", "No motor sound", "Control showing stop"],
        "possible_causes": ["Power supply issue", "Starter fault", "Motor failure", "Control interlock"],
        "diagnostic_steps": ["Verify power at starter", "Check starter contacts", "Test motor resistance", "Check control signals"],
        "solution": "Verify power supply and control signals. Reset overload if tripped. Replace starter contacts if pitted.",
        "parts_required": {},
        "estimated_labor_hours": 1.0,
        "priority": "high"
    },

    # VFD knowledge
    {
        "equipment_type": "vfd",
        "manufacturer": "ABB",
        "model": "ACS580",
        "component": "drive",
        "knowledge_type": "fault_code",
        "code": "F0001",
        "title": "Overcurrent Fault",
        "description": "Drive tripped on output overcurrent protection",
        "symptoms": ["Drive stopped", "F0001 fault displayed", "Motor stopped"],
        "possible_causes": ["Motor overload", "Short circuit in motor cable", "Motor winding fault", "Acceleration too fast"],
        "diagnostic_steps": ["Check motor cable insulation", "Measure motor resistance", "Review acceleration ramp", "Check load conditions"],
        "solution": "Check motor and cables for faults. Increase acceleration time if load is high inertia. Reset and monitor.",
        "parts_required": {},
        "estimated_labor_hours": 1.5,
        "priority": "high"
    },
    {
        "equipment_type": "vfd",
        "manufacturer": "ABB",
        "model": "ACS580",
        "component": "drive",
        "knowledge_type": "fault_code",
        "code": "F0002",
        "title": "Overvoltage Fault",
        "description": "Drive DC bus voltage exceeded maximum limit",
        "symptoms": ["Drive stopped", "F0002 fault displayed", "Motor coasting to stop"],
        "possible_causes": ["Deceleration too fast", "Regenerative load", "High supply voltage", "Brake resistor failure"],
        "diagnostic_steps": ["Check supply voltage", "Review deceleration ramp", "Verify brake resistor", "Check load type"],
        "solution": "Increase deceleration time. Install or verify brake resistor for regenerative loads. Check supply voltage.",
        "parts_required": {"items": [{"part_number": "NBRA-658C", "description": "Brake resistor 3.3 ohm", "quantity": 1}]},
        "estimated_labor_hours": 2.0,
        "priority": "medium"
    },

    # FCU knowledge
    {
        "equipment_type": "fcu",
        "manufacturer": "Carrier",
        "model": "42N",
        "component": "valve",
        "knowledge_type": "troubleshooting_guide",
        "code": "TS-FCU-001",
        "title": "No Cooling from FCU",
        "description": "Fan coil unit running but not providing cooling",
        "symptoms": ["Fan running", "Warm air from unit", "Space temperature high"],
        "possible_causes": ["Control valve stuck closed", "No chilled water flow", "Thermostat fault", "Coil airbound"],
        "diagnostic_steps": ["Check valve position", "Feel CHW pipes for cold", "Verify thermostat operation", "Bleed air from coil"],
        "solution": "Verify CHW available at unit. Check valve actuator operation. Bleed air from coil if pipes are cold but unit is warm.",
        "parts_required": {},
        "estimated_labor_hours": 1.0,
        "priority": "medium"
    },

    # BMS Controller knowledge
    {
        "equipment_type": "bms_controller",
        "manufacturer": "Johnson Controls",
        "model": "FX-PC",
        "component": "controller",
        "knowledge_type": "troubleshooting_guide",
        "code": "TS-BMS-001",
        "title": "Controller Offline Diagnosis",
        "description": "BMS controller not communicating with supervisory system",
        "symptoms": ["Controller offline", "No data from points", "Communication error"],
        "possible_causes": ["Network issue", "Controller fault", "IP conflict", "Power supply"],
        "diagnostic_steps": ["Ping controller IP", "Check network cables", "Verify power LED", "Check for IP conflicts"],
        "solution": "Verify network connectivity. Check power supply. Reboot controller if network is OK. Check for duplicate IP addresses.",
        "parts_required": {},
        "estimated_labor_hours": 1.0,
        "priority": "critical"
    },
    {
        "equipment_type": "bms_controller",
        "manufacturer": "Honeywell",
        "model": "Spyder",
        "component": "input",
        "knowledge_type": "fault_code",
        "code": "SENS-FAIL",
        "title": "Sensor Failure",
        "description": "Temperature sensor reading out of range or failed",
        "symptoms": ["Sensor showing 999 or -999", "Control not working", "Sensor fail alarm"],
        "possible_causes": ["Sensor open circuit", "Sensor short circuit", "Wiring fault", "Sensor drift"],
        "diagnostic_steps": ["Measure sensor resistance", "Check wiring continuity", "Compare to another sensor", "Check terminal connections"],
        "solution": "Check wiring first. Measure sensor resistance (10K NTC typical). Replace sensor if out of specification.",
        "parts_required": {"items": [{"part_number": "C7041D2001", "description": "10K NTC temperature sensor", "quantity": 1}]},
        "estimated_labor_hours": 0.75,
        "priority": "medium"
    },
]


async def main():
    """Main ingestion function."""
    print("RAG Knowledge Ingestion Script")
    print("=" * 50)

    # Initialize services
    client = get_supabase_client()
    embedding_service = get_embedding_service()
    vector_db = get_vector_db_service(client)

    print("\nEmbedding model: all-MiniLM-L6-v2")
    print(f"Vector dimensions: {embedding_service.get_embedding_dimension()}")

    # 1. Update existing knowledge entries with embeddings
    print("\n1. Updating existing knowledge entries with embeddings...")
    try:
        result = client.table('equipment_knowledge').select('id, title, description').is_('embedding', 'null').execute()
        existing = result.data or []
        print(f"   Found {len(existing)} entries without embeddings")

        for entry in existing:
            text = f"{entry['title']}. {entry['description']}"
            embedding = embedding_service.embed_text(text)

            client.table('equipment_knowledge').update({
                'embedding': embedding
            }).eq('id', entry['id']).execute()
            print(f"   Updated: {entry['title']}")

    except Exception as e:
        print(f"   Error updating existing: {e}")

    # 2. Add new knowledge entries
    print("\n2. Adding new equipment knowledge entries...")
    added_count = 0

    for knowledge in EQUIPMENT_KNOWLEDGE:
        # Check if already exists
        existing = client.table('equipment_knowledge').select('id').eq('code', knowledge['code']).execute()
        if existing.data:
            print(f"   Skipping (exists): {knowledge['title']}")
            continue

        # Generate embedding
        text = f"{knowledge['title']}. {knowledge['description']}"
        if knowledge.get('symptoms'):
            text += f" Symptoms: {', '.join(knowledge['symptoms'])}."
        if knowledge.get('solution'):
            text += f" Solution: {knowledge['solution']}"

        embedding = embedding_service.embed_text(text)

        # Insert with embedding
        entry_data = {**knowledge, 'embedding': embedding}
        try:
            client.table('equipment_knowledge').insert(entry_data).execute()
            print(f"   Added: {knowledge['title']}")
            added_count += 1
        except Exception as e:
            print(f"   Error adding {knowledge['title']}: {e}")

    print(f"\n   Added {added_count} new knowledge entries")

    # 3. Process documents (chunk and embed)
    print("\n3. Processing documents for chunking and embedding...")
    try:
        docs = client.table('documents').select('id, title, indexing_status').eq('indexing_status', 'pending').execute()
        pending_docs = docs.data or []
        print(f"   Found {len(pending_docs)} documents pending indexing")

        for doc in pending_docs:
            chunk_count = vector_db.chunk_and_embed_document(doc['id'])
            print(f"   Indexed {doc['title']}: {chunk_count} chunks")
    except Exception as e:
        print(f"   Error processing documents: {e}")

    # 4. Summary
    print("\n" + "=" * 50)
    print("Ingestion Complete!")

    # Get counts
    try:
        doc_count = client.table('documents').select('id', count='exact').execute().count or 0
        chunk_count = client.table('document_chunks').select('id', count='exact').execute().count or 0
        knowledge_count = client.table('equipment_knowledge').select('id', count='exact').execute().count or 0

        print("\nCurrent counts:")
        print(f"  Documents: {doc_count}")
        print(f"  Chunks: {chunk_count}")
        print(f"  Knowledge entries: {knowledge_count}")
    except Exception as e:
        print(f"Error getting counts: {e}")

    # 5. Test search
    print("\n" + "=" * 50)
    print("Testing search...")

    test_queries = [
        ("chiller high pressure", "chiller"),
        ("fan vibration", None),
        ("filter replacement", "ahu"),
    ]

    for query, eq_type in test_queries:
        print(f"\nQuery: '{query}' (equipment_type: {eq_type})")
        results = vector_db.search_knowledge(query, n_results=2, equipment_type=eq_type, similarity_threshold=0.2)
        if results:
            for r in results:
                print(f"  - {r['title']} (similarity: {r.get('similarity', 0):.3f})")
        else:
            print("  No results found")


if __name__ == "__main__":
    asyncio.run(main())
