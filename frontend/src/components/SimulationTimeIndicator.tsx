import { useState, useRef, useCallback } from 'react';
import { Sun, Moon, Cloud, CloudRain, GripVertical } from 'lucide-react';
import { useSimulation } from '@/contexts/SimulationContext';

interface SimulationTimeIndicatorProps {
  simulationRunning?: boolean;
  siteId?: string;
}

/**
 * Draggable simulation clock pill using SimulationContext.
 * Shows: grip handle | weather icon | HH:MM | Day X/365 | Season | temp
 * Click-and-drag to reposition anywhere on screen.
 */
export function SimulationTimeIndicator({
  simulationRunning: _unused,
  siteId: _unused2,
}: SimulationTimeIndicatorProps) {
  const {
    running,
    simulatedTime,
    daysSimulated,
    isRaining,
    cloudCover,
    ambientTemp,
    simulatedHour,
    currentSeason,
  } = useSimulation();

  // Draggable state
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const pillRef = useRef<HTMLDivElement>(null);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: position.x,
      origY: position.y,
    };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [position]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isDragging || !dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPosition({
      x: dragRef.current.origX + dx,
      y: dragRef.current.origY + dy,
    });
  }, [isDragging]);

  const handlePointerUp = useCallback(() => {
    setIsDragging(false);
    dragRef.current = null;
  }, []);

  if (!running) return null;

  // Extract HH:MM from simulatedTime (ISO string)
  const timeDisplay = simulatedTime
    ? simulatedTime.split('T')[1]?.substring(0, 5) || '00:00'
    : '00:00';

  const isDaytime = simulatedHour >= 6 && simulatedHour < 18;
  const isHighCloudCover = (cloudCover || 0) > 70;

  // Pick icon
  const WeatherIcon = isRaining
    ? CloudRain
    : isHighCloudCover
    ? Cloud
    : isDaytime
    ? Sun
    : Moon;

  // Pick accent color
  const accent = isRaining
    ? 'rgba(59,130,246,0.9)'
    : isHighCloudCover
    ? 'rgba(107,114,128,0.9)'
    : isDaytime
    ? 'rgba(245,158,11,0.9)'
    : 'rgba(30,58,138,0.9)';

  // Season emoji
  const seasonEmoji =
    currentSeason === 'summer' ? '\u2600\uFE0F' :
    currentSeason === 'autumn' ? '\uD83C\uDF42' :
    currentSeason === 'winter' ? '\u2744\uFE0F' :
    '\uD83C\uDF38'; // spring

  return (
    <div
      ref={pillRef}
      className="fixed top-20 right-4 z-50 flex items-center gap-2 px-3 py-1.5 rounded-full shadow-lg backdrop-blur-sm text-white text-xs font-medium select-none"
      style={{
        background: accent,
        transform: `translate(${position.x}px, ${position.y}px)`,
        cursor: isDragging ? 'grabbing' : 'grab',
        touchAction: 'none',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <GripVertical className="h-3 w-3 opacity-60 flex-shrink-0" />
      <WeatherIcon className="h-4 w-4 flex-shrink-0" />
      <span className="tabular-nums font-bold text-sm">{timeDisplay}</span>
      <span className="opacity-80">D{daysSimulated}/365</span>
      <span className="opacity-80">{seasonEmoji} {currentSeason}</span>
      <span className="opacity-80">{ambientTemp?.toFixed(0)}\u00B0C</span>
    </div>
  );
}
