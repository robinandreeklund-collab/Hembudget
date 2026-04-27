import { useEffect, useRef, useState } from "react";
import {
  BookOpenCheck,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Inbox,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import { api, getApiBase, getToken } from "@/api/client";
import { AssignmentList } from "@/components/AssignmentList";
import { InfoBanner } from "@/components/Tooltip";

type Artifact = {
  id: number;
  kind: string;
  title: string;
  filename: string;
  sort_order: number;
  imported_at: string | null;
  meta: Record<string, unknown> | null;
};

type BatchSummary = {
  id: number;
  year_month: string;
  artifact_count: number;
  imported_count: number;
};

type BatchDetail = BatchSummary & { artifacts: Artifact[] };

const KIND_LABEL: Record<string, string> = {
  lonespec: "Lönespec",
  kontoutdrag: "Kontoutdrag",
  lan_besked: "Lånebesked",
  kreditkort_faktura: "Kreditkortsfaktura",
};

export default function MyBatches() {
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [active, setActive] = useState<BatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [previewArt, setPreviewArt] = useState<Artifact | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Cleanup blob-URLs när komponenten unmountar / preview byts ut.
  const lastBlobRef = useRef<string | null>(null);

  async function openPreview(art: Artifact) {
    if (!active) return;
    setPreviewArt(art);
    setPreviewLoading(true);
    setErr(null);
    try {
      const url =
        `${getApiBase()}/student/batches/${active.id}/artifacts/${art.id}/download`;
      const tok = getToken();
      const res = await fetch(url, {
        headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
      });
      if (!res.ok) throw new Error(`Hämtning misslyckades (${res.status})`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      if (lastBlobRef.current) URL.revokeObjectURL(lastBlobRef.current);
      lastBlobRef.current = blobUrl;
      setPreviewUrl(blobUrl);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setPreviewArt(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  function closePreview() {
    setPreviewArt(null);
    setPreviewUrl(null);
    if (lastBlobRef.current) {
      URL.revokeObjectURL(lastBlobRef.current);
      lastBlobRef.current = null;
    }
  }

  useEffect(() => {
    return () => {
      if (lastBlobRef.current) URL.revokeObjectURL(lastBlobRef.current);
    };
  }, []);

  async function reload() {
    setLoading(true);
    try {
      const list = await api<BatchSummary[]>(
        "/student/batches?visible_in=my_batches",
      );
      setBatches(list);
      if (list.length > 0 && !active) {
        await openBatch(list[0].id);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function openBatch(id: number) {
    const detail = await api<BatchDetail>(
      `/student/batches/${id}?visible_in=my_batches`,
    );
    setActive(detail);
  }

  useEffect(() => {
    reload();
  }, []);

  async function downloadArtifact(art: Artifact) {
    if (!active) return;
    const url =
      `${getApiBase()}/student/batches/${active.id}/artifacts/${art.id}/download`;
    const tok = getToken();
    const res = await fetch(url, {
      headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
    });
    if (!res.ok) {
      setErr(`Nedladdning misslyckades (${res.status})`);
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

  async function importArtifact(art: Artifact) {
    if (!active) return;
    setImporting(art.id);
    try {
      await api(
        `/student/batches/${active.id}/artifacts/${art.id}/import`,
        { method: "POST" },
      );
      await openBatch(active.id);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(null);
    }
  }

  async function importAll() {
    if (!active) return;
    setImporting(-1);
    try {
      await api(`/student/batches/${active.id}/import-all`, { method: "POST" });
      await openBatch(active.id);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(null);
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Inbox className="w-6 h-6 text-brand-600" />
        <h1 className="serif text-3xl leading-tight">Dina dokument</h1>
      </div>
      <p className="text-sm text-slate-700">
        Här samlas dokumenten som din lärare skickat ut. Förhandsgranska dem
        direkt, och importera dem sedan i appen så syns de i din ekonomi.
      </p>
      <InfoBanner title="Så här gör du">
        <ol className="list-decimal ml-5 space-y-1">
          <li>Välj vilken månad du vill jobba med från månadslistan.</li>
          <li>
            Klicka på <strong>ögat</strong> för att förhandsgranska PDF:en
            direkt här i sidan — precis som du skulle gjort med en riktig
            faktura eller lönespec.
          </li>
          <li>
            Klicka på pilen <strong>⬆</strong> för att importera dokumentet i
            appen — då hamnar siffrorna på rätt plats i din ekonomi.
          </li>
          <li>
            Tips: Klicka <strong>Importera alla</strong> om du vill göra det i
            ett svep.
          </li>
        </ol>
      </InfoBanner>

      {/* Uppdrag */}
      <div className="bg-white border rounded-lg p-4">
        <h2 className="font-semibold flex items-center gap-2 mb-2">
          <BookOpenCheck className="w-5 h-5 text-brand-600" />
          Dina uppdrag
        </h2>
        <AssignmentList />
      </div>

      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
          {err}
        </div>
      )}

      {loading ? (
        <div>Laddar…</div>
      ) : batches.length === 0 ? (
        <div className="bg-amber-50 border border-amber-200 rounded p-4 text-amber-800">
          Inga dokument än. Vänta tills din lärare skickat ut månadens
          underlag.
        </div>
      ) : (
        <div className={`grid gap-4 ${
          previewArt
            ? "grid-cols-1 md:grid-cols-[180px_1fr] xl:grid-cols-[180px_minmax(0,1fr)_minmax(0,1fr)]"
            : "grid-cols-1 md:grid-cols-[200px_1fr]"
        }`}>
          {/* Sidolista över månader */}
          <div className="space-y-1">
            {batches.map((b) => (
              <button
                key={b.id}
                onClick={() => openBatch(b.id)}
                className={`w-full text-left rounded-lg p-3 ${
                  active?.id === b.id
                    ? "bg-brand-100 text-brand-900"
                    : "hover:bg-slate-100"
                }`}
              >
                <div className="font-medium">{b.year_month}</div>
                <div className="text-xs text-slate-500">
                  {b.imported_count}/{b.artifact_count} importerade
                </div>
              </button>
            ))}
          </div>

          {/* Aktiv batch */}
          {active && (
            <div className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 min-w-0">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-lg">
                  {active.year_month} – {active.artifact_count} dokument
                </h2>
                <button
                  onClick={importAll}
                  disabled={importing !== null}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white rounded px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  {importing === -1 ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4" />
                  )}
                  Importera alla
                </button>
              </div>

              <ul className="divide-y divide-slate-200">
                {active.artifacts.map((a) => {
                  const isPreviewing = previewArt?.id === a.id;
                  return (
                    <li
                      key={a.id}
                      className={`py-3 flex items-center gap-3 ${
                        isPreviewing ? "bg-brand-50 -mx-2 px-2 rounded" : ""
                      }`}
                    >
                      <FileText className="w-5 h-5 text-slate-400 flex-shrink-0" />
                      <button
                        onClick={() => openPreview(a)}
                        className="flex-1 text-left min-w-0 hover:text-brand-700"
                      >
                        <div className="font-medium text-sm truncate">
                          {KIND_LABEL[a.kind] ?? a.kind} – {a.title}
                        </div>
                        <div className="text-xs text-slate-500 truncate">
                          {a.filename}
                        </div>
                      </button>
                      {a.imported_at ? (
                        <span className="text-xs text-emerald-700 flex items-center gap-1 mr-2 hidden sm:inline-flex">
                          <CheckCircle2 className="w-4 h-4" /> Importerat
                        </span>
                      ) : null}
                      <button
                        onClick={() => openPreview(a)}
                        title="Förhandsgranska"
                        className={`p-2 rounded ${
                          isPreviewing
                            ? "bg-brand-100 text-brand-700"
                            : "hover:bg-slate-100 text-slate-600"
                        }`}
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => downloadArtifact(a)}
                        title="Ladda ner PDF"
                        className="p-2 hover:bg-slate-100 rounded text-slate-600"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => importArtifact(a)}
                        disabled={importing !== null}
                        title="Importera i appen"
                        className={`p-2 rounded text-emerald-600 ${
                          a.imported_at
                            ? "hover:bg-emerald-50"
                            : "hover:bg-emerald-100"
                        } disabled:opacity-50`}
                      >
                        {importing === a.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Upload className="w-4 h-4" />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Preview-pane (xl: side-by-side, mindre skärmar: modal) */}
          {previewArt && (
            <>
              {/* Desktop split-view */}
              <div className="hidden xl:flex bg-white rounded-lg border border-slate-200 flex-col min-w-0 sticky top-4 h-[calc(100vh-2rem)]">
                <div className="flex items-center justify-between p-3 border-b">
                  <div className="min-w-0">
                    <div className="font-medium text-sm truncate">
                      {previewArt.title}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {previewArt.filename}
                    </div>
                  </div>
                  <button
                    onClick={closePreview}
                    className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
                    aria-label="Stäng förhandsgranskning"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex-1 bg-slate-100">
                  {previewLoading ? (
                    <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      Laddar…
                    </div>
                  ) : previewUrl ? (
                    <iframe
                      title={previewArt.filename}
                      src={previewUrl}
                      className="w-full h-full"
                    />
                  ) : null}
                </div>
              </div>

              {/* Mobile/tablet modal */}
              <div className="xl:hidden fixed inset-0 z-50 flex flex-col bg-white">
                <div className="flex items-center justify-between p-3 border-b">
                  <div className="min-w-0">
                    <div className="font-medium text-sm truncate">
                      {previewArt.title}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {previewArt.filename}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => downloadArtifact(previewArt)}
                      title="Ladda ner"
                      className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={closePreview}
                      className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
                      aria-label="Stäng"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="flex-1 bg-slate-100">
                  {previewLoading ? (
                    <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      Laddar…
                    </div>
                  ) : previewUrl ? (
                    <iframe
                      title={previewArt.filename}
                      src={previewUrl}
                      className="w-full h-full"
                    />
                  ) : null}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
