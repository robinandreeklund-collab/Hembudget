/**
 * Lärar-vy · skapa elev (motsv. larare.html#p-skapa).
 *
 * Routas via /teacher/v2/skapa.
 *
 * Visar:
 * - Snabb-skapa-formulär: förnamn / efternamn-initial / arketyp /
 *   partner-modell / spend-profil / startnivå
 * - Lista skapade elever (senast först) · markerar oaktiverade
 *   med accent-färg och "väntar"-text
 * - Login-koden visas tydligt i mono-font efter creation så läraren
 *   kan kopiera och dela
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2CreatedStudentRow,
  type V2CreatedStudentsResponse,
  type V2CharacterArchetype,
  type V2CreateStudentIn,
} from "./api";
import { V2Banner } from "./V2Banner";
import { LoginQrModal } from "./LoginQrModal";
import { printAllLoginQrs } from "./printAllLoginQrs";
import "./larare.css";

const ARCHETYPE_LABEL: Record<V2CharacterArchetype, string> = {
  random: "Slumpa karaktär",
  vard_underskoterska: "Vård-undersköterska",
  it_konsult_junior: "IT-konsult junior",
  butiksbitrade: "Butiksbiträde",
  kassorska: "Kassörska",
  lar_vikarie: "Lärar-vikarie",
  anstalld_kommun: "Anställd i kommun",
  studerande_gymnasium: "Studerande gymnasium",
};

const PARTNER_LABEL: Record<string, string> = {
  solo: "Solo",
  ai: "AI-partner",
  klasskompis: "Klasskompis",
};

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

export function TeacherCreateStudentV2() {
  const [data, setData] = useState<V2CreatedStudentsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<V2CreatedStudentRow | null>(null);
  const [qrStudentId, setQrStudentId] = useState<number | null>(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const navigate = useNavigate();

  async function load() {
    try {
      const next = await v2Api.teacherListCreatedStudents();
      setData(next);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function bulkDeleteAll() {
    if (!data || data.rows.length === 0) return;
    const count = data.rows.length;
    const first = window.confirm(
      `Radera ALLA ${count} elever permanent?\n\n` +
      `All scope-data, BankID-sessioner, profiler och login-koder ` +
      `försvinner. Detta GÅR INTE att ångra.\n\n` +
      `Klicka OK för att gå vidare till bekräftelse.`,
    );
    if (!first) return;
    const second = window.prompt(
      `Skriv "RADERA ${count}" för att bekräfta:`,
    );
    if (second !== `RADERA ${count}`) {
      alert("Bekräftelse-text matchade inte. Avbryter.");
      return;
    }
    setBulkDeleting(true);
    try {
      const res = await v2Api.teacherDeleteAllMyStudents();
      alert(
        `Radering klar: ${res.deleted_count} elever borta, ` +
        `${res.failed_count} misslyckades` +
        (res.failed_count > 0
          ? `\nFailed IDs: ${res.failed_ids.join(", ")}`
          : ""),
      );
      await load();
    } catch (e) {
      alert(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBulkDeleting(false);
    }
  }

  useEffect(() => {
    load();
    // Hämta super-admin-status. Importerar api dynamiskt för att inte
    // ändra existerande imports.
    import("../api/client").then(({ api }) => {
      api<{ is_super_admin: boolean }>("/admin/ai/me")
        .then((d) => {
          if (d && typeof d.is_super_admin === "boolean") {
            setIsSuperAdmin(d.is_super_admin);
          }
        })
        .catch(() => undefined);
    });
  }, []);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda elev-listan
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar elev-listan…</div>
      </div>
    );
  }

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till klassen
        </a>

        <header className="larare-head">
          <div>
            <span className="pill">Lärar-admin · Skapa elever</span>
            <h1 className="larare-head-h1">
              Lägg till <em>nya elever</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Karaktärsgenerering · 8-teckens-kod · partner-modell · Nivå 1
              default. Eleven får v2 aktiverat direkt och hamnar på
              v2-onboardingen vid första inloggning.
            </p>
          </div>
          <div className="larare-head-meta">
            Totalt elever: <strong>{data.total_count}</strong>
            <br />
            Ej aktiverade:{" "}
            <strong style={{
              color:
                data.pending_activation_count > 0
                  ? "var(--warm, #fbbf24)"
                  : "#6ee7b7",
            }}>
              {data.pending_activation_count}
            </strong>
            <br />
            Aktiva:{" "}
            <strong style={{ color: "#6ee7b7" }}>
              {data.total_count - data.pending_activation_count}
            </strong>
          </div>
        </header>

        {/* Bekräftelse-card vid lyckad creation */}
        {created && (
          <article
            className="s-card green"
            style={{
              background:
                "linear-gradient(135deg, rgba(110,231,183,0.06), rgba(15,21,37,0.5))",
              borderColor: "rgba(110,231,183,0.35)",
              marginBottom: 22,
            }}
          >
            <div className="s-card-eye green">✓ Elev skapad</div>
            <div className="s-card-h">
              <em style={{ color: "#6ee7b7" }}>{created.student_name}</em>{" "}
              · login-kod{" "}
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 22,
                  fontWeight: 700,
                  color: "var(--warm, #fbbf24)",
                  letterSpacing: 3,
                  marginLeft: 6,
                  padding: "4px 12px",
                  background: "rgba(251,191,36,0.10)",
                  borderRadius: 6,
                }}
              >
                {created.login_code}
              </span>
            </div>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13.5,
                color: "rgba(255,255,255,0.7)",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              Spendprofil: <strong>{created.spend_profile || "—"}</strong>{" "}
              · partner: <strong>{PARTNER_LABEL[created.partner_model || ""] || created.partner_model || "—"}</strong>{" "}
              · nivå: <strong>{created.starting_level}</strong>. Dela
              koden med eleven så loggar hen in på{" "}
              <code style={{ color: "var(--warm)" }}>/student/login</code>.
            </p>
            <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
              <button
                type="button"
                onClick={() => setQrStudentId(created.student_id)}
                className="larare-tb-btn solid"
                style={{
                  background: "var(--warm, #fbbf24)",
                  color: "#422006",
                  borderColor: "var(--warm, #fbbf24)",
                }}
              >
                ▦ Visa QR-kod
              </button>
              <Link
                to={`/teacher/v2/elev/${created.student_id}`}
                className="larare-tb-btn"
              >
                Öppna elev-detalj →
              </Link>
            </div>
          </article>
        )}

        {/* Snabb-skapa formulär */}
        <CreateForm
          onCreated={(row) => {
            setCreated(row);
            load();
            // Scrolla upp så användaren ser bekräftelse-cardet
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />

        {/* Lista skapade elever */}
        <div
          style={{
            marginTop: 28,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            flexWrap: "wrap",
            gap: 10,
            marginBottom: 14,
          }}
        >
          <div className="section-title" style={{ margin: 0 }}>
            Skapade elever ({data.total_count})
            {data.pending_activation_count > 0 && (
              <span style={{ color: "var(--warm)" }}>
                {" "}
                · {data.pending_activation_count} väntar på aktivering
              </span>
            )}
          </div>
          {data.rows.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={async () => {
                  const r = await printAllLoginQrs();
                  if (r.error) alert(r.error);
                }}
                className="larare-tb-btn solid"
                style={{
                  background: "var(--warm, #fbbf24)",
                  color: "#422006",
                  borderColor: "var(--warm, #fbbf24)",
                }}
              >
                🖨 Skriv ut alla koder ({data.rows.length})
              </button>
              {isSuperAdmin && (
                <button
                  type="button"
                  onClick={bulkDeleteAll}
                  disabled={bulkDeleting}
                  className="larare-tb-btn solid"
                  title="Super-admin: radera ALLA mina elever permanent"
                  style={{
                    background: bulkDeleting
                      ? "rgba(239,68,68,0.4)"
                      : "rgba(239,68,68,0.9)",
                    color: "#fff",
                    borderColor: "rgba(239,68,68,1)",
                    cursor: bulkDeleting ? "wait" : "pointer",
                  }}
                >
                  {bulkDeleting
                    ? "⏳ Raderar…"
                    : `🗑 Radera ALLA elever (${data.rows.length})`}
                </button>
              )}
            </div>
          )}
        </div>

        {data.rows.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.5)",
            }}
          >
            Du har inga elever än. Använd formuläret ovan för att skapa
            den första.
          </div>
        ) : (
          <div
            style={{
              background: "rgba(15,21,37,0.7)",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "120px 1.5fr 110px 110px 110px 100px 80px",
                gap: 12,
                padding: "11px 16px",
                background: "rgba(0,0,0,0.15)",
                borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: 1.2,
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.5)",
              }}
            >
              <span>Kod</span>
              <span>Karaktär</span>
              <span>Profil</span>
              <span>Partner</span>
              <span>Nivå</span>
              <span>Skapad</span>
              <span>QR</span>
              <span>Radera</span>
            </div>
            {data.rows.map((row) => (
              <CreatedStudentRow
                key={row.student_id}
                row={row}
                onShowQr={() => setQrStudentId(row.student_id)}
                onDelete={async () => {
                  if (!confirm(
                    `Radera ${row.student_name} permanent? `
                    + "All scope-data, BankID-sessioner, profil och login-kod försvinner. "
                    + "Detta går inte att ångra."
                  )) return;
                  try {
                    await v2Api.teacherDeleteStudent(row.student_id);
                    const next = await v2Api.teacherListCreatedStudents();
                    setData(next);
                  } catch (e) {
                    alert(`Fel: ${String((e as Error)?.message || e)}`);
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>

      {qrStudentId !== null && (
        <LoginQrModal
          studentId={qrStudentId}
          onClose={() => setQrStudentId(null)}
        />
      )}
    </div>
  );
}

function CreateForm({
  onCreated,
}: {
  onCreated: (row: V2CreatedStudentRow) => void;
}) {
  const [firstName, setFirstName] = useState("");
  const [lastInitial, setLastInitial] = useState("");
  const [classLabel, setClassLabel] = useState<string>("");
  const [classes, setClasses] = useState<Array<{
    id: number; label: string; display_name: string | null; student_count: number;
  }>>([]);
  const [archetype, setArchetype] = useState<V2CharacterArchetype>("random");
  const [partnerModel, setPartnerModel] = useState<
    "auto" | "solo" | "ai" | "klasskompis"
  >("auto");
  const [spendProfile, setSpendProfile] = useState<
    "auto" | "sparsam" | "balanserad" | "slosa"
  >("auto");
  const [startingLevel, setStartingLevel] = useState<number>(1);
  const [guardianEmail, setGuardianEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bug #1 · hämta lärarens klasser för dropdown
  useEffect(() => {
    fetch("/v2/teacher/classes", {
      headers: { Authorization: `Bearer ${sessionStorage.getItem("hembudget_token") || ""}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setClasses)
      .catch(() => undefined);
  }, []);

  async function submit() {
    if (submitting || firstName.trim().length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: V2CreateStudentIn = {
        first_name: firstName.trim(),
        last_initial: lastInitial.trim() || undefined,
        archetype,
        starting_level: startingLevel,
        guardian_email: guardianEmail.trim() || undefined,
        class_label: classLabel.trim() || undefined,
      };
      if (spendProfile !== "auto") {
        payload.spend_profile = spendProfile;
      }
      if (partnerModel !== "auto") {
        payload.partner_model = partnerModel;
      }
      const row = await v2Api.teacherCreateStudent(payload);
      onCreated(row);
      // Reset (förutom level)
      setFirstName("");
      setLastInitial("");
      setArchetype("random");
      setPartnerModel("auto");
      setSpendProfile("auto");
      setGuardianEmail("");
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <article
      className="s-card"
      style={{
        marginBottom: 22,
        borderLeftWidth: 3,
        borderLeftColor: "var(--accent, #dc4c2b)",
      }}
    >
      <div className="s-card-eye accent">Snabb-skapa · en elev</div>
      <div className="s-card-h">
        Auto-genererad <em>karaktär</em> + 8-teckens-kod.
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          gap: 12,
          marginTop: 14,
        }}
      >
        <FormField label="Förnamn *">
          <input
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="ex: Ida"
            style={inputStyle()}
            required
          />
        </FormField>
        <FormField label="Efternamn-initial">
          <input
            value={lastInitial}
            onChange={(e) => setLastInitial(e.target.value)}
            placeholder="ex: P."
            maxLength={2}
            style={inputStyle()}
          />
        </FormField>
        <FormField label="Karaktärs-arketyp">
          <select
            value={archetype}
            onChange={(e) =>
              setArchetype(e.target.value as V2CharacterArchetype)
            }
            style={inputStyle()}
          >
            {Object.entries(ARCHETYPE_LABEL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Partner-modell">
          <select
            value={partnerModel}
            onChange={(e) =>
              setPartnerModel(e.target.value as typeof partnerModel)
            }
            style={inputStyle()}
          >
            <option value="auto">
              Slumpa (60% solo · 35% AI · 5% par)
            </option>
            <option value="solo">Solo (ingen partner)</option>
            <option value="ai">AI-genererad partner</option>
            <option value="klasskompis">Par med klasskompis</option>
          </select>
        </FormField>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 12,
          marginTop: 12,
        }}
      >
        <FormField label="Spendprofil">
          <select
            value={spendProfile}
            onChange={(e) =>
              setSpendProfile(e.target.value as typeof spendProfile)
            }
            style={inputStyle()}
          >
            <option value="auto">Auto från nivå</option>
            <option value="sparsam">Sparsam</option>
            <option value="balanserad">Balanserad</option>
            <option value="slosa">Slösa</option>
          </select>
        </FormField>
        <FormField label="Vårdnadshavar-mail (visning)">
          <input
            type="email"
            value={guardianEmail}
            onChange={(e) => setGuardianEmail(e.target.value)}
            placeholder="förälder@exempel.se"
            style={inputStyle()}
          />
        </FormField>
        <FormField label="Klass">
          {classes.length > 0 ? (
            <select
              value={classLabel}
              onChange={(e) => setClassLabel(e.target.value)}
              style={inputStyle()}
            >
              <option value="">— välj klass —</option>
              {classes.map((c) => (
                <option key={c.id} value={c.label}>
                  {c.label}
                  {c.display_name ? ` · ${c.display_name}` : ""}
                  {" "}({c.student_count} elever)
                </option>
              ))}
            </select>
          ) : (
            <input
              value={classLabel}
              onChange={(e) => setClassLabel(e.target.value)}
              placeholder="ex: 8A (skapa via Klasser-vyn)"
              style={inputStyle()}
            />
          )}
        </FormField>
        <FormField label="Startnivå">
          <select
            value={startingLevel}
            onChange={(e) => setStartingLevel(Number(e.target.value))}
            style={inputStyle()}
          >
            <option value={1}>▰▱▱ Nivå 1 · Sparsam (default)</option>
            <option value={2}>▰▰▱ Nivå 2 · Balanserad</option>
            <option value={3}>▰▰▰ Nivå 3 · Slösa</option>
          </select>
        </FormField>
      </div>

      {error && (
        <div
          style={{
            color: "#fca5a5",
            fontSize: 11,
            marginTop: 10,
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          display: "flex",
          gap: 10,
          marginTop: 16,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <button
          type="button"
          disabled={submitting || firstName.trim().length === 0}
          onClick={submit}
          className="larare-tb-btn solid"
          style={{
            cursor:
              submitting || firstName.trim().length === 0
                ? "not-allowed"
                : "pointer",
          }}
        >
          {submitting ? "Skapar…" : "+ Skapa elev"}
        </button>
        <span
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9.5,
            color: "rgba(255,255,255,0.4)",
            letterSpacing: 0.5,
          }}
        >
          Login-koden visas i bekräftelsen efter creation. Kopiera och
          dela med eleven.
        </span>
      </div>
    </article>
  );
}

function CreatedStudentRow({
  row,
  onShowQr,
  onDelete,
}: {
  row: V2CreatedStudentRow;
  onShowQr: () => void;
  onDelete: () => void;
}) {
  const isPending = !row.activated;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "120px 1.5fr 110px 110px 110px 100px 80px 70px",
        gap: 12,
        padding: "12px 16px",
        borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
        alignItems: "center",
        color: "rgba(255,255,255,0.92)",
      }}
    >
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 14,
          fontWeight: 700,
          color: "var(--warm, #fbbf24)",
          letterSpacing: 2,
        }}
      >
        {row.login_code}
      </span>
      <Link
        to={`/teacher/v2/elev/${row.student_id}`}
        style={{ textDecoration: "none", color: "inherit" }}
      >
        <div
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13.5,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {row.student_name}
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: isPending ? "var(--warm, #fbbf24)" : "#6ee7b7",
              flexShrink: 0,
            }}
            title={isPending ? "Väntar på första login" : "Aktiv"}
          />
        </div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            color: "rgba(255,255,255,0.4)",
          }}
        >
          {ARCHETYPE_LABEL[row.archetype] || row.archetype} ·{" "}
          {isPending ? "VÄNTAR" : "AKTIV"}
        </div>
      </Link>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.6)",
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        {row.spend_profile || "—"}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.6)",
        }}
      >
        {PARTNER_LABEL[row.partner_model || ""] || row.partner_model || "—"}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color:
            row.starting_level === 1
              ? "#6ee7b7"
              : row.starting_level === 2
              ? "var(--warm, #fbbf24)"
              : "#fda594",
          fontWeight: 700,
        }}
      >
        ▰{row.starting_level >= 2 ? "▰" : "▱"}
        {row.starting_level >= 3 ? "▰" : "▱"} N{row.starting_level}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.5)",
        }}
      >
        {SHORT_DATE(row.created_at)}
      </span>
      <button
        type="button"
        onClick={onShowQr}
        title="Visa QR-kod"
        style={{
          background: "rgba(251,191,36,0.10)",
          border: "1px solid rgba(251,191,36,0.35)",
          color: "var(--warm, #fbbf24)",
          padding: "6px 10px",
          borderRadius: 6,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          cursor: "pointer",
        }}
      >
        ▦ QR
      </button>
      <button
        type="button"
        onClick={onDelete}
        title="Radera elev permanent"
        style={{
          background: "rgba(252,165,165,0.08)",
          border: "1px solid rgba(252,165,165,0.4)",
          color: "#fda594",
          padding: "6px 10px",
          borderRadius: 6,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          cursor: "pointer",
        }}
      >
        ✕ Radera
      </button>
    </div>
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 1,
          textTransform: "uppercase",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    width: "100%",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
    color: "#fff",
    padding: "9px 12px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 13,
  };
}
