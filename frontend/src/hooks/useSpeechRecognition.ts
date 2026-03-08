/**
 * useSpeechRecognition - Browser-native Web Speech API hook
 *
 * Provides speech-to-text input for the chat panel using the browser's
 * built-in SpeechRecognition API (Chrome, Edge, Safari).
 *
 * Default language: en-ZA (South African English)
 * Mode: Single utterance per mic press (continuous: false)
 *
 * Future enhancements (not implemented):
 * - Whisper API fallback for unsupported browsers
 * - Wake word detection ("Hey Sentinel")
 * - Multi-language support with auto-detection
 * - Continuous listening mode with silence detection
 */

import { useState, useEffect, useRef, useCallback } from "react";

// Extend Window for vendor-prefixed SpeechRecognition
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
};

interface UseSpeechRecognitionOptions {
  /** Callback fired with final transcript when speech ends */
  onResult?: (transcript: string) => void;
  /** BCP-47 language tag (default: en-ZA) */
  language?: string;
}

interface UseSpeechRecognitionReturn {
  /** Whether the browser supports Web Speech API */
  isSupported: boolean;
  /** Whether the mic is currently listening */
  isListening: boolean;
  /** Current interim transcript (updates while speaking) */
  transcript: string;
  /** Last final transcript */
  finalTranscript: string;
  /** User-friendly error message */
  error: string | null;
  /** Start listening */
  startListening: () => void;
  /** Stop listening */
  stopListening: () => void;
  /** Toggle listening on/off */
  toggleListening: () => void;
  /** Reset transcript and error state */
  reset: () => void;
}

function getSpeechRecognitionConstructor(): (new () => SpeechRecognitionInstance) | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as
    | (new () => SpeechRecognitionInstance)
    | null;
}

export function useSpeechRecognition(
  options: UseSpeechRecognitionOptions = {}
): UseSpeechRecognitionReturn {
  const { onResult, language = "en-ZA" } = options;

  const [isSupported] = useState(() => getSpeechRecognitionConstructor() !== null);
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const onResultRef = useRef(onResult);
  // eslint-disable-next-line react-hooks/refs
  onResultRef.current = onResult;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        recognitionRef.current.onstart = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  const startListening = useCallback(() => {
    const Ctor = getSpeechRecognitionConstructor();
    if (!Ctor) {
      setError("Speech recognition is not supported in this browser");
      return;
    }

    // Abort any previous session
    if (recognitionRef.current) {
      recognitionRef.current.abort();
    }

    setError(null);
    setTranscript("");

    const recognition = new Ctor();
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final_ = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final_ += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final_) {
        setFinalTranscript(final_);
        setTranscript(final_);
        onResultRef.current?.(final_);
      } else {
        setTranscript(interim);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessages: Record<string, string> = {
        "not-allowed": "Microphone access denied. Please allow mic permissions.",
        "no-speech": "No speech detected. Please try again.",
        "network": "Network error. Check your connection.",
        "audio-capture": "No microphone found. Please connect a microphone.",
        "aborted": "", // User-initiated, no error to show
      };
      const msg = errorMessages[event.error] ?? `Speech recognition error: ${event.error}`;
      if (msg) setError(msg);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    try {
      recognition.start();
    } catch (_e) {
      setError("Failed to start speech recognition");
      setIsListening(false);
    }
  }, [language]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  const reset = useCallback(() => {
    setTranscript("");
    setFinalTranscript("");
    setError(null);
    if (recognitionRef.current) {
      recognitionRef.current.abort();
    }
  }, []);

  return {
    isSupported,
    isListening,
    transcript,
    finalTranscript,
    error,
    startListening,
    stopListening,
    toggleListening,
    reset,
  };
}
