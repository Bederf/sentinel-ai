/**
 * Chat Component - Grafana-inspired chat interface
 *
 * Features:
 * - Message history display with auto-scroll
 * - Dark theme styling matching dashboard
 * - Input field with Enter key support
 * - SSE stream consumption for real-time responses
 * - Loading state during AI response
 */

import { useState, useRef, useEffect } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Send, MessageSquare, Bot, Mic, MicOff, Trash2, BookOpen, Volume2, VolumeX } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { DocumentUpload } from "./DocumentUpload";
import { BuildingSelector } from "./BuildingSelector";
import api, { isExpectedApiError, streamChat } from '@/lib/api';
import type { Site } from '@/lib/api';
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useTextToSpeech } from "@/hooks/useTextToSpeech";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [includeSystemDocs, setIncludeSystemDocs] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false); // Auto-summarised voice playback

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const hasLoadedSitesRef = useRef(false);

  // Speech-to-text and text-to-speech hooks
  const stt = useSpeechRecognition();
  const tts = useTextToSpeech();

  // Fetch sites on mount
  useEffect(() => {
    if (hasLoadedSitesRef.current) return;
    hasLoadedSitesRef.current = true;

    const loadSites = async () => {
      const cachedSites = localStorage.getItem("sentinel_cached_sites");
      if (cachedSites) {
        try {
          const parsedSites = JSON.parse(cachedSites) as Site[];
          if (parsedSites.length > 0) {
            const sorted = parsedSites.sort((a, b) => a.name.localeCompare(b.name));
            setSites(sorted);
            const defaultSite =
              sorted.find((site) => site.id === "site-002")
              ?? sorted.find((site) => /sandton city office tower/i.test(site.name))
              ?? sorted[0];
            if (defaultSite) {
              setSelectedSiteId(defaultSite.id);
            }
            return;
          }
        } catch {
          // Ignore malformed cache and fall back to API fetch
        }
      }

      try {
        const sitesData = await api.getSites();
        setSites(sitesData.sort((a, b) => a.name.localeCompare(b.name)));
        // Default to Sandton City Office Tower (site-002) when available.
        const defaultSite =
          sitesData.find((site) => site.id === "site-002")
          ?? sitesData.find((site) => /sandton city office tower/i.test(site.name))
          ?? sitesData[0];
        if (defaultSite) {
          setSelectedSiteId(defaultSite.id);
        }
      } catch (error) {
        if (!isExpectedApiError(error)) {
          console.error("Failed to load sites:", error);
        }
      }
    };
    loadSites();
  }, []);

  // Check TTS availability on mount
  useEffect(() => {
    const checkTts = async () => {
      try {
        const siteQuery = selectedSiteId ? `?site_id=${encodeURIComponent(selectedSiteId)}` : "";
        const resp = await fetch(`/api/chat/status${siteQuery}`);
        if (resp.ok) {
          const data = await resp.json();
          tts.setAvailable(data.features?.tts === true);
        }
      } catch {
        // TTS unavailable, no action needed
      }
    };
    checkTts();
  }, [selectedSiteId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Auto-submit when speech recognition produces a final transcript
  useEffect(() => {
    console.log("[STT Effect] finalTranscript:", stt.finalTranscript, "isLoading:", isLoading);
    if (!stt.finalTranscript || isLoading) return;
    const text = stt.finalTranscript.trim();
    console.log("[STT Effect] sending:", text);
    stt.reset();
    sendMessage(text);
    // ESLint suppressed: we intentionally depend on finalTranscript and isLoading
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stt.finalTranscript, isLoading]);

  // No auto-greet — chat opens clean every time

  // Generate unique ID for messages
  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  const handleClearChat = () => {
    setMessages([]);
    setInput("");
    setStreamingContent("");
    setIsLoading(false);
    stt.reset();
    tts.stop();
    inputRef.current?.focus();
  };

  // Core send logic shared by form submit and command clicks
  const sendMessage = async (text: string) => {
    if (!text || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: text,
    };
    const assistantId = generateId();
    // Add both user message and a streaming placeholder in one update
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: "assistant", content: "", isStreaming: true },
    ]);
    setInput("");
    setIsLoading(true);
    setStreamingContent("");

    let fullResponse = "";
    try {

      await streamChat(text, undefined, (chunk) => {
        fullResponse += chunk;
        // Update the streaming message content in-place
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: fullResponse } : m
          )
        );
      }, selectedSiteId, includeSystemDocs);

      // Mark streaming complete (same message, no unmount/remount)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: fullResponse, isStreaming: false }
            : m
        )
      );
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Sorry, I encountered an error. Please try again.", isStreaming: false }
            : m
        )
      );
    } finally {
      setIsLoading(false);
      setStreamingContent("");
      inputRef.current?.focus();

      // Auto-play summarised voice if voice mode is on
      if (voiceMode && fullResponse && tts.isAvailable) {
        try {
          const { audio_url } = await api.voiceSummary(fullResponse);
          // Play directly from data URI — no blob fetch needed
          const audio = new Audio(audio_url);
          await audio.play();
        } catch {
          // Voice summary failed — text is already shown, no action needed
        }
      }
    }
  };

  // Handle form submission — prefer speech transcript over typed input
  const handleSubmit = async (e?: FormEvent) => {
    e?.preventDefault();
    // Speech recognition transcript takes priority over typed text
    const text = stt.finalTranscript || input;
    console.log("[handleSubmit] text:", text, "finalTranscript:", stt.finalTranscript);
    if (!text.trim()) return;
    // Clear transcript so the same text can't be re-sent on the next submit
    stt.reset();
    await sendMessage(text.trim());
  };

  // Handle clickable slash command buttons
  const handleCommandClick = (command: string) => {
    sendMessage(command);
  };

  // Handle Enter key
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div
      className="chat-container flex flex-col h-full rounded overflow-hidden"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      {/* Header */}
      <div
        className="flex-none p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(50, 116, 217, 0.15)" }}
          >
            <MessageSquare
              className="h-5 w-5"
              style={{ color: "var(--color-grafana-blue)" }}
            />
          </div>
          <div>
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              SENTINEL
            </h3>
            <span
              className="text-xs"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              AI-powered facilities management support
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleClearChat}
            disabled={isLoading || (messages.length === 0 && !streamingContent)}
            className="px-3 py-1.5 rounded text-xs flex items-center gap-1 transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:brightness-100"
            style={{
              background: "var(--color-grafana-bg-secondary)",
              border: "1px solid var(--color-grafana-border)",
              color: "var(--color-grafana-text-secondary)",
            }}
            aria-label="Clear chat"
            title="Clear chat"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Clear chat</span>
          </button>

          {/* System docs toggle */}
          <button
            type="button"
            onClick={() => setIncludeSystemDocs((prev) => !prev)}
            className="px-3 py-1.5 rounded text-xs flex items-center gap-1.5 transition-all hover:brightness-110"
            style={{
              background: includeSystemDocs
                ? "rgba(50, 116, 217, 0.15)"
                : "var(--color-grafana-bg-secondary)",
              border: includeSystemDocs
                ? "1px solid var(--color-grafana-blue)"
                : "1px solid var(--color-grafana-border)",
              color: includeSystemDocs
                ? "var(--color-grafana-blue)"
                : "var(--color-grafana-text-secondary)",
            }}
            aria-label="Include SENTINEL platform documentation"
            title="Include SENTINEL platform documentation in search"
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Platform docs</span>
          </button>

          {/* Building selector */}
          <BuildingSelector
            value={selectedSiteId}
            onChange={setSelectedSiteId}
            sites={sites}
            disabled={sites.length === 0}
          />
        </div>
      </div>

      {/* Messages area */}
      <div
        className="flex-1 overflow-y-auto p-4 pb-24 md:pb-4"
        role="list"
        aria-label="Chat messages"
      >
        {messages.length === 0 && !isLoading && (
          <div className="h-full flex flex-col items-center justify-center gap-4">
            <Bot
              className="h-16 w-16"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            />
            <div className="text-center">
              <p style={{ color: "var(--color-grafana-text-secondary)" }}>
                Start a conversation with SENTINEL
              </p>
              <p
                className="text-xs mt-2"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                Ask about equipment status, documentation, alerts, or maintenance insights
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            messageId={msg.id}
            role={msg.role}
            content={msg.content}
            isStreaming={msg.isStreaming}
            onCommandClick={msg.role === "assistant" ? handleCommandClick : undefined}
            onSpeak={
              tts.isAvailable && msg.role === "assistant" && !msg.isStreaming
                ? (text, id) => tts.speak(text, id)
                : undefined
            }
            ttsState={
              tts.isAvailable && msg.role === "assistant"
                ? {
                    isLoading: tts.isLoading && tts.activeMessageId === msg.id,
                    isPlaying: tts.isPlaying && tts.activeMessageId === msg.id,
                  }
                : undefined
            }
          />
        ))}

        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form
        onSubmit={handleSubmit}
        className="flex-none p-4 sticky bottom-0 md:relative"
        style={{
          borderTop: "1px solid var(--color-grafana-border)",
          background: "var(--color-grafana-bg-secondary)",
        }}
      >
        {/* STT error message */}
        {stt.error && (
          <p className="text-xs mb-2" style={{ color: "#f44" }}>
            {stt.error}
          </p>
        )}

        <div className="flex gap-2 md:gap-3">
          <input
            ref={inputRef}
            type="text"
            value={stt.isListening ? stt.transcript : input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              stt.isListening
                ? "Listening..."
                : "Ask about building management..."
            }
            disabled={isLoading || stt.isListening}
            className="flex-1 px-3 py-2 md:px-4 md:py-2 text-sm md:text-base rounded focus:outline-none disabled:cursor-not-allowed"
            style={{
              background: "var(--color-grafana-bg-panel)",
              border: stt.isListening
                ? "1px solid var(--color-grafana-orange)"
                : "1px solid var(--color-grafana-border)",
              color: "var(--color-grafana-text-primary)",
            }}
            aria-label="Chat message input"
          />

          {/* Document upload button */}
          <DocumentUpload
            siteId={selectedSiteId}
            onUploadComplete={() => {
              setMessages((prev) => [
                ...prev,
                {
                  id: generateId(),
                  role: "assistant",
                  content: "Document uploaded and indexed successfully. It's now available for search.",
                },
              ]);
            }}
            onError={(error) => {
              setMessages((prev) => [
                ...prev,
                {
                  id: generateId(),
                  role: "assistant",
                  content: `Upload failed: ${error}`,
                },
              ]);
            }}
          />

          {/* Mic button (only when browser supports Web Speech API) */}
          {stt.isSupported && (
            <button
              type="button"
              onClick={stt.toggleListening}
              disabled={isLoading}
              className="px-3 py-2 rounded flex items-center transition-all hover:brightness-110 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: stt.isListening
                  ? "rgba(255, 68, 68, 0.2)"
                  : "var(--color-grafana-bg-panel)",
                border: stt.isListening
                  ? "1px solid #f44"
                  : "1px solid var(--color-grafana-border)",
                color: stt.isListening
                  ? "#f44"
                  : "var(--color-grafana-text-secondary)",
                animation: stt.isListening ? "pulse 1.5s ease-in-out infinite" : undefined,
              }}
              aria-label={stt.isListening ? "Stop listening" : "Start voice input"}
              title={stt.isListening ? "Stop listening" : "Voice input"}
            >
              {stt.isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
          )}

          {/* Voice mode toggle — auto-summarised voice playback */}
          {tts.isAvailable && (
            <button
              type="button"
              onClick={() => setVoiceMode((v) => !v)}
              className="px-3 py-2 rounded flex items-center gap-1.5 transition-all hover:brightness-110 hover:scale-105"
              style={{
                background: voiceMode
                  ? "rgba(255, 136, 0, 0.15)"
                  : "var(--color-grafana-bg-panel)",
                border: voiceMode
                  ? "1px solid rgba(255,136,0,0.6)"
                  : "1px solid var(--color-grafana-border)",
                color: voiceMode
                  ? "#ff8800"
                  : "var(--color-grafana-text-secondary)",
              }}
              aria-label={voiceMode ? "Disable voice mode" : "Enable voice mode"}
              title={
                voiceMode
                  ? "Voice mode on — AI responds with summarised voice"
                  : "Voice mode off — enable to hear AI responses as summarised voice"
              }
            >
              {voiceMode ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
              <span className="hidden sm:inline text-xs">Voice</span>
            </button>
          )}

          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-3 py-2 md:px-4 md:py-2 rounded flex items-center gap-2 transition-all hover:brightness-110 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:brightness-100 disabled:hover:scale-100"
            style={{
              background: isLoading || !input.trim()
                ? "var(--color-grafana-border)"
                : "var(--color-grafana-blue)",
              color: "white",
            }}
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
      </form>
    </div>
  );
}

export default Chat;
