/**
 * V2 Budget · matchar /proposals/vol-7/elev.html#p-budget EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · pill "Verktyg 03 · Budget" + actor-name + sub +
 *      actor-meta (Total budget / Förbrukat / Kvar)
 *   3. .budget-total · top-card med total-belopp + sparkvot + knappar
 *   4. .section-eye + .budget-form-wrap · alla kategorier som rader
 *      (din budget / förbrukat / Konsumentverket / progress-bar)
 *   5. .echo-tip · pedagogisk tip-text (visas om någon är "over")
 *   6. .peda · stort pedagogik-block med bullets + concepts + tip
 *
 * All data hämtas via /v2/budget — ingen mock.
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { v2Api, type BudgetData } from "./api";
import { V2Banner } from "./V2Banner";
import "./budget.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const MONTH_NAMES = [
  "januari",
  "februari",
  "mars",
  "april",
  "maj",
  "juni",
  "juli",
  "augusti",
  "september",
  "oktober",
  "november",
  "december",
];

function monthLabel(ym: string): string {
  const [y, m] = ym.split("-");
  const idx = parseInt(m, 10) - 1;
  if (idx < 0 || idx > 11) return ym;
  return `${MONTH_NAMES[idx]} ${y}`;
}

export function BudgetV2() {
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params] = useSearchParams();
  const monthParam = params.get("month") || undefined;
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .budget(monthParam)
      .then(setBudget)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [monthParam]);

  if (error) {
    return (
      <div className="v2-budget-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda budget-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!budget) {
    return (
      <div className="v2-budget-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar budget-data…</div>
      </div>
    );
  }

  const { summary, categories, month } = budget;
  const overCategories = categories.filter((c) => c.status === "over");
  const overCount = overCategories.length;
  const expenseCategories = categories.filter((c) => !c.is_income);
  const incomeCategories = categories.filter((c) => c.is_income);
  const remaining = Math.max(
    0,
    summary.planned_expenses_total - summary.expenses_total,
  );
  const daysLeft = summary.days_in_month - summary.days_into_month;
  const consumedPct = Math.min(
    100,
    summary.progress_pct || 0,
  );

  // För progress-bar: cap visuellt vid 100% men visa sann procent som text
  const barWidth = (pct: number) => Math.min(100, Math.max(0, pct));

  return (
    <div className="v2-budget-root">
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
            <span className="pill">Verktyg 03 · Budget</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Budget {monthLabel(month).split(" ")[0]} —{" "}
              <em>plan möter utfall</em>.
            </h1>
            <p className="actor-sub">
              {expenseCategories.length} kategorier · dag{" "}
              {summary.days_into_month}/{summary.days_in_month} ·{" "}
              {Math.round(consumedPct)} % förbrukad · referens från
              Konsumentverket
            </p>
          </div>
          <div className="actor-meta">
            Total budget: <strong>{SEK(summary.planned_expenses_total)} kr</strong>
            <br />
            Förbrukat: <strong>{SEK(summary.expenses_total)} kr</strong> (
            {Math.round(consumedPct)} %)
            <br />
            Kvar: <strong>{SEK(remaining)} kr</strong> · {daysLeft} dgr
          </div>
        </header>

        {/* TOTAL-BAR */}
        <div className="budget-total">
          <div className="budget-total-row">
            <div>
              <div className="budget-total-eye">
                Total budget {monthLabel(month).split(" ")[0]}
              </div>
              <div className="budget-total-num">
                {SEK(summary.expenses_total)} kr{" "}
                <span>/ {SEK(summary.income_total)} inkomst</span>
              </div>
              <div className="budget-total-meta">
                Sparkvot {summary.save_rate_pct.toFixed(1)} %
                {summary.save_rate_pct >= 15
                  ? " · över mål 15 %"
                  : " · under mål 15 %"}
              </div>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className="cta-btn" type="button">
                Spara budget
              </button>
              <button className="cta-btn ghost" type="button">
                Återställ till Konsumentverket
              </button>
            </div>
          </div>
        </div>

        {/* KATEGORIER */}
        <div className="section-eye">
          Kategorier · skriv din budget · jämför med utfall &amp; Konsumentverket
        </div>
        {categories.length === 0 ? (
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
            Ingen budget satt än för {monthLabel(month)}. Använd
            "Återställ till Konsumentverket" för att starta från schabloner,
            eller lägg till kategorier en i taget.
          </div>
        ) : (
          <div className="budget-form-wrap">
            {/* Header-row */}
            <div className="budget-form-row head">
              <span></span>
              <span>Kategori</span>
              <span>Din budget</span>
              <span>Förbrukat</span>
              <span>Kons.verk</span>
              <span>Progress · status</span>
            </div>

            {/* Inkomst-rader först */}
            {incomeCategories.map((c) => (
              <div className="budget-form-row" key={c.category_id}>
                <span className="budget-icon">{c.icon}</span>
                <div>
                  <div className="budget-cat-name">{c.category_name}</div>
                  <div className="budget-cat-sub">Inkomst · månadsvis</div>
                </div>
                <input
                  className="budget-input"
                  type="number"
                  value={Math.round(c.planned)}
                  readOnly
                />
                <input
                  className="budget-input"
                  type="number"
                  value={Math.round(c.actual)}
                  disabled
                  style={{ opacity: 0.5, color: "#6ee7b7" }}
                />
                <span className="budget-ref">— inkomst</span>
                <div>
                  <div className="budget-bar">
                    <div
                      className="budget-bar-fill under"
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div
                    className="budget-bar-status under"
                    style={{ marginTop: 4 }}
                  >
                    {c.actual > 0
                      ? `+ ${SEK(c.actual)} mottagit`
                      : "Väntar på lön"}
                  </div>
                </div>
              </div>
            ))}

            {/* Utgifts-rader */}
            {expenseCategories.map((c) => {
              const fillClass =
                c.status === "over"
                  ? "over"
                  : c.status === "near"
                  ? "near"
                  : "under";
              const rowClass =
                c.status === "over"
                  ? " over-row"
                  : c.status === "savings"
                  ? " savings-row"
                  : "";
              const inputClass =
                c.status === "over"
                  ? " over"
                  : c.status === "savings"
                  ? " savings"
                  : "";
              const refText =
                c.consumer_reference != null
                  ? `${SEK(c.consumer_reference)} snitt`
                  : c.is_fixed
                  ? "— fast"
                  : c.status === "savings"
                  ? "— eget"
                  : "—";
              const statusText =
                c.status === "over"
                  ? `${Math.round(c.progress_pct)} % · + ${SEK(c.actual - c.planned)} över`
                  : c.status === "near"
                  ? c.is_fixed
                    ? "Klart · autogiro"
                    : `${Math.round(c.progress_pct)} % · klart`
                  : c.status === "savings"
                  ? c.actual >= c.planned
                    ? "100 % · pay yourself first"
                    : `${Math.round(c.progress_pct)} % · sparas`
                  : `${Math.round(c.progress_pct)} % · under budget`;
              const statusClass =
                c.status === "over"
                  ? "over"
                  : c.status === "under" || c.status === "savings"
                  ? "under"
                  : "";

              return (
                <div
                  className={`budget-form-row${rowClass}`}
                  key={c.category_id}
                >
                  <span className="budget-icon">{c.icon}</span>
                  <div>
                    <div className="budget-cat-name">{c.category_name}</div>
                    <div
                      className={`budget-cat-sub${
                        c.status === "over" ? " over" : ""
                      }`}
                    >
                      {c.is_fixed
                        ? "Fast kostnad · autogiro"
                        : c.status === "savings"
                        ? "Sparmål · pay yourself first"
                        : c.group_name
                        ? `Grupp · ${c.group_name}`
                        : c.status === "over"
                        ? "över budget — reflektera"
                        : "rörlig kostnad"}
                    </div>
                  </div>
                  <input
                    className={`budget-input${inputClass}`}
                    type="number"
                    value={Math.round(c.planned)}
                    readOnly={c.is_fixed}
                    onChange={() => {
                      /* TODO: PATCH /v2/budget i kommande fas */
                    }}
                    title={c.is_fixed ? "Fast kostnad — kan inte ändras" : ""}
                  />
                  <input
                    className="budget-input"
                    type="number"
                    value={Math.round(c.actual)}
                    disabled
                    style={{
                      opacity: 0.5,
                      color: c.status === "over" ? "var(--accent)" : undefined,
                    }}
                  />
                  <span className="budget-ref">{refText}</span>
                  <div>
                    <div className="budget-bar">
                      <div
                        className={`budget-bar-fill ${fillClass}`}
                        style={{ width: `${barWidth(c.progress_pct)}%` }}
                      />
                      {c.consumer_reference != null && c.planned > 0 && (
                        <div
                          className="budget-bar-marker"
                          style={{
                            left: `${Math.min(
                              100,
                              (c.consumer_reference / c.planned) * 100,
                            )}%`,
                          }}
                        />
                      )}
                    </div>
                    <div className={`budget-bar-status ${statusClass}`}>
                      {statusText}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ECHO-TIP — bara om någon är over */}
        {overCount > 0 && (
          <div className="echo-tip">
            <div className="echo-tip-eye">Echo · efter du sparat</div>
            <p className="echo-tip-prose">
              {overCount === 1 ? (
                <>
                  &quot;{overCategories[0].category_name} ligger på{" "}
                  {SEK(overCategories[0].planned)} igen — fast utfallet är{" "}
                  {SEK(overCategories[0].actual)}.{" "}
                  <em>Är budgeten orealistisk eller är beteendet det?</em>{" "}
                  Du kan höja för att inte fastna i nederlag, eller behålla
                  som mål du jobbar mot.&quot;
                </>
              ) : (
                <>
                  &quot;{overCount} kategorier är över budget med totalt{" "}
                  {SEK(summary.over_budget_total)} kr.{" "}
                  <em>
                    Är det kategorierna som är fel satta, eller är något annat
                    fel?
                  </em>{" "}
                  Reflektion är viktigare än perfekt budget.&quot;
                </>
              )}
            </p>
          </div>
        )}

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Budget är inte <em>kontroll</em>. Det är{" "}
            <em>kärlekspolitik mot dig själv</em>.
          </div>
          <p className="peda-prose">
            Att sätta en restaurang-budget på 1 200 är inte en bestraffning —
            det är en lovord till framtida-dig som vill ha buffert. Att
            överskrida med några hundra är inte misslyckande — det är data.
            Att se snitt från Konsumentverket är inte krav — det är referens.
            Du <em>förhandlar med dig själv</em>.
          </p>
          <ul className="peda-bullets">
            <li className="peda-bullet">
              <strong>Sparkvot</strong>Andel av inkomst som sparas. 15 % är
              riktvärde.
            </li>
            <li className="peda-bullet">
              <strong>Konsumentverket</strong>Schabloner per persontyp. Inte
              krav, referens.
            </li>
            <li className="peda-bullet">
              <strong>Pay yourself first</strong>Sparmål är räkning till dig
              själv. Dras först.
            </li>
            <li className="peda-bullet">
              <strong>Friktion</strong>Att se &quot;+ 900 över&quot; rött
              tvingar reflektion.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Sparkvot</span>
            <span className="peda-concept">Diskretionär utgift</span>
            <span className="peda-concept">Fast vs rörlig</span>
            <span className="peda-concept">Schablon</span>
            <span className="peda-concept">Cash flow</span>
          </div>
          <div className="peda-tip">
            Echo:{" "}
            {overCount > 0
              ? `"${overCategories[0].category_name} +${SEK(
                  overCategories[0].actual - overCategories[0].planned,
                )} är över budget. Är budgeten för låg, eller är något annat fel?"`
              : `"Du ligger inom budget på alla kategorier. Bra jobbat. Det är värt att reflektera över VAD som funkar."`}{" "}
            Det är frågan, inte svaret.
          </div>
        </div>
      </div>
    </div>
  );
}
