/**
 * Aktör 08 · Boendemarknaden — elev-vy med två tabbar.
 *
 * Spec: dev/game-motor/06-boendemarknaden.md
 *
 * Tabb 1 · Hyra (befintliga HyresvardenV2-funktionen)
 * Tabb 2 · Köp & sälj (Sprint 5 · B1-B5):
 *   - Min bostads värdering (om eleven äger)
 *   - Listings i elevens stad för aktuell sim-månad
 *   - Köp-knapp per listing
 *   - Sälj-knapp om eleven äger bostad
 *
 * Tidigare URL /v2/hyresvarden styr hit också (bakåt-kompat).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2BoendemarknadActiveHome,
  type V2BoendemarknadListing,
  type V2BoendemarknadListings,
  type V2BoendemarknadValuation,
} from "./api";
import { V2Banner } from "./V2Banner";
import { HyresvardenV2 } from "./HyresvardenV2";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const TYPE_LABEL: Record<V2BoendemarknadListing["type"], string> = {
  bostadsratt: "Bostadsrätt",
  villa: "Villa",
  radhus: "Radhus",
};

type Tab = "hyra" | "kop";

const CURRENT_YM = (() => {
  // Default till nuvarande realmånad — eleven kan ändra.
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
})();


export function BoendemarknadV2() {
  const [tab, setTab] = useState<Tab>("hyra");

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head" style={{ marginBottom: 0 }}>
          <div>
            <span className="pill warm">Aktör 08 · Boendemarknaden</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Boendemarknaden — <em>hyra eller köpa</em>.
            </h1>
            <p className="actor-sub">
              Här ser du ditt nuvarande boende, lediga objekt i din stad
              och kan välja att köpa eller sälja.
            </p>
          </div>
        </header>

        <div
          role="tablist"
          className="boendemarknad-tabs"
          style={{
            display: "flex",
            gap: 12,
            marginTop: 24,
            marginBottom: 24,
            borderBottom: "1px solid var(--border)",
          }}
        >
          <button
            role="tab"
            aria-selected={tab === "hyra"}
            className={`tab-btn ${tab === "hyra" ? "active" : ""}`}
            onClick={() => setTab("hyra")}
            style={tabBtnStyle(tab === "hyra")}
          >
            Hyresavtal & värd
          </button>
          <button
            role="tab"
            aria-selected={tab === "kop"}
            className={`tab-btn ${tab === "kop" ? "active" : ""}`}
            onClick={() => setTab("kop")}
            style={tabBtnStyle(tab === "kop")}
          >
            Köpa eller sälja
          </button>
        </div>

        {tab === "hyra" ? <HyresvardenInline /> : <KopSaljPanel />}
      </div>
    </div>
  );
}

function tabBtnStyle(active: boolean): React.CSSProperties {
  return {
    padding: "10px 18px",
    background: "transparent",
    border: "none",
    borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
    color: active ? "var(--text)" : "var(--text-mid)",
    fontWeight: active ? 600 : 400,
    cursor: "pointer",
    fontSize: "0.95rem",
  };
}


/**
 * Wrappar HyresvardenV2 utan dess egna shell+banner+actor-back så vi
 * får samma sub-content men i tab-läge.
 *
 * För enkelhet i Sprint 5 kör vi HyresvardenV2 som-är. Den har egen
 * V2Banner + actor-back vilket dubblerar lite, men funktionellt
 * fungerar det. En uppstädning kommer i Sprint 6.
 */
function HyresvardenInline() {
  return <HyresvardenV2 />;
}


function KopSaljPanel() {
  const [ym, setYm] = useState(CURRENT_YM);
  const [listings, setListings] = useState<V2BoendemarknadListings | null>(null);
  const [valuation, setValuation] = useState<V2BoendemarknadValuation | null>(null);
  const [activeHome, setActiveHome] = useState<V2BoendemarknadActiveHome | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);

  const refresh = (targetYm: string) => {
    setLoading(true);
    setError(null);
    Promise.all([
      v2Api.boendemarknadListings(targetYm, 6, true),
      v2Api.boendemarknadValuation(targetYm),
      v2Api.boendemarknadMyHome(targetYm).catch(() => null),
    ])
      .then(([ls, val, home]) => {
        setListings(ls);
        setValuation(val);
        setActiveHome(home);
      })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh(ym);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ym]);

  const handleTerminate = async () => {
    if (!confirm("Säga upp ditt hyreskontrakt? Du har 3 mån uppsägningstid.")) {
      return;
    }
    try {
      const r = await v2Api.boendemarknadTerminate({ year_month: ym });
      setConfirmMsg(
        `Uppsägning registrerad. Du måste flytta ut senast ${r.termination_date} ` +
          `(${r.months_until_termination} mån kvar).`,
      );
      refresh(ym);
    } catch (e) {
      setConfirmMsg(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  const handleBuy = async (listing: V2BoendemarknadListing) => {
    setConfirmId(listing.listing_id);
    setConfirmMsg(null);
    try {
      const result = await v2Api.boendemarknadBuy(listing.listing_id, {
        year_month: ym,
        listing_id: listing.listing_id,
      });
      if (result.accepted) {
        setConfirmMsg(
          `Köpet godkänt! Lån #${result.loan_id} skapat. ` +
            `Månadskostnad ${SEK(result.monthly_cost)} kr · ` +
            `kontantinsats ${SEK(result.cash_required)} kr.`,
        );
        // Refresh valuation
        v2Api.boendemarknadValuation(ym).then(setValuation).catch(() => {});
      } else {
        setConfirmMsg(`Köpet avslogs: ${result.error || "okänd anledning"}`);
      }
    } catch (e) {
      setConfirmMsg(`Fel vid köp: ${String((e as Error).message || e)}`);
    } finally {
      setConfirmId(null);
    }
  };

  const handleSell = async () => {
    if (!confirm("Vill du verkligen lägga ut din bostad till försäljning?")) {
      return;
    }
    try {
      const result = await v2Api.boendemarknadSell({ year_month: ym });
      setConfirmMsg(
        `Försäljnings-uppdrag skapat. Estimerade pengar efter kostnader: ` +
          `${SEK(result.estimated_proceeds_after_costs)} kr ` +
          `(försäljningstid ca ${result.sell_horizon_months} mån).`,
      );
    } catch (e) {
      setConfirmMsg(`Fel vid försäljning: ${String((e as Error).message || e)}`);
    }
  };

  const cityName = listings?.city_display || "din stad";

  return (
    <div className="boendemarknad-kop">
      <header style={{ marginBottom: 16, display: "flex", gap: 16, alignItems: "center" }}>
        <label>
          Spelmånad:&nbsp;
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value || CURRENT_YM)}
          />
        </label>
        {listings && (
          <span style={{ color: "var(--text-mid)" }}>
            Snittpris i {cityName}: <strong>{SEK(listings.market_price_per_kvm)} kr/kvm</strong>
          </span>
        )}
      </header>

      {/* MIN AKTIVA BOSTAD (Sprint 5b · ActiveHome) */}
      {activeHome && (
        <section
          className="acct"
          style={{
            marginBottom: 16,
            background:
              activeHome.status === "notice_given"
                ? "rgba(255, 200, 60, 0.08)"
                : activeHome.status === "selling"
                  ? "rgba(120, 180, 255, 0.08)"
                  : undefined,
            border:
              activeHome.status === "notice_given"
                ? "1px solid rgba(255, 200, 60, 0.4)"
                : "1px solid var(--border)",
            borderRadius: 8,
            padding: 14,
          }}
        >
          <div>
            <div className="acct-eye">Mitt boende just nu</div>
            <div className="acct-name">
              {activeHome.home_type === "hyresratt"
                ? "Hyresrätt"
                : activeHome.home_type === "bostadsratt"
                  ? "Bostadsrätt"
                  : activeHome.home_type === "villa"
                    ? "Villa"
                    : "Radhus"}{" "}
              · {activeHome.size_kvm} kvm · {activeHome.rooms} rum
            </div>
            <div className="acct-num" style={{ marginTop: 4 }}>
              {activeHome.address || "Ingen adress satt"} · hyra/avgift{" "}
              <strong>{SEK(activeHome.monthly_cost)} kr/mån</strong>
            </div>
            {activeHome.status === "notice_given" && (
              <div
                style={{
                  marginTop: 10,
                  padding: 10,
                  background: "rgba(255, 200, 60, 0.18)",
                  borderRadius: 6,
                }}
              >
                <strong>⚠ Uppsagd</strong> — du måste flytta ut senast{" "}
                <strong>{activeHome.termination_date}</strong>. Hitta nytt
                boende nedan eller köp en bostadsrätt.
              </div>
            )}
            {activeHome.status === "selling" && (
              <div
                style={{
                  marginTop: 10,
                  padding: 10,
                  background: "rgba(120, 180, 255, 0.18)",
                  borderRadius: 6,
                }}
              >
                Bostaden är ute till försäljning · estimerad slutdatum{" "}
                <strong>{activeHome.estimated_sale_date}</strong>.
              </div>
            )}
            {activeHome.status === "active" &&
              activeHome.home_type === "hyresratt" && (
                <button
                  onClick={handleTerminate}
                  style={{ marginTop: 12 }}
                  className="btn-secondary"
                >
                  Säg upp hyreskontraktet (3 mån)
                </button>
              )}
          </div>
        </section>
      )}

      {/* MIN ÄGDA BOSTAD VÄRDERING */}
      <section className="acct" style={{ marginBottom: 24 }}>
        <div>
          <div className="acct-eye">Värdering</div>
          {valuation?.has_owned_home ? (
            <>
              <div className="acct-name">
                Värdering: {SEK(valuation.current_value || 0)} kr
              </div>
              <div className="acct-num">
                Köppris {SEK(valuation.purchase_price || 0)} kr · lån{" "}
                {SEK(valuation.loan_balance || 0)} kr · eget kapital{" "}
                <strong>{SEK(valuation.equity || 0)} kr</strong>
              </div>
              {(valuation.unrealized_gain ?? 0) !== 0 && (
                <div
                  className="acct-num"
                  style={{
                    color:
                      (valuation.unrealized_gain ?? 0) > 0
                        ? "var(--success, #2a8)"
                        : "var(--danger, #c44)",
                  }}
                >
                  Orealiserad{" "}
                  {(valuation.unrealized_gain ?? 0) > 0 ? "vinst" : "förlust"}:{" "}
                  {SEK(Math.abs(valuation.unrealized_gain || 0))} kr
                </div>
              )}
              <button
                onClick={handleSell}
                style={{ marginTop: 12 }}
                className="btn-secondary"
              >
                Sälj min bostad
              </button>
            </>
          ) : (
            <>
              <div className="acct-name">Du hyr</div>
              <div className="acct-num">
                {valuation?.note || "Ingen värdering — du har inget eget boende."}
              </div>
            </>
          )}
        </div>
      </section>

      {/* CONFIRM-MESSAGE */}
      {confirmMsg && (
        <div
          style={{
            background: "var(--surface-2, #f5f5f7)",
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
            border: "1px solid var(--border)",
          }}
        >
          {confirmMsg}
        </div>
      )}

      {/* LISTINGS */}
      <h2 style={{ fontSize: "1.2rem", marginBottom: 12 }}>
        Lediga objekt i {cityName}
      </h2>

      {loading && <div>Laddar listings…</div>}
      {error && <div style={{ color: "var(--danger)" }}>Fel: {error}</div>}
      {!loading && !error && listings && listings.listings.length === 0 && (
        <div>Inga objekt ute denna månad. Prova en annan månad.</div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 16,
        }}
      >
        {listings?.listings.map((l) => (
          <article
            key={l.listing_id}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 12,
              padding: 16,
              background: "var(--surface, #fff)",
            }}
          >
            <header style={{ marginBottom: 8 }}>
              <span
                className="pill"
                style={{ fontSize: "0.75rem", marginBottom: 4 }}
              >
                {TYPE_LABEL[l.type]}
              </span>
              <h3 style={{ margin: "6px 0 2px", fontSize: "1.05rem" }}>
                {l.address}
              </h3>
              <div style={{ color: "var(--text-mid)", fontSize: "0.85rem" }}>
                {l.size_kvm} kvm · {l.rooms} rum · kvalitet {l.quality_score}/10
              </div>
            </header>

            <div style={{ marginBottom: 8 }}>
              <strong style={{ fontSize: "1.1rem" }}>
                {SEK(l.asking_price)} kr
              </strong>
              <div style={{ fontSize: "0.8rem", color: "var(--text-mid)" }}>
                Avgift/drift: {SEK(l.monthly_avgift)} kr/mån ·{" "}
                {Math.round(l.asking_price / l.size_kvm).toLocaleString("sv-SE")} kr/kvm
              </div>
            </div>

            <p style={{ fontSize: "0.85rem", color: "var(--text-mid)" }}>
              {l.description}
            </p>

            <button
              onClick={() => handleBuy(l)}
              disabled={confirmId === l.listing_id}
              style={{
                width: "100%",
                marginTop: 10,
                padding: "10px",
                background: "var(--accent, #0066cc)",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: confirmId === l.listing_id ? "wait" : "pointer",
              }}
            >
              {confirmId === l.listing_id ? "Behandlar…" : "Köp"}
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}
