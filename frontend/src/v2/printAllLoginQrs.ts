/**
 * printAllLoginQrs · hämta alla elevers login-QR och öppna en
 * utskriftsfärdig sida med 4×N-grid (1 elev per cell).
 *
 * Används av "Skriv ut alla koder"-knappen i TeacherCreateStudentV2
 * och V2RosterPage.
 */
import { v2Api } from "./api";

export async function printAllLoginQrs(): Promise<{
  count: number;
  error?: string;
}> {
  let data: Awaited<ReturnType<typeof v2Api.teacherLoginQrBulk>>;
  try {
    data = await v2Api.teacherLoginQrBulk();
  } catch (e) {
    return { count: 0, error: String((e as Error)?.message || e) };
  }

  if (data.items.length === 0) {
    return {
      count: 0,
      error: "Inga elever att skriva ut. Skapa elever först.",
    };
  }

  const win = window.open("", "_blank", "noopener");
  if (!win) {
    return {
      count: 0,
      error: "Kunde inte öppna utskrifts-fönstret. Tillåt popup.",
    };
  }

  const today = new Date().toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const baseUrl = (data.items[0]?.login_url || "").split("?")[0];

  win.document.write(`<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="utf-8">
  <title>Login-koder · ${data.teacher_name} · ${today}</title>
  <style>
    @page { margin: 18mm; }
    body {
      font-family: Georgia, serif;
      margin: 0;
      padding: 24px;
      color: #111;
    }
    .header {
      text-align: center;
      margin-bottom: 22px;
      padding-bottom: 16px;
      border-bottom: 2px solid #111;
    }
    .header h1 { font-size: 22px; margin: 0 0 4px; }
    .header p { margin: 0; font-size: 12px; color: #555; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 18px;
    }
    .card {
      border: 2px dashed #111;
      border-radius: 8px;
      padding: 16px;
      page-break-inside: avoid;
      text-align: center;
    }
    .name {
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 8px;
    }
    .code {
      font-family: monospace;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 5px;
      margin: 8px 0;
      color: #d97706;
    }
    .qr-wrap { margin: 8px auto; max-width: 220px; }
    .qr-wrap svg { width: 100%; height: auto; display: block; }
    .url {
      font-family: monospace;
      font-size: 9.5px;
      color: #555;
      margin-top: 6px;
      word-break: break-all;
    }
    .instructions {
      font-size: 10px;
      color: #888;
      margin-top: 8px;
      font-style: italic;
    }
    @media print {
      body { padding: 0; }
      .header { margin-top: 0; }
      .no-print { display: none !important; }
    }
    .print-btn {
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #d97706;
      color: #fff;
      border: 0;
      padding: 12px 22px;
      border-radius: 6px;
      font-family: inherit;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>Login-koder · ${escapeHtml(data.teacher_name)}</h1>
    <p>${data.items.length} elever · genererat ${today} · ${escapeHtml(baseUrl)}</p>
  </div>
  <div class="grid">
    ${data.items.map(it => `
      <div class="card">
        <div class="name">${escapeHtml(it.student_name)}</div>
        <div class="code">${escapeHtml(it.login_code)}</div>
        <div class="qr-wrap">${it.qr_svg}</div>
        <div class="url">${escapeHtml(it.login_url)}</div>
        <div class="instructions">
          Skanna med kamera-appen eller skriv in koden på ${escapeHtml(baseUrl)}
        </div>
      </div>
    `).join("")}
  </div>
  <button class="print-btn no-print" onclick="window.print()">
    🖨 Skriv ut
  </button>
</body>
</html>`);

  win.document.close();
  win.focus();
  // Auto-trigger print-dialogue efter en kort delay (för säkerhet)
  win.setTimeout(() => {
    try { win.print(); } catch { /* ignore */ }
  }, 500);

  return { count: data.items.length };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
