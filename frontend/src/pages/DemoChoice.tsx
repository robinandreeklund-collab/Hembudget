import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, GraduationCap, Users, Zap } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

type DemoStatus = {
  demo_available: boolean;
  teacher_email?: string;
  student_codes?: Array<{ name: string; code: string; class: string | null }>;
  next_reset_at?: string | null;
  reason?: string;
};

export default function DemoChoice() {
  const { demoTeacherLogin, demoStudentLogin } = useAuth();
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<DemoStatus>("/demo/status")
      .then(setStatus)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  async function loginAsTeacher() {
    setBusy(true); setErr(null);
    try {
      await demoTeacherLogin();
      window.location.href = "/teacher";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loginAsStudent(code: string) {
    setBusy(true); setErr(null);
    try {
      await demoStudentLogin(code);
      window.location.href = "/dashboard";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-amber-50 via-white to-brand-50 p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <Link
          to="/"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till startsidan
        </Link>

        <div className="bg-amber-100 border-l-4 border-amber-500 rounded p-4">
          <div className="flex items-center gap-2 font-semibold text-amber-900 mb-1">
            <Zap className="w-5 h-5" /> Demoläge
          </div>
          <p className="text-sm text-amber-900">
            All data i demo-miljön återställs automatiskt var 10:e minut.
            Perfekt för att testa plattformen utan att skapa konto. Du
            delar demo-miljön med andra besökare — spara inget viktigt.
          </p>
        </div>

        {err && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded p-3 text-sm">
            {err}
          </div>
        )}

        {!status ? (
          <div className="text-slate-500">Laddar…</div>
        ) : !status.demo_available ? (
          <div className="bg-slate-100 rounded p-4 text-sm text-slate-700">
            Demomiljön är inte tillgänglig just nu{status.reason ? `: ${status.reason}` : "."}. Testa igen om en minut.
          </div>
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 mb-1">
                Testa plattformen
              </h1>
              <p className="text-slate-600">Välj rollen du vill prova.</p>
            </div>

            {/* Lärarkortet */}
            <button
              onClick={loginAsTeacher}
              disabled={busy}
              className="w-full text-left group bg-white border-2 border-slate-200 hover:border-brand-500 rounded-2xl p-6 transition-all hover:shadow-xl disabled:opacity-50"
            >
              <div className="flex items-start gap-4">
                <div className="inline-flex w-12 h-12 bg-brand-100 text-brand-600 rounded-full items-center justify-center group-hover:scale-110 transition-transform">
                  <Users className="w-6 h-6" />
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-semibold text-slate-900">
                    Logga in som lärare
                  </h2>
                  <p className="text-sm text-slate-600 mt-1">
                    Skapa elever, skicka dokument, se klassöversikten, skriv
                    uppdrag. Som om du skulle använda det i klassrummet.
                  </p>
                </div>
              </div>
            </button>

            {/* Elevrad */}
            <div className="bg-white border-2 border-slate-200 rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="inline-flex w-10 h-10 bg-emerald-100 text-emerald-600 rounded-full items-center justify-center">
                  <GraduationCap className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    Logga in som elev
                  </h2>
                  <p className="text-sm text-slate-600">
                    Välj vilken av de 5 demo-eleverna du vill prova.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {(status.student_codes ?? []).map((s) => (
                  <button
                    key={s.code}
                    onClick={() => loginAsStudent(s.code)}
                    disabled={busy}
                    className="text-left border border-slate-200 hover:border-brand-400 hover:bg-brand-50 rounded-lg px-4 py-3 disabled:opacity-50"
                  >
                    <div className="font-medium text-slate-800">
                      {s.name}
                    </div>
                    <div className="text-xs text-slate-500">
                      {s.class} · kod {s.code}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {status.next_reset_at && (
              <ResetCountdown iso={status.next_reset_at} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ResetCountdown({ iso }: { iso: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);
  const diffMs = new Date(iso).getTime() - now;
  const mins = Math.max(0, Math.floor(diffMs / 60000));
  const secs = Math.max(0, Math.floor((diffMs % 60000) / 1000));
  return (
    <div className="text-center text-xs text-slate-500">
      Nästa automatiska reset om {mins} min {secs.toString().padStart(2, "0")} s
    </div>
  );
}
