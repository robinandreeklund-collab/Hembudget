/**
 * BizTillvaxt · Tillväxt-aktör · lokaler, utrustning, kapacitet, MCP, lån.
 *
 * Spec: Fas E+F · dev/feature-allabolag.md
 *
 * Vy:
 *  - Kapacitetsmätare (used / max)
 *  - Lokal-marketplace (hyra eller köpa)
 *  - Utrustning-marketplace
 *  - MCP-knapp för instant kapacitet
 *  - Lån-lista med ansökningsmodal
 */
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { BizActorShell } from "./BizActorShell";
import { TimeCapacityBreakdown, useTimeCapacity } from "./TimeCapacityWidget";


type Overview = {
  capacity: {
    used: number;
    max: number;
    base_max: number;
    speed_multiplier: number;
    mcp_bonus: number;
    location_kind: string;
    location_label: string;
    equipment_kind: string;
    equipment_label: string;
    is_overloaded: boolean;
    utilization_pct: number;
  };
  location: {
    kind: string;
    label: string;
    monthly_cost: number;
    max_employees: number;
    max_concurrent_jobs: number;
    is_owned: boolean;
  };
  equipment: {
    kind: string;
    label: string;
    speed_multiplier: number;
    breakdown_risk: number;
  };
  monthly_overhead: number;
  kassa: number;
  n_employees: number;
};

type LocationItem = {
  kind: string;
  label: string;
  monthly_cost: number;
  max_employees: number;
  max_concurrent_jobs: number;
  purchase_price: number | null;
  is_current: boolean;
};

type EquipmentItem = {
  kind: string;
  label: string;
  purchase_price: number;
  speed_multiplier: number;
  breakdown_risk: number;
  is_current: boolean;
};

type Loan = {
  id: number;
  purpose: string;
  lender: string;
  principal: number;
  outstanding: number;
  interest_rate: number;
  monthly_payment: number;
  months_total: number;
  months_left: number;
  is_personal_guarantee: boolean;
  status: string;
  started_on: string;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizTillvaxt() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [equipment, setEquipment] = useState<EquipmentItem[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"location" | "equipment" | "loans" | "decisions" | "marketing">("location");
  const [showLoanApply, setShowLoanApply] = useState(false);
  const [showMcp, setShowMcp] = useState(false);

  function refresh() {
    Promise.all([
      api<Overview>("/v2/foretag/growth/overview"),
      api<{ items: LocationItem[]; can_afford_kassa: number }>("/v2/foretag/growth/locations"),
      api<{ items: EquipmentItem[]; can_afford_kassa: number }>("/v2/foretag/growth/equipment"),
      api<Loan[]>("/v2/foretag/growth/loans"),
    ])
      .then(([o, l, e, ln]) => {
        setOverview(o);
        setLocations(l.items);
        setEquipment(e.items);
        setLoans(ln);
      })
      .catch((e) => setError(String((e as Error).message || e)));
  }

  useEffect(() => { refresh(); }, []);

  if (!overview) {
    return (
      <BizActorShell
        pillLabel="Aktör · biz · Tillväxt"
        title={<>Tillväxt</>}
        subtitle="Laddar…"
        meta={<>—</>}
      >
        {error ? <div style={errorBoxStyle}>{error}</div> : <div>Laddar…</div>}
      </BizActorShell>
    );
  }

  const cap = overview.capacity;
  const utilColor = cap.is_overloaded ? "#dc4c2b" : cap.utilization_pct > 80 ? "#fbbf24" : "#6ee7b7";

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Tillväxt"
      title={
        <>
          Skala företaget — <em>kapacitet, lokaler, lån</em>.
        </>
      }
      subtitle="Investera i bättre utrustning + större lokaler för att ta fler uppdrag"
      meta={
        <>
          Kapacitet: <strong>{cap.used} / {cap.max}</strong>
          <br />
          Anställda: <strong>{overview.n_employees}</strong>
          <br />
          Kassa: <strong>{SEK(overview.kassa)} kr</strong>
        </>
      }
    >
      {error && <div style={errorBoxStyle}>{error}</div>}

      {/* Startup-kit · bas-utrustning + bil (om bransch kräver) */}
      <StartupKitSection onRefresh={refresh} />

      {/* Tids-kapacitet · Fas K */}
      <TimeCapacitySection onRefresh={refresh} />

      {/* Kapacitetsmätare */}
      <div style={{ ...cardStyle, marginBottom: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ ...sectionEyeStyle }}>● KAPACITET · pågående uppdrag</div>
            <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 6 }}>
              <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontWeight: 700, fontSize: 32, color: utilColor }}>
                {cap.used} / {cap.max}
              </span>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
                {cap.utilization_pct} % belastning
              </span>
              {cap.mcp_bonus > 0 && (
                <span style={{ ...badgeStyle, background: "rgba(110,231,183,0.18)", color: "#6ee7b7" }}>
                  +{cap.mcp_bonus} MCP
                </span>
              )}
              {cap.is_overloaded && (
                <span style={{ ...badgeStyle, background: "rgba(220,76,43,0.18)", color: "#fda594" }}>
                  ⚠ ÖVERBELASTAD
                </span>
              )}
            </div>
            <div style={{ height: 8, marginTop: 12, background: "rgba(255,255,255,0.08)", borderRadius: 100 }}>
              <div style={{
                height: "100%",
                width: `${Math.min(100, cap.utilization_pct)}%`,
                background: utilColor,
                borderRadius: 100,
                transition: "width 0.3s",
              }} />
            </div>
          </div>
          <button onClick={() => setShowMcp(true)} style={{ ...btnPrimary, whiteSpace: "nowrap" }}>
            Hyr in frilans (MCP) →
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 8 }}>
          <Mini eye="LOKAL" value={cap.location_label} sub={`${cap.base_max} jobb i tid`} />
          <Mini eye="UTRUSTNING" value={cap.equipment_label} sub={`× ${cap.speed_multiplier.toFixed(2)} speed`} />
          <Mini eye="MÅNADSKOST" value={`${SEK(overview.monthly_overhead)} kr`} sub="hyra + lån" />
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        <TabBtn active={tab === "location"} onClick={() => setTab("location")}>Lokaler</TabBtn>
        <TabBtn active={tab === "equipment"} onClick={() => setTab("equipment")}>Utrustning</TabBtn>
        <TabBtn active={tab === "decisions"} onClick={() => setTab("decisions")}>Beslut & Drift</TabBtn>
        <TabBtn active={tab === "marketing"} onClick={() => setTab("marketing")}>Marknadsföring</TabBtn>
        <TabBtn active={tab === "loans"} onClick={() => setTab("loans")}>Lån</TabBtn>
      </div>

      {/* Lokal-marketplace */}
      {tab === "location" && (
        <div style={{ display: "grid", gap: 10 }}>
          {locations.map((loc) => (
            <LocationCard key={loc.kind} loc={loc} kassa={overview.kassa} onUpgraded={refresh} />
          ))}
        </div>
      )}

      {/* Utrustning-marketplace */}
      {tab === "equipment" && (
        <div style={{ display: "grid", gap: 10 }}>
          {equipment.map((eq) => (
            <EquipmentCard key={eq.kind} eq={eq} kassa={overview.kassa} onBought={refresh} />
          ))}
        </div>
      )}

      {/* Beslut & Drift · anställa, försäkring, leasing, friskvård */}
      {tab === "decisions" && (
        <DecisionsTab />
      )}

      {/* Marknadsföring · 10 paket-nivåer (lokaltidning → TV) */}
      {tab === "marketing" && (
        <MarketingTab kassa={overview.kassa} onBought={refresh} />
      )}

      {/* Lån */}
      {tab === "loans" && (
        <div>
          <div style={{ display: "flex", marginBottom: 12 }}>
            <button onClick={() => setShowLoanApply(true)} style={btnPrimary}>
              + Ansök om företagslån
            </button>
          </div>
          {loans.length === 0 ? (
            <div style={emptyStyle}>Inga lån. Ta ett tillväxtlån för att investera.</div>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {loans.map((ln) => <LoanCard key={ln.id} loan={ln} onRepaid={refresh} />)}
            </div>
          )}
        </div>
      )}

      {showMcp && <McpModal kassa={overview.kassa} onClose={(ok) => { setShowMcp(false); if (ok) refresh(); }} />}
      {showLoanApply && <LoanApplyModal onClose={(ok) => { setShowLoanApply(false); if (ok) refresh(); }} />}
    </BizActorShell>
  );
}


function LocationCard({ loc, kassa, onUpgraded }: { loc: LocationItem; kassa: number; onUpgraded: () => void }) {
  const [busy, setBusy] = useState(false);
  async function rent() {
    if (loc.is_current) return;
    if (!confirm(`Hyra ${loc.label} för ${SEK(loc.monthly_cost)} kr/mån?`)) return;
    setBusy(true);
    try {
      await api("/v2/foretag/growth/locations/upgrade", {
        method: "POST",
        body: JSON.stringify({ location_kind: loc.kind, is_purchase: false }),
      });
      onUpgraded();
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }
  async function buy() {
    if (!loc.purchase_price) return;
    if (kassa < loc.purchase_price) {
      alert(`Otillräcklig kassa (saknas ${SEK(loc.purchase_price - kassa)} kr). Ta ett företagslån först.`);
      return;
    }
    if (!confirm(`Köpa ${loc.label} för ${SEK(loc.purchase_price)} kr?`)) return;
    setBusy(true);
    try {
      await api("/v2/foretag/growth/locations/upgrade", {
        method: "POST",
        body: JSON.stringify({ location_kind: loc.kind, is_purchase: true }),
      });
      onUpgraded();
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }

  return (
    <div style={{
      ...cardStyle,
      borderColor: loc.is_current ? "rgba(110,231,183,0.40)" : "rgba(255,255,255,0.10)",
      background: loc.is_current ? "rgba(110,231,183,0.05)" : "rgba(15,21,37,0.55)",
    }}>
      <div style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
          {loc.label}
        </div>
        {loc.is_current && <span style={{ ...badgeStyle, background: "rgba(110,231,183,0.18)", color: "#6ee7b7" }}>NUVARANDE</span>}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
          {loc.monthly_cost > 0 ? `${SEK(loc.monthly_cost)} kr/mån` : "Gratis"}
        </span>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)", letterSpacing: 0.5, marginTop: 6 }}>
        Max {loc.max_employees} anställda · {loc.max_concurrent_jobs} samtidiga jobb
      </div>
      {!loc.is_current && (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {loc.monthly_cost > 0 && (
            <button onClick={rent} disabled={busy} style={btnSecondary}>
              Hyr · {SEK(loc.monthly_cost)} kr/mån
            </button>
          )}
          {loc.purchase_price && (
            <button onClick={buy} disabled={busy} style={btnPrimary}>
              Köp · {SEK(loc.purchase_price)} kr
            </button>
          )}
        </div>
      )}
    </div>
  );
}


function EquipmentCard({ eq, kassa, onBought }: { eq: EquipmentItem; kassa: number; onBought: () => void }) {
  const [busy, setBusy] = useState(false);
  async function buy() {
    if (eq.is_current) return;
    if (eq.purchase_price > 0 && kassa < eq.purchase_price) {
      alert(`Otillräcklig kassa (saknas ${SEK(eq.purchase_price - kassa)} kr).`);
      return;
    }
    if (!confirm(`Köpa ${eq.label}? ${eq.purchase_price > 0 ? SEK(eq.purchase_price) + " kr" : "Gratis"}`)) return;
    setBusy(true);
    try {
      await api("/v2/foretag/growth/equipment/buy", {
        method: "POST",
        body: JSON.stringify({ equipment_kind: eq.kind }),
      });
      onBought();
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }
  return (
    <div style={{
      ...cardStyle,
      borderColor: eq.is_current ? "rgba(110,231,183,0.40)" : "rgba(255,255,255,0.10)",
      background: eq.is_current ? "rgba(110,231,183,0.05)" : "rgba(15,21,37,0.55)",
    }}>
      <div style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
          {eq.label}
        </div>
        {eq.is_current && <span style={{ ...badgeStyle, background: "rgba(110,231,183,0.18)", color: "#6ee7b7" }}>NUVARANDE</span>}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
          × {eq.speed_multiplier.toFixed(2)} speed · {(eq.breakdown_risk * 100).toFixed(0)}% driftstopp/v
        </span>
      </div>
      {!eq.is_current && (
        <div style={{ marginTop: 10 }}>
          <button onClick={buy} disabled={busy} style={btnPrimary}>
            Köp · {eq.purchase_price > 0 ? SEK(eq.purchase_price) + " kr" : "Gratis"}
          </button>
        </div>
      )}
    </div>
  );
}


function LoanCard({ loan, onRepaid }: { loan: Loan; onRepaid: () => void }) {
  const [busy, setBusy] = useState(false);
  async function pay() {
    if (!confirm(`Betala 1 månads-rate (${SEK(loan.monthly_payment)} kr)?`)) return;
    setBusy(true);
    try {
      await api(`/v2/foretag/growth/loans/${loan.id}/pay`, { method: "POST" });
      onRepaid();
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
          {loan.purpose === "startup_capital" ? "Startup-kapitallån" : loan.purpose === "growth" ? "Tillväxtlån" : "Likviditetsbuffert"}
        </div>
        {loan.is_personal_guarantee && (
          <span style={{ ...badgeStyle, background: "rgba(251,191,36,0.18)", color: "#fbbf24" }}>
            PERSONLIG BORGEN
          </span>
        )}
        {loan.status === "repaid" && (
          <span style={{ ...badgeStyle, background: "rgba(110,231,183,0.18)", color: "#6ee7b7" }}>SLUTBETALT</span>
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 12 }}>
        <Mini eye="UTESTÅENDE" value={`${SEK(loan.outstanding)} kr`} sub={`av ${SEK(loan.principal)}`} />
        <Mini eye="RÄNTA" value={`${(loan.interest_rate * 100).toFixed(1)} %`} sub={`/ år`} />
        <Mini eye="MÅN.RATE" value={`${SEK(loan.monthly_payment)} kr`} sub={`${loan.months_left} mån kvar`} />
        <Mini eye="LÄNGD" value={`${loan.months_total} mån`} sub={loan.lender} />
      </div>
      {loan.status === "active" && (
        <div style={{ marginTop: 12 }}>
          <button onClick={pay} disabled={busy} style={btnSecondary}>
            Betala 1 månadsrate manuellt
          </button>
          <span style={{ marginLeft: 12, fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
            (auto-debiteras i tick-engine)
          </span>
        </div>
      )}
    </div>
  );
}


function McpModal({ kassa, onClose }: { kassa: number; onClose: (ok: boolean) => void }) {
  const [weeks, setWeeks] = useState(1);
  const [busy, setBusy] = useState(false);
  const cost = 48000 * weeks;
  async function submit() {
    if (kassa < cost) { alert(`Otillräcklig kassa (saknas ${SEK(cost - kassa)} kr)`); return; }
    setBusy(true);
    try {
      await api("/v2/foretag/growth/mcp/rent", {
        method: "POST",
        body: JSON.stringify({ weeks }),
      });
      onClose(true);
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }
  return (
    <Modal onClose={() => onClose(false)} title="Hyr in frilans-konsult (MCP)">
      <p style={{ color: "rgba(255,255,255,0.85)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.55 }}>
        MCP = "More Capacity Programmatically". En frilans-konsult ger dig
        +1 kapacitet i {weeks} vecka{weeks > 1 ? "or" : ""}. Snabbt att aktivera,
        men dyrare per uppdrag än en anställd.
      </p>
      <label style={{ color: "white", display: "block", marginTop: 12 }}>
        Antal veckor (max 4)
        <input type="number" min={1} max={4} value={weeks} onChange={(e) => setWeeks(Math.max(1, Math.min(4, parseInt(e.target.value, 10) || 1)))} style={inputStyle} />
      </label>
      <div style={{ marginTop: 14, padding: 12, background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 6 }}>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#818cf8", letterSpacing: 1.4 }}>KOSTNAD</div>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 22, fontStyle: "italic", color: "#fbbf24", fontWeight: 700, marginTop: 4 }}>
          {SEK(cost)} kr
        </div>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
          {SEK(48000)} kr × {weeks} v · 1 200 kr/h × 8 h × 5 dagar
        </div>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        <button onClick={submit} disabled={busy} style={btnPrimary}>
          {busy ? "Bokar…" : `Hyr in · ${SEK(cost)} kr →`}
        </button>
        <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
      </div>
    </Modal>
  );
}


function LoanApplyModal({ onClose }: { onClose: (ok: boolean) => void }) {
  const [purpose, setPurpose] = useState<"growth" | "buffer">("growth");
  const [principal, setPrincipal] = useState(100000);
  const [pg, setPg] = useState(false);
  const [busy, setBusy] = useState(false);
  const rate = pg ? (purpose === "growth" ? 6 : 9) : (purpose === "growth" ? 9.5 : 14);
  const months = purpose === "growth" ? 60 : 24;
  const r = rate / 100 / 12;
  const monthly = Math.round(principal * r / (1 - Math.pow(1 + r, -months)));

  async function submit() {
    setBusy(true);
    try {
      await api("/v2/foretag/growth/loans/apply", {
        method: "POST",
        body: JSON.stringify({
          purpose,
          principal,
          is_personal_guarantee: pg,
        }),
      });
      onClose(true);
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(false); }
  }

  return (
    <Modal onClose={() => onClose(false)} title="Ansök om företagslån">
      <label style={{ color: "white", display: "block", marginTop: 8 }}>
        Syfte
        <select value={purpose} onChange={(e) => setPurpose(e.target.value as "growth" | "buffer")} style={inputStyle}>
          <option value="growth">Tillväxtlån (lokal/utrustning) · 60 mån</option>
          <option value="buffer">Likviditetsbuffert · 24 mån</option>
        </select>
      </label>
      <label style={{ color: "white", display: "block", marginTop: 12 }}>
        Belopp
        <input type="number" value={principal} onChange={(e) => setPrincipal(parseInt(e.target.value, 10) || 0)} style={inputStyle} />
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", fontFamily: "JetBrains Mono, monospace" }}>
          {purpose === "growth" ? "10 000 – 500 000 kr" : "5 000 – 100 000 kr"}
        </span>
      </label>
      <label style={{ color: "white", display: "flex", alignItems: "center", gap: 8, marginTop: 14, fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14 }}>
        <input type="checkbox" checked={pg} onChange={(e) => setPg(e.target.checked)} />
        Personlig borgen — ger lägre ränta men du riskerar privat-ekonomin om bolaget går i konkurs
      </label>
      <div style={{ marginTop: 14, padding: 12, background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.25)", borderRadius: 6 }}>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#fbbf24", letterSpacing: 1.4 }}>FÖRSLAG</div>
        <div style={{ marginTop: 6, fontFamily: "Source Serif 4, Georgia, serif", color: "rgba(255,255,255,0.85)", fontSize: 13.5, lineHeight: 1.55 }}>
          {SEK(principal)} kr · {rate.toFixed(1)} % ränta · {months} mån<br/>
          Månadsbetalning: <strong style={{ color: "#fff" }}>{SEK(monthly)} kr</strong> · totalt över löptiden: {SEK(monthly * months)} kr
        </div>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        <button onClick={submit} disabled={busy} style={btnPrimary}>
          {busy ? "Skickar…" : "Ansök →"}
        </button>
        <button onClick={() => onClose(false)} style={btnGhost}>Avbryt</button>
      </div>
    </Modal>
  );
}


function Modal({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#0f1525", border: "1px solid rgba(99,102,241,0.4)", borderRadius: 12, padding: 24, maxWidth: 560, width: "100%" }}>
        <h2 style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff", marginTop: 0 }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}


function TabBtn({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      background: active ? "rgba(99,102,241,0.18)" : "transparent",
      border: `1px solid ${active ? "rgba(99,102,241,0.45)" : "rgba(255,255,255,0.18)"}`,
      color: active ? "#c7d2fe" : "rgba(255,255,255,0.7)",
      padding: "8px 16px", borderRadius: 6,
      fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
      letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
    }}>
      {children}
    </button>
  );
}


function Mini({ eye, value, sub }: { eye: string; value: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700, letterSpacing: 1.2, color: "rgba(255,255,255,0.4)" }}>{eye}</div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700, fontSize: 16, color: "#fff", marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "rgba(255,255,255,0.45)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}


// === Styles ===
const cardStyle: React.CSSProperties = {
  background: "rgba(15,21,37,0.55)",
  border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 10, padding: 16,
};

const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
  fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe",
};

const badgeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace", fontSize: 9,
  fontWeight: 700, letterSpacing: 1.2, padding: "3px 8px",
  borderRadius: 100, textTransform: "uppercase",
};

const inputStyle: React.CSSProperties = {
  width: "100%", marginTop: 6, padding: 10,
  background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 6, color: "#fff",
  fontFamily: "JetBrains Mono, monospace", fontSize: 13,
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24", border: "none", color: "#422006",
  padding: "9px 18px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  background: "rgba(99,102,241,0.18)", border: "1px solid rgba(99,102,241,0.45)",
  color: "#c7d2fe", padding: "9px 14px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent", border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.7)", padding: "9px 14px", borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
  fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
};

const emptyStyle: React.CSSProperties = {
  padding: "20px 24px", textAlign: "center",
  background: "rgba(15,21,37,0.4)", border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 8, color: "rgba(255,255,255,0.65)",
  fontFamily: "Source Serif 4, Georgia, serif",
};

const errorBoxStyle: React.CSSProperties = {
  padding: 12, background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)", borderRadius: 6,
  color: "#fda594", fontFamily: "Source Serif 4, Georgia, serif", marginBottom: 14,
};


function TimeCapacitySection({ onRefresh }: { onRefresh: () => void }) {
  const { data, refresh } = useTimeCapacity();
  if (!data) return null;
  async function quit() {
    if (!confirm(
      "Säga upp privat-jobbet?\n\nKonsekvens: Trygghet -15 i pentagon.\n"
      + "Bonus: +44 h/v till bolaget."
    )) return;
    try {
      await api("/v2/foretag/capacity/quit-private-job", { method: "POST" });
      refresh();
      onRefresh();
    } catch (e) { alert((e as Error).message); }
  }
  return (
    <div style={{ marginBottom: 18 }}>
      <TimeCapacityBreakdown data={data} onQuit={quit} />
    </div>
  );
}


// === Startup-kit-sektion · bas-utrustning + bil ===

type StartupKit = {
  has_base_equipment: boolean;
  has_car: boolean;
  requires_car: boolean;
  base_equipment_label: string;
  base_equipment_cost: number;
  car_cost: number;
  industry_label: string | null;
  industry_key: string | null;
};

function StartupKitSection({ onRefresh }: { onRefresh: () => void }) {
  const [kit, setKit] = useState<StartupKit | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    api<StartupKit>("/v2/foretag/growth/startup-kit").then(setKit).catch(() => undefined);
  }
  useEffect(() => { refresh(); }, []);
  if (!kit) return null;

  // Inget krävs för denna bransch
  if (kit.has_base_equipment && (!kit.requires_car || kit.has_car)) return null;

  async function buy(item: "base_equipment" | "car", funding: "cash" | "private_loan" | "business_loan_pg") {
    setBusy(true);
    try {
      await api("/v2/foretag/growth/startup-kit/buy", {
        method: "POST",
        body: JSON.stringify({ item, funding_method: funding }),
      });
      refresh();
      onRefresh();
    } catch (e) { alert((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div style={{
      background: "linear-gradient(135deg, rgba(220,76,43,0.08), rgba(15,21,37,0.55))",
      border: "1px solid rgba(220,76,43,0.30)",
      borderLeft: "3px solid #fda594",
      borderRadius: 10, padding: 18, marginBottom: 18,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
        fontWeight: 700, letterSpacing: 1.4, color: "#fda594",
      }}>
        ⚠ STARTUP-KIT KRÄVS · INNAN DU KAN TA UPPDRAG
      </div>
      <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.55, color: "rgba(255,255,255,0.85)", margin: "8px 0 14px" }}>
        En {kit.industry_label?.toLowerCase()} kan inte börja utan rätt
        utrustning. Köp dessa innan kunderna börjar höra av sig.
      </p>

      {/* Bas-utrustning */}
      {!kit.has_base_equipment && (
        <KitItemCard
          title="Bas-utrustning"
          desc={kit.base_equipment_label}
          cost={kit.base_equipment_cost}
          busy={busy}
          onBuyCash={() => buy("base_equipment", "cash")}
          onBuyPrivateLoan={() => buy("base_equipment", "private_loan")}
          onBuyBizLoan={() => buy("base_equipment", "business_loan_pg")}
        />
      )}

      {/* Bil */}
      {kit.requires_car && !kit.has_car && (
        <div style={{ marginTop: kit.has_base_equipment ? 0 : 10 }}>
          <KitItemCard
            title="Företagsbil"
            desc={`${kit.industry_label} kräver bil för transport till kund + leveranser. Utan bil kan du inte ta privat-kund-jobb.`}
            cost={kit.car_cost}
            busy={busy}
            onBuyCash={() => buy("car", "cash")}
            onBuyPrivateLoan={() => buy("car", "private_loan")}
            onBuyBizLoan={() => buy("car", "business_loan_pg")}
          />
        </div>
      )}
    </div>
  );
}


function KitItemCard({
  title, desc, cost, busy,
  onBuyCash, onBuyPrivateLoan, onBuyBizLoan,
}: {
  title: string; desc: string; cost: number; busy: boolean;
  onBuyCash: () => void;
  onBuyPrivateLoan: () => void;
  onBuyBizLoan: () => void;
}) {
  return (
    <div style={{ padding: 14, background: "rgba(0,0,0,0.2)", borderRadius: 8, marginTop: 10 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
          {title}
        </div>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: "#fbbf24", fontWeight: 700 }}>
          {SEK(cost)} kr
        </span>
      </div>
      <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "rgba(255,255,255,0.78)", lineHeight: 1.55, margin: "6px 0 10px" }}>
        {desc}
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={onBuyCash} disabled={busy} style={btnPrimary}>Betala från kassa</button>
        <button onClick={onBuyPrivateLoan} disabled={busy} style={btnSecondary}>Privat-lån</button>
        <button onClick={onBuyBizLoan} disabled={busy} style={btnSecondary}>Företagslån (personlig borgen)</button>
      </div>
    </div>
  );
}


// === Beslut & Drift-tab · återanvänder existing decision-API ===

type Decision = {
  id: number;
  kind: string;
  title: string;
  monthly_cost: number;
  pipeline_boost?: number;
  active: boolean;
  started_on: string;
};

const DECISION_PRESETS = [
  { kind: "employee", title: "Anställa heltidare", monthly_cost: 35000, desc: "+1 anställd · +40 h/v kapacitet · arbetsgivaravgifter ingår" },
  { kind: "marketing", title: "Marknadsföring · digital", monthly_cost: 8000, desc: "+10 % pipeline · varar tills uppsagd" },
  { kind: "insurance", title: "Företagsförsäkring", monthly_cost: 1200, desc: "Skydd vid skada/stöld + ansvarsförsäkring" },
  { kind: "leasing", title: "Leasing · servicebil", monthly_cost: 4500, desc: "Servicebil utan kapital · färre kostnader än köp" },
  { kind: "wellness", title: "Friskvårdsbidrag (5k/anställd/år)", monthly_cost: 0, desc: "Skattefri förmån · höjer trivsel" },
];

function DecisionsTab() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [busy, setBusy] = useState(false);

  function refresh() {
    api<Decision[]>("/v2/foretag/decisions").then(setDecisions).catch(() => undefined);
  }
  useEffect(() => { refresh(); }, []);

  async function add(preset: typeof DECISION_PRESETS[number]) {
    if (!confirm(`Aktivera "${preset.title}"? Månadskostnad: ${SEK(preset.monthly_cost)} kr`)) return;
    setBusy(true);
    try {
      await api("/v2/foretag/decisions", {
        method: "POST",
        body: JSON.stringify({
          kind: preset.kind,
          title: preset.title,
          monthly_cost: preset.monthly_cost,
        }),
      });
      refresh();
    } catch (e) { alert((e as Error).message); }
    finally { setBusy(false); }
  }

  async function endDecision(id: number) {
    if (!confirm("Avsluta detta beslut?")) return;
    try {
      await api(`/v2/foretag/decisions/${id}`, { method: "DELETE" });
      refresh();
    } catch (e) { alert((e as Error).message); }
  }

  const active = decisions.filter((d) => d.active);

  return (
    <div>
      <div style={sectionEyeStyle}>● AKTIVA BESLUT</div>
      <div style={{ display: "grid", gap: 8, marginTop: 10, marginBottom: 24 }}>
        {active.length === 0 ? (
          <div style={emptyStyle}>Inga aktiva beslut.</div>
        ) : (
          active.map((d) => (
            <div key={d.id} style={{
              padding: "12px 16px",
              background: "rgba(110,231,183,0.04)",
              border: "1px solid rgba(110,231,183,0.25)",
              borderRadius: 8,
              display: "flex",
              gap: 12,
              alignItems: "baseline",
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 15, fontWeight: 700, color: "#fff" }}>
                  {d.title}
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)" }}>
                  {d.kind} · sedan {d.started_on}
                </div>
              </div>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
                {SEK(d.monthly_cost)} kr/mån
              </span>
              <button onClick={() => endDecision(d.id)} style={btnGhost}>Avsluta</button>
            </div>
          ))
        )}
      </div>

      <div style={sectionEyeStyle}>● TILLGÄNGLIGA BESLUT · driv tillväxten</div>
      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        {DECISION_PRESETS.map((p) => (
          <div key={p.kind} style={{ ...cardStyle, display: "flex", gap: 12, alignItems: "baseline" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 15, fontWeight: 700, color: "#fff" }}>
                {p.title}
              </div>
              <p style={{ color: "rgba(255,255,255,0.7)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 12.5, margin: "4px 0 0", lineHeight: 1.5 }}>
                {p.desc}
              </p>
            </div>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
              {p.monthly_cost > 0 ? `${SEK(p.monthly_cost)} kr/mån` : "0 kr"}
            </span>
            <button onClick={() => add(p)} disabled={busy} style={btnPrimary}>Aktivera</button>
          </div>
        ))}
      </div>
    </div>
  );
}


// === Marknadsföring · 10 paket-nivåer (lokaltidning → TV) ===

type MarketingPackage = {
  key: string;
  level: number;
  title: string;
  channel: string;
  cost: number;
  duration_weeks: number;
  pipeline_boost: number;
  reputation_bump: number;
  description: string;
};

type ActiveMarketing = {
  id: number;
  kind: string;
  title: string;
  cost: number;
  duration_weeks: number;
  ai_feedback: string | null;
  started_on: string;
  ends_on: string;
  active: boolean;
};

function MarketingTab({ kassa, onBought }: { kassa: number; onBought: () => void }) {
  const [packages, setPackages] = useState<MarketingPackage[]>([]);
  const [active, setActive] = useState<ActiveMarketing[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  function refresh() {
    Promise.all([
      api<MarketingPackage[]>("/v2/foretag/marketing/packages"),
      api<ActiveMarketing[]>("/v2/foretag/marketing?only_active=true"),
    ])
      .then(([p, a]) => { setPackages(p); setActive(a); })
      .catch(() => undefined);
  }
  useEffect(() => { refresh(); }, []);

  async function buy(pkg: MarketingPackage) {
    if (kassa < pkg.cost) {
      if (!confirm(
        `Otillräcklig kassa (saknas ${SEK(pkg.cost - kassa)} kr). ` +
        `Detta blir en negativ post på företagskontot. Fortsätta?`
      )) return;
    } else if (!confirm(
      `Köpa "${pkg.title}" för ${SEK(pkg.cost)} kr?\n\n` +
      `Pipeline-boost: ${pkg.pipeline_boost.toFixed(2)}× i ${pkg.duration_weeks} v\n` +
      `Rykte: +${pkg.reputation_bump} omedelbart`
    )) return;

    setBusy(pkg.key);
    try {
      await api("/v2/foretag/marketing/packages/buy", {
        method: "POST",
        body: JSON.stringify({ key: pkg.key }),
      });
      refresh();
      onBought();
    } catch (e) { alert(`Fel: ${(e as Error).message || e}`); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <div style={{
        padding: 14,
        background: "rgba(99,102,241,0.06)",
        border: "1px solid rgba(99,102,241,0.25)",
        borderRadius: 8,
        marginBottom: 18,
        color: "rgba(255,255,255,0.78)",
        fontFamily: "Source Serif 4, Georgia, serif",
        fontSize: 13.5,
        lineHeight: 1.6,
      }}>
        <strong style={{ color: "#c7d2fe" }}>Hur paketen påverkar dig:</strong>
        {" "}Pipeline-boost ökar chansen att vinna offerter (kundförfrågningar). Rykte
        höjs omedelbart och ger dig ett försteg framöver. Större paket = bredare räckvidd =
        högre pris. Välj realistiskt — pengarna måste in från jobben.
      </div>

      {active.filter((a) => a.kind === "paket").length > 0 && (
        <>
          <div style={sectionEyeStyle}>● AKTIVA PAKET</div>
          <div style={{ display: "grid", gap: 8, marginTop: 10, marginBottom: 22 }}>
            {active.filter((a) => a.kind === "paket").map((m) => (
              <div key={m.id} style={{
                padding: "12px 16px",
                background: "rgba(110,231,183,0.04)",
                border: "1px solid rgba(110,231,183,0.25)",
                borderRadius: 8,
              }}>
                <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                  <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 15, fontWeight: 700, color: "#fff" }}>
                    {m.title}
                  </span>
                  <span style={{ flex: 1 }} />
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)" }}>
                    t.o.m. {m.ends_on}
                  </span>
                </div>
                {m.ai_feedback && (
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)", marginTop: 4 }}>
                    {m.ai_feedback}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <div style={sectionEyeStyle}>● MARKNADSFÖRINGS-PAKET · 10 NIVÅER</div>
      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        {packages.map((p) => {
          const affordable = kassa >= p.cost;
          return (
            <div key={p.key} style={{
              ...cardStyle,
              borderColor: affordable ? "rgba(255,255,255,0.10)" : "rgba(220,76,43,0.25)",
              opacity: 1,
            }}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <span style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
                  color: "#c7d2fe",
                  background: "rgba(99,102,241,0.18)",
                  padding: "3px 8px", borderRadius: 4,
                }}>
                  NIVÅ {p.level}
                </span>
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
                  {p.title}
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
                  · {p.channel}
                </span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "#fbbf24", fontWeight: 700 }}>
                  {SEK(p.cost)} kr
                </span>
              </div>
              <p style={{ color: "rgba(255,255,255,0.72)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, margin: "8px 0", lineHeight: 1.5 }}>
                {p.description}
              </p>
              <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 6 }}>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#6ee7b7", letterSpacing: 0.6 }}>
                  PIPELINE × {p.pipeline_boost.toFixed(2)}
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#fbbf24", letterSpacing: 0.6 }}>
                  RYKTE +{p.reputation_bump}
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.45)", letterSpacing: 0.6 }}>
                  · {p.duration_weeks} v
                </span>
                <span style={{ flex: 1 }} />
                <button
                  onClick={() => buy(p)}
                  disabled={busy !== null}
                  style={{
                    ...btnPrimary,
                    opacity: busy === p.key ? 0.6 : 1,
                  }}
                >
                  {busy === p.key ? "Köper…" : "Köp paket →"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
