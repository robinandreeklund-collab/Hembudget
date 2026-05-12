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

type Tab = "hyra" | "hyrmarknad" | "kop";

// Fallback om gameTime-API fail:ar · använder real-tid som
// nödfallback. Riktiga värdet hämtas via useGameYearMonth() nedan.
const REAL_YM_FALLBACK = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
})();

/**
 * Hook som returnerar elevens nuvarande SPEL-månad ("YYYY-MM").
 * Initialvärde = real-tids-månad (för att inte rendera tomt). Pollas
 * mot /v2/game-time vid mount + var 60 sekund (spel-månaden tickar
 * ungefär var 4.3 real-timme så 60s är gott och väl).
 */
function useGameYearMonth(): string {
  const [ym, setYm] = useState(REAL_YM_FALLBACK);
  useEffect(() => {
    let cancelled = false;
    const fetchYm = () => {
      v2Api.gameTime()
        .then((g) => {
          if (!cancelled && g && g.year_month) setYm(g.year_month);
        })
        .catch(() => null);
    };
    fetchYm();
    const interval = setInterval(fetchYm, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);
  return ym;
}


export function BoendemarknadV2() {
  const [tab, setTab] = useState<Tab>("hyra");

  // Auto-välj "kop"-tabben om eleven äger sin bostad — annars
  // landar de på en hyresrätt-vy som säger "Inget registrerat".
  useEffect(() => {
    v2Api.hub()
      .then((h) => {
        const t = h.character.housing_type;
        if (t === "bostadsratt" || t === "villa" || t === "radhus") {
          setTab("kop");
        }
      })
      .catch(() => null);
  }, []);

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
            aria-selected={tab === "hyrmarknad"}
            className={`tab-btn ${tab === "hyrmarknad" ? "active" : ""}`}
            onClick={() => setTab("hyrmarknad")}
            style={tabBtnStyle(tab === "hyrmarknad")}
          >
            Hyr en lägenhet
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

        {tab === "hyra" ? (
          <HyresvardenInline />
        ) : tab === "hyrmarknad" ? (
          <HyrmarknadPanel />
        ) : (
          <KopSaljPanel />
        )}
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
  // embedded · HyresvardenV2 renderar då bara innehållet utan eget
  // V2Banner/shell/back-länk så att Boendemarknad-tabsen ovanför
  // behålls. Annars hijack:as hela layouten och eleven tappar tabsen
  // + back-knappen leder till pentagonen istället för Boendemarknad.
  return <HyresvardenV2 embedded />;
}


function KopSaljPanel() {
  const gameYm = useGameYearMonth();
  const [ym, setYm] = useState(gameYm);
  // Synca om gameYm uppdateras (spel-tiden tickade förbi månadsskifte
  // eller fetchades efter initial render). Eleven kan manuellt välja
  // annan månad i dropdownen — då fryses den vid det valet.
  const [userTouchedYm, setUserTouchedYm] = useState(false);
  useEffect(() => {
    if (!userTouchedYm) setYm(gameYm);
  }, [gameYm, userTouchedYm]);
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
            onChange={(e) => {
              setUserTouchedYm(true);
              setYm(e.target.value || gameYm);
            }}
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
          ) : activeHome && (
            activeHome.home_type === "bostadsratt"
            || activeHome.home_type === "villa"
            || activeHome.home_type === "radhus"
          ) ? (
            <>
              <div className="acct-name">
                {activeHome.home_type === "villa" ? "Villa"
                  : activeHome.home_type === "radhus" ? "Radhus"
                  : "Bostadsrätt"} · {activeHome.size_kvm} kvm
              </div>
              <div className="acct-num">
                Boendekostnad{" "}
                <strong>
                  {SEK(activeHome.monthly_cost)} kr/mån
                </strong>{" "}
                · värdering uppdateras månadsvis baserat på marknad.
              </div>
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
            background: "rgba(110,231,183,0.06)",
            padding: "10px 16px",
            borderRadius: 6,
            marginBottom: 16,
            border: "1px solid rgba(110,231,183,0.4)",
            color: "#6ee7b7",
            fontFamily: "var(--mono)",
            fontSize: 11,
            letterSpacing: "0.4px",
          }}
        >
          ● {confirmMsg}
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
              border: "1px solid var(--line)",
              borderRadius: 8,
              padding: 18,
              background: "rgba(15,21,37,0.7)",
              color: "var(--text)",
            }}
          >
            <header style={{ marginBottom: 12 }}>
              <span
                style={{
                  display: "inline-block",
                  padding: "3px 9px",
                  borderRadius: 100,
                  background: "rgba(220,76,43,0.1)",
                  border: "1px solid var(--accent)",
                  fontFamily: "var(--mono)",
                  fontSize: 9.5,
                  fontWeight: 700,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                  color: "var(--accent)",
                  marginBottom: 8,
                }}
              >
                {TYPE_LABEL[l.type]}
              </span>
              <h3
                style={{
                  margin: "8px 0 4px",
                  fontFamily: "var(--serif)",
                  fontSize: 17,
                  fontWeight: 700,
                  color: "#fff",
                  letterSpacing: "-0.3px",
                }}
              >
                {l.address}
              </h3>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10.5,
                  color: "var(--text-mid)",
                  letterSpacing: "0.4px",
                }}
              >
                {l.size_kvm} kvm · {l.rooms} rum · kvalitet {l.quality_score}/10
              </div>
            </header>

            <div style={{ marginBottom: 12 }}>
              <strong
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 22,
                  fontStyle: "italic",
                  color: "var(--warm)",
                  fontWeight: 700,
                }}
              >
                {SEK(l.asking_price)} kr
              </strong>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10.5,
                  color: "var(--text-mid)",
                  marginTop: 4,
                }}
              >
                Avgift/drift: {SEK(l.monthly_avgift)} kr/mån ·{" "}
                {Math.round(l.asking_price / l.size_kvm).toLocaleString("sv-SE")} kr/kvm
              </div>
            </div>

            <p
              style={{
                fontFamily: "var(--serif)",
                fontSize: 13.5,
                lineHeight: 1.5,
                color: "var(--text)",
                margin: "10px 0 14px",
              }}
            >
              {l.description}
            </p>

            <button
              type="button"
              onClick={() => handleBuy(l)}
              disabled={confirmId === l.listing_id}
              style={{
                width: "100%",
                padding: "10px 18px",
                background: "var(--accent)",
                color: "#fff",
                border: 0,
                borderRadius: 100,
                cursor: confirmId === l.listing_id ? "wait" : "pointer",
                fontFamily: "var(--mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
              }}
            >
              {confirmId === l.listing_id ? "Behandlar…" : "Köp →"}
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}


// ===========================================================
// Hyrmarknad-panel (Fas 3) · 4 tiers från korridor till lyx
// ===========================================================

type RentalListing = {
  listing_id: string;
  city_key: string;
  city_display: string;
  tier: number;
  tier_label: string;
  address: string;
  size_kvm: number;
  rooms: number;
  monthly_rent: number;
  deposit: number;
  first_hand: boolean;
  queue_months: number;
  quality_score: number;
  description: string;
};

const TIER_BG: Record<number, string> = {
  1: "rgba(220,76,43,0.06)",
  2: "rgba(255,255,255,0.04)",
  3: "rgba(110,231,183,0.06)",
  4: "rgba(251,191,36,0.08)",
};
const TIER_BORDER: Record<number, string> = {
  1: "rgba(220,76,43,0.30)",
  2: "rgba(255,255,255,0.18)",
  3: "rgba(110,231,183,0.30)",
  4: "rgba(251,191,36,0.30)",
};
const TIER_HEADER: Record<number, string> = {
  1: "Korridor / akut",
  2: "Liten lägenhet",
  3: "Familjelägenhet",
  4: "Lyx-lägenhet",
};
function queueButtonStyle(
  kind: "queued" | "apply" | "ready",
): React.CSSProperties {
  const palette = {
    queued: { bg: "rgba(167,139,250,0.18)", color: "#c4b5fd", border: "rgba(167,139,250,0.4)" },
    apply: { bg: "rgba(167,139,250,0.10)", color: "#a78bfa", border: "rgba(167,139,250,0.3)" },
    ready: { bg: "#6ee7b7", color: "#0f1525", border: "transparent" },
  }[kind];
  return {
    width: "100%",
    padding: "9px 14px",
    background: palette.bg,
    color: palette.color,
    border: `1px solid ${palette.border}`,
    borderRadius: 100,
    cursor: "pointer",
    fontFamily: "var(--mono)",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "1.2px",
    textTransform: "uppercase" as const,
  };
}


const TIER_WELLBEING: Record<number, string> = {
  1: "⚠ -2 safety/mån · trångt och instabilt",
  2: "Baseline · 0 safety-drift",
  3: "+1 safety/mån · rymligt familjeboende",
  4: "+2 safety/mån · lyx (kostar i ekonomi)",
};

type RentalApplication = {
  id: number;
  listing_id: string;
  address: string;
  tier: number;
  tier_label: string;
  size_kvm: number;
  rooms: number;
  monthly_rent: number;
  deposit: number;
  applied_on: string;
  ready_on: string;
  status: string;
  days_left: number;
};

function HyrmarknadPanel() {
  const gameYm = useGameYearMonth();
  const [ym, setYm] = useState(gameYm);
  // Synca om gameYm uppdateras (spel-tiden tickade förbi månadsskifte
  // eller fetchades efter initial render). Eleven kan manuellt välja
  // annan månad i dropdownen — då fryses den vid det valet.
  const [userTouchedYm, setUserTouchedYm] = useState(false);
  useEffect(() => {
    if (!userTouchedYm) setYm(gameYm);
  }, [gameYm, userTouchedYm]);
  const [listings, setListings] = useState<RentalListing[] | null>(null);
  const [applications, setApplications] = useState<RentalApplication[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  function refresh(targetYm: string) {
    setLoading(true);
    setError(null);
    Promise.all([
      v2Api.boendemarknadListRentals(targetYm),
      v2Api.boendemarknadRentalApplications(),
    ])
      .then(([listed, apps]) => {
        setListings(listed.listings);
        setApplications(apps.applications);
      })
      .catch((e) => setError(String((e as Error)?.message || e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh(ym);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ym]);

  // Slå upp pending app för en listing
  function appFor(listingId: string): RentalApplication | undefined {
    return applications.find(
      (a) => a.listing_id === listingId
        && (a.status === "queued" || a.status === "ready"),
    );
  }

  async function applyForListing(listing: RentalListing) {
    if (!confirm(
      `Ställ dig i kö för ${listing.address}?\n\n`
        + `· ${listing.queue_months} spel-månader kö-tid\n`
        + `· När kön är klar kan du klicka "Flytta in nu"\n`
        + `· Kostar inget att ställa sig i kö`,
    )) return;
    setBusy(listing.listing_id);
    setMsg(null);
    try {
      await v2Api.boendemarknadRentalApply(listing.listing_id, ym);
      setMsg(`✓ Du står nu i kö för ${listing.address}`);
      refresh(ym);
    } catch (e) {
      setMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function cancelApplication(appId: number, address: string) {
    if (!confirm(`Avbryta köandet för ${address}?`)) return;
    try {
      await v2Api.boendemarknadRentalApplicationCancel(appId);
      setMsg(`Du står inte längre i kö för ${address}.`);
      refresh(ym);
    } catch (e) {
      setMsg(`Fel: ${String((e as Error)?.message || e)}`);
    }
  }

  async function moveIn(listing: RentalListing) {
    if (!confirm(
      `Flytta in i ${listing.address}?\n\n`
        + `· ${listing.size_kvm} kvm · ${listing.rooms} rok\n`
        + `· Hyra ${listing.monthly_rent.toLocaleString("sv-SE")} kr/mån\n`
        + `· Deposition ${listing.deposit.toLocaleString("sv-SE")} kr (dras direkt)\n`
        + `· ${listing.first_hand ? "Förstahandskontrakt" : "Andrahandskontrakt"}\n\n`
        + `Wellbeing-effekt: ${TIER_WELLBEING[listing.tier]}\n\n`
        + "OBS: din nuvarande bostad sägs upp · slutfaktura på 3 mån "
        + "av gamla hyran läggs i postlådan.",
    )) return;
    setBusy(listing.listing_id);
    setMsg(null);
    try {
      const r = await v2Api.boendemarknadRentalMoveIn(listing.listing_id, ym);
      const deltas = Object.entries(r.pentagon_deltas)
        .filter(([, v]) => v !== 0)
        .map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`)
        .join(" · ");
      setMsg(`✓ ${r.welcome_message}\nPentagon: ${deltas}`);
      refresh(ym);
    } catch (e) {
      setMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <header style={{ marginBottom: 16, display: "flex", gap: 16, alignItems: "center" }}>
        <label>
          Spelmånad:&nbsp;
          <input
            type="month"
            value={ym}
            onChange={(e) => {
              setUserTouchedYm(true);
              setYm(e.target.value || gameYm);
            }}
          />
        </label>
      </header>

      <p style={{ color: "var(--text-mid)", fontFamily: "var(--serif)", fontSize: 14, marginBottom: 20 }}>
        Hitta en hyresrätt — fyra prisklasser från akut-korridor till lyx.
        Bostadens kvalitet påverkar din wellbeing (safety-axeln) varje månad.
      </p>

      {msg && (
        <div style={{
          padding: "10px 16px", marginBottom: 16, borderRadius: 6,
          border: msg.startsWith("Fel") ? "1px solid rgba(252,165,165,0.4)" : "1px solid rgba(110,231,183,0.4)",
          background: msg.startsWith("Fel") ? "rgba(252,165,165,0.06)" : "rgba(110,231,183,0.06)",
          color: msg.startsWith("Fel") ? "#fca5a5" : "#6ee7b7",
          fontFamily: "var(--mono)", fontSize: 11, whiteSpace: "pre-wrap",
        }}>
          {msg}
        </div>
      )}

      {loading && <div>Laddar lediga lägenheter…</div>}
      {error && <div style={{ color: "var(--danger)" }}>Fel: {error}</div>}

      {/* Mina pending ansökningar */}
      {applications.length > 0 && (
        <section style={{ marginBottom: 28 }}>
          <h3 style={{
            fontFamily: "var(--serif)",
            fontSize: 17,
            color: "#fff",
            marginBottom: 6,
          }}>
            Mina pending ansökningar · <em>{applications.length}</em>
          </h3>
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            {applications.map((app) => (
              <div key={app.id} style={{
                padding: 12,
                background: app.status === "ready"
                  ? "rgba(110,231,183,0.08)"
                  : "rgba(167,139,250,0.06)",
                border: `1px solid ${app.status === "ready"
                  ? "rgba(110,231,183,0.30)"
                  : "rgba(167,139,250,0.25)"}`,
                borderRadius: 8,
                display: "flex",
                gap: 12,
                alignItems: "center",
                flexWrap: "wrap",
              }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <div style={{
                    fontFamily: "var(--serif)",
                    fontSize: 15, fontWeight: 700, color: "#fff",
                  }}>
                    {app.address}
                  </div>
                  <div style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10, color: "var(--text-mid)",
                    letterSpacing: 0.5, marginTop: 4,
                  }}>
                    Tier {app.tier} · {app.size_kvm} kvm · {app.rooms} rok
                    · {SEK(app.monthly_rent)} kr/mån
                    {app.status === "ready"
                      ? " · KLAR ATT FLYTTA IN"
                      : ` · ${app.days_left} dgr kvar`}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => cancelApplication(app.id, app.address)}
                  style={{
                    padding: "6px 12px",
                    background: "transparent",
                    border: "1px solid rgba(255,255,255,0.18)",
                    borderRadius: 100,
                    color: "rgba(255,255,255,0.7)",
                    fontFamily: "var(--mono)",
                    fontSize: 10, letterSpacing: 1, cursor: "pointer",
                    textTransform: "uppercase",
                  }}
                >
                  Avbryt
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {[4, 3, 2, 1].map((tier) => {
        const tierListings = (listings || []).filter((l) => l.tier === tier);
        if (tierListings.length === 0) return null;
        return (
          <section key={tier} style={{ marginBottom: 26 }}>
            <h3 style={{
              fontFamily: "var(--serif)",
              fontSize: 17,
              color: "#fff",
              marginBottom: 6,
            }}>
              Tier {tier} · <em>{TIER_HEADER[tier]}</em>
            </h3>
            <div style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              color: "var(--text-mid)",
              letterSpacing: "0.5px",
              marginBottom: 12,
              textTransform: "uppercase",
            }}>
              {TIER_WELLBEING[tier]}
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 14,
            }}>
              {tierListings.map((l) => (
                <article key={l.listing_id} style={{
                  border: `1px solid ${TIER_BORDER[l.tier]}`,
                  background: TIER_BG[l.tier],
                  borderRadius: 8,
                  padding: 16,
                }}>
                  <div style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    color: "var(--text-mid)",
                    textTransform: "uppercase",
                    marginBottom: 6,
                  }}>
                    {l.first_hand ? "Förstahand" : "Andrahand"} ·
                    {l.queue_months === 0 ? " ledig direkt" : ` ${l.queue_months} mån kö`}
                  </div>
                  <h4 style={{
                    fontFamily: "var(--serif)",
                    fontSize: 16,
                    color: "#fff",
                    margin: "4px 0",
                  }}>
                    {l.address}
                  </h4>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-mid)" }}>
                    {l.size_kvm} kvm · {l.rooms} rok · kvalitet {l.quality_score}/10
                  </div>
                  <div style={{
                    fontFamily: "var(--serif)",
                    fontSize: 22, fontStyle: "italic", fontWeight: 700,
                    color: "var(--warm)", marginTop: 10,
                  }}>
                    {SEK(l.monthly_rent)} kr/mån
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-mid)", marginTop: 4 }}>
                    Deposition {SEK(l.deposit)} kr
                  </div>
                  <p style={{ fontFamily: "var(--serif)", fontSize: 13, color: "var(--text)", margin: "10px 0 12px" }}>
                    {l.description}
                  </p>
                  {(() => {
                    const app = appFor(l.listing_id);
                    // Tre states:
                    //  - I kö (queued) · väntar
                    //  - Klar (ready)  · kan flytta in
                    //  - Ingen app + queue=0 · direkt flytt-in
                    //  - Ingen app + queue>0 · måste applicera först
                    if (app && app.status === "queued") {
                      return (
                        <button
                          type="button"
                          onClick={() => cancelApplication(app.id, l.address)}
                          style={queueButtonStyle("queued")}
                        >
                          {`★ I kö · ${app.days_left} dgr kvar (avbryt)`}
                        </button>
                      );
                    }
                    const isReady = (app && app.status === "ready")
                      || l.queue_months === 0;
                    const needsQueue = !app && l.queue_months > 0;
                    if (needsQueue) {
                      return (
                        <button
                          type="button"
                          onClick={() => applyForListing(l)}
                          disabled={busy === l.listing_id}
                          style={queueButtonStyle("apply")}
                        >
                          {busy === l.listing_id
                            ? "Ställer i kö…"
                            : `Ställ dig i kö · ${l.queue_months} mån →`}
                        </button>
                      );
                    }
                    // Direkt flytt-in (queue=0 eller ready app)
                    return (
                      <button
                        type="button"
                        onClick={() => moveIn(l)}
                        disabled={busy === l.listing_id}
                        style={{
                          width: "100%",
                          padding: "9px 14px",
                          background: isReady && app ? "#6ee7b7" : "var(--accent)",
                          color: isReady && app ? "#0f1525" : "#fff",
                          border: 0,
                          borderRadius: 100,
                          cursor: busy === l.listing_id ? "wait" : "pointer",
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          fontWeight: 700,
                          letterSpacing: "1.2px",
                          textTransform: "uppercase",
                        }}
                      >
                        {busy === l.listing_id
                          ? "Flyttar in…"
                          : (isReady && app ? "Flytta in nu →" : "Flytta in →")}
                      </button>
                    );
                  })()}
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
