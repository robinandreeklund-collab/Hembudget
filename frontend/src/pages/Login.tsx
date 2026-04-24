import { useEffect, useState } from "react";
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
  const [mode, setMode] = useState<Mode>("master");

  // schoolMode/schoolStatus laddas asynkront i useAuth — när vi vet att
  // skol-läget är på, växla bort från master-flödet (som inte gäller där)
  // och peka rätt: bootstrap om ingen lärare finns, annars teacher-login.
  useEffect(() => {
    if (schoolMode) {
      setMode((prev) => {
        if (prev === "master") {
          return schoolStatus?.bootstrap_ready ? "teacher_bootstrap" : "teacher";
        }
        return prev;
      });
    }
  }, [schoolMode, schoolStatus?.bootstrap_ready]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [bootstrapSecret, setBootstrapSecret] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loginCode, setLoginCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // I school-mode finns ingen master-DB-init — det är desktop-läge.
  // needsInit ska bara trigga master-flödet utanför school-mode.
  const needsInit = !schoolMode && initialized === false;
  // Sanity: säkerställ att vi aldrig hamnar i master-mode i school-mode
  // (det räddar t.ex. fall där sessionStorage från en gammal lokal
  // session får mode:n att hänga sig kvar).
  const effectiveMode: Mode = schoolMode && mode === "master"
    ? (schoolStatus?.bootstrap_ready ? "teacher_bootstrap" : "teacher")
    : mode;

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      if (effectiveMode === "master") {
        if (needsInit) {
          if (password.length < 8) throw new Error("Lösenord måste vara minst 8 tecken.");
          if (password !== confirm) throw new Error("Lösenorden matchar inte.");
          await initialize(password);
        } else {
          await login(password);
        }
      } else if (effectiveMode === "teacher") {
        await teacherLogin(email, password);
      } else if (effectiveMode === "teacher_bootstrap") {
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
          {effectiveMode === "student" ? (
            <GraduationCap className="w-5 h-5" />
          ) : effectiveMode.startsWith("teacher") ? (
            <Users className="w-5 h-5" />
          ) : (
            <Lock className="w-5 h-5" />
          )}
          <h1 className="text-xl font-semibold">
            {schoolMode ? "Ekonomilabbet" : "Hembudget"}
          </h1>
        </div>

        {schoolMode && (
          <div className="flex gap-1 text-xs bg-slate-100 rounded-lg p-1">
            <button
              type="button"
              onClick={() =>
                setMode(schoolStatus?.bootstrap_ready ? "teacher_bootstrap" : "teacher")
              }
              className={`flex-1 py-1.5 rounded ${
                effectiveMode.startsWith("teacher")
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
                effectiveMode === "student"
                  ? "bg-white shadow text-brand-700 font-medium"
                  : "text-slate-600"
              }`}
            >
              Elev
            </button>
          </div>
        )}

        {effectiveMode === "master" && (
          <p className="text-sm text-slate-700">
            {needsInit
              ? "Välj ett master-lösenord. Det används för att kryptera din databas — det kan inte återställas."
              : "Logga in med ditt master-lösenord."}
          </p>
        )}
        {effectiveMode === "teacher_bootstrap" && (
          <p className="text-sm text-amber-700 bg-amber-50 rounded p-2 border border-amber-200">
            {schoolStatus?.bootstrap_requires_secret
              ? "Första gången — skapa lärarkonto. Ange bootstrap-koden som satts i deployens env-vars."
              : "Välkommen till Ekonomilabbet! Skapa ditt lärarkonto. Du blir administratör för alla dina elever."}
          </p>
        )}
        {effectiveMode === "teacher" && (
          <p className="text-sm text-slate-700">Logga in som lärare.</p>
        )}
        {effectiveMode === "student" && (
          <p className="text-sm text-slate-700">
            Ange den 6-tecken kod du fått av din lärare.
          </p>
        )}

        {effectiveMode === "teacher_bootstrap" &&
          schoolStatus?.bootstrap_requires_secret && (
            <input
              type="text"
              value={bootstrapSecret}
              onChange={(e) => setBootstrapSecret(e.target.value)}
              placeholder="Bootstrap-kod"
              className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
            />
          )}
        {(effectiveMode === "teacher" || effectiveMode === "teacher_bootstrap") && (
          <>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="E-post"
              autoFocus
              className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
            />
            {effectiveMode === "teacher_bootstrap" && (
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
        {effectiveMode === "student" && (
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
        {(effectiveMode === "master" || effectiveMode === "teacher" || effectiveMode === "teacher_bootstrap") && (
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Lösenord"
            autoFocus={effectiveMode === "master"}
            className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
          />
        )}
        {(needsInit && effectiveMode === "master") || effectiveMode === "teacher_bootstrap" ? (
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
            : effectiveMode === "teacher_bootstrap"
            ? "Skapa lärarkonto"
            : effectiveMode === "student"
            ? "Logga in"
            : needsInit && effectiveMode === "master"
            ? "Skapa och logga in"
            : "Logga in"}
        </button>
      </form>
    </div>
  );
}
