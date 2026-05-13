/**
 * ComfortAssistant - Compact wrapper for ComfortComplaintPanel
 *
 * Features:
 * - Compact form for quick desk complaint submission
 * - Shows recent complaints summary
 * - Links to full complaint panel for details
 */

import { useState } from "react";
import { MessageSquare, ThermometerSun, ThermometerSnowflake, Wind, Cloud } from "lucide-react";
import ComfortComplaintPanel from "../ComfortComplaintPanel";

interface ComfortAssistantProps {
  compact?: boolean;
  onViewDetails?: () => void;
}

export function ComfortAssistant({ compact = true, onViewDetails }: ComfortAssistantProps) {
  const [showFullPanel, setShowFullPanel] = useState(false);

  // Ultra-compact version - just a button that expands
  if (compact && !showFullPanel) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <Flex justifyContent="between" alignItems="center">
          <Flex alignItems="center" className="gap-3">
            <div
              className="p-2 rounded-lg"
              style={{ background: "rgba(245, 158, 11, 0.2)" }}
            >
              <MessageSquare
                className="w-5 h-5"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
            </div>
            <div>
              <Text className="font-medium">Comfort Complaints</Text>
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Too hot? Too cold? Report here
              </Text>
            </div>
          </Flex>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowFullPanel(true)}
          >
            Report Issue
          </Button>
        </Flex>

        {/* Quick complaint type icons */}
        <Flex className="mt-3 gap-2">
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
            style={{ background: "rgba(239, 68, 68, 0.12)", color: "var(--color-sentinel-red)" }}
            onClick={() => setShowFullPanel(true)}
          >
            <ThermometerSun className="w-3.5 h-3.5" />
            Too Hot
          </div>
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
            style={{ background: "rgba(59, 130, 246, 0.12)", color: "var(--color-sentinel-blue)" }}
            onClick={() => setShowFullPanel(true)}
          >
            <ThermometerSnowflake className="w-3.5 h-3.5" />
            Too Cold
          </div>
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
            style={{ background: "rgba(148, 163, 184, 0.12)", color: "var(--color-sentinel-text-secondary)" }}
            onClick={() => setShowFullPanel(true)}
          >
            <Cloud className="w-3.5 h-3.5" />
            Stuffy
          </div>
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
            style={{ background: "rgba(34, 211, 238, 0.12)", color: "var(--color-sentinel-cyan)" }}
            onClick={() => setShowFullPanel(true)}
          >
            <Wind className="w-3.5 h-3.5" />
            Drafty
          </div>
        </Flex>
      </div>
    );
  }

  // Full panel view
  return (
    <div className="space-y-4">
      {compact && (
        <Flex justifyContent="between" alignItems="center">
          <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Comfort Assistant</h3>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setShowFullPanel(false)}
          >
            Minimize
          </Button>
        </Flex>
      )}

      <ComfortComplaintPanel
        compact={compact}
        onViewDetails={onViewDetails}
      />
    </div>
  );
}

export default ComfortAssistant;
