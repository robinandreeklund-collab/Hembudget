/**
 * Lärar-vy · full insyn i en elevs hyreskontrakt + notiser.
 *
 * Använder /v2/teacher/students/{id}/rental-overview som returnerar:
 * - summary (rent_share_of_net_pct, biggest_hike_pct_12m,
 *   notices_open, market_diff_pct, market_buy_estimate)
 * - aktivt kontrakt (eller null)
 * - alla notiser (12 mån)
 *
 * Lärare kan:
 * - Seedа Stockholmshem-mall (default-kontrakt + 4 notiser)
 * - Skapa hyresnotis (hyresavi/hyreshöjning/forhandling/etc)
 * - Ta bort notis
 *
 * Routas via /teacher/v2/rental/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherRentalOverview,
  type V2RentalNoticeType,
  type V2RentalNoticeStatus,
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

const STATUS_LABEL: Record<string, string> = {
  info: "Info",
  action_required: "Åtgärd krävs",
  paid: "Betald",
  acknowledged: "Bekräftad",
  denied: "Avslagen",
};

const CTYPE_LABEL: Record<string, string> = {
  forsta_hand: "Förstahand",
  andra_hand: "Andrahand",
  inneboende: "Inneboende",
  bostadsratt: "Bostadsrätt",
};

export function TeacherRentalOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherRentalOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  // Notice-form
  const [noticeOccurred, setNoticeOccurred] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [noticeType, setNoticeType] =
    useState<V2RentalNoticeType>("hyresavi");
  const [noticeTitle, setNoticeTitle] = useState("");
  const [noticeDescription, setNoticeDescription] = useState("");
  const [noticeAmount, setNoticeAmount] = useState("");
  const [noticeChangePct, setNoticeChangePct] = useState("");
  const [noticeStatus, setNoticeStatus] =
    useState<V2RentalNoticeStatus>("info");
  const [noticeError, setNoticeError] = useState<string | null>(null);
  const [noticeSubmitting, setNoticeSubmitting] = useState(false);

  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return v2Api
      .teacherRentalOverview(sid)
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
      const r = await v2Api.teacherSeedDefaultRental(sid);
      setSeedMessage(
        `+${r.contracts_created} kontrakt och ${r.notices_created} notiser seedade`,
      );
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeeding(false);
    }
  }

  async function addNotice() {
    setNoticeError(null);
    if (!noticeTitle.trim()) {
      setNoticeError("Ange titel");
      return;
    }
    const amount = noticeAmount
      ? parseFloat(noticeAmount.replace(/\s/g, "").replace(",", "."))
      : undefined;
    const pct = noticeChangePct
      ? parseFloat(noticeChangePct.replace(",", "."))
      : undefined;
    setNoticeSubmitting(true);
    try {
      await v2Api.teacherCreateRentalNotice(sid, {
        contract_id: data?.contract?.id,
        occurred_on: noticeOccurred,
        notice_type: noticeType,
        title: noticeTitle.trim(),
        description: noticeDescription.trim() || undefined,
        amount,
        change_pct: pct,
        status: noticeStatus,
      });
      setNoticeTitle("");
      setNoticeDescription("");
      setNoticeAmount("");
      setNoticeChangePct("");
      await refresh();
    } catch (e) {
      setNoticeError(String((e as Error)?.message || e));
    } finally {
      setNoticeSubmitting(false);
    }
  }

  async function deleteNotice(noticeId: number) {
    if (!confirm("Ta bort notis?")) return;
    try {
      await v2Api.teacherDeleteRentalNotice(sid, noticeId);
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
              Kunde inte ladda hyres-data
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
        <div className="bank-loading">Laddar hyres-profil…</div>
      </div>
    );
  }

  const c = data.contract;
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
            <span className="pill warm">Lärar-vy · Hyresvärden</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>boende-profil</em>.
            </h1>
            <p className="actor-sub">
              Aktivt kontrakt, hyresnotiser, hyresandel av netto, möjliga
              hyreshöjningar. Allt påverkar wellbeing-pentagonen (safety
              + economy).
            </p>
          </div>
          <div className="actor-meta">
            Hyra: <strong>{SEK(s.monthly_rent)} kr/mån</strong>
            <br />
            Andel netto:{" "}
            <strong>
              {s.rent_share_of_net_pct != null
                ? `${s.rent_share_of_net_pct} %`
                : "—"}
            </strong>
            <br />
            Notiser: <strong>{data.notices.length} (12 mån)</strong>
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
              <div className="acct-eye">Kontrakt</div>
              <div className="acct-name">
                {c
                  ? `${c.landlord} · ${c.rooms_label}`
                  : "Inget aktivt"}
              </div>
              <div className="acct-num">
                {c
                  ? `${c.area_sqm} m² · ${
                      CTYPE_LABEL[c.contract_type] || c.contract_type
                    }`
                  : "klicka 'Seedа default' nedan"}
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.monthly_rent)}</div>
              <div className="acct-bal-meta">kr/mån</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Hyresandel av netto</div>
              <div
                className="acct-name"
                style={{
                  color:
                    s.rent_share_of_net_pct != null &&
                    s.rent_share_of_net_pct > 40
                      ? "#fda594"
                      : "#fff",
                }}
              >
                {s.rent_share_of_net_pct != null
                  ? `${s.rent_share_of_net_pct} %`
                  : "—"}
              </div>
              <div className="acct-num">
                {s.rent_share_of_net_pct != null &&
                s.rent_share_of_net_pct > 40
                  ? "över 40 %-tröskeln"
                  : "rimlig nivå"}
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.rent_per_sqm_yearly)}</div>
              <div className="acct-bal-meta">kr/m²/år</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Hyresjustering 12 mån</div>
              <div
                className="acct-name"
                style={{
                  color:
                    s.biggest_hike_pct_12m != null &&
                    s.biggest_hike_pct_12m > 4
                      ? "#fda594"
                      : "#6ee7b7",
                }}
              >
                {s.biggest_hike_pct_12m != null
                  ? `+${s.biggest_hike_pct_12m} %`
                  : "ingen"}
              </div>
              <div className="acct-num">
                {s.biggest_hike_pct_12m != null && s.biggest_hike_pct_12m > 4
                  ? "över snittet"
                  : "snitt-höjning"}
              </div>
            </div>
            <div>
              <div className="acct-bal">{s.notices_open}</div>
              <div className="acct-bal-meta">öppna notiser</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div className="acct-name" style={{ color: "var(--warm)" }}>
                {c?.contract_type === "forsta_hand" ? "+5" : c?.contract_type === "andra_hand" ? "−3" : c?.contract_type === "inneboende" ? "−2" : "0"}
              </div>
              <div className="acct-num">safety (kontrakt-typ)</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--warm)" }}
              >
                {c?.duration_type === "tillsvidare" &&
                c?.contract_type !== "inneboende"
                  ? "+3"
                  : "0"}
              </div>
              <div className="acct-bal-meta">tillsvidare-bonus</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* KONTRAKT-DETALJER */}
            <div className="section-eye">Kontrakt-detaljer</div>
            {!c ? (
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
                Inget aktivt hyreskontrakt. Klicka "Seedа default-mall"
                för att skapa Stockholmshem 2 r o k Hökarängen + 4
                standard-notiser.
              </div>
            ) : (
              <div
                style={{
                  padding: "16px 22px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  marginBottom: 16,
                  fontFamily: "var(--serif)",
                  fontSize: 13.5,
                  lineHeight: 1.7,
                }}
              >
                <div>
                  <strong>{c.landlord}</strong> · {c.address}
                </div>
                <div style={{ color: "var(--text-mid)", fontSize: 12 }}>
                  {c.rooms_label} · {c.area_sqm} m² ·{" "}
                  {c.district || c.city || "—"} ·{" "}
                  {CTYPE_LABEL[c.contract_type]} ·{" "}
                  {c.duration_type === "tillsvidare"
                    ? "tillsvidare"
                    : "tidsbegränsad"}
                </div>
                <div
                  style={{
                    marginTop: 8,
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                  }}
                >
                  Tillträdde {SHORT_DATE(c.started_on)} · uppsägning{" "}
                  {c.notice_period_months} mån
                  {c.queue_years
                    ? ` · ${c.queue_years} år i bostadskö`
                    : ""}
                  {c.market_price_per_sqm
                    ? ` · marknadspris ${SEK(c.market_price_per_sqm)} kr/m² (köp ≈ ${SEK(s.market_buy_estimate || 0)} kr)`
                    : ""}
                </div>
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
                : "Seedа default-mall (Stockholmshem 2 r o k)"}
            </button>

            {/* NOTISER */}
            <div className="section-eye">
              Notiser & brev från värden ({data.notices.length})
            </div>
            {data.notices.length === 0 ? (
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
                Inga notiser registrerade.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 140px 1fr 90px 90px 50px",
                  }}
                >
                  <span>Datum</span>
                  <span>Typ</span>
                  <span>Titel / beskrivning</span>
                  <span>Belopp/%</span>
                  <span>Status</span>
                  <span></span>
                </div>
                {data.notices.map((n) => (
                  <div
                    className="biz-table-row"
                    key={n.id}
                    style={{
                      gridTemplateColumns:
                        "100px 140px 1fr 90px 90px 50px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(n.occurred_on)}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {NOTICE_TYPE_LABEL[n.notice_type] || n.notice_type}
                    </span>
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                        }}
                      >
                        {n.title}
                      </div>
                      {n.description && (
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 10,
                            color: "var(--text-dim)",
                            marginTop: 2,
                          }}
                        >
                          {n.description}
                        </div>
                      )}
                    </div>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {n.amount != null
                        ? `${SEK(n.amount)} kr`
                        : n.change_pct != null
                        ? `${n.change_pct > 0 ? "+" : ""}${n.change_pct} %`
                        : "—"}
                    </span>
                    <span
                      className={`biz-status ${
                        n.status === "paid"
                          ? "delta-up"
                          : n.status === "denied"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {STATUS_LABEL[n.status] || n.status}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteNotice(n.id)}
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

            {/* SKAPA NOTIS */}
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
                ● Lägg till notis (påverkar wellbeing)
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "130px 1fr 160px 130px",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <input
                  type="date"
                  value={noticeOccurred}
                  onChange={(e) => setNoticeOccurred(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  placeholder="Titel"
                  value={noticeTitle}
                  onChange={(e) => setNoticeTitle(e.target.value)}
                  style={inputStyle()}
                />
                <select
                  value={noticeType}
                  onChange={(e) =>
                    setNoticeType(e.target.value as V2RentalNoticeType)
                  }
                  style={inputStyle()}
                >
                  <option value="hyresavi">Hyresavi</option>
                  <option value="hyreshojning">Hyreshöjning</option>
                  <option value="forhandling">Hyresförhandling</option>
                  <option value="trapphusrenovering">
                    Trapphusrenovering
                  </option>
                  <option value="underhall">Underhåll</option>
                  <option value="brand">Brandsyn</option>
                  <option value="andrahand_ansokan">
                    Andrahandsansökan
                  </option>
                  <option value="ovrig">Övrigt</option>
                </select>
                <select
                  value={noticeStatus}
                  onChange={(e) =>
                    setNoticeStatus(
                      e.target.value as V2RentalNoticeStatus,
                    )
                  }
                  style={inputStyle()}
                >
                  <option value="info">Info</option>
                  <option value="action_required">Åtgärd krävs</option>
                  <option value="paid">Betald</option>
                  <option value="acknowledged">Bekräftad</option>
                  <option value="denied">Avslagen</option>
                </select>
              </div>
              <textarea
                placeholder="Beskrivning (valfritt)"
                value={noticeDescription}
                onChange={(e) => setNoticeDescription(e.target.value)}
                style={{ ...inputStyle(), minHeight: 50, marginBottom: 8 }}
              />
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  marginBottom: 10,
                }}
              >
                <input
                  type="number"
                  placeholder="Belopp (för hyresavi)"
                  value={noticeAmount}
                  onChange={(e) => setNoticeAmount(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  step="0.1"
                  placeholder="Förändring % (för hyreshöjning)"
                  value={noticeChangePct}
                  onChange={(e) => setNoticeChangePct(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              {noticeError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {noticeError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={noticeSubmitting}
                onClick={addNotice}
              >
                {noticeSubmitting ? "Sparar…" : "Spara notis"}
              </button>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Boende <em>räknas</em>
              </div>
              <div className="side-card-meta">
                Förstahand +5 safety, tillsvidare +3 safety, andrahand
                −3, inneboende −2. Hyra &gt; 40 % netto −economy. Hyres-
                höjning &gt; 4 % senaste året −2 economy. Inget
                registrerat boende −2 safety.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Bytesvärde (informativt)</div>
              <div className="side-card-h">
                {s.market_buy_estimate
                  ? `~ ${SEK(s.market_buy_estimate * 0.33)} kr`
                  : "—"}
              </div>
              <div className="side-card-meta">
                Förstahandskontrakt på populär adress kan vara värt en
                miljon på den otillåtna bytesmarknaden — pedagogiskt
                viktigt: därför finns reglerna mot olovlig
                andrahandsuthyrning.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Hyresrätt vs <em>köpa</em>
              </div>
              <div className="side-card-meta">
                Eleven ska kunna räkna både scenarier. Hyresrätt =
                stabil kostnad, ingen risk. Bostadsrätt = möjlig
                värdeökning men ränte-risk + amortering + drift. Ingen
                vinner alltid.
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
