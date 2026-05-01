/**
 * Lärar-vy · pedagogik-paket (motsv. larare.html#p-peda).
 *
 * Routas via /teacher/v2/pedagogik.
 *
 * Visar:
 * - 5 stat-kort (begrepp / mest-stötta / sällan / under-exponerade)
 * - 2-kolumns layout: pedagogik-boxar (per aktör/verktyg/modul)
 * - Sidopanel: 14 kompetensers nivå-fördelning + AI-genererade
 *   åtgärds-förslag
 *
 * Concept-boxarna är hård-kodade i backend (8 st) — exposure räknas
 * från onboarding/modul-progress/mailbox/bankid-sessions.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2PedagogicsResponse,
  type V2PedaConceptBox,
  type V2PedaCompetencyDist,
  type V2PedaSuggestion,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

export function TeacherPedagogicsV2() {
  const [data, setData] = useState<V2PedagogicsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .teacherPedagogics()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda pedagogik-paket
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar pedagogik-paket…</div>
      </div>
    );
  }

  const s = data.summary;
  const quizPct = data.competency_distribution.length > 0
    ? Math.round(
        (data.competency_distribution.reduce(
          (a, c) => a + c.fordjup_count + c.grund_count,
          0,
        )
          / Math.max(
              data.competency_distribution.reduce(
                (a, c) =>
                  a + c.basis_count + c.grund_count + c.fordjup_count,
                0,
              ),
              1,
            ))
          * 100,
      )
    : 0;

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till klassen
        </a>

        <header className="larare-head">
          <div>
            <span className="pill">Pedagogik-paket · ✦</span>
            <h1 className="larare-head-h1">
              Det <em>osynliga</em> innehållet.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Varje aktör och verktyg har en pedagogik-box som introducerar
              begreppen i kontext. Här ser du vilka koncept klassen har stött
              på — och hur kompetenserna fördelar sig.
            </p>
          </div>
          <div className="larare-head-meta">
            {s.total_boxes} ✦-boxar i systemet
            <br />
            <strong>{s.total_concepts}</strong> begrepp totalt
            <br />
            Klass-aggregerat
          </div>
        </header>

        {/* 5 stat-kort */}
        <div className="larare-stats">
          <div className="larare-stat">
            <div className="larare-stat-eye">Begrepp i klassen</div>
            <div className="larare-stat-num">
              <em>{s.total_concepts}</em>
            </div>
            <div className="larare-stat-sub">
              {s.total_boxes} boxar · 4–6 begrepp/box
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Mest stötta</div>
            <div className="larare-stat-num">{s.most_seen_count}</div>
            <div className="larare-stat-sub">
              ≥ 20 elever har stött
            </div>
          </div>
          <div className="larare-stat">
            <div
              className={`larare-stat-num${s.rarely_seen_count > 0 ? " accent" : ""}`}
              style={{ marginBottom: 0 }}
            >
              <em>{s.rarely_seen_count}</em>
            </div>
            <div className="larare-stat-eye">Sällan stötta</div>
            <div className="larare-stat-sub">
              ≤ 5 elever · ev. modulgap
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Mastery ≥ G</div>
            <div className="larare-stat-num">{quizPct} %</div>
            <div className="larare-stat-sub">
              över alla kompetens-värden
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Under-exponerade</div>
            <div
              className={`larare-stat-num${s.underexposed_boxes > 0 ? " accent" : ""}`}
            >
              {s.underexposed_boxes > 0 ? (
                <em>{s.underexposed_boxes}</em>
              ) : (
                s.underexposed_boxes
              )}
            </div>
            <div className="larare-stat-sub">
              boxar med &lt; 5 elever
            </div>
          </div>
        </div>

        {/* 2-kolumns layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.5fr 1fr",
            gap: 28,
            marginBottom: 36,
          }}
        >
          <div>
            <div className="section-title">
              Pedagogik-boxarna · per aktör/verktyg/modul
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: 14,
              }}
            >
              {data.concept_boxes.map((box) => (
                <ConceptBoxCard key={box.key} box={box} />
              ))}
            </div>
          </div>

          <aside style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Kompetens-fördelning */}
            <div className="s-card">
              <div className="s-card-eye">
                {data.competency_distribution.length} systemkompetenser
              </div>
              <div className="s-card-h">
                Klassens <em>nivå-fördelning</em>
              </div>
              {data.competency_distribution.length === 0 ? (
                <p
                  style={{
                    fontFamily: "Source Serif 4, Georgia, serif",
                    fontSize: 13,
                    color: "rgba(255,255,255,0.5)",
                    margin: 0,
                  }}
                >
                  Inga kompetenser seedade än.
                </p>
              ) : (
                <ul
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: 0,
                    fontFamily: "Inter, sans-serif",
                    fontSize: 13,
                  }}
                >
                  {data.competency_distribution.map((c) => (
                    <CompetencyDistRow key={c.competency_id} c={c} />
                  ))}
                </ul>
              )}
              <div
                style={{
                  marginTop: 10,
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 9,
                  color: "rgba(255,255,255,0.4)",
                  letterSpacing: 0.4,
                }}
              >
                B = basis · G = grund · F = fördjupning
              </div>
            </div>

            {/* Förslag */}
            {data.suggestions.length > 0 && (
              <div className="s-card purple">
                <div className="s-card-eye purple">
                  Föreslagna åtgärder ({data.suggestions.length})
                </div>
                <div className="s-card-h">Heuristiskt genererade</div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                    marginTop: 8,
                  }}
                >
                  {data.suggestions.map((sug, i) => (
                    <SuggestionCard key={i} suggestion={sug} />
                  ))}
                </div>
              </div>
            )}

            {/* Interaktiva guider · placeholder */}
            <div className="s-card">
              <div className="s-card-eye">Interaktiva guider</div>
              <div className="s-card-h">
                13 guider <em>tillgängliga</em>
              </div>
              <p
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  color: "rgba(255,255,255,0.6)",
                  marginTop: 6,
                  letterSpacing: 0.5,
                }}
              >
                intro (auto efter onboarding) · postlådan · banken ·
                pentagon · maria · bankid · bokföring · budget · avanza ·
                skatt · modul · uppdrag · kompetens
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function ConceptBoxCard({ box }: { box: V2PedaConceptBox }) {
  const isCritical = box.is_critical;
  return (
    <div
      className={`s-card${isCritical ? " alert" : ""}`}
      style={{
        borderLeftWidth: 3,
        borderLeftStyle: "solid",
        borderLeftColor: isCritical
          ? "var(--accent, #dc4c2b)"
          : box.kind === "module"
          ? "#a5b4fc"
          : "var(--warm, #fbbf24)",
      }}
    >
      <div
        className={`s-card-eye${isCritical ? " accent" : ""}`}
      >
        {box.title}
      </div>
      <div className="s-card-h">
        {box.concepts.length} begrepp ·{" "}
        <em>{box.student_count}</em>{" "}
        elev{box.student_count === 1 ? "" : "er"}
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 13,
          color: "rgba(255,255,255,0.6)",
          lineHeight: 1.5,
          margin: 0,
        }}
      >
        {box.concepts.join(" · ")}
      </p>
      {box.note && (
        <p
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9.5,
            color: "var(--accent, #dc4c2b)",
            marginTop: 8,
            letterSpacing: 0.5,
          }}
        >
          {box.note}
        </p>
      )}
    </div>
  );
}

function CompetencyDistRow({ c }: { c: V2PedaCompetencyDist }) {
  const total = c.basis_count + c.grund_count + c.fordjup_count;
  const distColor = c.is_concerning
    ? "var(--accent, #dc4c2b)"
    : "rgba(255,255,255,0.6)";
  return (
    <li
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "6px 0",
        borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
      }}
    >
      <span>{c.name}</span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: distColor,
        }}
      >
        B {c.basis_count} · G {c.grund_count} · F {c.fordjup_count}
        {total > 0 && c.is_concerning && (
          <span style={{ color: "var(--accent, #dc4c2b)" }}> ⚠</span>
        )}
      </span>
    </li>
  );
}

function SuggestionCard({ suggestion }: { suggestion: V2PedaSuggestion }) {
  return (
    <div
      style={{
        padding: "12px 14px",
        background: "rgba(99,102,241,0.08)",
        border: "1px solid rgba(99,102,241,0.25)",
        borderLeft: "3px solid #818cf8",
        borderRadius: 6,
      }}
    >
      <div
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 13.5,
          fontWeight: 700,
          color: "#fff",
          marginBottom: 4,
        }}
      >
        {suggestion.title}
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 12.5,
          color: "rgba(255,255,255,0.7)",
          lineHeight: 1.45,
          margin: "0 0 8px",
        }}
      >
        {suggestion.body}
      </p>
      {suggestion.cta_target && (
        <Link
          to={suggestion.cta_target}
          className="attn-go"
          style={{
            display: "inline-block",
            border: "1px solid #a5b4fc",
            padding: "6px 12px",
            borderRadius: 100,
            color: "#a5b4fc",
            fontSize: 9,
          }}
        >
          {suggestion.cta_label} →
        </Link>
      )}
    </div>
  );
}
