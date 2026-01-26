/**
 * ChatMessage Component - Grafana-inspired message display
 *
 * User messages appear on the right with accent blue background.
 * Assistant messages appear on the left with dark panel background.
 * Shows a blinking cursor during streaming.
 * Renders markdown content for assistant messages with improved formatting.
 */

import ReactMarkdown from "react-markdown";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function ChatMessage({ role, content, isStreaming }: ChatMessageProps) {
  const isUser = role === "user";

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

  const processedContent = isUser ? content : preprocessMarkdown(content);

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
                h1: ({ node, ...props }) => (
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
                h2: ({ node, ...props }) => (
                  <h2
                    className="font-semibold mb-2 mt-4 first:mt-0"
                    style={{
                      fontSize: "1rem",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                h3: ({ node, ...props }) => (
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
                p: ({ node, ...props }) => (
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
                ul: ({ node, ...props }) => (
                  <ul
                    className="mb-3 ml-4 space-y-1.5 last:mb-0"
                    style={{
                      listStyleType: "disc",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                ol: ({ node, ...props }) => (
                  <ol
                    className="mb-3 ml-4 space-y-1.5 last:mb-0"
                    style={{
                      listStyleType: "decimal",
                      color: "var(--color-grafana-text-primary)",
                    }}
                    {...props}
                  />
                ),
                li: ({ node, ...props }) => (
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
                code: ({ node, inline, ...props }: any) =>
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
                strong: ({ node, ...props }) => (
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
                em: ({ node, ...props }) => (
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
                a: ({ node, ...props }) => (
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
                hr: ({ node, ...props }) => (
                  <hr
                    className="my-4 border-0"
                    style={{
                      borderTop: "1px solid var(--color-grafana-border)",
                    }}
                    {...props}
                  />
                ),
                // Style blockquotes
                blockquote: ({ node, ...props }) => (
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
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
