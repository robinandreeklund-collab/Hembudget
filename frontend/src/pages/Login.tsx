import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { GraduationCap, Lock, Users } from "lucide-react";

type Mode = "master" | "teacher" | "student" | "teacher_bootstrap";

export default function Login() {
  const {
    initialized,
    login,
    initialize,
    schoolMode,
    schoolStatus,
    teacherLogin,
    teacherBootstrap,
    studentLogin,
  } = useAuth();
  const [mode, setMode] = useState<Mode>(() => {
    if (schoolMode) {
      return schoolStatus?.bootstrap_ready ? "teacher_bootstrap" : "student";
    }
    return "master";
  });
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [bootstrapSecret, setBootstrapSecret] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loginCode, setLoginCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const needsInit = initialized === false;

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      if (mode === "master") {
        if (needsInit) {
          if (password.length < 8) throw new Error("Lösenord måste vara minst 8 tecken.");
          if (password !== confirm) throw new Error("Lösenorden matchar inte.");
          await initialize(password);
        } else {
          await login(password);
        }
      } else if (mode === "teacher") {
        await teacherLogin(email, password);
      } else if (mode === "teacher_bootstrap") {
        if (password.length < 8) throw new Error("Lösenord måste vara minst 8 tecken.");
        if (password !== confirm) throw new Error("Lösenorden matchar inte.");
        await teacherBootstrap(bootstrapSecret, email, password, name || "Lärare");
      } else {
        await studentLogin(loginCode.toUpperCase());
      }
      window.location.reload();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full grid place-items-center bg-gradient-to-br from-slate-50 to-brand-50">
      <form
        onSubmit={handle}
        className="bg-white rounded-2xl shadow-lg p-8 w-[26rem] space-y-4 border border-slate-200"
      >
        <div className="flex items-center gap-2 text-brand-600">
          {mode === "student" ? (
            <GraduationCap className="w-5 h-5" />
          ) : mode.startsWith("teacher") ? (
            <Users className="w-5 h-5" />
          ) : (
            <Lock className="w-5 h-5" />
          )}
          <h1 className="text-xl font-semibold">Hembudget</h1>
        </div>

        {schoolMode && (
          <div className="flex gap-1 text-xs bg-slate-100 rounded-lg p-1">
            <button
              type="button"
              onClick={() =>
                setMode(schoolStatus?.bootstrap_ready ? "teacher_bootstrap" : "teacher")
              }
              className={`flex-1 py-1.5 rounded ${
                mode.startsWith("teacher")
                  ? "bg-white shadow text-brand-700 font-medium"
                  : "text-slate-600"
              }`}
            >
              Lärare
            </button>
            <button
              type="button"
              onClick={() => setMode("student")}
              className={`flex-1 py-1.5 rounded ${
                mode === "student"
                  ? "bg-white shadow text-brand-700 font-medium"
                  : "text-slate-600"
              }`}
            >
              Elev
            </button>
          </div>
        )}

        {mode === "master" && (
          <p className="text-sm text-slate-700">
            {needsInit
              ? "Välj ett master-lösenord. Det används för att kryptera din databas — det kan inte återställas."
              : "Logga in med ditt master-lösenord."}
          </p>
        )}
        {mode === "teacher_bootstrap" && (
          <p className="text-sm text-amber-700 bg-amber-50 rounded p-2 border border-amber-200">
            {schoolStatus?.bootstrap_requires_secret
              ? "Första gången — skapa lärarkonto. Ange bootstrap-koden som satts i deployens env-vars."
              : "Välkommen! Skapa ditt lärarkonto. Du blir administratör för alla elever på denna instans."}
          </p>
        )}
        {mode === "teacher" && (
          <p className="text-sm text-slate-700">Logga in som lärare.</p>
        )}
        {mode === "student" && (
          <p className="text-sm text-slate-700">
            Ange den 6-tecken kod du fått av din lärare.
          </p>
        )}

        {mode === "teacher_bootstrap" &&
          schoolStatus?.bootstrap_requires_secret && (
            <input
              type="text"
              value={bootstrapSecret}
              onChange={(e) => setBootstrapSecret(e.target.value)}
              placeholder="Bootstrap-kod"
              className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
            />
          )}
        {(mode === "teacher" || mode === "teacher_bootstrap") && (
          <>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="E-post"
              autoFocus
              className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
            />
            {mode === "teacher_bootstrap" && (
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Namn"
                className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
              />
            )}
          </>
        )}
        {mode === "student" && (
          <input
            type="text"
            value={loginCode}
            onChange={(e) => setLoginCode(e.target.value.toUpperCase())}
            placeholder="ABC123"
            autoFocus
            maxLength={6}
            className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none font-mono tracking-widest text-center text-lg"
          />
        )}
        {(mode === "master" || mode === "teacher" || mode === "teacher_bootstrap") && (
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Lösenord"
            autoFocus={mode === "master"}
            className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
          />
        )}
        {(needsInit && mode === "master") || mode === "teacher_bootstrap" ? (
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Bekräfta lösenord"
            className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
          />
        ) : null}

        {err && <div className="text-sm text-rose-600">{err}</div>}
        <button
          disabled={busy}
          className="w-full bg-brand-600 text-white rounded-lg py-2 font-medium hover:bg-brand-700 disabled:opacity-50"
        >
          {busy
            ? "Arbetar…"
            : mode === "teacher_bootstrap"
            ? "Skapa lärarkonto"
            : mode === "student"
            ? "Logga in"
            : needsInit && mode === "master"
            ? "Skapa och logga in"
            : "Logga in"}
        </button>
      </form>
    </div>
  );
}
