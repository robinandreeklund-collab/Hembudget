/**
 * Aktör 07 · Förbrukning — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (Förbrukning-sektionen):
 * - actor-head med pill, total april + el + övrigt
 * - acct-grid med 4 huvud-abonnemang (el, värme/vatten, bredband, mobil)
 * - el-historik · senaste 6 mån (UtilityReading)
 * - andra abonnemang & löpande (subscriptions med category != electricity)
 * - aside med spotpris-tips, säsong-mönster, bindningstid-varning, möjlig
 *   besparing
 * - peda-block "Förbrukning är fast i form, rörlig i siffra"
 *
 * All data hämtas via GET /v2/forbrukning. Eleven kan
 * skapa/uppdatera/avbryta egna subscriptions.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2UtilityData,
  type V2UtilityCategory,
  type V2UtilitySubStatus,
  type V2UtilitySubscriptionOut,
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

const MONTH_LABEL = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    month: "short",
    year: "numeric",
  });
};

const CATEGORY_HINT: Record<V2UtilityCategory, string> = {
  electricity: "El + nät + skatt",
  broadband: "Internet hemma",
  mobile: "Mobil-abonnemang",
  streaming: "Musik/film/podcast",
  transport: "Resor + bilen",
  water: "Vatten + avlopp",
  heating: "Värme + fjärrvärme",
  ovrig: "Övriga abonnemang",
};

export function ForbrukningV2() {
  const [data, setData] = useState<V2UtilityData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<number>>(new Set());

  // Lägg till-form
  const [addOpen, setAddOpen] = useState(false);
  const [newSupplier, setNewSupplier] = useState("");
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] =
    useState<V2UtilityCategory>("streaming");
  const [newCost, setNewCost] = useState("");
  const [newSpot, setNewSpot] = useState(false);
  const [newBindingEnd, setNewBindingEnd] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh(): Promise<void> {
    return v2Api
      .forbrukning()
      .then((d) => setData(d))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function changeStatus(
    sub: V2UtilitySubscriptionOut,
    status: V2UtilitySubStatus,
  ) {
    setBusy((s) => new Set(s).add(sub.id));
    try {
      await v2Api.utilityPatchSubscription(sub.id, { status });
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusy((s) => {
        const next = new Set(s);
        next.delete(sub.id);
        return next;
      });
    }
  }

  async function deleteSub(sub: V2UtilitySubscriptionOut) {
    if (!confirm(`Ta bort ${sub.supplier} ${sub.name}?`)) return;
    setBusy((s) => new Set(s).add(sub.id));
    try {
      await v2Api.utilityDeleteSubscription(sub.id);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusy((s) => {
        const next = new Set(s);
        next.delete(sub.id);
        return next;
      });
    }
  }

  async function addSubscription() {
    setAddError(null);
    if (!newSupplier.trim() || !newName.trim()) {
      setAddError("Ange leverantör och namn");
      return;
    }
    const cost = parseFloat(newCost.replace(/\s/g, "").replace(",", "."));
    if (isNaN(cost) || cost < 0) {
      setAddError("Ogiltig månadskostnad");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.utilityCreateSubscription({
        supplier: newSupplier.trim(),
        name: newName.trim(),
        category: newCategory,
        monthly_cost: cost,
        spot_pricing: newSpot,
        binding_end: newBindingEnd || undefined,
        status: "active",
      });
      setNewSupplier("");
      setNewName("");
      setNewCost("");
      setNewSpot(false);
      setNewBindingEnd("");
      setAddOpen(false);
      await refresh();
    } catch (e) {
      setAddError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
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
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar förbrukning…</div>
      </div>
    );
  }

  const { summary, subscriptions, readings } = data;

  // El-faktura-historik (electricity readings, energy/total) sorterade nyast först
  const electricityReadings = readings
    .filter(
      (r) =>
        r.meter_type === "electricity" &&
        (r.meter_role === "energy" || r.meter_role === "total"),
    )
    .slice(0, 6);

  // Topp-4 huvudabonnemang för acct-grid: prioritera el, värme, bredband, mobil
  const featured: V2UtilitySubscriptionOut[] = [];
  for (const cat of [
    "electricity",
    "heating",
    "water",
    "broadband",
    "mobile",
  ] as V2UtilityCategory[]) {
    const found = subscriptions.find(
      (s) => s.category === cat && s.status === "active",
    );
    if (found && featured.length < 4) featured.push(found);
  }

  const otherActive = subscriptions.filter(
    (s) =>
      s.status === "active" && !featured.some((f) => f.id === s.id),
  );

  const considered = subscriptions.filter((s) => s.status === "considered");
  const cancelled = subscriptions.filter((s) => s.status === "cancelled");

  // Senaste el-faktura för actor-meta
  const latestElectricityCost = electricityReadings.length
    ? electricityReadings[0].cost_kr
    : 0;
  const otherMonthly =
    summary.total_monthly_cost + summary.total_grid_fee
    - latestElectricityCost;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 07 · Förbrukning</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              El, värme, vatten — <em>det löpande</em>.
            </h1>
            <p className="actor-sub">
              {summary.has_spot_pricing
                ? "Spotpris-el · "
                : "Fast el-pris · "}
              {summary.active_count} aktiva abonnemang ·{" "}
              {summary.binding_expiring_soon > 0
                ? `${summary.binding_expiring_soon} bindning utgår snart`
                : "ingen bindning utgår snart"}
            </p>
          </div>
          <div className="actor-meta">
            Senaste mån:{" "}
            <strong>
              {SEK(
                summary.last_month_cost > 0
                  ? summary.last_month_cost
                  : summary.total_monthly_cost + summary.total_grid_fee,
              )}{" "}
              kr
            </strong>
            <br />
            El: <strong>{SEK(latestElectricityCost)} kr</strong>
            <br />
            Övrigt: <strong>{SEK(Math.max(0, otherMonthly))} kr</strong>
          </div>
        </header>

        {/* HUVUDABONNEMANG · acct-grid 4 kolumner */}
        <div
          className="acct-grid"
          style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
        >
          {featured.length === 0 ? (
            <div
              style={{
                gridColumn: "1 / -1",
                padding: "20px 24px",
                border: "1px solid var(--line)",
                borderRadius: 6,
                fontFamily: "var(--serif)",
                color: "var(--text-mid)",
              }}
            >
              Inga abonnemang seedade. Be läraren köra
              "Seedа default-katalog" — eller lägg till via
              "+ Lägg till abonnemang" nedan.
            </div>
          ) : (
            featured.map((u) => {
              const isSpot = u.spot_pricing;
              const inRent = u.included_in_rent;
              const cost = inRent
                ? "— ingår"
                : isSpot
                ? `${SEK(u.grid_fee_monthly || 0)} fast + spot`
                : `${SEK(u.monthly_cost)}`;
              return (
                <div
                  key={u.id}
                  className="acct"
                  style={
                    isSpot
                      ? {
                          borderColor: "rgba(251,191,36,0.4)",
                          background: "rgba(251,191,36,0.04)",
                        }
                      : undefined
                  }
                >
                  <div>
                    <div
                      className="acct-eye"
                      style={isSpot ? { color: "var(--warm)" } : undefined}
                    >
                      {u.supplier}
                      {isSpot ? " · spotpris" : ""}
                    </div>
                    <div className="acct-name">{u.name}</div>
                    <div className="acct-num">
                      {CATEGORY_HINT[u.category]}
                      {u.binding_end
                        ? ` · binding t.o.m. ${SHORT_DATE(u.binding_end)}`
                        : ""}
                    </div>
                  </div>
                  <div>
                    <div
                      className="acct-bal"
                      style={inRent ? { color: "var(--text-dim)" } : undefined}
                    >
                      {inRent ? (
                        cost
                      ) : isSpot ? (
                        <em>{cost}</em>
                      ) : (
                        cost
                      )}
                    </div>
                    <div className="acct-bal-meta">
                      {u.invoice_day
                        ? `faktura ${u.invoice_day}:e`
                        : inRent
                        ? "i hyran"
                        : "månadsvis"}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="act-grid" style={{ marginTop: 22 }}>
          <div>
            {/* EL-HISTORIK */}
            <div className="section-eye">
              El-historik · senaste 6 mån (Tibber spotpris)
            </div>
            {electricityReadings.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 18,
                }}
              >
                Ingen el-historik registrerad än. Be läraren lägga in en
                månadsfaktura så ser du kWh + kostnad här.
              </div>
            ) : (
              <div className="tx-list">
                {electricityReadings.map((r) => {
                  const kwh = r.consumption ? Number(r.consumption) : 0;
                  const pricePerKwh = kwh
                    ? Math.max(0, (r.cost_kr - 320 - 56) / kwh)
                    : 0;
                  return (
                    <div
                      key={r.id}
                      className="tx-row"
                      style={{
                        gridTemplateColumns: "80px 1fr 100px 100px",
                      }}
                    >
                      <span className="tx-date">
                        {MONTH_LABEL(r.period_end)}
                      </span>
                      <div>
                        <div className="tx-name">
                          {kwh
                            ? `${kwh} kWh · ${pricePerKwh.toFixed(2)} kr/kWh`
                            : "—"}
                        </div>
                        <div className="tx-name-sub">
                          {r.notes ||
                            "+ nätavgift Ellevio 320 + skatt 56"}
                        </div>
                      </div>
                      <span
                        style={{ fontFamily: "var(--mono)", fontSize: 11 }}
                      >
                        {SEK(r.cost_kr)} kr
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          color: "var(--text-mid)",
                        }}
                      >
                        {r.source === "manual" ? "lärare" : r.source}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ANDRA ABONNEMANG */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              Andra abonnemang & löpande
            </div>
            {otherActive.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 18,
                }}
              >
                Inga övriga abonnemang.
              </div>
            ) : (
              <div className="tx-list">
                {otherActive.map((u) => (
                  <div
                    key={u.id}
                    className="tx-row"
                    style={{
                      gridTemplateColumns: "1fr 90px 90px 110px",
                    }}
                  >
                    <div>
                      <div className="tx-name">
                        {u.supplier} {u.name}
                      </div>
                      <div className="tx-name-sub">
                        {u.notes || CATEGORY_HINT[u.category]}
                      </div>
                    </div>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
                    >
                      {SEK(u.monthly_cost)}/mån
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {u.invoice_day ? `${u.invoice_day}:e` : "—"}
                    </span>
                    <div
                      style={{
                        display: "flex",
                        gap: 4,
                        justifyContent: "flex-end",
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => changeStatus(u, "cancelled")}
                        disabled={busy.has(u.id)}
                        style={miniBtn("rgba(255,255,255,0.4)")}
                      >
                        Avbryt
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteSub(u)}
                        disabled={busy.has(u.id)}
                        style={miniBtn("rgba(255,255,255,0.3)")}
                      >
                        Ta bort
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ÖVERVÄGS / AVBRUTNA */}
            {(considered.length > 0 || cancelled.length > 0) && (
              <>
                <div className="section-eye" style={{ marginTop: 24 }}>
                  Övervägs / avbrutna
                </div>
                <div
                  style={{
                    padding: "12px 18px",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                    marginBottom: 18,
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 8,
                  }}
                >
                  {[...considered, ...cancelled].map((u) => (
                    <span
                      key={u.id}
                      style={{
                        padding: "4px 10px",
                        border: "1px solid var(--line-strong)",
                        borderRadius: 100,
                      }}
                    >
                      {u.supplier} {u.name} · {u.status}
                      {u.status !== "active" && (
                        <button
                          type="button"
                          onClick={() => changeStatus(u, "active")}
                          disabled={busy.has(u.id)}
                          style={{
                            marginLeft: 6,
                            background: "transparent",
                            border: "none",
                            color: "var(--warm)",
                            cursor: "pointer",
                            fontFamily: "var(--mono)",
                            fontSize: 10,
                          }}
                        >
                          aktivera
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              </>
            )}

            {/* LÄGG TILL */}
            <div style={{ marginTop: 14 }}>
              {!addOpen ? (
                <button
                  type="button"
                  className="cta-btn ghost"
                  onClick={() => setAddOpen(true)}
                >
                  + Lägg till abonnemang
                </button>
              ) : (
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
                    ● Nytt abonnemang
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr 130px",
                      gap: 8,
                      marginBottom: 8,
                    }}
                  >
                    <input
                      placeholder="Leverantör (t.ex. Comviq)"
                      value={newSupplier}
                      onChange={(e) => setNewSupplier(e.target.value)}
                      style={inputStyle()}
                    />
                    <input
                      placeholder="Namn (t.ex. Mobil 5GB)"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      style={inputStyle()}
                    />
                    <input
                      type="number"
                      placeholder="Kr/mån"
                      value={newCost}
                      onChange={(e) => setNewCost(e.target.value)}
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
                    <select
                      value={newCategory}
                      onChange={(e) =>
                        setNewCategory(e.target.value as V2UtilityCategory)
                      }
                      style={inputStyle()}
                    >
                      <option value="electricity">El</option>
                      <option value="heating">Värme</option>
                      <option value="water">Vatten</option>
                      <option value="broadband">Bredband</option>
                      <option value="mobile">Mobil</option>
                      <option value="streaming">Streaming</option>
                      <option value="transport">Transport</option>
                      <option value="ovrig">Övrigt</option>
                    </select>
                    <input
                      type="date"
                      value={newBindingEnd}
                      onChange={(e) => setNewBindingEnd(e.target.value)}
                      style={inputStyle()}
                      placeholder="Bindning t.o.m. (valfritt)"
                    />
                  </div>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--text-mid)",
                      marginBottom: 10,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={newSpot}
                      onChange={(e) => setNewSpot(e.target.checked)}
                    />
                    <span>
                      Spotpris (för el-abonnemang) · ger +1 economy i
                      wellbeing
                    </span>
                  </label>
                  {addError && (
                    <div
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "#fca5a5",
                        marginBottom: 8,
                      }}
                    >
                      {addError}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      className="cta-btn"
                      disabled={submitting}
                      onClick={addSubscription}
                    >
                      {submitting ? "Sparar…" : "Spara"}
                    </button>
                    <button
                      type="button"
                      className="cta-btn ghost"
                      onClick={() => setAddOpen(false)}
                      disabled={submitting}
                    >
                      Avbryt
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Spotpris-tips</div>
              <div className="side-card-h">
                Kör tvätten <em>natten</em>
              </div>
              <div className="side-card-meta">
                02–06 är spotpriset ~ 30 % lägre. Tibber-appen visar realtid
                · sätt timer på diskmaskin/tvätt.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Säsong-mönster</div>
              <div className="side-card-h">Feb är dyrast</div>
              <div className="side-card-meta">
                Februari + januari = ~ 50 % av årets el-kostnad. Buffra
                under sommaren.
              </div>
            </div>
            {summary.binding_expiring_soon > 0 && (
              <div
                className="side-card"
                style={{
                  background: "rgba(220,76,43,0.06)",
                  borderColor: "rgba(220,76,43,0.25)",
                }}
              >
                <div
                  className="side-card-eye"
                  style={{ color: "var(--accent)" }}
                >
                  Bindningstid
                </div>
                <div className="side-card-h">
                  {summary.binding_expiring_soon} abonnemang
                </div>
                <div className="side-card-meta">
                  Slut inom 30 dagar. Du kan byta för billigare alternativ.
                  Sätt påminnelse innan uppsägningstiden går ut.
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Möjlig besparing</div>
              <div className="side-card-h">
                <em>−{SEK(summary.suggested_savings_monthly)} kr/mån</em>
              </div>
              <div className="side-card-meta">
                Spotpris-styrning + omförhandling bredband + familj-Spotify
                = årlig{" "}
                {SEK(summary.suggested_savings_monthly * 12)} kr besparing
                utan att märka.
              </div>
            </div>
          </aside>
        </div>

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Förbrukning är <em>fast i form, rörlig i siffra</em>.
          </div>
          <p className="peda-prose">
            Du <em>kommer</em> ha el, värme, vatten, mobil, bredband — det
            går inte runt. Men du kan påverka <em>hur mycket</em>.
            Spotpris-elen är 70 % lägre nattetid. Bredband kan omförhandlas
            vid bindning slut. Mobilen finns från 49 kr/mån (Comviq). Att
            aktivt managera dessa fyra abonnemang ger ~ 250 kr/mån = 3 000
            kr/år = försäkring du inte behöver.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Spotpris</strong>Real-tids elpris · Tibber-app visar
              per timme.
            </li>
            <li>
              <strong>Nätavgift</strong>Fast oavsett förbrukning · Ellevio i
              Sthlm · ~ 320 kr/mån.
            </li>
            <li>
              <strong>Energiskatt</strong>~ 30 öre/kWh + moms · går till
              statskassan.
            </li>
            <li>
              <strong>Bindningstid</strong>Många abonnemang har 12–24 mån.
              Sätt påminnelse vid slut.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Spotpris</span>
            <span className="peda-concept">Effektavgift</span>
            <span className="peda-concept">Energiskatt</span>
            <span className="peda-concept">Bindningstid</span>
            <span className="peda-concept">Uppsägningstid</span>
            <span className="peda-concept">Variabel kostnad</span>
          </div>
          <div className="peda-tip">
            Pedagogiskt centralt: skilj på <em>vad du måste betala</em> (el
            som finns) och <em>hur mycket du betalar</em> (vilket
            abonnemang, vilken tid). Det första är inte förhandlingsbart.
            Det andra är allt.
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
    textTransform: "uppercase",
    letterSpacing: "0.6px",
    cursor: "pointer",
  };
}
