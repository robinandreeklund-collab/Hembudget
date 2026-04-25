import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Zap } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Eyebrow, PaperChip, SectionDivider } from "@/components/paper";

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
    <div className="min-h-screen bg-paper text-ink p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <Link
          to="/"
          className="text-sm text-[#666] nav-link inline-flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till startsidan
        </Link>

        <div className="border-l-[3px] border-ink bg-white p-4 flex items-start gap-3">
          <Zap className="w-5 h-5 mt-0.5 shrink-0" strokeWidth={1.5} />
          <div>
            <div className="serif text-lg leading-tight">Demoläge</div>
            <p className="body-prose text-sm mt-1">
              All data i demo-miljön återställs automatiskt var 10:e minut.
              Perfekt för att testa plattformen utan att skapa konto. Du
              delar demo-miljön med andra besökare — spara inget viktigt.
            </p>
          </div>
        </div>

        {err && (
          <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
            {err}
          </div>
        )}

        {!status ? (
          <div className="text-[#888] text-sm serif-italic">Laddar…</div>
        ) : !status.demo_available ? (
          <div className="border-[1.5px] border-rule bg-white p-4 text-sm text-[#555]">
            Demomiljön är inte tillgänglig just nu
            {status.reason ? `: ${status.reason}` : "."}. Testa igen om en minut.
          </div>
        ) : (
          <>
            <div>
              <Eyebrow className="mb-2">Testa plattformen</Eyebrow>
              <h1 className="serif text-3xl md:text-4xl leading-tight">
                Välj rollen du vill prova.
              </h1>
            </div>

            <button
              onClick={loginAsTeacher}
              disabled={busy}
              className="w-full text-left feature-card disabled:opacity-50"
            >
              <div className="flex items-start gap-4">
                <PaperChip color="special">Lä</PaperChip>
                <div className="flex-1">
                  <h2 className="serif text-xl">Logga in som lärare</h2>
                  <p className="body-prose text-sm mt-2">
                    Skapa elever, skicka dokument, se klassöversikten, skriv
                    uppdrag. Som om du skulle använda det i klassrummet.
                  </p>
                </div>
              </div>
            </button>

            <div className="border-[1.5px] border-ink bg-white p-6">
              <div className="flex items-center gap-3 mb-4">
                <PaperChip color="grund">El</PaperChip>
                <div>
                  <h2 className="serif text-xl">Logga in som elev</h2>
                  <p className="body-prose text-sm">
                    Välj vilken av demo-eleverna du vill prova.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {(status.student_codes ?? []).map((s) => (
                  <button
                    key={s.code}
                    onClick={() => loginAsStudent(s.code)}
                    disabled={busy}
                    className="text-left border-[1.5px] border-rule hover:border-ink hover:bg-paper px-4 py-3 transition-colors disabled:opacity-50"
                  >
                    <div className="serif text-base text-ink">{s.name}</div>
                    <div className="text-xs text-[#666] mt-0.5">
                      {s.class} · kod <span className="kbd">{s.code}</span>
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

        <SectionDivider className="pt-4">eller</SectionDivider>
        <div className="text-center">
          <Link to="/login" className="nav-link text-sm">Riktig inloggning</Link>
        </div>
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
    <div className="text-center text-xs text-[#888] serif-italic">
      Nästa automatiska reset om {mins} min {secs.toString().padStart(2, "0")} s
    </div>
  );
}
