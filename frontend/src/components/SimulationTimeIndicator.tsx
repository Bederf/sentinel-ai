import { Sun, Moon, Cloud, CloudRain, Droplets } from 'lucide-react';
import { useState, useEffect } from 'react';

interface SimulationTimeIndicatorProps {
  simulationRunning: boolean;
  siteId?: string;
}

/**
 * Enhanced simulation time indicator with real-time weather visualization.
 * 
 * Displays:
 * - Sun icon (6am-6pm) or Moon icon (6pm-6am)
 * - Rain drops animation when raining
 * - Cloud cover percentage (0-100%)
 * - Current simulated time (HH:MM)
 * - Hour counter (X/24 or X/365 for annual)
 * - Progress bar
 * - Temperature indicator
 * - Solar generation efficiency
 * - Detailed weather tooltip
 * 
 * Weather effects:
 * - Clear: Bright yellow gradient
 * - Cloudy: Gray overlay, reduced brightness
 * - Rainy: Blue with rain animation, droplets
 * - Night: Dark blue with stars
 * 
 * Polls /api/lifecycle/status/{site_id} every 2 seconds for real-time updates.
 */
export function SimulationTimeIndicator({
  simulationRunning,
  siteId = 'site-002',
}: SimulationTimeIndicatorProps) {
  const [simulatedHour, setSimulatedHour] = useState<number>(0);
  const [simulatedTime, setSimulatedTime] = useState<string>('00:00');
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [isRaining, setIsRaining] = useState(false);
  const [cloudCover, setCloudCover] = useState<number>(0);
  const [temperature, setTemperature] = useState<number>(22);
  const [solarEfficiency, setSolarEfficiency] = useState<number>(100);
  const [isLoading, setIsLoading] = useState(false);
  const [season, setSeason] = useState<string>('');
  const [showTooltip, setShowTooltip] = useState(false);

  useEffect(() => {
    if (!simulationRunning) return;

    setIsLoading(true);

    // Poll simulation status every 2 seconds
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/lifecycle/status/${siteId}`);
        const data = await response.json();

        if (data.running) {
          setSimulatedHour(data.simulated_hour || 0);
          setSimulatedTime(data.simulated_time || '00:00');
          setProgressPercent(data.progress_percent || 0);
          
          // Weather data from annual simulation
          if (data.is_raining !== undefined) {
            setIsRaining(data.is_raining);
          }
          
          if (data.cloud_cover !== undefined) {
            setCloudCover(data.cloud_cover);
          }
          
          if (data.ambient_temp !== undefined) {
            setTemperature(Math.round(data.ambient_temp));
          }
          
          if (data.solar_efficiency !== undefined) {
            setSolarEfficiency(Math.round(data.solar_efficiency * 100));
          }
          
          if (data.current_season) {
            setSeason(data.current_season);
          }
          
          setIsLoading(false);
        }
      } catch (error) {
        console.error('Failed to fetch simulation status:', error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [simulationRunning, siteId]);

  if (!simulationRunning) return null;

  const isDaytime = simulatedHour >= 6 && simulatedHour < 18;
  
  // Determine weather condition
  const isHighCloudCover = cloudCover > 70;
  const weatherCondition = isRaining ? 'rainy' : isHighCloudCover ? 'cloudy' : isDaytime ? 'clear' : 'night';

  // Color schemes by condition
  const getColorScheme = () => {
    switch (weatherCondition) {
      case 'rainy':
        return {
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.95) 0%, rgba(37, 99, 235, 0.95) 100%)',
          glow: '0 10px 30px rgba(59, 130, 246, 0.4)',
          label: 'RAINY',
        };
      case 'cloudy':
        return {
          background: 'linear-gradient(135deg, rgba(107, 114, 128, 0.95) 0%, rgba(75, 85, 99, 0.95) 100%)',
          glow: '0 10px 30px rgba(107, 114, 128, 0.3)',
          label: `CLOUDY (${cloudCover}%)`,
        };
      case 'clear':
        return {
          background: 'linear-gradient(135deg, rgba(253, 184, 19, 0.95) 0%, rgba(245, 158, 11, 0.95) 100%)',
          glow: '0 10px 30px rgba(253, 184, 19, 0.3)',
          label: 'DAYTIME',
        };
      case 'night':
      default:
        return {
          background: 'linear-gradient(135deg, rgba(30, 58, 138, 0.95) 0%, rgba(49, 46, 129, 0.95) 100%)',
          glow: '0 10px 30px rgba(30, 58, 138, 0.3)',
          label: 'NIGHT',
        };
    }
  };

  const colorScheme = getColorScheme();

  // Rain drop animation
  const RaindropsAnimation = () => {
    if (!isRaining) return null;
    
    const drops = Array.from({ length: 12 }).map((_, i) => (
      <div
        key={i}
        className="absolute w-1 h-2 bg-blue-200 rounded-full opacity-70"
        style={{
          left: `${(i * 8) % 100}%`,
          top: `-4px`,
          animation: `fall ${0.8 + (i % 3) * 0.2}s linear infinite`,
          animationDelay: `${(i * 0.15)}s`,
        }}
      />
    ));

    return (
      <>
        <style>{`
          @keyframes fall {
            to {
              transform: translateY(60px);
              opacity: 0;
            }
          }
        `}</style>
        <div className="absolute inset-0 overflow-hidden rounded-xl pointer-events-none">
          {drops}
        </div>
      </>
    );
  };

  // Cloud cover visualization
  const CloudCoverBar = () => (
    <div className="w-20 h-1 bg-white bg-opacity-20 rounded-full overflow-hidden">
      <div
        className="h-full bg-white bg-opacity-60 transition-all duration-300 rounded-full"
        style={{ width: `${cloudCover}%` }}
      />
    </div>
  );

  return (
    <div
      className="fixed top-20 right-6 z-50 transition-all duration-300"
      style={{
        animation: isLoading ? 'pulse 1s infinite' : 'none',
      }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Main Card */}
      <div
        className="px-5 py-4 rounded-xl shadow-2xl flex items-center gap-4 backdrop-blur-sm relative overflow-hidden"
        style={{
          background: colorScheme.background,
          color: 'white',
          boxShadow: colorScheme.glow,
        }}
      >
        {/* Rain animation overlay */}
        <RaindropsAnimation />

        {/* Icon Section */}
        <div className="flex-shrink-0 relative z-10">
          {isRaining ? (
            <div className="relative">
              <CloudRain className="h-7 w-7 animate-bounce" style={{
                filter: 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.6))',
              }} />
              <Droplets className="absolute h-3 w-3 bottom-0 right-0 text-blue-200 animate-pulse" />
            </div>
          ) : isHighCloudCover ? (
            <Cloud className="h-7 w-7 animate-pulse" style={{
              filter: 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.5))',
            }} />
          ) : isDaytime ? (
            <Sun className="h-7 w-7 animate-pulse" style={{
              filter: 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.5))',
            }} />
          ) : (
            <Moon className="h-7 w-7" style={{
              filter: 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.3))',
            }} />
          )}
        </div>

        {/* Content */}
        <div className="flex flex-col gap-2 relative z-10">
          {/* Status Label */}
          <span className="text-xs font-semibold opacity-95 tracking-wide">
            {colorScheme.label}
          </span>

          {/* Time */}
          <span className="text-2xl font-bold tabular-nums">
            {simulatedTime}
          </span>

          {/* Hour Counter & Season */}
          <div className="flex items-center gap-2 text-xs opacity-85 font-medium">
            <span>Hour {simulatedHour}/24</span>
            {season && <span className="text-opacity-75">• {season}</span>}
          </div>

          {/* Temperature with Rain Indicator */}
          <div className="flex items-center gap-2 text-sm font-semibold opacity-90">
            <span>{temperature}°C</span>
            {isRaining && <span className="text-xs text-blue-100">↓ Raining</span>}
          </div>
        </div>

        {/* Right Section: Cloud & Solar Info */}
        <div className="ml-2 flex flex-col gap-3 items-center relative z-10">
          {/* Cloud Cover */}
          <div className="flex flex-col items-center gap-1">
            <CloudCoverBar />
            <span className="text-xs font-semibold opacity-85">
              {cloudCover}%
            </span>
          </div>

          {/* Solar Efficiency */}
          {isDaytime && (
            <div className="text-center">
              <div className="text-xs font-semibold opacity-85">
                ☀️ {solarEfficiency}%
              </div>
              <div className="text-xs opacity-75">
                Solar
              </div>
            </div>
          )}

          {/* Progress Bar */}
          <div className="w-8 h-1 bg-white bg-opacity-30 rounded-full overflow-hidden">
            <div
              className="h-full bg-white bg-opacity-90 transition-all duration-500 rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs font-semibold opacity-85">
            {progressPercent}%
          </span>
        </div>
      </div>

      {/* Enhanced Tooltip */}
      {showTooltip && (
        <div className="absolute top-full mt-3 right-0 bg-gray-900 text-white rounded-lg shadow-xl p-4 w-64 text-xs z-50 border border-gray-700">
          <div className="space-y-2">
            {/* Weather Status */}
            <div className="border-b border-gray-700 pb-2">
              <div className="flex items-center justify-between font-semibold text-sm mb-1">
                <span>🌍 Weather Status</span>
                <span className="text-blue-400">{weatherCondition.toUpperCase()}</span>
              </div>
            </div>

            {/* Conditions */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="opacity-70">Temperature:</span>
                <div className="font-semibold text-lg">{temperature}°C</div>
              </div>
              <div>
                <span className="opacity-70">Cloud Cover:</span>
                <div className="font-semibold text-lg">{cloudCover}%</div>
              </div>
            </div>

            {/* Raining Info */}
            {isRaining && (
              <div className="bg-blue-900 bg-opacity-50 rounded p-2 border border-blue-700">
                <div className="flex items-center gap-2 text-blue-300">
                  <CloudRain className="h-4 w-4" />
                  <span>🌧️ Rain reducing temperature 2-4°C</span>
                </div>
              </div>
            )}

            {/* Solar Info */}
            {isDaytime && (
              <div className="bg-yellow-900 bg-opacity-50 rounded p-2 border border-yellow-700">
                <div className="flex items-center justify-between text-yellow-300">
                  <span>☀️ Solar Generation:</span>
                  <span className="font-semibold">{solarEfficiency}%</span>
                </div>
                <div className="text-xs opacity-75 mt-1">
                  {isRaining 
                    ? '🌧️ Rain reducing output 30-70%' 
                    : isHighCloudCover 
                    ? '☁️ Clouds reducing output' 
                    : '✨ Optimal conditions'}
                </div>
              </div>
            )}

            {/* Season Info */}
            {season && (
              <div className="bg-green-900 bg-opacity-50 rounded p-2 border border-green-700">
                <div className="flex items-center justify-between text-green-300">
                  <span>🌍 Season:</span>
                  <span className="font-semibold">{season}</span>
                </div>
              </div>
            )}

            {/* Occupancy Note */}
            {isRaining && (
              <div className="text-xs opacity-75 italic text-gray-400">
                💼 Some people working from home due to rain (+WFH)
              </div>
            )}
          </div>
          
          {/* Arrow pointer */}
          <div className="absolute top-0 right-4 w-2 h-2 bg-gray-900 border-r border-t border-gray-700 transform rotate-45 -translate-y-1" />
        </div>
      )}

      {/* Info Text */}
      <div className="mt-2 text-xs opacity-70 text-center px-2">
        <p className="text-gray-600 dark:text-gray-400">
          Annual simulation • Hover for details
        </p>
      </div>
    </div>
  );
}
