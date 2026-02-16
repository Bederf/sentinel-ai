/**
 * CardLibrary Component - Dashboard card customization panel
 *
 * Features:
 * - List of available dashboard cards with metadata
 * - Toggle switches to show/hide cards
 * - Grouped by category (KPI, Analytics, etc.)
 * - Slide-out panel from right side
 */

import { useState, useEffect } from 'react';
import {
  X,
  LayoutGrid,
  Eye,
  EyeOff,
  RotateCcw
} from 'lucide-react';
import { KPI_CARDS, SECTION_CARDS, type CardDefinition } from '../lib/cardDefinitions';

interface CardLibraryProps {
  isOpen: boolean;
  onClose: () => void;
  visibleKpiCards: string[];
  visibleSections: string[];
  onKpiVisibilityChange: (cardId: string, visible: boolean) => void;
  onSectionVisibilityChange: (sectionId: string, visible: boolean) => void;
  onResetToDefaults: () => void;
  isSaving?: boolean;
}

export default function CardLibrary({
  isOpen,
  onClose,
  visibleKpiCards,
  visibleSections,
  onKpiVisibilityChange,
  onSectionVisibilityChange,
  onResetToDefaults,
  isSaving = false
}: CardLibraryProps) {
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleReset = () => {
    onResetToDefaults();
    setShowResetConfirm(false);
  };

  const renderCardToggle = (
    card: CardDefinition,
    isVisible: boolean,
    onToggle: (id: string, visible: boolean) => void
  ) => {
    const bgStyle = isVisible
      ? 'rgba(59, 130, 246, 0.1)'
      : 'var(--color-sentinel-bg-secondary)';
    const borderStyle = isVisible
      ? 'rgba(59, 130, 246, 0.3)'
      : 'var(--color-sentinel-border)';
    const iconBg = isVisible
      ? 'rgba(59, 130, 246, 0.2)'
      : 'var(--color-sentinel-bg-panel)';
    const iconColor = isVisible
      ? 'var(--color-sentinel-blue)'
      : 'var(--color-sentinel-text-secondary)';
    // FIX: Always make button visible with better contrast
    const buttonBg = isVisible
      ? 'var(--color-sentinel-blue)'
      : 'rgba(100, 116, 139, 0.3)';  // Slate-500 with transparency for OFF state
    const buttonColor = isVisible ? 'white' : 'var(--color-sentinel-text-primary)';

    return (
      <div
        key={card.id}
        className="flex items-center justify-between p-3 rounded-lg transition-colors"
        style={{
          background: bgStyle,
          border: `1px solid ${borderStyle}`
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: iconBg, color: iconColor }}
          >
            {/* Card icon placeholder */}
          </div>
          <div>
            <p
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              {card.name}
            </p>
            <p
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              {card.description}
            </p>
          </div>
        </div>

        <button
          onClick={() => onToggle(card.id, !isVisible)}
          className="p-2 rounded-lg transition-all hover:scale-110 active:scale-95"
          style={{ 
            background: buttonBg, 
            color: buttonColor,
            border: '1px solid rgba(255,255,255,0.1)',
            cursor: 'pointer'
          }}
          title={isVisible ? 'Hide card' : 'Show card'}
        >
          {isVisible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
        </button>
      </div>
    );
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed right-0 top-0 h-full w-full max-w-md z-50 shadow-2xl overflow-hidden flex flex-col"
        style={{
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(var(--glass-blur-lg)) saturate(180%)',
          WebkitBackdropFilter: 'blur(var(--glass-blur-lg)) saturate(180%)',
          borderLeft: '1px solid var(--glass-border)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: '1px solid var(--glass-border)' }}
        >
          <div className="flex items-center gap-3">
            <LayoutGrid className="w-5 h-5" style={{ color: 'var(--color-sentinel-amber)' }} />
            <div>
              <h2
                className="font-semibold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Customize Dashboard
              </h2>
              <p
                className="text-xs"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Show or hide dashboard cards
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg transition-colors hover:bg-white/10"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* KPI Cards Section */}
          <div>
            <h3
              className="text-xs font-medium uppercase tracking-wider mb-3"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              KPI Cards
            </h3>
            <div className="space-y-2">
              {KPI_CARDS.map((card) =>
                renderCardToggle(card, visibleKpiCards.includes(card.id), onKpiVisibilityChange)
              )}
            </div>
          </div>

          {/* Dashboard Sections */}
          <div>
            <h3
              className="text-xs font-medium uppercase tracking-wider mb-3"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Dashboard Sections
            </h3>
            <div className="space-y-2">
              {SECTION_CARDS.map((card) =>
                renderCardToggle(card, visibleSections.includes(card.id), onSectionVisibilityChange)
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          className="px-4 py-3 space-y-3"
          style={{ borderTop: '1px solid var(--glass-border)' }}
        >
          {isSaving && (
            <div
              className="flex items-center justify-center gap-2 text-sm"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              Saving preferences...
            </div>
          )}

          {showResetConfirm ? (
            <div className="flex items-center gap-2">
              <span
                className="text-sm flex-1"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Reset all to defaults?
              </span>
              <button
                onClick={() => setShowResetConfirm(false)}
                className="px-3 py-1.5 rounded text-sm"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  color: 'var(--color-sentinel-text-secondary)'
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleReset}
                className="px-3 py-1.5 rounded text-sm font-medium"
                style={{
                  background: 'var(--color-sentinel-red)',
                  color: 'white'
                }}
              >
                Reset
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowResetConfirm(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors hover:bg-white/5"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                color: 'var(--color-sentinel-text-secondary)'
              }}
            >
              <RotateCcw className="w-4 h-4" />
              Reset to Defaults
            </button>
          )}
        </div>
      </div>
    </>
  );
}
