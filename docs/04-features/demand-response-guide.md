---
title: "Demand Response: Smart Building Power Reduction"
type: "guide"
status: "active"
version: "1.0.0"
created: "2026-05-18"
updated: "2026-05-18"
tags: ["demand-response", "load-shedding", "energy", "bess", "ddmp"]
domain: "operations"
audience: "fm", "operations", "executive"
complexity: "beginner"
estimated_read_time: 8
---

# Demand Response: Smart Building Power Reduction

**What it does:** Automatically calculates exactly how much air conditioning your building can safely turn off to help the power grid — without making people uncomfortable.

---

## The Simple Explanation

When the power grid is stressed (like during Eskom load shedding), buildings can help by **temporarily reducing power**. But you can't just randomly turn off air conditioners — that would make people hot and unhappy.

**Our system figures out the safe answer automatically:**
- ✅ How much power can be reduced (in kilowatts)
- ✅ How long it can stay reduced (in minutes)
- ✅ Which specific areas can be reduced
- ✅ How confident we are in the answer
- ✅ Whether the building qualifies for Eskom payments

---

## Real-World Example

### Scenario: Hot Summer Afternoon + Load Shedding

**Your building:**
- 5 floors, 200 employees
- Server room (critical — can't get hot)
- Executive offices (important)
- Open offices, lobby, parking (can tolerate some warming)
- Battery backup system (BESS)

**The Grid Needs Help:**
- Eskom announces Stage 2 load shedding
- Grid operators need 500 kW reduced across the area
- They ask your building to help

**What Our System Does:**

1. **Checks current conditions:**
   - Outside temperature: 32°C
   - Inside temperature: 22.4°C
   - Building can tolerate 26°C comfortably
   - Battery is 78% charged

2. **Calculates safe reduction:**
   ```
   Safe to reduce: 142 kW of air conditioning
   Safe duration: 95 minutes
   Confidence: 82%
   Limiting factor: Building thermal mass (heats up slowly)
   ```

3. **Identifies which zones:**
   - ✅ **Parking** — can reduce fully (not occupied)
   - ✅ **Lobby** — can reduce 50% (brief discomfort OK)
   - ✅ **Open offices** — can reduce 30% (fans still work)
   - ❌ **Server room** — NEVER reduce (priority P1)
   - ❌ **Executive floor** — NEVER reduce (priority P2)

4. **Checks battery backup:**
   - Battery can sustain critical loads for 95+ minutes
   - Safe to participate in demand response

**Result:**
- Building reduces 142 kW safely
- Grid stress reduced
- Nobody complains about heat
- Servers stay cool
- Building earns Eskom DDMP credits (if eligible)

---

## Key Concepts Explained

### What is "Curtailable Load"?

Think of it like a **dimmer switch for your building's air conditioning**.

- **Total building power:** 500 kW
- **Curtailable load:** 142 kW (28% can be safely reduced)
- **Why only 142 kW?** Because the rest is needed to keep people comfortable and servers running

### Zone Priorities (P1-P5)

Not all rooms are equal. We use a priority system:

| Priority | Areas | Can We Reduce AC? |
|----------|-------|-------------------|
| **P1** | Server rooms, data centers | ❌ NEVER |
| **P2** | Executive offices, banking halls | ⚠️ Only 50% |
| **P3** | Standard offices, meeting rooms | ✅ Yes, full reduction |
| **P4** | Lobbies, restrooms | ✅ Yes, full reduction |
| **P5** | Parking, plant rooms, storage | ✅ Yes, full reduction |

### Thermal Runway

This is like a **countdown timer** for comfort.

- If you turn off AC, how long until the building gets uncomfortably warm?
- **Example:** "95 minutes until we hit 26°C"
- This gives grid operators confidence: "We have 95 minutes to fix the grid before we need to turn the AC back on"

### Confidence Score

We never claim 100% certainty. The confidence score (0.0 to 0.95) tells you:

- **0.95 (95%):** Very confident — fresh data, all sensors working
- **0.82 (82%):** Confident — good data, minor gaps
- **0.50 (50%):** Cautious — some stale data or missing sensors
- **Below 0.50:** We won't recommend action — data quality too low

### Limiting Factors

What's stopping us from reducing more power?

| Factor | What It Means |
|--------|---------------|
| **chiller_thermal_mass** | Building heats up slowly — we have limited time |
| **comfort_boundary** | Some rooms are already at the warm limit |
| **bess_low_soc** | Battery is low — can't sustain backup power |
| **zone_temperature_limit** | Specific zones are near temperature limits |
| **thermal_runway_short** | Less than 1 hour of safe curtailment available |
| **none** | No major limits — good to go! |

---

## Who Uses This Information?

### 1. Building Owners/Facilities Managers

**Why:** Know exactly how much you can help the grid without complaints

**Example:**
> "The system says we can reduce 142 kW for 95 minutes safely. That qualifies us for Eskom's demand response payments while keeping employees comfortable."

### 2. BESS/Battery Companies (like IES)

**Why:** Know exactly how long batteries can support the building during load shedding

**Example:**
> "The building can sustain 95 minutes of HVAC curtailment. With the battery at 78%, we have plenty of buffer for safe discharge."

### 3. Demand Response Aggregators (like LTM Energy)

**Why:** Bid accurately into Eskom's DDMP (Distribution Demand Management Programme)

**Example:**
> "Site-002 can deliver 142 kW for 95 minutes with 82% confidence. Combined with Buildings B (92 kW) and C (78 kW), we hit 312 kW — well above the 200 kW DDMP minimum."

### 4. Grid Operators

**Why:** Know exactly which buildings can help during emergencies

**Example:**
> "We need 10 MW reduced immediately. These 50 buildings can safely deliver 12 MW combined."

---

## DDMP Eligibility (Eskom Payments)

**What is DDMP?**
Eskom's **Distribution Demand Management Programme (DDMP)** pays project developers to reduce power during evening peak periods. It follows a **performance contracting** model: you implement the project, Eskom verifies savings, then pays quarterly over 24 months.

**Reference:** [Eskom DDMP Official Page](https://www.eskom.co.za/distribution/demand-management-programme/)

### Programme Stream 1: Industrial/Commercial Load Management (What We Built For)

**This is the programme that matters for BESS controllers and commercial buildings.**

**Minimum Requirements:**
- Can reduce at least **200 kW** (0.2 MW) of load
- Can sustain reduction through Eskom's evening peak period
- Have backup power (BESS) at least **20% charged**

**Aggregation Allowed:**
Up to **4 sites** (same entity) can be combined to meet the 200 kW minimum.

**Incentive:**
- **R3 Million per MW** of achieved reduction
- Paid quarterly over **24-month sustainability period**

**Timeline:**
- **6 months** to implement from approval
- 24 months of performance verification

**Important:** Does NOT grant exemption from load shedding

---

### Programme Stream 2: Residential Load Management
- **Minimum:** 1 MW (hot water load control)
- **Geographic:** Single metro/municipality only
- **Timeline:** 12 months to implement

### Programme Stream 3: Energy Efficiency Programme
- **Minimum:** 50 kW average demand reduction (06:00-20:00 weekdays)
- **Minimum:** 45,500 kWh saved per quarter
- **Sites:** Up to 30 sites (same entity)
- **Rate:** 41.029 cents/kWh

---

**Example: Project Developer Portfolio**

LTM Energy aggregates 3 office buildings using our API:

```
Building A (Sandton Office Park):     85 kW curtailable ← our endpoint
Building B (Rosebank Towers):         92 kW curtailable ← our endpoint
Building C (Midrand Hub):             78 kW curtailable ← our endpoint
                                     ----
Portfolio Total:                     255 kW ✅

Exceeds 200 kW minimum?              YES
Sites aggregated:                     3 (max 4)
DDMP Eligible:                       ✅ YES
Incentive:                           0.255 MW × R3M = R765,000
Payment Schedule:                    Quarterly for 24 months
Implementation Period:               6 months
Sustainability Period:               24 months verified performance
```

**How SENTINEL Helps:**
1. **Pre-project:** Our API measures each building's actual curtailment potential
2. **Proposal:** Project developers use our data to prove to Eskom the savings are real
3. **Implementation:** SENTINEL endpoint tells each building exactly how much to reduce
4. **Verification:** Our data feeds independent M&V (Measurement & Verification)
5. **Payment:** Eskom pays based on verified savings

---

## Safety Features

### Data Freshness Guard

If our sensor data is older than **5 minutes**, we refuse to answer.

**Why?** Making decisions on stale data is dangerous. We'd rather say "I don't know" than give bad advice.

**What happens:**
- HTTP 503 error: "Insufficient live sensor data"
- Grid operators know to use conservative estimates
- Building safety is protected

### Zone-by-Zone Protection

We never recommend turning off critical areas:
- Server rooms stay cool (P1)
- Executive areas get priority (P2)
- Only general areas get reduced (P3-P5)

### Comfort Boundary Protection

If a zone is already warm (within 1°C of the comfort limit), we won't reduce AC there — even if it's a low-priority zone.

---

## API Response Example

Here's what the system returns:

```json
{
  "site_id": "site-002",
  "timestamp": "2026-05-18T17:45:00Z",
  "curtailable_load_kw": 142.0,
  "safe_duration_minutes": 95,
  "confidence": 0.82,
  "limiting_factor": "chiller_thermal_mass",
  "eskom_stage": 2,
  "is_load_shedding_active": true,
  "ddmp_eligible": false,
  "bess_soc_pct": 78.4,
  "zone_breakdown": [
    {
      "zone_id": "PARKING-01",
      "zone_name": "Basement Parking",
      "priority": 5,
      "curtailable_kw": 45.0
    },
    {
      "zone_id": "LOBBY-01",
      "zone_name": "Main Lobby",
      "priority": 4,
      "curtailable_kw": 38.0
    },
    {
      "zone_id": "OFFICE-A",
      "zone_name": "Open Office A",
      "priority": 3,
      "curtailable_kw": 59.0
    }
  ],
  "data_freshness_seconds": 45
}
```

**Translation:**
- We can reduce **142 kW** safely
- For **95 minutes**
- With **82% confidence**
- Limited by how fast the building heats up
- Battery is **78% charged**
- Data is **45 seconds old** (very fresh)
- **Not DDMP eligible alone** (under 500 kW)

---

## Common Questions

### Q: Can this automatically turn off my AC?
**A:** No. This endpoint is **read-only** — it only tells you what *could* be done. Actual control requires separate approval workflows and safety checks.

### Q: What if the building doesn't have a battery?
**A:** No problem. The `bess_soc_pct` field will be null, and DDMP eligibility will be calculated without the battery constraint.

### Q: How accurate is this?
**A:** The confidence score tells you. Typically 75-95% accurate. We use:
- Real-time temperature sensors
- Thermal modeling (how fast spaces heat up)
- Historical data
- Zone priorities
- Equipment load data

### Q: Can I use this for my building?
**A:** Yes, if:
- Your building is in the SENTINEL system
- You have sensor data (temperature, power meters)
- Your zones are properly configured with priorities

### Q: What's the difference between this and load shedding optimization?
**A:**
- **Load shedding optimization:** Internal — SENTINEL decides what to do during load shedding
- **Demand response API:** External — tells outside companies (IES, LTM) what the building can contribute

### Q: Why is DDMP eligibility often "false" for single buildings?
**A:** Eskom requires 500 kW minimum. Most individual buildings are smaller. You need an aggregator to combine multiple buildings.

---

## Integration Example

**For a Battery Management System:**

```python
# Check if it's safe to discharge batteries
response = get_curtailable_load(site_id="site-002")

if response.safe_duration_minutes > 60:
    # Safe to use batteries for over an hour
    start_battery_discharge()
else:
    # Not enough buffer — keep batteries charged
    maintain_standby_mode()
```

**For a Demand Response Aggregator:**

```python
# Build a portfolio for Eskom bid
total_kw = 0
for site in portfolio:
    response = get_curtailable_load(site_id=site.id)
    if response.confidence > 0.75:
        total_kw += response.curtailable_load_kw

if total_kw >= 500:
    submit_ddmp_bid(total_kw)
```

---

## Next Steps

**To use this in your building:**

1. **Verify your site is configured** in SENTINEL
2. **Check zone priorities** are set correctly (P1-P5)
3. **Ensure sensors are working** (temperature, power meters)
4. **Test the endpoint** with your site_id
5. **Integrate with your systems** (BMS, BESS, or aggregator platform)

**To learn more:**
- [Technical API Reference](./demand-response-api.md)
- [Phase 211 Implementation Details](../vault/00-GSD-Phases/Phase-211-Demand-Response-Endpoint.md)
- [Eskom DDMP Programme](https://www.eskom.co.za/demand-response/)

---

**Version:** 1.0.0 | **Phase:** 211 | **Status:** Production Ready
