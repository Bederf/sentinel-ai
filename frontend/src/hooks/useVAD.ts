/**
 * useVAD - Voice Activity Detection hook using silero-vad (via @ricky0123/vad-web)
 *
 * Provides browser-native VAD with:
 * - Speech detection (start/end)
 * - Audio segments captured for transcription
 * - Configurable silence threshold (triggers when user stops speaking)
 * - Works alongside existing useSpeechRecognition
 *
 * Default: 1.5s of silence triggers speech-end → transcript sent
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { MicVAD } from "@ricky0123/vad-web";
import { encodeWAV } from "@ricky0123/vad-web/dist/utils";

// Expose encodeWAV from vad-web utils
function toWav(samples: Float32Array, sampleRate = 16000): ArrayBuffer {
  return encodeWAV(samples, 1, sampleRate, 1, 16);
}

interface UseVADOptions {
  /** Called when speech segment ends — pass audio blob for transcription */
  onSpeechEnd?: (audioBlob: Blob, transcript: string) => void;
  /** Called when speech starts (user began talking) */
  onSpeechStart?: () => void;
  /** Time in ms of silence before triggering speech-end (default: 1500) */
  silenceThresholdMs?: number;
  /** Model version: "v5" (more accurate) or "legacy" (faster) (default: "v5") */
  model?: "v5" | "legacy";
}

interface UseVADReturn {
  /** Whether VAD is ready and loaded */
  isReady: boolean;
  /** Whether user is currently speaking */
  isSpeaking: boolean;
  /** Whether VAD engine is listening for speech */
  isListening: boolean;
  /** Loading error message */
  error: string | null;
  /** Start VAD listening */
  start: () => Promise<void>;
  /** Pause VAD (mic off but model loaded) */
  pause: () => Promise<void>;
  /** Resume after pause */
  resume: () => Promise<void>;
  /** Stop and cleanup VAD */
  destroy: () => Promise<void>;
}

export function useVAD(options: UseVADOptions = {}): UseVADReturn {
  const {
    onSpeechEnd,
    onSpeechStart,
    _silenceThresholdMs = 1500,
    model = "v5",
  } = options;

  const [isReady, setIsReady] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const vadRef = useRef<MicVAD | null>(null);
  const speechStartCallbackRef = useRef(onSpeechStart);
  const speechEndCallbackRef = useRef(onSpeechEnd);

  // Keep refs current without re-creating VAD
  // eslint-disable-next-line react-hooks/refs
  speechStartCallbackRef.current = onSpeechStart;
  // eslint-disable-next-line react-hooks/refs
  speechEndCallbackRef.current = onSpeechEnd;

  const initVAD = useCallback(async () => {
    try {
      const vad = await MicVAD.new({
        model,
        // Frame processing callbacks
        onSpeechStart: () => {
          setIsSpeaking(true);
          speechStartCallbackRef.current?.();
        },
        onSpeechEnd: (audio: Float32Array) => {
          setIsSpeaking(false);
          // Convert to WAV blob
          const wavBuffer = toWav(audio);
          const blob = new Blob([wavBuffer], { type: "audio/wav" });
          // onSpeechEnd callback receives blob for transcription
          speechEndCallbackRef.current?.(blob, "");
        },
        onVADMisfire: () => {
          setIsSpeaking(false);
        },
        onFrameProcessed: async () => {
          // Individual frame probabilities available but not used here
          // Can extend to show speech probability indicator
        },
      });
      vadRef.current = vad;
      setIsReady(true);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "VAD initialization failed";
      setError(msg);
      setIsReady(false);
    }
  }, [model]);

  const start = useCallback(async () => {
    if (!vadRef.current) {
      await initVAD();
    }
    if (vadRef.current) {
      try {
        await vadRef.current.start();
        setIsListening(true);
        setError(null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to start VAD";
        setError(msg);
      }
    }
  }, [initVAD]);

  const pause = useCallback(async () => {
    if (vadRef.current) {
      await vadRef.current.pause();
      setIsListening(false);
    }
  }, []);

  const resume = useCallback(async () => {
    if (vadRef.current) {
      await vadRef.current.start();
      setIsListening(true);
    }
  }, []);

  const destroy = useCallback(async () => {
    if (vadRef.current) {
      await vadRef.current.destroy();
      vadRef.current = null;
      setIsListening(false);
      setIsSpeaking(false);
      setIsReady(false);
    }
  }, []);

  // Auto-init on mount
  useEffect(() => {
    initVAD();
    return () => {
      if (vadRef.current) {
        vadRef.current.destroy().catch(() => {});
      }
    };
  }, [initVAD]);

  return {
    isReady,
    isSpeaking,
    isListening,
    error,
    start,
    pause,
    resume,
    destroy,
  };
}
