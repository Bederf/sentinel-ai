/**
 * CardLibrary Component - Floating overlay for dashboard card customization
 *
 * Features:
 * - Compact toggle button stays inline
 * - Expanded content floats as overlay (doesn't push content down)
 * - Toggle switches to show/hide intelligence cards
 * - Grouped by category (KPI, Intelligence Sections)
 * - Badge showing hidden count
 * - Click outside to close
 */

import { useState, useRef, useEffect } from 'react';
import {
  LayoutGrid,
  Eye,
  EyeOff,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  X,
} from 'lucide-react';
import { KPI_CARDS, SECTION_CARDS, type CardDefinition } from '../lib/cardDefinitions';

interface CardLibraryProps {
  visibleKpiCards: string[];
  visibleSections: string[];
  onKpiVisibilityChange: (cardId: string, visible: boolean) => void;
  onSectionVisibilityChange: (sectionId: string, visible: boolean) => void;
  onResetToDefaults: () => void;
  isSaving?: boolean;
}

export default function CardLibrary({
  visibleKpiCards,
  visibleSections,
  onKpiVisibilityChange,
  onSectionVisibilityChange,
  onResetToDefaults,
  isSaving = false,
}: CardLibraryProps) {
  const [expanded, setExpanded] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const totalCards = KPI_CARDS.length + SECTION_CARDS.length;
  const visibleCount = visibleKpiCards.length + visibleSections.length;
  const hiddenCount = totalCards - visibleCount;

  // Close on click outside
  useEffect(() => {
    if (!expanded) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [expanded]);

  const handleReset = () => {
    onResetToDefaults();
    setShowResetConfirm(false);
  };

  const renderCardToggle = (
    card: CardDefinition,
    isVisible: boolean,
    onToggle: (id: string, visible: boolean) => void
  ) => {
    return (
      <div
        key={card.id}
        className="flex items-center justify-between py-2 px-3 rounded transition-colors"
        style={{
          background: isVisible ? 'rgba(59, 130, 246, 0.05)' : 'transparent',
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="p-1 rounded"
            style={{
              color: isVisible ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-secondary)',
            }}
          >
            {card.icon}
          </div>
          <span
            className="text-sm"
            style={{
              color: isVisible ? 'var(--color-sentinel-text-primary)' : 'var(--color-sentinel-text-secondary)',
            }}
          >
            {card.name}
          </span>
        </div>

        <button
          onClick={() => onToggle(card.id, !isVisible)}
          className="p-1.5 rounded transition-all hover:scale-110 active:scale-95"
          style={{
            background: isVisible ? 'rgba(59, 130, 246, 0.2)' : 'rgba(100, 116, 139, 0.2)',
            color: isVisible ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-secondary)',
            border: 'none',
            cursor: 'pointer',
          }}
          title={isVisible ? 'Hide' : 'Show'}
        >
          {isVisible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>
      </div>
    );
  };

  return (
    <div className="relative mb-4" ref={panelRef}>
      {/* Toggle button — always in flow */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors hover:brightness-110"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
          cursor: 'pointer',
        }}
      >
        <LayoutGrid className="w-4 h-4" style={{ color: 'var(--color-sentinel-amber)' }} />
        <span
          className="text-sm font-medium"
          style={{ color: 'var(--color-sentinel-text-primary)' }}
        >
          Customize Panels
        </span>
        {hiddenCount > 0 && (
          <span
            className="text-xs px-1.5 py-0.5 rounded-full font-medium"
            style={{
              background: 'rgba(245, 158, 11, 0.15)',
              color: 'var(--color-sentinel-amber)',
            }}
          >
            {hiddenCount} hidden
          </span>
        )}
        {isSaving && (
          <div
            className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          />
        )}
        {expanded ? (
          <ChevronDown className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
        ) : (
          <ChevronRight className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
        )}
      </button>

      {/* Floating overlay panel */}
      {expanded && (
        <div
          className="absolute top-full left-0 mt-2 w-80 rounded-lg shadow-md z-50 max-h-[70vh] overflow-y-auto"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          {/* Panel header with close */}
          <div
            className="flex items-center justify-between p-3 sticky top-0"
            style={{
              background: 'var(--color-sentinel-bg-panel)',
              borderBottom: '1px solid var(--color-sentinel-border)',
            }}
          >
            <span className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Customize Panels
            </span>
            <button
              onClick={() => setExpanded(false)}
              className="p-1 rounded hover:brightness-110"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-sentinel-text-secondary)' }}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="p-3 space-y-4">
            {/* KPI Cards */}
            <div>
              <h3
                className="text-xs font-medium uppercase tracking-wider mb-2 px-1"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                KPI Cards
              </h3>
              <div className="space-y-1">
                {KPI_CARDS.map((card) =>
                  renderCardToggle(card, visibleKpiCards.includes(card.id), onKpiVisibilityChange)
                )}
              </div>
            </div>

            {/* Intelligence Sections */}
            <div>
              <h3
                className="text-xs font-medium uppercase tracking-wider mb-2 px-1"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Intelligence Cards
              </h3>
              <div className="space-y-1">
                {SECTION_CARDS.map((card) =>
                  renderCardToggle(card, visibleSections.includes(card.id), onSectionVisibilityChange)
                )}
              </div>
            </div>

            {/* Reset */}
            <div className="pt-2" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
              {showResetConfirm ? (
                <div className="flex items-center gap-2">
                  <span
                    className="text-xs flex-1"
                    style={{ color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    Reset all to defaults?
                  </span>
                  <button
                    onClick={() => setShowResetConfirm(false)}
                    className="px-2 py-1 rounded text-xs"
                    style={{
                      background: 'var(--color-sentinel-bg-secondary)',
                      color: 'var(--color-sentinel-text-secondary)',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleReset}
                    className="px-2 py-1 rounded text-xs font-medium"
                    style={{
                      background: 'var(--color-sentinel-red)',
                      color: 'white',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    Reset
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowResetConfirm(true)}
                  className="flex items-center gap-1.5 text-xs transition-colors hover:opacity-80"
                  style={{
                    color: 'var(--color-sentinel-text-secondary)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset to Defaults
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
