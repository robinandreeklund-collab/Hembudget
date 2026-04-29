import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";
import { LiveTime } from "@/components/editorial/LiveClock";

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
    setBusy(true);
    setErr(null);
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
    setBusy(true);
    setErr(null);
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
    <EditorialAuthShell topNavRight={<AuthAwareTopLinks />}>
      <div className="ed-eyebrow">Demoläge · Vol. 00</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <span className="ed-clock-countdown">
          Demon nollställs <em>var 10:e minut</em>.
        </span>
      </div>

      <p className="ed-subhead">
        Inget konto, ingen e-post. Testa plattformen som <em>lärare</em> eller
        som <em>elev</em> i en delad sandlåda. Allt återställs automatiskt
        så du kan börja om när du vill.
      </p>

      {err && <div className="ed-error">{err}</div>}

      {!status ? (
        <div className="ed-card">
          <p style={{ color: "rgba(255,255,255,0.6)", fontStyle: "italic", textAlign: "center", margin: 0 }}>
            Laddar demo-status…
          </p>
        </div>
      ) : !status.demo_available ? (
        <div className="ed-card">
          <p style={{ margin: 0 }}>
            Demomiljön är inte tillgänglig just nu
            {status.reason ? `: ${status.reason}` : "."}. Testa igen om en
            minut.
          </p>
        </div>
      ) : (
        <>
          <button
            onClick={loginAsTeacher}
            disabled={busy}
            className="ed-demo-tile"
            aria-label="Logga in som demo-lärare"
            style={{
              cursor: busy ? "not-allowed" : "pointer",
              opacity: busy ? 0.5 : 1,
              textAlign: "left",
              font: "inherit",
              color: "#fff",
              width: "100%",
            }}
          >
            <span className="ed-demo-tile-icon" aria-hidden="true">⚡</span>
            <div>
              <div className="ed-demo-tile-title">Logga in som lärare</div>
              <div className="ed-demo-tile-body">
                Skapa elever, skicka dokument, se klassöversikten, skriv
                uppdrag. Som om du skulle använda det i klassrummet.
              </div>
            </div>
          </button>

          {(status.student_codes ?? []).length > 0 && (
            <div>
              <div
                className="ed-eyebrow"
                style={{ marginTop: "12px", marginBottom: "16px" }}
              >
                Eller — som elev
              </div>
              <div className="ed-choices">
                {(status.student_codes ?? []).map((s) => (
                  <button
                    key={s.code}
                    onClick={() => loginAsStudent(s.code)}
                    disabled={busy}
                    className="ed-choice"
                    style={{
                      cursor: busy ? "not-allowed" : "pointer",
                      opacity: busy ? 0.5 : 1,
                      textAlign: "left",
                      font: "inherit",
                      color: "#fff",
                      width: "100%",
                    }}
                  >
                    <span className="ed-choice-eye">Kod · {s.code}</span>
                    <span className="ed-choice-title">{s.name}</span>
                    <span className="ed-choice-body">
                      {s.class ?? "Demo-elev"} · prova från elevens
                      perspektiv. Inget krävs av dig.
                    </span>
                    <span className="ed-choice-go">
                      Logga in <span className="ed-choice-go-arrow">→</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {status.next_reset_at && (
            <ResetCountdown iso={status.next_reset_at} />
          )}
        </>
      )}
    </EditorialAuthShell>
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
    <div
      style={{
        textAlign: "center",
        fontFamily: '"JetBrains Mono", ui-monospace, monospace',
        fontSize: "11px",
        letterSpacing: "1.6px",
        textTransform: "uppercase",
        color: "rgba(255, 255, 255, 0.5)",
        marginTop: "12px",
      }}
    >
      Nästa reset · {mins} min {secs.toString().padStart(2, "0")} s
    </div>
  );
}
