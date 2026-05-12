/**
 * BankIdSignModal · QR-kod-baserad signering för lån-acceptans.
 *
 * Återanvänd från MailDetailV2 + LanV2. Matchar /v2/bank-id-flödet
 * och pages/Bank.tsx-mönstret:
 *
 *  1. Föräldrarkomponent har redan initierat BankID-session via
 *     v2Api.bankSessionInit('private_loan_sign_<id>') och fått
 *     { token, qr_url, expires_at }.
 *  2. Modalen visar QR-kod som länkar till /bank/sign?token=...
 *  3. Eleven scannar med mobilen (eller klickar länken direkt) →
 *     /bank/sign-vyn visar PIN-form → POST /bank/session/{token}/
 *     confirm → confirmed_at sätts.
 *  4. Föräldrar pollar v2Api.bankSessionStatus och triggar accept-
 *     callback när confirmed_at != null. Modalen visar bara state.
 *
 * Modalen accepterar inte själv lånet · det gör föräldrarkomponenten
 * efter att den sett confirmed=true via polling. Detta håller
 * komponenten ren och återanvändbar.
 */
import { QRCodeSVG } from "qrcode.react";

type BankIdSession = {
  token: string;
  qr_url: string;
  expires_at: string;
};

export function BankIdSignModal({
  session,
  confirmed,
  error,
  onClose,
}: {
  session: BankIdSession;
  confirmed: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const fullUrl = `${window.location.origin}${session.qr_url}`;
  const expiresAt = new Date(session.expires_at);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.78)", zIndex: 200,
        display: "flex", alignItems: "center",
        justifyContent: "center", padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12,
          padding: 28,
          maxWidth: 540,
          width: "100%",
        }}
      >
        <div style={{
          fontFamily: "var(--mono)",
          fontSize: 10, letterSpacing: 1.4,
          color: "#a5b4fc",
        }}>
          ● BANKID · SIGNERA LÅN
        </div>
        <h2 style={{
          fontFamily: "var(--serif)",
          color: "#fff",
          marginTop: 12,
          marginBottom: 8,
          fontSize: 22,
        }}>
          {confirmed ? "Signering bekräftad" : "Bekräfta på din mobil"}
        </h2>

        {confirmed ? (
          <div style={{
            padding: "14px 16px",
            borderRadius: 8,
            background: "rgba(110,231,183,0.08)",
            border: "1px solid rgba(110,231,183,0.35)",
            color: "#6ee7b7",
            fontFamily: "var(--serif)",
            fontSize: 14,
            lineHeight: 1.5,
          }}>
            ✓ BankID-signaturen är bekräftad. Lånet utbetalas nu till
            ditt lönekonto…
          </div>
        ) : (
          <>
            <p style={{
              fontFamily: "var(--serif)",
              fontSize: 13.5,
              color: "rgba(255,255,255,0.7)",
              lineHeight: 1.5,
              marginBottom: 18,
            }}>
              Skanna QR-koden med din mobil — eller klicka länken
              direkt — för att signera lån-acceptansen med BankID.
            </p>
            <div style={{
              display: "grid",
              gridTemplateColumns: "180px 1fr",
              gap: 18,
              alignItems: "start",
            }}>
              <div style={{
                padding: 12,
                background: "#fff",
                borderRadius: 8,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}>
                <QRCodeSVG
                  value={fullUrl}
                  size={156}
                  bgColor="#ffffff"
                  fgColor="#0f172a"
                  level="M"
                />
              </div>
              <div>
                <div style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10, letterSpacing: 1.2,
                  color: "rgba(255,255,255,0.5)",
                  textTransform: "uppercase",
                  marginBottom: 6,
                }}>
                  Steg 1 · scanna
                </div>
                <div style={{
                  fontFamily: "var(--serif)",
                  fontSize: 13.5,
                  color: "rgba(255,255,255,0.85)",
                  marginBottom: 14,
                  lineHeight: 1.5,
                }}>
                  Skanna QR-koden eller öppna länken nedan i en ny
                  flik (för att simulera mobilen):
                </div>
                <a
                  href={session.qr_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "block",
                    border: "1px dashed rgba(255,255,255,0.25)",
                    borderRadius: 6,
                    padding: "8px 10px",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#a5b4fc",
                    wordBreak: "break-all",
                    textDecoration: "none",
                    marginBottom: 14,
                  }}
                >
                  {fullUrl}
                </a>
                <div style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10, letterSpacing: 1.2,
                  color: "rgba(255,255,255,0.5)",
                  textTransform: "uppercase",
                  marginBottom: 6,
                }}>
                  Steg 2 · skriv din PIN
                </div>
                <div style={{
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "rgba(255,255,255,0.65)",
                  lineHeight: 1.5,
                }}>
                  På telefon-vyn skriver du din 4-siffriga BankID-PIN
                  och trycker Bekräfta. Webben fortsätter automatiskt.
                </div>
                <div style={{
                  marginTop: 16,
                  padding: "8px 12px",
                  background: "rgba(167,139,250,0.06)",
                  border: "1px solid rgba(167,139,250,0.25)",
                  borderRadius: 6,
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "#a5b4fc",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}>
                  <span style={{ animation: "pulse 1.5s infinite" }}>
                    ●
                  </span>
                  Väntar på bekräftelse…
                </div>
              </div>
            </div>
          </>
        )}

        {error && (
          <div style={{
            marginTop: 14,
            padding: "10px 12px",
            borderRadius: 6,
            background: "rgba(252,165,165,0.08)",
            border: "1px solid rgba(252,165,165,0.35)",
            color: "#fca5a5",
            fontFamily: "var(--mono)",
            fontSize: 11,
          }}>
            {error}
          </div>
        )}

        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 18,
        }}>
          <p style={{
            fontFamily: "var(--mono)",
            fontSize: 10,
            color: "rgba(255,255,255,0.4)",
            margin: 0,
          }}>
            Session löper ut {expiresAt.toLocaleTimeString("sv-SE")}
          </p>
          <button
            type="button"
            className="cta-btn ghost"
            onClick={onClose}
            style={{ border: 0, cursor: "pointer" }}
            disabled={confirmed}
          >
            {confirmed ? "Slutför…" : "Avbryt"}
          </button>
        </div>
      </div>
    </div>
  );
}
