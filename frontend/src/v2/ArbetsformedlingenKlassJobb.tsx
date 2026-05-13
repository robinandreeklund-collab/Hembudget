/**
 * ArbetsformedlingenKlassJobb · klass-företag-jobb-flik på Arbetsförmedlingen.
 *
 * Spec: dev/feature-allabolag.md (Fas D)
 *
 * Eleven ser jobb postade av klasskompisars klass-företag, kan ansöka
 * via personligt brev (samma flow som riktiga jobb). Vid acceptance
 * dyker företaget upp under "Mina anställningar".
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Topbar } from "./V2Topbar";


type JobAd = {
  id: number;
  company_name: string;
  industry_label: string | null;
  title: string;
  description: string;
  monthly_salary: number;
  status: string;
  posted_at: string;
  n_applicants: number;
  is_my_company: boolean;
  have_i_applied: boolean;
  my_application_status: string | null;
};

type Employment = {
  id: number;
  company_name: string;
  industry_label: string | null;
  monthly_salary: number;
  started_at: string;
  status: string;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function ArbetsformedlingenKlassJobb() {
  const [ads, setAds] = useState<JobAd[]>([]);
  const [employments, setEmployments] = useState<Employment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [applyingTo, setApplyingTo] = useState<JobAd | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([
      api<JobAd[]>("/v2/arbetsformedlingen/klass-jobb"),
      api<Employment[]>("/v2/arbetsformedlingen/mina-anstallningar"),
    ])
      .then(([a, e]) => {
        setAds(a);
        setEmployments(e);
      })
      .catch((e) => setError(String((e as Error).message || e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    document.body.setAttribute("data-mode", "private");
    refresh();
  }, []);

  return (
    <div className="v2-shell">
      <V2Topbar status={{ role: "student", is_super_admin: false }} />
      <div style={shellStyle}>
        <Link to="/v2/arbetsformedlingen" style={backLinkStyle}>
          ← Arbetsförmedlingen
        </Link>
        <header style={{ marginBottom: 28 }}>
          <span style={pillStyle}>● AKTÖR · ARBETSFÖRMEDLINGEN · KLASS-FÖRETAG</span>
          <h1 style={h1Style}>
            Jobb hos <em>klasskompisar</em>.
          </h1>
          <p style={leadStyle}>
            Klasskompisar som driver bolag postar jobbannonser här. Sök en
            tjänst genom att skriva ett personligt brev — företagsägaren
            väljer en sökande.
          </p>
        </header>

        {error && <div style={errorBoxStyle}>{error}</div>}

        {/* Mina anställningar */}
        {employments.length > 0 && (
          <section style={{ marginBottom: 32 }}>
            <div style={{ ...sectionEyeStyle, color: "#6ee7b7" }}>
              ● DINA ANSTÄLLNINGAR · klass-företag
            </div>
            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              {employments.map((e) => (
                <div key={e.id} style={{
                  padding: 14,
                  background: "linear-gradient(135deg, rgba(110,231,183,0.06), rgba(15,21,37,0.55))",
                  border: "1px solid rgba(110,231,183,0.30)",
                  borderRadius: 8,
                }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
                      {e.company_name}
                    </div>
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)" }}>
                      {e.industry_label || "—"}
                    </span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#6ee7b7" }}>
                      {SEK(e.monthly_salary)} kr/mån
                    </span>
                  </div>
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.45)", letterSpacing: 0.5, marginTop: 4 }}>
                    Anställd sedan {e.started_at}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Lediga jobb */}
        <div style={{ ...sectionEyeStyle, color: "#fbbf24" }}>
          ● LEDIGA TJÄNSTER · klass-företag
        </div>
        {loading && ads.length === 0 && (
          <div style={{ color: "rgba(255,255,255,0.6)", marginTop: 12 }}>
            Laddar…
          </div>
        )}
        {!loading && ads.length === 0 && (
          <div style={emptyStateStyle}>
            Inga klass-företag har lediga tjänster just nu. När någon klasskompis
            postar en annons dyker den upp här.
          </div>
        )}
        <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
          {ads.map((ad) => (
            <AdCard key={ad.id} ad={ad} onApply={() => setApplyingTo(ad)} />
          ))}
        </div>

        {applyingTo && (
          <ApplyModal
            ad={applyingTo}
            onClose={(refreshed) => {
              setApplyingTo(null);
              if (refreshed) refresh();
            }}
          />
        )}
      </div>
    </div>
  );
}


function AdCard({ ad, onApply }: { ad: JobAd; onApply: () => void }) {
  const isMine = ad.is_my_company;
  const applied = ad.have_i_applied;
  const accepted = ad.my_application_status === "accepted";
  const rejected = ad.my_application_status === "rejected";

  return (
    <div style={{
      padding: 18,
      background: accepted
        ? "rgba(110,231,183,0.06)"
        : rejected
          ? "rgba(220,76,43,0.05)"
          : "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(15,21,37,0.55))",
      border: `1px solid ${accepted ? "rgba(110,231,183,0.30)" : rejected ? "rgba(220,76,43,0.30)" : "rgba(99,102,241,0.30)"}`,
      borderRadius: 10,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={tagStyle}>KLASS-FÖRETAG</span>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
          {ad.title}
        </div>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
          {SEK(ad.monthly_salary)} kr/mån
        </span>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)", letterSpacing: 0.5, marginTop: 6 }}>
        {ad.company_name}{ad.industry_label ? ` · ${ad.industry_label}` : ""} · {ad.n_applicants} sökande
      </div>
      <p style={{ color: "rgba(255,255,255,0.78)", fontFamily: "Inter, sans-serif", fontSize: 13.5, lineHeight: 1.5, margin: "10px 0" }}>
        {ad.description}
      </p>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        {isMine && (
          <span style={{ ...statusPillStyle, color: "#fbbf24" }}>
            DITT BOLAG · sökande visas i biz
          </span>
        )}
        {!isMine && !applied && (
          <button onClick={onApply} style={btnPrimary}>Sök tjänsten →</button>
        )}
        {!isMine && applied && (
          <span style={{
            ...statusPillStyle,
            color: accepted ? "#6ee7b7" : rejected ? "#fda594" : "#fbbf24",
          }}>
            {accepted ? "✓ ANSTÄLLD" : rejected ? "AVSLAGEN" : "DU HAR ANSÖKT · väntar"}
          </span>
        )}
      </div>
    </div>
  );
}


function ApplyModal({
  ad, onClose,
}: { ad: JobAd; onClose: (refreshed: boolean) => void }) {
  const [coverLetter, setCoverLetter] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      await api(`/v2/arbetsformedlingen/klass-jobb/${ad.id}/apply`, {
        method: "POST",
        body: JSON.stringify({ cover_letter: coverLetter.trim() }),
      });
      onClose(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div onClick={() => onClose(false)} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: "#0f1525", border: "1px solid rgba(99,102,241,0.4)",
        borderRadius: 12, padding: 24, maxWidth: 600, width: "100%",
      }}>
        <h2 style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", marginTop: 0 }}>
          Sök · {ad.title}
        </h2>
        <div style={{
          background: "rgba(99,102,241,0.06)",
          border: "1px solid rgba(99,102,241,0.2)",
          borderRadius: 6, padding: 12, marginTop: 8,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "#818cf8", letterSpacing: 1.4 }}>
            {ad.company_name} · {ad.industry_label || "—"}
          </div>
          <p style={{ color: "rgba(255,255,255,0.85)", fontFamily: "Inter, sans-serif", fontSize: 13, marginTop: 6 }}>
            {ad.description}
          </p>
          <p style={{ color: "#fbbf24", fontFamily: "JetBrains Mono, monospace", fontSize: 11, marginTop: 6 }}>
            Lön: {SEK(ad.monthly_salary)} kr/mån
          </p>
        </div>
        <label style={{ color: "white", display: "block", marginTop: 14 }}>
          Personligt brev (min 20 tecken)
          <textarea
            value={coverLetter}
            onChange={(e) => setCoverLetter(e.target.value)}
            placeholder="Berätta varför just du är rätt för jobbet. Vad har du för erfarenhet, intresse, drivkraft?"
            style={{ ...inputStyle, minHeight: 140 }}
          />
        </label>
        {err && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={submit} disabled={submitting || coverLetter.length < 20} style={btnPrimary}>
            {submitting ? "Skickar…" : "Skicka ansökan →"}
          </button>
          <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
        </div>
      </div>
    </div>
  );
}


// === Styles ===
const shellStyle: React.CSSProperties = {
  maxWidth: 1100, margin: "0 auto", padding: "32px 24px 80px",
};

const backLinkStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
  color: "rgba(255,255,255,0.55)", letterSpacing: 1.2,
  textDecoration: "none", display: "inline-block", marginBottom: 18,
};

const pillStyle: React.CSSProperties = {
  display: "inline-block", padding: "5px 14px", borderRadius: 100,
  background: "rgba(99,102,241,0.10)", border: "1px solid rgba(99,102,241,0.30)",
  fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700,
  letterSpacing: 1.6, color: "#c7d2fe",
};

const h1Style: React.CSSProperties = {
  fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700,
  fontSize: 38, letterSpacing: -0.6, color: "#fff",
  margin: "12px 0 8px", lineHeight: 1.1,
};

const leadStyle: React.CSSProperties = {
  fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17,
  lineHeight: 1.55, color: "rgba(255,255,255,0.7)", margin: 0, maxWidth: 720,
};

const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
  fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe",
};

const tagStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700,
  letterSpacing: 1.4, padding: "3px 8px", background: "rgba(99,102,241,0.20)",
  border: "1px solid rgba(99,102,241,0.4)", color: "#c7d2fe", borderRadius: 4,
};

const statusPillStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 10,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase",
  padding: "4px 10px", background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.12)", borderRadius: 100,
};

const inputStyle: React.CSSProperties = {
  width: "100%", marginTop: 6, padding: 10,
  background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 6, color: "#fff",
  fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.5,
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24", border: "none", color: "#422006",
  padding: "10px 20px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent", border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.7)",
  padding: "10px 20px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const emptyStateStyle: React.CSSProperties = {
  padding: "32px 24px", textAlign: "center",
  background: "rgba(15,21,37,0.5)", border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 10, color: "rgba(255,255,255,0.7)",
  fontFamily: "Source Serif 4, Georgia, serif", marginTop: 12,
};

const errorBoxStyle: React.CSSProperties = {
  padding: 12, background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)", borderRadius: 6,
  color: "#fda594", fontFamily: "Source Serif 4, Georgia, serif",
  marginBottom: 14,
};
