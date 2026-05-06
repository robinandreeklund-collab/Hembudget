/**
 * LeaderboardV2 · multi-kategori scoreboard + badges + entreprenörspoäng.
 * Spec: Fas H · dev/feature-allabolag.md
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Topbar } from "./V2Topbar";


type LeaderRow = {
  rank: number;
  student_id: number;
  student_display: string;
  company_name: string;
  company_level: string;
  metric_value: number;
  is_mine: boolean;
};

type Category = {
  key: string;
  label: string;
  emoji: string;
  desc: string;
  rows: LeaderRow[];
};

type Badge = {
  key: string;
  emoji: string;
  label: string;
  desc: string;
  earned_at: string | null;
  is_earned: boolean;
};

type Score = {
  student_id: number;
  total_points: number;
  badges: Badge[];
  n_earned: number;
  n_total: number;
};


const SEK = (n: number) => new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function LeaderboardV2() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [score, setScore] = useState<Score | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.body.setAttribute("data-mode", "private");
    Promise.all([
      api<Category[]>("/v2/leaderboard/categories"),
      api<Score>("/v2/leaderboard/me").catch(() => null),
    ])
      .then(([c, s]) => { setCategories(c); setScore(s); })
      .catch((e) => setError(String((e as Error).message || e)));
  }, []);

  return (
    <div className="v2-shell">
      <V2Topbar status={{ role: "student", is_super_admin: false }} />
      <div style={shellStyle}>
        <Link to="/v2/allabolag" style={backLinkStyle}>← Allabolag</Link>
        <header style={{ marginBottom: 28 }}>
          <span style={pillStyle}>● AKTÖR · KLASSENS LEADERBOARD</span>
          <h1 style={h1Style}>
            12 kategorier — <em style={{ color: "#fbbf24" }}>alla kan vinna</em>.
          </h1>
          <p style={leadStyle}>
            Scoreboards i 12 olika kategorier. Du behöver inte vara störst —
            kanske bäst marginal? Mest stabil? Comeback-kid? Här ser du var du
            ligger i klassen.
          </p>
        </header>

        {error && <div style={errorBoxStyle}>{error}</div>}

        {/* Min entreprenörspoäng */}
        {score && (
          <div style={{ ...cardStyle, marginBottom: 26 }}>
            <div style={sectionEyeStyle}>● ENTREPRENÖRSPOÄNG · DIN KARRIÄR</div>
            <div style={{ display: "flex", gap: 28, marginTop: 12, alignItems: "baseline" }}>
              <div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.4)" }}>POÄNG</div>
                <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontSize: 36, fontWeight: 700, color: "#fbbf24" }}>
                  {SEK(score.total_points)}
                </div>
              </div>
              <div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.4)" }}>BADGES</div>
                <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontSize: 24, fontWeight: 700, color: "#c7d2fe" }}>
                  {score.n_earned} / {score.n_total}
                </div>
              </div>
            </div>
            <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {score.badges.map((b) => (
                <div
                  key={b.key}
                  title={b.desc}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 100,
                    background: b.is_earned ? "rgba(110,231,183,0.10)" : "rgba(15,21,37,0.5)",
                    border: `1px solid ${b.is_earned ? "rgba(110,231,183,0.35)" : "rgba(255,255,255,0.10)"}`,
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 11,
                    color: b.is_earned ? "#fff" : "rgba(255,255,255,0.35)",
                    display: "flex",
                    gap: 6,
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontSize: 14, opacity: b.is_earned ? 1 : 0.3 }}>{b.emoji}</span>
                  <span>{b.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Kategorier */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          {categories.map((c) => (
            <CategoryBox key={c.key} cat={c} />
          ))}
        </div>
      </div>
    </div>
  );
}


function CategoryBox({ cat }: { cat: Category }) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 22 }}>{cat.emoji}</span>
        <h3 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff", margin: 0 }}>
          {cat.label}
        </h3>
      </div>
      <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 12.5, color: "rgba(255,255,255,0.6)", margin: "4px 0 12px" }}>
        {cat.desc}
      </p>
      {cat.rows.length === 0 ? (
        <div style={{ color: "rgba(255,255,255,0.45)", fontSize: 13, fontStyle: "italic" }}>
          Inga deltagare än.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 4 }}>
          {cat.rows.map((r) => {
            const medal = r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : `#${r.rank}`;
            return (
              <div key={r.student_id + ":" + cat.key} style={{
                display: "grid",
                gridTemplateColumns: "32px 1fr auto",
                gap: 8,
                padding: "5px 8px",
                background: r.is_mine ? "rgba(251,191,36,0.06)" : "transparent",
                border: `1px solid ${r.is_mine ? "rgba(251,191,36,0.3)" : "transparent"}`,
                borderRadius: 6,
                alignItems: "center",
              }}>
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, fontWeight: 700, color: "#fff" }}>{medal}</span>
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "#fff" }}>
                  {r.company_name}
                  <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11 }}>{" · " + r.student_display}</span>
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, color: "#fbbf24", fontWeight: 700 }}>
                  {Math.abs(r.metric_value) < 100 ? r.metric_value.toFixed(1) : SEK(Math.round(r.metric_value))}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// === Styles ===
const shellStyle: React.CSSProperties = { maxWidth: 1100, margin: "0 auto", padding: "32px 24px 80px" };
const backLinkStyle: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, color: "rgba(255,255,255,0.55)", letterSpacing: 1.2, textDecoration: "none", display: "inline-block", marginBottom: 18 };
const pillStyle: React.CSSProperties = { display: "inline-block", padding: "5px 14px", borderRadius: 100, background: "rgba(99,102,241,0.10)", border: "1px solid rgba(99,102,241,0.30)", fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700, letterSpacing: 1.6, color: "#c7d2fe" };
const h1Style: React.CSSProperties = { fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700, fontSize: 38, letterSpacing: -0.6, color: "#fff", margin: "12px 0 8px", lineHeight: 1.1 };
const leadStyle: React.CSSProperties = { fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, lineHeight: 1.55, color: "rgba(255,255,255,0.7)", margin: 0, maxWidth: 720 };
const cardStyle: React.CSSProperties = { background: "rgba(15,21,37,0.55)", border: "1px solid rgba(255,255,255,0.10)", borderRadius: 10, padding: 16 };
const sectionEyeStyle: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe" };
const errorBoxStyle: React.CSSProperties = { padding: 12, background: "rgba(220,76,43,0.08)", border: "1px solid rgba(220,76,43,0.35)", borderRadius: 6, color: "#fda594", fontFamily: "Source Serif 4, Georgia, serif", marginBottom: 14 };
