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

type OwnerEmployment = {
  id: number;
  employee_display: string;
  monthly_salary: number;
  started_at: string;
  ended_at: string | null;
  status: string;
  notice_days_left: number | null;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


type ClassmateEmploymentRow = {
  id: number;
  company_id: number;
  company_name: string;
  owner_student_id: number;
  employee_student_id: number;
  role: string;
  monthly_gross: number;
  status: "pending_offer" | "active" | "declined" | "terminated";
  offer_sent_on: string;
  accepted_on: string | null;
  last_day: string | null;
  termination_reason: string | null;
};

type ClassmateOption = {
  student_id: number;
  display_name: string;
  class_label: string | null;
};


export function BizJobAds() {
  const [ads, setAds] = useState<JobAd[]>([]);
  const [employments, setEmployments] = useState<OwnerEmployment[]>([]);
  const [classmateEmployments, setClassmateEmployments] = useState<
    ClassmateEmploymentRow[]
  >([]);
  const [showCreate, setShowCreate] = useState(false);
  const [showDirectHire, setShowDirectHire] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api<JobAd[]>("/v2/foretag/job-ads/mine")
      .then(setAds)
      .catch((e) => setError(String((e as Error).message || e)));
    api<OwnerEmployment[]>("/v2/foretag/job-ads/employments")
      .then(setEmployments)
      .catch(() => undefined);
    api<{ employments: ClassmateEmploymentRow[] }>(
      "/v2/employment/employments",
    )
      .then((d) => setClassmateEmployments(d.employments))
      .catch(() => undefined);
  }

  useEffect(() => { refresh(); }, []);

  async function terminateEmployment(empl: OwnerEmployment) {
    if (!confirm(
      `Säga upp ${empl.employee_display}?\n\n` +
      "Uppsägningstiden räknas enligt LAS § 11 baserat på " +
      "anställningstid. Lön betalas till slutdatumet.\n\n" +
      "Detta går inte att ångra."
    )) return;
    try {
      const res = await api<{ message: string }>(
        `/v2/foretag/job-ads/employments/${empl.id}/terminate`,
        { method: "POST" },
      );
      alert(res.message);
      refresh();
    } catch (e) {
      alert(`Fel: ${(e as Error).message || e}`);
    }
  }

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

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button onClick={() => setShowCreate(true)} style={btnPrimary}>
          + Posta ny jobbannons
        </button>
        <button onClick={() => setShowDirectHire(true)} style={btnGhost}>
          ★ Direktanställ klasskompis
        </button>
        {classmateEmployments.some((e) => e.status === "active") && (
          <PayrollButton onDone={refresh} />
        )}
      </div>

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

      {employments.length > 0 && (
        <>
          <div style={{ ...sectionEyeStyle, color: "#6ee7b7", marginTop: 32, marginBottom: 12 }}>
            ● MINA ANSTÄLLDA · {employments.filter((e) => e.status === "active").length} aktiva
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {employments.map((e) => {
              const isActive = e.status === "active";
              const isNotice = e.status === "notice_period";
              const bg = isActive
                ? "rgba(110,231,183,0.05)"
                : isNotice
                  ? "rgba(251,191,36,0.06)"
                  : "rgba(15,21,37,0.4)";
              const border = isActive
                ? "rgba(110,231,183,0.25)"
                : isNotice
                  ? "rgba(251,191,36,0.30)"
                  : "rgba(255,255,255,0.06)";
              return (
                <div key={e.id} style={{
                  padding: 14,
                  background: bg,
                  border: `1px solid ${border}`,
                  borderRadius: 8,
                  display: "flex", gap: 12, alignItems: "center",
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", fontWeight: 700 }}>
                      {e.employee_display}
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)", letterSpacing: 0.6, marginTop: 4 }}>
                      {SEK(e.monthly_salary)} kr/mån · sedan {e.started_at}
                      {isNotice && e.notice_days_left !== null && (
                        <span style={{ color: "#fbbf24", marginLeft: 8 }}>
                          · UPPSAGD · slutar om {e.notice_days_left} dgr
                        </span>
                      )}
                      {e.status === "terminated" && (
                        <span style={{ color: "rgba(255,255,255,0.45)", marginLeft: 8 }}>
                          · AVSLUTAD {e.ended_at}
                        </span>
                      )}
                    </div>
                  </div>
                  {isActive && (
                    <button
                      onClick={() => terminateEmployment(e)}
                      style={{
                        background: "transparent",
                        border: "1px solid rgba(220,76,43,0.40)",
                        color: "#fda594",
                        padding: "7px 14px",
                        borderRadius: 6,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 10, fontWeight: 700,
                        letterSpacing: 1.2, textTransform: "uppercase",
                        cursor: "pointer",
                      }}
                    >
                      Säg upp
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {classmateEmployments.length > 0 && (
        <>
          <div style={{ ...sectionEyeStyle, color: "#a78bfa", marginTop: 32, marginBottom: 12 }}>
            ● DIREKTANSTÄLLNINGAR · klasskompis-erbjudanden
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {classmateEmployments.map((e) => {
              const isPending = e.status === "pending_offer";
              const isActive = e.status === "active";
              const color = isActive ? "#6ee7b7"
                : isPending ? "#fbbf24"
                : e.status === "declined" ? "#fda594"
                : "rgba(255,255,255,0.5)";
              const bg = isActive ? "rgba(110,231,183,0.05)"
                : isPending ? "rgba(251,191,36,0.06)"
                : "rgba(15,21,37,0.4)";
              const border = `${color}55`;
              return (
                <div key={e.id} style={{
                  padding: 14,
                  background: bg,
                  border: `1px solid ${border}`,
                  borderRadius: 8,
                  display: "flex", gap: 12, alignItems: "center",
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", fontWeight: 700 }}>
                      Anställd #{e.employee_student_id} · {e.role}
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)", letterSpacing: 0.6, marginTop: 4 }}>
                      {SEK(e.monthly_gross)} kr brutto/mån · skickat {e.offer_sent_on.slice(0, 10)}
                      {e.accepted_on && (
                        <span style={{ marginLeft: 8 }}>· accepterad {e.accepted_on}</span>
                      )}
                      {e.last_day && (
                        <span style={{ marginLeft: 8 }}>· sista dag {e.last_day}</span>
                      )}
                    </div>
                  </div>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color, letterSpacing: 1, textTransform: "uppercase" }}>
                    {e.status}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {ads.length === 0 && employments.length === 0 && classmateEmployments.length === 0 && (
        <div style={emptyStateStyle}>
          Du har inga jobbannonser. Klicka "Posta ny jobbannons" eller "Direktanställ klasskompis" för att bygga teamet.
        </div>
      )}

      {showCreate && (
        <CreateAdModal onClose={(refreshed) => {
          setShowCreate(false);
          if (refreshed) refresh();
        }} />
      )}
      {showDirectHire && (
        <DirectHireModal onClose={(refreshed) => {
          setShowDirectHire(false);
          if (refreshed) refresh();
        }} />
      )}
    </BizActorShell>
  );
}


function PayrollButton({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function run() {
    if (
      !confirm(
        "Kör månadens lön för alla aktiva klasskompis-anställningar?\n\n"
          + "· Pengarna dras från företagets kassa (lön + arbetsgivaravgift 31,42 %)\n"
          + "· Lönespec landar i varje anställdas postlåda\n"
          + "· Nettolönen sätts in på deras lönekonto den 25:e\n\n"
          + "Idempotent — kan köras flera gånger samma månad utan dubbla utbetalningar.",
      )
    ) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await api<{
        n_paid: number;
        n_skipped: number;
        total_cost: number;
        year_month: string;
      }>("/v2/employment/payroll/run", { method: "POST", body: "{}" });
      setResult(
        `✓ Lön ${r.year_month}: ${r.n_paid} utbetalda`
          + (r.n_skipped > 0 ? ` (${r.n_skipped} skippade)` : "")
          + ` · totalkost ${SEK(r.total_cost)} kr`,
      );
      onDone();
    } catch (e) {
      setResult(`Fel: ${(e as Error).message || e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button onClick={run} disabled={busy} style={btnGhost}>
        {busy ? "Kör lön…" : "$ Kör månadens lön"}
      </button>
      {result && (
        <span style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: result.startsWith("Fel") ? "#fda594" : "#6ee7b7",
          alignSelf: "center",
          marginLeft: 8,
        }}>
          {result}
        </span>
      )}
    </>
  );
}


function DirectHireModal({
  onClose,
}: {
  onClose: (refreshed: boolean) => void;
}) {
  const [classmates, setClassmates] = useState<ClassmateOption[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [role, setRole] = useState("");
  const [salary, setSalary] = useState("28000");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ classmates: ClassmateOption[]; invites_enabled: boolean }>(
      "/v2/events/classmates",
    )
      .then((d) => {
        setClassmates(d.classmates);
        if (d.classmates.length > 0) setSelectedId(d.classmates[0].student_id);
      })
      .catch((e) => setErr(String((e as Error).message || e)));
  }, []);

  async function submit() {
    if (selectedId == null) { setErr("Välj en klasskompis."); return; }
    const r = role.trim();
    const s = parseInt(salary, 10);
    if (r.length < 2) { setErr("Beskriv rollen kort (min 2 tecken)."); return; }
    if (!Number.isFinite(s) || s < 15000 || s > 200000) {
      setErr("Månadslön måste vara mellan 15 000 och 200 000 kr."); return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await api("/v2/employment/hire-offer", {
        method: "POST",
        body: JSON.stringify({
          classmate_student_id: selectedId,
          role: r,
          monthly_gross: s,
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
        background: "#0f1525", border: "1px solid rgba(167,139,250,0.4)",
        borderRadius: 12, padding: 24, maxWidth: 600, width: "100%",
      }}>
        <h2 style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", marginTop: 0 }}>
          Direktanställ klasskompis
        </h2>
        <p style={{ color: "#aab", fontSize: 13 }}>
          Skicka ett anställningserbjudande direkt till en klasskompis. De får
          ett brev i sin postlåda och kan tacka ja eller nej. Om de tackar ja
          säger de upp sin gamla anställning med 30 dgr LAS-varsel.
        </p>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Klasskompis
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(parseInt(e.target.value, 10))}
            style={inputStyle}
          >
            {classmates.length === 0 && (
              <option value="">Inga klasskompisar tillgängliga</option>
            )}
            {classmates.map((c) => (
              <option key={c.student_id} value={c.student_id}>
                {c.display_name}
                {c.class_label ? ` · ${c.class_label}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Roll (t.ex. "Säljare", "Konsult", "Assistent")
          <input value={role} onChange={(e) => setRole(e.target.value)} style={inputStyle} />
        </label>
        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Månadslön brutto (kr)
          <input type="number" value={salary} onChange={(e) => setSalary(e.target.value)} style={inputStyle} />
        </label>
        {err && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={submit} disabled={submitting || selectedId == null} style={btnPrimary}>
            {submitting ? "Skickar…" : "Skicka erbjudande →"}
          </button>
          <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
        </div>
      </div>
    </div>
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
