/**
 * GuideDropdown — knapp i sidebar/header som öppnar dropdown med
 * 11 guider att välja mellan. Speglar prototypens .guide-dropdown.
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GUIDES } from "./guidesData";
import { useGuide } from "./GuideContext";

export function GuideDropdown() {
  const { startGuide, completedKeys } = useGuide();
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(
    null,
  );
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Positionera dropdown anchor:ad mot knappen — beräknas i fixed
  // koordinater eftersom dropdown renderas via Portal i body, utanför
  // knappens stacking-context.
  useEffect(() => {
    if (!open || !buttonRef.current) return;
    const r = buttonRef.current.getBoundingClientRect();
    setAnchor({
      top: r.bottom + 8,
      right: window.innerWidth - r.right,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      const target = e.target as Node;
      const inButton = buttonRef.current?.contains(target);
      const inDropdown = dropdownRef.current?.contains(target);
      if (!inButton && !inDropdown) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const guides = Object.values(GUIDES);

  return (
    <>
      <button
        type="button"
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        title="Interaktiva guider"
        className="tb-echo tb-echo-ghost"
      >
        <span style={{ marginRight: 4 }}>✦</span>
        <span>Guider</span>
      </button>

      {open && anchor && createPortal(
        <div
          ref={dropdownRef}
          className="guide-dropdown show"
          style={{
            position: "fixed",
            top: anchor.top,
            right: anchor.right,
            minWidth: 380,
            maxWidth: "calc(100vw - 40px)",
            // Portal-renderat i body → konkurrerar globalt med allt på
            // sidan. Höjt långt över alla stacking-contexts.
            zIndex: 9990,
            background: "rgba(15,21,37,0.98)",
            border: "1px solid rgba(251,191,36,0.3)",
            borderRadius: 8,
            boxShadow: "0 18px 40px rgba(0,0,0,0.4)",
          }}
        >
          <div
            style={{
              padding: "16px 20px",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono, monospace)",
                fontSize: 9.5,
                fontWeight: 700,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "var(--warm)",
              }}
            >
              ✦ Interaktiva guider
            </div>
            <div
              style={{
                fontFamily: "var(--serif, serif)",
                fontSize: 18,
                fontWeight: 700,
                marginTop: 4,
              }}
            >
              Vilken vill du{" "}
              <em style={{ fontStyle: "italic", color: "var(--warm)" }}>
                öva på
              </em>
              ?
            </div>
            <div
              style={{
                fontFamily: "var(--mono, monospace)",
                fontSize: 10,
                color: "rgba(255,255,255,0.5)",
                marginTop: 4,
                letterSpacing: "0.6px",
              }}
            >
              {guides.length} guider · klicka för att starta · kan när
              som helst pausas
            </div>
          </div>
          <div
            style={{
              padding: "6px 0",
              maxHeight: 480,
              overflowY: "auto",
            }}
          >
            {guides.map((g) => {
              const done = completedKeys.has(g.key);
              return (
                <a
                  key={g.key}
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    setOpen(false);
                    startGuide(g.key);
                  }}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "32px 1fr 90px",
                    gap: 12,
                    alignItems: "center",
                    padding: "10px 18px",
                    textDecoration: "none",
                    color: "inherit",
                    cursor: "pointer",
                    background: done
                      ? "rgba(110,231,183,0.04)"
                      : "transparent",
                    transition: "background .15s ease",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background =
                      "rgba(251,191,36,0.06)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = done
                      ? "rgba(110,231,183,0.04)"
                      : "transparent";
                  }}
                >
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: done
                        ? "rgba(110,231,183,0.18)"
                        : "rgba(251,191,36,0.18)",
                      border: done
                        ? "1px solid #6ee7b7"
                        : "1px solid var(--warm)",
                      display: "grid",
                      placeItems: "center",
                      fontFamily: "var(--mono, monospace)",
                      fontSize: 11,
                      fontWeight: 700,
                      color: done ? "#6ee7b7" : "var(--warm)",
                    }}
                  >
                    {done ? "✓" : g.icon}
                  </div>
                  <div>
                    <div
                      style={{
                        fontFamily: "var(--serif, serif)",
                        fontSize: 14,
                        fontWeight: 700,
                      }}
                    >
                      {g.label}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--mono, monospace)",
                        fontSize: 10,
                        color: "rgba(255,255,255,0.5)",
                        marginTop: 2,
                      }}
                    >
                      {g.sub}
                    </div>
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono, monospace)",
                      fontSize: 9,
                      color: "rgba(255,255,255,0.55)",
                      textAlign: "right",
                      lineHeight: 1.4,
                    }}
                  >
                    <strong style={{ color: "var(--warm)" }}>
                      {g.time.split(" · ")[0]}
                    </strong>
                    <br />
                    {g.time.split(" · ")[1] || ""}
                  </div>
                </a>
              );
            })}
          </div>
          <div
            style={{
              padding: "12px 20px",
              borderTop: "1px solid rgba(255,255,255,0.08)",
              fontFamily: "var(--mono, monospace)",
              fontSize: 10,
              color: "rgba(255,255,255,0.5)",
              lineHeight: 1.5,
            }}
          >
            Tip: kör <strong style={{ color: "var(--warm)" }}>Intro</strong>{" "}
            först om det är din första gång. Övriga guider antar
            grundläggande förståelse.
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
