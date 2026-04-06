/**
 * 2D/3D View Toggle Button
 *
 * Floating button in top-right corner allowing users to switch between:
 * - 2D: SVG floor plan (fast navigation, clear overview)
 * - 3D: Three.js 3D visualization (immersive, presentation-friendly)
 *
 * Styling: Dark theme matching existing SENTINEL UI
 */

interface ViewToggleProps {
  viewMode: '2D' | '3D';
  onToggle: (mode: '2D' | '3D') => void;
}

/**
 * Toggle button for switching between 2D and 3D views
 *
 * Positioned in top-right corner, above equipment filters
 * Shows active state with blue highlight
 */
export function ViewToggle({ viewMode, onToggle }: ViewToggleProps) {
  return (
    <div className="absolute top-4 right-4 z-10 flex gap-1 bg-slate-800 rounded-lg p-1 shadow-lg border border-slate-700">
      {/* 2D Button */}
      <button
        onClick={() => onToggle('2D')}
        className={`px-3 py-2 rounded text-sm font-medium transition-all flex items-center gap-2 ${
          viewMode === '2D'
            ? 'bg-blue-600 text-white shadow-lg'
            : 'text-slate-300 hover:bg-slate-700 hover:text-slate-100'
        }`}
        title="2D Floor Plan View - Fast navigation and clear overview"
        aria-label="Switch to 2D Floor Plan view"
      >
        <span className="text-lg">🗺️</span>
        <span>2D</span>
      </button>

      {/* 3D Button */}
      <button
        onClick={() => onToggle('3D')}
        className={`px-3 py-2 rounded text-sm font-medium transition-all flex items-center gap-2 ${
          viewMode === '3D'
            ? 'bg-blue-600 text-white shadow-lg'
            : 'text-slate-300 hover:bg-slate-700 hover:text-slate-100'
        }`}
        title="3D Visualization - Immersive 3D building model"
        aria-label="Switch to 3D Visualization view"
      >
        <span className="text-lg">🧊</span>
        <span>3D</span>
      </button>
    </div>
  );
}
