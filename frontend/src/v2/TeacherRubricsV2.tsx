/**
 * Lärar-vy · Rubric-mallar v2.
 *
 * Bug #17 · v2-port av v1 TeacherRubrics. Bedömnings-rubrics som lärare
 * kan återanvända på reflect-steg. Stödjer skapa/redigera/radera/klona/dela.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { useAutoStartTeacherGuide } from "./guides/GuideContext";
import { getToken } from "@/api/client";

type Criterion = {
  key: string;
  name: string;
  levels: string[];
};

type Template = {
  id: number;
  teacher_id: number | null;
  owner_name: string | null;
  name: string;
  description: string | null;
  criteria: Criterion[];
  is_shared: boolean;
  is_mine: boolean;
  created_at: string;
};

const EMPTY: Template = {
  id: 0,
  teacher_id: null,
  owner_name: null,
  name: "",
  description: "",
  criteria: [{ key: "c1", name: "Kriterium 1", levels: ["Låg", "Medel", "Hög"] }],
  is_shared: false,
  is_mine: true,
  created_at: "",
};


async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken() || ""}`,
      ...(opts.headers || {}),
    },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}


export function TeacherRubricsV2() {
  useAutoStartTeacherGuide();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Template | null>(null);

  async function load() {
    try {
      setTemplates(await api<Template[]>("/teacher/rubric-templates"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function save(t: Template) {
    const body = {
      name: t.name,
      description: t.description,
      criteria: t.criteria,
      is_shared: t.is_shared,
    };
    if (t.id === 0) {
      await api("/teacher/rubric-templates", {
        method: "POST",
        body: JSON.stringify(body),
      });
    } else {
      await api(`/teacher/rubric-templates/${t.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    }
    setEditing(null);
    load();
  }

  async function remove(id: number) {
    if (!confirm("Radera mallen?")) return;
    await api(`/teacher/rubric-templates/${id}`, { method: "DELETE" });
    load();
  }

  async function clone(id: number) {
    await api(`/teacher/rubric-templates/${id}/clone`, { method: "POST" });
    load();
  }

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <Link
          to="/teacher/v2"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            display: "inline-block",
            marginBottom: 18,
          }}
        >
          ← Tillbaka till klassen
        </Link>

        <header className="larare-head">
          <div>
            <span className="pill warm">Rubrics · bedömnings-mallar</span>
            <h1 className="larare-head-h1">
              Mallar för <em>reflect-bedömning</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Bygg återanvändbara rubrics som du kan applicera på reflect-
              steg i moduler. Dela med andra lärare eller håll dem privata.
            </p>
          </div>
          <div className="larare-head-meta">
            <button
              onClick={() => setEditing({ ...EMPTY })}
              style={{
                background: "var(--warm, #fbbf24)",
                color: "#1a1a1a",
                border: "none",
                padding: "10px 18px",
                borderRadius: 6,
                cursor: "pointer",
                fontWeight: 700,
              }}
            >
              + Ny mall
            </button>
          </div>
        </header>

        {err && (
          <div
            style={{
              padding: 14,
              background: "rgba(220,76,43,0.12)",
              border: "1px solid rgba(220,76,43,0.3)",
              borderRadius: 8,
              color: "#fda594",
              marginTop: 18,
              marginBottom: 16,
            }}
          >
            Fel: {err}
          </div>
        )}

        <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 10 }}>
          {templates.length === 0 ? (
            <div
              style={{
                padding: "40px 28px",
                textAlign: "center",
                color: "rgba(255,255,255,0.5)",
                fontFamily: "Source Serif 4, Georgia, serif",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 8,
              }}
            >
              Inga mallar än. Skapa en som du kan återanvända på reflect-steg.
            </div>
          ) : (
            templates.map((t) => (
              <article
                key={t.id}
                style={{
                  padding: 16,
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 10,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <strong style={{ color: "white", fontSize: "1.05rem" }}>
                      {t.name}
                    </strong>
                    {t.is_shared && (
                      <span
                        style={{
                          fontSize: 10,
                          fontFamily: "JetBrains Mono, monospace",
                          background: "rgba(110,231,183,0.18)",
                          color: "#6ee7b7",
                          padding: "2px 8px",
                          borderRadius: 100,
                          fontWeight: 700,
                          letterSpacing: 1.2,
                        }}
                      >
                        DELAD
                      </span>
                    )}
                    {!t.is_mine && (
                      <span style={{ fontSize: "0.78rem", color: "rgba(255,255,255,0.5)" }}>
                        av {t.owner_name ?? "system"}
                      </span>
                    )}
                  </div>
                  {t.description && (
                    <div style={{ fontSize: "0.9rem", color: "rgba(255,255,255,0.7)", marginTop: 4 }}>
                      {t.description}
                    </div>
                  )}
                  <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginTop: 6 }}>
                    {t.criteria.length} kriterier ·{" "}
                    {t.criteria.map((c) => c.name).join(", ")}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {t.is_mine ? (
                    <>
                      <button onClick={() => setEditing(t)} style={btnSmall()}>
                        Redigera
                      </button>
                      <button
                        onClick={() => remove(t.id)}
                        style={{ ...btnSmall(), color: "#fda594" }}
                      >
                        Radera
                      </button>
                    </>
                  ) : (
                    <button onClick={() => clone(t.id)} style={btnSmall()}>
                      Klona
                    </button>
                  )}
                </div>
              </article>
            ))
          )}
        </div>

        {editing && (
          <RubricEditor
            template={editing}
            onSave={save}
            onCancel={() => setEditing(null)}
          />
        )}
      </div>
    </div>
  );
}


function RubricEditor({
  template,
  onSave,
  onCancel,
}: {
  template: Template;
  onSave: (t: Template) => void | Promise<void>;
  onCancel: () => void;
}) {
  const [t, setT] = useState<Template>(template);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        zIndex: 9300,
        display: "grid",
        placeItems: "center",
        padding: 20,
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "rgba(15, 21, 37, 0.98)",
          border: "1px solid rgba(255,255,255,0.18)",
          borderRadius: 14,
          padding: 28,
          maxWidth: 720,
          width: "100%",
          maxHeight: "85vh",
          overflowY: "auto",
        }}
      >
        <h2 style={{ color: "white", fontSize: "1.3rem", margin: "0 0 18px" }}>
          {t.id === 0 ? "Ny rubric-mall" : `Redigera: ${t.name}`}
        </h2>
        <label style={lbl()}>
          Namn:
          <input
            type="text"
            value={t.name}
            onChange={(e) => setT({ ...t, name: e.target.value })}
            style={inputStyle()}
            placeholder="ex: Reflektion v.1"
          />
        </label>
        <label style={lbl()}>
          Beskrivning:
          <textarea
            rows={2}
            value={t.description || ""}
            onChange={(e) => setT({ ...t, description: e.target.value })}
            style={inputStyle()}
          />
        </label>

        <div style={{ marginTop: 20 }}>
          <strong style={{ color: "white" }}>Kriterier</strong>
          {t.criteria.map((c, i) => (
            <div
              key={c.key}
              style={{
                marginTop: 10,
                padding: 12,
                background: "rgba(255,255,255,0.03)",
                borderRadius: 8,
              }}
            >
              <input
                value={c.name}
                onChange={(e) => {
                  const next = [...t.criteria];
                  next[i] = { ...c, name: e.target.value };
                  setT({ ...t, criteria: next });
                }}
                style={{ ...inputStyle(), marginBottom: 8 }}
                placeholder="Kriterium-namn"
              />
              <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.6)" }}>
                Nivåer (komma-separerade):
              </div>
              <input
                value={c.levels.join(", ")}
                onChange={(e) => {
                  const next = [...t.criteria];
                  next[i] = {
                    ...c,
                    levels: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                  };
                  setT({ ...t, criteria: next });
                }}
                style={inputStyle()}
              />
              <button
                onClick={() => {
                  const next = t.criteria.filter((_, idx) => idx !== i);
                  setT({ ...t, criteria: next });
                }}
                style={{
                  ...btnSmall(),
                  color: "#fda594",
                  marginTop: 8,
                }}
              >
                Ta bort kriterium
              </button>
            </div>
          ))}
          <button
            onClick={() => {
              setT({
                ...t,
                criteria: [
                  ...t.criteria,
                  {
                    key: `c${t.criteria.length + 1}`,
                    name: `Kriterium ${t.criteria.length + 1}`,
                    levels: ["Låg", "Medel", "Hög"],
                  },
                ],
              });
            }}
            style={{ ...btnSmall(), marginTop: 10 }}
          >
            + Lägg till kriterium
          </button>
        </div>

        <label style={{ ...lbl(), display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={t.is_shared}
            onChange={(e) => setT({ ...t, is_shared: e.target.checked })}
          />
          <span>Dela med andra lärare</span>
        </label>

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <button
            onClick={() => onSave(t)}
            disabled={!t.name.trim()}
            style={{
              background: "var(--warm, #fbbf24)",
              color: "#1a1a1a",
              border: "none",
              padding: "10px 22px",
              borderRadius: 6,
              cursor: t.name.trim() ? "pointer" : "not-allowed",
              fontWeight: 700,
            }}
          >
            Spara
          </button>
          <button onClick={onCancel} style={btnSmall()}>
            Avbryt
          </button>
        </div>
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
    width: "100%",
    fontFamily: "inherit",
  };
}

function btnSmall(): React.CSSProperties {
  return {
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.18)",
    color: "rgba(255,255,255,0.85)",
    padding: "6px 12px",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: "0.85rem",
  };
}

function lbl(): React.CSSProperties {
  return {
    display: "block",
    color: "rgba(255,255,255,0.7)",
    fontSize: "0.85rem",
    marginTop: 14,
  };
}
