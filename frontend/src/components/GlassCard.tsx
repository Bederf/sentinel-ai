import type { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "subtle" | "heavy";
  highlight?: boolean;
  accentColor?: string;
  onClick?: () => void;
}

export default function GlassCard({
  children,
  className = "",
  variant = "default",
  highlight = false,
  accentColor,
  onClick,
}: GlassCardProps) {
  const variantClass = {
    default: "glass-card",
    subtle: "glass-subtle",
    heavy: "glass-panel",
  }[variant];

  return (
    <div
      className={`${variantClass} ${highlight ? "glass-highlight" : ""} ${className}`}
      onClick={onClick}
      style={accentColor ? { borderTop: `2px solid ${accentColor}` } : undefined}
    >
      {children}
    </div>
  );
}
