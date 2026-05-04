/**
 * Verktyg 06 · Lånekalkylator — elev-vy.
 *
 * Beräknar amorteringsplan (annuitet eller rak) + visar effekten av
 * extra-amortering. Speglar peda-tipset från p-lan: "vad händer om
 * jag amorterar 500 extra/mån i 5 år?"
 *
 * - Input-cards: belopp, ränta %, löptid mån, extra-amort kr/mån
 * - Toggle: annuitet vs rak amortering
 * - Resultat: månadskost baseline + med extra, total kost, ränte-
 *   besparing, månader sparat
 * - Schedule första 12 mån (uppdelat ränta/amort/saldo)
 * - peda-block om billig vs dyr skuld
 *
 * Sparar scenarier som Scenario(kind=loan) → läraren ser dem.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2LoanSimResult,
  type V2SimulatorScenarioRow,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const PRESETS = [
  {
    label: "CSN-lån",
    principal: 38200,
    rate: 1.7,
    months: 247,
    extra: 0,
  },
  {
    label: "Bolån (2:a Sthlm)",
    principal: 2_400_000,
    rate: 3.8,
    months: 360,
    extra: 0,
  },
  {
    label: "Privatlån (blanco)",
    principal: 100000,
    rate: 14,
    months: 60,
    extra: 0,
  },
  {
    label: "Billån",
    principal: 200000,
    rate: 6.5,
    months: 72,
    extra: 0,
  },
];

export function LanekalkylatorV2() {
  const [principal, setPrincipal] = useState("38200");
  const [rate, setRate] = useState("1.7");
  const [months, setMonths] = useState("247");
  const [extra, setExtra] = useState("0");
  const [amortType, setAmortType] = useState<"annuity" | "straight">(
    "annuity",
  );

  const [result, setResult] = useState<V2LoanSimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<
    V2SimulatorScenarioRow[]
  >([]);

  function loadSaved() {
    v2Api
      .simulatorScenarios("loan")
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
      const r = await v2Api.simulateLoan({
        principal: parseFloat(principal) || 0,
        interest_rate_pct: parseFloat(rate) || 0,
        term_months: parseInt(months, 10) || 1,
        extra_amortization_monthly: parseFloat(extra) || 0,
        amortization_type: amortType,
        save_as_scenario: save,
        scenario_name: name,
      });
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

  function applyPreset(p: typeof PRESETS[0]) {
    setPrincipal(String(p.principal));
    setRate(String(p.rate));
    setMonths(String(p.months));
    setExtra(String(p.extra));
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
            <span className="pill">Verktyg 06 · Lånekalkylator</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Räkna · <em>annuitet, ränta, amortering</em>.
            </h1>
            <p className="actor-sub">
              Skilj på billig skuld (CSN, bolån) och dyr skuld (blanco,
              sms-lån). Simulera effekten av extra-amortering.
            </p>
          </div>
          <div className="actor-meta">
            Standard: annuitet
            <br />
            CSN-mall förvald
            <br />
            Sparade syns för läraren
          </div>
        </header>

        {/* PRESET-CHIPS */}
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 14,
          }}
        >
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-mid)",
              alignSelf: "center",
              marginRight: 6,
            }}
          >
            Snabbval:
          </span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => applyPreset(p)}
              style={{
                background: "transparent",
                border: "1px solid var(--line-strong)",
                color: "var(--text-mid)",
                padding: "5px 12px",
                borderRadius: 100,
                fontFamily: "var(--mono)",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* INPUT-GRID */}
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
            label="Lånebelopp"
            value={principal}
            onChange={setPrincipal}
            suffix="kr"
            sub="kapital att låna"
          />
          <InputCard
            label="Ränta"
            value={rate}
            onChange={setRate}
            suffix="%"
            sub="årlig nominell"
          />
          <InputCard
            label="Löptid"
            value={months}
            onChange={setMonths}
            suffix="mån"
            sub={`= ${(parseInt(months, 10) / 12 || 0).toFixed(1)} år`}
          />
          <InputCard
            label="Extra-amort"
            value={extra}
            onChange={setExtra}
            suffix="kr/mån"
            sub="över annuiteten"
          />
        </div>

        {/* TYPE-toggle + run */}
        <div
          style={{
            display: "flex",
            gap: 14,
            alignItems: "center",
            flexWrap: "wrap",
            marginBottom: 18,
            padding: "12px 16px",
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 6,
          }}
        >
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-mid)",
            }}
          >
            Amortering:
          </span>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              cursor: "pointer",
              fontFamily: "var(--mono)",
              fontSize: 11,
            }}
          >
            <input
              type="radio"
              checked={amortType === "annuity"}
              onChange={() => setAmortType("annuity")}
            />
            <span>Annuitet (fast månadsbel)</span>
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              cursor: "pointer",
              fontFamily: "var(--mono)",
              fontSize: 11,
            }}
          >
            <input
              type="radio"
              checked={amortType === "straight"}
              onChange={() => setAmortType("straight")}
            />
            <span>Rak (samma kapital)</span>
          </label>
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

        {result && (
          <>
            {/* RESULTAT-GRID */}
            <div className="acct-grid" style={{ marginBottom: 22 }}>
              <div className="acct active">
                <div>
                  <div className="acct-eye">Månadskostnad</div>
                  <div className="acct-name">
                    {SEK(result.monthly_payment_with_extra)} kr
                  </div>
                  <div className="acct-num">
                    {result.extra_amortization_monthly > 0
                      ? `+${SEK(result.extra_amortization_monthly)} extra`
                      : "annuitet utan extra"}
                  </div>
                </div>
                <div>
                  <div className="acct-bal">
                    {SEK(result.monthly_payment_baseline)}
                  </div>
                  <div className="acct-bal-meta">utan extra</div>
                </div>
              </div>
              <div className="acct">
                <div>
                  <div className="acct-eye">Total kostnad</div>
                  <div className="acct-name">
                    {SEK(result.total_paid_with_extra)} kr
                  </div>
                  <div className="acct-num">
                    av {SEK(result.principal)} kapital
                  </div>
                </div>
                <div>
                  <div className="acct-bal">
                    {SEK(result.total_interest_with_extra)}
                  </div>
                  <div className="acct-bal-meta">i ränta</div>
                </div>
              </div>
              <div className="acct">
                <div>
                  <div className="acct-eye">Räntebesparing</div>
                  <div
                    className="acct-name"
                    style={{
                      color:
                        result.interest_savings > 0
                          ? "#6ee7b7"
                          : "var(--text-mid)",
                    }}
                  >
                    {result.interest_savings > 0
                      ? `−${SEK(result.interest_savings)} kr`
                      : "0 kr"}
                  </div>
                  <div className="acct-num">vs utan extra</div>
                </div>
                <div>
                  <div className="acct-bal">
                    {result.months_saved}
                  </div>
                  <div className="acct-bal-meta">månader sparat</div>
                </div>
              </div>
              <div className="acct">
                <div>
                  <div className="acct-eye">Klar</div>
                  <div className="acct-name">
                    {result.payoff_months_with_extra} mån
                  </div>
                  <div className="acct-num">
                    {(result.payoff_months_with_extra / 12).toFixed(1)} år
                  </div>
                </div>
                <div>
                  <div className="acct-bal">
                    {(
                      (result.total_paid_with_extra / result.principal) *
                      100 -
                      100
                    ).toFixed(0)}{" "}
                    %
                  </div>
                  <div className="acct-bal-meta">räntepålägg</div>
                </div>
              </div>
            </div>

            {/* SCHEMA */}
            <div className="section-eye">
              Amorteringsplan · första 12 månaderna
            </div>
            <div className="biz-table" style={{ marginBottom: 22 }}>
              <div
                className="biz-table-row head"
                style={{
                  gridTemplateColumns: "60px 100px 100px 100px 110px",
                }}
              >
                <span>Mån</span>
                <span>Betalt</span>
                <span>Ränta</span>
                <span>Amortering</span>
                <span>Restskuld</span>
              </div>
              {result.schedule_first_12.map((row) => (
                <div
                  className="biz-table-row"
                  key={row.month}
                  style={{
                    gridTemplateColumns: "60px 100px 100px 100px 110px",
                  }}
                >
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                    {row.month}
                  </span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                    {SEK(row.payment)} kr
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "#fda594",
                    }}
                  >
                    {SEK(row.interest)}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--warm)",
                    }}
                  >
                    {SEK(row.principal)}
                  </span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                    {SEK(row.balance)}
                  </span>
                </div>
              ))}
            </div>

            {/* Spara */}
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
                    `${SEK(parseFloat(principal))} kr · ${rate} %`,
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
                Läraren ser sparade scenarier i sin lärar-vy
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

            {savedScenarios.length > 0 && (
              <>
                <div className="section-eye">
                  Sparade låne-scenarier ({savedScenarios.length})
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  <div
                    className="biz-table-row head"
                    style={{
                      gridTemplateColumns:
                        "1.4fr 110px 80px 90px 110px 60px",
                    }}
                  >
                    <span>Namn</span>
                    <span>Belopp</span>
                    <span>Ränta</span>
                    <span>Löptid</span>
                    <span>Total ränta</span>
                    <span></span>
                  </div>
                  {savedScenarios.map((sc) => (
                    <div
                      className="biz-table-row"
                      key={sc.id}
                      style={{
                        gridTemplateColumns:
                          "1.4fr 110px 80px 90px 110px 60px",
                      }}
                    >
                      <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                        {sc.name}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {SEK(Number(sc.params.principal) || 0)}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {sc.params.interest_rate_pct as number} %
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {sc.params.term_months as number} mån
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: "#fda594",
                        }}
                      >
                        {SEK(
                          Number(
                            ((sc.result || {})["with_extra"] as Record<string, unknown> || {})[
                              "total_interest"
                            ] || 0,
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
            Inte alla lån är <em>lika</em>.
          </div>
          <p className="peda-prose">
            CSN-räntan på 1,7 % är cirka 1/4 av bolåneräntan och 1/10 av
            blanco-låneräntan. Bolån är dyrare men finansierar tillgång
            (bostad). Privatlån är dyrast och oftast onödigt. Sms-lån är
            finansiell rovdrift. Lär dig skilja på{" "}
            <code>billig skuld</code> (CSN, bolån mot bostad),{" "}
            <code>medel</code> (billån mot bil), och <code>dyr skuld</code>{" "}
            (kreditkort, blanco, sms-lån).
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Annuitet</strong>Samma månadsbelopp hela tiden —
              ränta minskar, amortering ökar.
            </li>
            <li>
              <strong>Rak amortering</strong>Samma kapital varje gång —
              månadskostnad sjunker.
            </li>
            <li>
              <strong>Effektiv ränta</strong>Inkluderar avgifter. Den
              enda räntan att jämföra med.
            </li>
            <li>
              <strong>Snabbamortering</strong>Lönar sig vid hög ränta.
              Vid 1,7 % CSN: marginellt. Vid 4 % bolån: tusentals kr.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Annuitet</span>
            <span className="peda-concept">Rak amortering</span>
            <span className="peda-concept">Effektiv ränta</span>
            <span className="peda-concept">Skuldkvot</span>
            <span className="peda-concept">Belåningsgrad</span>
          </div>
          <div className="peda-tip">
            Spoiler: vid 1,7 % CSN sparar 500 kr extra/mån i 5 år ~140 kr
            i ränta. Inte mycket. Investera istället. Men vid 4 % bolån
            blir det 28 000 kr — då lönar det sig.
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
          step="any"
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
