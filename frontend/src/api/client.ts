const TOKEN_KEY = "hembudget_token";
const PORT_KEY = "hembudget_api_port";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

function apiBase(): string {
  // In Tauri dev, the sidecar port is injected via env/localStorage at boot
  const port = localStorage.getItem(PORT_KEY) || import.meta.env.VITE_API_PORT || "8765";
  return `http://127.0.0.1:${port}`;
}

export function setApiPort(port: number | string): void {
  localStorage.setItem(PORT_KEY, String(port));
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${apiBase()}${path}`, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401 && token) {
      clearToken();
      window.location.reload();
    }
    let body: unknown = undefined;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, `HTTP ${res.status}: ${res.statusText}`, body);
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
  const res = await fetch(`${apiBase()}${path}`, { method: "POST", body: form, headers });
  if (!res.ok) {
    if (res.status === 401 && token) {
      clearToken();
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
