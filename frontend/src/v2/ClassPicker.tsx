/**
 * Klass-väljare i lärarens topbar (Bug 7).
 *
 * Visar en pill med valt klass-namn ("Klassen 9C ▾"). Klick öppnar en
 * dropdown med alla lärarens klasser. Vald klass sparas i localStorage
 * och delas med TeacherHubV2 via custom event "class-changed" så hubben
 * filtrerar elever baserat på vald klass.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";

type SchoolClass = {
  id: number;
  label: string;
  display_name: string | null;
  description: string | null;
  is_archived: boolean;
  student_count: number;
};

const KEY = "hb_teacher_class_label";

export function readSelectedClass(): string {
  return localStorage.getItem(KEY) || "";
}

function writeSelectedClass(label: string) {
  if (label) localStorage.setItem(KEY, label);
  else localStorage.removeItem(KEY);
  window.dispatchEvent(
    new CustomEvent("class-changed", { detail: { label } }),
  );
}

export function ClassPicker() {
  const [classes, setClasses] = useState<SchoolClass[]>([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string>(readSelectedClass());
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api<SchoolClass[]>("/v2/teacher/classes")
      .then(setClasses)
      .catch(() => setClasses([]));
  }, []);

  // Stäng dropdown när man klickar utanför
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  function pick(label: string) {
    setSelected(label);
    writeSelectedClass(label);
    setOpen(false);
  }

  const selectedClass = classes.find((c) => c.label === selected);
  const labelText = selectedClass
    ? selectedClass.display_name || `Klassen ${selectedClass.label}`
    : selected
    ? `Klassen ${selected}`
    : "Alla elever";

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Välj klass"
        style={{
          background: open
            ? "rgba(99,102,241,0.15)"
            : "rgba(255,255,255,0.04)",
          border: open
            ? "1px solid rgba(99,102,241,0.45)"
            : "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          color: open ? "#c7d2fe" : "var(--text, rgba(255,255,255,0.92))",
          padding: "6px 14px",
          borderRadius: 100,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "1.4px",
          textTransform: "uppercase",
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          whiteSpace: "nowrap",
        }}
      >
        <span>{labelText}</span>
        <span style={{ fontSize: 9, opacity: 0.6 }}>▾</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            minWidth: 240,
            background: "var(--bg-mid, #0f1525)",
            border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
            borderRadius: 10,
            boxShadow: "0 16px 48px -10px rgba(0,0,0,0.5)",
            zIndex: 1000,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              color: "var(--text-dim, rgba(255,255,255,0.4))",
              fontWeight: 700,
            }}
          >
            Välj klass
          </div>

          <button
            type="button"
            onClick={() => pick("")}
            style={{
              width: "100%",
              textAlign: "left",
              background:
                selected === ""
                  ? "rgba(99,102,241,0.12)"
                  : "transparent",
              border: 0,
              padding: "10px 16px",
              color: selected === "" ? "#c7d2fe" : "var(--text)",
              cursor: "pointer",
              fontFamily: "Inter, sans-serif",
              fontSize: 13,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>
              <strong>Alla elever</strong>
            </span>
            {selected === "" && <span>✓</span>}
          </button>

          {classes.length === 0 ? (
            <div
              style={{
                padding: "12px 16px",
                color: "var(--text-mid, rgba(255,255,255,0.6))",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                fontStyle: "italic",
              }}
            >
              Inga klasser skapade än.
            </div>
          ) : (
            classes
              .filter((c) => !c.is_archived)
              .map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => pick(c.label)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background:
                      selected === c.label
                        ? "rgba(99,102,241,0.12)"
                        : "transparent",
                    border: 0,
                    borderTop:
                      "1px solid var(--line, rgba(255,255,255,0.06))",
                    padding: "10px 16px",
                    color:
                      selected === c.label ? "#c7d2fe" : "var(--text)",
                    cursor: "pointer",
                    fontFamily: "Inter, sans-serif",
                    fontSize: 13,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>
                    <strong>
                      {c.display_name || `Klassen ${c.label}`}
                    </strong>{" "}
                    <span
                      style={{
                        color: "var(--text-dim, rgba(255,255,255,0.4))",
                        fontSize: 11,
                      }}
                    >
                      · {c.student_count}{" "}
                      {c.student_count === 1 ? "elev" : "elever"}
                    </span>
                  </span>
                  {selected === c.label && <span>✓</span>}
                </button>
              ))
          )}

          <div
            style={{
              padding: "8px 16px",
              borderTop: "1px solid var(--line, rgba(255,255,255,0.1))",
            }}
          >
            <Link
              to="/teacher/v2/klasser"
              onClick={() => setOpen(false)}
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: 1.2,
                textTransform: "uppercase",
                fontWeight: 700,
                color: "var(--accent, #dc4c2b)",
                textDecoration: "none",
              }}
            >
              + Hantera klasser →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
