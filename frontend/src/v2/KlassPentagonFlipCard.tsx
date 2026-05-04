/**
 * Klass-pentagon flip-card · klick på en axel visar klassens
 * fördelning + top/bottom-bidragare på just den axeln.
 *
 * Skiljer sig från PentagonFlipCard (per-elev) genom att visa
 * lärar-relevant data: snitt, distribution, drar-upp/drar-ner-listor.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2PentAxis,
  type V2KlassAxisDetail,
} from "./api";
import "./pent-flip.css";

type Props = {
  activeAxis: V2PentAxis | null;
  onClose: () => void;
  front: React.ReactNode;
};

export function KlassPentagonFlipCard({
  activeAxis, onClose, front,
}: Props) {
  const [detail, setDetail] = useState<V2KlassAxisDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (activeAxis === null) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    v2Api
      .teacherKlassPentagonAxis(activeAxis)
      .then(setDetail)
      .catch((e) => setError(String((e as Error)?.message || e)))
      .finally(() => setLoading(false));
  }, [activeAxis]);

  const flipped = activeAxis !== null;

  return (
    <div className={`pent-flip-stage${flipped ? " is-flipped" : ""}`}>
      <div className="pent-flip-inner">
        <div className="pent-front">{front}</div>
        <div className={`pent-back${flipped ? " show" : ""}`}>
          <button
            type="button"
            className="pent-back-close"
            onClick={onClose}
          >
            ← Tillbaka till klassen
          </button>
          {loading && (
            <div className="pent-back-loading">Laddar axel-detalj…</div>
          )}
          {error && (
            <div className="pent-back-loading" style={{ color: "#fca5a5" }}>
              Kunde inte ladda: {error}
            </div>
          )}
          {detail && !loading && !error && <KlassBack detail={detail} />}
        </div>
      </div>
    </div>
  );
}

function KlassBack({ detail }: { detail: V2KlassAxisDetail }) {
  return (
    <>
      <div className="pent-back-eye">
        Axel {detail.axis_number} · {detail.axis_label} ·
        klassens fördelning
      </div>
      <h2 className="pent-back-h">
        {detail.axis_label}{" "}
        <em>{detail.klass_avg}</em> i snitt.
      </h2>
      <div className="pent-back-score">{detail.klass_avg}</div>
      <div className="pent-back-score-meta">
        Klass-snitt · <strong>{detail.student_count}</strong> elever ·
        klass-pentagon <strong>{detail.klass_total_avg}</strong>/100
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14.5,
          color: "rgba(255,255,255,0.85)",
          lineHeight: 1.55,
          marginBottom: 18,
        }}
      >
        {detail.summary_text}
      </p>

      <div className="pent-back-grid">
        <div className="pent-history">
          <div className="pent-history-head">
            Drar UPP snittet · top 3
          </div>
          {detail.top_contributors.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga elever att visa.
            </div>
          ) : (
            detail.top_contributors.map((row) => (
              <Link
                key={`top-${row.student_id}`}
                to={`/teacher/v2/elev/${row.student_id}`}
                className="pent-event"
                style={{ textDecoration: "none" }}
              >
                <span className="pent-event-date">
                  {row.axis_value}
                </span>
                <div>
                  <div className="pent-event-name">
                    {row.student_name}
                  </div>
                  <div className="pent-event-meta">
                    Pent {row.pent_total}/100
                  </div>
                </div>
                <span
                  className={`pent-event-delta ${
                    row.delta_from_avg > 0 ? "up" : row.delta_from_avg < 0 ? "down" : "flat"
                  }`}
                >
                  {row.delta_from_avg > 0 ? "+" : ""}
                  {row.delta_from_avg}
                </span>
              </Link>
            ))
          )}

          <div
            className="pent-history-head"
            style={{ marginTop: 4 }}
          >
            Drar NER snittet · 3 lägsta
          </div>
          {detail.bottom_contributors.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga elever att visa.
            </div>
          ) : (
            detail.bottom_contributors.map((row) => (
              <Link
                key={`bottom-${row.student_id}`}
                to={`/teacher/v2/elev/${row.student_id}`}
                className="pent-event"
                style={{ textDecoration: "none" }}
              >
                <span className="pent-event-date">
                  {row.axis_value}
                </span>
                <div>
                  <div className="pent-event-name">
                    {row.student_name}
                  </div>
                  <div className="pent-event-meta">
                    Pent {row.pent_total}/100
                  </div>
                </div>
                <span
                  className={`pent-event-delta ${
                    row.delta_from_avg > 0 ? "up" : row.delta_from_avg < 0 ? "down" : "flat"
                  }`}
                >
                  {row.delta_from_avg > 0 ? "+" : ""}
                  {row.delta_from_avg}
                </span>
              </Link>
            ))
          )}
        </div>

        <aside>
          <div className="pent-side-card">
            <div className="pent-side-card-eye">Distribution</div>
            <div className="pent-side-card-h">
              Hur klassen fördelas
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr",
                gap: 6,
                marginTop: 10,
              }}
            >
              {Object.entries(detail.distribution).map(([range, count]) => {
                const pct = detail.student_count > 0
                  ? Math.round((count / detail.student_count) * 100)
                  : 0;
                const color = range === "<40"
                  ? "#fca5a5"
                  : range === "40-59"
                  ? "var(--warm)"
                  : range === "60-79"
                  ? "#a5b4fc"
                  : "#6ee7b7";
                return (
                  <div
                    key={range}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "60px 1fr 50px",
                      gap: 8,
                      alignItems: "center",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.7)",
                    }}
                  >
                    <span style={{ color }}>{range}</span>
                    <div
                      style={{
                        height: 8,
                        background: "rgba(255,255,255,0.05)",
                        borderRadius: 100,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${pct}%`,
                          height: "100%",
                          background: color,
                          borderRadius: 100,
                        }}
                      />
                    </div>
                    <span style={{ textAlign: "right" }}>
                      {count} st
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div
            className="pent-side-card"
            style={{
              borderLeftColor: "#a5b4fc",
              marginTop: 10,
            }}
          >
            <div className="pent-side-card-eye" style={{ color: "#a5b4fc" }}>
              Tips till läraren
            </div>
            <div className="pent-side-card-h">
              {axisTeacherTip(detail.axis)}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

function axisTeacherTip(axis: V2PentAxis): string {
  switch (axis) {
    case "economy":
      return "Låg ekonomi-axel? Kör budget-modul + sparmål-uppdrag";
    case "safety":
      return "Karriär-axel sjunker när lönesamtals-modul ej startat";
    case "health":
      return "Hälsa-axel påverkas av oöppnade vårdfakturor";
    case "social":
      return "Social-axel · 5+ olästa lärar-feedback drar ner";
    case "leisure":
      return "Fritid-axel kan vara låg vid både 0 nöje OCH överskridning";
  }
}
