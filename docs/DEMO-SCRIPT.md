# BMS Intelligence Demo Script

**Target Audience:** Bidvest FM CTO / Technical Leadership
**Duration:** 10 minutes
**Goal:** Impress with AI-powered predictive maintenance capabilities
**Date:** 2026-01-24

---

## Setup (5 min before interview)

### 1. Start Services
```bash
# Terminal 1 - Backend API
cd /opt/bms-intelligence
./start-backend.sh

# Terminal 2 - Frontend
cd /opt/bms-intelligence
./start-frontend.sh
```

### 2. Verify Health
```bash
# Backend health
curl http://localhost:9095/api/health

# Frontend accessible
open http://localhost:9096
```

### 3. Set Demo Mode
```bash
# Verify DEMO_MODE is enabled
grep DEMO_MODE backend/.env
# Should show: DEMO_MODE=true
```

### 4. Browser Setup
- Clear browser cache (Cmd+Shift+Delete / Ctrl+Shift+Delete)
- Open fresh browser window
- Navigate to http://localhost:9096
- Set to full screen (Cmd+F11 / F11)
- Open DevTools for network monitoring (optional, shows SSE streaming)

---

## Demo Flow (10 minutes)

### Opening - The Problem (1 minute)

**Show:** Dashboard with 5 at-risk assets, R185K potential savings

**Script:**
> "Facilities managers face a critical challenge: knowing WHICH equipment will fail before it does. Traditional BMS systems tell you WHEN something fails. Our AI tells you WHAT WILL fail."

**Actions:**
1. Scroll to predictions section
2. Highlight Gateway Chiller at 95% probability
3. Point out R185K total potential savings

**Key Numbers:**
- 15 FNB sites monitored
- 130 equipment items tracked
- 5 current at-risk assets
- R185K total potential savings

---

### Hero Feature - AI Prediction (3 minutes)

**Question 1:** "What's the status of Gateway Chiller?"

**Expected:** Shows PredictionDetail with 95% probability, contributing factors

**Script:**
> "Gateway Chiller has a 95% chance of compressor failure within 2-4 weeks. Notice the explainability - the AI shows WHY. Three repeat work orders, technician notes about bearing wear, asset exceeds expected life. This isn't a black box - we show the evidence."

**Actions:**
1. Click on Gateway Chiller prediction card
2. Show probability circle (95%)
3. Scroll through contributing factors
4. Highlight evidence (work orders, technician notes, asset age)
5. Point out confidence badge (HIGH)

**Demo Cache Response:**
- Triggered by: "Gateway Chiller status", "What's the status", "Gateway Chiller"
- Returns: Verified response with explainability breakdown

---

### Cost Impact - ROI Story (2 minutes)

**Question 2:** "What's the cost impact?"

**Expected:** Shows cost breakdown - R65K failure vs R28K prevention = R37K savings

**Script:**
> "The ROI is compelling. Emergency failure: R65K. Scheduled maintenance: R28K. We save R37K and prevent disruption during mall hours. This makes the business case clear - act now, not when it fails."

**Actions:**
1. Scroll to Cost Impact Analysis section
2. Show CostCard (compact view)
3. Click "View detailed breakdown"
4. Show CostBreakdownDetail (parts, labor, downtime, secondary damage)
5. Toggle back to compact view

**Demo Cache Response:**
- Triggered by: "cost impact", "Gateway cost", "savings"
- Returns: Detailed ROI breakdown with specific numbers

---

### Cross-Site Patterns - AI Learning (2 minutes)

**Question 3:** "Show me similar failures"

**Expected:** Shows Centurion Mall AHU that failed, Gateway AHU at risk

**Script:**
> "Here's where AI gets powerful. Gateway Chiller's pattern matches failures at three other sites. Centurion Mall's AHU failed with this same vibration pattern after 175 days. Gateway AHU-005 shows the same early warning. Our AI learns from portfolio-wide data to predict failures across all sites."

**Actions:**
1. Scroll to Cross-Site Pattern Detected section
2. Show similar failures list
3. Highlight common factors (vibration, bearing wear, age)
4. Point out pattern recognition insight callout

**Demo Cache Response:**
- Triggered by: "similar failures", "cross-site", "pattern"
- Returns: Cross-site pattern recognition with evidence

---

### Chat - Natural Language (2 minutes)

**Question 4:** "Create a work order for Gateway AHU-005"

**Expected:** Work order created, confirmation shown

**Script:**
> "Users interact naturally. No hunting through menus. Just tell the AI what you need. It creates work orders, queries data, controls systems - all through conversation."

**Actions:**
1. Click Chat in sidebar
2. Type: "Create a work order for Gateway AHU-005"
3. Show streaming response (SSE in real-time)
4. Point out natural language understanding
5. Mention help menu with example queries

**Demo Cache Response:**
- Triggered by: "work order", "create", "schedule"
- Returns: Work order creation guidance with steps

**Bonus Question:** "What's the portfolio overview?"

**Expected:** Summary of all 15 sites, 130 equipment, 5 predictions

**Demo Cache Response:**
- Triggered by: "portfolio", "overview", "summary"
- Returns: Portfolio-wide statistics

---

## Fallback Options

### If chat is slow:
- Use PredictionDetail modal (shows same data)
- Switch to Dashboard overview
- Click through prediction cards directly

### If prediction doesn't load:
- Refresh page (Cmd+R / F5)
- Try different prediction (Rosebank UPS)
- Check backend health: `curl http://localhost:9095/api/health`

### If cost analysis doesn't show:
- Check DEMO_MODE=true in backend/.env
- Try cached query: "cost impact Gateway"
- Use PredictionDetail modal directly

### If SSE streaming freezes:
- Check browser console for errors
- Verify backend running: `ps aux | grep python`
- Restart backend: Ctrl+C in Terminal 1, then `./start-backend.sh`

---

## Key Numbers to Reference

### Portfolio Scale
- **15 FNB sites** across Gauteng, Western Cape, KZN
- **130 equipment items** (HVAC chillers, AHUs, UPS, generators)
- **5 current at-risk assets** with active predictions
- **R185K total potential savings** if all preventive actions taken

### Hero Prediction (Gateway Chiller)
- **95% failure probability** within 2-4 weeks
- **R37K savings** (R65K failure → R28K prevention)
- **3 contributing factors**: repeat work orders (35%), technician notes (30%), asset age (20%)
- **Cross-site pattern**: matches failures at 3 other sites

### AI Capabilities
- **8 pre-seeded demo responses** for consistent demo experience
- **Explainability**: Every prediction includes evidence and citations
- **Cross-site learning**: Patterns detected across portfolio
- **Natural language**: Chat interface for all interactions

---

## Environment Checklist

### Pre-Demo Verification
- [ ] Backend running on :9095
- [ ] Frontend running on :9096
- [ ] DEMO_MODE=true set in backend/.env
- [ ] Browser cache cleared
- [ ] Full screen mode ready
- [ ] Demo script printed for reference

### Health Checks
```bash
# Backend health
curl http://localhost:9095/api/health
# Expected: {"status": "ok", "demo_mode": true}

# Chat status
curl http://localhost:9095/api/chat/status
# Expected: {"status": "ready", "demo_mode": true}

# Predictions endpoint
curl http://localhost:9095/api/predictions | jq '.predictions | length'
# Expected: 5
```

---

## Demo Questions & Expected Responses

### 1. Gateway Chiller Status
**Queries:**
- "What's the status of Gateway Chiller?"
- "Gateway Chiller status"
- "Tell me about Gateway Chiller"

**Response:**
- 95% compressor failure probability
- 3 contributing factors with weights
- Cross-site pattern matches
- Cost impact analysis

### 2. Cost Impact Analysis
**Queries:**
- "What's the cost impact?"
- "Gateway cost impact"
- "Show me the savings"

**Response:**
- R65K failure vs R28K prevention
- R37K potential savings
- Detailed breakdown (parts, labor, downtime)

### 3. Similar Failures / Cross-Site Patterns
**Queries:**
- "Show me similar failures"
- "Cross-site patterns"
- "What patterns did you find?"

**Response:**
- 3 similar failures at other sites
- Common factors (vibration, bearing wear, age)
- Pattern recognition insights

### 4. Work Order Creation
**Queries:**
- "Create a work order for Gateway AHU-005"
- "Schedule maintenance for Gateway Chiller"
- "I need to create a work order"

**Response:**
- Work order creation steps
- Recommended urgency
- Parts required

### 5. Portfolio Overview
**Queries:**
- "What's the portfolio overview?"
- "Show me all sites"
- "Portfolio summary"

**Response:**
- 15 sites across 3 provinces
- 130 equipment items
- 5 active predictions
- R185K total savings

---

## Post-Demo Discussion Points

### Technical Architecture
- **Frontend:** React 18 + Tremor UI components
- **Backend:** FastAPI with SSE streaming
- **AI:** Claude Sonnet 4 with RAG pipeline
- **Demo Cache:** 8 verified responses for reliability
- **Responsive Design:** Mobile, tablet, desktop breakpoints

### Differentiation vs Huawei
- **Explainability:** We show WHY, not just WHAT
- **Cross-Site Learning:** Portfolio-wide pattern recognition
- **Natural Language:** Chat interface, no complex menus
- **ROI Focus:** Cost impact analysis for every prediction
- **Proactive:** Predict failures before they happen

### Next Steps
- **Data Integration:** Connect to real CAFM/BMS systems
- **Historical Analysis:** Learn from past work orders
- **Real-Time Alerts:** Push notifications for critical predictions
- **Mobile App:** On-site technician access
- **Multi-Site Rollout:** Scale to all FNB sites

---

## Troubleshooting

### Backend Won't Start
```bash
# Check port conflicts
lsof -i :9095
# Kill existing process
kill -9 <PID>
# Restart backend
./start-backend.sh
```

### Frontend Won't Load
```bash
# Check port conflicts
lsof -i :9096
# Clear node_modules and reinstall
cd frontend
rm -rf node_modules
npm install
# Restart frontend
cd ..
./start-frontend.sh
```

### Demo Mode Not Working
```bash
# Check .env file
cat backend/.env | grep DEMO_MODE
# Should show: DEMO_MODE=true
# If missing, add it:
echo "DEMO_MODE=true" >> backend/.env
# Restart backend
```

### Chat Responses Slow/Empty
```bash
# Check demo cache file exists
ls -la backend/app/data/demo_responses.json
# Check API key (optional, for non-demo queries)
cat backend/.env | grep ANTHROPIC_API_KEY
# Verify backend logs
tail -f logs/backend.log
```

---

## Success Criteria

✅ **Demo flows smoothly** - No awkward pauses or errors
✅ **All responses verified** - Pre-seeded cache works consistently
✅ **Mobile responsive** - UI works on all breakpoints
✅ **Interview ready** - Clear narrative, compelling story
✅ **Technical depth** - Can answer architecture questions

---

## Contact

**Demo Issues:** Check logs in `/opt/bms-intelligence/logs/`
**Technical Questions:** Review architecture docs in `/opt/bms-intelligence/docs/`
**Feature Requests:** Document in `/opt/bms-intelligence/.planning/`

**Good luck with the Bidvest FM interview!** 🚀
