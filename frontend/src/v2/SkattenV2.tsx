/**
 * V2 Skatten · matchar /proposals/vol-7/elev.html#p-skatt EXAKT.
 *
 * RIKTIG DATA · ingen mockup:
 * - GET /v2/skatten — items + deductions + proposals + submitted
 * - POST /v2/skatten/deductions — eleven registrerar avdrag
 * - DELETE /v2/skatten/deductions/{id}
 * - POST /v2/skatten/proposals/{id}/decision · approve/reject
 * - POST /v2/skatten/{year}/submit — lämna in deklarationen
 *
 * Wellbeing påverkas automatiskt:
 * - Inlämnad deklaration → +3 economy
 * - Stor återbäring → +safety
 * - Stor kvarskatt → -economy
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type TaxData,
  type V2TaxLineItem,
  type TaxDeductionKind,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./skatten.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "long" });
};

const KIND_LABEL: Record<TaxDeductionKind, string> = {
  rese: "Reseavdrag",
  "bolane-ranta": "Ränteavdrag bolån",
  "csn-ranta": "Ränteavdrag CSN",
  "dubbel-bosattning": "Dubbel bosättning",
  rot: "ROT-avdrag",
  rut: "RUT-avdrag",
  fackavgift: "Fackavgift",
  ovrig: "Övrigt avdrag",
};

function formatAmount(amt: number): string {
  if (amt > 0) return `${SEK(amt)} kr`;
  if (amt < 0) return `−${SEK(Math.abs(amt))} kr`;
  return "0 kr";
}

export function SkattenV2() {
  const [data, setData] = useState<TaxData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Form-state · lägg till avdrag
  const [addOpen, setAddOpen] = useState(false);
  const [addKind, setAddKind] = useState<TaxDeductionKind>("rese");
  const [addName, setAddName] = useState("");
  const [addAmount, setAddAmount] = useState("");
  const [addDescription, setAddDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Submit-state
  const [submittingYear, setSubmittingYear] = useState(false);

  function refresh(): Promise<void> {
    return v2Api
      .skatten()
      .then((d) => setData(d))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function decideProposal(
    proposalId: number,
    decision: "approve" | "reject",
  ) {
    try {
      await v2Api.taxProposalDecision(proposalId, decision);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function submitYear() {
    if (!data) return;
    setSubmittingYear(true);
    try {
      await v2Api.taxSubmitYear(data.year);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmittingYear(false);
    }
  }

  async function addDeduction() {
    setSubmitError(null);
    const amt = parseFloat(addAmount.replace(/\s/g, "").replace(",", "."));
    if (!addName.trim()) {
      setSubmitError("Ange namn");
      return;
    }
    if (isNaN(amt) || amt < 0) {
      setSubmitError("Ange giltigt belopp");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.taxAddDeduction({
        year: data?.year || new Date().getFullYear(),
        kind: addKind,
        name: addName.trim(),
        description: addDescription || undefined,
        amount: amt,
      });
      setAddName("");
      setAddAmount("");
      setAddDescription("");
      setAddOpen(false);
      await refresh();
    } catch (e) {
      setSubmitError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteDeduction(deductionId: number) {
    if (!confirm("Ta bort avdraget?")) return;
    try {
      await v2Api.taxDeleteDeduction(deductionId);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error) {
    return (
      <div className="v2-skatt-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda deklarations-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-skatt-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar deklarations-data…</div>
      </div>
    );
  }

  const {
    items,
    year,
    deadline,
    gross_income,
    prelim_tax_paid,
    diff,
    proposals,
    deductions,
    submitted,
    can_submit,
  } = data;

  const pendingProposals = proposals.filter((p) => p.status === "pending");
  const firstPending = pendingProposals[0];
  const isLocked = submitted?.locked === true;

  return (
    <div className="v2-skatt-root">
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
            <span className="pill">
              Aktör 03 · Skatteverket
              {deadline ? ` · deadline ${SHORT_DATE(deadline)}` : ""}
            </span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Skatteverket — <em>förifyllt</em>.
            </h1>
            <p className="actor-sub">
              Inkomstdeklaration {year} · automatik ·{" "}
              {data.pending_proposal_count > 0
                ? `${data.pending_proposal_count} förslag att granska`
                : isLocked
                ? "deklaration inlämnad"
                : "inga förslag kvar att granska"}
            </p>
          </div>
          <div className="actor-meta">
            Bruttoinkomst <strong>{SEK(gross_income)} kr</strong>
            <br />
            Förskottsinbetald skatt <strong>{SEK(prelim_tax_paid)} kr</strong>
            <br />
            {diff >= 0 ? (
              <>
                Prognos: <strong>+ {SEK(diff)} kr</strong> tillbaka
              </>
            ) : (
              <>
                Prognos: <strong>− {SEK(Math.abs(diff))} kr</strong> kvarskatt
              </>
            )}
          </div>
        </header>

        {/* SUBMITTED-BANNER */}
        {isLocked && submitted && (
          <article
            className="cta-card"
            style={{
              borderColor: "rgba(110,231,183,0.45)",
              background:
                "linear-gradient(135deg, rgba(110,231,183,0.18), rgba(15,21,37,0.5))",
            }}
          >
            <div className="cta-eye" style={{ color: "#6ee7b7" }}>
              ● Deklaration inlämnad
            </div>
            <div className="cta-h">
              {year} är{" "}
              <em style={{ color: "#6ee7b7" }}>låst</em>.{" "}
              {submitted.diff >= 0
                ? `+ ${SEK(submitted.diff)} kr återbäring`
                : `− ${SEK(Math.abs(submitted.diff))} kr kvarskatt`}
              .
            </div>
            <p className="cta-prose">
              Inlämnad{" "}
              {new Date(submitted.submitted_at).toLocaleDateString("sv-SE")}.
              Slutlig skatt {SEK(submitted.final_tax)} kr efter avdrag på{" "}
              {SEK(submitted.deductions_total)} kr. Wellbeing-pentagonen har
              registrerat handlingen.
            </p>
          </article>
        )}

        {/* CTA · första pågående förslaget */}
        {firstPending && !isLocked && (
          <article className="cta-card">
            <div className="cta-eye">Förslag att granska</div>
            <div className="cta-h">
              {firstPending.name} —{" "}
              <em>+ {SEK(Math.round(firstPending.suggested_amount * 0.30))} kr</em>{" "}
              i återbäring.
            </div>
            <p className="cta-prose">
              Skatteverket föreslår: {firstPending.description}. Avdraget på{" "}
              <strong>{SEK(firstPending.suggested_amount)} kr</strong> ger
              30 % skatteeffekt ={" "}
              {SEK(Math.round(firstPending.suggested_amount * 0.30))} kr lägre
              skatt. Godkänn eller avvisa.
            </p>
            <button
              type="button"
              className="cta-btn"
              onClick={() => decideProposal(firstPending.id, "approve")}
            >
              Godkänn förslaget
            </button>
            <button
              type="button"
              className="cta-btn ghost"
              onClick={() => decideProposal(firstPending.id, "reject")}
            >
              Avvisa
            </button>
          </article>
        )}

        {/* DEKLARATIONS-LISTAN */}
        <div className="section-eye">Förifyllt underlag</div>
        <div className="tx-list">
          {items.map((item: V2TaxLineItem, idx: number) => {
            const isProposal = item.is_proposal;
            const isDiff = item.category === "diff";
            const rowClass = isProposal
              ? " proposal-row"
              : isDiff
              ? " diff-row"
              : "";
            const catLabel =
              item.category === "income"
                ? "Tjänst"
                : item.category === "deduction"
                ? "Tjänst"
                : item.category === "capital"
                ? "Kapital"
                : item.category === "tax"
                ? "Skatt"
                : "Tillbaka";
            const catClass = isProposal ? " unset" : "";
            const amtClass = item.amount > 0 ? " in" : "";
            const showEm = isProposal || isDiff;

            return (
              <div className={`tx-row${rowClass}`} key={`${idx}-${item.name}`}>
                <span className="tx-date">{item.label}</span>
                <div>
                  <div className="tx-name">
                    {item.name.includes("förslag") ? (
                      <>
                        {item.name.split("·")[0].trim()} ·{" "}
                        <em>förslag</em>
                      </>
                    ) : (
                      item.name
                    )}
                  </div>
                  <div className="tx-name-sub">{item.detail}</div>
                </div>
                <span className={`tx-cat${catClass}`}>
                  {isProposal ? "Granska" : catLabel}
                </span>
                <span className={`tx-amt${amtClass}`}>
                  {showEm ? (
                    <em>
                      {item.amount >= 0 ? "+ " : "− "}
                      {SEK(Math.abs(item.amount))}
                    </em>
                  ) : (
                    formatAmount(item.amount)
                  )}{" "}
                  {!showEm ? "" : "kr"}
                </span>
              </div>
            );
          })}
        </div>

        {/* AVDRAG · DETALJER + LÄGG TILL */}
        <div className="section-eye">Mina avdrag · {deductions.length} st</div>
        {deductions.length > 0 && (
          <div className="tx-list" style={{ marginBottom: 14 }}>
            {deductions.map((d) => (
              <div className="tx-row" key={`d-${d.id}`}>
                <span className="tx-date">{KIND_LABEL[d.kind as TaxDeductionKind] || d.kind}</span>
                <div>
                  <div className="tx-name">{d.name}</div>
                  <div className="tx-name-sub">
                    {d.description || `Brutto ${SEK(d.amount)} kr`} ·
                    skatteeffekt 30 % = {SEK(Math.round(d.amount * 0.30))} kr
                  </div>
                </div>
                <span className="tx-cat">{d.source === "manual" ? "Egen" : "Förslag"}</span>
                {!isLocked ? (
                  <button
                    type="button"
                    onClick={() => deleteDeduction(d.id)}
                    style={{
                      background: "transparent",
                      border: "1px solid var(--line-strong)",
                      color: "var(--text-mid)",
                      padding: "4px 10px",
                      borderRadius: 100,
                      fontFamily: "var(--mono)",
                      fontSize: 9.5,
                      textTransform: "uppercase",
                      letterSpacing: "0.6px",
                      cursor: "pointer",
                    }}
                  >
                    Ta bort
                  </button>
                ) : (
                  <span className="tx-cat">Låst</span>
                )}
              </div>
            ))}
          </div>
        )}

        {!isLocked && (
          <>
            {!addOpen ? (
              <button
                type="button"
                className="cta-btn ghost"
                onClick={() => setAddOpen(true)}
                style={{ marginBottom: 22 }}
              >
                + Lägg till avdrag
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
                  ● Lägg till avdrag
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 110px",
                    gap: 8,
                    marginBottom: 8,
                  }}
                >
                  <select
                    value={addKind}
                    onChange={(e) =>
                      setAddKind(e.target.value as TaxDeductionKind)
                    }
                    style={inputStyle()}
                  >
                    {(
                      Object.keys(KIND_LABEL) as TaxDeductionKind[]
                    ).map((k) => (
                      <option key={k} value={k}>
                        {KIND_LABEL[k]}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="Namn (t.ex. Vårdförbundet medlemsavgift)"
                    value={addName}
                    onChange={(e) => setAddName(e.target.value)}
                    style={inputStyle()}
                  />
                  <input
                    type="number"
                    placeholder="Belopp"
                    value={addAmount}
                    onChange={(e) => setAddAmount(e.target.value)}
                    style={inputStyle()}
                  />
                </div>
                <input
                  placeholder="Beskrivning (valfritt)"
                  value={addDescription}
                  onChange={(e) => setAddDescription(e.target.value)}
                  style={{ ...inputStyle(), marginBottom: 8 }}
                />
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
                  onClick={addDeduction}
                  style={{ marginRight: 8 }}
                >
                  {submitting ? "Sparar…" : "Spara avdrag"}
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

            {/* LÄMNA IN DEKLARATION */}
            {can_submit && (
              <article className="cta-card">
                <div className="cta-eye">Lämna in deklaration {year}</div>
                <div className="cta-h">
                  Lås det här året när du är{" "}
                  <em>klar med avdrag &amp; förslag</em>.
                </div>
                <p className="cta-prose">
                  När du lämnar in registreras{" "}
                  {diff >= 0
                    ? `+ ${SEK(diff)} kr återbäring`
                    : `− ${SEK(Math.abs(diff))} kr kvarskatt`}{" "}
                  permanent. Wellbeing-pentagonen får + 3 economy om du
                  lämnar in fjolåret i tid.
                </p>
                <button
                  type="button"
                  className="cta-btn"
                  disabled={submittingYear}
                  onClick={submitYear}
                >
                  {submittingYear ? "Lämnar in…" : `Lämna in ${year}`}
                </button>
              </article>
            )}
          </>
        )}

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Skatten är <em>förhandlingsbar</em> — i smågranskningen.
          </div>
          <p className="peda-prose">
            De flesta tror skatten är fast. Den är det inte:{" "}
            <code>ränteavdrag</code> (30 % på räntor under 100k),{" "}
            <code>reseavdrag</code> (om resa &gt; 5 km),{" "}
            <code>dubbel bosättning</code>, <code>förlust på värdepapper</code>,{" "}
            <code>ROT/RUT</code> — alla är <em>förhandlingar</em> mellan dig
            och Skatteverket. Den förifyllda blanketten är ett{" "}
            <strong>förslag</strong>, inte ett facit. Du har plikt att läsa
            den och säga emot om något saknas eller är fel.
          </p>
          <ul className="peda-bullets">
            <li className="peda-bullet">
              <strong>Ränteavdrag</strong>30 % på räntor &lt; 100k · 21 % på
              överskjutande.
            </li>
            <li className="peda-bullet">
              <strong>Jobbskatteavdrag</strong>Steg 1–4 efter inkomst. Sänker
              preliminär.
            </li>
            <li className="peda-bullet">
              <strong>Schablonintäkt ISK</strong>0,89 % på underlaget. Räknas
              automatiskt.
            </li>
            <li className="peda-bullet">
              <strong>Skattekonto</strong>Allt går in. Återbäring eller
              kvarskatt = differens.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Inkomstdeklaration</span>
            <span className="peda-concept">Förifyllt underlag</span>
            <span className="peda-concept">Avdrag</span>
            <span className="peda-concept">Kvarskatt</span>
            <span className="peda-concept">Återbäring</span>
            <span className="peda-concept">Kontrolluppgift</span>
          </div>
          <div className="peda-tip">
            Klicka "Godkänn förslaget" — då skapas en TaxDeduction kopplad
            till förslaget och slutskatten räknas om i realtid. Sedan
            "Lämna in" — och pentagonens economy-axel reagerar direkt.
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
