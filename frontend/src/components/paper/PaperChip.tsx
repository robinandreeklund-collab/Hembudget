import type { ReactNode } from "react";

export type ChipColor =
  | "grund" | "fordj" | "expert" | "konto" | "risk" | "special";

type Props = {
  color?: ChipColor;
  size?: "sm" | "md";
  children: ReactNode;
  className?: string;
};

/** Mini-cell ur periodiska systemet — används som ikon på feature-kort,
 * sidebar-poster, breadcrumbs, etc. Färgen styr bakgrunden enligt
 * paper-paletten (grund/fordj/expert/konto/risk/special). */
export function PaperChip({
  color = "grund", size = "md", children, className = "",
}: Props) {
  const sz = size === "sm"
    ? { width: 28, height: 28, fontSize: 12 }
    : undefined;
  return (
    <span
      className={`feature-chip ${color} ${className}`}
      style={sz}
      aria-hidden="true"
    >
      {children}
    </span>
  );
}
