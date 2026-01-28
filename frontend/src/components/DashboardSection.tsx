/**
 * DashboardSection Component
 * 
 * Wrapper component for dashboard sections that adds drag-and-drop functionality.
 * Provides visual feedback during drag operations.
 */

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import { useState, type ReactNode } from 'react';

interface DashboardSectionProps {
  id: string;
  children: ReactNode;
}

export function DashboardSection({ id, children }: DashboardSectionProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const [isHovered, setIsHovered] = useState(false);

  const style = {
    transform: CSS.Transform.toString(transform),
    transition: isDragging 
      ? 'none' 
      : transition || 'transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1)', // Spring-like snap effect
    opacity: isDragging ? 0.5 : 1,
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
          className="absolute top-2 right-2 z-10 p-2 rounded cursor-grab active:cursor-grabbing"
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

      {/* Section Content */}
      {children}
    </div>
  );
}

export default DashboardSection;
