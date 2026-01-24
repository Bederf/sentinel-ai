/**
 * ChatMessage Component - Displays individual chat messages
 *
 * User messages appear on the right with blue background.
 * Assistant messages appear on the left with gray background.
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
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-bidvest-blue-600 text-white rounded-br-sm"
            : "bg-gray-100 text-gray-900 rounded-bl-sm"
        }`}
      >
        {/* Message content with whitespace preserved */}
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {content}
          {/* Blinking cursor during streaming */}
          {isStreaming && (
            <span
              className="inline-block w-2 h-4 ml-1 bg-current animate-pulse"
              aria-label="typing"
            />
          )}
        </p>
      </div>
    </div>
  );
}

export default ChatMessage;
