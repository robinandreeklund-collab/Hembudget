import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, GraduationCap } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

export default function StudentLogin() {
  const { studentLogin } = useAuth();
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await studentLogin(code.toUpperCase().trim());
      window.location.reload();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-emerald-50 grid place-items-center p-6">
      <div className="w-full max-w-md">
        <Link
          to="/"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1 mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka
        </Link>
        <form
          onSubmit={handle}
          className="bg-white rounded-2xl shadow-xl p-8 space-y-5 border border-slate-200"
        >
          <div className="flex items-center gap-2 text-brand-600">
            <GraduationCap className="w-6 h-6" />
            <h1 className="text-xl font-semibold">Elevinloggning</h1>
          </div>
          <p className="text-sm text-slate-600">
            Ange din 6-teckens kod som din lärare har gett dig.
          </p>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABC123"
            autoFocus
            maxLength={6}
            className="w-full px-3 py-4 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none font-mono tracking-[0.4em] text-center text-2xl"
          />
          {err && <div className="text-sm text-rose-600">{err}</div>}
          <button
            disabled={busy || code.length < 4}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-3 font-medium disabled:opacity-50 text-lg"
          >
            {busy ? "Loggar in…" : "Logga in"}
          </button>
          <div className="text-center text-sm text-slate-500 pt-2 border-t">
            Är du lärare eller skolledare?{" "}
            <Link to="/login/teacher" className="text-brand-600 hover:underline">
              Lärarinloggning
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
