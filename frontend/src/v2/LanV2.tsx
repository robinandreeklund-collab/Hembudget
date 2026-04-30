/**
 * V2 Lånegivaren · matchar /proposals/vol-7/elev.html#p-lan EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · "Aktör 04 · Lånegivaren"-pill (warm) +
 *      h1 "Dina lån, din kreditprofil" + actor-meta (Total skuld /
 *      Skuldkvot / Kreditprofil)
 *   3. .acct-grid (4 kort) · 1 aktiv + 3 möjliga (bolån, privatlån, billån)
 *   4. .act-grid (1.4fr 1fr):
 *      MAIN:
 *        - .section-eye + .tx-list · CSN amorteringsplan (4 senaste mån)
 *        - .section-eye + .biz-table · kreditprövning (5 rader)
 *        - .cta-card · uppdrag bolån
 *      ASIDE:
 *        - 4 .side-card (ränteavdrag · snabbamortering · befrielse · sms-varning)
 *   5. .peda · pedagogik
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type LoanData } from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function LanV2() {
  const [data, setData] = useState<LoanData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .lan()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda lån-data
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
        <div className="bank-loading">Laddar lån-data…</div>
      </div>
    );
  }

  const {
    cards,
    schedule,
    credit_factors,
    total_debt,
    debt_ratio,
    credit_class,
  } = data;

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
            <span className="pill warm">Aktör 04 · Lånegivaren</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Dina <em>lån</em>, din kreditprofil.
            </h1>
            <p className="actor-sub">
              CSN · ev. bolån · privatlån · billån · kreditprövning av dig
              själv som låntagare
            </p>
          </div>
          <div className="actor-meta">
            Total skuld: <strong>{SEK(total_debt)} kr</strong>
            <br />
            Skuldkvot: <strong>{debt_ratio.toFixed(2)}×</strong> årsinkomst
            <br />
            Kreditprofil: <strong>{credit_class}</strong>
          </div>
        </header>

        {/* LÅNETYPER · aktiva lån (möjliga produkter visas i Fas 2 när
            LoanProduct-modellen finns) */}
        {cards.length === 0 ? (
          <div
            style={{
              padding: "32px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Inga aktiva lån registrerade. När du får ett CSN-lån, bolån
            eller annat lån från Lånegivaren visas det här som ett kort
            med saldo + amortering.
          </div>
        ) : (
        <div className="acct-grid">
          {cards.map((c, idx) => (
            <div
              key={c.id ?? `card-${idx}`}
              className={`acct${c.is_active ? " active" : ""}${
                c.is_warning ? " warning" : ""
              }`}
            >
              <div>
                <div className="acct-eye">{c.eyebrow}</div>
                <div className="acct-name">{c.name}</div>
                <div className="acct-num">{c.detail}</div>
              </div>
              <div>
                <div
                  className="acct-bal"
                  style={
                    c.balance == null
                      ? { color: "var(--text-dim)" }
                      : undefined
                  }
                >
                  {c.balance != null ? (
                    c.is_active ? (
                      <em>{SEK(c.balance)}</em>
                    ) : (
                      SEK(c.balance)
                    )
                  ) : (
                    "— ej"
                  )}
                  {c.balance != null && " kr"}
                </div>
                {c.monthly_text && (
                  <div className="acct-bal-meta">{c.monthly_text}</div>
                )}
              </div>
            </div>
          ))}
        </div>
        )}

        <div className="act-grid">
          <div>
            {/* AMORTERINGSPLAN · senaste 4 mån */}
            <div className="section-eye">CSN · amorteringsplan</div>
            {schedule.length === 0 ? (
              <div
                style={{
                  padding: 20,
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Inga betalningar registrerade än. När amorteringar dras visas
                de här som månadshändelser.
              </div>
            ) : (
              <div className="tx-list">
                {schedule.map((row, idx) => (
                  <div className="tx-row" key={`${row.month}-${idx}`}>
                    <span className="tx-date">{row.label}</span>
                    <div>
                      <div className="tx-name">
                        Annuitet · {SEK(row.monthly_amount)} kr
                      </div>
                      <div className="tx-name-sub">{row.description}</div>
                    </div>
                    <span className="tx-meta">
                      {row.capital_part != null
                        ? `${SEK(row.capital_part)} kap`
                        : ""}
                    </span>
                    <span className="tx-meta">
                      {row.interest_part != null
                        ? `${SEK(row.interest_part)} ränta`
                        : ""}
                    </span>
                    <span
                      className="tx-meta"
                      style={{
                        color:
                          row.status === "betald"
                            ? "var(--text-mid)"
                            : "var(--warm)",
                      }}
                    >
                      {row.status}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* KREDITPRÖVNING · visas bara om vi har riktig data */}
            {credit_factors.length > 0 && (
              <>
            <div className="section-eye" style={{ marginTop: 24 }}>
              Kreditprövning · av dig själv som låntagare
            </div>
            <div className="biz-table">
              <div className="biz-table-row head">
                <span>Faktor</span>
                <span>Ditt värde</span>
                <span>Bedömning</span>
              </div>
              {credit_factors.map((f, idx) => (
                <div className="biz-table-row" key={idx}>
                  <div>
                    <div className="biz-factor-name">{f.factor}</div>
                    <div className="biz-factor-detail">{f.detail}</div>
                  </div>
                  <span className={`biz-factor-value ${f.severity}`}>
                    {f.value}
                  </span>
                  <span
                    className={`biz-factor-assess${
                      f.severity === "good" ? " good" : ""
                    }`}
                  >
                    {f.assessment}
                  </span>
                </div>
              ))}
            </div>
              </>
            )}

            {/* CTA · "Aktivt uppdrag" tas in i Fas 2 när Assignment-
                modellen kopplas till Lånegivaren. Tills dess inget. */}

            {/* PEDAGOGIK */}
            <div className="peda">
              <div className="peda-eye">Pedagogik · vad du lär dig här</div>
              <div className="peda-h">
                Inte alla lån är <em>lika</em>.
              </div>
              <p className="peda-prose">
                CSN-räntan är cirka 1/4 av bolåneräntan och 1/10 av
                blanco-låneräntan. Bolån är dyrare men finansierar tillgång
                (bostad). Privatlån är dyrast och oftast onödigt. Sms-lån är
                finansiell rovdrift. Lär dig skilja på{" "}
                <code>billig skuld</code> (CSN, bolån mot bostad),{" "}
                <code>medel</code> (billån mot bil), och{" "}
                <code>dyr skuld</code> (kreditkort, blanco, sms-lån).
              </p>
              <ul className="peda-bullets">
                <li className="peda-bullet">
                  <strong>Annuitet</strong>Samma månadsbelopp hela tiden —
                  ränta minskar, amortering ökar.
                </li>
                <li className="peda-bullet">
                  <strong>Rak amortering</strong>Samma kapital varje gång —
                  månadskostnad sjunker.
                </li>
                <li className="peda-bullet">
                  <strong>Effektiv ränta</strong>Inkluderar avgifter. Den
                  enda räntan att jämföra med.
                </li>
                <li className="peda-bullet">
                  <strong>UC-score</strong>Kreditupplysning. A–E. För många
                  påbörjade ansökningar = sänker.
                </li>
              </ul>
              <div className="peda-concepts">
                <span className="peda-concept">Annuitet</span>
                <span className="peda-concept">Effektiv ränta</span>
                <span className="peda-concept">Skuldkvot</span>
                <span className="peda-concept">Belåningsgrad</span>
                <span className="peda-concept">UC-score</span>
                <span className="peda-concept">Kronofogden</span>
                <span className="peda-concept">Räntegolv</span>
              </div>
              <div className="peda-tip">
                Lånekalkylatorn (verktyg 06) låter dig simulera "vad händer
                om jag amorterar 500 extra/mån i 5 år?" För CSN: lite. För
                bolån vid 4 %: mycket. Räkna alltid innan du beslutar.
              </div>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Ränteavdrag</div>
              <div className="side-card-h">
                30 % <em>av räntan</em>
              </div>
              <div className="side-card-meta">
                Räntor på CSN och bolån ger 30 % skatteavdrag (under 100k).
                Syns i din deklaration.
              </div>
              <a
                className="side-card-link"
                onClick={(e) => {
                  e.preventDefault();
                  navigate("/v2/skatten");
                }}
                href="#"
              >
                Se deklarationen ↗
              </a>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Snabbamortering</div>
              <div className="side-card-h">
                Beror på <em>räntan</em>
              </div>
              <div className="side-card-meta">
                Att amortera extra på ett lån ger en "garanterad avkastning"
                lika hög som räntan. Jämför mot vad du kan tjäna i ISK-fond
                (~7 % real avk. historiskt) innan du beslutar.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Befrielse vid arbetslöshet</div>
              <div className="side-card-h">Möjlig</div>
              <div className="side-card-meta">
                CSN ger amorteringsbefrielse vid arbetslöshet, sjukdom,
                föräldraledighet. Pausa istället för missa.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Varning · sms-lån</div>
              <div className="side-card-h">
                <em>20–40 %</em> ränta
              </div>
              <div className="side-card-meta">
                Många unga vuxna fastnar i sms-lån för impulsköp. Effektiv
                ränta + ev. UC-anmärkning ger livslång ekonomisk skuldfälla.
                Aldrig.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
