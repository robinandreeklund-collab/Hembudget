/**
 * Transaktion-detalj — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-tx):
 * - actor-head med pill ("Transaktion · Foodora 17 apr"), AI-förslag,
 *   eget val, återkommande
 * - cc-summary 3 stat-cards (Belopp, Konto, Klassad)
 * - Välj kategori & konto-form (kategori, underkategori, konto, notes)
 * - Återkommande-mönster (samma normalized_merchant senaste 90 dgr)
 * - Aside · Echo-tip + Skapa regel + Bokföringspost
 * - peda "En transaktion är en berättelse"
 *
 * Wellbeing: aktivt klassande räknas redan via klassningsgrad-faktorn
 * i Bokföring (≥ 80 % → +2 economy). Skapa regel = automatisk klassning
 * framöver — räknas också med.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  v2Api,
  type V2TxDetailData,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const TIME_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export function TxV2() {
  const { txId } = useParams<{ txId: string }>();
  const id = txId ? parseInt(txId, 10) : 0;
  const [data, setData] = useState<V2TxDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  // Form state
  const [catId, setCatId] = useState<number | "">("");
  const [subId, setSubId] = useState<number | "">("");
  const [accountId, setAccountId] = useState<number | "">("");
  const [notes, setNotes] = useState("");

  function refresh() {
    return v2Api
      .txDetail(id)
      .then((d) => {
        setData(d);
        setCatId(d.category_id || "");
        setSubId(d.subcategory_id || "");
        setAccountId(d.account_id);
        setNotes(d.notes || "");
      })
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (id) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function save() {
    if (!data) return;
    setSaving(true);
    setSavedMsg(null);
    try {
      await v2Api.txClassify(id, {
        category_id: catId === "" ? undefined : Number(catId),
        subcategory_id: subId === "" ? undefined : Number(subId),
        account_id:
          accountId === "" ? undefined : Number(accountId),
        notes: notes,
      });
      setSavedMsg("✓ Klassning sparad");
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSaving(false);
    }
  }

  async function createRule() {
    if (!data || catId === "") return;
    if (
      !confirm(
        `Skapa regel: "${data.normalized_merchant || data.raw_description}" → kategori? Alla framtida och nuvarande oklassificerade matchande tx blir klassade automatiskt.`,
      )
    ) {
      return;
    }
    try {
      const r = await v2Api.txCreateRule(id, {
        category_id: Number(catId),
        apply_to_existing: true,
      });
      if (r.already_existed) {
        setSavedMsg("Regeln fanns redan.");
      } else {
        setSavedMsg(
          `✓ Regel skapad · ${r.applied_count} tidigare tx klassades om`,
        );
      }
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda transaktion
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
        <div className="bank-loading">Laddar transaktion…</div>
      </div>
    );
  }

  const monthlyBudget = 1200; // referensvärde · framtida: hämta från Budget
  const recurringMonthly =
    data.recurring_count_30d > 0
      ? data.recurring_total_30d
      : Math.abs(data.amount);

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/bokforing">
          Tillbaka till bokföring
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">
              Transaktion ·{" "}
              {data.raw_description.split(" ")[0]} {SHORT_DATE(data.date)}
            </span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.raw_description.split(" ")[0]}{" "}
              <em>
                {data.amount > 0 ? "+" : "−"} {SEK(Math.abs(data.amount))}{" "}
                kr
              </em>
              .
            </h1>
            <p className="actor-sub">
              {TIME_DATE(data.date)} · {data.account_name} ·{" "}
              {data.raw_description}
            </p>
          </div>
          <div className="actor-meta">
            AI-förslag:{" "}
            <strong>
              {data.ai_confidence != null
                ? `${data.category_name || "—"} (${Math.round(data.ai_confidence * 100)} %)`
                : "—"}
            </strong>
            <br />
            Eget val:{" "}
            <strong>
              {data.user_verified
                ? data.category_name || "—"
                : "ej klassad"}
            </strong>
            <br />
            Återkommande:{" "}
            <strong>
              {data.recurring_count_30d} ggr senaste 30 dgr
            </strong>
          </div>
        </header>

        {/* CC-SUMMARY · 3 stat-cards */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 22,
          }}
        >
          <StatCard
            eye="Belopp"
            value={`${data.amount > 0 ? "+" : "−"} ${SEK(Math.abs(data.amount))} kr`}
            sub={
              data.amount < 0
                ? "Utgift"
                : "Inkomst"
            }
          />
          <StatCard
            eye="Konto"
            value={data.account_name}
            sub={`tx-id ${data.id} · ${data.is_transfer ? "transfer" : "tx"}`}
          />
          <StatCard
            eye="Klassad"
            value={
              data.category_name ||
              (data.ai_confidence != null
                ? `AI-förslag (${Math.round(data.ai_confidence * 100)} %)`
                : "Ej klassad")
            }
            sub={
              data.user_verified
                ? "manuellt — verifierad"
                : data.ai_confidence != null
                ? "auto — vänta på din verif"
                : "kräver klassning"
            }
            warm={data.user_verified}
          />
        </div>

        <div className="act-grid">
          <div>
            {/* KLASS-FORM */}
            <div className="section-eye">Välj kategori & konto</div>
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
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 14,
                  marginBottom: 14,
                }}
              >
                <FormField label="Kategori">
                  <select
                    value={catId}
                    onChange={(e) =>
                      setCatId(
                        e.target.value === ""
                          ? ""
                          : parseInt(e.target.value, 10),
                      )
                    }
                    style={selectStyle()}
                  >
                    <option value="">Välj kategori…</option>
                    {data.categories
                      .filter((c) => c.parent_id == null)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                  </select>
                </FormField>
                <FormField label="Underkategori">
                  <select
                    value={subId}
                    onChange={(e) =>
                      setSubId(
                        e.target.value === ""
                          ? ""
                          : parseInt(e.target.value, 10),
                      )
                    }
                    style={selectStyle()}
                  >
                    <option value="">— ingen —</option>
                    {data.categories
                      .filter((c) => c.parent_id === catId)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                  </select>
                </FormField>
                <FormField label="Konto">
                  <select
                    value={accountId}
                    onChange={(e) =>
                      setAccountId(parseInt(e.target.value, 10))
                    }
                    style={selectStyle()}
                  >
                    {data.accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.type})
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Sammanhang">
                  <select
                    style={selectStyle()}
                    onChange={(e) => {
                      // Append context to notes
                      if (e.target.value) {
                        setNotes(
                          notes
                            ? `${notes}\n${e.target.value}`
                            : e.target.value,
                        );
                      }
                    }}
                  >
                    <option value="">— välj —</option>
                    <option value="Efter träning">Efter träning</option>
                    <option value="Vardagslunch">Vardagslunch</option>
                    <option value="Helgmiddag">Helgmiddag</option>
                    <option value="Med vänner">Med vänner</option>
                    <option value="Behov">Behov</option>
                    <option value="Impuls">Impuls</option>
                  </select>
                </FormField>
              </div>
              <FormField label="Egen anteckning (frivillig)">
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="t.ex. 'efter laxsim med Hassan'"
                  style={{
                    width: "100%",
                    minHeight: 60,
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--line-strong)",
                    color: "#fff",
                    padding: "10px 12px",
                    borderRadius: 6,
                    fontFamily: "Inter, sans-serif",
                    fontSize: 13,
                    resize: "vertical",
                  }}
                />
              </FormField>
              {savedMsg && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#6ee7b7",
                    marginTop: 10,
                  }}
                >
                  ● {savedMsg}
                </div>
              )}
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  marginTop: 14,
                  flexWrap: "wrap",
                }}
              >
                <button
                  type="button"
                  className="cta-btn"
                  disabled={saving}
                  onClick={save}
                >
                  {saving ? "Sparar…" : "Spara klassning"}
                </button>
                <button
                  type="button"
                  className="cta-btn ghost"
                  disabled={catId === "" || data.existing_rule_id != null}
                  onClick={createRule}
                  title={
                    data.existing_rule_id != null
                      ? "Regel finns redan"
                      : "Skapa regel som klassar alla framtida köp automatiskt"
                  }
                >
                  {data.existing_rule_id != null
                    ? "Regel finns ✓"
                    : `Skapa regel: "${
                        data.normalized_merchant ||
                        data.raw_description.split(" ")[0]
                      } → kategori"`}
                </button>
              </div>
            </div>

            {/* RECURRING */}
            {data.recurring.length > 0 && (
              <>
                <div className="section-eye">
                  Andra{" "}
                  {data.normalized_merchant ||
                    data.raw_description.split(" ")[0]}
                  -köp · återkommande mönster
                </div>
                <div className="biz-table" style={{ marginBottom: 12 }}>
                  {data.recurring.map((r) => (
                    <div
                      key={r.id}
                      className="biz-table-row"
                      style={{
                        gridTemplateColumns: "100px 1fr 100px",
                      }}
                    >
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: r.is_self
                            ? "var(--warm)"
                            : "var(--text-mid)",
                        }}
                      >
                        {SHORT_DATE(r.date)}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                        }}
                      >
                        {r.description}
                        {r.is_self && (
                          <em
                            style={{
                              color: "var(--warm)",
                              marginLeft: 8,
                              fontSize: 11,
                            }}
                          >
                            (denna)
                          </em>
                        )}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--serif)",
                          textAlign: "right",
                          color: r.is_self ? "var(--warm)" : "#fff",
                        }}
                      >
                        {r.amount > 0 ? "+" : "−"} {SEK(Math.abs(r.amount))}
                      </span>
                    </div>
                  ))}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-dim)",
                    letterSpacing: "0.5px",
                    marginBottom: 22,
                  }}
                >
                  Snitt:{" "}
                  <strong style={{ color: "var(--warm)" }}>
                    {data.recurring_count_30d > 0
                      ? `${SEK(
                          recurringMonthly /
                            Math.max(1, data.recurring_count_30d),
                        )} kr/gång · ${data.recurring_count_30d} ggr/30 dgr`
                      : "första gången"}
                  </strong>{" "}
                  = {SEK(recurringMonthly)} kr/30 dgr. Restaurangbudget
                  ref: {SEK(monthlyBudget)} kr.
                </div>
              </>
            )}
          </div>

          <aside>
            <div
              className="side-card"
              style={{
                background: "rgba(251,191,36,0.06)",
                borderColor: "rgba(251,191,36,0.3)",
              }}
            >
              <div
                className="side-card-eye"
                style={{ color: "var(--warm)" }}
              >
                Echo · efter klassning
              </div>
              <div className="side-card-h">
                "
                {data.recurring_count_30d > 0
                  ? `${data.recurring_count_30d + 1} ${data.normalized_merchant || "köp"} på 30 dgr`
                  : "Första köpet"}
                ."
              </div>
              <div className="side-card-meta">
                {data.recurring_count_30d >= 3
                  ? "Mönster syns. Är det vana, eller behov? Värt en reflektion."
                  : data.recurring_count_30d > 0
                  ? "Ett mönster börjar. Lägg märke till."
                  : "Klassa nu — sen kan du skapa regel."}
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Skapa regel?</div>
              <div className="side-card-h">
                "{data.normalized_merchant || data.raw_description.split(" ")[0]}{" "}
                → kategori"
              </div>
              <div className="side-card-meta">
                {data.existing_rule_id != null
                  ? "Regel finns redan — alla framtida köp klassas automatiskt."
                  : "Om du skapar regeln klassas alla framtida köp av denna typ automatiskt. Du kan alltid ändra enskilda."}
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Bokföringspost</div>
              <div className="side-card-h">
                {data.amount < 0 ? "Debet" : "Kredit"} ·{" "}
                {data.category_name || "—"}
              </div>
              <div className="side-card-meta">
                {data.account_name} · {SEK(Math.abs(data.amount))} kr · ver
                tx-{data.id}
              </div>
            </div>
          </aside>
        </div>

        <div className="peda" style={{ marginTop: 22 }}>
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            En transaktion är en <em>berättelse</em>.
          </div>
          <p className="peda-prose">
            Datum, plats, belopp — det är ytan. Sammanhanget är allt. När
            du klassar Foodora "efter laxsim" och ser att det hände 3 av
            4 gånger i april, ser du ett mönster du själv kan göra något
            åt: maten innan träning, fryst middag hemma, eller acceptera
            att laxsim-kvällar = take-away.
          </p>
        </div>

      </div>
    </div>
  );
}

function StatCard({
  eye, value, sub, warm,
}: {
  eye: string;
  value: string;
  sub: string;
  warm?: boolean;
}) {
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {eye}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 22,
          fontWeight: 700,
          marginTop: 4,
          color: warm ? "var(--warm)" : "#fff",
          fontStyle: warm ? "italic" : "normal",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function FormField({
  label, children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          color: "var(--text-dim)",
          letterSpacing: "1px",
          textTransform: "uppercase",
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function selectStyle(): React.CSSProperties {
  return {
    width: "100%",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong)",
    color: "#fff",
    padding: "9px 12px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 13,
  };
}
