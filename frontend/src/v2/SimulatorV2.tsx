/**
 * Verktyg 05 · Investeringssimulator — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-simul):
 * - actor-head med pill, default-värden (7 % real, ISK schablon)
 * - cc-summary med 4 input-cards (start, månadsspar, avkastning,
 *   tidshorisont)
 * - Resultat · 2 scenarier sida vid sida + skillnad
 * - peda-block "Tiden är över alla andra strategier"
 *
 * Sparar scenarier som Scenario(kind=invest) → påverkar wellbeing
 * (+1 economy om horisont ≥ 20 år).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2InvestSimResult,
  type V2SimulatorScenarioRow,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function SimulatorV2() {
  // Scenario A
  const [startA, setStartA] = useState("0");
  const [monthlyA, setMonthlyA] = useState("600");
  const [returnA, setReturnA] = useState("7");
  const [yearsA, setYearsA] = useState("40");
  const [iskA, setIskA] = useState(true);

  // Scenario B (jämförelse)
  const [showCompare, setShowCompare] = useState(true);
  const [monthlyB, setMonthlyB] = useState("1800");
  const [yearsB, setYearsB] = useState("13");

  const [result, setResult] = useState<V2InvestSimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<
    V2SimulatorScenarioRow[]
  >([]);

  function loadSaved() {
    v2Api
      .simulatorScenarios("invest")
      .then(setSavedScenarios)
      .catch(() => {});
  }

  useEffect(() => {
    loadSaved();
    runSim();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runSim(save = false, name?: string) {
    setError(null);
    if (save) setSaving(true);
    else setBusy(true);
    try {
      const body: Parameters<typeof v2Api.simulateInvestment>[0] = {
        start_amount: parseFloat(startA) || 0,
        monthly_save: parseFloat(monthlyA) || 0,
        return_pct: parseFloat(returnA) || 0,
        years: parseInt(yearsA, 10) || 1,
        is_isk: iskA,
        save_as_scenario: save,
        scenario_name: name,
      };
      if (showCompare) {
        body.compare = {
          start_amount: parseFloat(startA) || 0,
          monthly_save: parseFloat(monthlyB) || 0,
          return_pct: parseFloat(returnA) || 0,
          years: parseInt(yearsB, 10) || 1,
          is_isk: iskA,
        };
      }
      const r = await v2Api.simulateInvestment(body);
      setResult(r);
      if (save) {
        setSavedMessage(
          `✓ Sparat scenario · ID ${r.saved_scenario_id} · "${name || "namnlöst"}"`,
        );
        loadSaved();
      }
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusy(false);
      setSaving(false);
    }
  }

  async function deleteSaved(id: number) {
    if (!confirm("Ta bort sparat scenario?")) return;
    await v2Api.simulatorDeleteScenario(id);
    loadSaved();
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
            <span className="pill">Verktyg 05 · Investeringssimulator</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Räkna ·{" "}
              <em>tid, ränta-på-ränta, schablonskatt</em>.
            </h1>
            <p className="actor-sub">
              Fyra parametrar · ISK vs depå · jämförelse av två scenarier
            </p>
          </div>
          <div className="actor-meta">
            Standardvärden:
            <br />
            7 % real avk · ISK
            <br />
            Schablon 0,89 % 2026
          </div>
        </header>

        {/* INPUT-CARDS */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 10,
            marginBottom: 18,
          }}
        >
          <InputCard
            label="Startbelopp"
            value={startA}
            onChange={setStartA}
            suffix="kr"
            sub="från din ISK eller 0"
          />
          <InputCard
            label="Månadsspar"
            value={monthlyA}
            onChange={setMonthlyA}
            suffix="kr/mån"
            sub="0 – 10 000"
          />
          <InputCard
            label="Avkastning"
            value={returnA}
            onChange={setReturnA}
            suffix="%"
            sub="real, exkl. inflation"
          />
          <InputCard
            label="Tidshorisont"
            value={yearsA}
            onChange={setYearsA}
            suffix="år"
            sub="1 – 80"
          />
        </div>

        {/* ISK-toggle + jämförelse-toggle + run-knapp */}
        <div
          style={{
            display: "flex",
            gap: 16,
            alignItems: "center",
            flexWrap: "wrap",
            marginBottom: 18,
            padding: "12px 16px",
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 6,
          }}
        >
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontFamily: "var(--mono)",
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={iskA}
              onChange={(e) => setIskA(e.target.checked)}
            />
            <span>
              ISK (schablon 0,89 %) ·{" "}
              {iskA ? "billigare för långsiktig" : "depå (30 % på vinst)"}
            </span>
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontFamily: "var(--mono)",
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={showCompare}
              onChange={(e) => setShowCompare(e.target.checked)}
            />
            <span>Jämför med scenario B</span>
          </label>
          {showCompare && (
            <>
              <input
                type="number"
                value={monthlyB}
                onChange={(e) => setMonthlyB(e.target.value)}
                placeholder="B kr/mån"
                style={{
                  ...inputStyle(),
                  width: 100,
                  fontSize: 12,
                }}
              />
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-mid)",
                }}
              >
                kr/mån i
              </span>
              <input
                type="number"
                value={yearsB}
                onChange={(e) => setYearsB(e.target.value)}
                placeholder="B år"
                style={{
                  ...inputStyle(),
                  width: 70,
                  fontSize: 12,
                }}
              />
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-mid)",
                }}
              >
                år
              </span>
            </>
          )}
          <button
            type="button"
            className="cta-btn"
            onClick={() => runSim(false)}
            disabled={busy}
            style={{ marginLeft: "auto" }}
          >
            {busy ? "Räknar…" : "Räkna"}
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: "10px 16px",
              border: "1px solid #fca5a5",
              borderRadius: 6,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#fca5a5",
              marginBottom: 14,
            }}
          >
            {error}
          </div>
        )}

        {/* RESULTAT */}
        {result && (
          <>
            <div
              className="cc-summary"
              style={{
                display: "grid",
                gridTemplateColumns:
                  showCompare && result.compare
                    ? "repeat(3, 1fr)"
                    : "1fr",
                gap: 10,
                marginBottom: 22,
              }}
            >
              <ResultCard
                eyeColor="#c7d2fe"
                eye={`Scenario A · ${SEK(parseFloat(monthlyA) || 0)}/mån i ${yearsA} år · ${
                  iskA ? "ISK" : "depå"
                }`}
                value={result.final_value}
                sub={`Insatt ${SEK(result.total_invested)} · avkastning ${SEK(
                  result.total_growth,
                )} · skatt ~ ${SEK(result.total_taxes)}`}
                colorBar="#818cf8"
              />
              {showCompare && result.compare && (
                <>
                  <ResultCard
                    eyeColor="var(--accent)"
                    eye={`Scenario B · ${SEK(parseFloat(monthlyB) || 0)}/mån i ${yearsB} år · ${
                      iskA ? "ISK" : "depå"
                    }`}
                    value={result.compare.final_value}
                    sub={`Insatt ${SEK(result.compare.total_invested)} · avkastning ${SEK(
                      result.compare.final_value -
                        result.compare.total_invested,
                    )} · skatt ~ ${SEK(result.compare.total_taxes)}`}
                    colorBar="var(--accent)"
                  />
                  <DiffCard
                    diff={
                      result.final_value - result.compare.final_value
                    }
                    investedDiff={
                      result.total_invested -
                      result.compare.total_invested
                    }
                  />
                </>
              )}
            </div>

            {/* Spara-block */}
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                flexWrap: "wrap",
                marginBottom: 22,
              }}
            >
              <button
                type="button"
                className="cta-btn"
                onClick={() => {
                  const name = prompt(
                    "Namn på scenariot",
                    `${monthlyA} kr/mån i ${yearsA} år`,
                  );
                  if (name) runSim(true, name);
                }}
                disabled={saving}
              >
                {saving ? "Sparar…" : "Spara scenario"}
              </button>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-mid)",
                }}
              >
                Sparade scenarier syns för läraren och påverkar wellbeing
                (+1 economy om horisont ≥ 20 år)
              </span>
            </div>

            {savedMessage && (
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
                }}
              >
                {savedMessage}
              </div>
            )}

            {/* SPARADE */}
            {savedScenarios.length > 0 && (
              <>
                <div className="section-eye">
                  Sparade investerings-scenarier ({savedScenarios.length})
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  <div
                    className="biz-table-row head"
                    style={{
                      gridTemplateColumns:
                        "1.4fr 90px 90px 90px 110px 60px",
                    }}
                  >
                    <span>Namn</span>
                    <span>Mån</span>
                    <span>År</span>
                    <span>%</span>
                    <span>Slutvärde</span>
                    <span></span>
                  </div>
                  {savedScenarios.map((sc) => (
                    <div
                      className="biz-table-row"
                      key={sc.id}
                      style={{
                        gridTemplateColumns:
                          "1.4fr 90px 90px 90px 110px 60px",
                      }}
                    >
                      <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                        {sc.name}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {SEK(Number(sc.params.monthly_save) || 0)}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {sc.params.years as number}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {sc.params.return_pct as number} %
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                          fontStyle: "italic",
                          color: "var(--warm)",
                        }}
                      >
                        {SEK(
                          Number(
                            (sc.result || {})["final_value"] || 0,
                          ),
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => deleteSaved(sc.id)}
                        style={miniBtn("rgba(255,255,255,0.4)")}
                      >
                        X
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Tiden är <em>över alla andra strategier</em>.
          </div>
          <p className="peda-prose">
            Två scenarier med <em>nästan samma</em> insats: 600 × 480 mån
            = 288 000 vs 1 800 × 156 mån = 280 800. Den första ger 1,47
            Mkr. Den andra 440 tkr. Skillnaden = ränta-på-ränta. Det här
            är hela poängen med att börja spara <em>idag</em>, inte när
            lönen är högre.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Ränta-på-ränta</strong>Avkastningen genererar
              avkastning. Linje blir kurva.
            </li>
            <li>
              <strong>Real avkastning</strong>Avkastning minus inflation.
              Historiskt ~ 7 % på börsen.
            </li>
            <li>
              <strong>ISK vs depå</strong>ISK schablon ~ 0,89 % på
              underlag · depå 30 % på vinst.
            </li>
            <li>
              <strong>Tidshorisont</strong>Längre = mer kraftfull
              ränta-på-ränta.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Ränta-på-ränta</span>
            <span className="peda-concept">Real avkastning</span>
            <span className="peda-concept">ISK</span>
            <span className="peda-concept">Schablonskatt</span>
            <span className="peda-concept">Tidshorisont</span>
          </div>
          <div className="peda-tip">
            Pensionsmyndigheten visar din prognos baserat på det här
            scenariot. Räkna själv: vad om du höjer till 1 200/mån?
          </div>
        </div>
      </div>
    </div>
  );
}

function InputCard({
  label, value, onChange, suffix, sub,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix: string;
  sub: string;
}) {
  return (
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
        {label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 6,
          marginTop: 4,
        }}
      >
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            background: "transparent",
            border: 0,
            color: "#fff",
            fontFamily: "var(--serif)",
            fontSize: 26,
            fontWeight: 700,
            padding: 0,
            width: "100%",
            outline: "none",
          }}
        />
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 12,
            color: "var(--text-mid)",
          }}
        >
          {suffix}
        </span>
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

function ResultCard({
  eye, value, sub, eyeColor, colorBar,
}: {
  eye: string;
  value: number;
  sub: string;
  eyeColor: string;
  colorBar: string;
}) {
  return (
    <div
      className="cc-stat"
      style={{
        background: `${colorBar.replace(")", ",0.06)").replace("rgb", "rgba")}`,
        borderLeft: `3px solid ${colorBar}`,
        paddingLeft: 16,
        padding: "16px 20px",
        borderRadius: 6,
        border: "1px solid var(--line)",
        borderLeftWidth: 3,
        borderLeftColor: colorBar,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: eyeColor,
          marginBottom: 6,
        }}
      >
        {eye}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 28,
          fontStyle: "italic",
          fontWeight: 700,
          marginBottom: 6,
        }}
      >
        {SEK(value)} kr
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          lineHeight: 1.5,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function DiffCard({ diff, investedDiff }: {
  diff: number;
  investedDiff: number;
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
        Skillnad A − B
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 28,
          fontStyle: "italic",
          fontWeight: 700,
          color: diff >= 0 ? "var(--warm)" : "#fca5a5",
          marginTop: 4,
        }}
      >
        {diff >= 0 ? "+" : ""}
        {SEK(diff)} kr
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        Insatt-skillnad: {investedDiff >= 0 ? "+" : ""}
        {SEK(Math.abs(investedDiff))} kr · tiden vinner.
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
