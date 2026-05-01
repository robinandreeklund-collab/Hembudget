/**
 * Lärar-vy · komplett aktivitets-historik för en elev (motsv.
 * larare.html#p-historik).
 *
 * Routas via /teacher/v2/historik/:studentId.
 *
 * Visar:
 * - Header med signup-datum + dagar-aktiv + total events
 * - Filter: kind / period (klient-side) / sök / Exportera CSV
 * - 5 stat-kort (onboarding / transaktioner / modul-steg /
 *   reflektioner / BankID-signeringar)
 * - Komplett tidslinje grupperad på datum (idag / igår / vecka /
 *   månad / signup) med colored dots och kind-pills
 * - GDPR-card "Lärar-insyn · vad du har access till"
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  v2Api,
  type V2HistoryEvent,
  type V2HistoryEventKind,
  type V2HistoryResponse,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const KIND_LABELS: Record<V2HistoryEventKind, string> = {
  onboarding: "Onboarding",
  module_step: "Modul-steg",
  module_completed: "Modul klar",
  maria_round: "Maria-runda",
  bankid: "BankID",
  assignment: "Uppdrag",
  transaction: "Bokföring",
  budget: "Budget",
  loan: "Lån",
  transfer: "Överföring",
  import: "Import",
  competency_raised: "Kompetens",
  system: "System",
};

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const TIME_FMT = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleTimeString("sv-SE", {
    hour: "2-digit",
    minute: "2-digit",
  });
};

function dayBucket(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const eventDay = new Date(d);
  eventDay.setHours(0, 0, 0, 0);
  const diff = (today.getTime() - eventDay.getTime()) / 86400000;
  if (diff === 0) {
    return d
      .toLocaleDateString("sv-SE", {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
      .toUpperCase() + " · IDAG";
  }
  if (diff === 1) {
    return d
      .toLocaleDateString("sv-SE", {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
      .toUpperCase() + " · IGÅR";
  }
  if (diff < 7) {
    return d
      .toLocaleDateString("sv-SE", {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
      .toUpperCase();
  }
  if (diff < 30) {
    return `V${getISOWeek(d)} · ${d.toLocaleDateString("sv-SE", {
      day: "numeric",
      month: "long",
    })}`;
  }
  return d
    .toLocaleDateString("sv-SE", { month: "long", year: "numeric" })
    .toUpperCase();
}

function getISOWeek(d: Date): number {
  const target = new Date(d.valueOf());
  const dayNr = (d.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
  }
  return 1 + Math.ceil((firstThursday - target.valueOf()) / 604800000);
}

function eventsToCSV(events: V2HistoryEvent[]): string {
  const header = ["timestamp", "kind", "title", "detail"].join(";");
  const rows = events.map((e) =>
    [
      e.occurred_at,
      e.kind,
      `"${(e.title || "").replace(/"/g, '""')}"`,
      `"${(e.detail || "").replace(/"/g, '""')}"`,
    ].join(";"),
  );
  return [header, ...rows].join("\n");
}

export function TeacherStudentHistoryV2() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2HistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<"all" | V2HistoryEventKind>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherStudentHistory(sid, 200)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  const filteredEvents = useMemo(() => {
    if (!data) return [];
    let evs = data.events;
    if (kindFilter !== "all") {
      evs = evs.filter((e) => e.kind === kindFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      evs = evs.filter(
        (e) =>
          e.title.toLowerCase().includes(q)
          || (e.detail && e.detail.toLowerCase().includes(q)),
      );
    }
    return evs;
  }, [data, kindFilter, searchQuery]);

  const grouped = useMemo(() => {
    const buckets: { label: string; events: V2HistoryEvent[] }[] = [];
    for (const ev of filteredEvents) {
      const label = dayBucket(ev.occurred_at);
      const existing = buckets.find((b) => b.label === label);
      if (existing) {
        existing.events.push(ev);
      } else {
        buckets.push({ label, events: [ev] });
      }
    }
    return buckets;
  }, [filteredEvents]);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda historik
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar aktivitets-historik…</div>
      </div>
    );
  }

  function exportCSV() {
    const csv = eventsToCSV(filteredEvents);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `historik-${data?.student_name.replace(/\s/g, "_")}-${
      new Date().toISOString().split("T")[0]
    }.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/teacher/v2/elev/${sid}`);
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till {data.student_name}
        </a>

        <header className="larare-head">
          <div>
            <span className="pill">
              {data.student_name} · Aktivitets-historik · komplett insyn
            </span>
            <h1 className="larare-head-h1">
              Allt {data.student_name.split(" ")[0]} <em>gjort</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Onboarding · {data.stats.transactions_count} transaktioner ·{" "}
              {data.stats.reflections_count} reflektioner ·{" "}
              {data.stats.module_steps_count} modul-steg ·{" "}
              {data.stats.maria_rounds_count} lönesamtal-rundor · varje val
              sparat
            </p>
          </div>
          <div className="larare-head-meta">
            Sedan signup:{" "}
            <strong>{SHORT_DATE(data.signup_at)}</strong>
            <br />
            {data.stats.days_since_signup ?? "?"} dgr aktiv ·{" "}
            <strong>{data.events.length} events</strong>
            <br />
            Onboarding:{" "}
            {data.onboarding_completed_at ? (
              <strong style={{ color: "#6ee7b7" }}>
                klar {SHORT_DATE(data.onboarding_completed_at)}
              </strong>
            ) : (
              <strong style={{ color: "var(--warm)" }}>pågår</strong>
            )}
          </div>
        </header>

        {/* Filter-rad */}
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 22,
            padding: "14px 18px",
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line, rgba(255,255,255,0.1))",
            borderRadius: 6,
          }}
        >
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9.5,
              letterSpacing: 1,
              color: "rgba(255,255,255,0.6)",
              textTransform: "uppercase",
              alignSelf: "center",
            }}
          >
            Filter:
          </span>
          <select
            value={kindFilter}
            onChange={(e) =>
              setKindFilter(e.target.value as typeof kindFilter)
            }
            style={selectStyle()}
          >
            <option value="all">Alla typer</option>
            {Object.entries(KIND_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Sök händelse..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              ...selectStyle(),
              flex: 1,
              minWidth: 180,
            }}
          />
          <button
            type="button"
            onClick={exportCSV}
            style={{
              background: "var(--warm, #fbbf24)",
              color: "#422006",
              border: 0,
              padding: "7px 14px",
              borderRadius: 100,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9.5,
              fontWeight: 700,
              letterSpacing: 1.2,
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            Exportera CSV ({filteredEvents.length})
          </button>
        </div>

        {/* 5 stat-kort */}
        <div className="larare-stats">
          <div className="larare-stat">
            <div className="larare-stat-eye">Onboarding</div>
            <div className="larare-stat-num">
              {data.stats.onboarding_count > 0 ? "✓" : "—"}
            </div>
            <div className="larare-stat-sub">
              {data.onboarding_completed_at
                ? `klar ${SHORT_DATE(data.onboarding_completed_at)}`
                : "ej klar"}
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Transaktioner</div>
            <div className="larare-stat-num">
              <em>{data.stats.transactions_count}</em>
            </div>
            <div className="larare-stat-sub">i tidslinjen</div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Modul-steg</div>
            <div className="larare-stat-num">
              {data.stats.module_steps_count}
            </div>
            <div className="larare-stat-sub">klarade</div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Reflektioner</div>
            <div className="larare-stat-num">
              <em>{data.stats.reflections_count}</em>
            </div>
            <div className="larare-stat-sub">reflect-svar</div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">BankID-signeringar</div>
            <div className="larare-stat-num">
              {data.stats.bankid_count}
            </div>
            <div className="larare-stat-sub">slutförda sessioner</div>
          </div>
        </div>

        {/* Komplett tidslinje */}
        <div
          className="section-title"
          style={{ marginBottom: 14 }}
        >
          Komplett tidslinje · sortering nyast först ·{" "}
          {filteredEvents.length} events
        </div>

        <div
          style={{
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line, rgba(255,255,255,0.1))",
            borderRadius: 6,
            overflow: "hidden",
            marginBottom: 24,
          }}
        >
          {grouped.length === 0 ? (
            <div
              style={{
                padding: "20px 24px",
                fontFamily: "Source Serif 4, Georgia, serif",
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga events som matchar filtret.
            </div>
          ) : (
            grouped.map((bucket, i) => (
              <BucketGroup
                key={`${bucket.label}-${i}`}
                label={bucket.label}
                events={bucket.events}
                isFirst={i === 0}
              />
            ))
          )}
        </div>

        {/* GDPR-card */}
        <div
          className="s-card"
          style={{ background: "rgba(255,255,255,0.03)" }}
        >
          <div className="s-card-eye">
            Lärar-insyn · vad du har access till
          </div>
          <div className="s-card-h">
            Allt sparas · <em>inga undantag</em>
          </div>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: "12px 0 0",
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13.5,
              color: "rgba(255,255,255,0.6)",
            }}
          >
            <li>● {data.stats.transactions_count} transaktioner</li>
            <li>● {data.stats.reflections_count} reflektioner</li>
            <li>● {data.stats.maria_rounds_count} Maria-rundor</li>
            <li>● {data.stats.bankid_count} BankID-signeringar</li>
            <li>● {data.events.length} system-events totalt</li>
            <li>● {data.stats.module_steps_count} modul-steg klarade</li>
            <li>● Onboarding · alla beslut sparade</li>
            <li>● Pentagon-värden vecka för vecka</li>
            <li>● Karaktär · profil · partner-modell</li>
            <li>● Aktiehandel · varje köp/sälj</li>
            <li>● Lån-historik · CSN, ev. nya lån</li>
            <li>● Skattedeklarationer</li>
          </ul>
          <p
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              color: "rgba(255,255,255,0.4)",
              marginTop: 14,
              letterSpacing: 0.5,
            }}
          >
            GDPR-medvetenhet: eleven (och vårdnadshavare) har rätt att se
            exakt samma data. Du behöver inte be om lov — det är ett
            pedagogiskt verktyg, inte övervakning.
          </p>
        </div>
      </div>
    </div>
  );
}

function BucketGroup({
  label,
  events,
  isFirst,
}: {
  label: string;
  events: V2HistoryEvent[];
  isFirst: boolean;
}) {
  const isToday = label.includes("IDAG");
  const isOnboarding = label.toLowerCase().includes("jan");
  const headerBg = isFirst && isToday
    ? "rgba(220,76,43,0.08)"
    : isOnboarding
    ? "rgba(99,102,241,0.06)"
    : "rgba(255,255,255,0.03)";
  const headerColor = isFirst && isToday
    ? "var(--accent, #dc4c2b)"
    : isOnboarding
    ? "#c7d2fe"
    : "rgba(255,255,255,0.4)";
  return (
    <>
      <div
        style={{
          padding: "10px 18px",
          background: headerBg,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: 1.4,
          textTransform: "uppercase",
          color: headerColor,
          borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
        }}
      >
        ● {label} · {events.length} event{events.length === 1 ? "" : "s"}
      </div>
      {events.map((ev, i) => (
        <EventRow key={`${ev.kind}-${ev.source_id}-${i}`} event={ev} />
      ))}
    </>
  );
}

function EventRow({ event }: { event: V2HistoryEvent }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "90px 30px 1fr 110px",
        gap: 14,
        padding: "11px 18px",
        borderBottom: "1px solid var(--line, rgba(255,255,255,0.05))",
        alignItems: "center",
      }}
    >
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.5)",
        }}
      >
        {TIME_FMT(event.occurred_at)}
      </span>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: event.color,
          display: "inline-block",
        }}
      />
      <div>
        <div
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13.5,
            color: "#fff",
          }}
        >
          {event.title}
        </div>
        {event.detail && (
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9,
              color: "rgba(255,255,255,0.4)",
              marginTop: 2,
            }}
          >
            {event.detail}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          color: event.color,
          letterSpacing: 0.8,
          textAlign: "right",
        }}
      >
        {event.badge}
      </span>
    </div>
  );
}

function selectStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
    color: "#fff",
    padding: "7px 12px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 12,
  };
}
