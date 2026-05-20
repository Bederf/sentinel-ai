/**
 * SortableKPICard Component
 *
 * Wrapper around KPICard that adds drag-and-drop functionality
 * for reordering KPI cards in the dashboard.
 */

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import KPICard, { type KPICardProps } from './KPICard';

interface SortableKPICardProps extends KPICardProps {
  id: string;
}

export function SortableKPICard({ id, ...props }: SortableKPICardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const [isHovered, setIsHovered] = useState(false);

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition: isDragging
      ? 'none'
      : transition || 'transform 300ms cubic-bezier(0.25, 0.46, 0.45, 0.94)', // ease-out-quart
    opacity: isDragging ? 0.5 : 1,
    cursor: isDragging ? 'grabbing' : 'grab',
    backdropFilter: isDragging ? 'none' : undefined,
    WebkitBackdropFilter: isDragging ? 'none' : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Drag Handle */}
      {isHovered && (
        <div
          {...attributes}
          {...listeners}
          className="absolute top-2 right-2 z-10 p-1 rounded cursor-grab active:cursor-grabbing"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
          }}
          title="Drag to reorder"
        >
          <GripVertical
            className="h-4 w-4"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          />
        </div>
      )}

      {/* KPI Card */}
      <KPICard {...props} />
    </div>
  );
}

export default SortableKPICard;
