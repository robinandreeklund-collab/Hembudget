/**
 * V2 Skatten · matchar /proposals/vol-7/elev.html#p-skatt EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · "Aktör 03 · Skatteverket · deadline X maj"-pill +
 *      h1 "Skatteverket — förifyllt" + sub + actor-meta (Bruttoinkomst /
 *      Förskottsinbetald skatt / Prognos: + N kr tillbaka)
 *   3. .cta-card · "Förslag att granska" (om det finns ett förslag) med
 *      Godkänn/Avvisa-knappar
 *   4. .section-eye + .tx-list · 6 rader (Inkomst / Avdrag / Kapital /
 *      Förslag / Slutlig skatt / Återbäring eller Kvarskatt)
 *   5. .peda · pedagogik-block med 4 bullets + 6 koncept-pills
 *
 * All data hämtas via /v2/skatten — riktig data räknat från
 * StudentProfile + scope-DB.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type TaxData, type V2TaxLineItem } from "./api";
import { V2Banner } from "./V2Banner";
import "./skatten.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "long" });
};

function formatAmount(amt: number): string {
  if (amt > 0) return `${SEK(amt)} kr`;
  if (amt < 0) return `−${SEK(Math.abs(amt))} kr`;
  return "0 kr";
}

function categoryLabel(item: V2TaxLineItem): string {
  return item.label;
}

export function SkattenV2() {
  const [data, setData] = useState<TaxData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Lokal state för granskade förslag — när eleven godkänner/avvisar
  // ett förslag drar vi bort raden visuellt. Servern tar emot detta i
  // en framtida PATCH-endpoint; tills vidare är det visuellt.
  const [decisions, setDecisions] = useState<Record<string, "approved" | "rejected">>({});
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .skatten()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

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

  const { items, year, deadline, gross_income, prelim_tax_paid, diff } = data;
  const proposals = items.filter(
    (i) => i.is_proposal && (!i.proposal_id || decisions[i.proposal_id] !== "rejected"),
  );
  const firstProposal = proposals.find(
    (p) => !p.proposal_id || decisions[p.proposal_id] !== "approved",
  );

  // Filtrera ut avvisade förslag från visning
  const visibleItems = items.filter((i) => {
    if (i.is_proposal && i.proposal_id && decisions[i.proposal_id] === "rejected") {
      return false;
    }
    return true;
  });

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

        {/* CTA · första pågående förslaget */}
        {firstProposal && (
          <article className="cta-card">
            <div className="cta-eye">Förslag att granska</div>
            <div className="cta-h">
              {firstProposal.name.replace(/\s*·\s*förslag$/i, "")} —{" "}
              <em>+ {SEK(Math.abs(firstProposal.amount))} kr</em>
              {firstProposal.amount < 0 ? " i återbäring" : ""}.
            </div>
            <p className="cta-prose">
              Skatteverket föreslår: {firstProposal.detail}. Beloppet på{" "}
              <strong>{SEK(Math.abs(firstProposal.amount))} kr</strong>{" "}
              {firstProposal.amount < 0
                ? "minskar skatten"
                : "ökar skatten"}
              . Godkänn eller avvisa förslaget — siffrorna räknas om i
              realtid.
            </p>
            <button
              type="button"
              className="cta-btn"
              onClick={() => {
                if (firstProposal.proposal_id) {
                  setDecisions((d) => ({
                    ...d,
                    [firstProposal.proposal_id!]: "approved",
                  }));
                }
              }}
            >
              Godkänn förslaget
            </button>
            <button
              type="button"
              className="cta-btn ghost"
              onClick={() => {
                if (firstProposal.proposal_id) {
                  setDecisions((d) => ({
                    ...d,
                    [firstProposal.proposal_id!]: "rejected",
                  }));
                }
              }}
            >
              Avvisa
            </button>
          </article>
        )}

        {/* Förifyllt underlag · 6 rader */}
        <div className="section-eye">Förifyllt underlag</div>
        <div className="tx-list">
          {visibleItems.map((item, idx) => {
            const isProposal = item.is_proposal;
            const isDiff = item.category === "diff";
            const rowClass =
              isProposal && (!item.proposal_id || decisions[item.proposal_id] !== "approved")
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
            const catClass =
              isProposal && (!item.proposal_id || decisions[item.proposal_id] !== "approved")
                ? " unset"
                : "";
            const amtClass = item.amount > 0 ? " in" : "";
            const showEm = isProposal || isDiff;

            return (
              <div className={`tx-row${rowClass}`} key={idx}>
                <span className="tx-date">{categoryLabel(item)}</span>
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
                  {isProposal && (!item.proposal_id || decisions[item.proposal_id] !== "approved")
                    ? "Granska"
                    : catLabel}
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
            <code>dubbel bosättning</code>,{" "}
            <code>förlust på värdepapper</code>, <code>ROT/RUT</code> — alla
            är <em>förhandlingar</em> mellan dig och Skatteverket. Den
            förifyllda blanketten är ett <strong>förslag</strong>, inte ett
            facit. Du har plikt att läsa den och säga emot om något saknas
            eller är fel.
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
              <strong>Schablonintäkt ISK</strong>Liten kapitalskatt på
              underlaget. Räknas själv av Skatteverket.
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
            Klicka "Godkänn förslaget" — då ser du skatteposten flytta sig
            och slutskatten räknas om i realtid. Det är så du{" "}
            <em>känner</em> att skatten faktiskt rör sig efter dina val.
          </div>
        </div>
      </div>
    </div>
  );
}
