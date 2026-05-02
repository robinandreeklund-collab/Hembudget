/**
 * Aktör 09 · Pensionsmyndigheten — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-pen):
 * - actor-head med pill, prognos-meta, real avk-antagande
 * - acct-grid · 4 pelare (Inkomstpension, Premiepension, ITP1, Privat ISK)
 * - Pensions-prognos · scenarier (65/67/70 år)
 * - aside · verklighetschock + 7,5 IBB-mål
 * - peda-block "Pension är 40 år bort"
 *
 * Eleven kan:
 * - Patcha custom_isk_monthly (sitt eget pensionssparande)
 * - Se prognos uppdateras direkt
 *
 * Wellbeing-koppling: ISK-värde > 0 → +economy, age >= 25 utan ISK →
 * -economy.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { v2Api, type V2PensionData } from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function PensionV2() {
  const [data, setData] = useState<V2PensionData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingISK, setEditingISK] = useState(false);
  const [iskInput, setIskInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function refresh(): Promise<void> {
    return v2Api
      .pension()
      .then((d) => {
        setData(d);
        setIskInput(String(d.assumptions.custom_isk_monthly));
      })
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function saveISK() {
    const val = parseFloat(iskInput.replace(/\s/g, "").replace(",", "."));
    if (isNaN(val) || val < 0) {
      setError("Ange giltigt belopp ≥ 0");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.pensionPatchAssumptions({ custom_isk_monthly: val });
      setEditingISK(false);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
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
              Kunde inte ladda pensions-data
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
        <div className="bank-loading">Laddar pension…</div>
      </div>
    );
  }

  const totalIfShortFor = (need: number) =>
    data.total_monthly_at_retire < need;

  // Approx månads-utgift (samma referensvärde som prototypen)
  const referenceMonthly = 12640; // hyra+mat+el+transport
  const buffer = data.total_monthly_at_retire - referenceMonthly;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 09 · Pensionsmyndigheten</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Det orange <em>kuvertet</em>.
            </h1>
            <p className="actor-sub">
              {data.age != null
                ? `${data.age} år · ${data.years_to_retire} år till riktålder ${data.assumptions.retire_age}`
                : "Profil saknas — fyll i ålder och lön i onboardingen"}{" "}
              · Inkomstpension · premiepension · ITP1 · privat (Avanza
              ISK) · prognos i dagens penningvärde
            </p>
          </div>
          <div className="actor-meta">
            Prognos vid {data.assumptions.retire_age}:{" "}
            <strong>{SEK(data.total_monthly_at_retire)} kr/mån</strong>
            <br />
            I dagens penningvärde
            <br />
            Antagande: {data.assumptions.real_return_pct} % real avk
          </div>
        </header>

        {/* 4 PELARE */}
        <div
          className="acct-grid"
          style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
        >
          {data.pillars.length === 0 ? (
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
              Pelarna kan inte beräknas — fyll i ålder + lön i
              onboardingen, eller be läraren seedа din pension-profil.
            </div>
          ) : (
            data.pillars.map((p) => (
              <div
                key={`${p.label}-${p.name}`}
                className={`acct${p.source === "isk" ? " active" : ""}`}
                style={
                  p.source === "missing"
                    ? {
                        opacity: 0.6,
                        borderColor: "rgba(252,165,165,0.3)",
                      }
                    : undefined
                }
              >
                <div>
                  <div className="acct-eye">{p.label}</div>
                  <div className="acct-name">{p.name}</div>
                  <div className="acct-num">{p.detail}</div>
                </div>
                <div>
                  <div
                    className="acct-bal"
                    style={
                      p.source === "missing"
                        ? { color: "#fda594" }
                        : undefined
                    }
                  >
                    {SEK(p.monthly_at_retire)} kr/mån
                  </div>
                  <div className="acct-bal-meta">
                    Vid {data.assumptions.retire_age}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="act-grid" style={{ marginTop: 22 }}>
          <div>
            {/* SCENARIER */}
            <div className="section-eye">
              Pensions-prognos · scenario
            </div>
            <div className="tx-list">
              <div
                className="tx-row"
                style={{ gridTemplateColumns: "90px 1fr 130px" }}
              >
                <span className="tx-date">65 år</span>
                <div>
                  <div className="tx-name">
                    Pension om du tar ut tidigt
                  </div>
                  <div className="tx-name-sub">−4 % per år före 67</div>
                </div>
                <span
                  style={{
                    fontFamily: "var(--serif)",
                    fontStyle: "italic",
                    color: "#fca5a5",
                    fontWeight: 700,
                  }}
                >
                  {SEK(data.scenarios.age_65_early)} kr/mån
                </span>
              </div>
              <div
                className="tx-row"
                style={{ gridTemplateColumns: "90px 1fr 130px" }}
              >
                <span className="tx-date">
                  {data.assumptions.retire_age} år
                </span>
                <div>
                  <div className="tx-name">Pension vid riktålder</div>
                  <div className="tx-name-sub">Allt + ITP + privat</div>
                </div>
                <span
                  style={{
                    fontFamily: "var(--serif)",
                    fontStyle: "italic",
                    color: "var(--warm)",
                    fontWeight: 700,
                  }}
                >
                  {SEK(data.scenarios.age_67_target)} kr/mån
                </span>
              </div>
              <div
                className="tx-row"
                style={{ gridTemplateColumns: "90px 1fr 130px" }}
              >
                <span className="tx-date">70 år</span>
                <div>
                  <div className="tx-name">
                    Pension om du jobbar 3 år extra
                  </div>
                  <div className="tx-name-sub">+8 % per år efter 67</div>
                </div>
                <span
                  style={{
                    fontFamily: "var(--serif)",
                    fontStyle: "italic",
                    color: "#6ee7b7",
                    fontWeight: 700,
                  }}
                >
                  {SEK(data.scenarios.age_70_late)} kr/mån
                </span>
              </div>
            </div>

            {/* DITT EGET ISK-SPARANDE */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              Ditt privata ISK-sparande
            </div>
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
                ● Avanza ISK · vad du sparar per månad
              </div>
              {!editingISK ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 14,
                    flexWrap: "wrap",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 28,
                      fontStyle: "italic",
                      color: "var(--warm)",
                    }}
                  >
                    {SEK(data.assumptions.custom_isk_monthly)} kr/mån
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--text-mid)",
                    }}
                  >
                    nuvarande ISK-värde:{" "}
                    {SEK(data.isk_current_value)} kr
                  </div>
                  <button
                    type="button"
                    className="cta-btn ghost"
                    onClick={() => setEditingISK(true)}
                    style={{ marginLeft: "auto" }}
                  >
                    Ändra månadssparande
                  </button>
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <input
                    type="number"
                    value={iskInput}
                    onChange={(e) => setIskInput(e.target.value)}
                    placeholder="kr/mån"
                    style={{
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid var(--line-strong)",
                      color: "#fff",
                      padding: "10px 14px",
                      borderRadius: 4,
                      fontFamily: "var(--mono)",
                      fontSize: 14,
                      width: 140,
                    }}
                  />
                  <button
                    type="button"
                    className="cta-btn"
                    disabled={submitting}
                    onClick={saveISK}
                  >
                    {submitting ? "Sparar…" : "Spara"}
                  </button>
                  <button
                    type="button"
                    className="cta-btn ghost"
                    onClick={() => {
                      setEditingISK(false);
                      setIskInput(
                        String(data.assumptions.custom_isk_monthly),
                      );
                    }}
                  >
                    Avbryt
                  </button>
                </div>
              )}
              {data.assumptions.custom_isk_monthly > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                    lineHeight: 1.6,
                  }}
                >
                  Med {SEK(data.assumptions.custom_isk_monthly)} kr/mån i{" "}
                  {data.years_to_retire} år vid{" "}
                  {data.assumptions.real_return_pct} % real avkastning
                  blir det ungefär{" "}
                  <strong style={{ color: "var(--warm)" }}>
                    {SEK(
                      data.pillars.find((p) => p.source === "isk")
                        ?.monthly_at_retire || 0,
                    )}{" "}
                    kr/mån
                  </strong>{" "}
                  extra pension.
                </div>
              )}
            </div>

            <div style={{ marginTop: 18 }}>
              <Link
                to="/v2/avanza"
                className="cta-btn ghost"
                style={{ textDecoration: "none" }}
              >
                Öppna Avanza ISK →
              </Link>
            </div>
          </div>

          <aside>
            <div
              className="side-card"
              style={
                buffer < 1000
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
                  buffer < 1000 ? { color: "var(--accent)" } : undefined
                }
              >
                Verklighetschock
              </div>
              <div className="side-card-h">
                {SEK(data.total_monthly_at_retire)} kr{" "}
                {totalIfShortFor(referenceMonthly) ? (
                  <em>räcker inte</em>
                ) : (
                  <em>räcker</em>
                )}
              </div>
              <div className="side-card-meta">
                Hyra 7 240 + mat 4 000 + el 800 + transport 600 ={" "}
                {SEK(referenceMonthly)} kr.{" "}
                {buffer >= 0
                  ? `Bara ${SEK(Math.abs(buffer))} kr buffert.`
                  : `Saknar ${SEK(Math.abs(buffer))} kr.`}{" "}
                {data.assumptions.custom_isk_monthly === 0
                  ? "Måste ha eget sparande."
                  : "Eget sparande igång — bra!"}
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Mål · 7,5 IBB</div>
              <div className="side-card-h">
                ~ {SEK((data.assumptions.ibb_yearly * 7.5) / 12 * 0.6)} kr/mån
              </div>
              <div className="side-card-meta">
                7,5 IBB = inkomstbasbeloppstak ({SEK(data.assumptions.ibb_yearly)}{" "}
                kr/år). Över det får du proportionerligt mindre allmän
                pension. Spara mer privat om du tjänar över.
              </div>
            </div>
            {!data.has_collective_agreement && (
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
                  Saknar kollektivavtal
                </div>
                <div className="side-card-h">
                  ITP1 = <em>0 kr</em>
                </div>
                <div className="side-card-meta">
                  Egenföretagare/frilans utan kollektivavtal får ingen
                  tjänstepension automatiskt. Förhandla med kunder eller
                  spara extra privat ({" "}
                  {SEK(
                    Math.round(
                      (data.gross_salary_monthly || 0) * 0.045,
                    ),
                  )}{" "}
                  kr/mån motsvarar 4,5 % av lön).
                </div>
              </div>
            )}
          </aside>
        </div>

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Pension är <em>40 år bort</em> — och det är problemet.
          </div>
          <p className="peda-prose">
            Pension känns abstrakt eftersom belöningen ligger 40 år bort.
            Men beslut idag (tjänsteval, lönesnack, ISK-spar) påverkar
            den siffran enormt. Att se{" "}
            {SEK(data.total_monthly_at_retire)} kr i dagens penningvärde
            gör pensionen <em>konkret</em> — det räcker{" "}
            {totalIfShortFor(referenceMonthly) ? "knappt" : "till"} hyra +
            mat. Eget sparande är inte lyx, det är försäkring.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Inkomstpension</strong>Beräknas på alla intjänade
              pensionsrätter under livet.
            </li>
            <li>
              <strong>Premiepension</strong>Du väljer fonder själv —
              800+ att välja på.
            </li>
            <li>
              <strong>ITP1</strong>Tjänstepension via kollektivavtal ·
              4,5 % under 7,5 IBB · 30 % över.
            </li>
            <li>
              <strong>Riktålder</strong>{data.assumptions.retire_age} år 2026,
              höjs gradvis till 69 år 2030.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">IBB</span>
            <span className="peda-concept">Pensionsrätt</span>
            <span className="peda-concept">Delningstal</span>
            <span className="peda-concept">Riktålder</span>
            <span className="peda-concept">Inflationsuppräkning</span>
            <span className="peda-concept">Garantipension</span>
          </div>
          <div className="peda-tip">
            Spara 600 kr/mån i 40 år vid 7 % real avkastning ≈ 1,2 Mkr.
            Som ger ~ 4 800 kr/mån extra pension. Tiden är överlägsen
            alla andra strategier.
          </div>
        </div>
      </div>
    </div>
  );
}
