/**
 * BizJobAds · Företagsägaren publicerar jobbannonser och hanterar
 * ansökningar.
 *
 * Spec: dev/feature-allabolag.md (Fas D)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { BizActorShell } from "./BizActorShell";


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
};

type Application = {
  id: number;
  job_ad_id: number;
  applicant_display: string;
  cover_letter: string;
  status: string;
  submitted_at: string;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizJobAds() {
  const [ads, setAds] = useState<JobAd[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api<JobAd[]>("/v2/foretag/job-ads/mine")
      .then(setAds)
      .catch((e) => setError(String((e as Error).message || e)));
  }

  useEffect(() => { refresh(); }, []);

  const open = ads.filter((a) => a.status === "open");
  const filled = ads.filter((a) => a.status !== "open");

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Anställ klasskompis"
      title={
        <>
          Anställ en <em>klasskompis</em>.
        </>
      }
      subtitle="Posta jobbannons på Arbetsförmedlingen · klasskompisar söker · välj en"
      meta={
        <>
          Öppna annonser: <strong>{open.length}</strong>
          <br />
          Tillsatta: <strong>{filled.length}</strong>
        </>
      }
    >
      {error && <div style={errorBoxStyle}>{error}</div>}

      <button onClick={() => setShowCreate(true)} style={btnPrimary}>
        + Posta ny jobbannons
      </button>

      {open.length > 0 && (
        <>
          <div style={{ ...sectionEyeStyle, color: "#fbbf24", marginTop: 28, marginBottom: 12 }}>
            ● ÖPPNA ANNONSER · väntar på sökande
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            {open.map((a) => (
              <AdCard key={a.id} ad={a} onChanged={refresh} />
            ))}
          </div>
        </>
      )}

      {filled.length > 0 && (
        <>
          <div style={{ ...sectionEyeStyle, marginTop: 28, marginBottom: 12 }}>
            ● TILLSATTA / STÄNGDA
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {filled.map((a) => (
              <div key={a.id} style={{
                padding: 14,
                background: "rgba(15,21,37,0.4)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 8,
              }}>
                <div style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", fontWeight: 700 }}>
                  {a.title}
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)", letterSpacing: 0.6, marginTop: 4 }}>
                  {SEK(a.monthly_salary)} kr/mån · {a.n_applicants} ansökningar · {a.status}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {ads.length === 0 && (
        <div style={emptyStateStyle}>
          Du har inga jobbannonser. Klicka "Posta ny jobbannons" för att hitta en klasskompis till bolaget.
        </div>
      )}

      {showCreate && (
        <CreateAdModal onClose={(refreshed) => {
          setShowCreate(false);
          if (refreshed) refresh();
        }} />
      )}
    </BizActorShell>
  );
}


function AdCard({ ad, onChanged }: { ad: JobAd; onChanged: () => void }) {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [loadingApps, setLoadingApps] = useState(false);

  async function loadApps() {
    if (applications !== null) {
      setApplications(null);
      return;
    }
    setLoadingApps(true);
    try {
      const data = await api<Application[]>(
        `/v2/foretag/job-ads/${ad.id}/applications`,
      );
      setApplications(data);
    } finally {
      setLoadingApps(false);
    }
  }

  async function decide(appId: number, decision: "accepted" | "rejected") {
    if (decision === "accepted" && !confirm("Anställa denna sökande? (Övriga ansökningar avslås automatiskt.)")) return;
    try {
      await api(`/v2/foretag/job-ads/${ad.id}/applications/${appId}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      // Refresh allt
      const data = await api<Application[]>(
        `/v2/foretag/job-ads/${ad.id}/applications`,
      );
      setApplications(data);
      onChanged();
    } catch (e) {
      alert(`Fel: ${(e as Error).message || e}`);
    }
  }

  return (
    <div style={{
      padding: 16,
      background: "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(15,21,37,0.55))",
      border: "1px solid rgba(99,102,241,0.30)",
      borderRadius: 10,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
          {ad.title}
        </div>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
          {SEK(ad.monthly_salary)} kr/mån
        </span>
        <span style={{ flex: 1 }} />
        <button onClick={loadApps} style={btnGhost}>
          {applications !== null ? "DÖLJ" : "VISA"} {ad.n_applicants} ANSÖKNINGAR
        </button>
      </div>
      <p style={{ color: "rgba(255,255,255,0.78)", fontFamily: "Inter, sans-serif", fontSize: 13, lineHeight: 1.5, margin: "8px 0" }}>
        {ad.description}
      </p>
      {loadingApps && <div style={{ color: "#c7d2fe" }}>Laddar ansökningar…</div>}
      {applications !== null && applications.length === 0 && (
        <div style={{ color: "rgba(255,255,255,0.55)", fontStyle: "italic", marginTop: 8 }}>
          Inga ansökningar än.
        </div>
      )}
      {applications && applications.length > 0 && (
        <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
          {applications.map((app) => (
            <div key={app.id} style={{
              padding: 12,
              background: app.status === "accepted" ? "rgba(110,231,183,0.06)" : app.status === "rejected" ? "rgba(220,76,43,0.05)" : "rgba(0,0,0,0.18)",
              border: `1px solid ${app.status === "accepted" ? "rgba(110,231,183,0.3)" : app.status === "rejected" ? "rgba(220,76,43,0.3)" : "rgba(255,255,255,0.08)"}`,
              borderRadius: 6,
            }}>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, color: "#fff", fontWeight: 700 }}>
                  {app.applicant_display}
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.5)", letterSpacing: 1 }}>
                  {app.status.toUpperCase()}
                </span>
              </div>
              <p style={{ color: "rgba(255,255,255,0.85)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.5, margin: "8px 0" }}>
                {app.cover_letter}
              </p>
              {app.status === "pending" && (
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => decide(app.id, "accepted")} style={btnPrimary}>Anställ</button>
                  <button onClick={() => decide(app.id, "rejected")} style={btnGhost}>Avslå</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function CreateAdModal({ onClose }: { onClose: (refreshed: boolean) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [salary, setSalary] = useState("28000");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    const t = title.trim();
    const d = description.trim();
    const s = parseInt(salary, 10);
    if (t.length < 3) { setErr("Titeln måste vara minst 3 tecken."); return; }
    if (d.length < 10) {
      setErr("Beskriv jobbet med minst 10 tecken så klasskompisar förstår."); return;
    }
    if (!Number.isFinite(s) || s < 5000 || s > 200000) {
      setErr("Månadslön måste vara mellan 5 000 och 200 000 kr."); return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await api("/v2/foretag/job-ads", {
        method: "POST",
        body: JSON.stringify({
          title: t,
          description: d,
          monthly_salary: s,
        }),
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
          Posta jobbannons
        </h2>
        <p style={{ color: "#aab", fontSize: 13 }}>
          Annonsen syns på <Link to="/v2/arbetsformedlingen" style={{ color: "#fbbf24" }}>Arbetsförmedlingen</Link>
          {" "}för alla i klassen, taggad <strong>klass-företag</strong>.
        </p>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Titel
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="t.ex. Junior säljare deltid" style={inputStyle} />
        </label>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Beskrivning (vad ska personen göra)
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} style={{ ...inputStyle, minHeight: 100 }} />
        </label>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Månadslön (kr)
          <input type="number" value={salary} onChange={(e) => setSalary(e.target.value)} style={inputStyle} />
        </label>
        {err && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={submit} disabled={submitting || !title || !description} style={btnPrimary}>
            {submitting ? "Postar…" : "Posta annonsen →"}
          </button>
          <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
        </div>
      </div>
    </div>
  );
}


// === Styles ===
const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5, fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe",
};

const inputStyle: React.CSSProperties = {
  width: "100%", marginTop: 6, padding: 10,
  background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 6, color: "#fff",
  fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13.5,
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24", border: "none", color: "#422006",
  padding: "9px 18px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent", border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.7)",
  padding: "9px 14px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 10,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const emptyStateStyle: React.CSSProperties = {
  padding: "32px 24px", textAlign: "center",
  background: "rgba(15,21,37,0.5)", border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 10, color: "rgba(255,255,255,0.7)",
  fontFamily: "Source Serif 4, Georgia, serif", marginTop: 16,
};

const errorBoxStyle: React.CSSProperties = {
  padding: 12, background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)", borderRadius: 6,
  color: "#fda594", fontFamily: "Source Serif 4, Georgia, serif",
};
