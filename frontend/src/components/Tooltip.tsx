import { ReactNode, useState } from "react";
import { HelpCircle } from "lucide-react";

/** Enkel tooltip som visas vid hover/fokus och är tangentbordstillgänglig. */
export function Tooltip({
  content, children, width = "w-64",
}: { content: ReactNode; children: ReactNode; width?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          className={`absolute left-full ml-2 top-1/2 -translate-y-1/2 ${width} bg-slate-900 text-white text-xs rounded p-2 shadow-lg z-50`}
        >
          {content}
          <span className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-slate-900"></span>
        </span>
      )}
    </span>
  );
}

/** HelpIcon - cirkel med ? som visar en tooltip vid hover.
 * Använd inline efter en label: "Månadens överskott <HelpIcon content=..." /> */
export function HelpIcon({ content, width }: {
  content: ReactNode; width?: string;
}) {
  return (
    <Tooltip content={content} width={width}>
      <button
        type="button"
        aria-label="Hjälp"
        className="text-slate-400 hover:text-brand-600"
        onClick={(e) => e.preventDefault()}
      >
        <HelpCircle className="w-4 h-4" />
      </button>
    </Tooltip>
  );
}

/** InfoBanner - en infobanner som visar en pedagogisk tips-text.
 * Används på landningsskärmar för att förklara vad eleven ska göra. */
export function InfoBanner({
  title, children,
}: { title: string; children: ReactNode }) {
  return (
    <div className="bg-amber-50 border-l-4 border-amber-400 rounded p-3 text-sm">
      <div className="font-semibold text-amber-900 mb-1">💡 {title}</div>
      <div className="text-amber-900">{children}</div>
    </div>
  );
}
