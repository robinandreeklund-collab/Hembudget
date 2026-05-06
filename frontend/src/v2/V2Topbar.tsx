/**
 * V2 Topbar · 1:1 med prototyp /proposals/vol-7/elev.html (.topbar).
 *
 * Element från prototypen (i ordning):
 * - .tb-brand "Ekonomilabbet · Forskning · 2026"
 * - .priv-badge "Privatekonomi" (eller .biz-badge "Sara A. AB · enskild firma")
 * - .level-badge l1/l2/l3 "Nivå 1 · Sparsam"
 * - .tb-crumbs (nuvarande sökväg)
 * - .tb-spacer
 * - .mode-switch (privat ↔ företag toggle med ms-track + ms-knob)
 * - .tb-meter (AI-tokens kvar idag · bar-visualisering)
 * - .tb-echo "Guide ✦" (öppnar GuideDropdown)
 * - .notif-bell (öppnar notif-drawer)
 * - .tb-echo "Echo" (öppnar Echo-drawer)
 * - .tb-user (initialer)
 * - .tb-logout
 *
 * Echo-drawer + notif-drawer renderas globalt via App.tsx — den här
 * komponenten triggar dem via window-events ("echo-open", "notif-open").
 */
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { GuideDropdown } from "./guides/GuideDropdown";
import { NotifBell } from "./NotifBell";
import { ClassPicker } from "./ClassPicker";
import "./topbar.css";
import "./v2-mode-flip.css";

type Status = { role: string; is_super_admin: boolean };

const ROUTE_TO_CRUMBS: Array<[RegExp, string[]]> = [
  // Elev-vyer
  [/^\/v2\/hub$/, ["Hubben"]],
  [/^\/v2\/banken$/, ["Hubben", "Banken"]],
  [/^\/v2\/arbetsgivaren$/, ["Hubben", "Arbetsgivaren"]],
  [/^\/v2\/skatten$/, ["Hubben", "Skatteverket"]],
  [/^\/v2\/lan$/, ["Hubben", "Lånegivaren"]],
  [/^\/v2\/avanza$/, ["Hubben", "Avanza"]],
  [/^\/v2\/forsakringar$/, ["Hubben", "Försäkringar"]],
  [/^\/v2\/forbrukning$/, ["Hubben", "Förbrukning"]],
  [/^\/v2\/hyresvarden$/, ["Hubben", "Boendemarknaden"]],
  [/^\/v2\/boendemarknad$/, ["Hubben", "Boendemarknaden"]],
  [/^\/v2\/arbetsformedlingen$/, ["Hubben", "Arbetsförmedlingen"]],
  [/^\/v2\/pension$/, ["Hubben", "Pension"]],
  [/^\/v2\/postladan/, ["Hubben", "Postlådan"]],
  [/^\/v2\/bokforing$/, ["Hubben", "Bokföring"]],
  [/^\/v2\/budget$/, ["Hubben", "Budget"]],
  [/^\/v2\/mal$/, ["Hubben", "Mål"]],
  [/^\/v2\/aktier$/, ["Hubben", "Aktier"]],
  [/^\/v2\/lanekalkylator$/, ["Hubben", "Lånekalkylator"]],
  [/^\/v2\/maria$/, ["Hubben", "Maria · lönesamtal"]],
  [/^\/v2\/bankid/, ["Hubben", "BankID"]],
  [/^\/v2\/uppdrag$/, ["Hubben", "Mina uppdrag"]],
  [/^\/v2\/portfolio$/, ["Hubben", "Portfolio"]],
  [/^\/v2\/kompetens\//, ["Hubben", "Portfolio", "Kompetens"]],
  [/^\/v2\/moduler$/, ["Hubben", "Mina moduler"]],
  [/^\/v2\/feedback$/, ["Hubben", "Lärar-feedback"]],
  [/^\/v2\/meddelanden$/, ["Hubben", "Meddelanden"]],
  [/^\/v2\/tx\//, ["Hubben", "Transaktion"]],
  [/^\/v2\/foretag$/, ["Hubben", "Företaget"]],
  [/^\/v2\/foretag\//, ["Hubben", "Företaget"]],
  // Lärar-vyer
  [/^\/teacher\/v2$/, ["Klassen"]],
  [/^\/teacher\/v2\/elev\//, ["Klassen", "Elev"]],
  [/^\/teacher\/v2\/historik\//, ["Klassen", "Elev", "Aktivitets-historik"]],
  [/^\/teacher\/v2\/portfolio\//, ["Klassen", "Elev", "Portfolio"]],
  [/^\/teacher\/v2\/kompetens\//, ["Klassen", "Elev", "Kompetens"]],
  [/^\/teacher\/v2\/uppdrag\//, ["Klassen", "Elev", "Uppdrag"]],
  [/^\/teacher\/v2\/feedback\//, ["Klassen", "Elev", "Feedback"]],
  [/^\/teacher\/v2\/messages\//, ["Klassen", "Elev", "Meddelanden"]],
  [/^\/teacher\/v2\/maria(\/|$)/, ["Klassen", "Maria-lista"]],
  [/^\/teacher\/v2\/reflektioner$/, ["Klassen", "Reflektioner"]],
  [/^\/teacher\/v2\/postlador$/, ["Klassen", "Postlådor"]],
  [/^\/teacher\/v2\/pedagogik$/, ["Klassen", "Pedagogik-paket"]],
  [/^\/teacher\/v2\/skapa$/, ["Klassen", "Skapa elev"]],
  [/^\/teacher\/v2\/klasser$/, ["Klassen", "Klasser"]],
  [/^\/teacher\/v2\/roster$/, ["Klassen", "Roster"]],
  [/^\/teacher\/v2\/foretag-klass$/, ["Klassen", "Företag-klass"]],
];

function getCrumbs(path: string): string[] {
  for (const [pattern, crumbs] of ROUTE_TO_CRUMBS) {
    if (pattern.test(path)) return crumbs;
  }
  return ["v2"];
}

function getInitials(role: string, displayName?: string): string {
  if (displayName) {
    const parts = displayName.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (role === "teacher") return "L";
  if (role === "demo") return "D";
  return "E";
}

const SPEND_LABEL: Record<string, string> = {
  sparsam: "Sparsam",
  balanserad: "Balanserad",
  slosa: "Slösa",
};

type Mode = "private" | "business";
const MODE_KEY = "hb_company_mode";
const MODE_EVENT = "company-mode-changed";

function readMode(): Mode {
  return (localStorage.getItem(MODE_KEY) as Mode) || "private";
}

function writeMode(m: Mode) {
  localStorage.setItem(MODE_KEY, m);
  document.body.setAttribute("data-mode", m);
  window.dispatchEvent(new CustomEvent(MODE_EVENT, { detail: { mode: m } }));
}

export function V2Topbar({ status }: { status: Status }) {
  const location = useLocation();
  const navigate = useNavigate();
  const crumbs = getCrumbs(location.pathname);
  const isTeacher = status.role === "teacher";
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mode, setMode] = useState<Mode>(readMode());
  const [tokens, setTokens] = useState<{ used: number; limit: number } | null>(
    null,
  );
  const [studentInfo, setStudentInfo] = useState<{
    name: string;
    level: number;
    spend: string;
    biz_company_name: string | null;
  } | null>(null);

  // Stäng mobil-menyn vid route-byte
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Sätt body data-mode vid mount
  useEffect(() => {
    document.body.setAttribute("data-mode", mode);
  }, [mode]);

  // Bug 12 · lyssna på globalt mode-byte (om annan komponent togglar)
  useEffect(() => {
    function onChange(e: Event) {
      const detail = (e as CustomEvent).detail || {};
      if (detail.mode === "private" || detail.mode === "business") {
        setMode(detail.mode);
      }
    }
    window.addEventListener(MODE_EVENT, onChange);
    return () => window.removeEventListener(MODE_EVENT, onChange);
  }, []);

  // Hämta AI-token-status (visas i meter)
  useEffect(() => {
    api<{
      ai_enabled: boolean;
      available: boolean;
      daily_quota: number;
      used_today: number;
      remaining_today: number;
    }>("/ai/chat/status")
      .then((r) => {
        if (r.ai_enabled && r.available && r.daily_quota > 0) {
          setTokens({ used: r.used_today, limit: r.daily_quota });
        }
      })
      .catch(() => undefined);
    // Poll var 30:e sek så meter:n hålls aktuell
    const t = setInterval(() => {
      api<{
        ai_enabled: boolean;
        available: boolean;
        daily_quota: number;
        used_today: number;
        remaining_today: number;
      }>("/ai/chat/status")
        .then((r) => {
          if (r.ai_enabled && r.available && r.daily_quota > 0) {
            setTokens({ used: r.used_today, limit: r.daily_quota });
          }
        })
        .catch(() => undefined);
    }, 30000);
    return () => clearInterval(t);
  }, []);

  // Hämta elevens karaktärs-info för level-badge + biz-badge
  useEffect(() => {
    if (isTeacher) {
      setStudentInfo(null);
      return;
    }
    Promise.all([
      api<{
        v2_level: number;
        v2_spend_profile: string;
      }>("/v2/status"),
      // Biz-summary · null om eleven inte har företag (fail-soft)
      api<{
        has_company: boolean;
        company_name: string | null;
        industry_label: string | null;
      }>("/v2/foretag/private-summary").catch(() => null),
    ])
      .then(([r, biz]) =>
        setStudentInfo({
          name: "",
          level: r.v2_level,
          spend: r.v2_spend_profile,
          biz_company_name:
            biz && biz.has_company ? biz.company_name : null,
        }),
      )
      .catch(() => setStudentInfo(null));
  }, [isTeacher]);

  function toggleMode() {
    const next: Mode = mode === "private" ? "business" : "private";
    const target = document.getElementById("v2-flip-target");

    // Reduced-motion-användare slipper rotation. Vi byter ändå
    // mode + navigerar.
    const reducedMotion = window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Steg 1 · flip-out (hela main-areen roterar bort)
    if (target && !reducedMotion) {
      target.classList.add("flip-out");
    }

    // Steg 2 · efter flip-out: byt mode + navigera till hub
    setTimeout(() => {
      writeMode(next);
      setMode(next);
      if (location.pathname !== "/v2/hub") {
        navigate("/v2/hub");
      }

      // Steg 3 · flip-in (hela main-areen roterar in)
      if (target && !reducedMotion) {
        target.classList.remove("flip-out");
        target.classList.add("flip-in");
        setTimeout(() => target.classList.remove("flip-in"), 550);
      }
    }, reducedMotion ? 0 : 460);
  }

  function handleEcho() {
    window.dispatchEvent(new Event("echo-open"));
  }

  // Tokens-meter % kvar
  const tokensPctRemaining =
    tokens && tokens.limit > 0
      ? Math.max(0, 1 - tokens.used / tokens.limit)
      : 0;
  const tokensRemaining =
    tokens && tokens.limit > 0 ? Math.max(0, tokens.limit - tokens.used) : 0;

  return (
    <header
      className={`v2-topbar${mobileOpen ? " v2-topbar-mobile-open" : ""}`}
      data-guide="hub-banner"
    >
      <Link to={isTeacher ? "/teacher/v2" : "/v2/hub"} className="tb-brand">
        Ekonomilabbet
        <span className="tb-brand-meta">Forskning · 2026</span>
        <span className="beta-pill" title="Plattformen är i beta">
          Beta
        </span>
      </Link>

      {/* Privat / Företag badge — visas exklusivt baserat på data-mode */}
      {!isTeacher && (
        <>
          <span className="priv-badge">
            Privatekonomi
            {studentInfo?.biz_company_name && (
              <em
                style={{
                  marginLeft: 8,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontStyle: "normal",
                  fontSize: 9,
                  color: "#c7d2fe",
                  letterSpacing: 0.6,
                }}
                title={`Driver också ${studentInfo.biz_company_name}`}
              >
                · ▦ biz aktivt
              </em>
            )}
          </span>
          <span className="biz-badge">
            {studentInfo?.biz_company_name || "Företag"}
          </span>
          {/* Level-badge — fast nivå-meta för eleven */}
          {studentInfo && (
            <span
              className={`level-badge l${studentInfo.level} priv-only`}
              title={`Nivå ${studentInfo.level} av 3 · ${SPEND_LABEL[studentInfo.spend] || ""}-profil`}
            >
              Nivå {studentInfo.level} · {SPEND_LABEL[studentInfo.spend] || ""}
            </span>
          )}
        </>
      )}

      {isTeacher && (
        <span className="tb-role is-teacher">Lärare</span>
      )}
      {status.is_super_admin && (
        <span className="tb-role is-admin">Super-admin</span>
      )}

      {/* Bug 7 · klass-väljare för läraren */}
      {isTeacher && <ClassPicker />}

      <nav className="tb-crumbs" aria-label="Sökväg">
        {crumbs.map((c, i) => (
          <span key={i}>
            {i > 0 && <span className="sep">/</span>}
            {i === crumbs.length - 1 ? <strong>{c}</strong> : <span>{c}</span>}
          </span>
        ))}
      </nav>

      <div className="tb-spacer" />

      <button
        type="button"
        className="tb-mobile-toggle"
        onClick={() => setMobileOpen((s) => !s)}
        aria-label="Öppna meny"
        aria-expanded={mobileOpen}
      >
        {mobileOpen ? "✕" : "☰"}
      </button>

      <div className="tb-actions">
        {/* Mode-switch · privat ↔ företag (bara för elev) */}
        {!isTeacher && (
          <button
            type="button"
            className="mode-switch"
            onClick={toggleMode}
            title="Byt mellan privat och företag"
          >
            <span className="ms-track">
              <span className="ms-knob" />
            </span>
            <span>
              {mode === "private" ? "Byt till företag" : "Byt till privat"}
            </span>
          </button>
        )}

        {/* AI-tokens-meter */}
        {tokens && (
          <div className="tb-meter" title="AI-tokens · resterande idag">
            <span>AI</span>
            <div className="tb-meter-bar">
              <div
                className="tb-meter-fill"
                style={{ width: `${(tokensPctRemaining * 100).toFixed(0)}%` }}
              />
            </div>
            <span>
              {tokens.limit > 0
                ? `${Math.round(tokensPctRemaining * 100)} % kvar`
                : `${tokensRemaining}/${tokens.limit}`}
            </span>
          </div>
        )}

        {/* Guide ✦ (sekundär stil) */}
        <GuideDropdown />

        {/* Notiser */}
        <NotifBell />

        {/* Echo (primär · varm-färg) */}
        <button
          type="button"
          className="tb-echo"
          onClick={handleEcho}
          aria-label="Öppna Echo-chatt"
        >
          Echo
        </button>

        <Link
          to={isTeacher ? "/teacher/v2" : "/v2/hub"}
          className="tb-user"
          aria-label="Hem"
        >
          {getInitials(status.role, studentInfo?.name)}
        </Link>
        <button
          type="button"
          className="tb-logout"
          onClick={handleLogout}
          aria-label="Logga ut"
          title="Logga ut"
        >
          Logga ut
        </button>
      </div>
    </header>
  );
}

async function handleLogout() {
  try {
    await fetch("/logout", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${sessionStorage.getItem("hembudget_token") || ""}`,
      },
    }).catch(() => undefined);
  } finally {
    sessionStorage.removeItem("hembudget_token");
    sessionStorage.removeItem("hembudget_role");
    sessionStorage.removeItem("hembudget_as_student");
    window.location.href = "/";
  }
}

// Bakåtkompat
export { V2Topbar as V2Banner };
