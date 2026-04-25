import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  FileText,
  Inbox,
} from "lucide-react";
import { api, getApiBase, getToken } from "@/api/client";

type Artifact = {
  id: number;
  kind: string;
  title: string;
  filename: string;
  imported_at: string | null;
};

type BatchSummary = {
  id: number;
  year_month: string;
  artifact_count: number;
  imported_count: number;
};

type Row = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  family_name: string | null;
  batch: BatchSummary | null;
};

const KIND_LABEL: Record<string, string> = {
  lonespec: "Lönespec",
  kontoutdrag: "Kontoutdrag",
  lan_besked: "Lånebesked",
  kreditkort_faktura: "Kreditkort",
};

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function AllBatches() {
  const [months, setMonths] = useState<string[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<string>(thisMonth());
  const [rows, setRows] = useState<Row[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [artifactCache, setArtifactCache] = useState<
    Record<number, Artifact[]>
  >({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function reloadMonths() {
    try {
      const ms = await api<string[]>("/teacher/batches/months");
      setMonths(ms);
      if (ms.length > 0 && !ms.includes(selectedMonth)) {
        setSelectedMonth(ms[0]);
      }
    } catch (e) {
      /* ignore */
    }
  }

  async function reloadRows(ym: string) {
    setLoading(true);
    try {
      const list = await api<Row[]>(`/teacher/batches/by-month/${ym}`);
      setRows(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reloadMonths();
  }, []);
  useEffect(() => {
    reloadRows(selectedMonth);
    setExpanded(new Set());
    setArtifactCache({});
  }, [selectedMonth]);

  async function toggleRow(row: Row) {
    const next = new Set(expanded);
    if (next.has(row.student_id)) {
      next.delete(row.student_id);
      setExpanded(next);
      return;
    }
    next.add(row.student_id);
    setExpanded(next);
    if (row.batch && !artifactCache[row.batch.id]) {
      try {
        const detail = await api<{ artifacts: Artifact[] }>(
          `/student/batches/${row.batch.id}`,
        );
        setArtifactCache((c) => ({ ...c, [row.batch!.id]: detail.artifacts }));
      } catch {
        /* ignore */
      }
    }
  }

  async function downloadArtifact(batchId: number, art: Artifact) {
    const tok = getToken();
    const res = await fetch(
      `${getApiBase()}/student/batches/${batchId}/artifacts/${art.id}/download`,
      { headers: tok ? { Authorization: `Bearer ${tok}` } : undefined },
    );
    if (!res.ok) {
      setErr(`Kunde inte hämta PDF (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = art.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  const total = rows.length;
  const withBatch = rows.filter((r) => r.batch).length;
  const fullyImported = rows.filter(
    (r) => r.batch && r.batch.imported_count === r.batch.artifact_count,
  ).length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <Link
        to="/teacher"
        className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Lärarpanel
      </Link>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Inbox className="w-6 h-6 text-brand-600" />
          <h1 className="text-2xl font-semibold">Månadens PDF:er – alla elever</h1>
        </div>
        <select
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(e.target.value)}
          className="border rounded px-3 py-1.5"
        >
          {months.length === 0 ? (
            <option value={selectedMonth}>{selectedMonth}</option>
          ) : (
            months.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))
          )}
        </select>
      </div>

      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
          {err}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 text-sm">
        <Card label="Elever" value={total} />
        <Card label="Har batch" value={`${withBatch}/${total}`} />
        <Card
          label="Fullständigt importerat"
          value={`${fullyImported}/${total}`}
          color="emerald"
        />
      </div>

      {loading ? (
        <div className="text-slate-500">Laddar…</div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left">
              <tr>
                <th className="p-3">Elev</th>
                <th className="p-3">Klass / Familj</th>
                <th className="p-3">Batch</th>
                <th className="p-3">Import</th>
                <th className="p-3 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <RowItem
                  key={r.student_id}
                  row={r}
                  open={expanded.has(r.student_id)}
                  artifacts={
                    r.batch ? artifactCache[r.batch.id] ?? null : null
                  }
                  onToggle={() => toggleRow(r)}
                  onDownload={(art) => downloadArtifact(r.batch!.id, art)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RowItem({
  row, open, artifacts, onToggle, onDownload,
}: {
  row: Row;
  open: boolean;
  artifacts: Artifact[] | null;
  onToggle: () => void;
  onDownload: (a: Artifact) => void;
}) {
  const b = row.batch;
  return (
    <>
      <tr className="border-t hover:bg-slate-50 cursor-pointer" onClick={onToggle}>
        <td className="p-3 font-medium">{row.display_name}</td>
        <td className="p-3 text-slate-600">
          {row.class_label || "—"}
          {row.family_name && (
            <span className="ml-2 text-xs text-amber-700">🏠 {row.family_name}</span>
          )}
        </td>
        <td className="p-3">
          {b ? `${b.artifact_count} dokument` : (
            <span className="text-slate-400">Ingen batch</span>
          )}
        </td>
        <td className="p-3">
          {b ? (
            <span
              className={
                b.imported_count === b.artifact_count
                  ? "text-emerald-700"
                  : "text-amber-700"
              }
            >
              {b.imported_count}/{b.artifact_count}
            </span>
          ) : "—"}
        </td>
        <td className="p-3 text-slate-400">{open ? "▾" : "▸"}</td>
      </tr>
      {open && b && (
        <tr>
          <td colSpan={5} className="bg-slate-50 p-0">
            <div className="px-6 py-3">
              {artifacts === null ? (
                <div className="text-xs text-slate-500">Laddar…</div>
              ) : artifacts.length === 0 ? (
                <div className="text-xs text-slate-500">Inga artefakter</div>
              ) : (
                <ul className="space-y-1">
                  {artifacts.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 text-sm">
                      <FileText className="w-4 h-4 text-slate-400" />
                      <span className="flex-1">
                        {KIND_LABEL[a.kind] ?? a.kind} – {a.title}
                      </span>
                      {a.imported_at && (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      )}
                      <button
                        onClick={() => onDownload(a)}
                        className="p-1 text-slate-500 hover:text-brand-600"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Card({
  label, value, color = "slate",
}: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-white border rounded-lg p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-xl font-semibold text-${color}-700`}>{value}</div>
    </div>
  );
}
