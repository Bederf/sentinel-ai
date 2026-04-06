---
title: "Bounded Autonomy System - Demo Script"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Bounded Autonomy System - Demo Script

## Overview

This demo script showcases the complete bounded autonomy system for stakeholders, demonstrating safe autonomous control with multi-level escalation and emergency handling.

**Demo Duration:** 15-20 minutes
**Participants:** 1 presenter, 2-3 observers
**Equipment Needed:** Laptop with backend/frontend running, projector

## Pre-Demo Checklist

```bash
# 1. Verify backend is running
curl http://localhost:9095/health
# Expected: {"status": "healthy"}

# 2. Verify autonomous system initialized
curl http://localhost:9095/api/autonomous/status
# Expected: enabled=true, decision_count > 0

# 3. Verify frontend is running
curl http://localhost:9096/
# Expected: Page loads, no console errors

# 4. Load test data
curl -X POST http://localhost:9095/api/autonomous/test
# Expected: Test decision executed
```

## Demo Narrative

### Part 1: System Overview (3 min)

**Talking Points:**
- SENTINEL can now operate autonomously within strict safety boundaries
- All autonomous actions validated by safety engine before execution
- Multi-level escalation system provides operator visibility and control
- Emergency stop always available (< 1 second response)
- Complete audit trail of all decisions

**Demo Action:**
1. Open dashboard to Autonomous Decision Panel
2. Show autonomous system status: ENABLED, decision_count=N, safety_score=95.2
3. Point out key metrics: active decisions, last decision time

**What to Show:**
- Real-time autonomous decision display
- Safety score gauge (green > 80%, yellow 60-80%, red < 60%)
- Decision count and last update timestamp

---

### Part 2: Normal Operations (4 min)

**Talking Points:**
- System continuously monitors equipment and makes autonomous optimizations
- Decisions are made within predefined safety boundaries
- Each decision shows rationale for transparency

**Demo Sequence:**

**Step 1: Show Decision History**
```
Navigate to: Autonomous Decision Panel → Decision History
```

**Tell the story:**
"Let me show you some of the autonomous decisions the system has made today..."

**Point out:**
- HVAC Temperature Optimization: 22.0°C → 23.5°C (energy savings)
- Lighting Brightness Adjustment: 85% → 75% (occupancy-based)
- Equipment Runtime Staggering: Avoided demand peak (cost savings)

**Show Decision Details:**
```
Click on any decision to expand and show:
- Rationale: "Temperature optimization for peak hour"
- Current value: 22.0°C
- Target value: 23.5°C
- Status: SUCCESS
- Execution time: 250ms
- Safety score: 98.5/100
```

**Key Message:**
"Every decision is validated by the safety engine and shown with complete rationale. Operators can understand why the system made each choice."

---

### Part 3: Boundary Monitoring (3 min)

**Talking Points:**
- System continuously monitors equipment against safety boundaries
- Color-coded status shows how close equipment is to safety limits
- Multiple devices monitored simultaneously

**Demo Sequence:**

**Step 1: Show Boundary Status Panel**
```
Navigate to: Autonomous Decision Panel → Boundary Status
```

**Point out devices:**
- **Green (Normal):** HVAC Unit 1 - Temperature 22.0°C, Approach 62.5% to max (safe margin)
- **Yellow (Warning):** HVAC Unit 2 - Temperature 25.2°C, Approach 78.5% to max (getting close)

**Tell the story:**
"The system is monitoring the approach percentage - how close equipment is getting to safety limits. When approach reaches different thresholds, the system escalates through several levels..."

**Show the progression:**
```
< 75%   = NORMAL (green)       - Autonomous decisions continue
75-85%  = WARNING (yellow)     - System notification logged
85-95%  = ALERT (orange)       - Email sent to operators
95-100% = CRITICAL (red)       - Slack urgent + dashboard alert
≥100%   = EMERGENCY (dark red) - Autonomous stop triggered
```

---

### Part 4: Escalation Demonstration (5-7 min)

**Setup:** Use demo_escalations.json scenarios to illustrate escalation

**Talking Points:**
- As equipment approaches limits, system escalates through 4 levels
- Each level gets progressively more urgent notifications
- Operators can acknowledge and take action at any level

**Demo Sequence:**

**Scenario: Gradual Temperature Rise**

```
Timeline narrative:
Time 0:    Temperature 22.0°C - Normal operation
Time 5:    Temperature 24.5°C - Still normal (78.6% approach)
Time 10:   Temperature 25.8°C - Level 1 Warning (82% approach)
           → System log entry created

Time 15:   Temperature 26.4°C - Level 2 Alert (87.5% approach)
           → Email sent: "Temperature Alert: HVAC Unit 1"
           → Operator receives email notification

Time 20:   Temperature 27.1°C - Level 3 Critical (95% approach)
           → Slack: "CRITICAL: Temperature escalation at Site 002"
           → Dashboard red alert appears
           → Urgent bell icon appears

Time 22:   [OPERATOR RESPONSE] Increase cooling capacity
           → Technician acknowledges escalation
           → Takes manual action to increase compressor load

Time 25:   Temperature 26.8°C - De-escalates to Level 2
           → Operator action was effective
           → Alert conditions improving
           → System continues monitoring
```

**What to Show on Screen:**
1. Escalation timeline visualization (if available)
2. Email notification sample
3. Slack message example
4. Dashboard alert with action buttons
5. De-escalation as operator intervention takes effect

**Key Message:**
"Notice how the system gives operators time to respond at each level before escalating further. The escalation path is:
- Level 1: System aware (log only)
- Level 2: Operator aware (email)
- Level 3: Urgent response (Slack + dashboard)
- Level 4: Emergency action (autonomous stop)"

---

### Part 5: Emergency Stop (3-4 min)

**Talking Points:**
- If situation becomes critical, system can automatically stop equipment
- Prevents boundary breaches and equipment damage
- Operator can also trigger manual emergency stop instantly
- Response time < 1 second

**Demo Sequence:**

**Scenario: Rapid Pressure Increase (Equipment Failure)**

```
Timeline:
Time 0:    Pressure 500 kPa - Normal
Time 1:    Pressure 800 kPa - Compressor struggling
Time 2:    Pressure 1050 kPa - Level 1 Warning (62.5% approach)
Time 2.5:  Pressure 1110 kPa - Level 2 Alert (54% approach)
           → Email alert sent

Time 3:    Pressure 1170 kPa - Level 3 Critical (45% approach)
           → Slack urgent notification
           → Dashboard critical alert

Time 3.3:  Pressure 1199 kPa - 99.9% approach to limit
           → Level 4 EMERGENCY TRIGGERED
           → Autonomous emergency stop activated

Time 3.5:  AUTONOMOUS STOP EXECUTED
           → Compressor disabled
           → Relief valve opens (mechanical fail-safe)
           → Pressure controlled by relief valve
           → Equipment safe

Time 5:    Pressure 950 kPa (decreasing)
           → Relief valve working correctly
           → Equipment safe for now

Time 10:   Pressure 600 kPa (stabilized)
           → System in safe state
           → Manual inspection required before restart
```

**What to Show:**
1. Escalation progression with timestamps
2. Emergency stop execution moment (< 1 second)
3. Safe state achieved (pressure held below max)
4. Audit log entry showing complete incident

**Show Manual Emergency Stop:**
```
Dashboard → Emergency Controls → EMERGENCY STOP button
Click the button (show confirmation dialog)
Show response time: "Emergency stop executed in 0.8 seconds"
Show equipment status: All autonomy disabled, safe state
```

**Key Message:**
"The system has multiple layers of protection:
1. Autonomous decisions are validated before execution
2. Boundaries are hard limits (not guidelines)
3. Escalation gives operators time to respond
4. Automatic emergency stop as last resort
5. Manual emergency stop always available"

---

### Part 6: Decision History & Analytics (2-3 min)

**Talking Points:**
- Every autonomous decision is logged for audit and analysis
- Helps understand system behavior and performance
- Can identify patterns and optimization opportunities

**Demo Sequence:**

**Show Decision Export:**
```
Dashboard → Decision History → Export
Click Export button → Download CSV file
Show file contains:
- Decision ID
- Device name
- Action taken (e.g., "cooling_setpoint 22.0 → 23.5")
- Status (success, blocked, failed)
- Decision rationale
- Execution time
- Safety score
- Timestamp
```

**Show Performance Metrics:**
```
Dashboard → Autonomous System → Performance Metrics

Display:
- Total decisions (last 7 days): 284
- Successful: 275 (96.83%)
- Blocked by safety: 6 (2.1%)
- Failed (device error): 2 (0.7%)
- Cancelled (operator override): 1 (0.35%)
- Average execution time: 187.5ms
- Safety score: 97.4/100
```

**Key Message:**
"The audit trail provides complete visibility into what the system is doing and why. This builds operator confidence and enables continuous improvement."

---

## Demo Troubleshooting

### Issue: Autonomous system shows "disabled"

**Solution:**
```bash
curl -X POST http://localhost:9095/api/autonomous/enable
```

### Issue: No decisions in history

**Solution:**
```bash
# Create a test decision
curl -X POST http://localhost:9095/api/autonomous/test
```

### Issue: Escalation not triggering

**Solution:**
1. Verify escalation engine initialized
2. Create boundary condition that triggers escalation
3. Check browser console for JavaScript errors

### Issue: Emergency stop button not responsive

**Solution:**
1. Refresh the dashboard
2. Check backend logs for errors
3. Verify device manager is initialized

---

## Post-Demo Discussion

**Talking Points:**

1. **Safety First Approach**
   - "Autonomy is powerful but must be bounded. Our system validates every decision against safety rules."

2. **Operator Empowerment**
   - "Operators remain in control. They can monitor, override, or stop autonomous actions instantly."

3. **Transparency & Audit**
   - "Every decision is logged with rationale and can be reviewed. This builds trust in the system."

4. **Continuous Learning**
   - "The audit trail helps us understand what works and what doesn't, enabling system improvement."

5. **Cost & Efficiency**
   - "Autonomous optimization leads to measurable energy savings and cost reduction."

6. **Reliability**
   - "Multiple layers of protection ensure equipment safety even in unexpected situations."

---

## Key Statistics to Mention

During your demo, you can mention these realistic metrics:

- **Decision Success Rate:** 96-98% (indicating safe, effective operation)
- **Average Decision Time:** 150-300ms (fast enough for real-time optimization)
- **Escalation Frequency:** 2-5 escalations per day (normal for multi-device site)
- **Emergency Stops:** 0-1 per month (rare, indicates effective prevention)
- **Energy Savings:** 8-15% from autonomous HVAC optimization
- **Cost Savings:** R50-150/day from demand management and TOU optimization

---

## Advanced Topics (Optional)

If audience wants deeper dive:

### How Safety Validation Works
```
Show the safety engine logic:
1. Get current value
2. Apply proposed change
3. Check against all safety rules
4. If any rule violated → BLOCKED
5. If all rules pass → ALLOWED
6. Device write only if ALLOWED
```

### Boundary Types
```
Temperature: 16°C min (freeze protection) to 28°C max (comfort)
Pressure: 0 min to 1200 kPa max (equipment pressure limit)
Brightness: 0% min to 90% max (prevent over-illumination)
Runtime: 5 min minimum between starts (compressor protection)
```

### Escalation Mathematics
```
Approach % = (current - min) / (max - min) * 100

Examples:
22°C in 16-28°C range = (22-16)/(28-16)*100 = 50%  (normal)
26°C in 16-28°C range = (26-16)/(28-16)*100 = 83%  (warning)
27.6°C in 16-28°C range = (27.6-16)/(28-16)*100 = 97% (critical)
28°C in 16-28°C range = (28-16)/(28-16)*100 = 100% (emergency)
```

---

## Demo Script Timing

| Part | Duration | Activity |
|------|----------|----------|
| Pre-demo checklist | 2 min | Verify systems ready |
| Part 1: Overview | 3 min | Show dashboard, explain system |
| Part 2: Normal ops | 4 min | Show decision history, explain rationale |
| Part 3: Boundaries | 3 min | Show boundary monitoring, escalation thresholds |
| Part 4: Escalation | 5-7 min | Walk through escalation scenario |
| Part 5: Emergency stop | 3-4 min | Show automatic and manual emergency stop |
| Part 6: Analytics | 2-3 min | Show decision history export and metrics |
| Q&A | 5-10 min | Answer stakeholder questions |
| **Total** | **25-35 min** | |

---

## Presentation Tips

1. **Start Simple:** Begin with normal operations before showing escalation
2. **Use Real Data:** If possible, use actual historical data from the system
3. **Emphasize Safety:** Repeatedly highlight that safety is paramount
4. **Show Audit Trail:** Build trust by showing decisions are logged and reviewable
5. **Ask Questions:** Engage the audience ("What do you think happens next?")
6. **Have Backup Plans:** Be ready to manually trigger scenarios if timing is off
7. **Celebrate Efficiency:** Point out cost and energy savings results

---

## Q&A Preparation

**Common Questions:**

**Q: What if the autonomous system makes a wrong decision?**
A: "The safety engine validates every decision before execution. If it doesn't meet safety requirements, it's blocked. Additionally, the audit trail lets us review and learn from any issues."

**Q: Can operators always override?**
A: "Yes, operators can acknowledge escalations, disable autonomous mode, or trigger emergency stop instantly at any time."

**Q: What if the system fails?**
A: "The system degrades gracefully. Safety engine continues enforcing boundaries. Manual control continues to work. Equipment reverts to operator-set values."

**Q: How does it handle unusual situations?**
A: "Escalation system gives operators time to respond. If situation exceeds thresholds, automatic emergency stop activates as last resort."

**Q: Is this real or demo?**
A: "This is a fully functional system. The demo scenarios are realistic simulations, but the architecture is production-ready."
