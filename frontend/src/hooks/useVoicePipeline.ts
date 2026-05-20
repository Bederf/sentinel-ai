/**
 * useVoicePipeline - Continuous audio capture and streaming STT/TTS
 *
 * Handles the full conversational voice pipeline:
 * 1. Captures audio chunks from microphone (MediaRecorder)
 * 2. Sends to /api/chat/stt/stream for transcription
 * 3. Shows live partial transcripts
 * 4. Plays TTS audio chunks as they arrive
 *
 * Works alongside VAD hook for silence detection
 */

import { useState, useRef, useCallback, useEffect } from "react";
import api from "@/lib/api";

interface UseVoicePipelineOptions {
  /** Called with final transcript when speech segment ends (VAD silence) */
  onTranscript?: (transcript: string) => void;
  /** Called with interim transcript updates */
  onInterim?: (transcript: string) => void;
  /** Called when TTS audio chunk arrives for playback */
  onAudioChunk?: (audioChunk: ArrayBuffer) => void;
  /** Audio format for recording (default: webm) */
  audioFormat?: "webm" | "wav" | "mp4";
}

interface UseVoicePipelineReturn {
  /** Whether microphone access is granted */
  isReady: boolean;
  /** Whether audio is currently being captured */
  isRecording: boolean;
  /** Current (partial) transcript */
  transcript: string;
  /** Error message if any */
  error: string | null;
  /** Start continuous audio capture */
  startCapture: () => Promise<void>;
  /** Stop capture and send final segment */
  stopCapture: () => Promise<void>;
  /** Interrupt current TTS playback and stop capture */
  interrupt: () => void;
}

const CHUNK_DURATION_MS = 500; // Send chunk every 500ms
const INTERIM_THRESHOLD = 3; // Send interim after 3+ chunks

export function useVoicePipeline(
  options: UseVoicePipelineOptions = {}
): UseVoicePipelineReturn {
  const {
    onTranscript,
    onInterim,
    audioFormat = "webm",
  } = options;

  const [isReady, setIsReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const interimCountRef = useRef(0);
  const transcriptCallbackRef = useRef(onTranscript);
  const interimCallbackRef = useRef(onInterim);

  // eslint-disable-next-line react-hooks/refs
  transcriptCallbackRef.current = onTranscript;
  // eslint-disable-next-line react-hooks/refs
  interimCallbackRef.current = onInterim;

  const transcribeChunk = useCallback(async (audioBlob: Blob) => {
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        const base64 = (reader.result as string).split(",")[1];
        if (!base64) return;

        // Use raw fetch to avoid API abstraction complexity
        // Get token from the same source as streamChat
        const { getAccessToken } = await import("@/lib/api");
        const token = getAccessToken();

        const response = await fetch("/api/chat/stt/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ audio: base64, format: audioFormat }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.text) {
            setTranscript(data.text);
            interimCountRef.current += 1;

            if (interimCountRef.current >= INTERIM_THRESHOLD) {
              interimCallbackRef.current?.(data.text);
            }
          }
        }
      };
      reader.readAsDataURL(audioBlob);
    } catch {
      // Silent fail — individual chunk failure shouldn't stop recording
    }
  }, [audioFormat]);

  const startCapture = useCallback(async () => {
    try {
      // Get microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });
      streamRef.current = stream;
      audioChunksRef.current = [];
      interimCountRef.current = 0;
      setTranscript("");
      setError(null);

      // Create MediaRecorder
      const mimeType = audioFormat === "wav"
        ? "audio/wav"
        : audioFormat === "mp4"
        ? "audio/mp4"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
          // Transcribe chunk for live preview
          transcribeChunk(event.data);
        }
      };

      recorder.onerror = () => {
        setError("Recording failed");
        setIsRecording(false);
      };

      recorder.start(CHUNK_DURATION_MS);
      setIsRecording(true);
      setIsReady(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Microphone access denied";
      setError(msg);
      setIsReady(false);
    }
  }, [audioFormat, transcribeChunk]);

  const stopCapture = useCallback(async () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }

    // Stop all tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    setIsRecording(false);

    // Send final accumulated audio
    if (audioChunksRef.current.length > 0) {
      const finalBlob = new Blob(audioChunksRef.current, { type: `audio/${audioFormat}` });
      audioChunksRef.current = [];

      // Transcribe final segment and return via callback
      try {
        const reader = new FileReader();
        reader.onload = async () => {
          const base64 = (reader.result as string).split(",")[1];
          if (!base64) return;

          const { getAccessToken } = await import("@/lib/api");
          const token = getAccessToken();

          const response = await fetch("/api/chat/stt/stream", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ audio: base64, format: audioFormat }),
          });

          if (response.ok) {
            const data = await response.json();
            if (data.text) {
              transcriptCallbackRef.current?.(data.text);
            }
          }
        };
        reader.readAsDataURL(finalBlob);
      } catch {
        // Silent fail
      }
    }
  }, [audioFormat]);

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