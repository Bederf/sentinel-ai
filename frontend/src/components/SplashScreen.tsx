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
  const startTimeRef = useRef<number>(0);
  const completedRef = useRef(false);

  const complete = () => {
    if (completedRef.current) return;
    completedRef.current = true;
    setFadeOut(true);
    setTimeout(() => {
      onComplete();
    }, 500);
  };

  // Initialize start time on mount - avoid calling Date.now() during render
  useEffect(() => {
    startTimeRef.current = Date.now();
  }, []);

  useEffect(() => {
    console.log('SplashScreen: Component mounted');
    const video = videoRef.current;
    if (!video) {
      console.error('SplashScreen: Video ref is null!');
      const timeout = setTimeout(() => complete(), minDisplayTime);
      return () => clearTimeout(timeout);
    }

    const handleVideoEnd = () => {
      console.log('SplashScreen: Video ended');
      const elapsed = Date.now() - startTimeRef.current;
      const remainingTime = Math.max(0, minDisplayTime - elapsed);
      console.log('SplashScreen: Elapsed:', elapsed, 'Remaining:', remainingTime);

      // Wait for minimum display time, then fade out
      setTimeout(() => {
        console.log('SplashScreen: Starting fade out');
        complete();
      }, remainingTime);
    };

    // If video fails to load or play, still complete after minDisplayTime
    const handleError = (error?: unknown) => {
      const abortError = (error as { name?: string })?.name === "AbortError";
      if (!abortError) {
        console.error('SplashScreen: Video error or play failed:', error);
      }
      setTimeout(() => {
        console.log('SplashScreen: Fallback timeout triggering');
        complete();
      }, minDisplayTime);
    };

    video.addEventListener("ended", handleVideoEnd);
    video.addEventListener("error", handleError);

    // Start playing
    console.log('SplashScreen: Attempting to play video');
    video.play().catch((err) => {
      handleError(err);
    });

    const maxTimeout = window.setTimeout(() => {
      console.warn('SplashScreen: Max timeout reached, completing');
      complete();
    }, minDisplayTime + 1500);

    return () => {
      video.removeEventListener("ended", handleVideoEnd);
      video.removeEventListener("error", handleError);
      clearTimeout(maxTimeout);
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
            style={{ border: "none", outline: "none" }}
            muted
            playsInline
            autoPlay
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
