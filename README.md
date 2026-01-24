# BMS Intelligence Platform

An AI-powered facilities management demo for Bidvest FM interviews. Showcases intelligent building analytics, predictive maintenance, and conversational AI across simulated multi-site operations.

## Quick Start

```bash
# Backend (FastAPI + Python)
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9097

# Frontend (React + Vite)
cd frontend
npm install
npm run dev
```

**URLs:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:9097
- API Docs: http://localhost:9097/docs

## Features

### AI Chat Interface
Natural language queries for building data:
- "Why is Gateway Theatre's chiller vibration increasing?"
- "Which assets are approaching end of life?"
- "Show me the failure progression for AHU-002"

### Predictive Maintenance
Real-time telemetry analysis with failure prediction:
- Vibration trending and bearing wear detection
- Oil analysis correlation with mechanical failures
- Battery degradation monitoring for generators
- Motor current draw analysis for HVAC equipment

### Multi-Site Dashboard
Portfolio overview with drill-down capabilities:
- 10 South African commercial sites
- Work order tracking and SLA monitoring
- Energy consumption and cost analysis
- Asset lifecycle management

## Data Sources (10 Total)

| Source | Records | Description |
|--------|---------|-------------|
| Work Orders | 29 | CAFM maintenance history with costs, SLA, technician notes |
| Assets | 19 | Equipment register with lifecycle, criticality, condition |
| Sites | 10 | Commercial buildings with contracts, BMS types |
| Alarms | 20 | BCC alarm history with severity and resolution |
| Energy | 25 | Utility consumption (electricity, water, diesel) |
| Generator Telemetry | 41 | DeepSea DSE7320/8610 controller data |
| HVAC Telemetry | 16 | BACnet AHU/chiller readings |
| VSD Telemetry | 16 | Danfoss/ABB/Schneider drive data |
| Chiller Telemetry | 11 | York/Carrier/Trane with oil analysis |
| Pump Telemetry | 15 | Grundfos/KSB CHW/CW pump data |

## Key Stories in the Data

### 1. Centurion Mall AHU-002 - Catastrophic Failure (May 2025)
- 8 work orders over 14 months showing bearing degradation
- Technician warned 4 times, quote sat unapproved 8 months
- Final cost: R63,300 + R150,000 lost revenue
- **Lesson:** Early warnings ignored = catastrophic outcome

### 2. Gateway Theatre Chiller - Active Risk (Same Pattern)
- Vibration trending: 2.8 → 3.8 → 4.2 → 4.6 → 5.2 mm/s
- Oil analysis: NORMAL → ELEVATED (28ppm iron vs <15ppm normal)
- R45,000 quote pending vs R180,000+ if failure
- **AI Confidence:** 95% failure within 4-8 weeks

### 3. Centurion Generator - Battery Failure (Sept 2025)
- Battery voltage degraded: 27.2V → 26.8V → 26.1V → 25.4V
- Charger current dropped: 2.1A → 1.8A (9 months)
- Result: Overcrank shutdown during power outage
- **AI Detection:** Voltage <26V baseline = 85% failure probability

### 4. Mediclinic Hospital - Near Miss (March 2025)
- Generator started on 3rd attempt at 25.2V
- Hospital on UPS for 12 minutes during Eskom outage
- ICU, theatres, pharmacy all on battery backup
- **Outcome:** Emergency battery replacement within 7 days

### 5. Sandton City CHW Pump - Emerging Issue
- Vibration trending: 2.2 → 2.5 → 3.2 → 3.5 mm/s
- Bearing temp rising: 48 → 52 → 56 → 58°C
- Seal status: NONE → TRACE leakage
- **AI Confidence:** 75% bearing failure within 6 months

## Tech Stack

- **Backend:** FastAPI + Python 3.11
- **Frontend:** React 18 + TypeScript + Vite
- **UI Components:** Tremor (charts), Tailwind CSS
- **AI:** Claude API (Anthropic)
- **Data:** CSV files with realistic FM patterns

## Project Structure

```
bms-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   │   ├── chat.py    # AI chat endpoint
│   │   │   └── upload.py  # CSV upload endpoints
│   │   ├── services/
│   │   │   └── csv_loader.py  # Data loading with analysis methods
│   │   └── data/          # CSV data files
│   │       ├── work_orders.csv
│   │       ├── assets.csv
│   │       ├── sites.csv
│   │       ├── alarms.csv
│   │       ├── energy_readings.csv
│   │       ├── generator_telemetry.csv
│   │       ├── hvac_telemetry.csv
│   │       ├── vsd_telemetry.csv
│   │       ├── chiller_telemetry.csv
│   │       └── pump_telemetry.csv
│   └── venv/
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Sidebar.tsx    # Navigation + data upload
│       │   ├── Dashboard.tsx  # KPI cards + charts
│       │   └── Chat.tsx       # AI chat interface
│       └── App.tsx
├── .planning/             # GSD planning docs
└── README.md
```

## API Endpoints

### Data Upload
```
POST /api/upload/{file_type}  # Upload CSV (work_orders, assets, sites, etc.)
GET  /api/data-status         # Get current data counts
POST /api/reload-data         # Force reload all CSV files
GET  /api/download/{file_type} # Download CSV file
```

### Chat
```
POST /api/chat  # Send message to AI with building context
```

## Data Classes

Each data source has a dedicated class in `csv_loader.py` with:
- `load()` - Load and cache data from CSV
- `get_by_asset(asset_id)` - Filter by asset
- `get_by_site(site_id)` - Filter by site
- Specialized analysis methods (e.g., `get_vibration_events()`, `get_battery_trend()`)

### AI Context Summary
The `get_ai_context_summary()` function generates a comprehensive summary of all data for Claude, including:
- Portfolio overview with counts and totals
- Assets requiring attention (poor condition, end of life)
- Key failure stories with timeline and costs
- Telemetry insights with predictive indicators

## Environment Variables

```bash
# Backend (.env)
ANTHROPIC_API_KEY=sk-ant-...
```

## Development

### Adding a New Data Source

1. Create CSV file in `backend/app/data/`
2. Add data class in `csv_loader.py` following existing patterns
3. Update imports in `upload.py`
4. Add to `ALLOWED_FILES` dict
5. Update `reload_all_data()` function
6. Add upload option in `Sidebar.tsx`
7. Add insights to `get_ai_context_summary()`

### Testing Data Loading

```python
cd backend
source venv/bin/activate
python -c "
from app.services.csv_loader import *
print(f'Work Orders: {len(WorkOrderData.load())}')
print(f'Generator Telemetry: {len(GeneratorTelemetryData.load())}')
print(f'Pump Telemetry: {len(PumpTelemetryData.load())}')
"
```

## Demo Script

### Opening
"Traditional BMS tells you *what's happening*. Our AI tells you *why it's happening* and *what to do about it*."

### Key Demo Moments

1. **Natural Language Query**
   - "Why is Gateway's chiller showing elevated vibration?"
   - AI responds with trend, oil analysis correlation, and recommendation

2. **Predictive Maintenance**
   - Show Centurion AHU-002 failure chain
   - Demonstrate how AI would have detected it 8 months earlier

3. **Interactive**
   - "What would you like to ask about the buildings?"
   - Let interviewer explore with their own questions

### Closing
"In 6 months, every FM team will expect this. The question is whether Bidvest leads or follows."

## License

Demo project for interview purposes.
