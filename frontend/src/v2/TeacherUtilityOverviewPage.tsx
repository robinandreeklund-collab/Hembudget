/**
 * Lärar-vy · full insyn i en elevs förbruknings-aktör.
 *
 * Använder /v2/teacher/students/{id}/utility-overview som returnerar:
 * - summary (active_count, total_monthly_cost, last_month_cost,
 *   has_spot_pricing, binding_expiring_soon, suggested_savings_monthly)
 * - alla subscriptions
 * - alla utility_readings (12 mån)
 *
 * Lärare kan också:
 * - Seedа default-katalogen (6 svenska abonnemang)
 * - Skapa månadsfaktura (UtilityReading) för simulering
 * - Ta bort månadsfaktura
 *
 * Routas via /teacher/v2/utility/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherUtilityOverview,
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

const CATEGORY_LABEL: Record<string, string> = {
  electricity: "El",
  broadband: "Bredband",
  mobile: "Mobil",
  streaming: "Streaming",
  transport: "Transport",
  water: "Vatten",
  heating: "Värme",
  ovrig: "Övrigt",
};

const STATUS_LABEL: Record<string, string> = {
  active: "Aktiv",
  cancelled: "Avbruten",
  considered: "Övervägs",
};

export function TeacherUtilityOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherUtilityOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  // Reading-form
  const [readingSupplier, setReadingSupplier] = useState("Tibber");
  const [readingMeter, setReadingMeter] =
    useState<"electricity" | "broadband" | "water" | "heating">(
      "electricity",
    );
  const [readingPeriodStart, setReadingPeriodStart] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1)
      .toISOString()
      .slice(0, 10),
  );
  const [readingPeriodEnd, setReadingPeriodEnd] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [readingConsumption, setReadingConsumption] = useState("");
  const [readingCost, setReadingCost] = useState("");
  const [readingError, setReadingError] = useState<string | null>(null);
  const [readingSubmitting, setReadingSubmitting] = useState(false);

  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return v2Api
      .teacherUtilityOverview(sid)
      .then((d) => setData(d))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  async function seedDefault() {
    setSeeding(true);
    setSeedMessage(null);
    try {
      const r = await v2Api.teacherSeedDefaultUtility(sid);
      setSeedMessage(
        `+${r.subscriptions_created} default-abonnemang seedade`,
      );
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeeding(false);
    }
  }

  async function addReading() {
    setReadingError(null);
    if (!readingSupplier.trim()) {
      setReadingError("Ange leverantör");
      return;
    }
    const cost = parseFloat(
      readingCost.replace(/\s/g, "").replace(",", "."),
    );
    if (isNaN(cost) || cost < 0) {
      setReadingError("Ogiltig kostnad");
      return;
    }
    const consumption = readingConsumption
      ? parseFloat(
          readingConsumption.replace(/\s/g, "").replace(",", "."),
        )
      : undefined;
    if (consumption != null && isNaN(consumption)) {
      setReadingError("Ogiltig förbrukning");
      return;
    }
    setReadingSubmitting(true);
    try {
      await v2Api.teacherCreateUtilityReading(sid, {
        supplier: readingSupplier.trim(),
        meter_type: readingMeter,
        meter_role: readingMeter === "electricity" ? "energy" : "total",
        period_start: readingPeriodStart,
        period_end: readingPeriodEnd,
        consumption,
        consumption_unit:
          readingMeter === "electricity"
            ? "kWh"
            : readingMeter === "broadband"
            ? "GB"
            : readingMeter === "water"
            ? "m³"
            : undefined,
        cost_kr: cost,
      });
      setReadingConsumption("");
      setReadingCost("");
      await refresh();
    } catch (e) {
      setReadingError(String((e as Error)?.message || e));
    } finally {
      setReadingSubmitting(false);
    }
  }

  async function deleteReading(readingId: number) {
    if (!confirm("Ta bort månadsfaktura?")) return;
    try {
      await v2Api.teacherDeleteUtilityReading(sid, readingId);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda förbruknings-data
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
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">Laddar förbruknings-profil…</div>
      </div>
    );
  }

  const s = data.summary;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
        >
          Tillbaka till klass-hubben
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Lärar-vy · Förbrukning</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>förbruknings-portfölj</em>.
            </h1>
            <p className="actor-sub">
              Aktiva abonnemang, månadsfakturor (kWh + kr), bindningstider
              och besparings-potential. Allt påverkar wellbeing-pentagonen.
            </p>
          </div>
          <div className="actor-meta">
            Aktiva: <strong>{s.active_count}</strong>
            <br />
            Totalt: <strong>{SEK(s.total_monthly_cost)} kr/mån</strong>
            <br />
            Spotpris: <strong>{s.has_spot_pricing ? "Ja" : "Nej"}</strong>
          </div>
        </header>

        {seedMessage && (
          <div
            style={{
              padding: "10px 16px",
              border: "1px solid rgba(110,231,183,0.4)",
              background: "rgba(110,231,183,0.06)",
              borderRadius: 6,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#6ee7b7",
              marginBottom: 18,
              letterSpacing: "0.6px",
            }}
          >
            ● {seedMessage}
          </div>
        )}

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Aktiva abonnemang</div>
              <div className="acct-name">{s.active_count}</div>
              <div className="acct-num">
                {SEK(s.total_monthly_cost)} kr/mån
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.total_grid_fee)}</div>
              <div className="acct-bal-meta">grid-fees</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Senaste månad</div>
              <div className="acct-name">
                {SEK(s.last_month_cost)} kr
              </div>
              <div className="acct-num">
                {s.last_month_kwh > 0
                  ? `${s.last_month_kwh} kWh el`
                  : "ingen el-data"}
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: s.has_spot_pricing ? "var(--warm)" : "#fff" }}
              >
                {s.has_spot_pricing ? "✓" : "—"}
              </div>
              <div className="acct-bal-meta">spotpris</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Bindning</div>
              <div
                className="acct-name"
                style={{
                  color:
                    s.binding_expiring_soon > 0 ? "#fda594" : "#fff",
                }}
              >
                {s.binding_expiring_soon} utgår snart
              </div>
              <div className="acct-num">inom 30 dgr</div>
            </div>
            <div>
              <div className="acct-bal">
                {SEK(s.suggested_savings_monthly)}
              </div>
              <div className="acct-bal-meta">möjlig besparing</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div className="acct-name" style={{ color: "var(--warm)" }}>
                {s.active_count >= 3 ? "+3" : "0"}
              </div>
              <div className="acct-num">safety-bonus</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--warm)" }}
              >
                {s.has_spot_pricing ? "+1" : "0"}
              </div>
              <div className="acct-bal-meta">economy</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* SUBSCRIPTIONS */}
            <div className="section-eye">
              Subscriptions ({data.subscriptions.length})
            </div>
            {data.subscriptions.length === 0 ? (
              <div
                style={{
                  padding: "20px 24px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 16,
                }}
              >
                Inga abonnemang. Klicka "Seedа default-katalogen" för 6
                svenska abonnemang (Tibber, Stockholmshem, Telia bredband +
                mobil, Spotify, SL).
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "120px 1fr 100px 80px 100px 90px",
                  }}
                >
                  <span>Leverantör</span>
                  <span>Namn / kategori</span>
                  <span>Kr/mån</span>
                  <span>Spot</span>
                  <span>Bindning</span>
                  <span>Status</span>
                </div>
                {data.subscriptions.map((u) => (
                  <div
                    className="biz-table-row"
                    key={u.id}
                    style={{
                      gridTemplateColumns:
                        "120px 1fr 100px 80px 100px 90px",
                    }}
                  >
                    <span
                      style={{ fontFamily: "var(--serif)", fontSize: 13 }}
                    >
                      {u.supplier}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {u.name} · {CATEGORY_LABEL[u.category] || u.category}
                      {u.included_in_rent && (
                        <span
                          style={{
                            marginLeft: 6,
                            color: "var(--warm)",
                            fontSize: 9,
                            letterSpacing: "1px",
                            textTransform: "uppercase",
                          }}
                        >
                          ingår i hyran
                        </span>
                      )}
                    </span>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 12 }}
                    >
                      {SEK(u.monthly_cost)}
                      {u.grid_fee_monthly && u.grid_fee_monthly > 0
                        ? ` +${SEK(u.grid_fee_monthly)} fast`
                        : ""}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: u.spot_pricing ? "var(--warm)" : "var(--text-dim)",
                      }}
                    >
                      {u.spot_pricing ? "✓" : "—"}
                    </span>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 10 }}
                    >
                      {u.binding_end ? SHORT_DATE(u.binding_end) : "—"}
                    </span>
                    <span
                      className={`biz-status ${
                        u.status === "active"
                          ? "delta-up"
                          : u.status === "cancelled"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {STATUS_LABEL[u.status] || u.status}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <button
              type="button"
              className="cta-btn"
              disabled={seeding}
              onClick={seedDefault}
              style={{ marginRight: 8, marginBottom: 22 }}
            >
              {seeding
                ? "Seedar…"
                : "Seedа default-katalog (6 svenska abonnemang)"}
            </button>

            {/* READINGS */}
            <div className="section-eye">
              Månadsfakturor / avläsningar ({data.readings.length})
            </div>
            {data.readings.length === 0 ? (
              <div
                style={{
                  padding: "20px 24px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 16,
                }}
              >
                Inga månadsfakturor. Lägg in en nedan för att simulera
                el-räkning eller bredbandsfaktura.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 130px 120px 100px 100px 50px",
                  }}
                >
                  <span>Period</span>
                  <span>Leverantör</span>
                  <span>Typ / roll</span>
                  <span>Förbrukning</span>
                  <span>Kostnad</span>
                  <span></span>
                </div>
                {data.readings.map((r) => (
                  <div
                    className="biz-table-row"
                    key={r.id}
                    style={{
                      gridTemplateColumns:
                        "100px 130px 120px 100px 100px 50px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(r.period_end)}
                    </span>
                    <span
                      style={{ fontFamily: "var(--serif)", fontSize: 13 }}
                    >
                      {r.supplier}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {r.meter_type} · {r.meter_role}
                    </span>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 12 }}
                    >
                      {r.consumption
                        ? `${r.consumption} ${r.consumption_unit || ""}`
                        : "—"}
                    </span>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 12 }}
                    >
                      {SEK(r.cost_kr)} kr
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteReading(r.id)}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--line-strong)",
                        color: "var(--text-mid)",
                        padding: "4px 8px",
                        borderRadius: 100,
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        textTransform: "uppercase",
                        letterSpacing: "0.6px",
                        cursor: "pointer",
                      }}
                    >
                      X
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* SKAPA READING */}
            <div
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "16px 20px",
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
                ● Lägg till månadsfaktura (simulera)
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 130px 130px",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <input
                  placeholder="Leverantör (Tibber...)"
                  value={readingSupplier}
                  onChange={(e) => setReadingSupplier(e.target.value)}
                  style={inputStyle()}
                />
                <select
                  value={readingMeter}
                  onChange={(e) =>
                    setReadingMeter(e.target.value as typeof readingMeter)
                  }
                  style={inputStyle()}
                >
                  <option value="electricity">Electricity (kWh)</option>
                  <option value="broadband">Broadband (GB)</option>
                  <option value="water">Water (m³)</option>
                  <option value="heating">Heating</option>
                </select>
                <input
                  type="date"
                  value={readingPeriodStart}
                  onChange={(e) => setReadingPeriodStart(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="date"
                  value={readingPeriodEnd}
                  onChange={(e) => setReadingPeriodEnd(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <input
                  type="number"
                  placeholder="Förbrukning (184 kWh ...)"
                  value={readingConsumption}
                  onChange={(e) => setReadingConsumption(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Kostnad (812 kr)"
                  value={readingCost}
                  onChange={(e) => setReadingCost(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              {readingError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {readingError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={readingSubmitting}
                onClick={addReading}
              >
                {readingSubmitting ? "Sparar…" : "Spara månadsfaktura"}
              </button>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Förbrukning <em>räknas</em>
              </div>
              <div className="side-card-meta">
                3+ aktiva abonnemang +3 safety. Spotpris-el +1 economy.
                Total &gt; 1500 kr/mån belastar economy. Bindning som
                utgår &lt; 30 dgr loggas som growth-möjlighet.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Möjlig besparing</div>
              <div className="side-card-h">
                {SEK(s.suggested_savings_monthly)} kr/mån
              </div>
              <div className="side-card-meta">
                Heuristik: bredband &gt; 350 (-80), mobil &gt; 99 utan
                bindning (-50), Spotify utan familj-konto (-20), spotpris-el
                (-50). Eleven kan agera på dessa.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Förbrukning är <em>fast i form</em>
              </div>
              <div className="side-card-meta">
                El, mobil, internet — du måste ha dem. Men priset är
                förhandlingsbart. Skilj på "vad" (måste) från "hur mycket"
                (val). Det första lär sig eleven inte påverka. Det andra är
                hela pengen.
              </div>
            </div>
          </aside>
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
