# Ghost Room Intelligence: How SENTINEL Detects Empty Meeting Rooms

## The Problem: Your Building Is Lying to You

Every day, across every corporate office building, meeting rooms are booked on the calendar. The building management system sees the booking and does exactly what it's told — it fires up the air conditioning, turns on the lights, and conditions the space for a meeting. But nobody shows up. The meeting was cancelled, postponed, or simply never happened.

That room sits there — a perfectly climate-controlled empty box — burning energy and blocking other teams from using it. We call these "ghost rooms." They represent a massive hidden cost that facility managers have been unable to detect, until now.

This isn't an occasional hiccup. Industry research from firms like JLL and CBRE consistently shows that a significant portion of booked meeting rooms across corporate portfolios go completely unused. It's a systemic inefficiency hiding in plain sight.

The waste is twofold. First, the building pointlessly conditions an empty space — HVAC running, lights blazing, all for nothing. Second, that room is locked in the booking system, meaning another team that actually needs a space to meet is turned away. It's a waste of energy and a waste of opportunity, happening simultaneously across every floor.

## Why Your Existing Sensors Can't See Ghost Rooms

At this point, most facility managers say: "But we have motion sensors. Don't they handle this?" The answer is no — and the reason is fundamental physics, not a software bug.

Those standard PIR (passive infrared) motion sensors — the little white domes on your ceilings that control your lighting — have two fatal flaws that make them completely unreliable for occupancy detection.

**Fatal Flaw One: Corridor Bleed.** PIR sensors have a wide field of view. They detect people walking past the meeting room in the hallway and tell the system "someone's in here." That's a false positive. The room is empty, but the building thinks it's occupied.

**Fatal Flaw Two: The Stationary Person.** The moment everyone in a real meeting sits still — watching a presentation, reading a document, listening to a speaker — the PIR sensor sees no motion and tells the system the room is empty. That's a false negative. The room is full, but the building thinks it's vacant.

So you end up in the worst possible situation: the system thinks empty rooms are occupied and occupied rooms are empty, sometimes at the very same time. Any downstream logic built on that sensor data — energy optimisation, space analytics, ghost room detection — is working with fundamentally unreliable information.

## The Intelligence Gap

The real issue is what we call the intelligence gap — a complete disconnect between your booking system and physical reality.

Your building has two sources of truth that never talk to each other. On one side, the booking system knows what's supposed to happen. On the other side, the physical room knows what's actually happening. Nothing connects the two.

The calendar makes a claim — "meeting at two o'clock." The room knows the truth — it's empty. That intelligence gap is one simple unanswered question: did anyone actually show up? Your building has no way to answer it.

## How SENTINEL Bridges the Gap

This is precisely where SENTINEL fits in. It's not another sensor. It's not a replacement for your booking system. It's the missing intelligence layer — the brain that listens to what the calendar says, observes what's physically happening in the room, and cross-references them to find the truth.

### The Sensor: mmWave Radar (Not PIR)

SENTINEL uses the HLK-LD2410C, a 24GHz millimetre-wave presence radar mounted above the ceiling tile. Unlike PIR, this sensor uses frequency-modulated continuous wave technology to detect the micro-movements of a breathing human body. It doesn't need someone to wave their arms — it can sense a person sitting perfectly still at a meeting table.

Key advantages over PIR:
- **Detects stationary people** — breathing and micro-movements are enough
- **No corridor bleed** — configurable detection gates suppress false triggers from hallway traffic
- **Non-visual** — no cameras, no privacy concerns, no data retention liability
- **Hidden installation** — mounts above ceiling tiles, completely invisible
- **Low cost** — a fraction of the price of camera-based systems

The sensor reports one simple thing: is someone in this room, yes or no. That binary signal, combined with the booking data, is all SENTINEL needs.

### The Detection Logic: Smart, Not Trigger-Happy

When a booking starts, SENTINEL doesn't immediately flag an empty room. It waits. A configurable grace period — typically fifteen minutes — gives the organiser time to arrive. People run late. They're finishing a previous meeting. They're walking from another floor.

Only after the grace period expires with zero occupancy events does SENTINEL classify the room as a ghost booking. This is intelligent patience — balancing detection speed with accuracy to avoid false alarms.

If someone walks in after the grace period, the system automatically resolves the finding. No manual intervention needed. The ghost finding closes itself.

### The Concierge Workflow: Human in the Loop

SENTINEL never cancels a booking automatically. It never contacts the organiser directly. Instead, it notifies the building concierge — the person who knows the building, knows the tenants, and has the authority to act.

The notification arrives via WhatsApp, email, or Telegram — whatever channel the concierge prefers. The message is simple and actionable: "Ghost booking detected. Room X has been booked since nine o'clock but no presence detected. Please confirm if the room is occupied."

The concierge walks to the room or checks their knowledge of the building. They reply with a single tap: "yes" (someone is there) or "no" (it's empty). That's it. One-tap confirmation, no need to log into any system.

If confirmed empty, the finding is recorded and the concierge can contact the organiser to release the space. If occupied, the finding is resolved and the audit trail is preserved. Either way, the facility manager retains full control. SENTINEL advises — humans decide.

### Beyond Ghost Rooms: Right-Sizing Detection

Ghost rooms are the most dramatic case — zero occupancy in a booked room. But SENTINEL also detects subtler patterns of space underuse:

**Early Vacate** — A room was occupied, but everyone left well before the booking ends. The remaining time could be offered to someone else on a waiting list.

**Brief Occupation** — Someone popped in for a few minutes during a long booking. The space was barely used. This suggests the organiser could have booked a smaller room or a shorter slot.

**Sporadic Use** — Presence was detected for only a small fraction of the total booking duration. This flags speculative bookings — rooms held "just in case" that tie up valuable space.

These patterns aren't flagged to the facility manager. They're surfaced to the organiser as gentle nudges: "Your boardroom booking ran briefly and we have smaller rooms available. Could you release this space?" Over time, this drives a gradual behaviour change — people learn to book more accurately.

## The Integration Approach: Complement, Never Replace

The philosophy behind SENTINEL is not to rip and replace anything. You've already invested in your booking systems, your building management systems, your infrastructure. You keep all of that.

Here's what makes the integration non-invasive:

**Booking System — Unchanged.** SENTINEL doesn't need an API integration with your booking platform. It works by watching a BCC'd email inbox. When a booking is created, the confirmation email flows through. SENTINEL's parser handles iCalendar files, Resource Scheduler notifications, Outlook confirmations — all automatically. No changes to the booking workflow.

**Building Management System — Unchanged.** SENTINEL doesn't modify your BMS configuration. The mmWave sensor is standalone — it publishes its readings independently. SENTINEL subscribes and correlates. Your BMS continues to operate exactly as before.

**Occupancy Sensor — Standalone.** Mounted above the ceiling tile, powered by USB or PoE, communicating over your existing WiFi network. No wiring into the building's control bus. No integration with the lighting system. Completely self-contained.

**Result:** Zero changes to existing workflows. Can be turned off without breaking anything. Concierge retains full control. Purely advisory and informational. This is designed from the ground up to be an easy yes.

## What Happens When a Ghost Room Is Found

When SENTINEL has occupancy control integration enabled, it can go beyond detection:

**HVAC Relaxation** — The temperature setpoint shifts for the empty zone. Instead of conditioning an empty room to a comfortable temperature, the system relaxes to a maintenance level. When someone arrives, the setpoint is restored immediately.

**Lighting Control** — Brightness dims to a minimal level for empty zones, then restores to full when the room is re-occupied. This works alongside existing DALI lighting infrastructure where available.

Every control action is logged with a full audit trail — who triggered it, what changed, what the previous value was, and what the occupancy state was at the time. Complete accountability.

## Three Streams of Strategic Value

When you bridge the intelligence gap across your portfolio, you move from fixing a small annoyance to enabling real strategic asset management.

**Stream One: Energy Savings.** Every ghost room that's detected means HVAC and lighting can be relaxed in real time. Across a portfolio of buildings with many meeting rooms, the compound effect on your energy bill is substantial.

**Stream Two: Space Recovery.** Ghost rooms and underused spaces are returned to circulation. Teams that couldn't find a meeting room suddenly can. Productivity improves. Frustration drops. You're getting more value from the square metres you're already paying for.

**Stream Three: Portfolio Intelligence.** Over time, SENTINEL builds a detailed picture of how your spaces are actually used — not what the calendar claims, but what's physically happening. This data powers smarter decisions about leases, floor plans, renovation priorities, and portfolio strategy. You stop guessing and start making data-driven real estate decisions.

## The Audit Trail

Every finding follows a complete lifecycle:

**Open** — Ghost booking detected after grace period with zero occupancy.
**Pending Inspection** — Concierge notified, awaiting physical confirmation.
**Confirmed Empty** — Concierge verified the room is unoccupied.
**Verified Occupied** — Either concierge confirmed presence, or sensor auto-detected occupancy.
**Dismissed** — Finding reviewed and dismissed (e.g., known maintenance booking).

Every state transition is timestamped and attributed. This creates a defensible record for tenant discussions, energy reporting, and space utilisation audits.

## The Bottom Line

Right now, your building has a story to tell you — a detailed, minute-by-minute account of how it's really being used, or not being used. SENTINEL is the intelligence layer that surfaces that truth to the people — your facility managers, your real estate teams, your building operators — who can actually do something about it.

It's non-invasive. It's intelligent. It keeps humans in the loop. And it turns the ghost rooms hiding in your portfolio from a silent cost into a recovered asset.

The only question is: are you ready to listen?
