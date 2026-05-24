/**
 * ChatMessage Component - Grafana-inspired message display
 *
 * User messages appear on the right with accent blue background.
 * Assistant messages appear on the left with dark panel background.
 * Shows a blinking cursor during streaming.
 * Renders markdown content for assistant messages with improved formatting.
 * Typewriter effect: Characters appear one-by-one during streaming for readability.
 */

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Volume2, Loader2 } from "lucide-react";

/** Regex to detect slash commands in inline code: /info-S002-FCU-301 etc. */
const COMMAND_RE = /^\/(info|WO|inspect|reset|note)-[A-Za-z0-9][\w]*$/;

/** Regex to detect equipment IDs like S002-CHILLER-B1-001 */
const EQUIPMENT_ID_RE = /^S\d{3}-[A-Z0-9]+(?:-[A-Za-z0-9]+)+$/;
const EQUIPMENT_REPLACE_RE = /(?<!\w)(S\d{3}-[A-Z0-9]+(?:-[A-Za-z0-9]+)+)(?!\w)/g;

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  messageId?: string;
  /** Callback to speak the message text (only for assistant messages with TTS) */
  onSpeak?: (text: string, messageId: string) => void;
  /** TTS state for this specific message */
  ttsState?: { isLoading: boolean; isPlaying: boolean };
  /** Callback when a slash command button is clicked */
  onCommandClick?: (command: string) => void;
  /** Callback when an equipment ID is clicked — inserts into chat input */
  onEquipmentClick?: (equipmentId: string) => void;
}

export function ChatMessage({ role, content, isStreaming, messageId, onSpeak, ttsState, onCommandClick, onEquipmentClick }: ChatMessageProps) {
  const isUser = role === "user";
  const [displayedContent, setDisplayedContent] = useState(isUser ? content : "");
  const charIndexRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const [animDone, setAnimDone] = useState(isUser);

  // Typewriter effect: progressively reveal content word-by-word
  useEffect(() => {
    if (isUser) {
      setDisplayedContent(content);
      return;
    }

    // Nothing to show yet (waiting for first chunk)
    if (!content) return;

    // Already caught up — nothing to animate
    if (charIndexRef.current >= content.length) {
      setDisplayedContent(content);
      if (!isStreaming) setAnimDone(true);
      return;
    }

    // Animate: advance a few characters per frame (~60fps)
    const step = () => {
      const target = content;
      if (charIndexRef.current >= target.length) {
        setDisplayedContent(target);
        if (!isStreaming) setAnimDone(true);
        return;
      }
      // Advance 2-4 chars per frame (feels like fast typing)
      const advance = Math.min(3, target.length - charIndexRef.current);
      charIndexRef.current += advance;
      setDisplayedContent(target.slice(0, charIndexRef.current));
      rafRef.current = requestAnimationFrame(step);
    };

    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [content, isStreaming, isUser]);

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

    // Strip square brackets around equipment IDs (AI often wraps in [code])
    processed = processed.replace(/\[(S\d{3}-[A-Z0-9]+(?:-[A-Za-z0-9]+)+)\]/g, '$1');
    // Wrap equipment IDs in backticks so they render as clickable inline code
    if (onEquipmentClick) {
      processed = processed.replace(EQUIPMENT_REPLACE_RE, '`$1`');
    }

    return processed;
  };

  // Use displayed content (typewriter effect) until animation completes
  const contentToRender = animDone ? content : displayedContent;
  const processedContent = isUser ? contentToRender : preprocessMarkdown(contentToRender);

  return (
      <div
        className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
        role="listitem"
        style={{ userSelect: "text" }}
      >
        <div
          className="max-w-[85%] md:max-w-[80%] rounded-lg px-4 py-3"
          style={{
            userSelect: "text",
            background: isUser
              ? "var(--color-sentinel-blue)"
              : "var(--color-sentinel-bg-secondary)",
            color: isUser ? "white" : "var(--color-sentinel-text-primary)",
            borderBottomRightRadius: isUser ? "4px" : undefined,
            borderBottomLeftRadius: !isUser ? "4px" : undefined,
            border: !isUser ? "1px solid var(--color-sentinel-border)" : undefined,
          }}
      >
        {/* User messages: plain text */}
        {isUser ? (
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {content}
          </p>
        ) : isStreaming && !content ? (
          /* Thinking indicator while waiting for first chunk */
          <div className="flex items-center gap-2">
            <div
              className="animate-spin h-4 w-4 border-2 border-t-transparent rounded-full"
              style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }}
            />
            <span
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              SENTINEL is thinking...
            </span>
          </div>
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
                      color: "var(--color-sentinel-text-primary)",
                      borderBottom: "1px solid var(--color-sentinel-border)",
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
                      color: "var(--color-sentinel-text-primary)",
                    }}
                    {...props}
                  />
                ),
                h3: ({ ...props }) => (
                  <h3
                    className="font-semibold mb-2 mt-3 first:mt-0"
                    style={{
                      fontSize: "0.9375rem",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                    {...props}
                  />
                ),
                // Style paragraphs with better spacing
                p: ({ ...props }) => (
                  <p
                    className="mb-3 last:mb-0"
                    style={{
                      color: "var(--color-sentinel-text-primary)",
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
                      color: "var(--color-sentinel-text-primary)",
                    }}
                    {...props}
                  />
                ),
                ol: ({ ...props }) => (
                  <ol
                    className="mb-3 ml-4 space-y-1.5 last:mb-0"
                    style={{
                      listStyleType: "decimal",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                    {...props}
                  />
                ),
                li: ({ ...props }) => (
                  <li
                    className="pl-1"
                    style={{
                      color: "var(--color-sentinel-text-primary)",
                      lineHeight: "1.6",
                    }}
                    {...props}
                  />
                ),
                // Style code blocks — slash commands rendered as clickable buttons
                code: ({ inline, children, ...props }: { inline?: boolean; className?: string; children?: React.ReactNode }) => {
                  const text = String(children ?? "").replace(/\n$/, "");
                  if (inline && onCommandClick && COMMAND_RE.test(text)) {
                    return (
                      <button
                        type="button"
                        onClick={() => onCommandClick(text)}
                        className="px-2 py-0.5 rounded text-xs font-mono cursor-pointer transition-all hover:brightness-125"
                        style={{
                          background: "rgba(50, 116, 217, 0.15)",
                          color: "var(--color-sentinel-blue)",
                          border: "1px solid rgba(50, 116, 217, 0.3)",
                        }}
                      >
                        {text}
                      </button>
                    );
                  }
                  // Equipment IDs rendered as clickable spans (inserts into chat input)
                  if (inline && onEquipmentClick && EQUIPMENT_ID_RE.test(text)) {
                    return (
                      <span
                        onClick={() => onEquipmentClick(text)}
                        className="px-2 py-0.5 rounded text-xs font-mono cursor-pointer transition-all hover:brightness-125 select-all"
                        style={{
                          background: "rgba(16, 185, 129, 0.15)",
                          color: "var(--color-sentinel-green)",
                          border: "1px solid rgba(16, 185, 129, 0.3)",
                        }}
                      >
                        {text}
                      </span>
                    );
                  }
                  return inline ? (
                    <code
                      className="px-1.5 py-0.5 rounded text-xs font-mono"
                      style={{
                        background: "rgba(0, 0, 0, 0.25)",
                        color: "var(--color-sentinel-orange)",
                        border: "1px solid rgba(0, 0, 0, 0.1)",
                      }}
                      {...props}
                    >
                      {children}
                    </code>
                  ) : (
                    <code
                      className="block p-3 rounded text-xs font-mono mb-3 overflow-x-auto"
                      style={{
                        background: "rgba(0, 0, 0, 0.25)",
                        color: "var(--color-sentinel-text-primary)",
                        border: "1px solid var(--color-sentinel-border)",
                        lineHeight: "1.5",
                      }}
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
                // Style strong (bold) text with better visibility
                strong: ({ ...props }) => (
                  <strong
                    className="font-semibold"
                    style={{
                      color: "var(--color-sentinel-orange)",
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
                      color: "var(--color-sentinel-text-primary)",
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
                      color: "var(--color-sentinel-blue)",
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
                      borderTop: "1px solid var(--color-sentinel-border)",
                    }}
                    {...props}
                  />
                ),
                // Style blockquotes
                blockquote: ({ ...props }) => (
                  <blockquote
                    className="border-l-4 pl-4 my-3 italic"
                    style={{
                      borderLeftColor: "var(--color-sentinel-blue)",
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                    {...props}
                  />
                ),
              }}
            >
              {processedContent}
            </ReactMarkdown>
            {/* Blinking cursor while animating */}
            {!animDone && (
              <span
                className="inline-block w-2 h-4 ml-1 animate-pulse"
                style={{ background: "var(--color-sentinel-orange)" }}
                aria-label="typing"
              />
            )}
            {/* EU AI Act Article 50 — AI-generated content disclosure */}
            {animDone && (
              <p className="mt-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)", opacity: 0.7 }}>
                AI-generated &middot; Review before acting
              </p>
            )}
            {/* Speaker button for TTS (after animation completes) */}
            {onSpeak && animDone && messageId && (
              <button
                type="button"
                onClick={() => onSpeak(content, messageId)}
                disabled={ttsState?.isLoading}
                className="flex items-center gap-1.5 mt-2 px-2 py-1 rounded text-xs transition-all hover:brightness-110"
                style={{
                  background: ttsState?.isPlaying
                    ? "rgba(50, 116, 217, 0.2)"
                    : "transparent",
                  border: "1px solid var(--color-sentinel-border)",
                  color: ttsState?.isPlaying
                    ? "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-text-secondary)",
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
