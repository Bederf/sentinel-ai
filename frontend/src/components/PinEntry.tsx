/**
 * PinEntry Component - Simple PIN code authentication screen
 *
 * Features:
 * - 4-digit PIN entry with numeric keypad
 * - Visual feedback for entered digits
 * - Error shake animation on wrong PIN
 * - Follows SENTINEL dark theme design
 */

import { useState, useEffect, useCallback } from "react";
import { Shield, Delete, Lock } from "lucide-react";

// Default PIN code - can be changed or made configurable
const VALID_PIN = "27921";

interface PinEntryProps {
  onSuccess: () => void;
}

export function PinEntry({ onSuccess }: PinEntryProps) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);

  // Log component mount
  useEffect(() => {
    console.log('=== PIN ENTRY DEBUG ===');
    console.log('PinEntry component mounted');
    console.log('Valid PIN:', VALID_PIN);
    console.log('Current sessionStorage:', sessionStorage.getItem("sentinel_authenticated"));
    console.log('=======================');
  }, []);

  const handleDigitPress = useCallback((digit: string) => {
    console.log('Digit pressed:', digit, 'Current PIN:', pin);
    if (pin.length < 5) {
      const newPin = pin + digit;
      setPin(newPin);
      setError(false);

      console.log('PIN entered:', newPin, 'Length:', newPin.length, 'Expected:', VALID_PIN);

      // Auto-verify when 5 digits entered
      if (newPin.length === 5) {
        setTimeout(() => {
          console.log('Verifying PIN:', newPin, '===', VALID_PIN, '?', newPin === VALID_PIN);
          if (newPin === VALID_PIN) {
            // Store auth in sessionStorage
            sessionStorage.setItem("sentinel_authenticated", "true");
            console.log('PIN correct, calling onSuccess');
            onSuccess();
          } else {
            console.log('PIN incorrect');
            setError(true);
            setShake(true);
            setTimeout(() => {
              setPin("");
              setShake(false);
            }, 500);
          }
        }, 150);
      }
    }
  }, [pin, onSuccess]);

  const handleBackspace = useCallback(() => {
    setPin(pin.slice(0, -1));
    setError(false);
  }, [pin]);

  const handleClear = useCallback(() => {
    setPin("");
    setError(false);
  }, []);

  // Keyboard support
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key >= "0" && e.key <= "9") {
        handleDigitPress(e.key);
      } else if (e.key === "Backspace") {
        handleBackspace();
      } else if (e.key === "Escape") {
        handleClear();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleDigitPress, handleBackspace, handleClear]);

  const digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", ""];

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-4"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Logo and Title */}
      <div className="flex flex-col items-center mb-8">
        <div
          className="w-16 h-16 rounded-xl flex items-center justify-center mb-4"
          style={{
            background: "linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(59, 130, 246, 0.1))",
            border: "1px solid rgba(59, 130, 246, 0.3)",
          }}
        >
          <Shield className="w-8 h-8" style={{ color: "var(--color-sentinel-blue)" }} />
        </div>
        <h1
          className="text-2xl font-bold tracking-wide mb-2"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          SENTINEL
        </h1>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Enter PIN to continue
        </p>
      </div>

      {/* PIN Display */}
      <div
        className={`flex gap-3 mb-8 ${shake ? "animate-shake" : ""}`}
        style={{
          animation: shake ? "shake 0.5s ease-in-out" : "none",
        }}
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="w-12 h-14 rounded-lg flex items-center justify-center transition-all duration-150"
            style={{
              background: pin.length > i
                ? error
                  ? "rgba(239, 68, 68, 0.2)"
                  : "rgba(59, 130, 246, 0.2)"
                : "var(--color-sentinel-bg-secondary)",
              border: `2px solid ${
                pin.length > i
                  ? error
                    ? "var(--color-sentinel-red)"
                    : "var(--color-sentinel-blue)"
                  : "var(--color-sentinel-border)"
              }`,
            }}
          >
            {pin.length > i && (
              <div
                className="w-3 h-3 rounded-full"
                style={{
                  background: error
                    ? "var(--color-sentinel-red)"
                    : "var(--color-sentinel-blue)",
                }}
              />
            )}
          </div>
        ))}
      </div>

      {/* Error Message */}
      {error && (
        <p
          className="text-sm mb-4"
          style={{ color: "var(--color-sentinel-red)" }}
        >
          Incorrect PIN. Please try again.
        </p>
      )}

      {/* Keypad */}
      <div
        className="grid grid-cols-3 gap-3 p-4 rounded-xl"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {digits.map((digit, i) => {
          if (digit === "") {
            // Empty cell or backspace
            if (i === 9) {
              return <div key={i} className="w-16 h-14" />;
            }
            // Backspace button
            return (
              <button
                key={i}
                onClick={handleBackspace}
                className="w-16 h-14 rounded-lg flex items-center justify-center transition-all duration-150 hover:brightness-125 active:scale-95"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                <Delete className="w-5 h-5" />
              </button>
            );
          }

          return (
            <button
              key={i}
              onClick={() => handleDigitPress(digit)}
              className="w-16 h-14 rounded-lg text-xl font-semibold transition-all duration-150 hover:brightness-125 active:scale-95"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {digit}
            </button>
          );
        })}
      </div>

      {/* Hint */}
      <p
        className="mt-6 text-xs flex items-center gap-1"
        style={{ color: "var(--color-sentinel-text-disabled)" }}
      >
        <Lock className="w-3 h-3" />
        Use keyboard or tap to enter PIN
      </p>

      {/* Debug info - can be removed later */}
      <p
        className="mt-2 text-xs"
        style={{ color: "var(--color-sentinel-text-disabled)", opacity: 0.5 }}
      >
        DEBUG: PIN entry screen is active. Valid PIN is {VALID_PIN}
      </p>

      {/* Shake animation keyframes */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-8px); }
          20%, 40%, 60%, 80% { transform: translateX(8px); }
        }
        .animate-shake {
          animation: shake 0.5s ease-in-out;
        }
      `}</style>
    </div>
  );
}

export default PinEntry;
