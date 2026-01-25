/**
 * ChatMessage Component - Grafana-inspired message display
 *
 * User messages appear on the right with accent blue background.
 * Assistant messages appear on the left with dark panel background.
 * Shows a blinking cursor during streaming.
 */

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function ChatMessage({ role, content, isStreaming }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
      role="listitem"
    >
      <div
        className="max-w-[80%] rounded-lg px-4 py-3"
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
        {/* Message content with whitespace preserved */}
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {content}
          {/* Blinking cursor during streaming */}
          {isStreaming && (
            <span
              className="inline-block w-2 h-4 ml-1 animate-pulse"
              style={{ background: "var(--color-grafana-orange)" }}
              aria-label="typing"
            />
          )}
        </p>
      </div>
    </div>
  );
}

export default ChatMessage;
