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
  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [params] = useSearchParams();
  const monthParam = params.get("month") || undefined;
  const navigate = useNavigate();

  // Editor-state per rad: draft-värde (string för att tillåta tom input
  // och decimaler), spara-status, ev. felmeddelande.
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [savedFlash, setSavedFlash] = useState<Record<number, number>>({});
  const [rowError, setRowError] = useState<Record<number, string>>({});

  // Ny-kategori-form
  const [newCatName, setNewCatName] = useState("");
  const [newCatAmount, setNewCatAmount] = useState("");
  const [creatingCat, setCreatingCat] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Currently rendered month (eller fallback till budget.month om laddat)
  const ym = monthParam || budget?.month;

  function refreshBudget() {
    return v2Api
      .budget(monthParam)
      .then(setBudget)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    v2Api
      .budget(monthParam)
      .then(setBudget)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [monthParam]);

  async function saveCategoryAmount(
    categoryId: number,
    raw: string,
    isIncome: boolean,
  ): Promise<void> {
    const parsed = parseFloat(raw.replace(/\s/g, "").replace(",", "."));
    if (isNaN(parsed) || parsed < 0) {
      setRowError((r) => ({
        ...r,
        [categoryId]: "Ogiltigt belopp",
      }));
      return;
    }
    setRowError((r) => {
      const next = { ...r };
      delete next[categoryId];
      return next;
    });
    setSavingId(categoryId);
    try {
      await v2Api.updateBudgetCategory(categoryId, {
        planned_amount: parsed,
        month: ym,
        is_income: isIncome,
      });
      // Hämta hela budget på nytt så summary + alla progress-staplar
      // räknas om konsistent (sparkvot, total etc.)
      await refreshBudget();
      setSavedFlash((f) => ({ ...f, [categoryId]: Date.now() }));
      setDrafts((d) => {
        const next = { ...d };
        delete next[categoryId];
        return next;
      });
      // Auto-rensa "sparat"-tag efter 1.5 s
      setTimeout(() => {
        setSavedFlash((f) => {
          const next = { ...f };
          delete next[categoryId];
          return next;
        });
      }, 1500);
    } catch (e) {
      setRowError((r) => ({
        ...r,
        [categoryId]: String((e as Error)?.message || e),
      }));
    } finally {
      setSavingId(null);
    }
  }

  async function deleteCategoryRow(categoryId: number): Promise<void> {
    if (
      !confirm(
        "Ta bort budget-raden? Kategorin behålls — bara budgeten för månaden raderas.",
      )
    ) {
      return;
    }
    setSavingId(categoryId);
    try {
      await v2Api.deleteBudgetRow(categoryId, ym);
      await refreshBudget();
    } catch (e) {
      setRowError((r) => ({
        ...r,
        [categoryId]: String((e as Error)?.message || e),
      }));
    } finally {
      setSavingId(null);
    }
  }

  async function createCategory(): Promise<void> {
    const name = newCatName.trim();
    const parsed = parseFloat(
      newCatAmount.replace(/\s/g, "").replace(",", "."),
    );
    if (!name) {
      setCreateError("Skriv ett kategori-namn");
      return;
    }
    if (isNaN(parsed) || parsed < 0) {
      setCreateError("Ogiltigt belopp");
      return;
    }
    setCreateError(null);
    setCreatingCat(true);
    try {
      await v2Api.createBudgetCategory({
        category_name: name,
        planned_amount: parsed,
        month: ym,
        is_income: false,
      });
      await refreshBudget();
      setNewCatName("");
      setNewCatAmount("");
    } catch (e) {
      setCreateError(String((e as Error)?.message || e));
    } finally {
      setCreatingCat(false);
    }
  }

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

      <div className="shell" data-guide="budget-categories">
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
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "#6ee7b7",
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                  alignSelf: "center",
                }}
              >
                ● Auto-sparas per kategori
              </span>
              <button
                className="cta-btn ghost"
                type="button"
                disabled={resetting}
                onClick={async () => {
                  if (
                    !confirm(
                      "Återställ alla planerade belopp till Konsumentverkets schabloner? " +
                      "Befintliga värden skrivs över.",
                    )
                  ) return;
                  setResetting(true);
                  setResetMsg(null);
                  try {
                    const r = await v2Api.resetBudgetToKonsumentverket(
                      monthParam,
                    );
                    setResetMsg(
                      `✓ ${r.rows_created} skapade · ${r.rows_updated} uppdaterade · ` +
                      `${r.categories_with_reference} kategorier har referens-värde`,
                    );
                    await refreshBudget();
                  } catch (e) {
                    setResetMsg(
                      `Fel: ${String((e as Error)?.message || e)}`,
                    );
                  } finally {
                    setResetting(false);
                  }
                }}
              >
                {resetting
                  ? "Återställer…"
                  : "Återställ till Konsumentverket"}
              </button>
            </div>
          </div>
          {resetMsg && (
            <div
              style={{
                marginTop: 12,
                padding: "8px 14px",
                border: resetMsg.startsWith("Fel")
                  ? "1px solid rgba(252,165,165,0.4)"
                  : "1px solid rgba(110,231,183,0.4)",
                background: resetMsg.startsWith("Fel")
                  ? "rgba(252,165,165,0.06)"
                  : "rgba(110,231,183,0.06)",
                borderRadius: 6,
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: resetMsg.startsWith("Fel") ? "#fca5a5" : "#6ee7b7",
              }}
            >
              {resetMsg}
            </div>
          )}
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
            {incomeCategories.map((c) => {
              const draft = drafts[c.category_id];
              const display =
                draft !== undefined ? draft : String(Math.round(c.planned));
              const saving = savingId === c.category_id;
              const justSaved = savedFlash[c.category_id] != null;
              const errMsg = rowError[c.category_id];
              return (
                <div className="budget-form-row" key={c.category_id}>
                  <span className="budget-icon">{c.icon}</span>
                  <div>
                    <div className="budget-cat-name">{c.category_name}</div>
                    <div className="budget-cat-sub">
                      Inkomst · månadsvis
                      {saving && " · sparar…"}
                      {justSaved && !saving && " · sparat ✓"}
                      {errMsg && ` · ${errMsg}`}
                    </div>
                  </div>
                  <input
                    className="budget-input"
                    type="number"
                    inputMode="numeric"
                    value={display}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [c.category_id]: e.target.value,
                      }))
                    }
                    onBlur={() => {
                      if (draft !== undefined && draft !== String(Math.round(c.planned))) {
                        saveCategoryAmount(c.category_id, draft, true);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                    }}
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
              );
            })}

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

              const saving = savingId === c.category_id;
              const justSaved = savedFlash[c.category_id] != null;
              const errMsg = rowError[c.category_id];

              return (
                <div
                  className={`budget-form-row${rowClass}`}
                  key={c.category_id}
                >
                  <span className="budget-icon">{c.icon}</span>
                  <div>
                    <div className="budget-cat-name">
                      {c.category_name}
                      {!c.is_fixed && !saving && !justSaved && (
                        <button
                          type="button"
                          onClick={() => deleteCategoryRow(c.category_id)}
                          title="Ta bort budget-raden"
                          className="budget-row-delete"
                        >
                          ×
                        </button>
                      )}
                    </div>
                    <div
                      className={`budget-cat-sub${
                        c.status === "over" ? " over" : ""
                      }`}
                    >
                      {saving
                        ? "Sparar…"
                        : justSaved
                        ? "Sparat ✓"
                        : errMsg
                        ? errMsg
                        : c.is_fixed
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
                    inputMode="numeric"
                    value={
                      drafts[c.category_id] !== undefined
                        ? drafts[c.category_id]
                        : String(Math.round(c.planned))
                    }
                    readOnly={c.is_fixed}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [c.category_id]: e.target.value,
                      }))
                    }
                    onBlur={() => {
                      const draft = drafts[c.category_id];
                      if (
                        !c.is_fixed &&
                        draft !== undefined &&
                        draft !== String(Math.round(c.planned))
                      ) {
                        saveCategoryAmount(c.category_id, draft, false);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter")
                        (e.target as HTMLInputElement).blur();
                    }}
                    title={
                      c.is_fixed
                        ? "Fast kostnad — kan inte ändras direkt"
                        : "Tryck Enter eller flytta fokus för att spara"
                    }
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

            {/* Lägg till ny kategori — matchar prototypens sista rad */}
            <div className="budget-form-row budget-form-add">
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 14,
                  color: "var(--text-dim)",
                }}
              >
                +
              </span>
              <div>
                <input
                  type="text"
                  placeholder="Lägg till egen kategori (ex: Träning, Bok-klubb…)"
                  value={newCatName}
                  onChange={(e) => setNewCatName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") createCategory();
                  }}
                  className="budget-cat-input"
                />
                {createError && (
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      color: "var(--accent)",
                      marginTop: 4,
                    }}
                  >
                    {createError}
                  </div>
                )}
              </div>
              <input
                className="budget-input"
                type="number"
                inputMode="numeric"
                placeholder="0"
                value={newCatAmount}
                onChange={(e) => setNewCatAmount(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") createCategory();
                }}
              />
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-dim)",
                }}
              >
                —
              </span>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-dim)",
                }}
              >
                —
              </span>
              <button
                type="button"
                onClick={createCategory}
                disabled={creatingCat}
                className="budget-add-btn"
              >
                {creatingCat ? "Sparar…" : "Lägg till"}
              </button>
            </div>
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
