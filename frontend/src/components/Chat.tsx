/**
 * Chat Component - Main chat interface with message history and input
 *
 * Features:
 * - Message history display with auto-scroll
 * - Input field with Enter key support
 * - SSE stream consumption for real-time responses
 * - Loading state during AI response
 */

import { useState, useRef, useEffect } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Send } from "lucide-react";
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
      
      // Stream the response
      await streamChat(trimmedInput, undefined, (chunk) => {
        fullResponse += chunk;
        setStreamingContent(fullResponse);
      });

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

  // Handle Enter key (Shift+Enter for newline would need textarea)
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-container flex flex-col h-full bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4" role="list" aria-label="Chat messages">
        {messages.length === 0 && !isLoading && (
          <div className="h-full flex items-center justify-center text-gray-400">
            <p>Start a conversation with the FM Assistant</p>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
          />
        ))}

        {/* Streaming message */}
        {isLoading && streamingContent && (
          <ChatMessage
            role="assistant"
            content={streamingContent}
            isStreaming={true}
          />
        )}

        {/* Loading indicator when waiting for first chunk */}
        {isLoading && !streamingContent && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-100 rounded-lg px-4 py-3 rounded-bl-sm">
              <div className="flex items-center gap-2 text-gray-600">
                <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                <span className="text-sm">AI is thinking...</span>
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
        className="border-t border-gray-200 p-4 bg-gray-50"
      >
        <div className="flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about building management..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-bidvest-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
            aria-label="Chat message input"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-bidvest-blue-600 text-white rounded-lg hover:bg-bidvest-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
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
