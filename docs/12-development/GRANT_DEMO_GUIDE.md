# SENTINEL BMS + Tridonic Demo Guide

**For:** Grant (Demo Account)  
**Date:** February 2026  
**Duration:** 4 hours real-time (simulates full 365-day building year)  
**Building:** Site-002 (Sandton Office Complex)  

---

## 🎯 Demo Overview

This demo showcases how Tridonic DALI lighting system, when integrated with SENTINEL's AI optimization engine, transforms building energy management across a full year.

**What You'll See:**
- Tridonic lights responding to occupancy, daylight, season, and weather
- HVAC coordination working alongside lighting for maximum efficiency
- AI recommendations you can approve or reject in real-time
- Annual patterns: weekdays vs weekends, seasons, holidays, day/night cycles
- Equipment faults (realistic scenarios) and how the system responds
- Estimated energy savings from each approved recommendation

---

## 📋 Prerequisites (Before Demo)

### System Requirements
- **Backend:** Running on `http://localhost:9095`
- **Frontend:** Running on `http://localhost:9096`
- **Supabase:** Local instance (API: 55321, DB: 55322)
- **Redis:** Running (optional, for performance)

### Check Backend is Ready
```bash
curl http://localhost:9095/api/health
# Should return: {"status": "ok"}
```

### Check Frontend is Ready
```bash
# Frontend should load at http://localhost:9096
# You should see the SENTINEL login page
```

---

## 🚀 Starting the Demo

### Step 1: Login as Grant

**Method A: Email Login**
- Email: `grant@grantdemo.co.za`
- No password needed (DEMO_MODE auto-accepts)

**Method B: Social Login**
- Google: `grant@grantdemo.co.za`
- Microsoft: Same email

### Step 2: Auto-Start

After login, the system automatically:
1. ✅ Detects Grant's email
2. ✅ Resets the orchestrator for fresh demo
3. ✅ Loads `grant_hvac_dali_ai_annual` scenario
4. ✅ Redirects to Digital Twin 3D view
5. ✅ **Simulation starts: Day 1 of 365**

**You should see:**
- 3D building visualization
- Equipment status indicators (green = good, yellow = warning, red = critical)
- Timeline showing "Day X/365" and current time
- Notification toast: "New recommendation available"

---

## 🏢 Building Overview: Site-002

**Location:** Sandton Office Complex (Johannesburg, South Africa)

### Equipment on Site
- **Lighting (DALI/Tridonic):** 8 zones across 3 floors
- **HVAC:** 1 chiller, 1 AHU, 6 FCU units, 3 VAV dampers
- **Power:** 1 generator, 1 UPS, 3 distribution boards
- **Monitoring:** Temperature, humidity, CO2, occupancy sensors

### Building Structure
- **L0 (Ground):** Lobby, meeting rooms, security (Zones 001-005)
- **L1 (First Floor):** Open offices, small meeting rooms (Zones 100-104)
- **L2 (Second Floor):** Executive offices, conference rooms (Zones 200-204)

---

## 📊 What Happens During the Demo

### Timeline Overview (24-Hour Cycle)

```
06:00 → Pre-cooling starts (HVAC anticipates occupancy)
         Lighting remains at 20% (security level)

08:00 → Staff arrival begins (30-50% occupancy)
         DALI automatically increases to 60-80% brightness
         HVAC setpoint: 22°C

12:00 → Peak occupancy (95%)
         Daylight at maximum → DALI daylight harvesting reduces to 20%
         HVAC setpoint: 20.5°C (optimal comfort)
         **AI generates first recommendations**

14:00 → Post-lunch lull (80% occupancy, high ambient temperature)
         AI recommends HVAC relaxation + lighting optimization
         **Grant approves/rejects recommendations**

18:00 → Staff departure (30% occupancy)
         DALI dims to 40% (security + exit lighting)
         HVAC relaxes to 23°C

22:00 → Night mode (5% occupancy)
         DALI at 20% (security only)
         HVAC at 24°C (minimal cooling)

00:00 → Building inactive
         DALI: 15% (emergency lighting)
         HVAC: Standby mode
```

### Seasonal Variations (Throughout 365 Days)

**Summer (Dec-Feb):**
- Higher ambient temperature (28-32°C)
- Longer daylight hours
- Increased DALI daylight harvesting
- Higher HVAC load (cooling priority)
- Fault probability: 1.8x higher (heat stress on equipment)

**Autumn (Mar-May):**
- Moderate temperature (18-25°C)
- Balanced day/night cycle
- Most efficient building operation
- Reduced HVAC load

**Winter (Jun-Aug):**
- Lower ambient temperature (7-18°C)
- Shorter daylight hours
- More artificial lighting needed
- HVAC load: 25-30% (minimal cooling)
- Fault probability: 0.6x lower (equipment stress reduced)

**Spring (Sep-Nov):**
- Temperature recovering (15-26°C)
- Increasing daylight
- Return to balanced operations

### Weekly Patterns

**Monday-Friday (Weekday):**
- Occupancy: 80-100%
- Monday: 100% (full staff)
- Tuesday-Thursday: 85-90%
- Friday: 70-80% (early departures)

**Saturday:**
- Occupancy: 30%
- Minimal HVAC/lighting
- Security/maintenance presence only

**Sunday:**
- Occupancy: 20%
- Skeleton crew
- Maintenance day (potential repairs)

### Special Days

**Public Holidays (South Africa):**
- New Year (Jan 1): 0% occupancy
- Human Rights Day (Mar 21): 0% occupancy
- Easter: 3 days reduced occupancy
- Worker's Day (May 1): 0% occupancy
- Youth Day (Jun 16): 0% occupancy
- National Day (Jun 24): 0% occupancy
- Heritage Day (Sep 24): 0% occupancy
- Day of Reconciliation (Dec 16): 0% occupancy
- Christmas (Dec 25): 0% occupancy
- Boxing Day (Dec 26): 0% occupancy

**School Holidays (Reduced Occupancy -25%):**
- December-January: 25 days
- March-April: 15 days (Easter period)
- June-July: 35 days (winter break)

---

## 💡 DALI (Tridonic) Lighting Responses

### Daylight Harvesting
**How it works:**
- Natural daylight calculated based on time of day and season
- Peak daylight at solar noon: 100%
- Inverse relationship: High daylight → Low artificial light needed

**In the demo, you'll see:**
- 12:00 (noon): Brightness drops to 20% (daylight sufficient)
- 14:00: Daylight fades → Brightness increases to 60%
- 16:00: Daylight drops → Brightness to 80%
- 18:00 onwards: Full artificial lighting (100%)

### Occupancy-Aware Control
**Brightness levels by occupancy:**

| Occupancy | Brightness | Use Case |
|-----------|-----------|----------|
| < 10% | 20% | Security/emergency lighting |
| 10-50% | 40-60% | Transition (arrival/departure) |
| 50-80% | 60-90% | Working conditions |
| 80%+ | 80-100% | Peak productivity |

**Smart override:**
- If occupancy is high but daylight is bright → Keep brightness low (harvesting wins)
- If occupancy is low but it's dark outside → Keep brightness at 20% (security)

### Zone-Based Control
**8 DALI zones per floor:**

**L0 (Ground):** Zones 001-005
- 001: Lobby (high visibility need)
- 002: Meeting Room A
- 003: Meeting Room B
- 004: Hallway
- 005: Security/Emergency

**L1 (First Floor):** Zones 100-104
- 100: Open office (100 desks)
- 101: Small meeting room
- 102: Executive corridor
- 103: Kitchen/Break room
- 104: File storage

**L2 (Second Floor):** Zones 200-204
- 200: Executive offices (20 desks)
- 201: Conference room
- 202: Private offices
- 203: Boardroom
- 204: Stairwell

---

## 🤖 AI Recommendations (Approval Workflow)

### How Recommendations Work

Every 2 hours of simulation, the AI analyzes:
- Current occupancy level
- Equipment status
- Season/weather
- Historical patterns

Then generates recommendations like:

**Example 1: Mid-morning Optimization**
```
Equipment: S002-FCU-101 (Zone 1, First Floor Office)
Action: Increase cooling setpoint 22°C → 23°C
Reason: Occupancy is low (35%), ambient comfortable
Expected Benefit: Save 45 kWh daily, reduce noise
Status: ⏳ PENDING YOUR APPROVAL
```

**Example 2: Daylight Harvesting**
```
Equipment: S002-DALI-200 (Zone 200, Executive Floor)
Action: Reduce brightness 100% → 25%
Reason: Peak daylight (1200h), high natural light available
Expected Benefit: Save 120 kWh daily, improve visual comfort
Status: ⏳ PENDING YOUR APPROVAL
```

**Example 3: Fault Response**
```
Equipment: S002-CHILLER-B1-001 (Basement Chiller)
Action: Increase flow rate (equipment degradation detected)
Reason: Delta-T has declined 15% - efficiency warning
Expected Benefit: Maintain reliability, prevent failure
Status: ⏳ PENDING YOUR APPROVAL
```

### Your Options

When a recommendation appears:

**✅ APPROVE**
- AI executes the change immediately
- Equipment responds in real-time
- Savings tracked and displayed
- Feedback collected for AI learning

**❌ REJECT**
- AI learns your preference
- No change applied
- Recommendation logged for future reference
- After 3+ rejections, AI stops suggesting this type

**⏱ DEFER**
- Skip this recommendation
- Re-evaluate in next cycle (2 hours)
- Useful if you want to see consequences first

### Real-Time Updates

**Dashboard shows:**
- Number of pending recommendations
- Equipment status (before/after approval)
- Estimated savings (kWh, cost, CO2)
- Timeline of your decisions

---

## 🔧 What Happens When Equipment Fails

### Realistic Fault Scenarios

During the 365-day simulation, equipment failures occur randomly based on season:

**Summer (High Stress):**
- Generator load shedding failures
- HVAC compressor degradation
- UPS battery strain
- DALI controller overheating

**Winter (Lower Stress):**
- Fewer faults overall
- Mainly aging-related issues

### When Equipment Fails

**Timeline:**
1. Equipment health drops below 50%
2. System generates alert (< 1 second)
3. Work order auto-created
4. Technician assigned based on specialty
5. Service completed (simulated repair)
6. Feedback collected (photos, readings)
7. Equipment health restored
8. Dashboard updates (green ✓)

**You'll see in the demo:**
- Equipment icon turns yellow (warning)
- Toast notification: "S002-CHILLER-B1-001 needs attention"
- Work order appears in dashboard
- Technician name shown (e.g., "John Smith - HVAC Specialist")
- Option to view work order details
- Equipment returns to green after repair (2 hours later)

---

## 📈 Performance Metrics You'll See

### Energy Savings
**Tracked per recommendation:**
- kWh saved daily
- Cost saved (R/ZAR per unit)
- CO2 reduction (kg equivalent)

**Example:**
```
Your Approvals Today (Day 47):
- 6 recommendations approved
- Total daily savings: 2,840 kWh
- Cost savings: R 2,980/day
- CO2 reduction: 850 kg/day
- Year-to-date total: 845,000 kWh saved
```

### Equipment Health Tracking
**Shows per equipment:**
- Current health percentage (0-100%)
- Trend (improving/declining)
- Remaining useful life estimate
- Last service date

### AI Model Performance
**Background metrics (not shown but running):**
- Prediction accuracy improving over time
- Recommendation acceptance rate
- Equipment failure prevention rate
- Cost optimization effectiveness

---

## 🎮 Interactive Elements

### Digital Twin 3D View
**Click on equipment to:**
- See detailed status
- View sensor readings
- Check maintenance history
- Approve/reject recommendations for that equipment

### Timeline Scrubber
**Drag to jump forward/backward:**
- Fast-forward to interesting times (noon, evening, holidays)
- Review past recommendations
- See seasonal transitions

### Recommendation Toast
**Pops up when new recommendations available:**
- Click to open approval dialog
- Dismiss to ignore for now
- Auto-refreshes every 30 seconds

### Approval Dialog
**Interactive form:**
- Equipment name and code
- Current value vs. Target value
- Reason for recommendation
- Estimated benefit breakdown
- "Approve" and "Reject" buttons
- Optional notes field

---

## 📱 Demo Flow (Suggested)

### Phase 1: Introduction (15 min)
1. Log in as grant@grantdemo.co.za
2. Show Digital Twin 3D building
3. Explain equipment layout (zones, HVAC, lighting)
4. Point out timeline: "Day 1 of 365"

### Phase 2: Occupancy & Lighting (30 min)
1. Fast-forward to 08:00 (staff arrival)
   - Show occupancy increasing from 10% → 50%
   - DALI brightness increasing 20% → 60%
2. Fast-forward to 12:00 (peak + daylight)
   - Occupancy at 95%
   - Daylight at maximum
   - DALI harvesting kicks in: brightness drops to 20%
   - Show natural vs. artificial light balance

### Phase 3: AI Recommendations (45 min)
1. Approve first recommendation (DALI optimization)
2. Show energy savings in real-time
3. Reject a recommendation (show learning)
4. Approve another (HVAC setpoint)
5. Explain cross-system coordination

### Phase 4: Seasonal Transitions (30 min)
1. Fast-forward to Day 90 (Autumn)
2. Show temperature changes
3. Show occupancy patterns (weekday vs. weekend)
4. Fast-forward to Day 180 (Winter)
   - Shorter daylight → More artificial lighting
   - Lower ambient temperature → Less HVAC load
5. Fast-forward to Day 270 (Spring)

### Phase 5: Holiday & Weekend Patterns (20 min)
1. Navigate to Day 174 (Easter holiday)
   - Show occupancy drop (25%)
   - Show lighting reduction
2. Navigate to a weekend (e.g., Day 50 - Saturday)
   - Show minimal operations (30% occupancy)
3. Show how building adapts automatically

### Phase 6: Fault Handling (20 min)
1. If a fault hasn't occurred yet, wait for one
2. When equipment fails:
   - Show yellow warning indicator
   - Show alert notification
   - Open work order details
   - Show technician assignment
   - Wait for repair completion
3. Explain: "System handles faults automatically without your intervention"

### Phase 7: Year Summary (10 min)
1. Fast-forward to Day 365 (End of year)
2. Show annual statistics:
   - Total recommendations: 1,847
   - You approved: 1,400+ (76%)
   - Total energy saved: 820,000 kWh
   - Annual cost savings: R 900,000+
   - CO2 reduction: 250 tons
3. Explain value proposition:
   - "Your Tridonic system + BMS integration + AI = This level of optimization"
   - "Without AI: Standard HVAC + Fixed lighting schedules = 5-10% savings"
   - "With SENTINEL: Smart recommendations = 15-20% savings"

---

## ⚠️ What to Expect (Common Demo Events)

### Toast Notifications
You'll see notifications appear regularly:
- "New recommendation available" (green)
- "Equipment warning: S002-FCU-101 cooling efficiency declining" (yellow)
- "Work order completed: S002-CHILLER-B1-001" (blue)
- "Recommendation rejected: Learning from your decision" (info)

### Simulation Speed
- Normal speed: 365 days in 4 hours real-time
- 1 minute real-time = ~90 minutes simulated time
- This creates a balance between seeing the full year and having time to interact

### Data Updates
- Equipment status updates every 15 minutes (simulated)
- Recommendations generated every 2 hours (simulated)
- Faults occur randomly throughout the year

---

## 🔐 Security Note

**Demo Mode Features:**
- ✅ No password required (pre-authenticated as Grant)
- ✅ Safe to show to clients
- ✅ No real data exposed
- ✅ Simulation-only (no actual device control)
- ✅ Resets when Grant logs out

**After Demo:**
- Log out to stop simulation
- Next login resets to Day 1
- All demo data cleared

---

## 📞 Troubleshooting

### Issue: Simulation not starting
**Solution:**
1. Check backend logs: `tail -f backend/logs/*.log`
2. Verify `grant_hvac_dali_ai_annual` scenario exists
3. Clear browser cache and reload

### Issue: No recommendations appearing
**Solution:**
1. Wait 2+ hours of simulation (recommendations every 2 hours)
2. Check browser console for errors
3. Verify Redis is running (if using caching)

### Issue: 3D Digital Twin not loading
**Solution:**
1. Check frontend build: `npm run build`
2. Verify WebGL is enabled in browser
3. Try Firefox/Chrome (Safari has WebGL issues)

### Issue: Recommendations not executing
**Solution:**
1. Verify backend device_manager is initialized
2. Check device IDs match equipment codes
3. Review backend logs for execution errors

### Issue: Simulation running too fast/slow
**Solution:**
- Check backend CPU load
- Verify no other simulations running
- Adjust time compression in orchestrator settings

---

## 📊 Key Takeaways for Grant

**Value Proposition:**
1. **Tridonic lighting system** provides lighting control
2. **SENTINEL's BMS integration** connects lighting to HVAC and building data
3. **AI optimization layer** makes coordinated recommendations
4. **Your approval workflow** maintains human oversight
5. **Result:** 15-20% annual energy savings + improved comfort + predictive maintenance

**Use Cases:**
- Real-time occupancy response (people arriving/leaving)
- Daylight harvesting (reducing artificial lighting when sun is bright)
- Seasonal adjustments (automatic winter/summer mode)
- Fault detection (catching issues before they cause failures)
- Data-driven decisions (see exactly how much each change saves)

**Lighting Integration Role:**
- Install Tridonic DALI controllers (64 channels/controller)
- Network to building BMS via your integration
- SENTINEL handles the intelligence layer
- You get control and visibility over everything

---

## 👤 Demo Contact

**Questions during demo?**
- Ask about specific equipment or time period
- Request to jump to particular dates
- Ask about how specific recommendations work
- Check work order details or technician assignments

**After demo?**
- Review energy savings estimates
- Discuss integration timeline
- Discuss pilot project scope
- Plan installation at customer sites

---

**Ready to start? Log in as: `grant@grantdemo.co.za`**

Let the simulation begin! 🚀
