/**
 * Lärar-vy · full insyn i en elevs försäkrings-aktör.
 *
 * Använder /v2/teacher/students/{id}/insurance-overview som returnerar:
 * - summary (active/considered/cancelled, premie, coverage, claims)
 * - alla policies (alla statusar)
 * - alla claims (alla)
 *
 * Lärare kan också:
 * - Seedа default-katalogen (6 svenska försäkringspaket)
 * - Skapa skadehändelse (paid eller no_policy/unprotected) → påverkar wellbeing
 * - Ta bort skadehändelse
 *
 * Routas via /teacher/v2/insurance/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherInsuranceOverview,
  type V2InsuranceClaimKind,
  type V2ClaimStatus,
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

const CLAIM_STATUS_LABEL: Record<string, string> = {
  reported: "Anmäld",
  in_review: "Granskas",
  approved: "Godkänd",
  partial: "Delvis betald",
  denied: "Avslagen",
  paid: "Utbetald",
  info: "Info",
};

const CLAIM_KIND_LABEL: Record<string, string> = {
  vattenskada: "Vattenskada",
  inbrott: "Inbrott",
  brand: "Brand",
  cykelstold: "Cykelstöld",
  resa: "Reseskada",
  olycksfall: "Olycksfall",
  bil: "Bilskada",
  ovrig: "Övrig",
};

export function TeacherInsuranceOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherInsuranceOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  // Skadehändelse-form
  const [claimOccurredOn, setClaimOccurredOn] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [claimPolicyId, setClaimPolicyId] = useState<string>("");
  const [claimKind, setClaimKind] =
    useState<V2InsuranceClaimKind>("vattenskada");
  const [claimTitle, setClaimTitle] = useState("");
  const [claimAmountClaimed, setClaimAmountClaimed] = useState("");
  const [claimAmountPaid, setClaimAmountPaid] = useState("");
  const [claimStatus, setClaimStatus] = useState<V2ClaimStatus>("paid");
  const [claimNoPolicy, setClaimNoPolicy] = useState(false);
  const [claimDescription, setClaimDescription] = useState("");
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimSubmitting, setClaimSubmitting] = useState(false);

  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return v2Api
      .teacherInsuranceOverview(sid)
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
      const r = await v2Api.teacherSeedDefaultInsurance(sid);
      setSeedMessage(
        `+${r.policies_created} default-försäkringar seedade (status=considered)`,
      );
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeeding(false);
    }
  }

  async function addClaim() {
    setClaimError(null);
    if (!claimTitle.trim()) {
      setClaimError("Ange en titel på händelsen");
      return;
    }
    const amountClaimed = claimAmountClaimed
      ? parseFloat(claimAmountClaimed.replace(/\s/g, "").replace(",", "."))
      : undefined;
    const amountPaid = claimAmountPaid
      ? parseFloat(claimAmountPaid.replace(/\s/g, "").replace(",", "."))
      : undefined;
    if (amountClaimed != null && isNaN(amountClaimed)) {
      setClaimError("Ogiltigt belopp · krävt");
      return;
    }
    if (amountPaid != null && isNaN(amountPaid)) {
      setClaimError("Ogiltigt belopp · utbetalt");
      return;
    }
    const policyIdNum = claimPolicyId ? parseInt(claimPolicyId, 10) : undefined;
    setClaimSubmitting(true);
    try {
      await v2Api.teacherCreateInsuranceClaim(sid, {
        occurred_on: claimOccurredOn,
        policy_id: claimNoPolicy ? undefined : policyIdNum,
        kind: claimKind,
        title: claimTitle.trim(),
        description: claimDescription.trim() || undefined,
        amount_claimed: amountClaimed,
        amount_paid: amountPaid,
        status: claimStatus,
        paid_at: claimStatus === "paid" ? claimOccurredOn : undefined,
        no_policy: claimNoPolicy,
      });
      setClaimTitle("");
      setClaimDescription("");
      setClaimAmountClaimed("");
      setClaimAmountPaid("");
      setClaimNoPolicy(false);
      setClaimPolicyId("");
      await refresh();
    } catch (e) {
      setClaimError(String((e as Error)?.message || e));
    } finally {
      setClaimSubmitting(false);
    }
  }

  async function deleteClaim(claimId: number) {
    if (!confirm("Ta bort skadehändelse?")) return;
    try {
      await v2Api.teacherDeleteInsuranceClaim(sid, claimId);
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
              Kunde inte ladda försäkrings-data
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
        <div className="bank-loading">Laddar försäkrings-profil…</div>
      </div>
    );
  }

  const s = data.summary;
  const activePolicies = data.policies.filter((p) => p.status === "active");
  const consideredPolicies = data.policies.filter(
    (p) => p.status === "considered",
  );
  const cancelledPolicies = data.policies.filter(
    (p) => p.status === "cancelled",
  );

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
            <span className="pill warm">Lärar-vy · Försäkringar</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>försäkrings-profil</em>.
            </h1>
            <p className="actor-sub">
              Aktiva försäkringar, övervägs-katalog, skadehändelser och
              täcknings-luckor. Allt påverkar wellbeing-pentagonen (safety +
              economy).
            </p>
          </div>
          <div className="actor-meta">
            Aktiva: <strong>{s.active_count}</strong>
            <br />
            Premie: <strong>{SEK(s.total_premium_monthly)} kr/mån</strong>
            <br />
            Coverage: <strong>{SEK(s.total_coverage)} kr</strong>
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

        {/* TÄCKNINGS-LUCKOR */}
        {s.coverage_gaps.length > 0 && (
          <div
            style={{
              padding: "14px 18px",
              border: "1px solid rgba(252,165,165,0.4)",
              background: "rgba(252,165,165,0.06)",
              borderRadius: 6,
              marginBottom: 18,
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "#fca5a5",
                marginBottom: 8,
              }}
            >
              ▲ Täcknings-luckor ({s.coverage_gaps.length})
            </div>
            <ul
              style={{
                margin: 0,
                paddingLeft: 18,
                fontFamily: "var(--serif)",
                fontSize: 14,
                color: "#fca5a5",
                lineHeight: 1.6,
              }}
            >
              {s.coverage_gaps.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </div>
        )}

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Aktiva försäkringar</div>
              <div className="acct-name">{s.active_count}</div>
              <div className="acct-num">
                {SEK(s.total_premium_monthly)} kr/mån
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.total_coverage)}</div>
              <div className="acct-bal-meta">total coverage</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Övervägs</div>
              <div className="acct-name">{s.considered_count}</div>
              <div className="acct-num">i katalogen</div>
            </div>
            <div>
              <div className="acct-bal">{s.cancelled_count}</div>
              <div className="acct-bal-meta">avbrutna</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Skador 12 mån</div>
              <div
                className="acct-name"
                style={{ color: s.claims_paid_12m > 0 ? "#6ee7b7" : "#fff" }}
              >
                {s.claims_paid_12m} betalda
              </div>
              <div className="acct-num">
                {SEK(s.claims_paid_amount_12m)} kr utbetalt
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color: s.claims_unprotected_12m > 0 ? "#fda594" : "#fff",
                }}
              >
                {s.claims_unprotected_12m}
              </div>
              <div className="acct-bal-meta">oskyddade</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div className="acct-name" style={{ color: "var(--warm)" }}>
                {s.active_count >= 3
                  ? "+8"
                  : s.active_count >= 1
                  ? "+5"
                  : "0"}
              </div>
              <div className="acct-num">safety-bonus</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color:
                    s.total_premium_monthly > 700 ? "#fda594" : "#6ee7b7",
                }}
              >
                {s.total_premium_monthly > 700 ? "−" : ""}
                {s.total_premium_monthly > 700
                  ? Math.min(
                      8,
                      Math.round((s.total_premium_monthly - 700) / 100),
                    )
                  : 0}
              </div>
              <div className="acct-bal-meta">economy-belastning</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* AKTIVA POLICIES */}
            <div className="section-eye">
              Aktiva försäkringar ({activePolicies.length})
            </div>
            {activePolicies.length === 0 ? (
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
                Inga aktiva försäkringar. Klicka "Seedа default-katalogen"
                för att fylla i 6 svenska försäkringar (Hyresförsäkring · If,
                Olycksfall · Folksam, Hemförsäkring · Trygg-Hansa, Liv ·
                Skandia, Barnförsäkring · Länsförsäkringar, Bostadsrätt ·
                ICA Försäkring) — alla i status "considered" så eleven
                aktivt får välja.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "150px 1.2fr 100px 110px 90px",
                  }}
                >
                  <span>Bolag</span>
                  <span>Namn / typ</span>
                  <span>Premie</span>
                  <span>Coverage</span>
                  <span>Self-risk</span>
                </div>
                {activePolicies.map((p) => (
                  <div
                    className="biz-table-row"
                    key={p.id}
                    style={{
                      gridTemplateColumns: "150px 1.2fr 100px 110px 90px",
                    }}
                  >
                    <span
                      style={{ fontFamily: "var(--serif)", fontSize: 13 }}
                    >
                      {p.provider}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {p.name} · {p.kind}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {SEK(p.premium_monthly)} kr/mån
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {p.coverage_amount != null
                        ? SEK(p.coverage_amount)
                        : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {p.deductible != null ? SEK(p.deductible) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* ÖVERVÄGS */}
            {consideredPolicies.length > 0 && (
              <>
                <div className="section-eye">
                  Övervägs ({consideredPolicies.length})
                </div>
                <div className="biz-table" style={{ marginBottom: 16 }}>
                  {consideredPolicies.map((p) => (
                    <div
                      className="biz-table-row"
                      key={p.id}
                      style={{
                        gridTemplateColumns: "150px 1.2fr 100px",
                      }}
                    >
                      <span
                        style={{ fontFamily: "var(--serif)", fontSize: 13 }}
                      >
                        {p.provider}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: "var(--text-mid)",
                        }}
                      >
                        {p.name} · {p.kind}
                      </span>
                      <span
                        style={{ fontFamily: "var(--mono)", fontSize: 12 }}
                      >
                        {SEK(p.premium_monthly)} kr/mån
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* AVBRUTNA */}
            {cancelledPolicies.length > 0 && (
              <>
                <div className="section-eye">
                  Avbrutna ({cancelledPolicies.length})
                </div>
                <div
                  style={{
                    padding: "12px 18px",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                    marginBottom: 22,
                  }}
                >
                  {cancelledPolicies
                    .map((p) => `${p.name} (${p.provider})`)
                    .join(" · ")}
                </div>
              </>
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
                : "Seedа default-katalog (6 svenska paket)"}
            </button>

            {/* SKADEHÄNDELSER */}
            <div className="section-eye">
              Skadehändelser ({data.claims.length})
            </div>
            {data.claims.length === 0 ? (
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
                Inga skadehändelser registrerade.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 1.4fr 100px 90px 90px 80px 50px",
                  }}
                >
                  <span>Datum</span>
                  <span>Händelse</span>
                  <span>Typ</span>
                  <span>Krävt</span>
                  <span>Utbetalt</span>
                  <span>Status</span>
                  <span></span>
                </div>
                {data.claims.map((c) => (
                  <div
                    className="biz-table-row"
                    key={c.id}
                    style={{
                      gridTemplateColumns:
                        "100px 1.4fr 100px 90px 90px 80px 50px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(c.occurred_on)}
                    </span>
                    <span
                      style={{ fontFamily: "var(--serif)", fontSize: 13 }}
                    >
                      {c.title}
                      {c.no_policy && (
                        <span
                          style={{
                            marginLeft: 6,
                            color: "#fda594",
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            letterSpacing: "1px",
                            textTransform: "uppercase",
                          }}
                        >
                          oskyddad
                        </span>
                      )}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {CLAIM_KIND_LABEL[c.kind] || c.kind}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {c.amount_claimed != null
                        ? SEK(c.amount_claimed)
                        : "—"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        color:
                          c.amount_paid != null && c.amount_paid > 0
                            ? "#6ee7b7"
                            : "var(--text-mid)",
                      }}
                    >
                      {c.amount_paid != null ? SEK(c.amount_paid) : "—"}
                    </span>
                    <span
                      className={`biz-status ${
                        c.status === "paid"
                          ? "delta-up"
                          : c.status === "denied"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {CLAIM_STATUS_LABEL[c.status] || c.status}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteClaim(c.id)}
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

            {/* SKAPA SKADEHÄNDELSE */}
            <div
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "16px 20px",
                marginBottom: 22,
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
                ● Lägg till skadehändelse (påverkar wellbeing)
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "130px 1fr 130px 130px",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "end",
                }}
              >
                <input
                  type="date"
                  value={claimOccurredOn}
                  onChange={(e) => setClaimOccurredOn(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  placeholder="Händelse (t.ex. Inbrott i lägenheten)"
                  value={claimTitle}
                  onChange={(e) => setClaimTitle(e.target.value)}
                  style={inputStyle()}
                />
                <select
                  value={claimKind}
                  onChange={(e) =>
                    setClaimKind(e.target.value as V2InsuranceClaimKind)
                  }
                  style={inputStyle()}
                >
                  <option value="vattenskada">Vattenskada</option>
                  <option value="inbrott">Inbrott</option>
                  <option value="brand">Brand</option>
                  <option value="cykelstold">Cykelstöld</option>
                  <option value="resa">Reseskada</option>
                  <option value="olycksfall">Olycksfall</option>
                  <option value="bil">Bilskada</option>
                  <option value="ovrig">Övrig</option>
                </select>
                <select
                  value={claimStatus}
                  onChange={(e) =>
                    setClaimStatus(e.target.value as V2ClaimStatus)
                  }
                  style={inputStyle()}
                >
                  <option value="paid">Utbetald</option>
                  <option value="approved">Godkänd</option>
                  <option value="partial">Delvis betald</option>
                  <option value="denied">Avslagen</option>
                  <option value="reported">Anmäld</option>
                  <option value="in_review">Granskas</option>
                  <option value="info">Info</option>
                </select>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 130px 130px",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "end",
                }}
              >
                <select
                  value={claimPolicyId}
                  onChange={(e) => setClaimPolicyId(e.target.value)}
                  disabled={claimNoPolicy}
                  style={inputStyle()}
                >
                  <option value="">— Koppla till försäkring —</option>
                  {data.policies
                    .filter((p) => p.status === "active")
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.provider} · {p.name}
                      </option>
                    ))}
                </select>
                <input
                  type="number"
                  placeholder="Krävt belopp"
                  value={claimAmountClaimed}
                  onChange={(e) => setClaimAmountClaimed(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Utbetalt"
                  value={claimAmountPaid}
                  onChange={(e) => setClaimAmountPaid(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              <textarea
                placeholder="Beskrivning (valfritt)"
                value={claimDescription}
                onChange={(e) => setClaimDescription(e.target.value)}
                style={{ ...inputStyle(), minHeight: 60, marginBottom: 8 }}
              />
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
                  checked={claimNoPolicy}
                  onChange={(e) => setClaimNoPolicy(e.target.checked)}
                />
                <span>
                  ⚠ Oskyddad händelse (eleven hade ingen försäkring) ·
                  påverkar safety negativt
                </span>
              </label>
              {claimError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {claimError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={claimSubmitting}
                onClick={addClaim}
              >
                {claimSubmitting ? "Sparar…" : "Spara skadehändelse"}
              </button>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Försäkring <em>påverkar</em>
              </div>
              <div className="side-card-meta">
                Aktiv hemförsäkring +5 safety. 3+ aktiva +8 totalt. Total
                premie över 700 kr/mån belastar economy. Utbetald skada
                +safety (max +8). Oskyddad händelse −safety (max −15).
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Premie-belastning</div>
              <div className="side-card-h">
                {SEK(s.total_premium_monthly)} kr/mån
              </div>
              <div className="side-card-meta">
                {s.total_premium_monthly > 700
                  ? `Eleven betalar ${SEK(
                      s.total_premium_monthly - 700,
                    )} kr/mån över "rimlig"-tröskeln 700 kr.`
                  : "Inom rimlig nivå (under 700 kr/mån)."}
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Försäkring är <em>risköverföring</em>
              </div>
              <div className="side-card-meta">
                Eleven ska känna att premien är priset för att slippa stora
                oväntade kostnader. Coverage_gaps visar vilka risker som är
                oskyddade — driver beslutsfattande utan att tvinga.
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
