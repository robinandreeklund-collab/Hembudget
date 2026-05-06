/**
 * Lärar-vy · hantera klasser (skapa/byt namn/arkivera/radera).
 *
 * Bug #1 · när lärare har klasser visas dropdown vid 'skapa elev' i
 * stället för fritext. Klasser används också som filter i lärar-
 * dashboarden.
 *
 * Routas via /teacher/v2/klasser.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { getToken } from "@/api/client";

type SchoolClass = {
  id: number;
  label: string;
  display_name: string | null;
  description: string | null;
  is_archived: boolean;
  student_count: number;
  created_at: string;
};

const TOKEN = () => getToken() || "";

async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN()}`,
      ...(opts.headers || {}),
    },
  });
  if (!r.ok) {
    throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}


export function TeacherClassesV2() {
  const [classes, setClasses] = useState<SchoolClass[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newLabel, setNewLabel] = useState("");
  const [newDisplay, setNewDisplay] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    api<SchoolClass[]>("/v2/teacher/classes")
      .then(setClasses)
      .catch((e) => setError(String(e?.message || e)));
  };

  useEffect(() => {
    refresh();
  }, []);

  const create = async () => {
    if (!newLabel.trim()) return;
    setBusy(true);
    try {
      await api("/v2/teacher/classes", {
        method: "POST",
        body: JSON.stringify({
          label: newLabel.trim(),
          display_name: newDisplay.trim() || null,
        }),
      });
      setNewLabel("");
      setNewDisplay("");
      refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const archive = async (id: number, archived: boolean) => {
    try {
      await api(`/v2/teacher/classes/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_archived: !archived }),
      });
      refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  };

  const remove = async (id: number, label: string) => {
    if (!confirm(`Radera klass "${label}"? Eleverna behåller sin klass-text.`)) return;
    try {
      await api(`/v2/teacher/classes/${id}`, { method: "DELETE" });
      refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  };

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <Link to="/teacher/v2" style={{ color: "rgba(255,255,255,0.6)", textDecoration: "none" }}>
          ← Tillbaka till klassen
        </Link>

        <header style={{ marginTop: 24, marginBottom: 24 }}>
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              color: "var(--warm)",
              fontWeight: 700,
              letterSpacing: 1.4,
            }}
          >
            BUG #1 · KLASS-HANTERING
          </span>
          <h1 style={{ color: "white", fontSize: "1.6rem", margin: "8px 0 0" }}>
            Mina klasser
          </h1>
          <p style={{ color: "rgba(255,255,255,0.6)", marginTop: 6 }}>
            Skapa klasser så att 'skapa elev' visar dropdown istället för fritext.
            Eleven kopplas till klassen via <code>class_label</code>.
          </p>
        </header>

        {error && (
          <div style={{ padding: 12, background: "rgba(220,76,43,0.15)", borderRadius: 8, color: "#fda594", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Skapa ny */}
        <section
          style={{
            padding: 18,
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 12,
            marginBottom: 24,
          }}
        >
          <strong style={{ color: "white" }}>Skapa ny klass</strong>
          <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
            <input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Etikett (ex: 8A)"
              style={inputStyle()}
            />
            <input
              value={newDisplay}
              onChange={(e) => setNewDisplay(e.target.value)}
              placeholder="Visningsnamn (valfritt)"
              style={{ ...inputStyle(), flex: 1 }}
            />
            <button
              onClick={create}
              disabled={busy || !newLabel.trim()}
              style={{
                background: "var(--warm, #fbbf24)",
                color: "#1a1a1a",
                padding: "10px 18px",
                border: "none",
                borderRadius: 6,
                cursor: busy ? "wait" : "pointer",
                fontWeight: 600,
              }}
            >
              + Skapa klass
            </button>
          </div>
        </section>

        {/* Lista */}
        <section>
          <h2 style={{ color: "white", fontSize: "1.15rem", marginBottom: 12 }}>
            Klasser ({classes.length})
          </h2>
          {classes.length === 0 && (
            <div style={{ color: "rgba(255,255,255,0.5)" }}>
              Inga klasser skapade än. Skapa en ovan.
            </div>
          )}
          <div style={{ display: "grid", gap: 8 }}>
            {classes.map((c) => (
              <article
                key={c.id}
                style={{
                  padding: 14,
                  background: c.is_archived
                    ? "rgba(255,255,255,0.02)"
                    : "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 10,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  opacity: c.is_archived ? 0.6 : 1,
                }}
              >
                <div>
                  <strong style={{ color: "white", fontSize: "1.05rem" }}>
                    {c.label}
                  </strong>
                  {c.display_name && (
                    <span style={{ color: "rgba(255,255,255,0.6)", marginLeft: 10 }}>
                      · {c.display_name}
                    </span>
                  )}
                  <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.85rem", marginTop: 4 }}>
                    {c.student_count} elever
                    {c.is_archived && " · arkiverad"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => archive(c.id, c.is_archived)}
                    style={smallBtnStyle()}
                  >
                    {c.is_archived ? "Återställ" : "Arkivera"}
                  </button>
                  <button
                    onClick={() => remove(c.id, c.label)}
                    style={{ ...smallBtnStyle(), color: "#fda594" }}
                  >
                    Radera
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}


function inputStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.15)",
    color: "white",
    padding: "8px 12px",
    borderRadius: 6,
  };
}

function smallBtnStyle(): React.CSSProperties {
  return {
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.15)",
    color: "rgba(255,255,255,0.85)",
    padding: "6px 12px",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: "0.85rem",
  };
}
