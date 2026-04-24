import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, MessageSquare, RefreshCcw, Send } from "lucide-react";
import { api } from "@/api/client";

type Target = {
  progress_id: number;
  module_title: string;
  step_title: string;
  step_question: string | null;
  reflection: string;
};

type Received = {
  id: number;
  body: string;
  created_at: string;
  module_title: string;
  step_title: string;
};

export default function PeerReview() {
  const [target, setTarget] = useState<Target | null>(null);
  const [received, setReceived] = useState<Received[]>([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  async function loadNext() {
    setLoading(true);
    setSubmitted(false);
    setBody("");
    try {
      const t = await api<Target | null>("/student/peer-review/next");
      setTarget(t);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadReceived() {
    try {
      setReceived(await api<Received[]>("/student/peer-review/received"));
    } catch {
      setReceived([]);
    }
  }

  useEffect(() => {
    loadNext();
    loadReceived();
  }, []);

  async function submit() {
    if (!target || body.trim().length < 10) return;
    setBusy(true);
    setErr(null);
    try {
      await api("/student/peer-review", {
        method: "POST",
        body: JSON.stringify({
          progress_id: target.progress_id,
          body: body.trim(),
        }),
      });
      setSubmitted(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <Link
        to="/dashboard"
        className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Dashboard
      </Link>
      <div className="flex items-center gap-2">
        <MessageSquare className="w-6 h-6 text-brand-600" />
        <h1 className="text-2xl font-semibold">Kamratrespons</h1>
      </div>
      <p className="text-sm text-slate-700">
        Läs en annan elevs reflektion och ge konstruktiv feedback. Allt
        är anonymt — du vet inte vem du läser, och de vet inte vem som
        gav dem feedback.
      </p>

      {err && (
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="text-slate-500">Laddar…</div>
      ) : !target ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded p-4 text-sm">
          Inga reflektioner från klasskamrater att läsa just nu. Kolla
          igen senare!
        </div>
      ) : submitted ? (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded p-4 text-sm">
          Tack för din feedback! Klasskamraten får läsa den anonymt.
          <button
            onClick={loadNext}
            className="ml-3 inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded px-3 py-1.5 text-xs"
          >
            <RefreshCcw className="w-3.5 h-3.5" /> Läs nästa
          </button>
        </div>
      ) : (
        <section className="bg-white rounded-xl border p-5 space-y-4">
          <div className="text-xs text-slate-500">
            {target.module_title} · {target.step_title}
          </div>
          {target.step_question && (
            <div className="bg-slate-50 rounded p-3 text-sm">
              <div className="font-semibold mb-1">Frågan:</div>
              {target.step_question}
            </div>
          )}
          <div className="bg-sky-50 border-l-4 border-sky-400 rounded p-3">
            <div className="text-xs text-slate-600 mb-1">Anonymt svar:</div>
            <div className="text-sm text-slate-900 whitespace-pre-wrap">
              {target.reflection}
            </div>
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium text-slate-700">
              Din feedback (minst 10 tecken):
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              placeholder="Vad var bra? Finns det något du saknar? Var snäll och konkret."
              className="w-full border rounded p-2 text-sm"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={submit}
                disabled={busy || body.trim().length < 10}
                className="bg-brand-600 hover:bg-brand-700 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1"
              >
                <Send className="w-4 h-4" />
                {busy ? "Skickar…" : "Skicka"}
              </button>
              <button
                onClick={loadNext}
                className="text-sm text-slate-600 hover:text-brand-700"
              >
                Hoppa över
              </button>
            </div>
          </div>
        </section>
      )}

      {received.length > 0 && (
        <section className="bg-white rounded-xl border p-5 space-y-3">
          <h2 className="font-semibold">
            Anonym feedback på dina reflektioner ({received.length})
          </h2>
          <ul className="space-y-3">
            {received.map((r) => (
              <li
                key={r.id}
                className="bg-amber-50 border-l-4 border-amber-400 rounded p-3 text-sm"
              >
                <div className="text-xs text-slate-600">
                  På din reflektion "{r.step_title}" ({r.module_title})
                </div>
                <div className="text-slate-900 whitespace-pre-wrap mt-1">
                  {r.body}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {new Date(r.created_at).toLocaleDateString("sv-SE")}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
