/**
 * useTextToSpeech - TTS playback management hook
 *
 * Calls the backend TTS endpoint to get MP3 audio for a text,
 * then plays it using the HTML5 Audio API.
 *
 * Handles loading states, playback controls, and Object URL cleanup.
 */

import { useState, useRef, useCallback, useEffect } from "react";
import api from "@/lib/api";

interface UseTextToSpeechReturn {
  /** Whether TTS is available (set by parent after checking /chat/status) */
  isAvailable: boolean;
  /** Set TTS availability from parent */
  setAvailable: (available: boolean) => void;
  /** Whether audio is being fetched from the API */
  isLoading: boolean;
  /** Whether audio is currently playing */
  isPlaying: boolean;
  /** ID of the message currently playing/loading */
  activeMessageId: string | null;
  /** User-friendly error message */
  error: string | null;
  /** Request and play TTS for text */
  speak: (text: string, messageId: string) => void;
  /** Stop current playback */
  stop: () => void;
}

export function useTextToSpeech(): UseTextToSpeechReturn {
  const [isAvailable, setAvailable] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  // Cleanup Object URLs to prevent memory leaks
  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => cleanup, [cleanup]);

  const speak = useCallback(
    async (text: string, messageId: string) => {
      // If same message is playing, toggle off
      if (activeMessageId === messageId && isPlaying) {
        cleanup();
        setIsPlaying(false);
        setActiveMessageId(null);
        return;
      }

      // Stop any current playback
      cleanup();
      setError(null);
      setIsLoading(true);
      setActiveMessageId(messageId);
      setIsPlaying(false);

      try {
        const blob = await api.textToSpeech(text);
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;

        const audio = new Audio(url);
        audioRef.current = audio;

        audio.onended = () => {
          setIsPlaying(false);
          setActiveMessageId(null);
          cleanup();
        };

        audio.onerror = () => {
          setError("Audio playback failed");
          setIsPlaying(false);
          setActiveMessageId(null);
          cleanup();
        };

        await audio.play();
        setIsPlaying(true);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "TTS failed";
        setError(msg);
        setActiveMessageId(null);
        cleanup();
      } finally {
        setIsLoading(false);
      }
    },
    [activeMessageId, isPlaying, cleanup]
  );

  const stop = useCallback(() => {
    cleanup();
    setIsPlaying(false);
    setIsLoading(false);
    setActiveMessageId(null);
  }, [cleanup]);

  return {
    isAvailable,
    setAvailable,
    isLoading,
    isPlaying,
    activeMessageId,
    error,
    speak,
    stop,
  };
}
