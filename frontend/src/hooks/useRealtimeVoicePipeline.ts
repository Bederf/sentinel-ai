/**
 * useRealtimeVoicePipeline — OpenAI Realtime-2 STT pipeline (Path C surgical)
 *
 * Replaces ElevenLabs STT with OpenAI Realtime-2 while preserving:
 * - ElevenLabs Rachel TTS (useStreamingTTS / useTextToSpeech)
 * - Claude Sonnet via POST /api/chat
 * - 4-state machine: idle | user_speaking | ai_speaking | interrupted
 * - useSpeechRecognition.ts for text-only fallback
 *
 * Behavior:
 * - On startCapture(): connect WebSocket to OpenAI Realtime, stream PCM audio
 * - Extract transcript from conversation.item.completed events
 * - Call onTranscript() callback — same output shape as ElevenLabs STT
 * - On interrupt(): fire session.interrupt() (fire-and-forget), pause TTS
 *
 * Audio: Realtime-2 expects PCM 24kHz mono via input_audio_buffer.append (base64).
 *        MediaRecorder webm/opus is converted before sending.
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { getRealtimeSessionToken } from "@/lib/api";

interface UseRealtimeVoicePipelineProps {
  /** System docs context string (passed for future use; not used in Path C) */
  systemDocsContext?: string;
  /** Called with final transcript when speech segment ends */
  onTranscript?: (transcript: string) => void;
  /** Called with interim transcript updates */
  onInterim?: (transcript: string) => void;
  /** Called on WebSocket or session errors */
  onError?: (error: Error) => void;
}

interface UseRealtimeVoicePipelineReturn {
  isReady: boolean;
  isRecording: boolean;
  transcript: string;
  error: string | null;
  startCapture: () => Promise<void>;
  stopCapture: () => Promise<void>;
  interrupt: () => void;
}

interface RealtimeEvent {
  type: string;
  item?: {
    content?: Array<{ type: string; transcript?: string }>;
  };
  error?: { message?: string };
  [key: string]: unknown;
}

const MAX_RETRIES = 2;
const REALTIME_MODEL = "gpt-4o-mini-realtime";
const REALTIME_WS_URL = `wss://api.openai.com/v1/realtime?model=${REALTIME_MODEL}`;

/** Convert webm/opus Blob from MediaRecorder to PCM 24kHz mono base64 */
async function convertToPCM24kMono(blob: Blob): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new AudioContext({ sampleRate: 24000 });
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

  // Mono channel, 24kHz
  const pcmData = audioContext.createBuffer(1, audioBuffer.length, 24000);
  pcmData.copyToChannel(audioBuffer.getChannelData(0), 0);

  // Convert to 16-bit PCM
  const pcmSamples = pcmData.getChannelData(0);
  const pcmBytes = new Uint8Array(pcmSamples.length * 2);
  const view = new DataView(pcmBytes.buffer);
  for (let i = 0; i < pcmSamples.length; i++) {
    const s = Math.max(-1, Math.min(1, pcmSamples[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  await audioContext.close();
  return btoa(String.fromCharCode(...pcmBytes));
}

export function useRealtimeVoicePipeline(
  props: UseRealtimeVoicePipelineProps = {}
): UseRealtimeVoicePipelineReturn {
  const { onTranscript, onInterim, onError } = props;

  const [isReady, setIsReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const interimTranscriptRef = useRef("");
  const onTranscriptRef = useRef(onTranscript);
  const onInterimRef = useRef(onInterim);
  const onErrorRef = useRef(onError);
  const retriesRef = useRef(0);

  // Keep refs current without re-renders
  // eslint-disable-next-line react-hooks/refs
  onTranscriptRef.current = onTranscript;
  // eslint-disable-next-line react-hooks/refs
  onInterimRef.current = onInterim;
  // eslint-disable-next-line react-hooks/refs
  onErrorRef.current = onError;

  /** Parse OpenAI Realtime event, extract transcript text, handle errors */
  const handleRealtimeEvent = useCallback(
    (rawEvent: MessageEvent) => {
      let data: RealtimeEvent;
      try {
        data = JSON.parse(rawEvent.data as string) as RealtimeEvent;
      } catch {
        return; // Non-JSON — ignore
      }

      // Error events
      if (data.type === "error" && data.error?.message) {
        onErrorRef.current?.(new Error(`Realtime error: ${data.error.message}`));
        return;
      }

      // Log and ignore response_audio_delta events — ElevenLabs TTS handles output
      if (data.type === "response_audio_delta") {
        const delta = data as { audio?: ArrayBuffer | unknown };
        const byteLen = delta?.audio
          ? (delta.audio as ArrayBuffer).byteLength || "?"
          : "0";
        console.debug(
          `Ignoring ${byteLen} audio delta bytes; using ElevenLabs TTS instead`
        );
        return;
      }

      // Transcript events
      const content = data.item?.content;
      if (content && Array.isArray(content)) {
        for (const item of content) {
          if (item.type === "input_audio" && item.transcript) {
            const text = item.transcript;

            // Update live transcript state
            setTranscript(text);

            if (data.type === "conversation.item.completed") {
              // Final transcript
              onTranscriptRef.current?.(text);
              interimTranscriptRef.current = "";
            } else {
              // Interim — only call onInterim if text grew
              if (text.length > interimTranscriptRef.current.length) {
                interimTranscriptRef.current = text;
                onInterimRef.current?.(text);
              }
            }
            return;
          }
        }
      }
    },
    [] // all state accessed via refs
  );

  /** Connect WebSocket and set up event handlers */
  const connectWebSocket = useCallback(
    async (sessionToken: string, isRetry = false): Promise<WebSocket> => {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(REALTIME_WS_URL);

        ws.onopen = () => {
          // Authenticate with ephemeral token sent as session.update
          ws.send(
            JSON.stringify({
              type: "session.update",
              session: { token: sessionToken },
            })
          );
          resolve(ws);
        };

        ws.onmessage = handleRealtimeEvent;

        ws.onerror = () => {
          const err = new Error("WebSocket connection error");
          onErrorRef.current?.(err);
          reject(err);
        };

        ws.onclose = async (event) => {
          if (event.code === 401 && !isRetry) {
            // Token expired — one-shot retry with fresh token
            try {
              const { token: newToken } = await getRealtimeSessionToken();
              const newWs = await connectWebSocket(newToken, true);
              wsRef.current = newWs;
            } catch {
              onErrorRef.current?.(
                new Error("Session token expired; please refresh and try again")
              );
            }
            return;
          }

          if (event.code !== 1000) {
            const err = new Error(`WebSocket closed: ${event.code} ${event.reason}`);
            onErrorRef.current?.(err);
          }
        };

        wsRef.current = ws;
      });
    },
    [handleRealtimeEvent]
  );

  const startCapture = useCallback(async () => {
    setError(null);
    setTranscript("");
    interimTranscriptRef.current = "";
    retriesRef.current = 0;

    try {
      // 1. Get ephemeral token from backend
      const { token: sessionToken } = await getRealtimeSessionToken();

      // 2. Connect WebSocket
      await connectWebSocket(sessionToken);

      // 3. Get microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 48000, // MediaRecorder native; converted to 24kHz for OpenAI
        },
      });
      streamRef.current = stream;

      // 4. Create MediaRecorder (webm/opus)
      const recorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus",
      });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = async (event) => {
        if (
          event.data &&
          event.data.size > 0 &&
          wsRef.current?.readyState === WebSocket.OPEN
        ) {
          try {
            const pcmBase64 = await convertToPCM24kMono(event.data);
            wsRef.current.send(
              JSON.stringify({
                type: "input_audio_buffer.append",
                audio: pcmBase64,
              })
            );
          } catch {
            // Individual chunk failure — don't stop recording
          }
        }
      };

      recorder.onerror = () => {
        setError("Recording failed");
        setIsRecording(false);
      };

      recorder.start(500); // 500ms chunks
      setIsRecording(true);
      setIsReady(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to start voice capture";
      setError(msg);
      setIsReady(false);
      onErrorRef.current?.(new Error(msg));

      // Retry up to MAX_RETRIES times
      if (retriesRef.current < MAX_RETRIES) {
        retriesRef.current += 1;
        await new Promise((r) => setTimeout(r, 500));
        return startCapture();
      }
    }
  }, [connectWebSocket]);

  const stopCapture = useCallback(async () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    setIsRecording(false);

    // Commit the accumulated audio buffer and request final transcription
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
        wsRef.current.send(
          JSON.stringify({
            type: "conversation.item.create",
            item: {
              type: "input_audio",
              audio: "",
            },
          })
        );
        wsRef.current.send(JSON.stringify({ type: "response.create" }));
      } catch {
        // Best-effort commit — don't block cleanup
      }
    }
  }, []);

  const interrupt = useCallback(() => {
    // Stop recording
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    audioChunksRef.current = [];
    setIsRecording(false);
    setTranscript("");

    // Fire cancel to OpenAI (async, fire-and-forget)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "response.cancel" }));
      } catch {
        // Best-effort
      }
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, "Interrupted");
      wsRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "Unmount");
        wsRef.current = null;
      }
    };
  }, []);

  return {
    isReady,
    isRecording,
    transcript,
    error,
    startCapture,
    stopCapture,
    interrupt,
  };
}
