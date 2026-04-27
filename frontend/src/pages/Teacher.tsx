import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getApiBase, getToken } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { AssignmentSummary } from "@/components/AssignmentList";
import { FamilyManager, Family } from "@/components/FamilyManager";
import {
  AlertTriangle,
  Eye,
  Loader2,
  Pencil,
  Play,
  Plus,
  QrCode,
  RotateCcw,
  Trash2,
  Users,
  Wrench,
  X,
} from "lucide-react";

type Student = {
  id: number;
  display_name: string;
  class_label: string | null;
  login_code: string;
  active: boolean;
  family_id: number | null;
  family_name: string | null;
  profession: string | null;
  personality: string | null;
  last_login_at: string | null;
  created_at: string;
  months_generated: string[];
  has_profile: boolean;
};

type PulseRow = {
  student_id: number;
  flag: "good" | "watch" | "alert" | "no_data";
  month_balance: number;
  savings_rate_pct: number;
};

type GenerateRow = {
  student_id: number;
  display_name: string;
  year_month: string;
  status: string;
  seed?: number;
  stats?: Record<string, number>;
  error?: string;
};

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Teacher() {
  const { impersonate, teacherMeta } = useAuth();
  const isFamily = teacherMeta?.is_family_account === true;
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showFamilies, setShowFamilies] = useState(false);
  const [families, setFamilies] = useState<Family[]>([]);
  const [editStudent, setEditStudent] = useState<Student | null>(null);
  const [qrStudent, setQrStudent] = useState<Student | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);

  useEffect(() => {
    api<{ is_super_admin: boolean }>("/admin/ai/me")
      .then((r) => setIsSuperAdmin(Boolean(r.is_super_admin)))
      .catch(() => setIsSuperAdmin(false));
  }, []);

  async function openQr(s: Student) {
    setQrStudent(s);
    setQrUrl(null);
    try {
      const tok = getToken();
      const res = await fetch(
        `${getApiBase()}/teacher/students/${s.id}/qr`,
        { headers: tok ? { Authorization: `Bearer ${tok}` } : undefined },
      );
      if (!res.ok) throw new Error("QR-kod misslyckades");
      const blob = await res.blob();
      setQrUrl(URL.createObjectURL(blob));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }
  const [newName, setNewName] = useState("");
  const [newClass, setNewClass] = useState("");
  const [newFamilyId, setNewFamilyId] = useState<number | "">("");
  const [ym, setYm] = useState(thisMonth());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lastRun, setLastRun] = useState<GenerateRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pulse, setPulse] = useState<Record<number, PulseRow>>({});

  async function reload() {
    setLoading(true);
    try {
      const [list, fams] = await Promise.all([
        api<Student[]>("/teacher/students"),
        api<Family[]>("/teacher/families"),
      ]);
      setStudents(list);
      setFamilies(fams);
      // Ekonomi-puls — körs separat och fail-soft så listan visas
      // även om pulse-endpointen ger 500.
      api<PulseRow[]>("/teacher/students/pulse")
        .then((rows) => {
          const m: Record<number, PulseRow> = {};
          for (const r of rows) m[r.student_id] = r;
          setPulse(m);
        })
        .catch(() => setPulse({}));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function createStudent() {
    if (!newName.trim()) return;
    try {
      await api("/teacher/students", {
        method: "POST",
        body: JSON.stringify({
          display_name: newName.trim(),
          class_label: newClass.trim() || null,
          family_id: newFamilyId === "" ? null : newFamilyId,
        }),
      });
      setNewName("");
      setNewClass("");
      setNewFamilyId("");
      setShowCreate(false);
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function saveEdit() {
    if (!editStudent) return;
    try {
      await api(`/teacher/students/${editStudent.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: editStudent.display_name,
          class_label: editStudent.class_label || null,
          family_id: editStudent.family_id,
          active: editStudent.active,
        }),
      });
      setEditStudent(null);
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }


  async function deleteStudent(id: number) {
    if (!confirm("Ta bort eleven och all data?")) return;
    await api(`/teacher/students/${id}`, { method: "DELETE" });
    reload();
  }

  async function repairProfile(id: number) {
    try {
      await api(`/teacher/students/${id}/repair-profile`, { method: "POST" });
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function resetStudent(id: number) {
    if (!confirm("Nollställ all data för eleven? (behåller själva kontot)")) return;
    await api(`/teacher/students/${id}/reset`, { method: "POST" });
    reload();
  }

  function toggleSelect(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  function selectAll() {
    if (selected.size === students.length) setSelected(new Set());
    else setSelected(new Set(students.map((s) => s.id)));
  }

  async function runGenerate() {
    setGenerating(true);
    setErr(null);
    setLastRun(null);
    try {
      const body = {
        year_month: ym,
        student_ids: selected.size > 0 ? [...selected] : null,
        overwrite,
      };
      // Använder /teacher/batches (PDF-utskick) istället för det gamla
      // direkt-data-flödet — PDF:erna hamnar i /student/batches och
      // eleven importerar själv.
      const res = await api<{
        student_id: number; display_name: string; year_month: string;
        status: string; batch_id?: number; artifact_count?: number;
        error?: string;
      }[]>("/teacher/batches", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setLastRun(res.map((r) => ({
        student_id: r.student_id,
        display_name: r.display_name,
        year_month: r.year_month,
        status: r.status,
        stats: r.artifact_count
          ? { artifacts_created: r.artifact_count }
          : undefined,
      })));
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  }

  function viewAs(id: number) {
    impersonate(id);
    window.location.href = "/dashboard";
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="eyebrow mb-1">
            {isFamily ? "Familjepanel" : "Lärarpanel"}
          </div>
          <h1 className="serif text-2xl md:text-4xl leading-tight">
            {isFamily ? "Dina barn." : "Din klass."}
          </h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link
            to="/teacher/modules"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            🎓 Kursmoduler
          </Link>
          <Link
            to="/teacher/reflections"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            ✍️ Reflektioner
          </Link>
          <Link
            to="/teacher/rubrics"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            📋 Rubric-mallar
          </Link>
          <Link
            to="/teacher/time-on-task"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            ⏱ Time on task
          </Link>
          <button
            onClick={async () => {
              const { getApiBase, getToken } = await import("@/api/client");
              const res = await fetch(
                `${getApiBase()}/teacher/portfolio-bundle.zip`,
                {
                  headers: getToken()
                    ? { Authorization: `Bearer ${getToken()}` }
                    : undefined,
                },
              );
              if (!res.ok) {
                alert("Kunde inte skapa ZIP");
                return;
              }
              const blob = await res.blob();
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "klass_portfolio.zip";
              a.click();
              URL.revokeObjectURL(a.href);
            }}
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            📦 Klass-portfolio (ZIP)
          </button>
          <Link
            to="/docs"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            📖 Guide
          </Link>
          <Link
            to="/messages"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            💬 Meddelanden
          </Link>
          <Link
            to="/teacher/matrix"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            📊 Klassöversikt
          </Link>
          <Link
            to="/teacher/all-batches"
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            📄 Alla PDF:er
          </Link>
          {isSuperAdmin && (
            <Link
              to="/teacher/admin-ai"
              className="border-[1.5px] border-ink bg-paper hover:bg-[#fffef5] rounded-md px-4 py-2 flex items-center gap-2 text-ink"
              title="Super-admin · AI, lärar-toggel, SMTP/Gmail, API-nyckel"
            >
              ⚙ Inställningar
            </Link>
          )}
          <button
            onClick={() => setShowFamilies(!showFamilies)}
            className="btn-outline rounded-md px-4 py-2 text-sm"
          >
            <Users className="w-4 h-4" /> Familjer
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="btn-dark rounded-md px-4 py-2 text-sm flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> {isFamily ? "Nytt barn" : "Ny elev"}
          </button>
        </div>
      </div>

      {isSuperAdmin && <SmtpStatusCallout />}

      {showFamilies && <FamilyManager onChange={reload} />}

      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
          {err}
        </div>
      )}

      {/* Generator-panel */}
      <div className="bg-white border-[1.5px] border-rule p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Play className="w-5 h-5 text-emerald-600" />
          <h2 className="font-semibold">Generera exempeldata för månad</h2>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <div className="text-slate-600 mb-1">Månad</div>
            <input
              type="month"
              value={ym}
              onChange={(e) => setYm(e.target.value)}
              className="border rounded px-2 py-1.5"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
            />
            Skriv över befintlig månadsdata
          </label>
          <div className="text-sm text-slate-600">
            {selected.size === 0
              ? "Genererar för alla elever"
              : `Genererar för ${selected.size} valda`}
          </div>
          <button
            onClick={runGenerate}
            disabled={generating || students.length === 0}
            className="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-2 flex items-center gap-2 disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Generera
          </button>
        </div>

        {lastRun && (
          <div className="text-sm border-t pt-3">
            <div className="font-medium mb-2">Resultat:</div>
            <ul className="space-y-1">
              {lastRun.map((r) => (
                <li key={r.student_id} className="flex gap-3 items-start">
                  <span className="font-medium w-40 shrink-0">{r.display_name}</span>
                  <span
                    className={`px-2 rounded text-xs shrink-0 ${
                      r.status === "created"
                        ? "bg-emerald-100 text-emerald-700"
                        : r.status === "overwritten"
                        ? "bg-amber-100 text-amber-700"
                        : r.status === "skipped"
                        ? "bg-slate-100 text-slate-600"
                        : "bg-rose-100 text-rose-700"
                    }`}
                  >
                    {r.status}
                  </span>
                  <span className="text-slate-600 text-xs break-all font-mono">
                    {r.stats
                      ? Object.entries(r.stats)
                          .map(([k, v]) => `${k.replace("_created", "")}:${v}`)
                          .join(" · ")
                      : r.error || "(inget felmeddelande från servern — kolla Cloud Run-loggar)"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Elevlista — overflow-x-auto så bred tabell går att scrolla
          horisontellt på små skärmar istället för att bryta layout. */}
      <div className="bg-white rounded-xl shadow-sm border overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="p-3 w-8">
                <input
                  type="checkbox"
                  checked={
                    selected.size === students.length && students.length > 0
                  }
                  onChange={selectAll}
                />
              </th>
              <th className="p-3">Namn</th>
              <th className="p-3">Klass</th>
              <th className="p-3">Kod</th>
              <th className="p-3">Genererade månader</th>
              <th className="p-3">Senast inloggad</th>
              <th className="p-3 w-40 text-right">Åtgärder</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  Laddar…
                </td>
              </tr>
            ) : students.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  {isFamily
                    ? "Inga barn ännu. Skapa det första med \"Nytt barn\"."
                    : "Inga elever ännu. Skapa din första med \"Ny elev\"."}
                </td>
              </tr>
            ) : (
              students.map((s) => (
                <tr key={s.id} className="border-t hover:bg-slate-50">
                  <td className="p-3">
                    <input
                      type="checkbox"
                      checked={selected.has(s.id)}
                      onChange={() => toggleSelect(s.id)}
                    />
                  </td>
                  <td className="p-3 font-medium">
                    <div className="flex items-center gap-2">
                      <PulseDot pulse={pulse[s.id]} />
                      <Link
                        to={`/teacher/students/${s.id}`}
                        className="text-brand-700 hover:underline"
                      >
                        {s.display_name}
                      </Link>
                    </div>
                    {pulse[s.id] && pulse[s.id].flag !== "no_data" && (
                      <div className="mt-1 text-[11px] text-slate-500 ml-5">
                        Netto denna mån:{" "}
                        <span className={
                          pulse[s.id].month_balance >= 0
                            ? "text-emerald-700 font-medium"
                            : "text-rose-700 font-medium"
                        }>
                          {pulse[s.id].month_balance >= 0 ? "+" : ""}
                          {pulse[s.id].month_balance.toLocaleString("sv-SE")} kr
                        </span>
                        {" · sparkvot "}
                        {pulse[s.id].savings_rate_pct.toFixed(0)} %
                      </div>
                    )}
                    {!s.has_profile && (
                      <div className="mt-1 inline-flex items-center gap-1 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
                        <AlertTriangle className="w-3 h-3" />
                        Saknar profil — reparera eller ta bort
                      </div>
                    )}
                    <div className="mt-1">
                      <AssignmentSummary studentId={s.id} />
                    </div>
                  </td>
                  <td className="p-3 text-slate-600">
                    {s.class_label || "—"}
                    {s.family_name && (
                      <div className="text-xs text-amber-700 mt-0.5">
                        🏠 {s.family_name}
                      </div>
                    )}
                  </td>
                  <td className="p-3">
                    <button
                      onClick={() => openQr(s)}
                      className="font-mono text-brand-600 bg-brand-50 hover:bg-paper px-2 py-0.5 rounded inline-flex items-center gap-1"
                      title="Visa QR-kod"
                    >
                      {s.login_code}
                      <QrCode className="w-3 h-3" />
                    </button>
                  </td>
                  <td className="p-3 text-xs">
                    {s.months_generated.length === 0
                      ? "—"
                      : s.months_generated.join(", ")}
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {s.last_login_at
                      ? new Date(s.last_login_at).toLocaleDateString("sv-SE")
                      : "Aldrig"}
                  </td>
                  <td className="p-3 text-right space-x-1">
                    {!s.has_profile && (
                      <button
                        onClick={() => repairProfile(s.id)}
                        title="Reparera saknad profil"
                        className="p-1.5 hover:bg-amber-100 rounded text-amber-700"
                      >
                        <Wrench className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={() => viewAs(s.id)}
                      title="Titta som elev"
                      className="p-1.5 hover:bg-paper rounded text-brand-600"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setEditStudent(s)}
                      title="Redigera elev"
                      className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => resetStudent(s.id)}
                      title="Nollställ elevens data"
                      className="p-1.5 hover:bg-amber-100 rounded text-amber-600"
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteStudent(s.id)}
                      title="Ta bort elev"
                      className="p-1.5 hover:bg-rose-100 rounded text-rose-600"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div
          className="fixed inset-0 bg-black/40 grid place-items-center z-50"
          onClick={() => setShowCreate(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-96 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-semibold text-lg">
              {isFamily ? "Nytt barn" : "Ny elev"}
            </h2>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Namn"
              className="w-full px-3 py-2 border rounded-lg"
              autoFocus
            />
            <input
              type="text"
              value={newClass}
              onChange={(e) => setNewClass(e.target.value)}
              placeholder="Klass (valfritt, t.ex. 9A)"
              className="w-full px-3 py-2 border rounded-lg"
            />
            <select
              value={newFamilyId}
              onChange={(e) =>
                setNewFamilyId(e.target.value === "" ? "" : parseInt(e.target.value, 10))
              }
              className="w-full px-3 py-2 border rounded-lg"
            >
              <option value="">— Ingen familj (solo) —</option>
              {families.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name} ({f.member_count} st)
                </option>
              ))}
            </select>
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded text-slate-600 hover:bg-slate-100"
              >
                Avbryt
              </button>
              <button
                onClick={createStudent}
                className="px-4 py-2 rounded bg-brand-600 text-white hover:bg-brand-700"
              >
                Skapa
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit student modal */}
      {editStudent && (
        <div
          className="fixed inset-0 bg-black/40 grid place-items-center z-50"
          onClick={() => setEditStudent(null)}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-96 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-semibold text-lg">Redigera elev</h2>
            <label className="block">
              <span className="text-xs text-slate-600">Namn</span>
              <input
                type="text"
                value={editStudent.display_name}
                onChange={(e) =>
                  setEditStudent({ ...editStudent, display_name: e.target.value })
                }
                className="w-full px-3 py-2 border rounded-lg"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-600">Klass</span>
              <input
                type="text"
                value={editStudent.class_label || ""}
                onChange={(e) =>
                  setEditStudent({ ...editStudent, class_label: e.target.value || null })
                }
                className="w-full px-3 py-2 border rounded-lg"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-600">Familj</span>
              <select
                value={editStudent.family_id ?? ""}
                onChange={(e) =>
                  setEditStudent({
                    ...editStudent,
                    family_id: e.target.value === "" ? null : parseInt(e.target.value, 10),
                  })
                }
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">— Ingen familj (solo) —</option>
                {families.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
              <span className="text-xs text-amber-700">
                OBS: vid byte av familj börjar eleven från noll i ny scope-DB.
              </span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={editStudent.active}
                onChange={(e) =>
                  setEditStudent({ ...editStudent, active: e.target.checked })
                }
              />
              <span className="text-sm">Aktiv (kan logga in)</span>
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={() => setEditStudent(null)}
                className="px-4 py-2 rounded text-slate-600 hover:bg-slate-100"
              >
                Avbryt
              </button>
              <button
                onClick={saveEdit}
                className="px-4 py-2 rounded bg-brand-600 text-white hover:bg-brand-700"
              >
                Spara
              </button>
            </div>
          </div>
        </div>
      )}

      {/* QR modal */}
      {qrStudent && (
        <div
          className="fixed inset-0 bg-black/60 grid place-items-center z-50"
          onClick={() => {
            setQrStudent(null);
            if (qrUrl) URL.revokeObjectURL(qrUrl);
            setQrUrl(null);
          }}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-80 text-center space-y-3 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => {
                setQrStudent(null);
                if (qrUrl) URL.revokeObjectURL(qrUrl);
                setQrUrl(null);
              }}
              className="absolute top-2 right-2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 className="font-semibold text-lg">{qrStudent.display_name}</h2>
            {qrUrl ? (
              <img
                src={qrUrl}
                alt="QR-kod"
                className="mx-auto w-56 h-56 object-contain"
              />
            ) : (
              <div className="w-56 h-56 mx-auto grid place-items-center bg-slate-100 rounded">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
              </div>
            )}
            <div className="text-2xl font-mono tracking-widest text-ink">
              {qrStudent.login_code}
            </div>
            <p className="text-xs text-slate-500">
              Eleven anger denna kod på inloggningssidan, eller skannar
              QR-koden för att se den.
            </p>
            <button
              onClick={() => window.print()}
              className="text-sm nav-link"
            >
              Skriv ut
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- SMTP-status-callout (visas bara för super-admin) ----------

function SmtpStatusCallout() {
  const [cfg, setCfg] = useState<{ configured: boolean; source: string } | null>(null);
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem("hembudget_smtp_callout_dismissed") === "1",
  );

  useEffect(() => {
    api<{ configured: boolean; source: string }>("/admin/smtp/config")
      .then(setCfg)
      .catch(() => setCfg(null));
  }, []);

  if (!cfg || cfg.configured || dismissed) return null;

  return (
    <div className="border-l-[3px] border-ink bg-white p-4 flex items-start gap-4">
      <div className="text-2xl shrink-0" aria-hidden="true">✉</div>
      <div className="flex-1">
        <div className="serif text-lg leading-tight">
          E-post är inte konfigurerat än.
        </div>
        <p className="body-prose text-sm mt-1">
          Utan SMTP kan nya lärare inte verifiera sin e-post och elever
          kan inte återställa lösenord. Sätt Gmail app-password (eller
          annan SMTP) under <strong>⚙ Inställningar</strong>.
        </p>
        <div className="mt-3 flex gap-2 items-center">
          <Link
            to="/teacher/admin-ai"
            className="btn-dark rounded-md px-4 py-2 text-sm"
          >
            Öppna inställningar
          </Link>
          <button
            onClick={() => {
              sessionStorage.setItem("hembudget_smtp_callout_dismissed", "1");
              setDismissed(true);
            }}
            className="text-sm text-[#888] hover:text-ink px-3 py-2"
          >
            Påminn mig nästa session
          </button>
        </div>
      </div>
    </div>
  );
}


function PulseDot({ pulse }: { pulse?: PulseRow }) {
  if (!pulse) {
    return (
      <span
        className="w-2.5 h-2.5 rounded-full bg-slate-200 shrink-0"
        title="Beräknar..."
      />
    );
  }
  const colors: Record<string, { bg: string; title: string }> = {
    good: {
      bg: "bg-emerald-500",
      title: `Bra: sparkvot ${pulse.savings_rate_pct.toFixed(0)} % · netto +${pulse.month_balance.toLocaleString("sv-SE")} kr`,
    },
    watch: {
      bg: "bg-amber-400",
      title: `Bevakas: låg sparkvot (${pulse.savings_rate_pct.toFixed(0)} %) men netto positivt`,
    },
    alert: {
      bg: "bg-rose-500",
      title: `Behöver hjälp: utgifter > inkomster (${pulse.month_balance.toLocaleString("sv-SE")} kr)`,
    },
    no_data: {
      bg: "bg-slate-200",
      title: "Ingen data för månaden",
    },
  };
  const c = colors[pulse.flag] ?? colors.no_data;
  return (
    <span
      className={`w-2.5 h-2.5 rounded-full ${c.bg} shrink-0`}
      title={c.title}
    />
  );
}
