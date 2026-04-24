import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Users } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

type Mode = "login" | "bootstrap";

export default function TeacherLogin() {
  const { schoolMode, schoolStatus, teacherLogin, teacherBootstrap } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Om ingen lärare finns än, välj bootstrap automatiskt
  useEffect(() => {
    if (schoolMode && schoolStatus?.bootstrap_ready) {
      setMode("bootstrap");
    }
  }, [schoolMode, schoolStatus?.bootstrap_ready]);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      if (mode === "bootstrap") {
        if (password.length < 8)
          throw new Error("Lösenord måste vara minst 8 tecken.");
        if (password !== confirm)
          throw new Error("Lösenorden matchar inte.");
        await teacherBootstrap(secret, email, password, name || "Lärare");
      } else {
        await teacherLogin(email, password);
      }
      window.location.reload();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 grid place-items-center p-6">
      <div className="w-full max-w-md">
        <Link
          to="/"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1 mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka
        </Link>
        <form
          onSubmit={handle}
          className="bg-white rounded-2xl shadow-xl p-8 space-y-4 border border-slate-200"
        >
          <div className="flex items-center gap-2 text-brand-600">
            <Users className="w-6 h-6" />
            <h1 className="text-xl font-semibold">Lärarinloggning</h1>
          </div>

          {mode === "bootstrap" ? (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-900">
              <div className="font-semibold mb-1">Välkommen till Ekonomilabbet!</div>
              {schoolStatus?.bootstrap_requires_secret
                ? "Första gången — ange bootstrap-koden som administratören gav dig."
                : "Första gången — skapa ditt lärarkonto. Du blir administratör för klassen."}
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              Logga in med e‑post och lösenord.
            </p>
          )}

          {mode === "bootstrap" && schoolStatus?.bootstrap_requires_secret && (
            <input
              type="text"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Bootstrap-kod"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
          )}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="E-post"
            autoFocus
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          {mode === "bootstrap" && (
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Namn"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
          )}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Lösenord"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          {mode === "bootstrap" && (
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Bekräfta lösenord"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
          )}
          {err && <div className="text-sm text-rose-600">{err}</div>}
          <button
            disabled={busy}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium disabled:opacity-50"
          >
            {busy ? "Arbetar…" : mode === "bootstrap" ? "Skapa lärarkonto" : "Logga in"}
          </button>

          <div className="text-center text-sm text-slate-500 pt-2 border-t">
            Är du elev?{" "}
            <Link to="/login/student" className="text-brand-600 hover:underline">
              Elevinloggning
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
