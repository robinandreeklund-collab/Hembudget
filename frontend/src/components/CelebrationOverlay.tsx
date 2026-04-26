import { useEffect, useRef, useState } from "react";

export type Achievement = {
  key: string;
  title: string;
  emoji: string;
  description: string;
};

/** Fullscreen-overlay som poppar upp 2.5 s med konfetti + ett kort per
 * tjänad prestation. Stäng via klick, Escape eller auto-dismiss.
 *
 * Respekterar `prefers-reduced-motion` — då hoppas animationer över
 * och kortet visas statiskt.
 */
export function CelebrationOverlay({
  items,
  onClose,
}: {
  items: Achievement[];
  onClose: () => void;
}) {
  const [reduced, setReduced] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    timerRef.current = window.setTimeout(onClose, 4500);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (items.length === 0) return null;

  return (
    <div
      role="dialog"
      aria-live="assertive"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-6"
    >
      {!reduced && <ConfettiBurst />}
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full text-center space-y-4 relative"
      >
        <div className="text-2xl font-semibold text-slate-900">
          Grattis!
        </div>
        <div className="space-y-3">
          {items.map((a) => (
            <div
              key={a.key}
              className="flex items-center gap-3 bg-gradient-to-br from-amber-50 to-rose-50 border border-amber-200 rounded-xl p-3"
            >
              <div className="text-4xl">{a.emoji}</div>
              <div className="text-left">
                <div className="font-semibold text-slate-900">{a.title}</div>
                <div className="text-xs text-slate-600">{a.description}</div>
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-2 btn-dark rounded-md px-5 py-2 font-medium"
        >
          Tack!
        </button>
      </div>
    </div>
  );
}

/** Enkel CSS-baserad konfetti — 24 divar med slumpade positioner och
 * fall-rotera-animationer. Inga externa deps. */
function ConfettiBurst() {
  const pieces = Array.from({ length: 24 }, (_, i) => i);
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {pieces.map((i) => {
        const left = (i * 4.1 + (i % 7) * 3) % 100;
        const delay = (i % 8) * 80;
        const dur = 1600 + (i % 5) * 200;
        const colors = [
          "#f59e0b", "#10b981", "#3b82f6",
          "#ef4444", "#8b5cf6", "#14b8a6",
        ];
        const color = colors[i % colors.length];
        const size = 8 + (i % 4) * 3;
        return (
          <span
            key={i}
            className="absolute confetti-piece"
            style={{
              left: `${left}%`,
              top: "-20px",
              width: `${size}px`,
              height: `${size * 0.4}px`,
              background: color,
              animationDelay: `${delay}ms`,
              animationDuration: `${dur}ms`,
            }}
          />
        );
      })}
      <style>{`
        @keyframes confetti-fall {
          0%   { transform: translateY(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(110vh) rotate(720deg); opacity: 0.2; }
        }
        .confetti-piece {
          border-radius: 2px;
          animation-name: confetti-fall;
          animation-timing-function: cubic-bezier(0.25, 0.46, 0.45, 0.94);
          animation-fill-mode: forwards;
        }
      `}</style>
    </div>
  );
}
