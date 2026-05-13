/**
 * V2 Försäkringar · Aktör 06 · matchar prototyp-design.
 *
 * RIKTIG DATA · ingen mockup:
 * - GET /v2/forsakringar — policies + claims + summary med
 *   coverage_gaps räknat dynamiskt från StudentProfile
 * - POST /v2/forsakringar/policies — eleven skapar egen
 * - PATCH /v2/forsakringar/policies/{id}/status — aktivera/avbryt
 * - DELETE /v2/forsakringar/policies/{id}
 *
 * Wellbeing-effekter:
 * - Aktiv hemförsäkring → +5 safety
 * - 3+ aktiva → +3 safety
 * - Total premie > 700/mån → -economy (kostar i nuet)
 * - Skada paid → +safety (försäkring fungerade)
 * - Oskyddad händelse → -safety (kostar)
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2InsuranceData,
  type V2InsurancePolicyOut,
  type V2InsuranceStatus,
  type V2InsurancePolicyKind,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const KIND_LABEL: Record<V2InsurancePolicyKind, string> = {
  hem: "Hemförsäkring",
  olycksfall: "Olycksfall",
  liv: "Liv",
  barnforsakring: "Barnförsäkring",
  bostadsrattsforsakring: "Bostadsrätt",
  bilforsakring: "Bil",
  djur: "Djur",
  frisktandvard: "Frisktandvård",
  ovrig: "Övrig",
};

const STATUS_LABEL: Record<V2InsuranceStatus, string> = {
  active: "Aktiv",
  considered: "Övervägs",
  cancelled: "Avbruten",
};

type FrisktandvardOffer = {
  tier: number;
  age_category: "atb" | "normal";
  premium_monthly: number;
  explanation: string;
  tier_prices_atb: Record<number, number>;
  tier_prices_normal: Record<number, number>;
  already_active: boolean;
};

export function ForsakringarV2() {
  const [data, setData] = useState<V2InsuranceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Skapa-policy-form
  const [addOpen, setAddOpen] = useState(false);
  const [provider, setProvider] = useState("");
  const [policyName, setPolicyName] = useState("");
  const [policyKind, setPolicyKind] = useState<V2InsurancePolicyKind>("hem");
  const [premium, setPremium] = useState("");
  const [coverage, setCoverage] = useState("");
  const [deductible, setDeductible] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Frisktandvård-offert (SKV-4)
  const [ftvOffer, setFtvOffer] = useState<FrisktandvardOffer | null>(null);
  const [ftvBusy, setFtvBusy] = useState(false);
  const [ftvError, setFtvError] = useState<string | null>(null);

  async function loadFtvOffer() {
    setFtvError(null);
    setFtvBusy(true);
    try {
      const offer = await v2Api.frisktandvardOffer();
      setFtvOffer(offer);
    } catch (e) {
      setFtvError(String((e as Error)?.message || e));
    } finally {
      setFtvBusy(false);
    }
  }

  async function activateFtv() {
    if (!ftvOffer) return;
    setFtvBusy(true);
    try {
      // Hitta existerande considered-policy (från default-seed)
      const existing = (data?.policies || []).find(
        (p) => p.kind === "frisktandvard",
      );
      if (existing) {
        await v2Api.insuranceUpdateStatus(existing.id, "active");
      } else {
        await v2Api.insuranceCreatePolicy({
          provider: "Folktandvården",
          name: `Frisktandvård · grupp ${ftvOffer.tier}`,
          kind: "frisktandvard",
          premium_monthly: ftvOffer.premium_monthly,
          autogiro: true,
          status: "active",
          started_on: new Date().toISOString().slice(0, 10),
          notes: (
            `Prisgrupp ${ftvOffer.tier} (${ftvOffer.age_category}). ` +
            `Täcker karieskontroll, lagningar, tandstensborttagning, ` +
            `rotfyllning hos Folktandvården. 3-årsavtal.`
          ),
        });
      }
      setFtvOffer(null);
      await refresh();
    } catch (e) {
      setFtvError(String((e as Error)?.message || e));
    } finally {
      setFtvBusy(false);
    }
  }

  function refresh(): Promise<void> {
    return v2Api
      .forsakringar()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function changeStatus(p: V2InsurancePolicyOut, status: V2InsuranceStatus) {
    try {
      await v2Api.insuranceUpdateStatus(p.id, status);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function deletePolicy(p: V2InsurancePolicyOut) {
    if (!confirm(`Ta bort försäkringen "${p.name}"?`)) return;
    try {
      await v2Api.insuranceDeletePolicy(p.id);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function createPolicy() {
    setSubmitError(null);
    if (!provider.trim() || !policyName.trim()) {
      setSubmitError("Ange försäkringsbolag och namn");
      return;
    }
    const prem = parseFloat(premium.replace(/\s/g, "").replace(",", "."));
    if (isNaN(prem) || prem < 0) {
      setSubmitError("Ange giltig premie kr/mån");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.insuranceCreatePolicy({
        provider: provider.trim(),
        name: policyName.trim(),
        kind: policyKind,
        premium_monthly: prem,
        coverage_amount: coverage
          ? parseFloat(coverage.replace(/\s/g, "").replace(",", "."))
          : undefined,
        deductible: deductible
          ? parseFloat(deductible.replace(/\s/g, "").replace(",", "."))
          : undefined,
        status: "considered",
      });
      setProvider("");
      setPolicyName("");
      setPremium("");
      setCoverage("");
      setDeductible("");
      setAddOpen(false);
      await refresh();
    } catch (e) {
      setSubmitError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda försäkringar
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
        <div className="bank-loading">Laddar försäkringar…</div>
      </div>
    );
  }

  const { summary, policies, claims } = data;
  const active = policies.filter((p) => p.status === "active");

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/v2/hub");
          }}
          href="#"
        >
          Tillbaka till pentagonen
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 06 · Försäkringar</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {summary.active_count > 0
                ? `${summary.active_count} aktiva försäkringar`
                : "Inga aktiva försäkringar än"}
            </h1>
            <p className="actor-sub">
              Hem · olycksfall · liv · boende ·{" "}
              {SEK(summary.total_premium_monthly)} kr/mån i premie
            </p>
          </div>
          <div className="actor-meta">
            Premie/mån: <strong>{SEK(summary.total_premium_monthly)} kr</strong>
            <br />
            Total täckning:{" "}
            <strong>{SEK(summary.total_coverage)} kr</strong>
            <br />
            Skadehändelser 12m: <strong>{summary.claims_paid_12m}</strong>{" "}
            ersatta
          </div>
        </header>

        {/* COVERAGE GAPS · varning */}
        {summary.coverage_gaps.length > 0 && (
          <div
            style={{
              background: "rgba(220,76,43,0.06)",
              border: "1px solid rgba(220,76,43,0.4)",
              borderRadius: 6,
              padding: "16px 20px",
              marginBottom: 22,
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "var(--accent)",
                marginBottom: 10,
              }}
            >
              ● Skydd som saknas
            </div>
            <ul
              style={{
                margin: 0,
                paddingLeft: 20,
                fontFamily: "var(--serif)",
                fontSize: 14,
                lineHeight: 1.6,
                color: "var(--text)",
              }}
            >
              {summary.coverage_gaps.map((g, idx) => (
                <li key={idx}>{g}</li>
              ))}
            </ul>
          </div>
        )}

        {/* === SKV-4 · Frisktandvård CTA === */}
        {!policies.some(
          (p) => p.kind === "frisktandvard" && p.status === "active",
        ) && (
          <div
            style={{
              marginTop: 20, marginBottom: 14,
              padding: 18,
              background: "linear-gradient(135deg, rgba(110,231,183,0.08), rgba(15,21,37,0.55))",
              border: "1px solid rgba(110,231,183,0.30)",
              borderRadius: 10,
              display: "flex",
              gap: 18,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <div style={{ flex: 1, minWidth: 280 }}>
              <div style={{
                fontFamily: "JetBrains Mono, monospace", fontSize: 10,
                fontWeight: 700, color: "#6ee7b7", letterSpacing: 1.4,
              }}>
                ● FOLKTANDVÅRDEN · NY TJÄNST
              </div>
              <div style={{
                fontFamily: "Source Serif 4, Georgia, serif", fontSize: 20,
                fontWeight: 700, color: "#fff", marginTop: 6,
              }}>
                Frisktandvård — fast månadspris
              </div>
              <div style={{
                fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13,
                color: "rgba(255,255,255,0.78)", marginTop: 6, lineHeight: 1.5,
              }}>
                Slipp överraskningar vid stora ingrepp. Premien beror
                på din tandhälsa (grupp 1-10) och ålder (ATB-rabatt
                för 20-23 år och 67+).
              </div>
            </div>
            <button
              onClick={loadFtvOffer}
              disabled={ftvBusy}
              style={{
                background: "rgba(110,231,183,0.20)",
                border: "1px solid rgba(110,231,183,0.45)",
                color: "#6ee7b7",
                padding: "10px 18px",
                borderRadius: 6,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 1.4,
                cursor: ftvBusy ? "default" : "pointer",
                whiteSpace: "nowrap",
              }}
            >
              {ftvBusy ? "..." : "HÄMTA OFFERT →"}
            </button>
          </div>
        )}

        {ftvError && (
          <div style={{
            padding: 10, marginBottom: 10,
            background: "rgba(220,76,43,0.12)",
            border: "1px solid rgba(220,76,43,0.35)",
            borderRadius: 6,
            color: "#fda594",
            fontFamily: "JetBrains Mono, monospace", fontSize: 11,
          }}>
            {ftvError}
          </div>
        )}

        {ftvOffer && (
          <FtvOfferModal
            offer={ftvOffer}
            busy={ftvBusy}
            onActivate={activateFtv}
            onClose={() => setFtvOffer(null)}
          />
        )}

        {/* AKTIVA + ÖVERVÄGDA POLICYS */}
        <div className="acct-grid">
          {policies.length === 0 ? (
            <div
              style={{
                gridColumn: "1 / -1",
                padding: "32px 28px",
                border: "1px solid var(--line)",
                borderRadius: 6,
                fontFamily: "var(--serif)",
                color: "var(--text-mid)",
              }}
            >
              Inga försäkringar registrerade än. Lärare seedar default-
              katalogen eller du skapar egna nedan.
            </div>
          ) : (
            policies.map((p) => (
              <div
                key={p.id}
                className={`acct${p.status === "active" ? " active" : ""}${
                  p.status === "cancelled" ? " warning" : ""
                }`}
              >
                <div>
                  <div className="acct-eye">{p.provider}</div>
                  <div className="acct-name">{p.name}</div>
                  <div className="acct-num">
                    {KIND_LABEL[p.kind]}
                    {p.coverage_amount
                      ? ` · ${SEK(p.coverage_amount)} kr täckning`
                      : ""}
                    {p.deductible
                      ? ` · ${SEK(p.deductible)} självrisk`
                      : ""}
                  </div>
                </div>
                <div>
                  <div
                    className="acct-bal"
                    style={{
                      color:
                        p.status === "active"
                          ? "var(--warm)"
                          : "var(--text-dim)",
                    }}
                  >
                    {p.status === "active" ? (
                      <em>{SEK(p.premium_monthly)}</em>
                    ) : (
                      SEK(p.premium_monthly)
                    )}{" "}
                    kr/mån
                  </div>
                  <div className="acct-bal-meta">
                    {STATUS_LABEL[p.status]}
                    {p.status === "active" && p.autogiro
                      ? " · autogiro"
                      : ""}
                  </div>
                  <div
                    style={{
                      marginTop: 8,
                      display: "flex",
                      gap: 4,
                      justifyContent: "flex-end",
                      flexWrap: "wrap",
                    }}
                  >
                    {p.status !== "active" && (
                      <button
                        type="button"
                        onClick={() => changeStatus(p, "active")}
                        style={miniBtn("var(--warm)")}
                      >
                        Aktivera
                      </button>
                    )}
                    {p.status === "active" && (
                      <button
                        type="button"
                        onClick={() => changeStatus(p, "cancelled")}
                        style={miniBtn("rgba(255,255,255,0.4)")}
                      >
                        Avbryt
                      </button>
                    )}
                    {p.status === "cancelled" && (
                      <button
                        type="button"
                        onClick={() => changeStatus(p, "considered")}
                        style={miniBtn("rgba(255,255,255,0.4)")}
                      >
                        Återöppna
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => deletePolicy(p)}
                      style={miniBtn("rgba(255,255,255,0.3)")}
                    >
                      Ta bort
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* LÄGG TILL POLICY */}
        <div style={{ marginTop: 18 }}>
          {!addOpen ? (
            <button
              type="button"
              className="cta-btn ghost"
              onClick={() => setAddOpen(true)}
            >
              + Lägg till försäkring
            </button>
          ) : (
            <div
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "18px 22px",
                marginBottom: 22,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "1.4px",
                  textTransform: "uppercase",
                  color: "var(--warm)",
                  marginBottom: 12,
                }}
              >
                ● Lägg till försäkring
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 140px",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <input
                  placeholder="Försäkringsbolag (t.ex. Folksam)"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  placeholder="Namn (t.ex. Hemförsäkring)"
                  value={policyName}
                  onChange={(e) => setPolicyName(e.target.value)}
                  style={inputStyle()}
                />
                <select
                  value={policyKind}
                  onChange={(e) =>
                    setPolicyKind(e.target.value as V2InsurancePolicyKind)
                  }
                  style={inputStyle()}
                >
                  {(
                    Object.keys(KIND_LABEL) as V2InsurancePolicyKind[]
                  ).map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]}
                    </option>
                  ))}
                </select>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <input
                  type="number"
                  placeholder="Premie kr/mån"
                  value={premium}
                  onChange={(e) => setPremium(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Täckning kr (valfritt)"
                  value={coverage}
                  onChange={(e) => setCoverage(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Självrisk kr (valfritt)"
                  value={deductible}
                  onChange={(e) => setDeductible(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              {submitError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {submitError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={submitting}
                onClick={createPolicy}
                style={{ marginRight: 8 }}
              >
                {submitting ? "Sparar…" : "Spara försäkring"}
              </button>
              <button
                type="button"
                className="cta-btn ghost"
                onClick={() => setAddOpen(false)}
              >
                Avbryt
              </button>
            </div>
          )}
        </div>

        {/* SKADEHÄNDELSER */}
        <div className="section-eye" style={{ marginTop: 32 }}>
          Försäkringshändelser · senaste 12 mån
        </div>
        {claims.length === 0 ? (
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
            Inga skadehändelser registrerade. Läraren simulerar
            scenarier (cykel-stöld, vattenskada osv) som påverkar
            wellbeing-pentagonen direkt.
          </div>
        ) : (
          <div className="biz-table" style={{ marginBottom: 22 }}>
            <div
              className="biz-table-row head"
              style={{
                gridTemplateColumns: "100px 1.4fr 130px 100px 110px",
              }}
            >
              <span>Datum</span>
              <span>Händelse</span>
              <span>Status</span>
              <span>Yrkat</span>
              <span>Utbetalt</span>
            </div>
            {claims.map((c) => (
              <div
                className={`biz-table-row${c.no_policy ? " open-row" : ""}`}
                key={c.id}
                style={{
                  gridTemplateColumns: "100px 1.4fr 130px 100px 110px",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                  }}
                >
                  {SHORT_DATE(c.occurred_on)}
                </span>
                <div>
                  <div className="biz-factor-name">
                    {c.title}
                    {c.no_policy && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontFamily: "var(--mono)",
                          fontSize: 9,
                          color: "var(--accent)",
                          letterSpacing: "1.2px",
                          textTransform: "uppercase",
                          padding: "2px 6px",
                          border: "1px solid rgba(220,76,43,0.4)",
                          borderRadius: 100,
                        }}
                      >
                        Oskyddad
                      </span>
                    )}
                  </div>
                  <div className="biz-factor-detail">
                    {c.description ||
                      (c.policy_name
                        ? `Täckt av ${c.policy_name}`
                        : "Ingen aktiv försäkring täckte händelsen")}
                  </div>
                </div>
                <span
                  className={`biz-status ${
                    c.status === "paid"
                      ? "delta-up"
                      : c.status === "denied"
                      ? "delta-down"
                      : "open"
                  }`}
                >
                  {c.status}
                </span>
                <span
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13,
                    color: "var(--text-mid)",
                  }}
                >
                  {c.amount_claimed != null
                    ? `${SEK(c.amount_claimed)} kr`
                    : "—"}
                </span>
                <span
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13,
                    color: c.amount_paid && c.amount_paid > 0
                      ? "#6ee7b7"
                      : "var(--text-mid)",
                  }}
                >
                  {c.amount_paid != null && c.amount_paid > 0
                    ? `+ ${SEK(c.amount_paid)} kr`
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ASIDE-CARDS */}
        <div className="act-grid">
          <div></div>
          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                {active.length === 0 ? (
                  <>
                    Hemförsäkring <em>saknas</em>
                  </>
                ) : (
                  <>
                    {active.length} aktiva = <em>+ trygghet</em>
                  </>
                )}
              </div>
              <div className="side-card-meta">
                Aktiv hemförsäkring +5 safety. 3+ försäkringar +3 safety.
                Höga premier (&gt; 700/mån) -economy. Synligt i pentagonen.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Premie-belastning</div>
              <div className="side-card-h">
                {SEK(summary.total_premium_monthly)} kr/mån
              </div>
              <div className="side-card-meta">
                Snitt för ung vuxen är ~ 320 kr/mån. Bundling Hem +
                Olycksfall hos samma bolag ger ofta 30-50 kr/mån i rabatt.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Försäkring är <em>risköverföring</em>
              </div>
              <div className="side-card-meta">
                Eleven betalar premie för att slippa bära fulla risken
                själv. När en oskyddad händelse inträffar känns det
                direkt — pentagon-axeln sjunker.
              </div>
            </div>
          </aside>
        </div>

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Försäkring är <em>risköverföring</em>.
          </div>
          <p className="peda-prose">
            Du betalar 320 kr/mån för att <em>någon annan</em> tar risken
            vid skada. Hemförsäkring är obligatorisk om du har bohag att
            skydda — utan blir 200 000 kr lösegendom din egen risk.
            Olycksfall = sjukvårdskostnader om du faller. Liv = ekonomisk
            trygghet för efterlevande. Bostadsrätt är en separat — bara för
            bostadsrättshavare.
          </p>
          <ul className="peda-bullets">
            <li className="peda-bullet">
              <strong>Premie</strong>Det du betalar varje månad för
              försäkringsskydd.
            </li>
            <li className="peda-bullet">
              <strong>Självrisk</strong>Ditt eget belopp innan försäkring
              tar över.
            </li>
            <li className="peda-bullet">
              <strong>Skadeanmälan</strong>Snabbt = bättre. Bilder hjälper.
            </li>
            <li className="peda-bullet">
              <strong>Allrisk</strong>Tillval · täcker även "saker du
              tappar". Värd det?
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Premie</span>
            <span className="peda-concept">Självrisk</span>
            <span className="peda-concept">Aktsamhetskrav</span>
            <span className="peda-concept">Skadeanmälan</span>
            <span className="peda-concept">Allrisk</span>
            <span className="peda-concept">Risk-pool</span>
          </div>
          <div className="peda-tip">
            Aktivera en "Övervägs"-försäkring och se hur safety-axeln i
            pentagonen reagerar. Bundling (Hem + Olycksfall hos samma
            bolag) sparar pengar — men räkna på enskilda kostnader också.
          </div>
        </div>
      </div>
    </div>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    background: "rgba(255, 255, 255, 0.04)",
    border: "1px solid var(--line-strong)",
    color: "#fff",
    padding: "8px 12px",
    borderRadius: 4,
    fontFamily: "var(--mono)",
    fontSize: 12.5,
    width: "100%",
  };
}

function miniBtn(color: string): React.CSSProperties {
  return {
    background: "transparent",
    border: `1px solid ${color}`,
    color,
    padding: "4px 10px",
    borderRadius: 100,
    fontFamily: "var(--mono)",
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.6px",
    textTransform: "uppercase",
    cursor: "pointer",
  };
}


// === SKV-4 · Frisktandvård-offert-modal ===

function FtvOfferModal({
  offer, busy, onActivate, onClose,
}: {
  offer: FrisktandvardOffer;
  busy: boolean;
  onActivate: () => void;
  onClose: () => void;
}) {
  const myPrices = offer.age_category === "atb"
    ? offer.tier_prices_atb
    : offer.tier_prices_normal;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.65)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "linear-gradient(180deg, #0f1525, #0a0e1a)",
          border: "1px solid rgba(110,231,183,0.30)",
          borderRadius: 12,
          padding: 28,
          maxWidth: 640,
          width: "100%",
          maxHeight: "90vh",
          overflow: "auto",
        }}
      >
        <div style={{
          fontFamily: "JetBrains Mono, monospace", fontSize: 10,
          fontWeight: 700, color: "#6ee7b7", letterSpacing: 1.4,
        }}>
          ● DIN PERSONLIGA OFFERT
        </div>
        <h2 style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 24, fontWeight: 700, color: "#fff",
          margin: "8px 0 16px",
        }}>
          Frisktandvård · grupp {offer.tier} ·{" "}
          <em style={{ color: "#6ee7b7", fontStyle: "italic" }}>
            {offer.premium_monthly} kr/mån
          </em>
        </h2>

        <div style={{
          fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14,
          color: "rgba(255,255,255,0.85)", lineHeight: 1.6,
          whiteSpace: "pre-line",
          marginBottom: 20,
        }}>
          {offer.explanation}
        </div>

        {/* Pristabell */}
        <div style={{
          background: "rgba(15,21,37,0.55)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 8,
          padding: 14,
          marginBottom: 20,
        }}>
          <div style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 10,
            fontWeight: 700, color: "#c7d2fe", letterSpacing: 1.4,
            marginBottom: 10,
          }}>
            ● HELA PRISTABELLEN ({offer.age_category === "atb" ? "ATB-rabatt" : "normal-ålder"})
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(5, 1fr)",
            gap: 6,
            fontFamily: "JetBrains Mono, monospace", fontSize: 11,
          }}>
            {Object.entries(myPrices).map(([tier, price]) => {
              const isMine = parseInt(tier, 10) === offer.tier;
              return (
                <div key={tier} style={{
                  padding: 8,
                  borderRadius: 4,
                  background: isMine
                    ? "rgba(110,231,183,0.18)"
                    : "rgba(255,255,255,0.03)",
                  border: `1px solid ${isMine ? "rgba(110,231,183,0.45)" : "rgba(255,255,255,0.08)"}`,
                  textAlign: "center",
                }}>
                  <div style={{
                    color: isMine ? "#6ee7b7" : "rgba(255,255,255,0.50)",
                    fontSize: 9, fontWeight: 700, letterSpacing: 0.8,
                  }}>
                    GRUPP {tier}
                  </div>
                  <div style={{
                    color: isMine ? "#fff" : "rgba(255,255,255,0.85)",
                    fontWeight: 700, marginTop: 3,
                  }}>
                    {price} kr
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {offer.already_active ? (
          <div style={{
            padding: 12,
            background: "rgba(110,231,183,0.10)",
            border: "1px solid rgba(110,231,183,0.30)",
            borderRadius: 6,
            color: "#6ee7b7",
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13,
            marginBottom: 12,
          }}>
            ✓ Du har redan ett aktivt frisktandvårdsavtal · ingen åtgärd behövs.
          </div>
        ) : null}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.20)",
              color: "rgba(255,255,255,0.65)",
              padding: "10px 18px",
              borderRadius: 6,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 1.4,
              cursor: "pointer",
            }}
          >
            STÄNG
          </button>
          {!offer.already_active && (
            <button
              onClick={onActivate}
              disabled={busy}
              style={{
                background: "rgba(110,231,183,0.20)",
                border: "1px solid rgba(110,231,183,0.45)",
                color: "#6ee7b7",
                padding: "10px 22px",
                borderRadius: 6,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 1.4,
                cursor: busy ? "default" : "pointer",
              }}
            >
              {busy ? "AKTIVERAR..." : `AKTIVERA · ${offer.premium_monthly} KR/MÅN →`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
