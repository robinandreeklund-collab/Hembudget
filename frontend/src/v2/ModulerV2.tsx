/**
 * Skola 09 · Mina moduler — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-modules):
 * - actor-head med pill, pågående/klara/snitt-progress
 * - cc-summary med 3 stora cards för pågående moduler (current step,
 *   progress-bar, klicka för att fortsätta)
 * - acct-grid med möjliga moduler
 * - peda-block "Moduler är scaffolding, inte föreläsningar"
 *
 * Modulen leder till v1-vyn /modules/{id} eller /modules där
 * själva genomförandet sker (oförändrat — v2 ger bara översikt-vyn).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2ModulerData,
  type V2ModuleProgressOut,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

export function ModulerV2() {
  const [data, setData] = useState<V2ModulerData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    v2Api
      .moduler()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda moduler
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar moduler…</div>
      </div>
    );
  }

  const s = data.summary;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell" data-guide="moduler-list">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Skola · Mina moduler</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {s.in_progress_count} i <em>arbete</em>,{" "}
              {s.available_count} möjliga.
            </h1>
            <p className="actor-sub">
              Lärar-tilldelade systemmoduler · stegen leder dig genom
              appens funktioner ·{" "}
              {s.completed_count > 0
                ? `${s.completed_count} klara hittills`
                : "ingen klar än"}
            </p>
          </div>
          <div className="actor-meta">
            Pågående: <strong>{s.in_progress_count}</strong>
            <br />
            Klara: <strong>{s.completed_count}</strong>
            <br />
            Snitt-progress:{" "}
            <strong>{Math.round(s.avg_progress_pct)} %</strong>
          </div>
        </header>

        {/* CC-SUMMARY · pågående moduler som kort */}
        {data.in_progress.length > 0 && (
          <div
            className="cc-summary"
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${Math.min(data.in_progress.length, 3)}, 1fr)`,
              gap: 12,
              marginBottom: 22,
            }}
          >
            {data.in_progress.slice(0, 3).map((m) => (
              <ProgressCard key={m.student_module_id} m={m} />
            ))}
          </div>
        )}

        {/* MÖJLIGA · acct-grid */}
        <div className="section-eye">
          Möjliga moduler · klicka för att starta
        </div>
        {data.available.length === 0 && data.completed.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Inga moduler tillgängliga än. Be läraren tilldela en
            systemmodul (t.ex. "Din första månad") eller skapa en egen
            modul i lärar-vyn.
          </div>
        ) : (
          <div
            className="acct-grid"
            style={{
              gridTemplateColumns: "repeat(3, 1fr)",
              marginBottom: 22,
            }}
          >
            {/* Klara moduler först */}
            {data.completed.map((m) => (
              <Link
                to={`/modules/${m.module_id}`}
                key={`done-${m.student_module_id}`}
                className="acct"
                style={{ textDecoration: "none" }}
              >
                <div>
                  <div className="acct-eye">SYSTEMMODUL</div>
                  <div className="acct-name">{m.title}</div>
                  <div className="acct-num">
                    {m.step_count} steg ·{" "}
                    {m.estimated_minutes_left || 0} min · klar{" "}
                    {SHORT_DATE(m.completed_at)}
                  </div>
                </div>
                <div>
                  <div
                    className="acct-bal"
                    style={{ color: "#6ee7b7" }}
                  >
                    Klar
                  </div>
                  <div className="acct-bal-meta">visa →</div>
                </div>
              </Link>
            ))}
            {/* Tillgängliga */}
            {data.available.map((m) => (
              <Link
                to={`/modules/${m.module_id}`}
                key={`av-${m.module_id}`}
                className="acct"
                style={
                  !m.is_template
                    ? {
                        borderColor: "rgba(99,102,241,0.4)",
                        background: "rgba(99,102,241,0.04)",
                        textDecoration: "none",
                      }
                    : { textDecoration: "none" }
                }
              >
                <div>
                  <div
                    className="acct-eye"
                    style={!m.is_template ? { color: "#c7d2fe" } : undefined}
                  >
                    {m.is_template
                      ? "SYSTEMMODUL"
                      : m.teacher_owned
                      ? "EGEN MODUL · LÄRARE"
                      : "MODUL"}
                    {!m.is_template && m.teacher_owned ? "" : ""}
                  </div>
                  <div className="acct-name">{m.title}</div>
                  <div className="acct-num">
                    {m.step_count} steg · ~{" "}
                    {m.estimated_total_minutes} min · ej startad
                  </div>
                </div>
                <div>
                  <div
                    className="acct-bal"
                    style={{
                      color: !m.is_template ? "#c7d2fe" : "var(--text-mid)",
                    }}
                  >
                    Starta {!m.is_template ? "→" : ""}
                  </div>
                  <div className="acct-bal-meta">
                    {m.is_template ? "—" : "klicka"}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Moduler är <em>scaffolding</em>, inte föreläsningar.
          </div>
          <p className="peda-prose">
            Modulerna leder dig genom appens funktioner med pedagogisk
            styrning — men du kan alltid hoppa runt utanför modulen.
            Modulen säger "öppna lånekalkylatorn nu" — appen kan
            användas hela tiden ändå. Det handlar om{" "}
            <em>guidning</em>, inte tvång.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Steg-typer</strong>Läs · titta · reflektera ·
              uppgift · quiz · samarbete.
            </li>
            <li>
              <strong>Heartbeat</strong>App pingar var 30 sek för
              time-on-task-statistik.
            </li>
            <li>
              <strong>Kompetenskoppling</strong>Varje steg höjer en
              eller fler kompetenser.
            </li>
            <li>
              <strong>Adaptivitet</strong>Lärare kan tilldela olika
              moduler till olika elever.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Scaffolding</span>
            <span className="peda-concept">Time-on-task</span>
            <span className="peda-concept">Kompetensmål</span>
            <span className="peda-concept">Bedömning</span>
            <span className="peda-concept">Rubric</span>
          </div>
          <div className="peda-tip">
            {s.completed_count >= 3
              ? "Bra jobbat! 3+ klara moduler ger +leisure i wellbeing-pentagonen."
              : "Klara 3 moduler för en bonus i wellbeing-pentagonen (leisure)."}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProgressCard({ m }: { m: V2ModuleProgressOut }) {
  return (
    <Link
      to={`/modules/${m.module_id}`}
      className="cc-stat"
      style={{
        textDecoration: "none",
        borderLeft: "3px solid var(--warm)",
        paddingLeft: 16,
        cursor: "pointer",
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        background: "rgba(220,76,43,0.04)",
        display: "block",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--warm)",
          marginBottom: 6,
        }}
      >
        PÅGÅR · steg {m.current_step_no || m.completed_step_count + 1}/
        {m.step_count} · klicka →
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 22,
          fontStyle: "italic",
          fontWeight: 700,
          marginBottom: 6,
        }}
      >
        {m.title}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--text-mid)",
          marginBottom: 12,
          minHeight: 14,
        }}
      >
        {m.summary || `${m.step_count} steg totalt`}
        {m.estimated_minutes_left
          ? ` · ${m.estimated_minutes_left} min kvar`
          : ""}
      </div>
      <div
        style={{
          height: 6,
          background: "rgba(255,255,255,0.06)",
          borderRadius: 100,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${m.progress_pct}%`,
            background: "var(--warm)",
            borderRadius: 100,
          }}
        />
      </div>
    </Link>
  );
}
