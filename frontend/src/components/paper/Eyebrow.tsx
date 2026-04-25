import type { ReactNode } from "react";

/** Liten kicker-text — caps, letterspacing 0.18em, grå. */
export function Eyebrow({
  children, className = "",
}: { children: ReactNode; className?: string }) {
  return <div className={`eyebrow ${className}`}>{children}</div>;
}
