/**
 * useStreamingTTS - Progressive TTS playback hook
 *
 * Sends complete sentences to TTS as they accumulate from LLM token stream.
 * Audio plays as each sentence is synthesized — before LLM finishes.
 *
 * Flow:
 * 1. LLM tokens arrive via SSE → accumulate in buffer
 * 2. On sentence boundary (.) → send to TTS
 * 3. TTS returns MP3 (~1-2s per sentence)
 * 4. Play immediately while more sentences accumulate
 *
 * Usage:
 *   const tts = useStreamingTTS();
 *   tts.speakChunk("Partial AI response text with a sentence.");
 *   // Audio plays as each complete sentence is ready
 */

import { useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/api";

interface UseStreamingTTSReturn {
  /** Whether TTS is currently playing a sentence */
  isPlaying: boolean;
  /** Currently playing text (for UI indicator) */
  currentText: string;
  /** Error message if any */
  error: string | null;
  /** Play a text chunk (accumulates until sentence end, then sends to TTS) */
  speakChunk: (text: string) => Promise<void>;
  /** Stop current playback and clear buffer */
  stop: () => void;
}

// Sentence-ending punctuation for chunking
const SENTENCE_PATTERN = /[^.!?]*[.!?]+/g;
const MIN_CHUNK = 20; // Min chars before sending

export function useStreamingTTS(): UseStreamingTTSReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentText, setCurrentText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bufferRef = useRef(""); // Accumulated text
  const pendingCountRef = useRef(0); // Outstanding TTS requests
  const stopRef = useRef(false);

  const playAudio = useCallback(async (text: string) => {
    try {
      const token = getAccessToken();

      const response = await fetch("/api/chat/tts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        throw new Error(`TTS error: ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        pendingCountRef.current -= 1;
        if (pendingCountRef.current <= 0) {
          setIsPlaying(false);
          setCurrentText("");
        }
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        pendingCountRef.current -= 1;
        if (pendingCountRef.current <= 0) {
          setIsPlaying(false);
        }
      };

      pendingCountRef.current += 1;
      setIsPlaying(true);
      setCurrentText(text);
      await audio.play();
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      pendingCountRef.current -= 1;
      if (pendingCountRef.current <= 0) {
        setIsPlaying(false);
      }
      setError(e instanceof Error ? e.message : "TTS failed");
    }
  }, []);

  const speakChunk = useCallback(async (text: string) => {
    if (stopRef.current) return;

    // Accumulate
    bufferRef.current += text;

    // Find complete sentences
    const match = bufferRef.current.match(SENTENCE_PATTERN);
    if (!match) {
      // No complete sentence yet — check if buffer is getting long
      if (bufferRef.current.length > 200) {
        // Force send without terminal punctuation
        const toSend = bufferRef.current.trim();
        bufferRef.current = "";
        if (toSend.length >= MIN_CHUNK) {
          await playAudio(toSend);
        }
      }
      return;
    }

    // Send complete sentences
    const toSend = match[0];
    const remainder = bufferRef.current.slice(toSend.length);
    bufferRef.current = remainder;

    if (toSend.trim().length >= MIN_CHUNK) {
      await playAudio(toSend.trim());
    }
  }, [playAudio]);

  const stop = useCallback(() => {
    stopRef.current = true;
    bufferRef.current = "";
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    pendingCountRef.current = 0;
    setIsPlaying(false);
    setCurrentText("");
    setError(null);
    // Reset stop flag after a tick
    setTimeout(() => { stopRef.current = false; }, 0);
  }, []);

  return {
    isPlaying,
    currentText,
    error,
    speakChunk,
    stop,
  };
}