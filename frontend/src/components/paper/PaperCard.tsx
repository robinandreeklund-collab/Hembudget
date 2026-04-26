import type { HTMLAttributes, ReactNode } from "react";

type Props = HTMLAttributes<HTMLDivElement> & {
  variant?: "feature" | "outline" | "active";
  children: ReactNode;
};

/** Paper-kort i tre varianter:
 *   feature — 1.5px svart border + paper bg + hover-lyft (default)
 *   outline — 1.5px ljus border + vit bg, ingen hover
 *   active  — 2.5px svart border + paper bg, used som "current plan"-stil */
export function PaperCard({
  variant = "feature", className = "", children, ...rest
}: Props) {
  const cls =
    variant === "feature" ? "feature-card" :
    variant === "outline" ? "border-[1.5px] border-rule bg-white p-5" :
    "border-[2.5px] border-ink bg-paper p-7";
  return (
    <div {...rest} className={`${cls} ${className}`}>{children}</div>
  );
}
