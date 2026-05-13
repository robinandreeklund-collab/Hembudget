/**
 * BizSharedOpps · klass-pool offertförfrågningar.
 *
 * Spec: dev/feature-allabolag.md (Fas C)
 *
 * Eleven ser:
 * - Pågående pool-förfrågningar (open · countdown till deadline)
 * - Lämna in-form (ETT bud per förfrågan)
 * - Beslutade förfrågningar med:
 *   - Vinnar-tagg om eleven vann
 *   - AI:s motivering
 *   - Konkurrent-tabell · andras pris/leveranstid/pitch
 *
 * Pedagogiken: eleven ser EXAKT varför AI valde någons offert.
 */
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { BizActorShell } from "./BizActorShell";


type SharedOpp = {
  id: number;
  customer_name: string;
  customer_segment: string;
  title: string;
  description: string;
  market_price: number;
  expected_delivery_days: number;
  industry_key: string;
  deadline_at: string;
  hours_until_deadline: number;
  status: string;
  n_competitors: number;
  has_my_quote: boolean;
  is_winner: boolean | null;
  decision_explanation: string | null;
  estimated_hours: number;
  hours_per_week: number;
};

type Competitor = {
  student_display: string;
  offered_price: number;
  offered_delivery_days: number;
  pitch_text: string | null;
  pitch_quality: number | null;
  is_winner: boolean;
  is_mine: boolean;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizSharedOpps() {
  const [opps, setOpps] = useState<SharedOpp[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SharedOpp | null>(null);

  function refresh() {
    setLoading(true);
    api<SharedOpp[]>("/v2/foretag/opportunities/shared")
      .then(setOpps)
      .catch((e) => setError(String((e as Error).message || e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => { refresh(); }, []);

  const open = opps.filter((o) => o.status === "open");
  const decided = opps.filter((o) => o.status === "decided" || o.status === "expired");
  const wonByMe = decided.filter((o) => o.is_winner === true).length;

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Klass-pool · ⭐ premium"
      title={
        <>
          {open.length} <em>premium-förfrågningar</em> · klassen tävlar.
        </>
      }
      subtitle="Klass-pool-uppdrag betalar 40–60 % över marknadspris · vinnaren får +5 rykte direkt + ⭐ klass-pool-badge på jobbet"
      meta={
        <>
          Pågår: <strong>{open.length}</strong>
          <br />
          Beslutade: <strong>{decided.length}</strong>
          <br />
          Vunna av dig: <strong>{wonByMe}</strong>
        </>
      }
    >
      {error && <div style={errorBoxStyle}>{error}</div>}
      {loading && opps.length === 0 && (
        <div style={{ color: "rgba(255,255,255,0.6)" }}>Laddar pool-förfrågningar…</div>
      )}

      {!loading && opps.length === 0 && (
        <div style={emptyStateStyle}>
          Pool-förfrågningar dyker upp för din bransch ungefär varje 6:e timme. Auto-motorn rullar automatiskt — kom tillbaka senare.
        </div>
      )}

      {/* Öppna · pågår */}
      {open.length > 0 && (
        <>
          <div style={{ ...sectionEyeStyle, color: "#fbbf24", marginBottom: 10 }}>
            ● PÅGÅR · klassen tävlar
          </div>
          <div style={{ display: "grid", gap: 12, marginBottom: 28 }}>
            {open.map((o) => (
              <OppCard
                key={o.id}
                opp={o}
                onClick={() => setEditing(o)}
              />
            ))}
          </div>
        </>
      )}

      {/* Beslutade */}
      {decided.length > 0 && (
        <>
          <div style={sectionEyeStyle}>● BESLUTADE · läs vinnar-motiveringar</div>
          <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
            {decided.map((o) => (
              <DecidedCard key={o.id} opp={o} />
            ))}
          </div>
        </>
      )}

      {editing && (
        <SharedQuoteModal
          opp={editing}
          onClose={(refreshed) => {
            setEditing(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </BizActorShell>
  );
}


function OppCard({ opp, onClick }: { opp: SharedOpp; onClick: () => void }) {
  const hours = opp.hours_until_deadline;
  const urgent = hours < 6;
  return (
    <a
      href="#"
      onClick={(e) => { e.preventDefault(); onClick(); }}
      style={{
        display: "block",
        padding: 18,
        background: opp.has_my_quote
          ? "linear-gradient(135deg, rgba(110,231,183,0.05), rgba(15,21,37,0.55))"
          : "linear-gradient(135deg, rgba(251,191,36,0.06), rgba(15,21,37,0.55))",
        border: `1px solid ${opp.has_my_quote ? "rgba(110,231,183,0.30)" : "rgba(251,191,36,0.30)"}`,
        borderRadius: 10,
        textDecoration: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, fontWeight: 700, letterSpacing: 1.4, color: "#fbbf24" }}>
          {opp.has_my_quote ? "✓ DU HAR LÄMNAT BUD" : "NY · " + opp.customer_segment.toUpperCase()}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          color: urgent ? "#fda594" : "rgba(255,255,255,0.7)",
          fontWeight: 700,
        }}>
          ⌛ {hours.toFixed(1)} h kvar
        </span>
      </div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
        {opp.customer_name} <span style={{ color: "rgba(255,255,255,0.5)", fontWeight: 400 }}>· {opp.title}</span>
      </div>
      <p style={{ color: "rgba(255,255,255,0.78)", fontFamily: "Inter, sans-serif", fontSize: 13, lineHeight: 1.5, margin: "8px 0" }}>
        {opp.description}
      </p>
      <div style={{ display: "flex", gap: 18, marginTop: 10, flexWrap: "wrap", fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.6)", letterSpacing: 0.6 }}>
        <span>📅 Leverans inom <strong style={{ color: "#fff" }}>{opp.expected_delivery_days} dagar</strong></span>
        <span>💰 Riktpris <strong style={{ color: "#fbbf24" }}>{SEK(opp.market_price)} kr</strong></span>
        {opp.estimated_hours > 0 && (
          <span>⏱ Tid <strong style={{ color: "#6ee7b7" }}>{opp.estimated_hours} h</strong> · {opp.hours_per_week} h/v</span>
        )}
        <span>👥 <strong style={{ color: "#c7d2fe" }}>{opp.n_competitors}</strong> konkurrenter</span>
        <span style={{ marginLeft: "auto", color: "#fbbf24", fontWeight: 700 }}>
          {opp.has_my_quote ? "ÄNDRA EJ MÖJLIGT" : "LÄMNA OFFERT →"}
        </span>
      </div>
    </a>
  );
}


function DecidedCard({ opp }: { opp: SharedOpp }) {
  const won = opp.is_winner === true;
  const lost = opp.has_my_quote && opp.is_winner === false;
  const [showCompetitors, setShowCompetitors] = useState(false);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);

  function loadCompetitors() {
    if (showCompetitors) {
      setShowCompetitors(false);
      return;
    }
    api<Competitor[]>(`/v2/foretag/opportunities/shared/${opp.id}/competitors`)
      .then((data) => {
        setCompetitors(data);
        setShowCompetitors(true);
      })
      .catch(() => undefined);
  }

  return (
    <div
      style={{
        padding: 16,
        background: won
          ? "rgba(110,231,183,0.06)"
          : lost
            ? "rgba(220,76,43,0.05)"
            : "rgba(15,21,37,0.4)",
        border: `1px solid ${won ? "rgba(110,231,183,0.30)" : lost ? "rgba(220,76,43,0.30)" : "rgba(255,255,255,0.08)"}`,
        borderRadius: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
        <span style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: 1.4,
          color: won ? "#6ee7b7" : lost ? "#fda594" : "rgba(255,255,255,0.5)",
        }}>
          {won ? "🏆 DU VANN" : lost ? "DU FÖRLORADE" : opp.status === "expired" ? "FÖRFALLEN" : "BESLUTAD"}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ color: "rgba(255,255,255,0.45)", fontFamily: "JetBrains Mono, monospace", fontSize: 10 }}>
          {opp.n_competitors} bud
        </span>
      </div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
        {opp.customer_name} <span style={{ color: "rgba(255,255,255,0.5)", fontWeight: 400 }}>· {opp.title}</span>
      </div>
      {opp.decision_explanation && (
        <div style={{
          marginTop: 10,
          padding: 12,
          background: "rgba(0,0,0,0.18)",
          borderLeft: `2px solid ${won ? "#6ee7b7" : "#fda594"}`,
          borderRadius: 4,
          fontFamily: "Source Serif 4, Georgia, serif",
          fontStyle: "italic",
          fontSize: 13.5,
          color: "rgba(255,255,255,0.85)",
          lineHeight: 1.55,
        }}>
          {opp.decision_explanation}
        </div>
      )}
      {opp.has_my_quote && (
        <button
          onClick={loadCompetitors}
          style={{
            marginTop: 12,
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.18)",
            color: "rgba(255,255,255,0.75)",
            padding: "6px 12px",
            borderRadius: 6,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: 1.2,
            cursor: "pointer",
          }}
        >
          {showCompetitors ? "DÖLJ" : "VISA"} ALLA BUD →
        </button>
      )}
      {showCompetitors && competitors.length > 0 && (
        <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
          {competitors.map((c, i) => (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "1.5fr 0.7fr 0.7fr 0.6fr 80px",
                gap: 12,
                padding: "8px 12px",
                background: c.is_winner ? "rgba(110,231,183,0.08)" : c.is_mine ? "rgba(251,191,36,0.05)" : "rgba(15,21,37,0.4)",
                border: `1px solid ${c.is_winner ? "rgba(110,231,183,0.3)" : c.is_mine ? "rgba(251,191,36,0.25)" : "rgba(255,255,255,0.05)"}`,
                borderRadius: 6,
                alignItems: "center",
              }}
            >
              <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "#fff" }}>
                {c.is_winner && "🏆 "}{c.is_mine && !c.is_winner && "📍 "}{c.student_display}
              </div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
                {SEK(c.offered_price)} kr
              </div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
                {c.offered_delivery_days} dgr
              </div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
                pitch {c.pitch_quality !== null ? Math.round(c.pitch_quality * 100) + "%" : "—"}
              </div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: c.is_winner ? "#6ee7b7" : "rgba(255,255,255,0.5)", letterSpacing: 1.2, textAlign: "right" }}>
                {c.is_winner ? "VINNARE" : c.is_mine ? "DITT" : ""}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function SharedQuoteModal({
  opp, onClose,
}: { opp: SharedOpp; onClose: (refreshed: boolean) => void }) {
  const [price, setPrice] = useState(opp.market_price.toString());
  const [days, setDays] = useState(opp.expected_delivery_days.toString());
  const [pitch, setPitch] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [competitors, setCompetitors] = useState<Competitor[] | null>(null);

  // Hämta konkurrent-bud om eleven redan lämnat eget bud — visar
  // bolagsnamn, pris och leveranstid (pitch döljs förrän opp:en
  // beslutats för att inte uppmuntra copy-paste).
  useEffect(() => {
    if (!opp.has_my_quote) return;
    api<Competitor[]>(
      `/v2/foretag/opportunities/shared/${opp.id}/competitors`,
    )
      .then(setCompetitors)
      .catch(() => undefined);
  }, [opp.id, opp.has_my_quote]);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      await api(`/v2/foretag/opportunities/shared/${opp.id}/quote`, {
        method: "POST",
        body: JSON.stringify({
          offered_price: parseInt(price, 10),
          offered_delivery_days: parseInt(days, 10),
          pitch_text: pitch.trim() || undefined,
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
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12,
          padding: 24,
          maxWidth: 600,
          width: "100%",
        }}
      >
        <h2 style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", marginTop: 0 }}>
          {opp.has_my_quote ? "Ditt bud · " : "Lämna pool-bud · "}{opp.customer_name}
        </h2>
        <div style={{
          background: "rgba(99,102,241,0.06)",
          border: "1px solid rgba(99,102,241,0.2)",
          borderRadius: 6,
          padding: 12,
          marginTop: 10,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "#818cf8", letterSpacing: 1.4, fontWeight: 700, marginBottom: 4 }}>
            UPPDRAGET · {opp.n_competitors} bolag har lämnat bud
          </div>
          <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
            {opp.title}
          </div>
          <div style={{ fontFamily: "Inter, sans-serif", fontSize: 13, color: "rgba(255,255,255,0.85)" }}>
            {opp.description}
          </div>
        </div>
        <p style={{ color: "#aab", fontSize: "0.85rem", marginTop: 14, lineHeight: 1.6 }}>
          Riktpris <strong style={{ color: "#fbbf24" }}>{SEK(opp.market_price)} kr</strong> ·
          förväntad leverans <strong style={{ color: "#fff" }}>{opp.expected_delivery_days} dagar</strong> ·
          deadline om <strong style={{ color: "#fda594" }}>{opp.hours_until_deadline.toFixed(1)} h</strong>
          {opp.estimated_hours > 0 && (
            <>
              <br />
              Uppskattad arbetsinsats: <strong style={{ color: "#6ee7b7" }}>{opp.estimated_hours} h</strong> totalt
              {" "}<span style={{ color: "rgba(255,255,255,0.45)" }}>(≈ {opp.hours_per_week} h/v av din kapacitet)</span>
            </>
          )}
        </p>

        {opp.has_my_quote ? (
          // === Vy-läge: bud redan lämnat → visa konkurrent-tabell ===
          <div style={{ marginTop: 14 }}>
            <div style={{
              padding: "12px 14px",
              background: "rgba(110,231,183,0.08)",
              border: "1px solid rgba(110,231,183,0.30)",
              borderRadius: 6,
              marginBottom: 16,
            }}>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, fontWeight: 700, letterSpacing: 1.4, color: "#6ee7b7", marginBottom: 4 }}>
                ✓ DU HAR LÄMNAT BUD
              </div>
              <p style={{ color: "rgba(255,255,255,0.78)", margin: 0, fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.5 }}>
                Vänta tills deadline — då bestämmer kunden vinnaren. Andras
                pitch döljs tills dess (för att inte uppmuntra copy-paste),
                men du ser pris och leveranstid redan nu.
              </p>
            </div>
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700, letterSpacing: 1.2, color: "#c7d2fe", marginBottom: 8 }}>
              ● ALLA BUD I LÖPET
            </div>
            {competitors === null ? (
              <div style={{ color: "rgba(255,255,255,0.5)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
                Laddar bud…
              </div>
            ) : competitors.length === 0 ? (
              <div style={{ color: "rgba(255,255,255,0.5)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
                Inga andra bud än.
              </div>
            ) : (
              <div style={{ display: "grid", gap: 6 }}>
                {competitors.map((c, i) => (
                  <div
                    key={i}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1.6fr 0.8fr 0.8fr 70px",
                      gap: 10,
                      padding: "8px 12px",
                      background: c.is_mine ? "rgba(251,191,36,0.08)" : "rgba(15,21,37,0.5)",
                      border: `1px solid ${c.is_mine ? "rgba(251,191,36,0.30)" : "rgba(255,255,255,0.06)"}`,
                      borderRadius: 6,
                      alignItems: "center",
                    }}
                  >
                    <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "#fff" }}>
                      {c.is_mine && "📍 "}{c.student_display}
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
                      {SEK(c.offered_price)} kr
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
                      {c.offered_delivery_days} dgr
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: c.is_mine ? "#fbbf24" : "rgba(255,255,255,0.45)", letterSpacing: 1, textAlign: "right" }}>
                      {c.is_mine ? "DITT" : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "flex-end" }}>
              <button onClick={() => onClose(false)} style={btnGhost}>Stäng</button>
            </div>
          </div>
        ) : (
          // === Form-läge: lämna nytt bud ===
          <>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Ditt pris (kr exkl moms)
              <input type="number" value={price} onChange={(e) => setPrice(e.target.value)} style={inputStyle} />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Leveranstid (dagar)
              <input type="number" value={days} onChange={(e) => setDays(e.target.value)} style={inputStyle} />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              Din pitch (frivilligt — höjer dina chanser)
              <textarea
                value={pitch}
                onChange={(e) => setPitch(e.target.value)}
                placeholder="Vad gör just er bra? Varför ska kunden välja er?"
                style={{ ...inputStyle, minHeight: 80 }}
              />
            </label>
            {err && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{err}</div>}
            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button onClick={submit} disabled={submitting} style={btnPrimary}>
                {submitting ? "Skickar…" : "Skicka offert →"}
              </button>
              <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


// === Styles ===
const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "#c7d2fe",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 6,
  padding: 10,
  background: "rgba(0,0,0,0.3)",
  border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 6,
  color: "#fff",
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 13,
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24",
  border: "none",
  color: "#422006",
  padding: "10px 20px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.7)",
  padding: "10px 20px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const emptyStateStyle: React.CSSProperties = {
  padding: "32px 24px",
  textAlign: "center",
  background: "rgba(15,21,37,0.5)",
  border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 10,
  color: "rgba(255,255,255,0.7)",
  fontFamily: "Source Serif 4, Georgia, serif",
};

const errorBoxStyle: React.CSSProperties = {
  padding: 12,
  background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)",
  borderRadius: 6,
  color: "#fda594",
  fontFamily: "Source Serif 4, Georgia, serif",
};
