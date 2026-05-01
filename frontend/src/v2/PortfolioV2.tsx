/**
 * Skola · Min portfolio — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-portfolio):
 * - actor-head med pill, B/G/F-räknare
 * - section-eye + biz-table med 14 kompetenser sorterade efter nivå
 * - per kompetens: mastery-procent, B/G/F-pill, senaste händelse,
 *   nästa nivå-villkor
 * - peda "Portfolio är inte betyg — det är karta"
 *
 * Wellbeing-koppling: 5+ kompetenser på FÖRDJUPNING → +3 health.
 * 2-4 → +1 health.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2PortfolioData,
  type V2CompetencyEntry,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const LEVEL_COLOR: Record<string, string> = {
  B: "var(--text-dim)",
  G: "var(--accent)",
  F: "#6ee7b7",
};

const NEXT_HINT: Record<string, string> = {
  B: "→ G · gör 1 modul-steg klart",
  G: "→ F · gör 3+ steg klara",
  F: "— max",
};

export function PortfolioV2() {
  const [data, setData] = useState<V2PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    v2Api
      .portfolio()
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
              Kunde inte ladda portfolio
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
        <div className="bank-loading">Laddar portfolio…</div>
      </div>
    );
  }

  const s = data.summary;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Skola · Min portfolio</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {s.total_competencies} kompetenser, <em>din nivå</em>.
            </h1>
            <p className="actor-sub">
              Lärar-bedömt · syns för läraren och dina vårdnadshavare ·
              senast händelse{" "}
              {s.last_event_at
                ? SHORT_DATE(s.last_event_at)
                : "—"}
            </p>
          </div>
          <div className="actor-meta">
            B (basis): <strong>{s.basis_count}</strong>
            <br />
            G (grund): <strong style={{ color: "var(--accent)" }}>{s.grund_count}</strong>
            <br />
            F (fördjupning):{" "}
            <strong style={{ color: "#6ee7b7" }}>{s.fordjup_count}</strong>
          </div>
        </header>

        {/* SAMMANFATTNING · färg-kodade summary cards */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 22,
          }}
        >
          <SummaryCard
            level="B"
            count={s.basis_count}
            label="BASIS"
            sub="grundläggande förståelse"
          />
          <SummaryCard
            level="G"
            count={s.grund_count}
            label="GRUND"
            sub="kan applicera självständigt"
          />
          <SummaryCard
            level="F"
            count={s.fordjup_count}
            label="FÖRDJUPNING"
            sub="kan reflektera + lära ut"
          />
        </div>

        <div className="section-eye">
          {s.total_competencies} systemkompetenser · sorterat efter nivå
        </div>
        {data.competencies.length === 0 ? (
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
            Inga kompetenser registrerade än. Be läraren seedа default-
            kompetenser eller starta din första modul.
          </div>
        ) : (
          <div className="biz-table" style={{ marginBottom: 22 }}>
            <div
              className="biz-table-row head"
              style={{
                gridTemplateColumns: "36px 1.4fr 110px 1fr 130px",
              }}
            >
              <span></span>
              <span>Kompetens</span>
              <span>Nivå</span>
              <span>Senaste händelse</span>
              <span>Nästa nivå</span>
            </div>
            {data.competencies.map((c) => (
              <CompetencyRow key={c.competency_id} c={c} />
            ))}
          </div>
        )}

        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Portfolio är inte <em>betyg</em> — det är <em>karta</em>.
          </div>
          <p className="peda-prose">
            Du ser var du står på {s.total_competencies} dimensioner, vad
            du gjort som lett dit, och vad nästa nivå kräver. Läraren höjer
            manuellt baserat på vad hen ser — inte algoritm. Det är{" "}
            <em>läraren som professionellt bedömer</em>, AI som hjälpmedel.
            Detta sparas i din portfolio och följer dig genom skoltiden.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Mastery</strong>Beräknas på modul-steg klar × steg-
              vikt mot kompetensen.
            </li>
            <li>
              <strong>BASIS (B)</strong>Du har börjat — under 33 % mastery.
            </li>
            <li>
              <strong>GRUND (G)</strong>Du kan applicera — 33–66 %
              mastery.
            </li>
            <li>
              <strong>FÖRDJUPNING (F)</strong>Du kan reflektera och lära
              ut — 66 %+ mastery.
            </li>
          </ul>
          <div className="peda-tip">
            Wellbeing-koppling: 5+ kompetenser på FÖRDJUPNING → +3 health
            ("expertis bygger självkänsla"). 2–4 på F → +1 health. Klassas
            som health eftersom kunskap = trygg självbild.
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  level, count, label, sub,
}: {
  level: "B" | "G" | "F";
  count: number;
  label: string;
  sub: string;
}) {
  const color = LEVEL_COLOR[level];
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        borderLeftWidth: 3,
        borderLeftColor: color,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color,
        }}
      >
        {level} · {label}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 32,
          fontWeight: 700,
          fontStyle: "italic",
          marginTop: 4,
          color,
        }}
      >
        {count}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function CompetencyRow({ c }: { c: V2CompetencyEntry }) {
  return (
    <Link
      to={`/v2/kompetens/${c.competency_id}`}
      className="biz-table-row"
      style={{
        gridTemplateColumns: "36px 1.4fr 110px 1fr 130px",
        textDecoration: "none",
        color: "inherit",
      }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          fontWeight: 700,
          color: LEVEL_COLOR[c.level],
        }}
      >
        {c.level}
      </span>
      <div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 14,
            color: "#fff",
          }}
        >
          {c.name}
        </div>
        <div
          style={{
            fontFamily: "var(--mono)",
            fontSize: 9,
            color: "var(--text-dim)",
          }}
        >
          {c.completed_steps} steg klara · mastery{" "}
          {Math.round(c.mastery * 100)} %
        </div>
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          color: LEVEL_COLOR[c.level],
          fontWeight: 700,
          letterSpacing: "0.6px",
        }}
      >
        {c.level_label}
      </span>
      <span
        style={{
          fontSize: 12.5,
          color: "var(--text-mid)",
        }}
      >
        {c.last_event_at
          ? `${SHORT_DATE(c.last_event_at)} · senaste klar-händelse`
          : "— ingen aktivitet än"}
      </span>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: c.level === "F" ? "var(--text-dim)" : "var(--warm)",
        }}
      >
        {NEXT_HINT[c.level]}
      </span>
    </Link>
  );
}
