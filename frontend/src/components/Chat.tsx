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
import { Send, MessageSquare, Bot, BookOpen } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { streamChat } from "../lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [searchDocs, setSearchDocs] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Generate unique ID for messages
  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  // Handle form submission
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    const trimmedInput = input.trim();
    if (!trimmedInput || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: trimmedInput,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setStreamingContent("");

    try {
      let fullResponse = "";

      // Stream the response (pass searchDocs to enable documentation mode)
      await streamChat(trimmedInput, undefined, (chunk) => {
        fullResponse += chunk;
        setStreamingContent(fullResponse);
      }, searchDocs);

      // When streaming completes, add assistant message with full content
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: fullResponse,
        },
      ]);
    } catch (error) {
      console.error("Chat error:", error);
      // Add error message
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: "Sorry, I encountered an error. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
      setStreamingContent("");
      // Refocus input after response
      inputRef.current?.focus();
    }
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
        className="flex-none p-4 flex items-center gap-3"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
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
                {searchDocs
                  ? "Ask about SENTINEL features, capabilities, or how things work"
                  : "Ask about equipment status, alerts, or maintenance insights"}
              </p>
              {!searchDocs && (
                <p
                  className="text-xs mt-1"
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                >
                  Toggle <strong>Docs</strong> to search system documentation
                </p>
              )}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} role={msg.role} content={msg.content} />
        ))}

        {/* Streaming message */}
        {isLoading && streamingContent && (
          <ChatMessage role="assistant" content={streamingContent} isStreaming={true} />
        )}

        {/* Loading indicator when waiting for first chunk */}
        {isLoading && !streamingContent && (
          <div className="flex justify-start mb-4">
            <div
              className="rounded-lg px-4 py-3"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
              }}
            >
              <div className="flex items-center gap-2">
                <div
                  className="animate-spin h-4 w-4 border-2 border-t-transparent rounded-full"
                  style={{ borderColor: "var(--color-grafana-blue)", borderTopColor: "transparent" }}
                />
                <span
                  className="text-sm"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  SENTINEL is thinking...
                </span>
              </div>
            </div>
          </div>
        )}

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
        {/* Documentation toggle */}
        <div className="flex items-center gap-2 mb-3">
          <button
            type="button"
            onClick={() => setSearchDocs(!searchDocs)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-all"
            style={{
              background: searchDocs
                ? "rgba(50, 116, 217, 0.2)"
                : "var(--color-grafana-bg-panel)",
              border: searchDocs
                ? "1px solid var(--color-grafana-blue)"
                : "1px solid var(--color-grafana-border)",
              color: searchDocs
                ? "var(--color-grafana-blue)"
                : "var(--color-grafana-text-secondary)",
            }}
            title={searchDocs ? "Documentation mode: ON" : "Documentation mode: OFF"}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Docs</span>
            <span
              className="w-2 h-2 rounded-full"
              style={{
                background: searchDocs
                  ? "var(--color-grafana-blue)"
                  : "var(--color-grafana-text-disabled)",
              }}
            />
          </button>
          {searchDocs && (
            <span
              className="text-xs"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Searching SENTINEL documentation
            </span>
          )}
        </div>

        <div className="flex gap-2 md:gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={searchDocs ? "Ask about SENTINEL features..." : "Ask about building management..."}
            disabled={isLoading}
            className="flex-1 px-3 py-2 md:px-4 md:py-2 text-sm md:text-base rounded focus:outline-none disabled:cursor-not-allowed"
            style={{
              background: "var(--color-grafana-bg-panel)",
              border: "1px solid var(--color-grafana-border)",
              color: "var(--color-grafana-text-primary)",
            }}
            aria-label="Chat message input"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-3 py-2 md:px-4 md:py-2 rounded flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
