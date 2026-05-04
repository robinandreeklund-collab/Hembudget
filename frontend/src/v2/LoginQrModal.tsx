/**
 * LoginQrModal · visar QR-kod + login-URL + login-kod för en elev.
 *
 * Lärare öppnar för att antingen visa direkt i klassrummet (eleven
 * scannar med mobilen) eller skriva ut + dela.
 *
 * Backend genererar QR som SVG-string så vi kan dangerouslySetInnerHTML
 * direkt — ingen runtime-rendering i frontend.
 */
import { useEffect, useState } from "react";
import { v2Api } from "./api";

type Props = {
  studentId: number;
  onClose: () => void;
};

export function LoginQrModal({ studentId, onClose }: Props) {
  const [data, setData] = useState<{
    student_name: string;
    login_code: string;
    login_url: string;
    qr_svg: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "url" | null>(null);

  useEffect(() => {
    v2Api
      .teacherStudentLoginQr(studentId)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [studentId]);

  // Esc-stäng
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function copy(value: string, kind: "code" | "url") {
    navigator.clipboard
      ?.writeText(value)
      .then(() => {
        setCopied(kind);
        window.setTimeout(() => setCopied(null), 1800);
      })
      .catch(() => undefined);
  }

  function printQr() {
    if (!data) return;
    const win = window.open("", "_blank", "noopener");
    if (!win) return;
    win.document.write(`<!DOCTYPE html>
<html lang="sv"><head><meta charset="utf-8">
<title>Login-QR · ${data.student_name}</title>
<style>
  body { font-family: Georgia, serif; padding: 40px; text-align: center; }
  .code { font-family: monospace; font-size: 32px; font-weight: 700; letter-spacing: 6px; margin: 20px 0; color: #d97706; }
  .name { font-size: 24px; margin-bottom: 8px; }
  .url { font-family: monospace; font-size: 12px; color: #555; margin-top: 16px; word-break: break-all; }
  svg { max-width: 320px; margin: 0 auto; display: block; }
</style></head><body>
  <div class="name">${data.student_name}</div>
  <div class="code">${data.login_code}</div>
  ${data.qr_svg}
  <div class="url">${data.login_url}</div>
  <p style="font-size: 11px; color: #888; margin-top: 24px;">
    Skanna med kamera-appen eller skriv in koden på<br>${data.login_url.split("?")[0]}
  </p>
</body></html>`);
    win.document.close();
    win.focus();
    win.print();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        background: "rgba(0,0,0,0.6)",
        display: "grid",
        placeItems: "center",
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 500,
          background: "rgba(15,21,37,0.98)",
          border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          borderTop: "3px solid var(--warm, #fbbf24)",
          borderRadius: 8,
          padding: "24px 28px",
          maxHeight: "calc(100vh - 80px)",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "start",
            marginBottom: 14,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 1.4,
                textTransform: "uppercase",
                color: "var(--warm, #fbbf24)",
                marginBottom: 4,
              }}
            >
              ● Login-QR
            </div>
            <h2
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 22,
                fontWeight: 700,
                color: "#fff",
                margin: 0,
                letterSpacing: -0.4,
              }}
            >
              {data ? data.student_name : "Laddar…"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Stäng"
            style={{
              background: "transparent",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              color: "rgba(255,255,255,0.7)",
              width: 32,
              height: 32,
              borderRadius: 50,
              fontSize: 16,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            ×
          </button>
        </div>

        {error && (
          <div
            style={{
              color: "#fca5a5",
              fontSize: 12,
              fontFamily: "JetBrains Mono, monospace",
              padding: 12,
              background: "rgba(220,76,43,0.08)",
              borderRadius: 6,
            }}
          >
            Kunde inte ladda QR: {error}
          </div>
        )}

        {data && (
          <>
            <div
              style={{
                background: "#fff",
                padding: 16,
                borderRadius: 6,
                marginBottom: 14,
                display: "grid",
                placeItems: "center",
              }}
              dangerouslySetInnerHTML={{ __html: data.qr_svg }}
            />

            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9.5,
                color: "rgba(255,255,255,0.4)",
                letterSpacing: 1.2,
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              Login-kod
            </div>
            <div
              style={{
                display: "flex",
                gap: 8,
                marginBottom: 12,
              }}
            >
              <code
                style={{
                  flex: 1,
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 22,
                  fontWeight: 700,
                  letterSpacing: 4,
                  color: "var(--warm, #fbbf24)",
                  background: "rgba(251,191,36,0.10)",
                  padding: "8px 14px",
                  borderRadius: 6,
                  border: "1px solid rgba(251,191,36,0.25)",
                }}
              >
                {data.login_code}
              </code>
              <button
                type="button"
                onClick={() => copy(data.login_code, "code")}
                style={pillBtnStyle()}
              >
                {copied === "code" ? "✓ Kopierad" : "Kopiera"}
              </button>
            </div>

            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9.5,
                color: "rgba(255,255,255,0.4)",
                letterSpacing: 1.2,
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              Login-URL
            </div>
            <div
              style={{
                display: "flex",
                gap: 8,
                marginBottom: 18,
              }}
            >
              <code
                style={{
                  flex: 1,
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 11,
                  color: "rgba(255,255,255,0.7)",
                  background: "rgba(255,255,255,0.04)",
                  padding: "10px 12px",
                  borderRadius: 6,
                  border: "1px solid var(--line, rgba(255,255,255,0.1))",
                  wordBreak: "break-all",
                }}
              >
                {data.login_url}
              </code>
              <button
                type="button"
                onClick={() => copy(data.login_url, "url")}
                style={pillBtnStyle()}
              >
                {copied === "url" ? "✓ Kopierad" : "Kopiera"}
              </button>
            </div>

            <div
              style={{
                display: "flex",
                gap: 8,
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <p
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontSize: 12.5,
                  color: "rgba(255,255,255,0.55)",
                  margin: 0,
                  flex: 1,
                  paddingRight: 12,
                }}
              >
                Eleven scannar QR-koden med mobilen för att logga in
                — eller skriver in koden manuellt på login-sidan.
              </p>
              <button
                type="button"
                onClick={printQr}
                style={{
                  ...pillBtnStyle(),
                  background: "var(--warm, #fbbf24)",
                  color: "#422006",
                  borderColor: "var(--warm, #fbbf24)",
                }}
              >
                Skriv ut
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function pillBtnStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
    color: "rgba(255,255,255,0.85)",
    fontFamily: "JetBrains Mono, monospace",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    padding: "8px 14px",
    borderRadius: 100,
    cursor: "pointer",
  };
}
