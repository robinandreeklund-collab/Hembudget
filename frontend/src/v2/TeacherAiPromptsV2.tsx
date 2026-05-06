/**
 * Lärar-AI-laboratorium · /teacher/v2/ai-prompts
 *
 * Lärare anpassar AI-systempromptar för:
 * - Personas eleven möter (Maria HR, Mats Arbetsförmedlingen, studiecoach)
 * - Företagsmotor (offert-pitch, marknadsföring, jobb-beskrivningar)
 * - Bedömningsstöd (reflektion-feedback, rubric, aktie-feedback...)
 * - Innehållsgenerering (modul, kategori-förklaring...)
 *
 * Designprinciper:
 * - Default-text alltid synlig (skrivskyddad, monospace)
 * - Egen anpassning bredvid (textarea)
 * - Förhandsgranska kör en riktig AI-call mot exempel-input · läraren
 *   ser EXAKT hur deras anpassning beter sig innan eleven möter den
 * - Återställ / aktivera-toggle
 * - Variabel-hint för promptar med {employer}, {profession} etc
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Banner } from "./V2Banner";


type PromptTemplate = {
  name: string;
  description: string;
  text: string;
};

type PromptSpec = {
  key: string;
  label: string;
  category: "personas" | "biz_eval" | "teacher_grading" | "content_gen";
  description: string;
  default_text: string;
  variables: string[];
  used_at: string;
  model: string;
  preview_input: string;
  templates: PromptTemplate[];
};

type PromptOverride = {
  key: string;
  custom_text: string;
  is_active: boolean;
  updated_at: string | null;
};

type PreviewResult = {
  output_text: string;
  input_tokens: number;
  output_tokens: number;
  model: string;
};


const CATEGORY_LABELS: Record<PromptSpec["category"], string> = {
  personas: "Personas eleven möter",
  biz_eval: "Företagsmotor · bedömningar",
  teacher_grading: "Lärar-bedömningsstöd",
  content_gen: "Innehållsgenerering",
};

const CATEGORY_DESCRIPTIONS: Record<PromptSpec["category"], string> = {
  personas: "Maria, Mats och studiecoachen pratar direkt med eleven. Här styr du tonen.",
  biz_eval: "AI som bedömer elevens företagande (pitch, marknadsföring) och genererar nya jobb.",
  teacher_grading: "Förslag till feedback + bedömningar mot rubric. AI ersätter inte din bedömning.",
  content_gen: "Generatorer av förklaringar, modulskisser och sammanfattningar.",
};


export function TeacherAiPromptsV2() {
  const [specs, setSpecs] = useState<PromptSpec[]>([]);
  const [overrides, setOverrides] = useState<Record<string, PromptOverride>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<PromptSpec[]>("/v2/teacher/ai-prompts/registry"),
      api<PromptOverride[]>("/v2/teacher/ai-prompts"),
    ])
      .then(([s, o]) => {
        setSpecs(s);
        const m: Record<string, PromptOverride> = {};
        for (const r of o) m[r.key] = r;
        setOverrides(m);
      })
      .catch((e) => setError(String((e as Error).message || e)))
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => {
    const out: Record<string, PromptSpec[]> = {
      personas: [],
      biz_eval: [],
      teacher_grading: [],
      content_gen: [],
    };
    for (const sp of specs) out[sp.category].push(sp);
    return out;
  }, [specs]);

  function updateLocal(key: string, partial: Partial<PromptOverride>) {
    setOverrides((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] ?? {
          key,
          custom_text: "",
          is_active: true,
          updated_at: null,
        }),
        ...partial,
      },
    }));
  }

  async function exportJson() {
    try {
      const data = await api<{
        version: number;
        exported_at: string;
        teacher_id: number;
        prompts: PromptOverride[];
      }>("/v2/teacher/ai-prompts/export/json");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ai-promptar-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Export-fel: ${(e as Error).message || e}`);
    }
  }

  function triggerImport() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed.prompts)) {
          throw new Error("Filen saknar prompts[]-array.");
        }
        if (
          !confirm(
            `Importera ${parsed.prompts.length} prompts? Befintliga "
            "anpassningar skrivs över.`,
          )
        ) {
          return;
        }
        const result = await api<{
          imported: number;
          skipped: number;
          rejected: { key: string; reason: string }[];
        }>("/v2/teacher/ai-prompts/import/json", {
          method: "POST",
          body: JSON.stringify({
            version: 1,
            prompts: parsed.prompts,
            overwrite_existing: true,
          }),
        });
        let msg = `Importerade ${result.imported}, hoppade över ${result.skipped}.`;
        if (result.rejected.length > 0) {
          msg += `\n\nAvvisade:\n` + result.rejected
            .map((r) => `· ${r.key}: ${r.reason}`).join("\n");
        }
        alert(msg);
        // Ladda om overrides
        const refreshed = await api<PromptOverride[]>("/v2/teacher/ai-prompts");
        const m: Record<string, PromptOverride> = {};
        for (const r of refreshed) m[r.key] = r;
        setOverrides(m);
      } catch (e) {
        alert(`Import-fel: ${(e as Error).message || e}`);
      }
    };
    input.click();
  }

  if (loading) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div style={shellStyle}>Laddar AI-promptar…</div>
      </div>
    );
  }

  return (
    <div className="v2-shell">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />
      <div style={shellStyle}>
        <header style={{ marginBottom: 28 }}>
          <div style={eyebrowStyle}>● AI-LABORATORIUM · KLASS-INSTÄLLNING</div>
          <h1 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 32, color: "#fff", margin: "8px 0 6px", fontWeight: 700, letterSpacing: -0.5 }}>
            Bestäm hur AI pratar <em style={{ color: "#fbbf24" }}>med dina elever</em>.
          </h1>
          <p style={{ color: "rgba(255,255,255,0.7)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, lineHeight: 1.55, maxWidth: 720, margin: 0 }}>
            Här styr du Maria HR, Mats Arbetsförmedlingen, offert-pitch-bedömaren och 13 andra AI-anrop.
            Alla ändringar gäller bara dina elever. Återställ när du vill — default-prompten är alltid kvar.
          </p>
          {error && (
            <div style={errorBoxStyle}>{error}</div>
          )}
          <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <Link to="/teacher/v2" style={{ color: "#c7d2fe", textDecoration: "none", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              ← Tillbaka
            </Link>
            <span style={{ flex: 1 }} />
            <button onClick={exportJson} style={btnGhost}>
              Exportera JSON
            </button>
            <button onClick={triggerImport} style={btnGhost}>
              Importera JSON
            </button>
          </div>
        </header>

        {(Object.keys(grouped) as PromptSpec["category"][]).map((cat) => (
          <section key={cat} style={{ marginBottom: 36 }}>
            <div style={categoryHeadStyle}>
              <div style={categoryEyeStyle}>● {CATEGORY_LABELS[cat]}</div>
              <p style={{ color: "rgba(255,255,255,0.6)", fontSize: 13, margin: "4px 0 0", fontFamily: "Source Serif 4, Georgia, serif" }}>
                {CATEGORY_DESCRIPTIONS[cat]}
              </p>
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              {grouped[cat].map((sp) => (
                <PromptCard
                  key={sp.key}
                  spec={sp}
                  override={overrides[sp.key] ?? null}
                  expanded={activeKey === sp.key}
                  onToggle={() => setActiveKey(activeKey === sp.key ? null : sp.key)}
                  onLocalChange={(partial) => updateLocal(sp.key, partial)}
                  onSaved={(o) => updateLocal(sp.key, o)}
                  onDeleted={() => {
                    setOverrides((prev) => {
                      const next = { ...prev };
                      delete next[sp.key];
                      return next;
                    });
                  }}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}


function PromptCard({
  spec,
  override,
  expanded,
  onToggle,
  onLocalChange,
  onSaved,
  onDeleted,
}: {
  spec: PromptSpec;
  override: PromptOverride | null;
  expanded: boolean;
  onToggle: () => void;
  onLocalChange: (partial: Partial<PromptOverride>) => void;
  onSaved: (o: PromptOverride) => void;
  onDeleted: () => void;
}) {
  const customText = override?.custom_text ?? "";
  const isActive = override?.is_active ?? true;
  const hasOverride = override !== null && customText.trim().length > 0;
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const [previewInput, setPreviewInput] = useState(spec.preview_input);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  async function save() {
    setSaveErr(null);
    setSaving(true);
    try {
      const r = await api<PromptOverride>(
        `/v2/teacher/ai-prompts/${spec.key}`,
        {
          method: "PUT",
          body: JSON.stringify({
            custom_text: customText,
            is_active: isActive,
          }),
        },
      );
      onSaved(r);
    } catch (e) {
      setSaveErr(String((e as Error).message || e));
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (!confirm("Återställ till standardprompt? Din anpassning raderas.")) return;
    try {
      await api(`/v2/teacher/ai-prompts/${spec.key}`, { method: "DELETE" });
      onDeleted();
    } catch (e) {
      setSaveErr(String((e as Error).message || e));
    }
  }

  async function runPreview() {
    setPreviewBusy(true);
    setPreviewErr(null);
    setPreviewResult(null);
    try {
      const r = await api<PreviewResult>(
        `/v2/teacher/ai-prompts/${spec.key}/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            custom_text: customText.trim() || undefined,
            preview_input: previewInput,
          }),
        },
      );
      setPreviewResult(r);
    } catch (e) {
      setPreviewErr(String((e as Error).message || e));
    } finally {
      setPreviewBusy(false);
    }
  }

  const cardBg = hasOverride && isActive
    ? "linear-gradient(135deg, rgba(99,102,241,0.10), rgba(15,21,37,0.5))"
    : "rgba(15,21,37,0.5)";
  const borderColor = hasOverride && isActive
    ? "rgba(99,102,241,0.35)"
    : "rgba(255,255,255,0.08)";

  return (
    <div
      style={{
        background: cardBg,
        border: `1px solid ${borderColor}`,
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      <button
        onClick={onToggle}
        style={{
          width: "100%",
          padding: "16px 20px",
          background: "transparent",
          border: "none",
          color: "inherit",
          textAlign: "left",
          cursor: "pointer",
          display: "flex",
          gap: 16,
          alignItems: "center",
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
            {spec.label}
          </div>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "rgba(255,255,255,0.45)", letterSpacing: 1, marginTop: 4, textTransform: "uppercase" }}>
            {spec.used_at} · {spec.model}
          </div>
        </div>
        {hasOverride && isActive && (
          <span style={{ ...pillStyle, background: "rgba(99,102,241,0.25)", color: "#c7d2fe" }}>
            ANPASSAD
          </span>
        )}
        {hasOverride && !isActive && (
          <span style={{ ...pillStyle, background: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.4)" }}>
            AV (sparad)
          </span>
        )}
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: "#c7d2fe" }}>
          {expanded ? "−" : "+"}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: "0 20px 20px 20px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          <p style={{ color: "rgba(255,255,255,0.75)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.55, margin: "16px 0" }}>
            {spec.description}
          </p>

          {spec.variables.length > 0 && (
            <div style={varHintStyle}>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "#c7d2fe", letterSpacing: 1.2, marginBottom: 4 }}>
                VARIABLER DU MÅSTE INKLUDERA
              </div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "rgba(255,255,255,0.85)" }}>
                {spec.variables.join("  ·  ")}
              </div>
              <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, marginTop: 6, fontFamily: "Source Serif 4, Georgia, serif" }}>
                Skriv exakt så här i din anpassning · annars går prompten inte att spara.
              </div>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            {/* Default-prompt (skrivskyddad) */}
            <div>
              <div style={blockEyeStyle}>STANDARDPROMPT (skrivskyddad)</div>
              <textarea
                value={spec.default_text}
                readOnly
                style={{ ...textareaStyle, opacity: 0.65, minHeight: 240 }}
              />
            </div>

            {/* Lärarens custom-text */}
            <div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, justifyContent: "space-between" }}>
                <div style={{ ...blockEyeStyle, color: "#fbbf24" }}>DIN ANPASSNING (frivillig)</div>
                {spec.templates.length > 0 && (
                  <select
                    onChange={(e) => {
                      const idx = parseInt(e.target.value, 10);
                      if (idx >= 0 && idx < spec.templates.length) {
                        if (
                          customText.trim() === ""
                          || confirm("Skriv över din nuvarande anpassning?")
                        ) {
                          onLocalChange({
                            custom_text: spec.templates[idx].text,
                          });
                        }
                      }
                      e.target.value = "-1";
                    }}
                    defaultValue="-1"
                    style={selectStyle}
                  >
                    <option value="-1">Klistra in mall…</option>
                    {spec.templates.map((t, i) => (
                      <option key={i} value={i} title={t.description}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <textarea
                value={customText}
                onChange={(e) => onLocalChange({ custom_text: e.target.value })}
                placeholder={
                  spec.variables.length > 0
                    ? `Skriv din variant här. Glöm inte: ${spec.variables.join(", ")}`
                    : "Skriv din variant här. Lämnar du tomt används standard."
                }
                style={{ ...textareaStyle, minHeight: 240, borderColor: hasOverride ? "rgba(99,102,241,0.45)" : undefined }}
              />
              <div style={{ display: "flex", gap: 12, marginTop: 8, alignItems: "center", fontSize: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, color: "rgba(255,255,255,0.7)", fontFamily: "Source Serif 4, Georgia, serif", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(e) => onLocalChange({ is_active: e.target.checked })}
                  />
                  Aktiv (av = använd standard utan att radera din text)
                </label>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
            <button onClick={save} disabled={saving} style={btnPrimary}>
              {saving ? "Sparar…" : "Spara"}
            </button>
            <button onClick={runPreview} disabled={previewBusy} style={btnSecondary}>
              {previewBusy ? "Kör test…" : "Förhandsgranska →"}
            </button>
            {hasOverride && (
              <button onClick={reset} style={btnGhost}>
                Återställ till standard
              </button>
            )}
            {override?.updated_at && (
              <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, fontFamily: "JetBrains Mono, monospace", alignSelf: "center", marginLeft: "auto" }}>
                Senast sparat {new Date(override.updated_at).toLocaleString("sv-SE")}
              </span>
            )}
          </div>
          {saveErr && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{saveErr}</div>}

          {/* Förhandsgranskning */}
          {(previewResult || previewErr || previewBusy) && (
            <div style={{ marginTop: 22, padding: 16, background: "rgba(0,0,0,0.25)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.08)" }}>
              <div style={blockEyeStyle}>FÖRHANDSGRANSKNING</div>
              <div style={{ marginTop: 8 }}>
                <div style={{ ...blockEyeStyle, marginBottom: 4, fontSize: 9 }}>EXEMPEL-INPUT</div>
                <textarea
                  value={previewInput}
                  onChange={(e) => setPreviewInput(e.target.value)}
                  style={{ ...textareaStyle, minHeight: 80, fontSize: 12, opacity: 0.85 }}
                />
              </div>
              {previewBusy && <div style={{ color: "#c7d2fe", marginTop: 12, fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic" }}>Skickar till Claude…</div>}
              {previewErr && <div style={{ ...errorBoxStyle, marginTop: 10 }}>{previewErr}</div>}
              {previewResult && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ ...blockEyeStyle, fontSize: 9, color: "#6ee7b7" }}>AI-SVAR ({previewResult.input_tokens} in / {previewResult.output_tokens} ut tokens)</div>
                  <div style={{ marginTop: 6, padding: 14, background: "rgba(110,231,183,0.05)", borderLeft: "2px solid #6ee7b7", borderRadius: 4, color: "#fff", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                    {previewResult.output_text}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// === Styles ===
const shellStyle: React.CSSProperties = {
  maxWidth: 1100,
  margin: "0 auto",
  padding: "32px 24px 80px",
};

const eyebrowStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.6,
  color: "#fbbf24",
};

const categoryHeadStyle: React.CSSProperties = {
  marginBottom: 12,
  paddingBottom: 8,
  borderBottom: "1px solid rgba(255,255,255,0.08)",
};

const categoryEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "#c7d2fe",
};

const blockEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 9.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "rgba(255,255,255,0.55)",
  textTransform: "uppercase",
  marginBottom: 6,
};

const pillStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  padding: "4px 10px",
  borderRadius: 100,
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  minHeight: 180,
  background: "rgba(0,0,0,0.3)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 6,
  padding: 12,
  color: "rgba(255,255,255,0.92)",
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 12.5,
  lineHeight: 1.55,
  resize: "vertical" as const,
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24",
  border: "none",
  color: "#422006",
  padding: "9px 18px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  background: "rgba(99,102,241,0.18)",
  border: "1px solid rgba(99,102,241,0.45)",
  color: "#c7d2fe",
  padding: "9px 18px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.65)",
  padding: "9px 18px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const varHintStyle: React.CSSProperties = {
  marginTop: 12,
  padding: "12px 14px",
  background: "rgba(99,102,241,0.06)",
  border: "1px solid rgba(99,102,241,0.25)",
  borderRadius: 6,
};

const selectStyle: React.CSSProperties = {
  background: "rgba(99,102,241,0.10)",
  border: "1px solid rgba(99,102,241,0.35)",
  color: "#c7d2fe",
  padding: "4px 8px",
  borderRadius: 4,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 0.8,
  textTransform: "uppercase" as const,
  cursor: "pointer",
};

const errorBoxStyle: React.CSSProperties = {
  marginTop: 10,
  padding: 10,
  background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)",
  borderRadius: 6,
  color: "#fda594",
  fontFamily: "Source Serif 4, Georgia, serif",
  fontSize: 13,
};
