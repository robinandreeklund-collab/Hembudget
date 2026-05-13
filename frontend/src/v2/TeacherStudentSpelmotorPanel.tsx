/**
 * Spelmotor-panel på lärar-elev-detalj — synliggör all data Sprint 1-6
 * skapar för en elev.
 *
 * Visar:
 *  - Tick-historik (vilka spelmånader är genomförda)
 *  - Pentagon-historik (senaste 10 WellbeingEvent med requested vs applied)
 *  - Snabbspola-knappar (advance-month)
 *  - Aktiva job-applications (Sprint 6)
 *
 * Allt-i-ett-vy så läraren kan se exakt vad spelmotorn gjort utan
 * att klicka in i varje aktör.
 */
import { useEffect, useState } from "react";
import { v2Api } from "./api";
import { getToken } from "@/api/client";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("sv-SE", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

type TickRun = {
  id: number;
  year_month: string;
  status: string;
  seed_used: number | null;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
};

type PentagonEvent = {
  id: number;
  occurred_at: string;
  occurred_at_game: string | null;  // spel-tid ISO
  occurred_at_label: string | null;  // "14 jan 09:30"
  axis: string;
  requested_delta: number;
  applied_delta: number;
  new_value: number;
  reason_kind: string;
  explanation: string | null;
  year_month: string | null;
};

const AXIS_LABEL: Record<string, string> = {
  economy: "Ekonomi",
  safety: "Trygghet",
  health: "Hälsa",
  social: "Social",
  leisure: "Fritid",
};

const REASON_LABEL: Record<string, string> = {
  drift: "Drift",
  event: "Händelse",
  decision: "Beslut",
  init: "Start",
  goal_achieved: "Mål nått",
};


export function TeacherStudentSpelmotorPanel({ studentId }: { studentId: number }) {
  const [ticks, setTicks] = useState<TickRun[]>([]);
  const [pentagon, setPentagon] = useState<PentagonEvent[]>([]);
  const [advanceYm, setAdvanceYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [advanceSeed, setAdvanceSeed] = useState<number>(studentId * 31 + 7);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // Bug #7-utbyggnad · företagsläge per elev
  const [bizEnabled, setBizEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    // KRITISKT: tidigare körde detta useEffect ett POST /toggle med
    // `enabled: false` som "dry-read" — vilket faktiskt skrev över
    // flaggan till FALSE varje gång läraren laddade dashboarden. Det
    // var DÄRFÖR business_mode_enabled "försvann" vid varje reload.
    // Nu läser vi bara student-detalj-endpointen som redan returnerar
    // business_mode_enabled i sin payload.
    fetch(`/v2/teacher/students/${studentId}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    }).then(r => r.json()).then((d) => {
      if (typeof d?.business_mode_enabled === "boolean") {
        setBizEnabled(d.business_mode_enabled);
      } else {
        setBizEnabled(false);
      }
    }).catch(() => setBizEnabled(false));
  }, [studentId]);

  const toggleBiz = async () => {
    if (bizEnabled === null) return;
    const next = !bizEnabled;
    try {
      await fetch(`/v2/teacher/foretag/toggle/${studentId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ enabled: next }),
      });
      setBizEnabled(next);
      setMsg(next
        ? "Företagsläget aktiverat. Eleven kan nu starta enskild firma eller AB."
        : "Företagsläget avstängt. Eleven återgår till bara privatekonomi.");
    } catch (e) {
      setMsg(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  const refresh = async () => {
    try {
      const [t, p] = await Promise.all([
        fetchTicks(studentId),
        fetchPentagon(studentId),
      ]);
      setTicks(t);
      setPentagon(p);
    } catch (e) {
      setMsg(`Fel vid hämtning: ${String((e as Error).message || e)}`);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  const handleAdvance = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await advanceMonth(studentId, advanceYm, advanceSeed);
      if (res.skipped) {
        setMsg(`Månad ${advanceYm} var redan tickad — ingen ny data skapad.`);
      } else {
        setMsg(
          `Tick klar för ${advanceYm}. ` +
            `Lön ${res.summary?.salary?.total_net_credited ?? 0} kr, ` +
            `${res.summary?.fixed?.items_created ?? 0} fakturor, ` +
            `${res.summary?.variable?.transactions_created ?? 0} txns, ` +
            `${res.summary?.events?.triggered ?? 0} oväntade händelser, ` +
            `${res.summary?.health?.episodes ?? 0} sjuk/VAB.`,
        );
      }
      await refresh();
    } catch (e) {
      setMsg(`Fel: ${String((e as Error).message || e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      style={{
        marginTop: 32,
        padding: 20,
        borderRadius: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <header style={{ marginBottom: 18 }}>
        <span
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 1.4,
            color: "var(--warm)",
          }}
        >
          SPELMOTOR · sim-historik
        </span>
        <h2 style={{ fontSize: "1.3rem", margin: "8px 0 0", color: "white" }}>
          Tick-historik · Pentagon-händelser · Snabbspola
        </h2>
      </header>

      {/* Bug #7-utbyggnad · Företagsläge-toggle */}
      <div
        style={{
          background: "rgba(99,102,241,0.06)",
          border: "1px solid rgba(99,102,241,0.25)",
          padding: 14,
          borderRadius: 10,
          marginBottom: 14,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <div style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            color: "#818cf8",
            letterSpacing: 1.4,
            fontWeight: 700,
          }}>
            FÖRETAGSLÄGE
          </div>
          <div style={{ color: "white", marginTop: 4 }}>
            {bizEnabled === null
              ? "Hämtar status…"
              : bizEnabled
                ? "✓ Aktiverat — eleven kan starta enskild firma eller AB"
                : "Av — eleven har bara privatekonomi"}
          </div>
        </div>
        <button
          onClick={toggleBiz}
          disabled={bizEnabled === null}
          style={{
            padding: "8px 18px",
            background: bizEnabled
              ? "rgba(220,76,43,0.15)"
              : "rgba(129,140,248,0.18)",
            border: `1px solid ${bizEnabled
              ? "rgba(220,76,43,0.4)"
              : "rgba(129,140,248,0.4)"}`,
            color: bizEnabled ? "#fda594" : "#c7d2fe",
            borderRadius: 6,
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "0.85rem",
          }}
        >
          {bizEnabled === null ? "..." : bizEnabled ? "Stäng av" : "Aktivera"}
        </button>
      </div>

      {/* Snabbspola */}
      <div
        style={{
          background: "rgba(0,102,204,0.05)",
          border: "1px solid rgba(0,102,204,0.2)",
          padding: 14,
          borderRadius: 10,
          marginBottom: 18,
        }}
      >
        <strong style={{ color: "white" }}>Snabbspola en spelmånad</strong>
        <div
          style={{
            display: "flex",
            gap: 10,
            marginTop: 10,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <label style={labelStyle()}>
            Spelmånad:&nbsp;
            <input
              type="month"
              value={advanceYm}
              onChange={(e) => setAdvanceYm(e.target.value)}
              style={inputStyle()}
            />
          </label>
          <label style={labelStyle()}>
            Seed:&nbsp;
            <input
              type="number"
              value={advanceSeed}
              onChange={(e) => setAdvanceSeed(parseInt(e.target.value) || 0)}
              style={{ ...inputStyle(), width: 110 }}
            />
          </label>
          <button
            onClick={handleAdvance}
            disabled={busy}
            style={{
              padding: "8px 18px",
              background: "var(--warm, #fbbf24)",
              border: "none",
              borderRadius: 6,
              cursor: busy ? "wait" : "pointer",
              fontWeight: 600,
            }}
          >
            {busy ? "Behandlar…" : "Tick månad →"}
          </button>
        </div>
        {msg && (
          <div
            style={{
              marginTop: 10,
              padding: 10,
              background: "rgba(255,255,255,0.04)",
              borderRadius: 6,
              color: "rgba(255,255,255,0.8)",
              fontSize: "0.9rem",
            }}
          >
            {msg}
          </div>
        )}
      </div>

      {/* === Reseed-elev-data · för stuck failed runs === */}
      <ReseedButton
        studentId={studentId}
        onMsg={setMsg}
        onDone={refresh}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 18,
        }}
      >
        {/* Tick-historik */}
        <div>
          <h3 style={{ color: "white", fontSize: "1rem", marginBottom: 8 }}>
            Tick-historik ({ticks.length})
          </h3>
          {ticks.length === 0 && (
            <div style={{ color: "rgba(255,255,255,0.5)" }}>
              Inga tickar genomförda än.
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {ticks.slice(0, 10).map((t) => (
              <div
                key={t.id}
                style={{
                  padding: 10,
                  borderRadius: 6,
                  background: "rgba(255,255,255,0.03)",
                  fontSize: "0.85rem",
                }}
              >
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}>
                  <div>
                    <strong style={{ color: "white" }}>{t.year_month}</strong>
                    {t.seed_used !== null && (
                      <span style={{ color: "rgba(255,255,255,0.4)", marginLeft: 8 }}>
                        seed {t.seed_used}
                      </span>
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 600,
                      padding: "2px 8px",
                      borderRadius: 10,
                      background:
                        t.status === "completed"
                          ? "rgba(110,231,183,0.2)"
                          : t.status === "failed"
                            ? "rgba(220,76,43,0.2)"
                            : "rgba(251,191,36,0.2)",
                      color:
                        t.status === "completed"
                          ? "#6ee7b7"
                          : t.status === "failed"
                            ? "#fda594"
                            : "var(--warm)",
                    }}
                  >
                    {t.status}
                  </span>
                </div>
                {/* Visa error_message vid failed så vi ser ROTORSAKEN */}
                {t.status === "failed" && t.error_message && (
                  <div
                    style={{
                      marginTop: 8,
                      padding: 8,
                      background: "rgba(220,76,43,0.08)",
                      border: "1px solid rgba(220,76,43,0.3)",
                      borderRadius: 4,
                      color: "#fda594",
                      fontSize: "0.75rem",
                      fontFamily: "JetBrains Mono, ui-monospace, monospace",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      lineHeight: 1.45,
                    }}
                  >
                    {t.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Pentagon-historik */}
        <div>
          <h3 style={{ color: "white", fontSize: "1rem", marginBottom: 8 }}>
            Pentagon-händelser (senaste 30 d)
          </h3>
          {pentagon.length === 0 && (
            <div style={{ color: "rgba(255,255,255,0.5)" }}>
              Inga pentagon-deltas loggade än.
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {pentagon.slice(0, 10).map((p) => {
              const clamped = p.requested_delta !== p.applied_delta;
              return (
                <div
                  key={p.id}
                  style={{
                    padding: 8,
                    borderRadius: 6,
                    background: "rgba(255,255,255,0.03)",
                    fontSize: "0.85rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong style={{ color: "white" }}>
                      {AXIS_LABEL[p.axis] || p.axis}
                    </strong>
                    <span
                      style={{
                        color:
                          p.applied_delta > 0
                            ? "#6ee7b7"
                            : p.applied_delta < 0
                              ? "#fda594"
                              : "rgba(255,255,255,0.4)",
                        fontWeight: 600,
                      }}
                    >
                      {p.applied_delta > 0 ? "+" : ""}{p.applied_delta}
                      {clamped && (
                        <span
                          style={{
                            color: "var(--warm)",
                            marginLeft: 4,
                            fontSize: "0.75rem",
                          }}
                          title={`Önskat ${p.requested_delta}, klampat av tröghet`}
                        >
                          (clamp)
                        </span>
                      )}
                      <span style={{ marginLeft: 6, color: "rgba(255,255,255,0.5)" }}>
                        →{p.new_value}
                      </span>
                    </span>
                  </div>
                  <div
                    style={{
                      color: "rgba(255,255,255,0.5)",
                      fontSize: "0.75rem",
                      marginTop: 2,
                    }}
                  >
                    {REASON_LABEL[p.reason_kind] || p.reason_kind}
                    {p.explanation && ` · ${p.explanation}`}
                    <span style={{ marginLeft: 6 }}>
                      {p.occurred_at_label || SHORT_DATE(p.occurred_at)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}


// === API-helpers ===

async function fetchTicks(studentId: number): Promise<TickRun[]> {
  const r = await fetch(`/v2/teacher/students/${studentId}/tick-history`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!r.ok) throw new Error(`tick-history HTTP ${r.status}`);
  return r.json();
}

async function fetchPentagon(studentId: number): Promise<PentagonEvent[]> {
  const r = await fetch(
    `/v2/teacher/students/${studentId}/pentagon-history?days=30`,
    { headers: { Authorization: `Bearer ${getToken()}` } },
  );
  if (!r.ok) throw new Error(`pentagon-history HTTP ${r.status}`);
  return r.json();
}

async function advanceMonth(
  studentId: number, ym: string, seed: number,
): Promise<{ skipped: boolean; summary?: any }> {
  // Använder den existerande game_engine-routen via v2Api är möjligt, men
  // den finns inte i v2Api än — använd raw fetch.
  const r = await fetch(`/v2/teacher/students/${studentId}/advance-month`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ year_month: ym, seed }),
  });
  if (!r.ok) throw new Error(`advance HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

// getToken importeras från @/api/client (lokal version som läste
// sessionStorage borttagen — token migrerades till localStorage och
// den lokala kopian läste fel källa = "Missing bearer token"-fel).


/** Knapp · trigga reseed för stuck failed runs.
 *
 * Reseed kallar samma flöde som auto-recovery vid student-detail.
 * Idempotent — om eleven redan har data svarar vi att inget gjordes. */
function ReseedButton({
  studentId, onMsg, onDone,
}: {
  studentId: number;
  onMsg: (s: string) => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const handle = async () => {
    setBusy(true);
    onMsg("Kör reseed…");
    try {
      const r = await fetch(
        `/v2/teacher/students/${studentId}/reseed-initial-data`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
        },
      );
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      }
      const data = await r.json();
      onMsg(`✓ ${data.message}`);
      await onDone();
    } catch (e) {
      onMsg(`Fel vid reseed: ${String((e as Error).message || e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        background: "rgba(220,76,43,0.05)",
        border: "1px solid rgba(220,76,43,0.2)",
        padding: 14,
        borderRadius: 10,
        marginBottom: 18,
      }}
    >
      <strong style={{ color: "white" }}>Reseed elev-data</strong>
      <div
        style={{
          color: "rgba(255,255,255,0.6)",
          fontSize: "0.85rem",
          margin: "4px 0 10px",
        }}
      >
        Om eleven saknar postlådan, banken eller pentagon-data — tryck
        här för att köra om initial-seeden. Säkert · idempotent (gör
        inget om eleven redan har data).
      </div>
      <button
        onClick={handle}
        disabled={busy}
        style={{
          padding: "8px 18px",
          background: "rgba(220,76,43,0.85)",
          border: "none",
          color: "#fff",
          borderRadius: 6,
          cursor: busy ? "wait" : "pointer",
          fontWeight: 600,
        }}
      >
        {busy ? "Kör reseed…" : "Reseed elev-data →"}
      </button>
    </div>
  );
}

function labelStyle(): React.CSSProperties {
  return {
    color: "rgba(255,255,255,0.7)",
    fontSize: "0.85rem",
    display: "flex",
    alignItems: "center",
  };
}

function inputStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    color: "white",
    padding: "6px 8px",
    borderRadius: 4,
    fontFamily: "inherit",
  };
}

// Suppress unused-import warning
void v2Api;
