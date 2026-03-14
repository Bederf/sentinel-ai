/**
 * HistoricalTimeline — horizontal scrubber for replaying building state
 * over 24h / 7d / 30d in the Digital Twin view.
 *
 * Styling follows the glass-panel card pattern matching BottomStatusBar.
 */

import { useState, useEffect, useRef, useMemo } from 'react'
import { Play, Pause, SkipBack, Clock } from 'lucide-react'

type TimeRange = '24h' | '7d' | '30d'

interface HistoricalTimelineProps {
  onTimestampChange: (timestamp: Date) => void
  isPlaying: boolean
  onPlayPause: () => void
}

const RANGE_MS: Record<TimeRange, number> = {
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
}

const SPEED_OPTIONS = [1, 2, 5] as const

export function HistoricalTimeline({
  onTimestampChange,
  isPlaying,
  onPlayPause,
}: HistoricalTimelineProps) {
  const [range, setRange] = useState<TimeRange>('24h')
  const [speed, setSpeed] = useState<number>(1)
  const [progress, setProgress] = useState(1) // 0-1, 1 = now
  const [endTimeMs, setEndTimeMs] = useState(() => Date.now())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Derive timestamp from progress and endTime (all state, no refs in render)
  const ts = useMemo(() => {
    const rangeMs = RANGE_MS[range]
    const start = endTimeMs - rangeMs
    return new Date(start + progress * rangeMs)
  }, [range, progress, endTimeMs])

  // Emit timestamp changes
  useEffect(() => {
    onTimestampChange(ts)
  }, [ts, onTimestampChange])

  // Playback loop
  useEffect(() => {
    if (isPlaying) {
      // Advance by speed * 60s of simulated time per real second
      const stepMs = (speed * 60 * 1000) / RANGE_MS[range]
      intervalRef.current = setInterval(() => {
        setProgress((prev) => {
          const next = prev + stepMs
          if (next >= 1) {
            onPlayPause() // stop at end
            return 1
          }
          return next
        })
      }, 1000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [isPlaying, speed, range, onPlayPause])

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setProgress(parseFloat(e.target.value))
  }

  const handleReset = () => {
    setEndTimeMs(Date.now())
    setProgress(0)
  }
  const formattedTime = ts.toLocaleString('en-ZA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  })

  return (
    <div
      className="absolute bottom-0 left-0 right-0 z-40 px-4 pb-4"
      style={{ pointerEvents: 'none' }}
    >
      <div
        className="rounded-lg border px-4 py-3 flex items-center gap-4"
        style={{
          pointerEvents: 'auto',
          background: 'rgba(15, 23, 42, 0.88)',
          borderColor: 'rgba(100, 116, 139, 0.3)',
          backdropFilter: 'blur(8px)',
        }}
      >
        {/* Play / Pause */}
        <button
          onClick={onPlayPause}
          className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <Pause className="w-5 h-5 text-blue-400" />
          ) : (
            <Play className="w-5 h-5 text-blue-400" />
          )}
        </button>

        {/* Reset */}
        <button
          onClick={handleReset}
          className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          title="Reset to start"
        >
          <SkipBack className="w-4 h-4 text-slate-400" />
        </button>

        {/* Slider */}
        <div className="flex-1 relative">
          <input
            type="range"
            min={0}
            max={1}
            step={0.001}
            value={progress}
            onChange={handleSliderChange}
            className="w-full h-1.5 rounded-lg appearance-none cursor-pointer"
            style={{
              background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${progress * 100}%, #334155 ${progress * 100}%, #334155 100%)`,
            }}
          />
        </div>

        {/* Current time */}
        <div className="flex items-center gap-2 min-w-[220px]">
          <Clock className="w-4 h-4 text-slate-400" />
          <span className="font-mono text-sm text-slate-200 whitespace-nowrap">
            {formattedTime}
          </span>
        </div>

        {/* Speed selector */}
        <div className="flex items-center gap-1">
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                speed === s
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-white/10'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Range selector */}
        <div className="flex items-center gap-1 border-l border-slate-600 pl-3">
          {(['24h', '7d', '30d'] as TimeRange[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                range === r
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-white/10'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
