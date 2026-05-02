/**
 * Lärar-vy · klass-aggregat över elevers företag.
 *
 * Spec: deb/README.md avsnitt 8 ("Klassöversikt").
 *
 * Visar en tabell över alla lärarens elever — för de som har
 * företagsläget på + ett aktivt bolag visas: bolagsnamn, form, rykte,
 * vecka, omsättning 4v, vinst 4v, obetalda fakturor, öppna offerter.
 *
 * Lärare kan också mass-skicka leverantörsfaktura till valda elever
 * (klick på leverantörsfaktura-knappen).
 *
 * Routas via /teacher/v2/foretag-klass.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { teacherBizApi, type TeacherClassOverview } from "./biz/api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function TeacherForetagKlassPage() {
  const [data, setData] = useState<TeacherClassOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showSupplier, setShowSupplier] = useState(false);
  const navigate = useNavigate();

  function refresh() {
    teacherBizApi.classOverview()
      .then(setData)
      .catch((e) => setError(String((e as Error).message || e)));
  }

  useEffect(() => { refresh(); }, []);

  function toggle(sid: number) {
    const next = new Set(selected);
    if (next.has(sid)) next.delete(sid);
    else next.add(sid);
    setSelected(next);
  }

  if (error) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container">
          <p className="error">Fel: {error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container"><p>Laddar klassdata…</p></div>
      </div>
    );
  }

  const eligible = data.rows.filter(r => r.has_company);

  return (
    <div className="v2-shell">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />
      <div className="lan-container" style={{ paddingBottom: 64 }}>
        <button
          onClick={() => navigate("/teacher/v2")}
          style={{
            background: "transparent",
            border: "1px solid rgba(99,102,241,0.3)",
            color: "#c7d2fe",
            padding: "6px 12px",
            borderRadius: 6,
            cursor: "pointer",
            marginBottom: 16,
          }}
        >
          ← Tillbaka
        </button>

        <h1 style={{ margin: "0 0 8px 0" }}>Klassens företag</h1>
        <p style={{ color: "rgba(255,255,255,0.55)", marginTop: 0 }}>
          Aggregerad bild av alla elevers företag. Mass-skicka
          leverantörsfaktura, granska kundfakturor, jämför rykte.
        </p>

        {/* Stats */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
            marginTop: 16,
          }}
        >
          <Stat label="Elever totalt" value={data.n_students.toString()} />
          <Stat label="Med aktivt bolag"
                value={data.n_with_active_company.toString()} />
          <Stat label="Snitt-rykte"
                value={data.avg_reputation !== null
                  ? `${data.avg_reputation}/100` : "—"} />
          <Stat label="Snitt-omsättning 4v"
                value={data.avg_revenue_4w !== null
                  ? `${SEK(data.avg_revenue_4w)} kr` : "—"} />
        </div>

        <div style={{ marginTop: 24, marginBottom: 12 }}>
          <button
            onClick={() => setShowSupplier(true)}
            disabled={selected.size === 0}
            style={{
              background: selected.size > 0
                ? "rgba(99,102,241,0.25)" : "rgba(99,102,241,0.08)",
              border: "1px solid rgba(99,102,241,0.4)",
              color: "white",
              padding: "10px 18px",
              borderRadius: 8,
              cursor: selected.size > 0 ? "pointer" : "not-allowed",
              fontWeight: 600,
            }}
          >
            Skicka leverantörsfaktura till {selected.size} markerad{selected.size === 1 ? "" : "e"} elev{selected.size === 1 ? "" : "er"}
          </button>
        </div>

        <div style={{
          background: "rgba(15,21,37,0.4)",
          border: "1px solid rgba(99,102,241,0.18)",
          borderRadius: 12, padding: 16, marginTop: 8,
        }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr style={{ color: "#aab", textAlign: "left",
                borderBottom: "1px solid rgba(99,102,241,0.2)" }}>
                <th style={{ padding: "8px 4px", width: 30 }}></th>
                <th style={{ padding: "8px 4px" }}>Elev</th>
                <th style={{ padding: "8px 4px" }}>Bolag</th>
                <th style={{ padding: "8px 4px" }}>Form</th>
                <th style={{ padding: "8px 4px", textAlign: "right" }}>Rykte</th>
                <th style={{ padding: "8px 4px", textAlign: "center" }}>Vecka</th>
                <th style={{ padding: "8px 4px", textAlign: "right" }}>Omsättning 4v</th>
                <th style={{ padding: "8px 4px", textAlign: "right" }}>Vinst 4v</th>
                <th style={{ padding: "8px 4px", textAlign: "center" }}>Obetalda</th>
                <th style={{ padding: "8px 4px", textAlign: "center" }}>Öppna</th>
                <th style={{ padding: "8px 4px" }}></th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.student_id}
                    style={{ borderBottom: "1px solid rgba(99,102,241,0.08)" }}>
                  <td style={{ padding: "8px 4px" }}>
                    {r.has_company && (
                      <input
                        type="checkbox"
                        checked={selected.has(r.student_id)}
                        onChange={() => toggle(r.student_id)}
                      />
                    )}
                  </td>
                  <td style={{ padding: "8px 4px" }}>
                    <div style={{ color: "white" }}>{r.student_name}</div>
                    <div style={{ color: "#aab", fontSize: "0.75rem" }}>
                      {r.biz_mode_enabled ? "biz aktivt" : "biz av"}
                    </div>
                  </td>
                  <td style={{ padding: "8px 4px" }}>
                    {r.company_name ?? "—"}
                  </td>
                  <td style={{ padding: "8px 4px", color: "#aab" }}>
                    {r.company_form ?? "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "right" }}>
                    {r.reputation !== null ? (
                      <span style={{
                        color: r.reputation >= 70 ? "#6ee7b7"
                          : r.reputation >= 40 ? "white" : "#fda594",
                        fontWeight: 600,
                      }}>
                        {r.reputation}/100
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "center", color: "#aab" }}>
                    {r.week_no ?? "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "right" }}>
                    {r.revenue_4w !== null ? `${SEK(r.revenue_4w)} kr` : "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "right" }}>
                    {r.profit_4w !== null ? (
                      <span style={{
                        color: r.profit_4w >= 0 ? "#6ee7b7" : "#fda594",
                      }}>
                        {SEK(r.profit_4w)} kr
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "center" }}>
                    {r.n_invoices_unpaid !== null ? (
                      <span style={{
                        color: r.n_invoices_unpaid > 0 ? "#fbbf24" : "#aab",
                      }}>
                        {r.n_invoices_unpaid}
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "center", color: "#aab" }}>
                    {r.n_open_opportunities ?? "—"}
                  </td>
                  <td style={{ padding: "8px 4px" }}>
                    <button
                      onClick={() => navigate(`/teacher/v2/foretag/${r.student_id}`)}
                      style={{
                        background: "transparent",
                        border: "1px solid rgba(99,102,241,0.3)",
                        color: "#c7d2fe",
                        padding: "4px 10px",
                        borderRadius: 4,
                        cursor: "pointer",
                        fontSize: "0.8rem",
                      }}
                    >
                      Detaljer →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {showSupplier && (
          <SupplierMassModal
            studentIds={Array.from(selected)}
            studentNames={eligible.filter(r => selected.has(r.student_id))
              .map(r => r.student_name)}
            onClose={(refreshed) => {
              setShowSupplier(false);
              if (refreshed) {
                setSelected(new Set());
                refresh();
              }
            }}
          />
        )}
      </div>
    </div>
  );
}


function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      background: "rgba(15,21,37,0.4)",
      border: "1px solid rgba(99,102,241,0.18)",
      borderRadius: 8, padding: 12,
    }}>
      <div style={{
        fontSize: 9, letterSpacing: 1.3, color: "#818cf8",
        textTransform: "uppercase",
        fontFamily: "JetBrains Mono, monospace",
      }}>{label}</div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}


function SupplierMassModal({
  studentIds, studentNames, onClose,
}: {
  studentIds: number[];
  studentNames: string[];
  onClose: (refreshed: boolean) => void;
}) {
  const [sender, setSender] = useState("Hyra · Storgatan 12");
  const [desc, setDesc] = useState("Hyra för Q3 2026");
  const [amount, setAmount] = useState("4500");
  const [vat, setVat] = useState("0.25");
  const [days, setDays] = useState("14");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{
    n_created: number; n_skipped_no_company: number;
  } | null>(null);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      const r = await teacherBizApi.sendSupplierInvoice({
        target_student_ids: studentIds,
        sender_name: sender,
        description: desc,
        amount_excl_vat: parseInt(amount, 10),
        vat_rate: parseFloat(vat),
        due_in_days: parseInt(days, 10),
        notes: notes.trim() || undefined,
      });
      setResult(r);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(result !== null)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 540, width: "100%",
          maxHeight: "85vh", overflowY: "auto",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>
          Skicka leverantörsfaktura
        </h2>
        <p style={{ color: "#aab", fontSize: "0.85rem" }}>
          Till {studentIds.length} elev{studentIds.length === 1 ? "" : "er"}:{" "}
          {studentNames.slice(0, 3).join(", ")}
          {studentNames.length > 3 && ` + ${studentNames.length - 3} till`}
        </p>

        {result === null ? (
          <>
            <Field label="Avsändare (företagsnamn)" value={sender}
                   onChange={setSender} />
            <Field label="Beskrivning" value={desc} onChange={setDesc} />
            <Field label="Belopp (kr exkl moms)" value={amount}
                   onChange={setAmount} type="number" />
            <Field label="Momssats" value={vat} onChange={setVat} type="number" />
            <Field label="Förfaller om (dagar)" value={days}
                   onChange={setDays} type="number" />
            <Field label="Lärar-anteckning (frivilligt)" value={notes}
                   onChange={setNotes} />

            {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button onClick={submit} disabled={submitting}
                style={{
                  background: "rgba(99,102,241,0.25)",
                  border: "1px solid rgba(99,102,241,0.5)",
                  color: "white", padding: "8px 16px", borderRadius: 6,
                  cursor: "pointer", fontWeight: 600,
                }}>
                {submitting ? "Skickar…" : "Skicka"}
              </button>
              <button onClick={() => onClose(false)}
                style={{
                  background: "transparent",
                  border: "1px solid rgba(99,102,241,0.3)",
                  color: "#c7d2fe", padding: "8px 16px", borderRadius: 6,
                  cursor: "pointer",
                }}>
                Avbryt
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{
              padding: 14, borderRadius: 8,
              background: "rgba(34,197,94,0.1)",
              border: "1px solid rgba(34,197,94,0.3)",
              marginTop: 16,
            }}>
              <h3 style={{ color: "#6ee7b7", margin: "0 0 8px" }}>Klart!</h3>
              <p style={{ color: "white", margin: 0 }}>
                Skickat till <strong>{result.n_created}</strong> elever.
                {result.n_skipped_no_company > 0 && (
                  <><br />
                  <span style={{ color: "#aab", fontSize: "0.85rem" }}>
                    {result.n_skipped_no_company} elev(er) hade inget aktivt
                    bolag och hoppades över.
                  </span></>
                )}
              </p>
            </div>
            <button onClick={() => onClose(true)}
              style={{
                background: "rgba(99,102,241,0.25)",
                border: "1px solid rgba(99,102,241,0.5)",
                color: "white", padding: "8px 16px", borderRadius: 6,
                cursor: "pointer", fontWeight: 600, marginTop: 16,
              }}>
              Klar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function Field({
  label, value, onChange, type = "text",
}: {
  label: string; value: string;
  onChange: (v: string) => void; type?: string;
}) {
  return (
    <label style={{ color: "white", display: "block", marginTop: 12 }}>
      {label}
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          display: "block", width: "100%", marginTop: 4,
          padding: "8px 10px", borderRadius: 6,
          border: "1px solid rgba(99,102,241,0.3)",
          background: "rgba(15,21,37,0.5)", color: "white",
          fontSize: "0.95rem",
        }}
      />
    </label>
  );
}
