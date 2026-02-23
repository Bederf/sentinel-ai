/**
 * ChatMessage Component - Grafana-inspired message display
 *
 * User messages appear on the right with accent blue background.
 * Assistant messages appear on the left with dark panel background.
 * Shows a blinking cursor during streaming.
 * Renders markdown content for assistant messages with improved formatting.
 * Typewriter effect: Characters appear one-by-one during streaming for readability.
 */

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Volume2, Loader2 } from "lucide-react";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  messageId?: string;
  /** Callback to speak the message text (only for assistant messages with TTS) */
  onSpeak?: (text: string, messageId: string) => void;
  /** TTS state for this specific message */
  ttsState?: { isLoading: boolean; isPlaying: boolean };
}

export function ChatMessage({ role, content, isStreaming, messageId, onSpeak, ttsState }: ChatMessageProps) {
  const isUser = role === "user";
  const [displayedContent, setDisplayedContent] = useState("");
  const [charIndex, setCharIndex] = useState(0);

  // Typewriter effect: animate characters one-by-one during streaming
  useEffect(() => {
    // If not streaming, show full content immediately
    if (!isStreaming) {
      setDisplayedContent(content);
      setCharIndex(0);
      return;
    }

    // If streaming, animate characters with slight delay (30ms per char)
    if (charIndex < content.length) {
      const timer = setTimeout(() => {
        setDisplayedContent(content.slice(0, charIndex + 1));
        setCharIndex(charIndex + 1);
      }, 30); // 30ms delay per character

      return () => clearTimeout(timer);
    }
  }, [content, charIndex, isStreaming]);

  // Preprocess markdown content to improve structure
  const preprocessMarkdown = (text: string): string => {
    let processed = text;

    // Fix common markdown issues
    // Fix "**text**" that appears without proper spacing
    processed = processed.replace(/(\S)\*\*(\w)/g, "$1 **$2");
    processed = processed.replace(/(\w)\*\*(\S)/g, "$1** $2");

    // Ensure proper line breaks before headings
    processed = processed.replace(/([^\n])\n(#{1,6}\s)/g, "$1\n\n$2");

    // Ensure proper spacing around lists
    processed = processed.replace(/([^\n])\n([-*]\s)/g, "$1\n\n$2");
    processed = processed.replace(/([^\n])\n(\d+\.\s)/g, "$1\n\n$2");

    // Fix double asterisks that aren't properly closed
    processed = processed.replace(/\*\*([^*]+)\*\*/g, "**$1**");

    // Add spacing after headings
    processed = processed.replace(/(#{1,6}\s+[^\n]+)\n([^\n#])/g, "$1\n\n$2");

    return processed;
  };

  // Use displayed content (typewriter effect) during streaming, full content when done
  const contentToRender = isStreaming ? displayedContent : content;
  const processedContent = isUser ? contentToRender : preprocessMarkdown(contentToRender);

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
      role="listitem"
    >
      <div
        className="max-w-[85%] md:max-w-[80%] rounded-lg px-4 py-3"
        style={{
          background: isUser
            ? "var(--color-grafana-blue)"
            : "var(--color-grafana-bg-secondary)",
          color: isUser ? "white" : "var(--color-grafana-text-primary)",
          borderBottomRightRadius: isUser ? "4px" : undefined,
          borderBottomLeftRadius: !isUser ? "4px" : undefined,
          border: !isUser ? "1px solid var(--color-grafana-border)" : undefined,
        }}
      >
        {/* User messages: plain text */}
        {isUser ? (
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {content}
          </p>
        ) : (
          /* Assistant messages: render markdown with improved structure */
          <div className="break-words" style={{ fontSize: "0.875rem", lineHeight: "1.6" }}>
            <ReactMarkdown
              components={{
                // Style headings with better hierarchy
                h1: ({ ...props }) => (
                  <h1
                    className="font-semibold mb-3 mt-4 first:mt-0"
                    style={{
                      fontSize: "1.125rem",
                      color: "var(--color-grafana-text-primary)",
                      borderBottom: "1px solid var(--color-grafana-border)",
                      paddingBottom: "0.5rem",
                    }}
                    {...props}
                  />
                ),
                h2: ({ ...props }) => (
                  <h2
                    className="font-semibold mb-2 mt-4 first:mt-0"
                    style={{
                      fontSize: "1rem",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                h3: ({ ...props }) => (
                  <h3
                    className="font-semibold mb-2 mt-3 first:mt-0"
                    style={{
                      fontSize: "0.9375rem",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                // Style paragraphs with better spacing
                p: ({ ...props }) => (
                  <p
                    className="mb-3 last:mb-0"
                    style={{
                      color: "var(--color-grafana-text-primary)",
                      lineHeight: "1.6",
                    }}
                    {...props}
                  />
                ),
                // Style lists with better spacing and indentation
                ul: ({ ...props }) => (
                  <ul
                    className="mb-3 ml-4 space-y-1.5 last:mb-0"
                    style={{
                      listStyleType: "disc",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                ol: ({ ...props }) => (
                  <ol
                    className="mb-3 ml-4 space-y-1.5 last:mb-0"
                    style={{
                      listStyleType: "decimal",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                li: ({ ...props }) => (
                  <li
                    className="pl-1"
                    style={{
                      color: "var(--color-grafana-text-primary)",
                      lineHeight: "1.6",
                    }}
                    {...props}
                  />
                ),
                // Style code blocks
                code: ({ inline, ...props }: { inline?: boolean; className?: string; children?: React.ReactNode }) =>
                  inline ? (
                    <code
                      className="px-1.5 py-0.5 rounded text-xs font-mono"
                      style={{
                        background: "rgba(0, 0, 0, 0.25)",
                        color: "var(--color-grafana-orange)",
                        border: "1px solid rgba(0, 0, 0, 0.1)",
                      }}
                      {...props}
                    />
                  ) : (
                    <code
                      className="block p-3 rounded text-xs font-mono mb-3 overflow-x-auto"
                      style={{
                        background: "rgba(0, 0, 0, 0.25)",
                        color: "var(--color-grafana-text-primary)",
                        border: "1px solid var(--color-grafana-border)",
                        lineHeight: "1.5",
                      }}
                      {...props}
                    />
                  ),
                // Style strong (bold) text with better visibility
                strong: ({ ...props }) => (
                  <strong
                    className="font-semibold"
                    style={{
                      color: "var(--color-grafana-orange)",
                      fontWeight: "600",
                    }}
                    {...props}
                  />
                ),
                // Style emphasis (italic)
                em: ({ ...props }) => (
                  <em
                    className="italic"
                    style={{
                      color: "var(--color-grafana-text-primary)",
                      fontStyle: "italic",
                    }}
                    {...props}
                  />
                ),
                // Style links
                a: ({ ...props }) => (
                  <a
                    className="underline"
                    style={{
                      color: "var(--color-grafana-blue)",
                      textDecoration: "underline",
                    }}
                    {...props}
                  />
                ),
                // Style horizontal rules for section breaks
                hr: ({ ...props }) => (
                  <hr
                    className="my-4 border-0"
                    style={{
                      borderTop: "1px solid var(--color-grafana-border)",
                    }}
                    {...props}
                  />
                ),
                // Style blockquotes
                blockquote: ({ ...props }) => (
                  <blockquote
                    className="border-l-4 pl-4 my-3 italic"
                    style={{
                      borderLeftColor: "var(--color-grafana-blue)",
                      color: "var(--color-grafana-text-secondary)",
                    }}
                    {...props}
                  />
                ),
              }}
            >
              {processedContent}
            </ReactMarkdown>
            {/* Blinking cursor during streaming */}
            {isStreaming && (
              <span
                className="inline-block w-2 h-4 ml-1 animate-pulse"
                style={{ background: "var(--color-grafana-orange)" }}
                aria-label="typing"
              />
            )}
            {/* EU AI Act Article 50 — AI-generated content disclosure */}
            {!isStreaming && (
              <p className="mt-2 text-xs" style={{ color: "var(--color-grafana-text-secondary)", opacity: 0.7 }}>
                AI-generated &middot; Review before acting
              </p>
            )}
            {/* Speaker button for TTS (non-streaming assistant messages only) */}
            {onSpeak && !isStreaming && messageId && (
              <button
                type="button"
                onClick={() => onSpeak(content, messageId)}
                disabled={ttsState?.isLoading}
                className="flex items-center gap-1.5 mt-2 px-2 py-1 rounded text-xs transition-all hover:brightness-110"
                style={{
                  background: ttsState?.isPlaying
                    ? "rgba(50, 116, 217, 0.2)"
                    : "transparent",
                  border: "1px solid var(--color-grafana-border)",
                  color: ttsState?.isPlaying
                    ? "var(--color-grafana-blue)"
                    : "var(--color-grafana-text-secondary)",
                  cursor: ttsState?.isLoading ? "wait" : "pointer",
                }}
                aria-label={ttsState?.isPlaying ? "Stop audio" : "Listen to response"}
              >
                {ttsState?.isLoading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Volume2 className="w-3 h-3" />
                )}
                <span>
                  {ttsState?.isLoading
                    ? "Loading..."
                    : ttsState?.isPlaying
                      ? "Playing..."
                      : "Listen"}
                </span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
