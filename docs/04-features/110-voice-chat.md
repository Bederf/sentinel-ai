---
status: implemented
version: 110
date: 2026-02-21
---

# Phase 110: Voice Chat — STT Input + ElevenLabs TTS Summary Output

## Overview

Voice interface for the SENTINEL chat panel. Users speak via microphone (browser-native Speech-to-Text), receive the full AI text response displayed as usual, and hear a summarized 1-2 sentence version via ElevenLabs TTS audio. The voice feature is additive — chat works identically without it.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Chat.tsx (Chat Panel)                                    │
│  ┌──────────┐  ┌─────────────┐  ┌────────────────────┐  │
│  │ Mic btn  │  │ Text Input  │  │ Send btn           │  │
│  │ (STT)    │  │ (shows      │  │                    │  │
│  │          │  │  transcript) │  │                    │  │
│  └────┬─────┘  └──────┬──────┘  └────────────────────┘  │
│       │               │                                   │
│       ▼               ▼                                   │
│  useSpeechRecognition  ──► setInput(transcript)           │
│  (Web Speech API)                                         │
│                                                           │
│  ChatMessage.tsx                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │ AI Response (full markdown)                        │   │
│  │ ┌──────────────────┐                              │   │
│  │ │ 🔊 Listen button │  ──► useTextToSpeech         │   │
│  │ └──────────────────┘       │                      │   │
│  └────────────────────────────┼──────────────────────┘   │
└───────────────────────────────┼──────────────────────────┘
                                │
                    POST /api/chat/tts
                                │
                                ▼
┌──────────────────────────────────────────────────────────┐
│  Backend: tts_service.py                                  │
│                                                           │
│  1. Check Redis cache (SHA256 content hash, 1hr TTL)     │
│  2. Claude summarizes to 1-2 sentences                    │
│     (short texts <200 chars pass through)                 │
│  3. ElevenLabs synthesizes MP3 audio                      │
│  4. Cache result, return audio/mpeg                       │
└──────────────────────────────────────────────────────────┘
```

## Components

### Backend

**`backend/app/services/tts_service.py`** — Singleton TTS service

| Method | Description |
|--------|-------------|
| `is_configured()` | Checks `ELEVENLABS_TTS_ENABLED` + `ELEVENLABS_API_KEY` |
| `summarize_for_speech(text)` | Claude summarizes to 1-2 spoken sentences; short texts (<200 chars) pass through with markdown stripped |
| `synthesize(text)` | POST to ElevenLabs `/v1/text-to-speech/{voice_id}`, returns MP3 bytes |
| `text_to_speech(full_response)` | Full pipeline: cache check → summarize → synthesize → cache store |

**`backend/app/api/chat.py`** — TTS endpoint

| Endpoint | Method | Rate Limit | Description |
|----------|--------|------------|-------------|
| `/api/chat/tts` | POST | 10/min | Accepts `{ text: string }`, returns `audio/mpeg` |
| `/api/chat/status` | GET | — | Updated: `features.tts` boolean in response |

Error codes:
- `503` — TTS not configured (missing API key or disabled)
- `400` — Empty text
- `502` — ElevenLabs synthesis failed

### Frontend

**`frontend/src/hooks/useSpeechRecognition.ts`** — Browser STT hook

- Uses Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)
- Default language: `en-ZA` (South African English)
- Single utterance mode (`continuous: false`)
- Returns: `isSupported`, `isListening`, `transcript`, `finalTranscript`, `error`
- Actions: `startListening()`, `stopListening()`, `toggleListening()`, `reset()`
- Browser support: Chrome, Edge, Safari. Hidden on unsupported browsers (Firefox).

**`frontend/src/hooks/useTextToSpeech.ts`** — TTS playback hook

- Calls `api.textToSpeech()` → creates `Audio` object → plays MP3
- Returns: `isAvailable`, `isLoading`, `isPlaying`, `activeMessageId`, `error`
- Actions: `speak(text, messageId)`, `stop()`
- Memory cleanup: `URL.revokeObjectURL()` on unmount and between plays
- Toggle: clicking speaker on a playing message stops it

**`frontend/src/components/Chat.tsx`** — Integration

- Mic button: appears between input and Send button when browser supports Web Speech API
- Visual states: pulsing red border when listening, orange input border
- Input shows live interim transcript while listening
- TTS availability check via `/api/chat/status` on mount
- STT error display below docs toggle

**`frontend/src/components/ChatMessage.tsx`** — Speaker button

- Shows on non-streaming assistant messages when TTS is configured
- States: "Listen" (idle), "Loading..." (fetching), "Playing..." (audio active)
- Icons: `Volume2` (ready/playing), `Loader2` (loading spinner)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ELEVENLABS_API_KEY` | `""` | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | Voice ID (default: Rachel) |
| `ELEVENLABS_MODEL_ID` | `eleven_monolingual_v1` | TTS model |
| `ELEVENLABS_TTS_ENABLED` | `false` | Master enable switch |

### Enabling Voice Chat

```bash
# Add to backend/.env
ELEVENLABS_API_KEY=your_api_key_here
ELEVENLABS_TTS_ENABLED=true

# Restart backend
```

No frontend configuration required — the mic button auto-detects browser support, and the speaker button auto-detects TTS availability from the backend.

## Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| TTS not configured | Speaker button hidden; chat works normally |
| Browser lacks Web Speech API | Mic button hidden; text input only |
| ElevenLabs API down | `POST /chat/tts` returns 502; chat works normally |
| Claude summarization fails | Falls back to first 2 sentences of plain text |
| Redis unavailable | Skips caching; still synthesizes audio |

## Future Enhancements

Documented for future implementation:

- **Whisper API fallback** — Server-side STT for browsers without Web Speech API
- **Wake word detection** — "Hey Sentinel" hands-free activation
- **Multi-language support** — Auto-detect language, multilingual TTS voices
- **Voice cloning** — Custom facility manager voice via ElevenLabs voice cloning
- **Streaming TTS** — ElevenLabs streaming API for lower latency on long summaries
