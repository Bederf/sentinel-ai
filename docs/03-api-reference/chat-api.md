---
title: "Chat / Voice API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2025-01-01"
updated: "2026-05-23"
author: "Sentinel Development Team"
tags: ["api", "chat", "voice", "stt", "tts", "realtime", "elevenlabs", "openai-realtime"]
domain: "ai"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Chat / Voice API Reference

Chat and voice I/O endpoints. Covers text chat with tool calling, ElevenLabs STT/TTS, and OpenAI Realtime-2 voice pipeline (Path C-Surgical).

Base path: `/api/chat`

## Status

### GET `/api/chat/status`

Returns voice provider configuration status.

**Response:**
```json
{
  "stt": { "configured": true, "provider": "elevenlabs" },
  "tts": { "configured": true, "provider": "elevenlabs", "voice_id": "21m00Tcm4TlvDq8ikWAM" },
  "realtime_voice": { "configured": false, "provider": "openai-realtime" }
}
```

---

## Chat (Claude Sonnet)

### POST `/api/chat`

Stream a chat message to Claude Sonnet with tool calling. Supports RAG context, conversation history, and voice summarization.

**Request Body:**
```json
{
  "message": "What's the current temperature in Zone A?",
  "conversation_id": "uuid-optional",
  "site_id": "site-002",
  "include_system_docs": true
}
```

**Response:** Server-Sent Events (SSE) stream of tokens.

```json
{"token": "The"}
{"token": " current"}
{"token": " temperature"}
```

**Tool Calling:** The endpoint can call backend tools (equipment control, doc search, work orders) during the stream. Tool result chunks are returned as:
```json
{"tool": "equipment_control", "input": {"equipment_id": "S002-VAV-A1", "point": "cooling_setpoint", "value": 22}}
```

**Errors:**
- `401` — Authentication required
- `429` — Rate limit exceeded
- `503` — Claude API unavailable (falls back to OpenAI or local)

---

## Text-to-Speech

### POST `/api/chat/tts`

Synthesize text to speech via ElevenLabs. Returns full MP3 blob (non-streaming).

**Request Body:**
```json
{
  "text": "The current Zone A temperature is 23°C.",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "model": "eleven_monolingual_v1"
}
```

**Response:** `audio/mpeg` binary (MP3).

**Errors:**
- `400` — Invalid text (empty or exceeds token limit)
- `503` — ElevenLabs not configured

---

## Streaming Text-to-Speech

### POST `/api/chat/tts/stream`

Stream synthesized speech via ElevenLabs. Progressive chunks returned as they're generated.

**Request Body:**
```json
{
  "text": "The current Zone A temperature is 23°C.",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "model": "eleven_multilingual"
}
```

**Response:** `audio/mpeg` stream (8192-byte chunks).

**Interruption:** Client-side stop (`useStreamingTTS.stop()`) pauses playback but does **not** abort ElevenLabs server-side generation.

---

## Speech-to-Text

### POST `/api/chat/stt/stream`

Transcribe audio to text via ElevenLabs speech-to-text. Accepts base64-encoded audio chunks.

**Request Body:**
```json
{
  "audio": "<base64-encoded-audio>",
  "format": "webm",
  "language": "en"
}
```

**Response:**
```json
{
  "text": "What's the current temperature in Zone A?",
  "language": "en"
}
```

**Supported formats:** `webm`, `wav`, `mp4` (MediaRecorder formats from browser).

**Rate limit:** 30 requests/minute per IP.

---

## Voice Summary

### POST `/api/chat/voice-summary`

Summarize an AI response via Claude Haiku, then synthesize via ElevenLabs. Returns text summary + data URI audio for direct `<audio>` playback.

**Request Body:**
```json
{
  "text": "Long AI response that needs to be condensed for voice playback..."
}
```

**Response:**
```json
{
  "text": "The Zone A temperature is 23°C and the humidity is 55%.",
  "audio_url": "data:audio/mpeg;base64,..."
}
```

**Use case:** When AI response is too long for real-time TTS, pre-summarize for faster voice playback.

---

## OpenAI Realtime-2 Voice (Path C-Surgical)

### POST `/api/chat/realtime/connect`

Issue an ephemeral OpenAI Realtime-2 session token. Frontend uses this token to connect directly to OpenAI's WebSocket.

**Authentication:** JWT Bearer token required.

**Request Body:**
```json
{
  "site_id": "site-002"
}
```

**Response:**
```json
{
  "token": "eyJhbGc...",
  "expires_in": 3600,
  "model": "gpt-4o-mini-realtime"
}
```

**Gates (all enforced server-side):**

| Gate | Condition | Response |
|------|-----------|----------|
| Feature flag | `OPENAI_REALTIME_API_KEY` not set | `503` |
| Feature flag | `REALTIME_VOICE_ENABLED=false` | `503` |
| Site access | Site not found or inaccessible | `404` |
| Operating hours | Current time outside `operating_hours.weekday` window | `403` |
| Auth | Invalid/missing JWT | `401` |

**Operating hours gate:** The `sites.operating_hours` JSON column is parsed as `"HH:MM-HH:MM"`. Gate fires if `now` is outside the window.

**Errors:**
```json
// 403 — Outside operating hours
{"detail": "Voice unavailable outside operating hours (08:00-18:00)"}

// 404 — Site not found
{"detail": "Site 'site-002' not found or inaccessible"}

// 503 — Not configured
{"detail": "OpenAI Realtime voice is disabled."}
```

---

## Voice Pipeline Architecture

```
Chat.tsx (Frontend)
│
├─ System docs OFF → useSpeechRecognition (Web Speech API, single utterance)
│
└─ System docs ON → voicePipeline = useVoicePipeline (ElevenLabs STT)
                   OR
                   voicePipeline = useRealtimeVoicePipeline (OpenAI Realtime-2)

ElevenLabs STT path (legacy):
  MediaRecorder → POST /api/chat/stt/stream → ElevenLabs s2t_medium → transcript
  → POST /api/chat → Claude Sonnet → response text
  → POST /api/chat/tts/stream → ElevenLabs Rachel TTS → audio

OpenAI Realtime-2 path (Path C-Surgical):
  MediaRecorder → WebSocket wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime
  → Realtime-2 transcript (conversation.updated event)
  → POST /api/chat → Claude Sonnet → response text
  → POST /api/chat/tts/stream → ElevenLabs Rachel TTS → audio
  (response_audio_delta events from Realtime-2 are discarded; ElevenLabs TTS handles output)
```

### State Machine

Voice mode uses a 4-state interruptible machine:

| State | Trigger | Exit |
|-------|---------|------|
| `idle` | Waiting for mic press | Mic pressed → `user_speaking` |
| `user_speaking` | VAD detects speech start | Silence detected → `ai_speaking` |
| `ai_speaking` | TTS playback begins | `audio.onended` → `idle`, or interrupt → `interrupted` |
| `interrupted` | Mic pressed during AI speech | Restarts listening → `user_speaking` |

### Feature Flags

| Flag | Location | Default | Purpose |
|------|----------|---------|---------|
| `VITE_REALTIME_VOICE_ENABLED` | Frontend `.env` | `false` | Enable Realtime-2 hook in Chat.tsx |
| `realtime_voice_enabled` | Backend `settings.py` | `false` | Allow token issuance |
| `OPENAI_REALTIME_API_KEY` | Backend env | unset | OpenAI API key for session creation |

**To enable Path C-Surgical:** set `VITE_REALTIME_VOICE_ENABLED=true` (frontend) + `OPENAI_REALTIME_API_KEY=<key>` (backend env) + `realtime_voice_enabled=true` (backend setting).
