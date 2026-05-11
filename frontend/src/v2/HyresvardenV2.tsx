/**
 * Aktör 08 · Hyresvärden — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-hyra):
 * - actor-head med pill, hyra/mån, kr/kvm/år, kontraktstyp
 * - acct-grid · 3 kolumner: Hyresavi (innevarande mån), Bostadssökande
 *   (kö-info), Avtal (typ + uppsägning + tillträde)
 * - Hyresnotiser & brev från värden — tx-list med datum, titel,
 *   undertext, belopp/status
 * - aside · bytesvärde, köpa istället, dynamiskt vid hyreshöjning
 * - peda-block "Hyresrätt är oslagbar ekonomiskt"
 *
 * Eleven kan:
 * - Skapa eget kontrakt (om saknas) eller säga upp aktivt
 * - Se alla notiser från läraren (hyreshöjningar etc)
 *
 * Allt påverkar wellbeing: förstahand +5 safety, tillsvidare +3 safety,
 * andrahand -3, inneboende -2, hyra > 40 % netto -economy, hyreshöjning
 * > 4 % -2 economy.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2RentalData,
  type V2RentalContractType,
  type V2RentalDurationType,
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

const SHORT_DATE_NO_YEAR = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

const CONTRACT_TYPE_LABEL: Record<V2RentalContractType, string> = {
  forsta_hand: "Förstahand",
  andra_hand: "Andrahand",
  inneboende: "Inneboende",
  bostadsratt: "Bostadsrätt",
};

const DURATION_LABEL: Record<V2RentalDurationType, string> = {
  tillsvidare: "Tillsvidare",
  tidsbegransad: "Tidsbegränsad",
};

const NOTICE_TYPE_LABEL: Record<string, string> = {
  hyresavi: "Hyresavi",
  underhall: "Underhåll",
  hyreshojning: "Hyreshöjning",
  trapphusrenovering: "Trapphusrenovering",
  forhandling: "Hyresförhandling",
  brand: "Brandsyn",
  andrahand_ansokan: "Andrahandsansökan",
  ovrig: "Övrigt",
};

/**
 * Hyresvärden · standalone-vy ELLER inbäddad i Boendemarknad.
 *
 * `embedded={true}` används av BoendemarknadV2's "Hyresavtal & värd"-flik
 * — då rendrar vi INTE eget V2Banner/shell/back-länk/header, så att
 * tabs-stripen ovanför behålls och eleven kan klicka tillbaka till
 * "Köpa eller sälja". Tidigare hijack:ade HyresvardenV2 hela layouten
 * → tabs försvann + back-knappen ledde till pentagonen istället för
 * tillbaka till Boendemarknad.
 */
export function HyresvardenV2({ embedded = false }: { embedded?: boolean } = {}) {
  const [data, setData] = useState<V2RentalData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Add-form
  const [addOpen, setAddOpen] = useState(false);
  const [newLandlord, setNewLandlord] = useState("");
  const [newAddress, setNewAddress] = useState("");
  const [newRooms, setNewRooms] = useState("2 r o k");
  const [newArea, setNewArea] = useState("");
  const [newRent, setNewRent] = useState("");
  const [newType, setNewType] =
    useState<V2RentalContractType>("forsta_hand");
  const [newDuration, setNewDuration] =
    useState<V2RentalDurationType>("tillsvidare");
  const [addError, setAddError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh(): Promise<void> {
    return v2Api
      .hyresvarden()
      .then((d) => setData(d))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  const [housingType, setHousingType] = useState<string | null>(null);
  const [housingMonthly, setHousingMonthly] = useState<number | null>(null);

  useEffect(() => {
    refresh();
    // Hämta också hub-data så vi vet om eleven äger eller hyr.
    // Om eleven äger sin bostad ska vi inte säga "Inget registrerat
    // boende" — vi ska visa info om ägt boende istället och hänvisa
    // till köp/sälj-tabben.
    v2Api.hub()
      .then((h) => {
        setHousingType(h.character.housing_type || null);
        setHousingMonthly(h.character.housing_monthly || null);
      })
      .catch(() => null);
  }, []);

  const ownsHome = housingType === "bostadsratt"
    || housingType === "villa"
    || housingType === "radhus";

  async function terminateContract(id: number) {
    if (!confirm("Säg upp kontraktet?")) return;
    try {
      await v2Api.rentalPatchContract(id, { status: "terminated" });
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function addContract() {
    setAddError(null);
    if (!newLandlord.trim() || !newAddress.trim()) {
      setAddError("Ange hyresvärd och adress");
      return;
    }
    const area = parseFloat(newArea.replace(",", "."));
    const rent = parseFloat(newRent.replace(/\s/g, "").replace(",", "."));
    if (isNaN(area) || area <= 0) {
      setAddError("Ange yta i kvm");
      return;
    }
    if (isNaN(rent) || rent < 0) {
      setAddError("Ange månadshyra");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.rentalCreateContract({
        landlord: newLandlord.trim(),
        address: newAddress.trim(),
        rooms_label: newRooms,
        area_sqm: area,
        monthly_rent: rent,
        contract_type: newType,
        duration_type: newDuration,
      });
      setAddOpen(false);
      setNewLandlord("");
      setNewAddress("");
      setNewArea("");
      setNewRent("");
      await refresh();
    } catch (e) {
      setAddError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !data) {
    const inner = (
      <div className="bank-loading">
        <div>
          <div style={{ color: "#fca5a5", marginBottom: 8 }}>
            Kunde inte ladda hyres-data
          </div>
          <pre style={{ fontSize: 11 }}>{error}</pre>
        </div>
      </div>
    );
    if (embedded) return inner;
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        {inner}
      </div>
    );
  }
  if (!data) {
    const inner = <div className="bank-loading">Laddar hyresvärden…</div>;
    if (embedded) return inner;
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        {inner}
      </div>
    );
  }

  const { contract, notices, summary } = data;

  const body = (
    <>
      {!embedded && (
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>
      )}

      <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 08 · Hyresvärden</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {contract ? (
                <>
                  {contract.landlord} — <em>din lägenhet</em>.
                </>
              ) : ownsHome ? (
                <>
                  Du <em>äger din bostad</em>.
                </>
              ) : (
                <>
                  Inget <em>registrerat boende</em>.
                </>
              )}
            </h1>
            <p className="actor-sub">
              {contract
                ? `${contract.rooms_label} · ${contract.area_sqm} m²${
                    contract.district ? ` · ${contract.district}` : ""
                  } · ${
                    CONTRACT_TYPE_LABEL[contract.contract_type]
                  }-kontrakt · tillträtt ${SHORT_DATE(
                    contract.started_on,
                  )}`
                : ownsHome
                ? `${
                    housingType === "villa"
                      ? "Villa"
                      : housingType === "radhus"
                      ? "Radhus"
                      : "Bostadsrätt"
                  } · boendekostnad ${
                    housingMonthly ? SEK(housingMonthly) : "—"
                  } kr/mån (avgift/bolån/drift). Hyresvärden hanterar bara hyresrätter — du har ingen sådan. Se köp/sälj-flikar för bostadsrätt.`
                : "Skapa ett kontrakt nedan eller be läraren seedа Stockholmshem-mallen."}
            </p>
          </div>
          <div className="actor-meta">
            {contract ? (
              <>
                Hyra: <strong>{SEK(contract.monthly_rent)} kr/mån</strong>
                <br />
                Per kvm:{" "}
                <strong>
                  {SEK(summary.rent_per_sqm_yearly)} kr/år
                </strong>
                <br />
                Kontrakt:{" "}
                <strong>
                  {DURATION_LABEL[contract.duration_type].toLowerCase()}
                </strong>
              </>
            ) : (
              <span style={{ color: "var(--text-mid)" }}>—</span>
            )}
          </div>
        </header>

        {/* 3-KORTS ACCT-GRID (matchar prototyp) */}
        {contract && (
          <div
            className="acct-grid"
            style={{ gridTemplateColumns: "repeat(3, 1fr)" }}
          >
            <div className="acct">
              <div>
                <div className="acct-eye">Hyresavi · senaste</div>
                <div className="acct-name">
                  {SEK(contract.monthly_rent)} kr
                </div>
                <div className="acct-num">
                  {contract.ocr_reference
                    ? `OCR ${contract.ocr_reference} · `
                    : ""}
                  {contract.autogiro
                    ? "autogiro"
                    : "manuell betalning"}
                </div>
              </div>
              <div>
                <div className="acct-bal">
                  {SEK(contract.monthly_rent)} kr
                </div>
                <div className="acct-bal-meta">
                  {summary.notices_paid_12m > 0
                    ? `${summary.notices_paid_12m} betalda 12 mån`
                    : "i postlådan"}
                </div>
              </div>
            </div>
            <div className="acct">
              <div>
                <div className="acct-eye">Bostadssökande</div>
                <div className="acct-name">
                  {contract.queue_priority
                    ? "Stockholm bostadsförmedling"
                    : "Eget kontrakt"}
                </div>
                <div className="acct-num">
                  {contract.queue_years
                    ? `${contract.queue_years} år i kö`
                    : "ingen aktiv kö"}
                </div>
              </div>
              <div>
                <div
                  className="acct-bal"
                  style={{ color: "var(--text-dim)" }}
                >
                  — kö
                </div>
                <div className="acct-bal-meta">
                  {contract.queue_priority || "—"}
                </div>
              </div>
            </div>
            <div className="acct">
              <div>
                <div className="acct-eye">Avtal</div>
                <div className="acct-name">
                  {DURATION_LABEL[contract.duration_type]}
                </div>
                <div className="acct-num">
                  {contract.notice_period_months} mån uppsägning ·{" "}
                  {CONTRACT_TYPE_LABEL[contract.contract_type]}
                </div>
              </div>
              <div>
                <div className="acct-bal">
                  {contract.started_on
                    ? new Date(contract.started_on).getFullYear()
                    : "—"}
                </div>
                <div className="acct-bal-meta">
                  {contract.started_on
                    ? `tillträtt ${SHORT_DATE_NO_YEAR(contract.started_on)}`
                    : "okänt"}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="act-grid" style={{ marginTop: 22 }}>
          <div>
            {/* HYRESNOTISER */}
            <div className="section-eye">
              Hyresnotiser & brev från värden
            </div>
            {notices.length === 0 ? (
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
                Inga notiser registrerade. Be läraren lägga in en hyresavi
                eller hyresförhandling så fylls timeline.
              </div>
            ) : (
              <div className="tx-list">
                {notices.map((n) => (
                  <div
                    key={n.id}
                    className="tx-row"
                    style={{
                      gridTemplateColumns: "90px 1fr 100px",
                    }}
                  >
                    <span className="tx-date">
                      {SHORT_DATE_NO_YEAR(n.occurred_on)}
                    </span>
                    <div>
                      <div className="tx-name">{n.title}</div>
                      <div className="tx-name-sub">
                        {n.description ||
                          NOTICE_TYPE_LABEL[n.notice_type] ||
                          n.notice_type}
                      </div>
                    </div>
                    {n.amount != null ? (
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                        }}
                      >
                        {SEK(n.amount)} kr
                      </span>
                    ) : n.change_pct != null ? (
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color:
                            n.change_pct === 0
                              ? "#6ee7b7"
                              : n.change_pct > 4
                              ? "#fda594"
                              : "var(--text-mid)",
                        }}
                      >
                        {n.change_pct > 0 ? "+" : ""}
                        {n.change_pct} %
                      </span>
                    ) : (
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: "var(--text-mid)",
                        }}
                      >
                        {n.status === "paid"
                          ? "betald"
                          : n.status === "info"
                          ? "info"
                          : n.status}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* LÄGG TILL KONTRAKT */}
            {!contract && (
              <div style={{ marginTop: 20 }}>
                {!addOpen ? (
                  <button
                    type="button"
                    className="cta-btn"
                    onClick={() => setAddOpen(true)}
                  >
                    + Registrera hyreskontrakt
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
                      ● Nytt hyreskontrakt
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
                        placeholder="Hyresvärd"
                        value={newLandlord}
                        onChange={(e) => setNewLandlord(e.target.value)}
                        style={inputStyle()}
                      />
                      <input
                        placeholder="Adress"
                        value={newAddress}
                        onChange={(e) => setNewAddress(e.target.value)}
                        style={inputStyle()}
                      />
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 100px 130px",
                        gap: 8,
                        marginBottom: 8,
                      }}
                    >
                      <input
                        placeholder="Storlek (2 r o k)"
                        value={newRooms}
                        onChange={(e) => setNewRooms(e.target.value)}
                        style={inputStyle()}
                      />
                      <input
                        type="number"
                        placeholder="Kvm"
                        value={newArea}
                        onChange={(e) => setNewArea(e.target.value)}
                        style={inputStyle()}
                      />
                      <input
                        type="number"
                        placeholder="Hyra/mån"
                        value={newRent}
                        onChange={(e) => setNewRent(e.target.value)}
                        style={inputStyle()}
                      />
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 8,
                        marginBottom: 10,
                      }}
                    >
                      <select
                        value={newType}
                        onChange={(e) =>
                          setNewType(
                            e.target.value as V2RentalContractType,
                          )
                        }
                        style={inputStyle()}
                      >
                        <option value="forsta_hand">Förstahand</option>
                        <option value="andra_hand">Andrahand</option>
                        <option value="inneboende">Inneboende</option>
                        <option value="bostadsratt">Bostadsrätt</option>
                      </select>
                      <select
                        value={newDuration}
                        onChange={(e) =>
                          setNewDuration(
                            e.target.value as V2RentalDurationType,
                          )
                        }
                        style={inputStyle()}
                      >
                        <option value="tillsvidare">Tillsvidare</option>
                        <option value="tidsbegransad">Tidsbegränsad</option>
                      </select>
                    </div>
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
                        onClick={addContract}
                      >
                        {submitting ? "Sparar…" : "Spara kontrakt"}
                      </button>
                      <button
                        type="button"
                        className="cta-btn ghost"
                        disabled={submitting}
                        onClick={() => setAddOpen(false)}
                      >
                        Avbryt
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {contract && (
              <div style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="cta-btn ghost"
                  onClick={() => terminateContract(contract.id)}
                >
                  Säg upp kontraktet
                </button>
              </div>
            )}
          </div>

          <aside>
            {contract && summary.market_buy_estimate != null && (
              <div className="side-card">
                <div className="side-card-eye">Bytesvärde</div>
                <div className="side-card-h">
                  ~ {SEK(summary.market_buy_estimate * 0.33)} kr
                </div>
                <div className="side-card-meta">
                  Förstahandskontrakt är värt mycket på den otillåtna
                  bytesmarknaden — det är därför man inte hyr ut i
                  andrahand utan tillstånd.
                </div>
              </div>
            )}
            {contract && summary.market_buy_estimate != null && (
              <div className="side-card">
                <div className="side-card-eye">Köpa istället?</div>
                <div className="side-card-h">
                  {SEK(summary.market_buy_estimate / 1000000)} Mkr för
                  motsvarande
                </div>
                <div className="side-card-meta">
                  Marknadspris för {contract.area_sqm} m² i{" "}
                  {contract.district || contract.city || "området"} ≈{" "}
                  {SEK(contract.market_price_per_sqm || 0)} kr/m². Modulen
                  "Ditt första bolån" guidar dig genom kalkylen.
                </div>
              </div>
            )}
            {summary.rent_share_of_net_pct != null && (
              <div
                className="side-card"
                style={
                  summary.rent_share_of_net_pct > 40
                    ? {
                        background: "rgba(220,76,43,0.06)",
                        borderColor: "rgba(220,76,43,0.25)",
                      }
                    : undefined
                }
              >
                <div
                  className="side-card-eye"
                  style={
                    summary.rent_share_of_net_pct > 40
                      ? { color: "var(--accent)" }
                      : undefined
                  }
                >
                  Hyresandel av netto
                </div>
                <div className="side-card-h">
                  {summary.rent_share_of_net_pct} %
                </div>
                <div className="side-card-meta">
                  {summary.rent_share_of_net_pct > 40
                    ? "Över 40 %-tröskeln. Lite kvar att leva på efter fasta utgifter."
                    : summary.rent_share_of_net_pct < 25
                    ? "Bra utrymme för sparande och oväntade utgifter."
                    : "I rimlig nivå (25–40 %)."}
                </div>
              </div>
            )}
            {summary.biggest_hike_pct_12m != null &&
              summary.biggest_hike_pct_12m > 0 && (
                <div
                  className="side-card"
                  style={{
                    background:
                      summary.biggest_hike_pct_12m > 4
                        ? "rgba(220,76,43,0.06)"
                        : undefined,
                    borderColor:
                      summary.biggest_hike_pct_12m > 4
                        ? "rgba(220,76,43,0.25)"
                        : undefined,
                  }}
                >
                  <div className="side-card-eye">Hyresjustering 12 mån</div>
                  <div className="side-card-h">
                    +{summary.biggest_hike_pct_12m} %
                  </div>
                  <div className="side-card-meta">
                    {summary.biggest_hike_pct_12m > 4
                      ? "Större höjning än Hyresgästföreningens snitt — kostnaden växer snabbare än lönen."
                      : "Inom Hyresgästföreningens snitt-höjning."}
                  </div>
                </div>
              )}
          </aside>
        </div>

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Hyresrätt är <em>oslagbar</em> ekonomiskt — om du har en.
          </div>
          <p className="peda-prose">
            Köpa kontra hyra är en av de viktigaste ekonomiska besluten du
            fattar. Hyresrätt med första-handskontrakt = stabil kostnad,
            ingen amortering, ingen ränte-risk, ingen reparation.
            Bostadsrätt = möjlig värdeökning men full risk + amortering +
            drift. Lär dig räkna på <em>båda</em> innan du säger "köpa
            lönar sig".
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Hyresförhandling</strong>Mellan hyresvärd och
              Hyresgästföreningen. Sker årligen.
            </li>
            <li>
              <strong>Andrahandsuthyrning</strong>Kräver hyresvärdens
              tillstånd · max 2 år.
            </li>
            <li>
              <strong>Besittningsskydd</strong>Du har rätt att bo kvar om
              du sköter dig.
            </li>
            <li>
              <strong>Förråd / källare</strong>Ingår normalt · värt att
              kolla i kontraktet.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Bruksvärde</span>
            <span className="peda-concept">Hyresförhandling</span>
            <span className="peda-concept">Bostadskö</span>
            <span className="peda-concept">Andrahand</span>
            <span className="peda-concept">Besittningsskydd</span>
          </div>
          <div className="peda-tip">
            Lärar-uppdrag: räkna ut total kostnad för 5 år med hyran din
            ({SEK((contract?.monthly_rent || 7240) * 60)} kr) vs köp av
            samma 2:a (
            {summary.market_buy_estimate
              ? SEK(summary.market_buy_estimate / 1000000)
              : "2.4"}{" "}
            Mkr · ränta 3,8 % · amortering 2 % · drift 4 200/mån).
            Fascinerande resultat.
          </div>
        </div>
    </>
  );

  if (embedded) {
    return body;
  }
  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />
      <div className="shell">{body}</div>
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
