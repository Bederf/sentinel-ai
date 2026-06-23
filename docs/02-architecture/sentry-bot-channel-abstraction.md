---
title: "Sentry Bot Channel Abstraction — Current State"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-06-23"
updated: "2026-06-23"
tags: ["sentinel", "sentry", "channel-abstraction", "telegram", "architecture"]
domain: "architecture"
audience: "engineering, architecture"
complexity: "intermediate"
estimated_read_time: 5
---

# Sentry Bot Channel Abstraction — Current State (as of June 2026)

**Date:** 2026-06-23
**Owner:** SENTINEL Platform Team

---

## Gateway (Node.js/OpenClaw)

Proper channel abstraction exists at the engine level via `api.registerInteractiveHandler({ channel: "telegram" })`. Multi-bot routing is supported per `sentry.json` config.

---

## Backend (Python)

Abstraction is lost after webhook handoff. Handlers receive raw Telegram primitives (`chat_id`, `callback_data`, `message_id`) directly. Key Telegram-coupled classes:

- `TelegramMessageSender`
- `TelegramIntent`
- `TelegramConversationManager`

---

## Transport-Agnostic Exceptions

- **`DiagnosisFlowEngine`** (`technician_chat.py`) — pure state machine, no transport references. This is the model for future abstraction.
- **`SentryNotificationRouter`** — outbound-only, has `DeliveryChannel` enum already in place.

---

## To Add a Second Channel

Requires introducing `IncomingMessage`/`OutgoingResponse` normalized types and refactoring all Telegram-coupled handlers to consume/produce them instead of raw Telegram primitives. Estimated scope: not a quick add — touches every handler in the conversation flow.

---

## Sales Positioning for Enterprise Reviews

Architecture intent is transport-agnostic. Current implementation is Telegram-coupled. If a client requires a second channel, scope this refactor explicitly before committing to a timeline.
