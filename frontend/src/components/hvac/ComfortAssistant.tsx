/**
 * ComfortAssistant - Compact wrapper for ComfortComplaintPanel
 *
 * Features:
 * - Compact form for quick desk complaint submission
 * - Shows recent complaints summary
 * - Links to full complaint panel for details
 */

import { useState } from "react";
import { Text, Flex, Button } from "@tremor/react";
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
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
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
              <Text className="text-xs text-gray-400">
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
        <Flex className="mt-3 gap-3">
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer hover:bg-white/10"
            onClick={() => setShowFullPanel(true)}
          >
            <ThermometerSun className="w-4 h-4 text-red-400" />
            <span className="text-red-300">Too Hot</span>
          </div>
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer hover:bg-white/10"
            onClick={() => setShowFullPanel(true)}
          >
            <ThermometerSnowflake className="w-4 h-4 text-blue-400" />
            <span className="text-blue-300">Too Cold</span>
          </div>
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer hover:bg-white/10"
            onClick={() => setShowFullPanel(true)}
          >
            <Cloud className="w-4 h-4 text-gray-400" />
            <span className="text-gray-300">Stuffy</span>
          </div>
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer hover:bg-white/10"
            onClick={() => setShowFullPanel(true)}
          >
            <Wind className="w-4 h-4 text-cyan-400" />
            <span className="text-cyan-300">Drafty</span>
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
          <Title>Comfort Assistant</Title>
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
