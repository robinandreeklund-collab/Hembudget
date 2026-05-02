/**
 * Företagsläget · spelmotor-vyer (deb/README.md fas 2-3).
 *
 * BizOfferter      · /v2/foretag/offerter (offertförfrågningar + ge offert)
 * BizJobb          · /v2/foretag/jobb (pågående + leverera)
 * BizMarknad       · /v2/foretag/marknad (marknadsföringskampanjer)
 * BizBeslut        · /v2/foretag/beslut (anställa/friskvård/leasing)
 * BizLeverantorer  · /v2/foretag/leverantorer (inkommande fakturor)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { V2Banner } from "../V2Banner";
import {
  bizEngineApi,
  type Decision,
  type Job,
  type MarketingCampaign,
  type Opportunity,
  type Quote,
  type SupplierInvoice,
} from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


function BizShell({ title, eye, children }: {
  title: string; eye: string; children: React.ReactNode;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #0a0e1a 0%, #0f1525 100%)",
      }}
    >
      <V2Banner status={{ role: "student", is_super_admin: false }} />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "20px 28px 40px" }}>
        <Link
          to="/v2/hub"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            display: "inline-block",
            marginBottom: 18,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: "0.8rem",
            letterSpacing: 1.1,
            textTransform: "uppercase",
          }}
        >
          ← Bolag · översikt
        </Link>
        <header style={{ marginBottom: 24 }}>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "#818cf8",
              letterSpacing: 1.4,
              fontWeight: 700,
            }}
          >
            {eye}
          </div>
          <h1 style={{ color: "white", fontSize: "1.8rem", margin: "6px 0 0" }}>
            {title}
          </h1>
        </header>
        {children}
      </div>
    </div>
  );
}


// === BIZ OFFERTER ===

export function BizOfferter() {
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [editing, setEditing] = useState<Opportunity | null>(null);

  function refresh() {
    bizEngineApi.listOpportunities(filter || undefined)
      .then(setOpps)
      .catch((e) => setErr(String((e as Error).message || e)));
  }

  useEffect(() => { refresh(); /* eslint-disable-line */ }, [filter]);

  return (
    <BizShell title="Offertförfrågningar" eye="Spelmotor · 01 / Pipeline">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[
          ["", "Alla"], ["open", "Öppna"], ["quoted", "Offererade"],
          ["won", "Vunna"], ["lost", "Förlorade"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid rgba(99,102,241,0.3)",
              background: filter === v
                ? "rgba(99,102,241,0.25)" : "transparent",
              color: "#c7d2fe",
              cursor: "pointer",
              fontSize: "0.85rem",
            }}
          >{l}</button>
        ))}
      </div>

      {opps.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga offertförfrågningar än. Tryck på <strong>Stega vecka</strong> i
          biz-hubben för att simulera fram nya kunder.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {opps.map(o => (
            <OpportunityCard
              key={o.id}
              opp={o}
              onClick={() => setEditing(o)}
            />
          ))}
        </div>
      )}

      {editing && (
        <QuoteModal
          opp={editing}
          onClose={(refreshed) => {
            setEditing(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </BizShell>
  );
}


function OpportunityCard({
  opp, onClick,
}: { opp: Opportunity; onClick: () => void }) {
  const SEGMENT_LABEL: Record<string, string> = {
    privat: "Privat",
    foretag: "Företag",
    kommun: "Kommun",
  };
  const STATUS_COLOR: Record<string, string> = {
    open: "#fbbf24",
    quoted: "#818cf8",
    won: "#6ee7b7",
    lost: "#fda594",
    expired: "#aab",
  };
  const STATUS_LABEL: Record<string, string> = {
    open: "Öppen",
    quoted: "Offererad",
    won: "Vunnen",
    lost: "Förlorad",
    expired: "Förfallen",
  };
  return (
    <div
      onClick={onClick}
      style={{
        background: "rgba(15,21,37,0.6)",
        border: "1px solid rgba(99,102,241,0.18)",
        borderRadius: 10,
        padding: 16,
        cursor: opp.status === "open" ? "pointer" : "default",
        opacity: opp.status === "open" ? 1 : 0.85,
      }}
    >
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "flex-start", marginBottom: 8,
      }}>
        <div>
          <div style={{
            color: STATUS_COLOR[opp.status] || "white",
            fontSize: "0.7rem",
            fontFamily: "JetBrains Mono, monospace",
            letterSpacing: 1.2,
            textTransform: "uppercase",
          }}>
            {STATUS_LABEL[opp.status] || opp.status} · v{opp.week_no}
          </div>
          <h3 style={{ color: "white", margin: "4px 0 0" }}>{opp.title}</h3>
          <div style={{ color: "#aab", fontSize: "0.85rem" }}>
            {opp.customer_name} · {SEGMENT_LABEL[opp.customer_segment]}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: "white", fontSize: "1.2rem", fontWeight: 700 }}>
            {SEK(opp.market_price)} kr
          </div>
          <div style={{ color: "#aab", fontSize: "0.75rem" }}>
            riktpris · ~{opp.expected_delivery_days} dgr
          </div>
        </div>
      </div>
      <p style={{ color: "rgba(255,255,255,0.7)", margin: 0, fontSize: "0.9rem" }}>
        {opp.description}
      </p>
      {opp.status === "open" && (
        <div style={{
          marginTop: 10, color: "#6ee7b7",
          fontSize: "0.8rem", fontWeight: 600,
        }}>
          → Klicka för att lämna offert
        </div>
      )}
    </div>
  );
}


function QuoteModal({
  opp, onClose,
}: { opp: Opportunity; onClose: (refreshed: boolean) => void }) {
  const [price, setPrice] = useState(opp.market_price.toString());
  const [days, setDays] = useState(opp.expected_delivery_days.toString());
  const [pitch, setPitch] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<Quote | null>(null);

  async function submit() {
    setErr(null);
    setSubmitting(true);
    try {
      const q = await bizEngineApi.submitQuote(opp.id, {
        offered_price: parseInt(price, 10),
        offered_delivery_days: parseInt(days, 10),
        pitch_text: pitch.trim() || undefined,
      });
      setResult(q);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(result !== null)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 540, width: "100%",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>
          Lämna offert · {opp.title}
        </h2>
        <p style={{ color: "#aab", fontSize: "0.85rem" }}>
          Riktpris {SEK(opp.market_price)} kr · förväntad leverans{" "}
          {opp.expected_delivery_days} dagar
        </p>

        {result === null ? (
          <>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Ditt pris (kr exkl moms)
              <input
                type="number"
                value={price}
                onChange={e => setPrice(e.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Leveranstid (dagar)
              <input
                type="number"
                value={days}
                onChange={e => setDays(e.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Din pitch (frivilligt — höjer dina chanser)
              <textarea
                value={pitch}
                onChange={e => setPitch(e.target.value)}
                rows={4}
                placeholder="Vad gör just er bra? Varför ska kunden välja er?"
                style={{ ...inputStyle, fontFamily: "inherit" }}
              />
            </label>
            {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button onClick={submit} disabled={submitting} style={btnPrimary}>
                {submitting ? "Skickar…" : "Skicka offert"}
              </button>
              <button onClick={() => onClose(false)} style={btnGhost}>
                Avbryt
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{
              padding: 14, borderRadius: 8,
              background: "rgba(34,197,94,0.1)",
              border: "1px solid rgba(34,197,94,0.3)",
              marginTop: 16,
            }}>
              <h3 style={{ color: "#6ee7b7", margin: "0 0 8px" }}>
                Offerten är skickad!
              </h3>
              <p style={{ color: "white", margin: 0, fontSize: "0.9rem" }}>
                Pris: <strong>{SEK(result.offered_price)} kr</strong> ·
                Leverans: <strong>{result.offered_delivery_days} dagar</strong>
              </p>
              {result.pitch_quality !== null && (
                <p style={{ color: "#aab", margin: "8px 0 0", fontSize: "0.85rem" }}>
                  AI-bedömd pitch-kvalitet:{" "}
                  <strong style={{ color: "white" }}>
                    {(result.pitch_quality * 100).toFixed(0)}%
                  </strong>
                </p>
              )}
              <p style={{
                color: "rgba(255,255,255,0.8)",
                margin: "12px 0 0", fontSize: "0.85rem",
              }}>
                Kunden svarar nästa vecka. Tryck på "Stega vecka" i biz-hubben
                för att få deras beslut.
              </p>
            </div>
            <button
              onClick={() => onClose(true)}
              style={{ ...btnPrimary, marginTop: 16 }}
            >
              Klar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


// === BIZ JOBB ===

export function BizJobb() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [delivering, setDelivering] = useState<Job | null>(null);

  function refresh() {
    bizEngineApi.listJobs(filter || undefined)
      .then(setJobs)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); /* eslint-disable-line */ }, [filter]);

  const STATUS_LABEL: Record<string, string> = {
    in_progress: "Pågår",
    delivered: "Levererat",
    invoiced: "Fakturerat",
    paid: "Betalt",
    disputed: "Tvist",
  };
  const STATUS_COLOR: Record<string, string> = {
    in_progress: "#fbbf24",
    delivered: "#818cf8",
    invoiced: "#a78bfa",
    paid: "#6ee7b7",
    disputed: "#fda594",
  };

  return (
    <BizShell title="Pågående jobb" eye="Spelmotor · 02 / Leveranser">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[
          ["", "Alla"], ["in_progress", "Pågår"], ["delivered", "Levererade"],
          ["paid", "Betalda"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            style={{
              padding: "6px 12px", borderRadius: 6,
              border: "1px solid rgba(99,102,241,0.3)",
              background: filter === v
                ? "rgba(99,102,241,0.25)" : "transparent",
              color: "#c7d2fe", cursor: "pointer", fontSize: "0.85rem",
            }}
          >{l}</button>
        ))}
      </div>

      {jobs.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga jobb än. Vinn en offert först!
        </p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr style={{ color: "#aab", textAlign: "left" }}>
              <th style={{ padding: "8px 4px" }}>Jobb / Kund</th>
              <th style={{ padding: "8px 4px", textAlign: "right" }}>Pris</th>
              <th style={{ padding: "8px 4px" }}>Status</th>
              <th style={{ padding: "8px 4px" }}>Kvalitet</th>
              <th style={{ padding: "8px 4px" }}></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(j => (
              <tr key={j.id} style={{ borderBottom: "1px solid rgba(99,102,241,0.08)" }}>
                <td style={{ padding: "10px 4px" }}>
                  <div style={{ color: "white", fontWeight: 600 }}>{j.title}</div>
                  <div style={{ color: "#aab", fontSize: "0.8rem" }}>{j.customer_name}</div>
                </td>
                <td style={{ padding: "10px 4px", textAlign: "right", color: "white" }}>
                  {SEK(j.agreed_price)} kr
                </td>
                <td style={{
                  padding: "10px 4px",
                  color: STATUS_COLOR[j.status] || "white",
                }}>
                  {STATUS_LABEL[j.status] || j.status}
                </td>
                <td style={{ padding: "10px 4px", color: "white" }}>
                  {j.quality_score !== null ? `${j.quality_score}/100` : "—"}
                </td>
                <td style={{ padding: "10px 4px", textAlign: "right" }}>
                  {j.status === "in_progress" && (
                    <button
                      onClick={() => setDelivering(j)}
                      style={btnPrimary}
                    >
                      Leverera
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {delivering && (
        <DeliverModal
          job={delivering}
          onClose={(refreshed) => {
            setDelivering(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </BizShell>
  );
}


function DeliverModal({
  job, onClose,
}: { job: Job; onClose: (refreshed: boolean) => void }) {
  const [quality, setQuality] = useState(70);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<{ invoice_number: string | null } | null>(null);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      const r = await bizEngineApi.deliverJob(job.id, {
        quality_score: quality,
        create_invoice: true,
      });
      setDone({ invoice_number: r.invoice_number });
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(done !== null)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 480, width: "100%",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>
          Leverera · {job.title}
        </h2>
        <p style={{ color: "#aab", fontSize: "0.85rem" }}>
          {job.customer_name} · {SEK(job.agreed_price)} kr
        </p>

        {done === null ? (
          <>
            <label style={{ color: "white", display: "block", marginTop: 16 }}>
              Kvalitet på leverans · {quality}/100
              <input
                type="range" min="0" max="100" step="5"
                value={quality}
                onChange={e => setQuality(parseInt(e.target.value, 10))}
                style={{ width: "100%", marginTop: 8 }}
              />
              <div style={{
                display: "flex", justifyContent: "space-between",
                fontSize: "0.75rem", color: "#aab",
              }}>
                <span>Slarvigt</span>
                <span>OK</span>
                <span>Excellent</span>
              </div>
            </label>
            <p style={{
              color: "rgba(255,255,255,0.7)", fontSize: "0.85rem",
              marginTop: 16,
            }}>
              Hög kvalitet → rykte upp + chans till repetitionsorder.
              Låg kvalitet → klagomål + ryktesfall.
            </p>
            {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button onClick={submit} disabled={submitting} style={btnPrimary}>
                {submitting ? "Levererar…" : "Leverera + skapa faktura"}
              </button>
              <button onClick={() => onClose(false)} style={btnGhost}>
                Avbryt
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{
              padding: 14, borderRadius: 8,
              background: "rgba(34,197,94,0.1)",
              border: "1px solid rgba(34,197,94,0.3)",
              marginTop: 16,
            }}>
              <h3 style={{ color: "#6ee7b7", margin: "0 0 8px" }}>
                Levererat!
              </h3>
              <p style={{ color: "white", margin: 0, fontSize: "0.9rem" }}>
                Faktura <strong>{done.invoice_number}</strong> har skickats.
              </p>
              <p style={{
                color: "rgba(255,255,255,0.7)",
                margin: "8px 0 0", fontSize: "0.85rem",
              }}>
                Kunden betalar inom 30 dagar (de flesta).
              </p>
            </div>
            <button
              onClick={() => onClose(true)}
              style={{ ...btnPrimary, marginTop: 16 }}
            >
              Klar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


// === BIZ MARKNAD ===

const MARKETING_KINDS = [
  { value: "social", label: "Sociala medier", base: 1500 },
  { value: "flygblad", label: "Flygblad", base: 2500 },
  { value: "google", label: "Google-annonser", base: 4000 },
  { value: "sponsring", label: "Sponsring", base: 6000 },
  { value: "event", label: "Event/mässa", base: 8000 },
];

export function BizMarknad() {
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  function refresh() {
    bizEngineApi.listMarketing()
      .then(setCampaigns)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  return (
    <BizShell title="Marknadsföring" eye="Spelmotor · 03 / Sälj">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <button onClick={() => setShowAdd(true)} style={{ ...btnPrimary, marginBottom: 16 }}>
        + Skapa kampanj
      </button>

      {campaigns.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga kampanjer än. Marknadsföring höjer pipeline-genereringen.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {campaigns.map(c => (
            <div
              key={c.id}
              style={{
                background: "rgba(15,21,37,0.6)",
                border: "1px solid rgba(99,102,241,0.18)",
                borderRadius: 10, padding: 16,
                opacity: c.active ? 1 : 0.6,
              }}
            >
              <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}>
                <div>
                  <div style={{
                    fontSize: "0.7rem",
                    fontFamily: "JetBrains Mono, monospace",
                    color: "#818cf8", letterSpacing: 1.2,
                    textTransform: "uppercase",
                  }}>
                    {MARKETING_KINDS.find(k => k.value === c.kind)?.label || c.kind}
                    {c.active && " · AKTIV"}
                  </div>
                  <h3 style={{ color: "white", margin: "4px 0 0" }}>
                    {c.title}
                  </h3>
                  <div style={{ color: "#aab", fontSize: "0.85rem" }}>
                    {c.started_on} → {c.ends_on} · {SEK(c.cost)} kr
                  </div>
                </div>
                {c.ai_quality_factor !== null && (
                  <div style={{
                    textAlign: "right",
                    fontSize: "0.85rem",
                  }}>
                    <div style={{ color: "#818cf8" }}>AI-kvalitet</div>
                    <div style={{
                      color: c.ai_quality_factor >= 1.2 ? "#6ee7b7"
                        : c.ai_quality_factor <= 0.8 ? "#fda594" : "white",
                      fontWeight: 700, fontSize: "1.1rem",
                    }}>
                      ×{c.ai_quality_factor.toFixed(2)}
                    </div>
                  </div>
                )}
              </div>
              {c.copy_text && (
                <p style={{
                  color: "rgba(255,255,255,0.7)",
                  fontSize: "0.85rem", margin: "8px 0 0",
                  fontStyle: "italic",
                }}>
                  "{c.copy_text}"
                </p>
              )}
              {c.ai_feedback && (
                <p style={{
                  color: "#a78bfa", fontSize: "0.8rem", margin: "8px 0 0",
                }}>
                  AI: {c.ai_feedback}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <MarketingModal onClose={(r) => {
          setShowAdd(false);
          if (r) refresh();
        }} />
      )}
    </BizShell>
  );
}


function MarketingModal({ onClose }: { onClose: (refreshed: boolean) => void }) {
  const [kind, setKind] = useState("social");
  const [title, setTitle] = useState("");
  const [copyText, setCopyText] = useState("");
  const [cost, setCost] = useState("1500");
  const [duration, setDuration] = useState("4");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const k = MARKETING_KINDS.find(x => x.value === kind);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      await bizEngineApi.createMarketing({
        kind,
        title,
        copy_text: copyText.trim() || undefined,
        cost: parseInt(cost, 10),
        duration_weeks: parseInt(duration, 10),
      });
      onClose(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(false)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 540, width: "100%",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>Skapa kampanj</h2>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Typ
          <select
            value={kind}
            onChange={e => {
              setKind(e.target.value);
              const k2 = MARKETING_KINDS.find(x => x.value === e.target.value);
              if (k2) setCost(k2.base.toString());
            }}
            style={inputStyle}
          >
            {MARKETING_KINDS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Rubrik
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="t.ex. Sommarkampanj 2026"
            style={inputStyle}
          />
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Copy / kampanjtext (AI-bedöms)
          <textarea
            value={copyText}
            onChange={e => setCopyText(e.target.value)}
            rows={4}
            placeholder="Skriv din reklamtext här. Konkret målgrupp + tydlig CTA = högre kvalitet."
            style={{ ...inputStyle, fontFamily: "inherit" }}
          />
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Budget (kr)
          <input
            type="number"
            value={cost}
            onChange={e => setCost(e.target.value)}
            style={inputStyle}
          />
          <div style={{ color: "#aab", fontSize: "0.75rem" }}>
            Förslag för {k?.label}: {SEK(k?.base || 1500)} kr
          </div>
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Varaktighet (veckor)
          <input
            type="number" min="1" max="12"
            value={duration}
            onChange={e => setDuration(e.target.value)}
            style={inputStyle}
          />
        </label>

        {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            onClick={submit}
            disabled={submitting || !title.trim()}
            style={btnPrimary}
          >
            {submitting ? "Skapar…" : "Starta kampanj"}
          </button>
          <button onClick={() => onClose(false)} style={btnGhost}>
            Avbryt
          </button>
        </div>
      </div>
    </div>
  );
}


// === BIZ BESLUT ===

const DECISION_TEMPLATES = [
  {
    kind: "hire_part_time",
    label: "Anställ deltid",
    monthly: 18000, oneTime: 0, capacity: 1, rep: 0,
    desc: "+1 leveranskapacitet, 18 000 kr/mån i lönekostnad.",
  },
  {
    kind: "wellness",
    label: "Friskvårdsbidrag",
    monthly: 500, oneTime: 0, capacity: 0, rep: 3,
    desc: "+3 rykte (medarbetarnöjdhet), 500 kr/mån.",
  },
  {
    kind: "car_lease",
    label: "Leasa bil",
    monthly: 4500, oneTime: 5000, capacity: 0, rep: 0,
    desc: "Låser upp körnings-jobb. 4 500 kr/mån + 5 000 kr engångs.",
  },
  {
    kind: "insurance",
    label: "Företagsförsäkring",
    monthly: 800, oneTime: 0, capacity: 0, rep: 0,
    desc: "Skyddar mot slumpevent (-90 % skada). 800 kr/mån.",
    insurance_kind: "egendom",
  },
  {
    kind: "new_office",
    label: "Större lokal",
    monthly: 8000, oneTime: 12000, capacity: 1, rep: 5,
    desc: "+5 rykte + 1 kapacitet. 8 000 kr/mån + 12 000 engångs.",
  },
];

export function BizBeslut() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);

  function refresh() {
    bizEngineApi.listDecisions()
      .then(setDecisions)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  return (
    <BizShell title="Beslut" eye="Spelmotor · 04 / Strategi">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <button onClick={() => setPicking(true)} style={{ ...btnPrimary, marginBottom: 16 }}>
        + Nytt beslut
      </button>

      {decisions.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga beslut än. Anställa, friskvård, leasing, försäkring eller ny
          lokal — varje val påverkar spelmotorn.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {decisions.map(d => (
            <DecisionCard
              key={d.id}
              decision={d}
              onEnd={async () => {
                if (confirm("Avsluta detta beslut?")) {
                  await bizEngineApi.endDecision(d.id);
                  refresh();
                }
              }}
            />
          ))}
        </div>
      )}

      {picking && (
        <DecisionPicker onClose={(r) => {
          setPicking(false);
          if (r) refresh();
        }} />
      )}
    </BizShell>
  );
}


function DecisionCard({
  decision, onEnd,
}: { decision: Decision; onEnd: () => void }) {
  const tmpl = DECISION_TEMPLATES.find(t => t.kind === decision.kind);
  return (
    <div
      style={{
        background: "rgba(15,21,37,0.6)",
        border: "1px solid rgba(99,102,241,0.18)",
        borderRadius: 10, padding: 16,
        opacity: decision.active ? 1 : 0.5,
      }}
    >
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
      }}>
        <div>
          <div style={{
            fontSize: "0.7rem",
            fontFamily: "JetBrains Mono, monospace",
            color: "#818cf8", letterSpacing: 1.2,
            textTransform: "uppercase",
          }}>
            {tmpl?.label || decision.kind}{decision.active && " · AKTIVT"}
          </div>
          <h3 style={{ color: "white", margin: "4px 0 0" }}>
            {decision.title}
          </h3>
          <div style={{ color: "#aab", fontSize: "0.85rem", marginTop: 4 }}>
            Sedan {decision.started_on}
            {decision.ends_on && ` → ${decision.ends_on}`}
            {" · "}
            {decision.monthly_cost > 0 && `${SEK(decision.monthly_cost)} kr/mån `}
            {decision.capacity_delta !== 0 &&
              `· kapacitet ${decision.capacity_delta > 0 ? "+" : ""}${decision.capacity_delta} `}
            {decision.reputation_delta !== 0 &&
              `· rykte ${decision.reputation_delta > 0 ? "+" : ""}${decision.reputation_delta}`}
          </div>
        </div>
        {decision.active && (
          <button onClick={onEnd} style={btnDanger}>
            Avsluta
          </button>
        )}
      </div>
    </div>
  );
}


function DecisionPicker({ onClose }: { onClose: (refreshed: boolean) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function pick(t: typeof DECISION_TEMPLATES[number]) {
    setSubmitting(true);
    setErr(null);
    try {
      await bizEngineApi.createDecision({
        kind: t.kind,
        title: t.label,
        monthly_cost: t.monthly,
        one_time_cost: t.oneTime,
        capacity_delta: t.capacity,
        reputation_delta: t.rep,
        insurance_kind: (t as { insurance_kind?: string }).insurance_kind,
      });
      onClose(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(false)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 600, width: "100%",
          maxHeight: "85vh", overflowY: "auto",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>Välj beslut</h2>

        {err && <div style={{ color: "#fda594", marginBottom: 8 }}>{err}</div>}

        <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
          {DECISION_TEMPLATES.map(t => (
            <button
              key={t.kind}
              onClick={() => pick(t)}
              disabled={submitting}
              style={{
                background: "rgba(99,102,241,0.08)",
                border: "1px solid rgba(99,102,241,0.3)",
                borderRadius: 8, padding: 14,
                color: "white", textAlign: "left",
                cursor: submitting ? "not-allowed" : "pointer",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>{t.label}</div>
              <div style={{ color: "#aab", fontSize: "0.85rem", marginTop: 4 }}>
                {t.desc}
              </div>
            </button>
          ))}
        </div>

        <button
          onClick={() => onClose(false)}
          style={{ ...btnGhost, marginTop: 16 }}
        >
          Avbryt
        </button>
      </div>
    </div>
  );
}


// === BIZ LEVERANTÖRER ===

export function BizLeverantorer() {
  const [invoices, setInvoices] = useState<SupplierInvoice[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [paying, setPaying] = useState<number | null>(null);

  function refresh() {
    bizEngineApi.listSupplierInvoices(filter || undefined)
      .then(setInvoices)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); /* eslint-disable-line */ }, [filter]);

  async function pay(id: number) {
    setPaying(id);
    try {
      await bizEngineApi.paySupplierInvoice(id);
      refresh();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setPaying(null);
    }
  }

  return (
    <BizShell title="Leverantörsfakturor" eye="Spelmotor · 05 / Inköp">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[
          ["", "Alla"], ["open", "Obetalda"], ["paid", "Betalda"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            style={{
              padding: "6px 12px", borderRadius: 6,
              border: "1px solid rgba(99,102,241,0.3)",
              background: filter === v
                ? "rgba(99,102,241,0.25)" : "transparent",
              color: "#c7d2fe", cursor: "pointer", fontSize: "0.85rem",
            }}
          >{l}</button>
        ))}
      </div>

      {invoices.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga leverantörsfakturor. Antingen är allt betalt, eller så har
          läraren inte skickat ut några än.
        </p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr style={{ color: "#aab", textAlign: "left" }}>
              <th style={{ padding: "8px 4px" }}>Avsändare / beskrivning</th>
              <th style={{ padding: "8px 4px" }}>Förfaller</th>
              <th style={{ padding: "8px 4px", textAlign: "right" }}>Belopp</th>
              <th style={{ padding: "8px 4px" }}>Status</th>
              <th style={{ padding: "8px 4px" }}></th>
            </tr>
          </thead>
          <tbody>
            {invoices.map(si => {
              const today = new Date().toISOString().slice(0, 10);
              const overdue = si.status === "open" && si.due_on < today;
              return (
                <tr key={si.id} style={{
                  borderBottom: "1px solid rgba(99,102,241,0.08)",
                }}>
                  <td style={{ padding: "10px 4px" }}>
                    <div style={{ color: "white", fontWeight: 600 }}>
                      {si.sender_name}
                    </div>
                    <div style={{ color: "#aab", fontSize: "0.8rem" }}>
                      {si.description}
                    </div>
                    {si.source === "teacher" && (
                      <div style={{
                        color: "#a78bfa", fontSize: "0.75rem",
                        fontFamily: "JetBrains Mono, monospace",
                        letterSpacing: 1.1,
                      }}>
                        FRÅN LÄRARE
                      </div>
                    )}
                  </td>
                  <td style={{
                    padding: "10px 4px",
                    color: overdue ? "#fda594" : "white",
                    fontWeight: overdue ? 700 : 400,
                  }}>
                    {si.due_on}{overdue && " ⚠"}
                  </td>
                  <td style={{ padding: "10px 4px", textAlign: "right", color: "white" }}>
                    {SEK(si.amount_excl_vat)} kr
                  </td>
                  <td style={{
                    padding: "10px 4px",
                    color: si.status === "paid" ? "#6ee7b7"
                      : overdue ? "#fda594" : "white",
                  }}>
                    {si.status === "paid" ? "Betald" : "Obetald"}
                  </td>
                  <td style={{ padding: "10px 4px", textAlign: "right" }}>
                    {si.status === "open" && (
                      <button
                        onClick={() => pay(si.id)}
                        disabled={paying === si.id}
                        style={btnPrimary}
                      >
                        {paying === si.id ? "…" : "Betala"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </BizShell>
  );
}


// === Shared styles ===

const inputStyle: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 4,
  padding: "8px 10px", borderRadius: 6,
  border: "1px solid rgba(99,102,241,0.3)",
  background: "rgba(15,21,37,0.5)", color: "white",
  fontSize: "0.95rem",
};

const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", fontSize: "0.9rem",
};

const btnPrimary: React.CSSProperties = {
  background: "rgba(99,102,241,0.25)",
  border: "1px solid rgba(99,102,241,0.5)",
  color: "white", padding: "8px 16px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.9rem", fontWeight: 600,
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(99,102,241,0.3)",
  color: "#c7d2fe", padding: "8px 16px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.9rem",
};

const btnDanger: React.CSSProperties = {
  background: "rgba(248,113,113,0.18)",
  border: "1px solid rgba(248,113,113,0.4)",
  color: "#fda594", padding: "6px 12px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.85rem",
};
