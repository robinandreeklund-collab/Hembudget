import type { ReactNode } from "react";

/** Vågrät linje med ett ord centrerat i mitten — sektions-intro. */
export function SectionDivider({
  children, className = "",
}: { children: ReactNode; className?: string }) {
  return <div className={`section-divider ${className}`}>{children}</div>;
}
