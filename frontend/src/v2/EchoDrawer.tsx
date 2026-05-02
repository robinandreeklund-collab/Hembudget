/**
 * V2 Echo Drawer · 1:1 med prototyp /proposals/vol-7/elev.html (.drawer).
 *
 * Right-side drawer som öppnas när användaren klickar Echo-knappen i
 * topbaren. Lyssnar på "echo-open"-event på window. Inte en floating
 * FAB, inte en centrerad modal — exakt prototyp-design.
 */
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/api/client";

type Msg = {
  id: number;
  role: "user" | "echo";
  content: string;
};

type ChatStatus = {
  ai_enabled: boolean;
  available: boolean;
  daily_quota: number;
  used_today: number;
  remaining_today: number;
};

export function EchoDrawer() {
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState<boolean>(false);
  const [quota, setQuota] = useState<{ used: number; limit: number } | null>(
    null,
  );
  const [messages, setMessages] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const nextIdRef = useRef(1);

  // Lyssna på topbar-knappens event
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("echo-open", onOpen);
    return () => window.removeEventListener("echo-open", onOpen);
  }, []);

  // Hämta status (om AI är på + token-kvot)
  useEffect(() => {
    api<ChatStatus>("/ai/chat/status")
      .then((r) => {
        setAvailable(Boolean(r.ai_enabled && r.available));
        setQuota({ used: r.used_today, limit: r.daily_quota });
      })
      .catch(() => setAvailable(false));
  }, []);

  // Auto-fokus när drawer öppnas
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 350);
    }
  }, [open]);

  // Auto-scroll body
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTo({
        top: bodyRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages]);

  // ESC stänger
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function close() {
    setOpen(false);
  }

  async function send() {
    if (!q.trim() || busy) return;
    const question = q.trim();
    setQ("");
    setErr(null);
    const userId = nextIdRef.current++;
    const echoId = nextIdRef.current++;
    setMessages((m) => [
      ...m,
      { id: userId, role: "user", content: question },
      { id: echoId, role: "echo", content: "Tänker…" },
    ]);
    setBusy(true);
    try {
      const r = await api<{
        answer: string;
        used_today: number;
        remaining_today: number;
      }>("/ai/chat/send", {
        method: "POST",
        body: JSON.stringify({ content: question }),
      });
      setMessages((m) =>
        m.map((mm) =>
          mm.id === echoId ? { ...mm, content: r.answer } : mm,
        ),
      );
      setQuota((p) =>
        p ? { ...p, used: r.used_today } : p,
      );
    } catch (e) {
      const errMsg =
        e instanceof ApiError ? e.message : (e as Error).message;
      setErr(errMsg);
      setMessages((m) => m.filter((mm) => mm.id !== echoId));
    } finally {
      setBusy(false);
    }
  }

  if (!available) return null;

  const remaining =
    quota && quota.limit > 0 ? Math.max(0, quota.limit - quota.used) : null;

  return (
    <>
      <div
        className={`v2-drawer-scrim${open ? " on" : ""}`}
        onClick={close}
        aria-hidden={!open}
      />
      <aside
        className={`v2-echo-drawer${open ? " open" : ""}`}
        role="dialog"
        aria-label="Echo · sokratiskt stöd"
        aria-hidden={!open}
      >
        <header className="v2-echo-drawer-head">
          <div>
            <div className="v2-echo-drawer-eye">Echo · sokratiskt stöd</div>
            <div className="v2-echo-drawer-meta">
              Claude Haiku 4.5
              {remaining !== null && ` · ${remaining}/${quota!.limit} kvar idag`}
              {" · vet vad du tittar på"}
            </div>
          </div>
          <button
            className="v2-echo-drawer-close"
            onClick={close}
            aria-label="Stäng"
          >
            ×
          </button>
        </header>

        <div className="v2-echo-drawer-body" ref={bodyRef}>
          {messages.length === 0 ? (
            <div className="v2-echo-msg echo">
              "Hej. Echo ställer frågor — inte ger råd. Vad funderar du på?"
            </div>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`v2-echo-msg ${m.role}`}>
                {m.content}
              </div>
            ))
          )}
          {err && <div className="v2-echo-msg-error">{err}</div>}
        </div>

        <div className="v2-echo-drawer-foot">
          <input
            ref={inputRef}
            type="text"
            placeholder="Skriv till Echo…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                send();
              }
            }}
            disabled={busy}
          />
          <button onClick={send} disabled={busy || !q.trim()}>
            {busy ? "…" : "Skicka"}
          </button>
        </div>
      </aside>
    </>
  );
}
