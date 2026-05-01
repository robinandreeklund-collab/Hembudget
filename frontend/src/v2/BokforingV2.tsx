/**
 * Verktyg 02 · Bokföring — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-bok):
 * - actor-head med pill, klassningsgrad, senast bokat
 * - cc-summary med Inkomster + Utgifter + Sparat
 * - filter-bar (konto, status, period, sök, "Klassa alla X (AI)")
 * - 12 ovettade-tabell med inline-kategori-select per rad
 * - Auto-klassade-tabell
 * - peda-block "Ovettade transaktioner är din spegel"
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2BookkeepingData,
  type V2BookkeepingTxRow,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const DATE_LABEL = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

function currentMonthIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function buildPeriodOptions(): { value: string; label: string }[] {
  const now = new Date();
  const opts: { value: string; label: string }[] = [];
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString("sv-SE", {
      month: "long",
      year: "numeric",
    });
    opts.push({ value, label: label[0].toUpperCase() + label.slice(1) });
  }
  opts.push({ value: "all", label: "Hela perioden" });
  return opts;
}

export function BokforingV2() {
  const [data, setData] = useState<V2BookkeepingData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState(currentMonthIso());
  const [accountFilter, setAccountFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<number | null>(null);

  function refresh(): Promise<void> {
    return v2Api
      .bokforing(period)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  async function classifyTx(txId: number, categoryId: number) {
    setClassifyingId(txId);
    try {
      await v2Api.bookkeepingClassify(txId, { category_id: categoryId });
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setClassifyingId(null);
    }
  }

  async function bulkClassify() {
    setBulkBusy(true);
    setBulkMessage(null);
    try {
      const r = await v2Api.bookkeepingBulkClassify({ period });
      setBulkMessage(
        `${r.classified} klassade (${r.via_rule} regelmotor, ${r.via_history} historik, ${r.via_llm} AI) · ${r.still_unclassified} kvar`,
      );
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBulkBusy(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda bokföring
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
        <div className="bank-loading">Laddar bokföring…</div>
      </div>
    );
  }

  const s = data.summary;

  // Filtrering på unclassified + classified separat
  const matchesFilters = (t: V2BookkeepingTxRow): boolean => {
    if (
      accountFilter !== "all" &&
      String(t.account_id) !== accountFilter
    )
      return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      if (
        !t.raw_description.toLowerCase().includes(q) &&
        !(t.normalized_merchant || "").toLowerCase().includes(q) &&
        !(t.category_name || "").toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  };

  let unclassifiedView = data.unclassified.filter(matchesFilters);
  let classifiedView = data.classified.filter(matchesFilters);

  if (statusFilter === "unclassified") {
    classifiedView = [];
  } else if (statusFilter === "auto") {
    unclassifiedView = [];
    classifiedView = classifiedView.filter((t) => !t.user_verified);
  } else if (statusFilter === "manual") {
    unclassifiedView = [];
    classifiedView = classifiedView.filter((t) => t.user_verified);
  }

  // Lista unika konton för filter
  const accountSet = new Map<number, string>();
  for (const t of [...data.unclassified, ...data.classified]) {
    accountSet.set(t.account_id, t.account_name);
  }

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Verktyg 02 · Bokföring</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Transaktioner — <em>där pengar talar</em>.
            </h1>
            <p className="actor-sub">
              {s.total_transactions} transaktioner i {s.period_label} ·{" "}
              {s.auto_classified} auto · {s.manual_classified} manuellt ·{" "}
              {s.unclassified} ovettade
            </p>
          </div>
          <div className="actor-meta">
            Ovettade:{" "}
            <strong>
              {s.unclassified} (
              {s.total_transactions > 0
                ? Math.round((s.unclassified / s.total_transactions) * 100)
                : 0}{" "}
              %)
            </strong>
            <br />
            Klassningsgrad:{" "}
            <strong
              style={{
                color:
                  s.classification_rate_pct >= 80
                    ? "#6ee7b7"
                    : s.classification_rate_pct >= 50
                    ? "#fff"
                    : "#fda594",
              }}
            >
              {s.classification_rate_pct} %
            </strong>
            <br />
            Senast bokat:{" "}
            <strong>
              {s.last_classified_at
                ? DATE_LABEL(s.last_classified_at)
                : "—"}
            </strong>
          </div>
        </header>

        {/* CC-SUMMARY */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 18,
          }}
        >
          <div
            className="cc-stat"
            style={{
              padding: "16px 20px",
              border: "1px solid var(--line)",
              borderRadius: 6,
            }}
          >
            <div
              className="cc-stat-eye"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                color: "var(--text-dim)",
              }}
            >
              Inkomster
            </div>
            <div
              className="cc-stat-num"
              style={{
                fontFamily: "var(--serif)",
                fontSize: 26,
                fontStyle: "italic",
                fontWeight: 700,
                color: "#6ee7b7",
                marginTop: 4,
              }}
            >
              + {SEK(s.income_total)} kr
            </div>
            <div
              className="cc-stat-sub"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                color: "var(--text-mid)",
                marginTop: 4,
              }}
            >
              Lön + bidrag + utdelning
            </div>
          </div>
          <div
            className="cc-stat"
            style={{
              padding: "16px 20px",
              border: "1px solid var(--line)",
              borderRadius: 6,
            }}
          >
            <div
              className="cc-stat-eye"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                color: "var(--text-dim)",
              }}
            >
              Utgifter
            </div>
            <div
              className="cc-stat-num"
              style={{
                fontFamily: "var(--serif)",
                fontSize: 26,
                fontWeight: 700,
                marginTop: 4,
              }}
            >
              − {SEK(s.expense_total)} kr
            </div>
            <div
              className="cc-stat-sub"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                color: "var(--text-mid)",
                marginTop: 4,
              }}
            >
              {data.categories.length} kategorier
            </div>
          </div>
          <div
            className="cc-stat"
            style={{
              padding: "16px 20px",
              border: "1px solid var(--line)",
              borderRadius: 6,
            }}
          >
            <div
              className="cc-stat-eye"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                color: "var(--text-dim)",
              }}
            >
              Sparat {s.period_label.split(" ")[0]}
            </div>
            <div
              className="cc-stat-num"
              style={{
                fontFamily: "var(--serif)",
                fontSize: 26,
                fontStyle: "italic",
                fontWeight: 700,
                color: s.saved_total >= 0 ? "var(--warm)" : "#fca5a5",
                marginTop: 4,
              }}
            >
              {s.saved_total >= 0 ? "+" : ""} {SEK(s.saved_total)} kr
            </div>
            <div
              className="cc-stat-sub"
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                color: "var(--text-mid)",
                marginTop: 4,
              }}
            >
              {s.saved_pct} % av inkomst
            </div>
          </div>
        </div>

        {/* FILTER-BAR */}
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
            marginBottom: 18,
            padding: "14px 18px",
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 6,
          }}
        >
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-mid)",
            }}
          >
            Filter:
          </span>
          <select
            value={accountFilter}
            onChange={(e) => setAccountFilter(e.target.value)}
            style={selStyle()}
          >
            <option value="all">Alla konton</option>
            {Array.from(accountSet.entries()).map(([id, name]) => (
              <option key={id} value={String(id)}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={selStyle()}
          >
            <option value="all">Alla statusar</option>
            <option value="unclassified">
              Ovettade ({s.unclassified})
            </option>
            <option value="auto">Auto-klassade ({s.auto_classified})</option>
            <option value="manual">Manuella ({s.manual_classified})</option>
          </select>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            style={selStyle()}
          >
            {buildPeriodOptions().map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Sök transaktion..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              ...selStyle(),
              flex: 1,
              minWidth: 180,
            }}
          />
          {s.unclassified > 0 && (
            <button
              type="button"
              disabled={bulkBusy}
              onClick={bulkClassify}
              style={{
                background: "var(--warm)",
                color: "#422006",
                border: 0,
                padding: "8px 14px",
                borderRadius: 100,
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                fontWeight: 700,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                cursor: bulkBusy ? "wait" : "pointer",
              }}
            >
              {bulkBusy
                ? "Klassar…"
                : `Klassa alla ${s.unclassified} (AI)`}
            </button>
          )}
        </div>

        {bulkMessage && (
          <div
            style={{
              padding: "10px 16px",
              border: "1px solid rgba(110,231,183,0.4)",
              background: "rgba(110,231,183,0.06)",
              borderRadius: 6,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#6ee7b7",
              marginBottom: 14,
              letterSpacing: "0.6px",
            }}
          >
            ● {bulkMessage}
          </div>
        )}

        {/* OVETTADE */}
        {unclassifiedView.length > 0 && (
          <>
            <div className="section-eye">
              {data.unclassified.length} ovettade · klassa per rad
            </div>
            <div className="biz-table" style={{ marginBottom: 22 }}>
              <div
                className="biz-table-row head"
                style={{
                  gridTemplateColumns: "100px 1.4fr 1.2fr 90px",
                }}
              >
                <span>Datum</span>
                <span>Beskrivning</span>
                <span>Kategori / konto</span>
                <span>Belopp</span>
              </div>
              {unclassifiedView.map((t) => (
                <div
                  className="biz-table-row"
                  key={t.id}
                  style={{
                    gridTemplateColumns: "100px 1.4fr 1.2fr 90px",
                  }}
                >
                  <span
                    style={{ fontFamily: "var(--mono)", fontSize: 10 }}
                  >
                    {DATE_LABEL(t.date)}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 13.5,
                      }}
                    >
                      {t.raw_description}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: "var(--text-dim)",
                      }}
                    >
                      {t.account_name}
                      {t.normalized_merchant
                        ? ` · ${t.normalized_merchant}`
                        : ""}
                    </div>
                  </div>
                  <select
                    value={t.category_id || ""}
                    disabled={classifyingId === t.id}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      if (!isNaN(v)) classifyTx(t.id, v);
                    }}
                    style={{
                      background: "rgba(220,76,43,0.08)",
                      border: "1px dashed var(--accent)",
                      color: "#fff",
                      padding: "6px 8px",
                      borderRadius: 4,
                      fontFamily: "Inter, sans-serif",
                      fontSize: 12,
                    }}
                  >
                    <option value="">Välj kategori...</option>
                    {data.categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <span
                    style={{
                      fontFamily: "var(--serif)",
                      textAlign: "right",
                      color: t.amount < 0 ? "#fff" : "#6ee7b7",
                    }}
                  >
                    {t.amount > 0 ? "+ " : "− "}
                    {SEK(Math.abs(t.amount))} kr
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* KLASSADE */}
        {classifiedView.length > 0 && (
          <>
            <div className="section-eye">
              {data.classified.length} klassade · regelmotor + AI +
              manuella
            </div>
            <div className="biz-table">
              <div
                className="biz-table-row head"
                style={{
                  gridTemplateColumns: "100px 1.4fr 1fr 110px 90px",
                }}
              >
                <span>Datum</span>
                <span>Beskrivning</span>
                <span>Kategori</span>
                <span>Konto</span>
                <span>Belopp</span>
              </div>
              {classifiedView.slice(0, 50).map((t) => (
                <div
                  className="biz-table-row"
                  key={t.id}
                  style={{
                    gridTemplateColumns: "100px 1.4fr 1fr 110px 90px",
                  }}
                >
                  <span
                    style={{ fontFamily: "var(--mono)", fontSize: 10 }}
                  >
                    {DATE_LABEL(t.date)}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 13.5,
                      }}
                    >
                      {t.raw_description}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: "var(--text-dim)",
                      }}
                    >
                      {t.user_verified
                        ? "manuell"
                        : t.ai_confidence != null
                        ? `auto · ${Math.round(t.ai_confidence * 100)} % conf`
                        : "auto"}
                    </div>
                  </div>
                  <span
                    className={`biz-status ${
                      t.amount > 0 ? "paid" : "sent"
                    }`}
                  >
                    {t.category_name || "—"}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "var(--text-mid)",
                    }}
                  >
                    {t.account_name}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--serif)",
                      textAlign: "right",
                      color: t.amount < 0 ? "#fff" : "#6ee7b7",
                    }}
                  >
                    {t.amount > 0 ? "+ " : "− "}
                    {SEK(Math.abs(t.amount))}
                  </span>
                </div>
              ))}
              {classifiedView.length > 50 && (
                <div
                  style={{
                    textAlign: "center",
                    padding: 12,
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-dim)",
                    letterSpacing: "1px",
                  }}
                >
                  + {classifiedView.length - 50} transaktioner till
                </div>
              )}
            </div>
          </>
        )}

        {unclassifiedView.length === 0 && classifiedView.length === 0 && (
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
            Inga transaktioner i {s.period_label} matchar filtret.
          </div>
        )}

        {/* PEDA */}
        <div className="peda" style={{ marginTop: 22 }}>
          <div className="peda-eye">
            Pedagogik · vad du lär dig här
          </div>
          <div className="peda-h">
            Ovettade transaktioner är <em>din spegel</em>.
          </div>
          <p className="peda-prose">
            Att klassa en transaktion = du <em>bestämmer</em> vad det
            betyder. Coop på 312 kr blir "Mat" (vana) eller "Restaurang"
            (om det egentligen var färdiglagat). Ditt eget val avslöjar
            dina ekonomiska beteenden. Ju mer du klassar, desto mer ser
            du.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Regelmotor</strong>"Stockholmshem" → alltid Hyra.
              Lärs in över tid.
            </li>
            <li>
              <strong>Historik-match</strong>Tidigare verifierade
              merchant-namn återanvänds automatiskt.
            </li>
            <li>
              <strong>Manuell klass</strong>Du säger emot AI · alltid din
              slutgiltiga.
            </li>
            <li>
              <strong>Anomalier</strong>Plötslig 800 kr Coop på en sön
              kväll = flagga (kommer i senare fas).
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Kategorisering</span>
            <span className="peda-concept">Regelmotor</span>
            <span className="peda-concept">Anomali</span>
            <span className="peda-concept">Bokföringsmetod</span>
            <span className="peda-concept">Verifikat</span>
          </div>
          <div className="peda-tip">
            Lärar-vyn ser din klassningsgrad (
            {s.classification_rate_pct} %).{" "}
            {s.classification_rate_pct >= 80
              ? "Bra — över 80 % gör att vi kan dra slutsatser om dina vanor."
              : s.classification_rate_pct >= 50
              ? "OK — försök komma över 80 %."
              : "Under 50 % flaggas som 'behöver stöd'. Klassa fler för att se din spegel."}
          </div>
        </div>
      </div>
    </div>
  );
}

function selStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong)",
    color: "#fff",
    padding: "7px 11px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 12.5,
  };
}
