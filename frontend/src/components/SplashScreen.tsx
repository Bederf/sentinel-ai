/**
 * SplashScreen Component - SENTINEL Logo Animation
 *
 * Displays the animated logo on initial load, then fades out
 * to reveal the main dashboard.
 */

import { useState, useEffect, useRef } from "react";

interface SplashScreenProps {
  onComplete: () => void;
  minDisplayTime?: number; // Minimum time to show splash (ms)
}

export function SplashScreen({ onComplete, minDisplayTime = 2500 }: SplashScreenProps) {
  const [fadeOut, setFadeOut] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const startTimeRef = useRef(Date.now());

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleVideoEnd = () => {
      const elapsed = Date.now() - startTimeRef.current;
      const remainingTime = Math.max(0, minDisplayTime - elapsed);

      // Wait for minimum display time, then fade out
      setTimeout(() => {
        setFadeOut(true);
        // After fade animation, call onComplete
        setTimeout(onComplete, 500);
      }, remainingTime);
    };

    // If video fails to load or play, still complete after minDisplayTime
    const handleError = () => {
      setTimeout(() => {
        setFadeOut(true);
        setTimeout(onComplete, 500);
      }, minDisplayTime);
    };

    video.addEventListener("ended", handleVideoEnd);
    video.addEventListener("error", handleError);

    // Start playing
    video.play().catch(handleError);

    return () => {
      video.removeEventListener("ended", handleVideoEnd);
      video.removeEventListener("error", handleError);
    };
  }, [onComplete, minDisplayTime]);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-500 ${
        fadeOut ? "opacity-0" : "opacity-100"
      }`}
      style={{ background: "#ffffff" }}
    >
      <div className="flex flex-col items-center">
        {/* Video Container - Large */}
        <div className="w-[400px] h-[400px] md:w-[500px] md:h-[500px] lg:w-[600px] lg:h-[600px] flex items-center justify-center">
          <video
            ref={videoRef}
            className="max-w-full max-h-full object-contain"
            muted
            playsInline
            preload="auto"
          >
            <source src="/sentinel-logo.mp4" type="video/mp4" />
          </video>
        </div>

        {/* Loading text below video */}
        <div
          className="mt-8 text-sm tracking-widest animate-pulse"
          style={{ color: "#1A2B4C" }}
        >
          INITIALIZING
        </div>
      </div>
    </div>
  );
}

export default SplashScreen;
