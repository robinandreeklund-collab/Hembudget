import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "dark" | "outline";
type Size = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

const SIZES: Record<Size, string> = {
  sm: "text-sm px-3.5 py-2 rounded-md",
  md: "px-5 py-3 rounded-md",
  lg: "px-6 py-3.5 rounded-md",
};

/** Paper-knapp i två varianter:
 *   dark    — svart fyld, hover blir helt svart
 *   outline — vit + ljus border, hover ger paper-yellow bg + svart border
 *
 * Kan användas som <button> direkt, eller som className-källa via
 * paperButtonClass() för <Link> / <a>. */
export function PaperButton({
  variant = "dark", size = "md", className = "", children, ...rest
}: Props) {
  return (
    <button
      {...rest}
      className={`${variant === "dark" ? "btn-dark" : "btn-outline"} ${SIZES[size]} ${className}`}
    >
      {children}
    </button>
  );
}

export function paperButtonClass(variant: Variant = "dark", size: Size = "md") {
  return `${variant === "dark" ? "btn-dark" : "btn-outline"} ${SIZES[size]}`;
}
