/**
 * HighlightedNotes Component - Keyword highlighting in technician notes
 *
 * Shows AI's ability to extract insights from unstructured text:
 * - Red (Critical): "schedule replacement", "upper threshold", "failed", "failure"
 * - Orange (Warning): "wear", "increasing", "elevated", "recommend", "degradation"
 * - Blue (Observation): "cleaned", "tested", "topped up", "checked", "normal"
 */

import { FileText, AlertCircle, AlertTriangle, Info } from "lucide-react";

interface HighlightedNotesProps {
  notes: string[];
}

// Keyword categories with colors
const KEYWORD_CONFIG = {
  critical: {
    keywords: [
      "schedule replacement",
      "upper threshold",
      "failed",
      "failure",
      "replace",
      "replacement",
      "critical",
      "emergency",
      "immediate",
      "urgent",
    ],
    color: "var(--color-status-error)",
    bg: "rgba(242, 73, 92, 0.2)",
    icon: AlertCircle,
    label: "Critical",
  },
  warning: {
    keywords: [
      "wear",
      "wearing",
      "increasing",
      "elevated",
      "recommend",
      "recommendation",
      "degradation",
      "degrading",
      "monitor",
      "attention",
      "concern",
      "high",
      "above",
      "trending",
    ],
    color: "var(--color-status-warning)",
    bg: "rgba(255, 152, 48, 0.2)",
    icon: AlertTriangle,
    label: "Warning",
  },
  observation: {
    keywords: [
      "cleaned",
      "tested",
      "topped up",
      "checked",
      "normal",
      "within spec",
      "good condition",
      "operational",
      "completed",
      "verified",
      "inspected",
    ],
    color: "var(--color-sentinel-blue)",
    bg: "rgba(50, 116, 217, 0.2)",
    icon: Info,
    label: "Observation",
  },
};

// Function to highlight keywords in text
function highlightText(text: string): React.ReactNode[] {
  // Build a regex pattern for all keywords
  const allKeywords: { keyword: string; category: keyof typeof KEYWORD_CONFIG }[] = [];

  Object.entries(KEYWORD_CONFIG).forEach(([category, config]) => {
    config.keywords.forEach((keyword) => {
      allKeywords.push({ keyword, category: category as keyof typeof KEYWORD_CONFIG });
    });
  });

  // Sort by length (longer keywords first to avoid partial matches)
  allKeywords.sort((a, b) => b.keyword.length - a.keyword.length);

  // Create regex pattern
  const pattern = new RegExp(
    `(${allKeywords.map((k) => k.keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi"
  );

  const parts = text.split(pattern);
  const result: React.ReactNode[] = [];

  parts.forEach((part, index) => {
    if (!part) return;

    // Check if this part matches any keyword
    const lowerPart = part.toLowerCase();
    const matchedKeyword = allKeywords.find((k) => k.keyword.toLowerCase() === lowerPart);

    if (matchedKeyword) {
      const config = KEYWORD_CONFIG[matchedKeyword.category];
      result.push(
        <span
          key={index}
          className="px-1 py-0.5 rounded font-medium"
          style={{
            background: config.bg,
            color: config.color,
          }}
        >
          {part}
        </span>
      );
    } else {
      result.push(
        <span key={index} style={{ color: "var(--color-sentinel-text-primary)" }}>
          {part}
        </span>
      );
    }
  });

  return result;
}

// Function to extract date from note
function extractDateFromNote(note: string): string | null {
  const dateMatch = note.match(/^(\d{4}-\d{2}-\d{2}|\w+ \d{1,2},? \d{4}|\d{1,2}\/\d{1,2}\/\d{2,4})/);
  if (dateMatch) {
    return dateMatch[1];
  }
  // Try to find date after common prefixes
  const prefixMatch = note.match(/^([^:]+):/);
  if (prefixMatch) {
    return prefixMatch[1];
  }
  return null;
}

// Function to get note content without date
function getNoteContent(note: string): string {
  const colonIndex = note.indexOf(":");
  if (colonIndex > 0 && colonIndex < 30) {
    return note.slice(colonIndex + 1).trim();
  }
  return note;
}

// Function to count keywords by category
function countKeywords(notes: string[]): Record<string, number> {
  const counts: Record<string, number> = { critical: 0, warning: 0, observation: 0 };

  const fullText = notes.join(" ").toLowerCase();

  Object.entries(KEYWORD_CONFIG).forEach(([category, config]) => {
    config.keywords.forEach((keyword) => {
      const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      const matches = fullText.match(regex);
      if (matches) {
        counts[category] += matches.length;
      }
    });
  });

  return counts;
}

export function HighlightedNotes({ notes }: HighlightedNotesProps) {
  const keywordCounts = countKeywords(notes);

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
          <h3
            className="font-semibold text-sm"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Technician Notes Analysis
          </h3>
        </div>

        {/* Keyword counts */}
        <div className="flex items-center gap-2">
          {Object.entries(KEYWORD_CONFIG).map(([category, config]) => {
            const count = keywordCounts[category];
            if (count === 0) return null;

            const Icon = config.icon;
            return (
              <div
                key={category}
                className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
                style={{ background: config.bg, color: config.color }}
                title={`${count} ${config.label.toLowerCase()} keyword${count > 1 ? "s" : ""} found`}
              >
                <Icon className="h-3 w-3" />
                <span className="font-medium">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div
        className="px-4 py-2 flex flex-wrap gap-4 text-xs"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          borderBottom: "1px solid var(--color-sentinel-border)",
        }}
      >
        {Object.entries(KEYWORD_CONFIG).map(([category, config]) => {
          const Icon = config.icon;
          return (
            <div key={category} className="flex items-center gap-1.5">
              <Icon className="h-3 w-3" style={{ color: config.color }} />
              <span
                className="px-1.5 py-0.5 rounded"
                style={{ background: config.bg, color: config.color }}
              >
                {config.label}
              </span>
            </div>
          );
        })}
        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>
          — AI-detected indicators
        </span>
      </div>

      {/* Notes */}
      <div className="p-4 space-y-4">
        {notes.map((note, index) => {
          const dateLabel = extractDateFromNote(note);
          const content = getNoteContent(note);

          return (
            <div key={index} className="flex gap-3">
              <div
                className="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              >
                <FileText
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                />
              </div>
              <div className="flex-1 min-w-0">
                {dateLabel && (
                  <div
                    className="text-xs mb-1"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {dateLabel}
                  </div>
                )}
                <p className="text-sm leading-relaxed">{highlightText(content)}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* AI Insight Footer */}
      <div
        className="px-4 py-3"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          borderTop: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-start gap-2">
          <Info
            className="h-4 w-4 flex-shrink-0 mt-0.5"
            style={{ color: "var(--color-sentinel-cyan)" }}
          />
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            <strong style={{ color: "var(--color-sentinel-cyan)" }}>AI Insight:</strong> The
            highlighted keywords were automatically extracted by the AI model to identify
            progressive warning signs and maintenance patterns from unstructured technician notes.
          </p>
        </div>
      </div>
    </div>
  );
}

export default HighlightedNotes;
