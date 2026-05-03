/**
 * BankID-simulator — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-bankid):
 * - bankid-head med "Signering — N fakturor, en handling"
 * - 2-kolumns grid: QR-mock + 6-stegs-flöde (steps)
 * - doc-list · alla fakturor som ska signeras med beloppen
 * - bankid-cta · "Signera alla i appen" + "Avbryt"
 * - peda-block "Du signerar X kr. Fingret ska få veta."
 *
 * Pedagogiskt: friktion bevarad. Eleven måste välja, läsa, signera.
 * Tid-spårning för wellbeing-faktorn (< 5 sek = "fingret fick inte veta").
 */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import {
  v2Api,
  type V2BankIDSessionOut,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

const STEPS = [
  {
    title: "Banken har tagit emot fakturor från Bankgirot.",
    sub: "Senast uppdaterat idag",
  },
  {
    title: "Återkommande fakturor matchade vanor — autoklassade.",
    sub: "Hyra · El · SL · Spotify · m.fl.",
  },
  {
    title: "Oregelbundna fakturor klassade manuellt.",
    sub: "Tandläkare · IKEA · Foodora · Apoteket",
  },
  {
    title: "Skanna QR-koden med Ekonomilabbet-ID.",
    sub: "Eller skriv in personnumret för länk till mobilen",
  },
  {
    title: "Öppna appen, läs sammandraget, ange din 6-siffriga PIN.",
    sub: "Signera total summa",
  },
  {
    title: "Banken bekräftar — fakturorna betalas automatiskt.",
    sub: "Ingen mer åtgärd krävs",
  },
];

export function BankIDV2() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const sid = sessionId ? parseInt(sessionId, 10) : 0;
  const navigate = useNavigate();
  const [session, setSession] = useState<V2BankIDSessionOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasPin, setHasPin] = useState<boolean | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!sid) return;
    startTimeRef.current = Date.now();
    v2Api
      .bankidGet(sid)
      .then(setSession)
      .catch((e) => setError(String((e as Error)?.message || e)));
    // Kolla om eleven har satt sin 4-siffriga PIN
    v2Api.bankidPinStatus()
      .then((s) => setHasPin(s.has_pin))
      .catch(() => setHasPin(null));
  }, [sid]);

  // Polling · när desktop visar QR och eleven scannar med mobil,
  // pollar vi sessionen var 2:a sekund för att upptäcka när mobilens
  // PIN-bekräftelse går igenom (status ändras pending → signed).
  useEffect(() => {
    if (!sid || !session || session.status !== "pending") return;
    const id = window.setInterval(async () => {
      try {
        const fresh = await v2Api.bankidGet(sid);
        if (fresh.status !== "pending") {
          setSession(fresh);
          window.clearInterval(id);
          if (fresh.status === "signed") {
            // Visa "signed" i 1.5s, gå sedan till banken
            setTimeout(() => navigate("/v2/banken"), 1500);
          }
        }
      } catch {
        // tyst fel · pollar igen nästa interval
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [sid, session?.status, session, navigate]);

  // Sign-knappen visar instruktioner istället för att signera direkt.
  // PIN-flödet sker på mobilen efter QR-scan.
  async function sign() {
    // Om PIN saknas, hänvisa eleven att sätta en i banken först
    if (hasPin === false) {
      setError(
        "Du måste sätta din 4-siffriga BankID-PIN i banken först. "
        + "Gå tillbaka till banken och sätt en PIN.",
      );
      return;
    }
    setError(
      "Scanna QR-koden med din mobil för att signera. "
      + "PIN-frågan kommer upp på mobilen.",
    );
  }

  async function cancel() {
    if (!session) return;
    if (!confirm("Avbryt signeringen?")) return;
    try {
      await v2Api.bankidCancel(session.id);
      navigate("/v2/banken");
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error && !session) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda BankID-session
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!session) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar BankID-simulator…</div>
      </div>
    );
  }

  const isSigned = session.status === "signed";
  const isCancelled = session.status === "cancelled";
  const currentStep = isSigned ? 6 : session.current_step;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell" data-guide="bankid-qr">
        <Link className="actor-back" to="/v2/banken">
          Tillbaka till banken
        </Link>

        <div
          style={{
            background: "rgba(15,21,37,0.8)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: "32px 36px",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "1.4px",
              textTransform: "uppercase",
              color: "var(--warm)",
              marginBottom: 8,
            }}
          >
            BankID-simulator · Ekonomilabbet-ID
          </div>
          <h1
            style={{
              fontFamily: "var(--serif)",
              fontWeight: 700,
              fontSize: 32,
              letterSpacing: "-0.8px",
              margin: 0,
            }}
          >
            Signering — <em>{session.invoice_count} fakturor</em>, en
            handling.
          </h1>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "var(--text-mid)",
              marginTop: 8,
            }}
          >
            Sandbox · känns som riktigt
          </div>

          {isSigned && (
            <div
              style={{
                marginTop: 18,
                padding: "16px 20px",
                background: "rgba(110,231,183,0.08)",
                border: "1px solid rgba(110,231,183,0.4)",
                borderRadius: 6,
                fontFamily: "var(--serif)",
                fontSize: 14,
                color: "#6ee7b7",
              }}
            >
              ✓ Signerat {SEK(session.total_amount)} kr på{" "}
              {session.invoice_count} fakturor.{" "}
              {session.duration_seconds != null && (
                <em
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                  }}
                >
                  Tog dig {session.duration_seconds} sekunder.{" "}
                  {session.duration_seconds < 5
                    ? "(snabbt — har du läst sammandraget?)"
                    : "Bra — fingret fick veta."}
                </em>
              )}
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-mid)",
                  marginTop: 8,
                }}
              >
                Återgår till banken om 1,5 sek…
              </div>
            </div>
          )}

          {isCancelled && (
            <div
              style={{
                marginTop: 18,
                padding: "16px 20px",
                background: "rgba(220,76,43,0.06)",
                border: "1px solid rgba(220,76,43,0.4)",
                borderRadius: 6,
                fontFamily: "var(--serif)",
                fontSize: 14,
                color: "#fda594",
              }}
            >
              ○ Avbrutet — du läste och tänkte efter, vilket är hälsosamt.
              Inga autogiro skapade.
            </div>
          )}
        </div>

        {!isSigned && !isCancelled && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "260px 1fr",
              gap: 24,
              marginBottom: 22,
            }}
          >
            {/* Riktig QR-kod · använder qrcode.react. Värdet är
                pedagogisk-meaningful URL till själva sessionen så
                eleven kan scanna med mobil och hamnar på samma sida.
                Eftersom det är en simulator gör vi inget riktigt
                BankID-anrop, men flödet känns äkta. */}
            <div>
              <div
                style={{
                  width: 240,
                  height: 240,
                  background: "#fff",
                  borderRadius: 12,
                  padding: 20,
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <QRCodeSVG
                  value={
                    session.confirm_token
                      ? (typeof window !== "undefined"
                        ? `${window.location.origin}/v2/bankid/confirm/${session.confirm_token}`
                        : `https://ekonomilabbet.org/v2/bankid/confirm/${session.confirm_token}`)
                      : `https://ekonomilabbet.org/v2/bankid/${session.id}`
                  }
                  size={200}
                  bgColor="#ffffff"
                  fgColor="#0a0e1a"
                  level="M"
                  includeMargin={false}
                />
              </div>
              <div
                style={{
                  textAlign: "center",
                  fontFamily: "var(--mono)",
                  fontSize: 9.5,
                  color: "var(--text-dim)",
                  marginTop: 10,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                }}
              >
                QR · skanna med Ekonomilabbet-ID
              </div>
            </div>

            {/* Steg-flöde */}
            <ol
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: 14,
              }}
            >
              {STEPS.map((s, i) => {
                const stepNum = i + 1;
                const isDone = stepNum < currentStep;
                const isNow = stepNum === currentStep;
                return (
                  <li
                    key={i}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "32px 1fr",
                      gap: 14,
                      alignItems: "start",
                    }}
                  >
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: "50%",
                        display: "grid",
                        placeItems: "center",
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        fontWeight: 700,
                        background: isDone
                          ? "rgba(110,231,183,0.15)"
                          : isNow
                          ? "var(--warm)"
                          : "rgba(255,255,255,0.04)",
                        color: isDone
                          ? "#6ee7b7"
                          : isNow
                          ? "#422006"
                          : "var(--text-mid)",
                        border: isDone
                          ? "1px solid rgba(110,231,183,0.4)"
                          : isNow
                          ? "1px solid var(--warm)"
                          : "1px solid var(--line-strong)",
                      }}
                    >
                      {isDone ? "✓" : stepNum}
                    </div>
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 14,
                          color: isNow
                            ? "var(--warm)"
                            : isDone
                            ? "var(--text-mid)"
                            : "#fff",
                        }}
                      >
                        {s.title}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          color: "var(--text-dim)",
                          marginTop: 2,
                        }}
                      >
                        {stepNum === 5 && session.total_amount > 0
                          ? `Total summa att signera: ${SEK(session.total_amount)} kr`
                          : s.sub}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        {/* DOC-LIST · fakturor */}
        <div
          style={{
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            overflow: "hidden",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              padding: "12px 18px",
              fontFamily: "var(--mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-dim)",
              borderBottom: "1px solid var(--line)",
            }}
          >
            {session.invoice_count} fakturor · att signera ·{" "}
            {SEK(session.total_amount)} kr totalt
          </div>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              maxHeight: 360,
              overflowY: "auto",
            }}
          >
            {session.invoices.map((inv) => (
              <li
                key={inv.upcoming_id}
                style={{
                  padding: "10px 18px",
                  display: "grid",
                  gridTemplateColumns: "1fr 90px 100px",
                  gap: 12,
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: inv.is_anomaly ? "var(--accent)" : "#fff",
                }}
              >
                <span>
                  {inv.name}
                  {inv.is_anomaly && " ⚠ NY"}
                  {inv.is_recurring && (
                    <span
                      style={{
                        marginLeft: 6,
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: "var(--text-dim)",
                      }}
                    >
                      · återkommande
                    </span>
                  )}
                </span>
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                    textAlign: "right",
                  }}
                >
                  {SHORT_DATE(inv.due_date)}
                </span>
                <em
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    color: "var(--warm)",
                    textAlign: "right",
                    fontStyle: "normal",
                  }}
                >
                  {SEK(inv.amount)} kr
                </em>
              </li>
            ))}
          </ul>
        </div>

        {!isSigned && !isCancelled && (
          <div
            style={{
              display: "flex",
              gap: 14,
              alignItems: "center",
              flexWrap: "wrap",
              marginBottom: 22,
            }}
          >
            <button
              type="button"
              className="cta-btn"
              disabled={false}
              onClick={sign}
              style={{ fontSize: 14, padding: "12px 24px" }}
            >
              {`Signera ${session.invoice_count} fakturor på mobilen →`}
            </button>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                cancel();
              }}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--text-mid)",
                textDecoration: "none",
                letterSpacing: "1px",
                textTransform: "uppercase",
              }}
            >
              Avbryt & gå tillbaka
            </a>
          </div>
        )}

        <div
          style={{
            textAlign: "center",
            fontFamily: "var(--mono)",
            fontSize: 9.5,
            color: "var(--text-dim)",
            margin: "24px 0",
            letterSpacing: "1px",
            textTransform: "uppercase",
          }}
        >
          Detta är en simulator. Inga riktiga BankID-anrop görs.
          Pedagogisk friktion bevarad.
        </div>

        <div className="peda" style={{ marginTop: 28 }}>
          <div className="peda-eye">
            Pedagogik · varför vi inte hoppar över BankID
          </div>
          <div className="peda-h">
            Du <em>signerar {SEK(session.total_amount)} kr</em>. Fingret
            ska få veta.
          </div>
          <p className="peda-prose">
            Det vore tekniskt trivialt att låta dig trycka enter och
            hoppa över QR-koden. Men då försvinner{" "}
            <strong>medvetenheten</strong> — känslan av att{" "}
            <em>
              "detta är {session.invoice_count} fakturor som binder mig
              till leverantörer i 30 dagar"
            </em>
            . BankID-flödet är medvetet <em>4–6 stegs</em> långt eftersom
            det är i den friktionen vana vuxna lär sig att{" "}
            <strong>inte signera utan att läsa</strong>.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Säkerhet</strong>QR-koden är bunden till en
              specifik signering. Aldrig återanvändbar.
            </li>
            <li>
              <strong>Verkligt flöde</strong>Skanna · läs · ange PIN.
              Tre enkla steg som tränar muskeln.
            </li>
            <li>
              <strong>Granskningstid</strong>Sammandraget visar vad du
              faktiskt signerar. Lär dig läsa det.
            </li>
            <li>
              <strong>Återkalla</strong>Banken kan avbryta autogiro
              <em>innan</em> dragning. Lär dig hur.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Elektronisk signatur</span>
            <span className="peda-concept">Autogiro</span>
            <span className="peda-concept">Bankgiro</span>
            <span className="peda-concept">Förfallodatum</span>
            <span className="peda-concept">OCR-nummer</span>
          </div>
          <div className="peda-tip">
            Pedagogisk wellbeing-koppling: 1+ signerad session senaste
            90 dgr → +2 economy. Snabb signering (&lt; 5 sek) flaggas
            negativt — fingret fick inte veta.
          </div>
        </div>

        {/* Echo · fråga om vad som ska signeras */}
      </div>
    </div>
  );
}
