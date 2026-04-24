import { useEffect, useRef } from "react";

type Props = {
  siteKey: string;
  onToken: (token: string) => void;
  onExpire?: () => void;
  /** "auto" = följer dark mode, "light" / "dark" tvingar. */
  theme?: "auto" | "light" | "dark";
};

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opts: {
          sitekey: string;
          callback: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
          theme?: string;
          size?: string;
        },
      ) => string;
      remove: (id: string) => void;
    };
  }
}

const SCRIPT_SRC =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let scriptPromise: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_SRC}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("turnstile-load-failed")));
      return;
    }
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("turnstile-load-failed"));
    document.head.appendChild(s);
  });
  return scriptPromise;
}

/** Cloudflare Turnstile "Smart CAPTCHA" — invisible för de flesta besökare,
 * interaktiv challenge om Cloudflare misstänker bot. Helt gratis och
 * respekterar privacy (ingen cookie/tracking till 3rdpart).
 *
 * Om siteKey är tom sträng → renderar inget. Användbart för lokalt dev
 * och desktop-läget där bot-skyddet är av. */
export function Turnstile({ siteKey, onToken, onExpire, theme = "auto" }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!siteKey || !hostRef.current) return;
    let cancelled = false;
    loadScript()
      .then(() => {
        if (cancelled || !window.turnstile || !hostRef.current) return;
        widgetIdRef.current = window.turnstile.render(hostRef.current, {
          sitekey: siteKey,
          callback: (token) => onToken(token),
          "expired-callback": () => onExpire?.(),
          theme,
          size: "flexible",
        });
      })
      .catch(() => {
        // Tyst — om Cloudflare-scriptet inte laddar visar vi bara ingen
        // widget. Backend gör fortfarande rate-limit-check.
      });
    return () => {
      cancelled = true;
      const id = widgetIdRef.current;
      if (id && window.turnstile) {
        try {
          window.turnstile.remove(id);
        } catch {
          /* ignore */
        }
      }
    };
  }, [siteKey]);

  if (!siteKey) return null;
  return <div ref={hostRef} className="my-2" />;
}
