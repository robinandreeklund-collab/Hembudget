/**
 * Pentagon flip-card · klick på en axel flippar hela kortet och visar
 * detaljerade wellbeing-faktorer + senaste relevanta händelser.
 *
 * Speglar prototypens elev.html .pent-flip-stage → .pent-back.
 */
import { useEffect, useState } from "react";
import type { V2PentAxis, V2PentAxisDetail } from "./api";
import "./pent-flip.css";

type Props = {
  /** Funktion som hämtar detaljen — beroende på elev/lärar-vy. */
  fetchDetail: (axis: V2PentAxis) => Promise<V2PentAxisDetail>;
  /** Vilken axel är aktiv (null = front-side visas) */
  activeAxis: V2PentAxis | null;
  /** Callback när läraren stänger flip-kortet */
  onClose: () => void;
  /** Pentagon SVG + axis-tags som visas på fram-sidan */
  front: React.ReactNode;
};

export function PentagonFlipCard({
  fetchDetail, activeAxis, onClose, front,
}: Props) {
  const [detail, setDetail] = useState<V2PentAxisDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (activeAxis === null) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchDetail(activeAxis)
      .then(setDetail)
      .catch((e) => setError(String((e as Error)?.message || e)))
      .finally(() => setLoading(false));
  }, [activeAxis, fetchDetail]);

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
            aria-label="Stäng axel-detalj"
          >
            ← Tillbaka
          </button>
          {loading && (
            <div className="pent-back-loading">Laddar axel-detalj…</div>
          )}
          {error && (
            <div className="pent-back-loading" style={{ color: "#fca5a5" }}>
              Kunde inte ladda: {error}
            </div>
          )}
          {detail && !loading && !error && (
            <PentBack detail={detail} />
          )}
        </div>
      </div>
    </div>
  );
}

function PentBack({ detail }: { detail: V2PentAxisDetail }) {
  return (
    <>
      <div className="pent-back-eye">
        Axel {detail.axis_number} · {detail.axis_label} ·{" "}
        {detail.year_month}
      </div>
      <h2 className="pent-back-h">
        {detail.axis_label} <em>{detail.score}</em> av 100.
      </h2>
      <div className="pent-back-score">{detail.score}</div>
      <div className="pent-back-score-meta">
        Antal faktorer: <strong>{detail.factors.length}</strong> ·
        Antal händelser: <strong>{detail.events.length}</strong>
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
        {/* Vänster: faktorer + events */}
        <div className="pent-history">
          <div className="pent-history-head">
            Faktorer som bidrar nu (live)
          </div>
          {detail.factors.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga faktorer registrerade för {detail.axis_label.toLowerCase()}{" "}
              denna månad än.
            </div>
          ) : (
            detail.factors.map((f, i) => (
              <div className="pent-event" key={`f-${i}`}>
                <span className="pent-event-date">live</span>
                <div>
                  <div className="pent-event-name">{f.explanation}</div>
                  <div className="pent-event-meta">
                    Wellbeing-bidrag · auto-räknat
                  </div>
                </div>
                <span
                  className={`pent-event-delta ${
                    f.points > 0 ? "up" : f.points < 0 ? "down" : "flat"
                  }`}
                >
                  {f.delta_label}
                </span>
              </div>
            ))
          )}

          <div
            className="pent-history-head"
            style={{ marginTop: 4 }}
          >
            Beslut & händelser som påverkat
          </div>
          {detail.events.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga konkreta händelser registrerade än.
            </div>
          ) : (
            detail.events.map((ev, i) => (
              <div className="pent-event" key={`e-${i}`}>
                <span className="pent-event-date">{ev.date_label}</span>
                <div>
                  <div className="pent-event-name">{ev.title}</div>
                  {ev.detail && (
                    <div className="pent-event-meta">{ev.detail}</div>
                  )}
                </div>
                <span
                  className={`pent-event-delta ${
                    (ev.delta || 0) > 0
                      ? "up"
                      : (ev.delta || 0) < 0
                      ? "down"
                      : "flat"
                  }`}
                >
                  {ev.delta_label || "—"}
                </span>
              </div>
            ))
          )}
        </div>

        {/* Höger: pedagogik */}
        <aside>
          <div className="pent-side-card">
            <div className="pent-side-card-eye">Vad axeln mäter</div>
            <div className="pent-side-card-h">
              {axisDescription(detail.axis)}
            </div>
            <div className="pent-side-card-meta">
              {axisExplanationLong(detail.axis)}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

function axisDescription(axis: V2PentAxis): string {
  switch (axis) {
    case "economy":
      return "Saldo, sparkvot, skuld";
    case "safety":
      return "Karriär & framtidstrygghet";
    case "health":
      return "Vård, mat, sömn-implicit";
    case "social":
      return "Lärare, peer, partner";
    case "leisure":
      return "Fritid, nöje, restaurang";
  }
}

function axisExplanationLong(axis: V2PentAxis): string {
  switch (axis) {
    case "economy":
      return (
        "Mäter likviditet (saldo), sparmål-disciplin (avsatta belopp), "
        + "och hur skuldnivån utvecklas. Tippas av oväntade utgifter, "
        + "stora köp och försummade fakturor — höjs av sparande, "
        + "regelbunden lön och budget-disciplin."
      );
    case "safety":
      return (
        "Karriärs-tryggheten — kompetens-progression, lönesamtals-utfall, "
        + "modul-completion, klassningsgrad och kollektivavtal. "
        + "Höjs av lärar-bedömda kompetens-höjningar."
      );
    case "health":
      return (
        "Hälsa via signaler vi har data på: betalda vårdfakturor, "
        + "pensionssparande (långsiktig hälso-disciplin), reflektion "
        + "om mående, undvikande av alkohol-tunga köp."
      );
    case "social":
      return (
        "Relations-axeln — lärar-feedback (engagemang i dialog), peer-"
        + "review-ärenden, partner-interaktioner. "
        + "Sjunker av ohanterad dialog (5+ olästa feedback)."
      );
    case "leisure":
      return (
        "Fritid + balans — restaurang/nöje-utgifter, men också att man "
        + "INTE överdriver. Sjunker både vid 0 fritid (allt jobb) och "
        + "vid budget-överskridning på lyx."
      );
  }
}
