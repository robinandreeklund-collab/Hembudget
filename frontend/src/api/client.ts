const TOKEN_KEY = "hembudget_token";
const PORT_KEY = "hembudget_api_port";
const BASE_OVERRIDE_KEY = "hembudget_api_base_override";
const ROLE_KEY = "hembudget_role";
const AS_STUDENT_KEY = "hembudget_as_student";

export type Role = "teacher" | "student";

// === Auth-storage · localStorage istället för sessionStorage ===
//
// sessionStorage är PER FLIK · öppnar eleven en ny flik (eller följer
// en länk som öppnas i ny flik) försvinner token och fetchen får
// "Missing bearer token" → 401 → reload → utloggad. Det är samma
// underliggande orsak till den intermittenta utloggningen användaren
// rapporterade. localStorage är gemensam för alla flikar på samma
// origin och persistar även över browser-restart, vilket matchar
// användarens förväntning ("jag är fortfarande inloggad").
//
// Migrations-stöd: läs först från legacy sessionStorage så befintliga
// elev-sessioner inte tappas vid deploy. Skriv alltid till localStorage.

function readAuthValue(key: string): string | null {
  // 1. Ny canonical lagring · localStorage
  const fromLocal = localStorage.getItem(key);
  if (fromLocal !== null) return fromLocal;
  // 2. Legacy fallback · läs från sessionStorage och migrera
  const fromSession = sessionStorage.getItem(key);
  if (fromSession !== null) {
    localStorage.setItem(key, fromSession);
    sessionStorage.removeItem(key);
    return fromSession;
  }
  return null;
}

function writeAuthValue(key: string, value: string): void {
  localStorage.setItem(key, value);
  // Rensa legacy-värdet så inte stale data ligger kvar
  sessionStorage.removeItem(key);
}

function clearAuthValue(key: string): void {
  localStorage.removeItem(key);
  sessionStorage.removeItem(key);
}

export function getRole(): Role | null {
  const v = readAuthValue(ROLE_KEY);
  return v === "teacher" || v === "student" ? v : null;
}
export function setRole(role: Role): void {
  writeAuthValue(ROLE_KEY, role);
}
export function clearRole(): void {
  clearAuthValue(ROLE_KEY);
}

export function getAsStudent(): number | null {
  const v = readAuthValue(AS_STUDENT_KEY);
  return v ? parseInt(v, 10) : null;
}
export function setAsStudent(id: number | null): void {
  if (id === null) clearAuthValue(AS_STUDENT_KEY);
  else writeAuthValue(AS_STUDENT_KEY, String(id));
}

export function setApiBaseOverride(url: string | null): void {
  if (url) localStorage.setItem(BASE_OVERRIDE_KEY, url);
  else localStorage.removeItem(BASE_OVERRIDE_KEY);
}

export function getApiBaseOverride(): string | null {
  return localStorage.getItem(BASE_OVERRIDE_KEY);
}

export function getToken(): string | null {
  return readAuthValue(TOKEN_KEY);
}

export function setToken(token: string): void {
  writeAuthValue(TOKEN_KEY, token);
}

export function clearToken(): void {
  clearAuthValue(TOKEN_KEY);
}

function apiBase(): string {
  // 1. Runtime-override (satt av användaren via UI)
  const override = getApiBaseOverride();
  if (override) return override.replace(/\/$/, "");
  // 2. Build-time env (Render, Cloud Run m.fl.)
  let explicit = import.meta.env.VITE_API_BASE;
  if (explicit) {
    // "/" eller "SAME_ORIGIN" → servera API från samma host som
    // frontend (Cloud Run-deploy där en container har båda). Returnera
    // tom sträng så fetch använder browserns current origin automatiskt.
    if (explicit === "/" || explicit.toUpperCase() === "SAME_ORIGIN") {
      return "";
    }
    if (!/^https?:\/\//i.test(explicit)) explicit = `https://${explicit}`;
    return explicit.replace(/\/$/, "");
  }
  // 3. Tauri/lokal dev — använd current hostname så att om frontend öppnas
  // från ett annat LAN-device (http://192.168.1.x:1420) pekar API till
  // samma maskin (http://192.168.1.x:8765), inte klienternas 127.0.0.1.
  const port = localStorage.getItem(PORT_KEY) || import.meta.env.VITE_API_PORT || "8765";
  const hostname =
    typeof window !== "undefined" && window.location.hostname
      ? window.location.hostname
      : "127.0.0.1";
  return `http://${hostname}:${port}`;
}

export function getApiBase(): string {
  return apiBase();
}

export function setApiPort(port: number | string): void {
  localStorage.setItem(PORT_KEY, String(port));
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

export type ApiOptions = RequestInit & { turnstileToken?: string };

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { turnstileToken, ...restOptions } = options;
  const headers = new Headers(restOptions.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const asStudent = getAsStudent();
  if (asStudent) headers.set("X-As-Student", String(asStudent));
  if (turnstileToken) headers.set("X-Turnstile-Token", turnstileToken);

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, { ...restOptions, headers });
  } catch (err) {
    // Browser-nätverksfel (typisk "Failed to fetch"): kabelfel, backend
    // avstängd, CORS-preflight misslyckad eller tunnel nere. Ge
    // användaren ett tydligare meddelande som skiljer från HTTP-fel.
    throw new ApiError(
      0,
      `Kunde inte nå servern (${apiBase()}). Kolla att backend är igång ` +
        `och att nätverket fungerar. Tekniskt: ${String((err as Error).message ?? err)}`,
      undefined,
    );
  }
  if (!res.ok) {
    // 401 = ogiltig/utgången token → rensa allt + reload så användaren
    // tvingas logga in igen. 403 däremot är ETT NORMALFALL i
    // skolläget — t.ex. lärare som klickar på en student-endpoint via
    // impersonation, eller mutationer som inte tillåts utan student-
    // roll. Vi vill INTE logga ut på 403; UI:n får visa felmeddelandet
    // och låta användaren navigera tillbaka.
    if (res.status === 401 && token) {
      clearToken();
      clearRole();
      setAsStudent(null);
      window.location.reload();
    }
    let body: unknown = undefined;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    // FastAPI svarar med {detail: "..."} på HTTPException — visa den
    // texten i felmeddelandet så att UI kan visa den direkt för
    // användaren utan att behöva packa upp body manuellt.
    let detailMsg = "";
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      if (typeof d === "string") detailMsg = ` — ${d}`;
    }
    throw new ApiError(
      res.status,
      `HTTP ${res.status}: ${res.statusText}${detailMsg}`,
      body,
    );
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

export async function uploadFile<T = unknown>(
  path: string,
  form: FormData,
): Promise<T> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const asStudent = getAsStudent();
  if (asStudent) headers.set("X-As-Student", String(asStudent));
  const res = await fetch(`${apiBase()}${path}`, { method: "POST", body: form, headers });
  if (!res.ok) {
    // Bara 401 räknas som "logga ut", se kommentar i api() ovan.
    if (res.status === 401 && token) {
      clearToken();
      clearRole();
      setAsStudent(null);
      window.location.reload();
    }
    throw new ApiError(res.status, `HTTP ${res.status}: ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export function formatSEK(amount: number | string | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("sv-SE", {
    style: "currency",
    currency: "SEK",
    maximumFractionDigits: 0,
  });
}
