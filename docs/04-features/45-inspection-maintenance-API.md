---
title: "Phase 45: Routine Inspection & Maintenance - API Documentation"
type: "api-documentation"
status: "implemented"
version: "45.1"
date: "2026-02-01"
phase: "45"
implements: "Routine Inspection & Maintenance (Technical Phase 45)"
requires: "Phase 44 (Asset Baseline Assessment)"
---

# Phase 45: Routine Inspection & Maintenance API

This document describes the REST API endpoints for routine inspection and maintenance management as part of Phase 45 implementation.

## Overview

The inspection system builds upon Phase 44 (Asset Baseline Assessment) to provide:
1. **Automated inspection scheduling** based on baseline findings
2. **Checklist-driven inspections** with pass/fail criteria
3. **Deficiency tracking** with automatic work order creation
4. **Mobile-first results capture** for field technicians
5. **Trend analysis** to identify recurring issues

## Key Features

- **Schedule Management**: Recurring inspection schedules (weekly, monthly, quarterly, annual)
- **Task Generation**: Automatic task creation from schedules
- **Checklist Templates**: Pre-defined checklists for each equipment type
- **Results Capture**: Mobile-friendly inspection results capture
- **Deficiency Tracking**: Automatic deficiency creation from failed items
- **Work Order Integration**: Link deficiencies to work orders

## Database Schema

### Tables Created

1. **inspection_schedules**: Recurring inspection schedule definitions
2. **inspection_checklist_templates**: Template definitions for checklists
3. **inspection_tasks**: Individual scheduled inspection instances
4. **inspection_results**: Completed inspection data and measurements
5. **inspection_deficiencies**: Issues found during inspections
6. **inspection_measurements**: Detailed measurement records

### Views Created

1. **v_inspection_overview**: Summary of inspection status across equipment
2. **v_inspection_tasks_due**: Upcoming and overdue tasks
3. **v_equipment_inspection_summary**: Per-equipment inspection statistics
4. **v_critical_inspection_findings**: Recent critical deficiencies

### Sample Data Included

- Generator Monthly Inspection Template (8 checklist items)
- Chiller Monthly Inspection Template (8 checklist items)
- Pre-configured with baseline reference integration

## API Endpoints

### Inspection Schedule Management

#### Create Inspection Schedule
```http
POST /api/inspection/schedules
```

Create a recurring inspection schedule for equipment.

**Request Body:**
```json
{
  "equipment_id": "generator-001",
  "schedule_name": "Monthly Generator Inspection",
  "schedule_description": "Monthly routine inspection with vibration analysis",
  "frequency_type": "monthly",
  "estimated_duration_minutes": 90,
  "assigned_to": "John Smith",
  "required_skills": ["generator_maintenance", "vibration_analysis"],
  "is_active": true
}
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "equipment_id": "generator-001",
  "schedule_name": "Monthly Generator Inspection",
  "frequency_type": "monthly",
  "estimated_duration_minutes": 90,
  "assigned_to": "John Smith",
  "required_skills": ["generator_maintenance", "vibration_analysis"],
  "is_active": true,
  "created_by": "admin",
  "created_at": "2026-02-01T10:00:00Z",
  "updated_at": "2026-02-01T10:00:00Z"
}
```

**Frequency Types:**
- `weekly`: Every week
- `monthly`: Every month
- `quarterly`: Every 3 months
- `annual`: Every year
- `custom`: Use frequency_days field

#### List Inspection Schedules
```http
GET /api/inspection/schedules
```

**Query Parameters:**
- `equipment_id` (optional): Filter by equipment

**Response:** Array of inspection schedule objects

#### Get Inspection Schedule
```http
GET /api/inspection/schedules/{schedule_id}
```

**Response:** Inspection schedule object

#### Deactivate Inspection Schedule
```http
DELETE /api/inspection/schedules/{schedule_id}
```

**Response:** 204 No Content

### Inspection Task Management

#### Generate Inspection Tasks
```http
POST /api/inspection/tasks/generate
```

Generate inspection tasks from active schedules. Can filter by specific equipment.

**Query Parameters:**
- `equipment_id` (optional): Specific equipment to generate tasks for

**Response:**
```json
{
  "success": true,
  "generated_count": 5,
  "equipment_id": "generator-001",
  "tasks": [
    {"id": "123...", "name": "Monthly Generator Inspection - Generator 001"},
    {"id": "124...", "name": "Monthly Generator Inspection - Generator 002"}
  ]
}
```

#### Get Inspection Task
```http
GET /api/inspection/tasks/{task_id}
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174001",
  "schedule_id": "123e4567-e89b-12d3-a456-426614174000",
  "task_name": "Monthly Generator Inspection - Generator 001",
  "equipment_id": "generator-001",
  "scheduled_date": "2026-03-01T08:00:00Z",
  "due_date": "2026-03-08T17:00:00Z",
  "assigned_to": "John Smith",
  "status": "scheduled",
  "priority": "high",
  "is_critical": true,
  "estimated_duration_minutes": 90
}
```

#### List Due Inspections
```http
GET /api/inspection/tasks/due/days/{days_ahead}
```

**Query Parameters:**
- `days_ahead`: Days ahead to check (default: 7)
- `assigned_to` (optional): Filter by technician
- `equipment_id` (optional): Filter by equipment

**Response:** Array of due inspection tasks

#### List Overdue Inspections
```http
GET /api/inspection/tasks/overdue
```

**Query Parameters:**
- `assigned_to` (optional): Filter by technician
- `equipment_id` (optional): Filter by equipment

**Response:** Array of overdue inspection tasks

#### Assign Inspection Task
```http
POST /api/inspection/tasks/{task_id}/assign
```

**Request Body:**
```json
{
  "assigned_to": "John Smith",
  "assigned_by": "Supervisor"
}
```

**Response:** Updated inspection task

#### Start Inspection Task
```http
POST /api/inspection/tasks/{task_id}/start
```

**Request Body:**
```json
{
  "started_by": "John Smith"
}
```

**Response:** Updated inspection task with status "in_progress"

#### Complete Inspection Task
```http
POST /api/inspection/tasks/{task_id}/complete
```

**Request Body:**
```json
{
  "completed_by": "John Smith",
  "completion_notes": "All checks completed successfully",
  "actual_duration_minutes": 85
}
```

**Response:** Updated inspection task with status "completed"

#### Reschedule Inspection Task
```http
POST /api/inspection/tasks/{task_id}/reschedule
```

**Request Body:**
```json
{
  "new_due_date": "2026-03-15T17:00:00Z",
  "reason": "Technician unavailable due to training",
  "rescheduled_by": "Supervisor"
}
```

**Response:** Updated inspection task with new due date

### Inspection Results

#### Create Inspection Result
```http
POST /api/inspection/results
```

Submit completed inspection results.

**Request Body:**
```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174001",
  "equipment_id": "generator-001",
  "inspected_by": "John Smith",
  "overall_status": "pass",
  "item_results": [
    {
      "item_id": "gen_001",
      "status": "pass",
      "measurement_value": "Normal",
      "notes": "Oil level OK"
    },
    {
      "item_id": "gen_002",
      "status": "fail",
      "measurement_value": "Leak present",
      "notes": "Oil leak at gasket worsened",
      "photos": ["https://storage.example.com/leak.jpg"]
    }
  ],
  "measurements": {
    "oil_level": "Normal",
    "battery_voltage": 12.8
  },
  "deficiencies_found": 1,
  "critical_findings": 0,
  "general_notes": "Generator running well except for oil leak"
}
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174002",
  "task_id": "123e4567-e89b-12d3-a456-426614174001",
  "equipment_id": "generator-001",
  "inspected_by": "John Smith",
  "inspection_date": "2026-03-01T10:30:00Z",
  "overall_status": "pass",
  "item_results": [...],
  "deficiencies_found": 1,
  "critical_findings": 0,
  "created_at": "2026-03-01T10:30:00Z"
}
```

#### Get Inspection Results for Task
```http
GET /api/inspection/results/task/{task_id}
```

**Response:** Array of inspection results for the task

#### Get Inspection Results for Equipment
```http
GET /api/inspection/results/equipment/{equipment_id}
```

**Query Parameters:**
- `limit` (optional): Maximum results (default: 50, max: 200)

**Response:** Array of inspection results for equipment

### Deficiency Management

#### Create Inspection Deficiency
```http
POST /api/inspection/deficiencies
```

Log deficiency found during inspection.

**Request Body:**
```json
{
  "result_id": "123e4567-e89b-12d3-a456-426614174002",
  "task_id": "123e4567-e89b-12d3-a456-426614174001",
  "equipment_id": "generator-001",
  "deficiency_title": "Oil leak at pan gasket",
  "deficiency_description": "Oil leak has worsened from 2 drops/min to 8 drops/min",
  "severity": "major",
  "category": "mechanical",
  "recommended_action": "Replace oil pan gasket",
  "estimated_repair_cost_min": 1500.00,
  "estimated_repair_cost_max": 2500.00,
  "estimated_repair_hours": 4,
  "reported_by": "John Smith"
}
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174003",
  "result_id": "123e4567-e89b-12d3-a456-426614174002",
  "task_id": "123e4567-e89b-12d3-a456-426614174001",
  "equipment_id": "generator-001",
  "deficiency_title": "Oil leak at pan gasket",
  "deficiency_description": "Oil leak has worsened from 2 drops/min to 8 drops/min",
  "severity": "major",
  "category": "mechanical",
  "recommended_action": "Replace oil pan gasket",
  "estimated_repair_cost_min": 1500.00,
  "estimated_repair_cost_max": 2500.00,
  "estimated_repair_hours": 4,
  "is_resolved": false,
  "reported_by": "John Smith",
  "reported_date": "2026-03-01T10:30:00Z"
}
```

**Severity Levels:**
- `minor`: Minor issue, can be addressed at next scheduled maintenance
- `major`: Significant issue, requires attention within 30 days
- `critical`: Serious issue, requires immediate attention
- `safety`: Safety hazard, requires immediate action

#### List Deficiencies for Equipment
```http
GET /api/inspection/deficiencies/equipment/{equipment_id}
```

**Query Parameters:**
- `resolved` (optional): Filter by resolved status

**Response:** Array of deficiencies

#### Resolve Deficiency
```http
POST /api/inspection/deficiencies/{deficiency_id}/resolve
```

**Request Body:**
```json
{
  "resolved_by": "John Smith",
  "resolution_notes": "Oil pan gasket replaced. Leak stopped."
}
```

**Response:** Updated deficiency with resolved status

#### Escalate Deficiency
```http
POST /api/inspection/deficiencies/{deficiency_id}/escalate
```

**Request Body:**
```json
{
  "new_severity": "critical",
  "escalation_notes": "Leak rate increased to 15 drops/min. Requires immediate attention."
}
```

**Response:** Updated deficiency with new severity

#### Get Critical Unresolved Deficiencies
```http
GET /api/inspection/deficiencies/unresolved/critical
```

**Query Parameters:**
- `equipment_id` (optional): Filter by equipment

**Response:** Array of critical/safety deficiencies that are unresolved

### Summary and Statistics

#### Get Inspection Overview
```http
GET /api/inspection/summary/equipment/{equipment_id}
```

**Response:**
```json
{
  "equipment_id": "generator-001",
  "equipment_name": "Generator 001",
  "equipment_type": "generator",
  "active_schedules": 2,
  "scheduled_tasks": 3,
  "in_progress_tasks": 1,
  "overdue_tasks": 0,
  "completed_last_30_days": 4,
  "open_deficiencies": 2,
  "critical_deficiencies": 1
}
```

#### Get Inspection Statistics
```http
GET /api/inspection/statistics
```

**Query Parameters:**
- `equipment_id` (optional): Filter by equipment

**Response:**
```json
{
  "total_schedules": 15,
  "active_schedules": 12,
  "total_tasks_generated": 156,
  "tasks_by_status": {
    "scheduled": 23,
    "in_progress": 5,
    "completed": 120,
    "overdue": 3,
    "cancelled": 5
  },
  "overdue_tasks": 3,
  "completed_last_30_days": 45
}
```

#### Get Deficiency Statistics
```http
GET /api/inspection/deficiencies/statistics
```

**Query Parameters:**
- `equipment_id` (optional): Filter by equipment
- `days_back` (optional): Days back to analyze (default: 30)

**Response:**
```json
{
  "total_deficiencies": 28,
  "by_severity": {
    "minor": 12,
    "major": 10,
    "critical": 4,
    "safety": 2
  },
  "resolved": 22,
  "unresolved": 6
}
```

## Integration with Phase 44 (Asset Baseline)

### Baseline Reference Integration

During inspection scheduling and execution, the system references Phase 44 baselines:

```json
{
  "inspection_task": {
    "id": "task-001",
    "equipment_id": "chiller-001",
    "baseline_reference_id": "baseline-001",
    "item_results": [
      {
        "item_id": "ch_001",
        "status": "warning",
        "measurement_value": "8.5°C",
        "baseline_value": "7.2°C",
        "deviation_percent": 18.1
      }
    ]
  }
}
```

### Critical Elements from Baseline

Inspections automatically prioritize critical elements identified during baseline assessment:

1. **Schedule Generation**: Schedules for equipment with critical elements are marked `is_critical: true`
2. **Task Priority**: Critical equipment gets higher task priority
3. **Checklist Integration**: Critical elements appear first in checklist
4. **Automatic Deficiencies**: Failures on critical items automatically create major/critical deficiencies

## Mobile Field Usage

### Technician Workflow

```bash
# 1. Technician gets list of due inspections
curl "http://localhost:9095/api/inspection/tasks/due/days/7?assigned_to=john.smith"

# 2. Start inspection
curl -X POST http://localhost:9095/api/inspection/tasks/task-123/start \
  -d '{"started_by": "john.smith"}'

# 3. Submit results (mobile app would capture photos, measurements)
curl -X POST http://localhost:9095/api/inspection/results \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-123",
    "equipment_id": "generator-001",
    "inspected_by": "john.smith",
    "overall_status": "pass",
    "item_results": [...],
    "measurements": {"oil_level": "normal", "battery_voltage": 12.8}
  }'

# 4. System automatically creates deficiencies for failed items
#    and updates task to completed
```

## Implementation Status

✅ **Completed:**
- Database schema (6 tables + 4 views)
- Inspection scheduling engine with automatic task generation
- Inspection task management (CRUD operations)
- Results capture with deficiency auto-creation
- Deficiency tracking and escalation
- Statistics and reporting
- REST API endpoints (30+ endpoints)
- Integration with Phase 44 baselines

📋 **Integration Points:**
- SIMBIOT checklist templates
- Work order system (future enhancement)
- Email/Slack notifications for critical deficiencies (future)
- Mobile app frontend (future)

## Usage Examples

### Example 1: Monthly Inspection Cycle

```bash
# Month 1: Create schedule
curl -X POST http://localhost:9095/api/inspection/schedules \
  -d '{
    "equipment_id": "generator-001",
    "schedule_name": "Monthly Generator Inspection",
    "frequency_type": "monthly",
    "assigned_to": "john.smith",
    "created_by": "admin"
  }'

# Generate first task
curl -X POST http://localhost:9095/api/inspection/tasks/generate \
  -d 'equipment_id=generator-001'

# Month 2: Generate next task (run via cron/job scheduler)
curl -X POST http://localhost:9095/api/inspection/tasks/generate \
  -d 'equipment_id=generator-001'
```

### Example 2: Inspection with Findings

```bash
# Start inspection
curl -X POST http://localhost:9095/api/inspection/tasks/task-001/start \
  -d '{"started_by": "john.smith"}'

# Submit results with deficiency
curl -X POST http://localhost:9095/api/inspection/results \
  -d '{
    "task_id": "task-001",
    "equipment_id": "chiller-001",
    "inspected_by": "john.smith",
    "overall_status": "partial",
    "item_results": [
      {
        "item_id": "ch_003",
        "status": "fail",
        "notes": "Refrigerant leak detected",
        "photos": ["photo1.jpg"]
      }
    ],
    "deficiencies_found": 1
  }'

# Check created deficiency
curl http://localhost:9095/api/inspection/deficiencies/equipment/chiller-001

# Escalate to critical
curl -X POST http://localhost:9095/api/inspection/deficiencies/def-001/escalate \
  -d '{"new_severity": "critical", "escalation_notes": "High leak rate"}'
```

## Next Steps: Foundation for Phase 46

Phase 45 provides the foundation for Phase 46 (Repair Effectiveness & ML Feedback):

1. **Pre/Post Repair Comparisons**: Use inspection results to compare equipment condition before and after repairs
2. **Repair Validation**: Automatically validate repair effectiveness based on inspection findings
3. **ML Feedback Loop**: Feed inspection data back to ML models for continuous improvement
4. **Work Order Integration**: Link inspection deficiencies to work orders for repair tracking

## API Testing

Run the development server:
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

Access API documentation:
- Swagger UI: http://localhost:9095/docs
- Look for "inspection" tag with 30+ endpoints

Test inspection endpoints:
```bash
# List all schedules
curl http://localhost:9095/api/inspection/schedules

# Generate tasks
curl -X POST http://localhost:9095/api/inspection/tasks/generate

# Get due inspections
curl http://localhost:9095/api/inspection/tasks/due/days/7

# Get statistics
curl http://localhost:9095/api/inspection/statistics
```
