/**
 * BizBank · företagskontot, separat från privat.
 *
 * Matchar proposals/vol-7 p-biz-bank (rad 7144-7219). Layout:
 *   1. actor-back + actor-head (rubrik · "Företagskonto — separat
 *      från privat" · meta saldo + senaste rörelse + F-skatt)
 *   2. acct-grid med 3 konton (företagskonto · skattekonto · buffert)
 *   3. act-grid · vänster: kontoutdrag senaste 30 dgr (tx-list);
 *      höger aside: 3 side-cards (egen lön / moms varning / privat-vs-biz)
 *   4. peda-block · "Företagsbanken är juridiskt obligatorisk"
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { bizApi, type BizBankOverview } from "./api";
import { BizActorShell } from "./BizActorShell";
import "./biz.css";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};


export function BizBank() {
  useEffect(() => {
    document.body.setAttribute("data-mode", "business");
  }, []);

  const [data, setData] = useState<BizBankOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bizApi
      .bankOverview()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error) {
    return (
      <BizActorShell
        pillLabel="Aktör · biz · Banken (företag)"
        title={<>Företagskonto.</>}
      >
        <div className="biz-error">{error}</div>
      </BizActorShell>
    );
  }

  if (!data) {
    return (
      <BizActorShell
        pillLabel="Aktör · biz · Banken (företag)"
        title={<>Laddar.</>}
      >
        <div className="biz-empty">Laddar bank-data…</div>
      </BizActorShell>
    );
  }

  const primaryAcct = data.accounts.find((a) => a.is_primary)
    ?? data.accounts[0];
  const lastTxDate = data.transactions[0]?.occurred_on;

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Banken (företag)"
      title={
        <>
          Företagskonto — <em>separat från privat</em>.
        </>
      }
      subtitle={
        <>
          {primaryAcct?.name || "Företagskonto"} · separat från ditt
          privatkonto · obligatoriskt enligt skattelagen
        </>
      }
      meta={
        <>
          Saldo: <strong>{SEK(primaryAcct?.balance || 0)} kr</strong>
          <br />
          Senaste rörelse:{" "}
          <strong>
            {lastTxDate ? SHORT_DATE(lastTxDate) : "ingen"}
          </strong>
          <br />
          {data.next_vat_due ? (
            <>
              Moms {data.next_vat_due}:{" "}
              <strong style={{ color: "#fbbf24" }}>
                −{SEK(data.next_vat_amount)} kr
              </strong>
            </>
          ) : (
            <>
              F-skatt prognos: <strong>—</strong>
            </>
          )}
        </>
      }
    >
      {/* === 3-konto-grid === */}
      <div className="acct-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {data.accounts.map((acc) => (
          <a
            key={acc.eye}
            href="#"
            className="acct"
            onClick={(e) => e.preventDefault()}
          >
            <div>
              <div className="acct-eye">{acc.eye}</div>
              <div className="acct-name">{acc.name}</div>
              <div className="acct-num">{acc.number}</div>
            </div>
            <div>
              <div className="acct-bal">
                {acc.is_primary ? (
                  <em>{SEK(acc.balance)}</em>
                ) : (
                  SEK(acc.balance)
                )}{" "}
                kr
              </div>
              <div className="acct-bal-meta">{acc.balance_meta}</div>
            </div>
          </a>
        ))}
      </div>

      {/* === act-grid: kontoutdrag + aside === */}
      <div className="act-grid" style={{ marginTop: 22 }}>
        <div>
          <div className="section-eye">
            Företagsbankens kontoutdrag · senaste 30 dgr
          </div>
          {data.transactions.length === 0 ? (
            <div className="biz-empty">
              Inga rörelser senaste 30 dgr. Skapa en kund-faktura och markera
              som betald — eller registrera en utgift — för att se
              transaktioner här.
            </div>
          ) : (
            <div className="tx-list">
              {data.transactions.map((tx, idx) => (
                <div
                  key={idx}
                  className="tx-row"
                  style={{
                    gridTemplateColumns: "70px 1fr 100px 100px",
                  }}
                >
                  <span className="tx-date">{SHORT_DATE(tx.occurred_on)}</span>
                  <div>
                    <div className="tx-name">{tx.name}</div>
                    {tx.name_sub && (
                      <div className="tx-name-sub">{tx.name_sub}</div>
                    )}
                  </div>
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: tx.is_income
                        ? "#6ee7b7"
                        : tx.is_owner_salary
                        ? "#fbbf24"
                        : "rgba(255,255,255,0.55)",
                    }}
                  >
                    {tx.category}
                  </span>
                  <span
                    className={`tx-amt${tx.is_income ? " in" : ""}`}
                    style={{
                      fontStyle: tx.is_income ? "italic" : "normal",
                    }}
                  >
                    {tx.is_income ? "+ " : ""}
                    {SEK(tx.amount_signed)} kr
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <aside>
          {/* Egen lön · indigo accent */}
          <div
            className="side-card"
            style={{ borderColor: "rgba(99,102,241,0.25)" }}
          >
            <div
              className="side-card-eye"
              style={{ color: "#c7d2fe" }}
            >
              Egen lön denna mån
            </div>
            <div className="side-card-h">
              {SEK(data.own_salary_this_month)} kr <em>uttag</em>
            </div>
            <div className="side-card-meta">
              Du tar ut det du behöver. Ingen arbetsgivaravgift. Privatskatt på
              överskott vid årsskifte.
            </div>
          </div>

          {/* Moms · accent när det finns ett kommande VAT-due */}
          {data.next_vat_due && data.next_vat_amount > 0 && (
            <div
              className="side-card"
              style={{
                background: "rgba(220, 76, 43, 0.06)",
                borderColor: "rgba(220, 76, 43, 0.25)",
              }}
            >
              <div
                className="side-card-eye"
                style={{ color: "#dc4c2b" }}
              >
                Moms {data.next_vat_due}
              </div>
              <div className="side-card-h">
                −{SEK(data.next_vat_amount)} kr
              </div>
              <div className="side-card-meta">
                Är du säker att du har för det? Företagskontot går från{" "}
                {SEK(primaryAcct?.balance || 0)} →{" "}
                {SEK((primaryAcct?.balance || 0) - data.next_vat_amount)}.
              </div>
              <Link to="/v2/foretag/moms" className="side-card-link">
                Se skatte-vyn ↗
              </Link>
            </div>
          )}

          {/* Företag vs privat */}
          <div className="side-card">
            <div className="side-card-eye">Företag vs privat</div>
            <div className="side-card-h">
              Två separata <em>böcker</em>
            </div>
            <div className="side-card-meta">
              Aldrig blanda. Privata köp på företagskontot = bokföringsfel.
              Egen lön är överföring, inte privatkostnad.
            </div>
            <a
              href="#"
              className="side-card-link"
              onClick={(e) => {
                e.preventDefault();
                // Trigga mode-switch (samma mekanism som V2Topbar)
                try {
                  localStorage.setItem("hb_company_mode", "private");
                  window.dispatchEvent(
                    new CustomEvent("company-mode-changed", {
                      detail: "private",
                    }),
                  );
                  document.body.setAttribute("data-mode", "private");
                  // Navigera till privat hub
                  window.location.assign("/v2/hub");
                } catch {
                  /* fail-soft */
                }
              }}
            >
              Byt till privat ↻
            </a>
          </div>
        </aside>
      </div>

      {/* === Pedagogik-block === */}
      <div className="peda" style={{ borderLeftColor: "#a5b4fc" }}>
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Företagsbanken är <em>juridiskt obligatorisk</em>.
        </div>
        <p className="peda-prose">
          Lagen säger att företagspengar och privata pengar måste vara i
          separata konton. Att blanda är inte bara slarvigt — det är skattefel
          som kan ge straffavgift. Egen lön är en <em>överföring</em>, inte en
          kostnad i företaget. Och företagets resultat slut-beskattas hos dig
          privat vid årsskiftet.
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>Företagskonto</strong>Obligatoriskt för enskild firma + AB.
            Banken vet om f-skatt-koll.
          </li>
          <li>
            <strong>Egen lön</strong>Inte en kostnad. Överföring privat. Ingen
            arbetsgivaravgift.
          </li>
          <li>
            <strong>Egen insättning</strong>Privata pengar in i firma. Bokförs
            som eget kapital.
          </li>
          <li>
            <strong>Skattekontot</strong>Skatteverkets eget konto för dig som
            företagare. Allt går in.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">Företagskonto</span>
          <span className="peda-concept">Skattekonto</span>
          <span className="peda-concept">Egen lön</span>
          <span className="peda-concept">Eget kapital</span>
          <span className="peda-concept">Resultatöverföring</span>
        </div>
        <div className="peda-tip">
          När du flippar tillbaka till privat — egen lön{" "}
          {SEK(data.own_salary_this_month)} dyker upp på ditt privatkonto. Det
          är samma pengar, två konton, två bokföringar. Pentagon påverkas inte
          direkt — utan på årsbasis när överskottet beskattas.
        </div>
      </div>
    </BizActorShell>
  );
}
