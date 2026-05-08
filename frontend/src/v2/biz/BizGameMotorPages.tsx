/**
 * Företagsläget · spelmotor-vyer (deb/README.md fas 2-3).
 *
 * BizOfferter      · /v2/foretag/offerter (offertförfrågningar + ge offert)
 * BizJobb          · /v2/foretag/jobb (pågående + leverera)
 * BizMarknad       · /v2/foretag/marknad (marknadsföringskampanjer)
 * BizBeslut        · /v2/foretag/beslut (anställa/friskvård/leasing)
 * BizLeverantorer  · /v2/foretag/leverantorer (inkommande fakturor)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { ImpactPreviewBox } from "./TimeCapacityWidget";
import {
  bizEngineApi,
  type Decision,
  type Job,
  type MarketingCampaign,
  type Opportunity,
  type Quote,
  type SupplierInvoice,
} from "./api";
import { BizActorShell } from "./BizActorShell";
import "./biz.css";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


// === BIZ OFFERTER (matchar prototyp p-biz-kunder) ===

type StartupKitStatus = {
  has_base_equipment: boolean;
  has_car: boolean;
  requires_car: boolean;
  base_equipment_label: string;
  base_equipment_cost: number;
};

export function BizOfferter() {
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [kit, setKit] = useState<StartupKitStatus | null>(null);
  const [tick, setTick] = useState<import("./api").TickStatus | null>(null);
  const [nowTick, setNowTick] = useState(Date.now());
  // Pagination · 44 nya offertförfrågningar bara över natten gör listan
  // helt omöjlig att skrolla. Max 5 per sida.
  const NYA_PAGE_SIZE = 5;
  const [nyaPage, setNyaPage] = useState(0);

  function refresh() {
    bizEngineApi.listOpportunities(undefined)
      .then(setOpps)
      .catch((e) => setErr(String((e as Error).message || e)));
    // Hämta startup-kit-status så vi kan visa varför inga förfrågningar
    // dyker upp om bas-utrustning saknas
    api<StartupKitStatus>("/v2/foretag/growth/startup-kit")
      .then(setKit)
      .catch(() => undefined);
    bizEngineApi.tickStatus()
      .then(setTick)
      .catch(() => undefined);
  }

  useEffect(() => { refresh(); }, []);

  // Lokal tick-uppdatering var sekund så countdown rör sig. Var 60:e
  // tick refetchar vi tick-status från backend för att synka mot
  // verklig server-tid (annars driftar countdown om browser-klockan
  // är off eller om eleven öppnat fliken länge sedan).
  useEffect(() => {
    const id = window.setInterval(() => {
      setNowTick((n) => {
        const next = n + 1000;
        return next;
      });
    }, 1000);
    const refreshId = window.setInterval(() => {
      bizEngineApi.tickStatus().then(setTick).catch(() => undefined);
      // Re-fetch opps när vi just passerat next_tick_at + 5 s så vi
      // ser nya decisions direkt utan att eleven behöver F5:a.
      bizEngineApi.listOpportunities(undefined)
        .then(setOpps)
        .catch(() => undefined);
    }, 60000);
    return () => {
      window.clearInterval(id);
      window.clearInterval(refreshId);
    };
  }, []);

  const nextTickAt = tick ? new Date(tick.next_tick_at).getTime() : 0;
  const secondsUntilTick = nextTickAt > 0
    ? Math.max(0, Math.floor((nextTickAt - nowTick) / 1000))
    : 0;
  const tickH = Math.floor(secondsUntilTick / 3600);
  const tickM = Math.floor((secondsUntilTick % 3600) / 60);
  const tickS = secondsUntilTick % 60;
  const tickLabel = secondsUntilTick === 0
    ? "körs vid nästa sidladdning"
    : tickH > 0
      ? `${tickH} h ${tickM} min`
      : tickM > 0
        ? `${tickM} min ${tickS} s`
        : `${tickS} s`;

  // Pipelinen delas i tre sektioner enligt prototypen p-biz-kunder:
  //   - Aktiva uppdrag = "quoted" eller "won" (vi har lagt offert / vunnit)
  //   - Nya förfrågningar = "open" (väntar på offert)
  //   - Levererat = "lost" eller "expired" (avslutat)
  const activa = opps.filter((o) => o.status === "quoted" || o.status === "won");
  const nya = opps.filter((o) => o.status === "open");
  const klara = opps.filter((o) => o.status === "lost" || o.status === "expired");

  // Kalkylera vunnen-andel
  const totalDecided = opps.filter(
    (o) => o.status === "won" || o.status === "lost",
  ).length;
  const wonCount = opps.filter((o) => o.status === "won").length;
  const winPct = totalDecided > 0
    ? Math.round((wonCount / totalDecided) * 100) : null;

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Kunder & offerter"
      title={
        <>
          {nya.length > 0 ? (
            <>
              {opps.length === 0 ? "Inga" : activa.length} <em>kunder</em>,{" "}
              {nya.length} förfråga{nya.length === 1 ? "n" : "ningar"}.
            </>
          ) : (
            <>Pipelinen <em>just nu</em>.</>
          )}
        </>
      }
      subtitle="Pipelinen som driver omsättningen · ryktet ger fler offertförfrågningar"
      meta={
        <>
          Aktiva uppdrag: <strong>{activa.length}</strong>
          <br />
          Förfrågningar i kö: <strong>{nya.length}</strong>
          <br />
          Vunnen-andel:{" "}
          <strong>
            {winPct !== null ? `${winPct} %` : "—"}
          </strong>
        </>
      }
    >
      {err && <div className="biz-error">{err}</div>}

      {tick && tick.last_tick_status === "failed" && tick.last_tick_error && (
        <div style={{
          padding: "14px 18px",
          marginBottom: 16,
          background: "rgba(220,76,43,0.10)",
          border: "1px solid rgba(220,76,43,0.45)",
          borderLeft: "3px solid #dc4c2b",
          borderRadius: 8,
        }}>
          <div style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
            color: "#fda594", marginBottom: 6,
          }}>
            ⚠ TICK MISSLYCKADES · OFFERTER AVGÖRS INTE
          </div>
          <div style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13.5, color: "#fff", marginBottom: 4,
          }}>
            Senaste auto-tick kraschade. Därför ligger offerterna kvar.
          </div>
          <pre style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11.5,
            color: "#fda594",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
            lineHeight: 1.5,
          }}>{tick.last_tick_error}</pre>
        </div>
      )}

      {tick && (
        <div style={{
          padding: "12px 16px",
          marginBottom: 16,
          background: secondsUntilTick === 0
            ? "rgba(110,231,183,0.06)"
            : "rgba(99,102,241,0.06)",
          border: `1px solid ${secondsUntilTick === 0
            ? "rgba(110,231,183,0.25)"
            : "rgba(99,102,241,0.25)"}`,
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          gap: 14,
          flexWrap: "wrap",
        }}>
          <div style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
            color: secondsUntilTick === 0 ? "#6ee7b7" : "#c7d2fe",
          }}>
            ● BIZ-TICK
          </div>
          <div style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 14, color: "#fff",
          }}>
            {secondsUntilTick === 0 ? (
              <>Tick körs vid nästa sidladdning · {tick.open_quotes_count} offerter avgörs</>
            ) : (
              <>Nästa tick om <strong style={{
                color: "#fbbf24",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 13.5,
              }}>{tickLabel}</strong>
              {tick.open_quotes_count > 0 && (
                <> · {tick.open_quotes_count} offerter avgörs då</>
              )}
              </>
            )}
          </div>
          <span style={{ flex: 1 }} />
          <span style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9.5,
            color: "rgba(255,255,255,0.45)",
            letterSpacing: 0.6,
          }}>
            VECKA {tick.week_no} · 1 H = 1 BIZ-VECKA
          </span>
        </div>
      )}

      {kit && !kit.has_base_equipment && (
        <div style={{
          padding: "16px 18px",
          marginBottom: 20,
          background: "linear-gradient(135deg, rgba(220,76,43,0.08), rgba(15,21,37,0.55))",
          border: "1px solid rgba(220,76,43,0.40)",
          borderLeft: "3px solid #dc4c2b",
          borderRadius: 8,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700, letterSpacing: 1.4, color: "#fda594", marginBottom: 6 }}>
            ⚠ INGA FÖRFRÅGNINGAR · BAS-UTRUSTNING SAKNAS
          </div>
          <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14.5, color: "#fff", marginBottom: 6 }}>
            Kunderna ringer inte förrän du kan utföra jobbet.
          </div>
          <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "rgba(255,255,255,0.78)", margin: "0 0 12px", lineHeight: 1.55 }}>
            Du behöver <strong>{kit.base_equipment_label}</strong>
            {" "}({SEK(kit.base_equipment_cost)} kr) innan kunder hör av sig
            med offertförfrågningar. Köp via Tillväxt — du kan ta lån om
            kassan inte räcker.
          </p>
          <Link to="/v2/foretag/tillvaxt" style={{
            display: "inline-block",
            background: "#fbbf24",
            color: "#422006",
            padding: "8px 16px",
            borderRadius: 6,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
            textTransform: "uppercase", textDecoration: "none",
          }}>
            Öppna Tillväxt → köp bas-utrustning
          </Link>
        </div>
      )}

      {kit && kit.has_base_equipment && opps.length === 0 && !err && (
        <div style={{
          padding: "14px 16px",
          marginBottom: 20,
          background: "rgba(99,102,241,0.06)",
          border: "1px solid rgba(99,102,241,0.25)",
          borderRadius: 8,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe", marginBottom: 6 }}>
            ● VÄNTAR PÅ FÖRFRÅGNINGAR
          </div>
          <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "rgba(255,255,255,0.78)", margin: 0, lineHeight: 1.55 }}>
            Bas-utrustning ✓. Pipeline-motorn rullar 1 vecka per timme
            real-tid. Större rykte och marknadsföring → fler förfrågningar.
            {" "}<Link to="/v2/foretag/tillvaxt" style={{ color: "#fbbf24" }}>
              Köp ett marknadsförings-paket
            </Link>{" "}
            för en boost.
          </p>
        </div>
      )}

      <div className="act-grid">
        <div>
          {/* === Aktiva kunder & pågående jobb === */}
          <div className="section-eye" style={{ color: "#c7d2fe" }}>
            Aktiva kunder &amp; pågående jobb
          </div>
          {activa.length === 0 ? (
            <div className="biz-empty">
              Inga pågående uppdrag — när du vinner en offert hamnar den här.
            </div>
          ) : (
            <div className="biz-table-grid">
              <div
                className="biz-table-grid-row head"
                style={{
                  gridTemplateColumns:
                    "50px 1.6fr 1fr 100px 110px 100px",
                }}
              >
                <span>#</span>
                <span>Kund / Jobb</span>
                <span>Bransch</span>
                <span>Pris</span>
                <span>Deadline</span>
                <span>Status</span>
              </div>
              {activa.map((o, i) => (
                <a
                  key={o.id}
                  className="biz-table-grid-row"
                  href={o.status === "won" ? "/v2/foretag/jobb" : "#"}
                  onClick={(e) => {
                    // Vunnen offert · klicka leder till jobb-vyn med
                    // live-countdown istället för att öppna offert-modal
                    // igen. 'Skicka offert' är meningslöst för en vunnen
                    // affär.
                    if (o.status === "won") {
                      // Native nav (no preventDefault) → /v2/foretag/jobb
                      return;
                    }
                    e.preventDefault();
                    setEditing(o);
                  }}
                  style={{
                    gridTemplateColumns:
                      "50px 1.6fr 1fr 100px 110px 100px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.4)",
                    }}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: "Source Serif 4, Georgia, serif",
                        fontSize: 14.5,
                        fontWeight: 700,
                        color: "#fff",
                      }}
                    >
                      {o.customer_name}
                    </div>
                    <div
                      style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 9.5,
                        color: "rgba(255,255,255,0.4)",
                        marginTop: 2,
                        letterSpacing: 0.4,
                      }}
                    >
                      {o.title}
                    </div>
                  </div>
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.55)",
                    }}
                  >
                    {o.industry_tag || "Tjänst"}
                  </span>
                  <span
                    style={{
                      fontFamily: "Source Serif 4, Georgia, serif",
                      fontStyle: "italic",
                      color: "#c7d2fe",
                      fontWeight: 700,
                    }}
                  >
                    {SEK(o.market_price)} kr
                  </span>
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.55)",
                    }}
                  >
                    {o.expected_delivery_days} dgr
                  </span>
                  <div style={{
                    display: "flex", flexDirection: "column",
                    alignItems: "flex-end", gap: 4,
                  }}>
                    <span
                      className={`biz-status ${
                        o.status === "won" ? "paid" : "sent"
                      }`}
                      title={
                        o.status === "won"
                          ? "Klicka för att se progress på jobbet"
                          : "Du har lämnat offert · väntar på kundens beslut"
                      }
                    >
                      {o.status === "won" ? "Vunnen → jobb" : "Offert lämnad"}
                    </span>
                    {o.status === "quoted" && tick && (
                      <span style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 9,
                        color: secondsUntilTick === 0
                          ? "#6ee7b7"
                          : "rgba(255,255,255,0.5)",
                        letterSpacing: 0.6,
                      }}>
                        {secondsUntilTick === 0
                          ? "svar nu"
                          : `svar om ${tickLabel}`}
                      </span>
                    )}
                  </div>
                </a>
              ))}
            </div>
          )}

          {/* === Nya offertförfrågningar === */}
          {nya.length > 0 && (() => {
            const totalPages = Math.max(1, Math.ceil(nya.length / NYA_PAGE_SIZE));
            const safePage = Math.min(nyaPage, totalPages - 1);
            const start = safePage * NYA_PAGE_SIZE;
            const pageItems = nya.slice(start, start + NYA_PAGE_SIZE);
            return (
            <>
              <div
                className="section-eye"
                style={{ color: "#fbbf24", marginTop: 26 }}
              >
                {nya.length} {nya.length === 1
                  ? "ny offertförfrågan"
                  : "nya offertförfrågningar"}{" "}
                · väntar på din offert
                {totalPages > 1 && (
                  <span style={{ marginLeft: 12, color: "rgba(255,255,255,0.55)", fontSize: 10, letterSpacing: 0.6 }}>
                    visar {start + 1}–{Math.min(start + NYA_PAGE_SIZE, nya.length)} av {nya.length}
                  </span>
                )}
              </div>
              {/* Detaljerade offert-kort istället för en mager radlista —
               * eleven måste se VAD jobbet gäller (jobbeskrivning,
               * kundsegment, leveranstid) innan de kan skriva en
               * meningsfull pitch. Tidigare visades bara "Större projekt"
               * vilket var meningslöst. */}
              <div
                style={{
                  display: "grid",
                  gap: 12,
                  borderTop: "1px solid rgba(251,191,36,0.3)",
                  borderBottom: "1px solid rgba(251,191,36,0.3)",
                  paddingTop: 12,
                  paddingBottom: 12,
                }}
              >
                {pageItems.map((o) => (
                  <a
                    key={o.id}
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setEditing(o);
                    }}
                    style={{
                      display: "block",
                      padding: 16,
                      borderRadius: 8,
                      background: "rgba(251,191,36,0.04)",
                      border: "1px solid rgba(251,191,36,0.25)",
                      textDecoration: "none",
                      transition: "all 0.15s",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.background = "rgba(251,191,36,0.08)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.background = "rgba(251,191,36,0.04)";
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        gap: 12,
                        marginBottom: 6,
                      }}
                    >
                      <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                        <span
                          style={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: 9.5,
                            color: "#fbbf24",
                            fontWeight: 700,
                            letterSpacing: 1.4,
                          }}
                        >
                          NY · {(o.customer_segment || "privat").toUpperCase()}
                        </span>
                        {o.requires_car && (
                          <span style={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: 9, fontWeight: 700, letterSpacing: 1.2,
                            padding: "2px 6px", borderRadius: 4,
                            background: "rgba(220,76,43,0.18)",
                            border: "1px solid rgba(220,76,43,0.4)",
                            color: "#fda594",
                          }}>
                            🚗 KRÄVER BIL
                          </span>
                        )}
                        <span
                          style={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: 9,
                            color: "rgba(255,255,255,0.4)",
                            letterSpacing: 1.2,
                          }}
                        >
                          {o.industry_tag || "Tjänst"}
                        </span>
                      </div>
                      <span
                        style={{
                          fontFamily: "Source Serif 4, Georgia, serif",
                          fontStyle: "italic",
                          color: "#fbbf24",
                          fontWeight: 700,
                          fontSize: 14,
                        }}
                      >
                        {SEK(Math.round(o.market_price * 0.85))}–
                        {SEK(Math.round(o.market_price * 1.15))} kr
                      </span>
                    </div>
                    <div
                      style={{
                        fontFamily: "Source Serif 4, Georgia, serif",
                        fontSize: 16,
                        fontWeight: 700,
                        color: "#fff",
                        marginBottom: 4,
                      }}
                    >
                      {o.customer_name} <span style={{ color: "rgba(255,255,255,0.5)", fontWeight: 400 }}>· {o.title}</span>
                    </div>
                    {o.description && (
                      <div
                        style={{
                          fontFamily: "Inter, sans-serif",
                          fontSize: 13,
                          color: "rgba(255,255,255,0.78)",
                          lineHeight: 1.5,
                          marginTop: 6,
                          marginBottom: 8,
                        }}
                      >
                        {o.description}
                      </div>
                    )}
                    <div
                      style={{
                        display: "flex",
                        gap: 18,
                        marginTop: 8,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 10,
                        color: "rgba(255,255,255,0.55)",
                        letterSpacing: 0.6,
                      }}
                    >
                      <span>📅 Leverans inom <strong style={{ color: "#fff" }}>{o.expected_delivery_days} dagar</strong></span>
                      <span>⌛ Deadline {o.deadline_on}</span>
                      <span style={{ marginLeft: "auto", color: "#fbbf24", fontWeight: 700 }}>SKAPA OFFERT →</span>
                    </div>
                  </a>
                ))}
              </div>
              {totalPages > 1 && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  marginTop: 14, justifyContent: "center",
                  fontFamily: "JetBrains Mono, monospace", fontSize: 11,
                }}>
                  <button
                    onClick={() => setNyaPage(Math.max(0, safePage - 1))}
                    disabled={safePage === 0}
                    style={{
                      background: "transparent",
                      border: "1px solid rgba(255,255,255,0.18)",
                      color: safePage === 0 ? "rgba(255,255,255,0.3)" : "#c7d2fe",
                      padding: "6px 12px", borderRadius: 6,
                      cursor: safePage === 0 ? "default" : "pointer",
                      fontWeight: 700, letterSpacing: 1.2,
                    }}
                  >
                    ← FÖREGÅENDE
                  </button>
                  <span style={{ color: "rgba(255,255,255,0.55)", padding: "0 8px" }}>
                    Sida {safePage + 1} / {totalPages}
                  </span>
                  <button
                    onClick={() => setNyaPage(Math.min(totalPages - 1, safePage + 1))}
                    disabled={safePage >= totalPages - 1}
                    style={{
                      background: "transparent",
                      border: "1px solid rgba(255,255,255,0.18)",
                      color: safePage >= totalPages - 1 ? "rgba(255,255,255,0.3)" : "#c7d2fe",
                      padding: "6px 12px", borderRadius: 6,
                      cursor: safePage >= totalPages - 1 ? "default" : "pointer",
                      fontWeight: 700, letterSpacing: 1.2,
                    }}
                  >
                    NÄSTA →
                  </button>
                </div>
              )}
            </>
            );
          })()}

          {/* === Levererat / avslutat ===
           * Pedagogiskt kort istället för enrad — vid förlorad offert SKA
           * eleven se VARFÖR (decision_explanation från acceptance_model
           * + sin egen pris/leveranstid jämfört med riktpriset). Rött
           * "FÖRLORAD"-pill utan förklaring lärde inget. */}
          {klara.length > 0 && (
            <>
              <div className="section-eye" style={{ marginTop: 26 }}>
                Senaste avslutade
              </div>
              <div style={{ display: "grid", gap: 10 }}>
                {klara.slice(0, 5).map((o) => {
                  const isLost = o.status === "lost";
                  const isExpired = o.status === "expired";
                  return (
                    <div
                      key={o.id}
                      style={{
                        padding: 14,
                        borderRadius: 8,
                        background: isLost
                          ? "rgba(220,76,43,0.06)"
                          : "rgba(255,255,255,0.02)",
                        border: `1px solid ${isLost ? "rgba(220,76,43,0.25)" : "rgba(255,255,255,0.08)"}`,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          gap: 12,
                          alignItems: "baseline",
                          marginBottom: 4,
                        }}
                      >
                        <span
                          className={`biz-status ${isLost ? "overdue" : "draft"}`}
                          style={{ flexShrink: 0 }}
                        >
                          {isLost ? "Förlorad" : isExpired ? "Förfallen" : o.status}
                        </span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, fontWeight: 700, color: "#fff" }}>
                            {o.customer_name}
                            <span style={{ color: "rgba(255,255,255,0.5)", fontWeight: 400 }}> · {o.title}</span>
                          </div>
                        </div>
                        <span
                          style={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: 10,
                            color: "rgba(255,255,255,0.5)",
                          }}
                        >
                          v{o.week_no} · riktpris {SEK(o.market_price)} kr
                        </span>
                      </div>

                      {/* Visa elevens egen offert + förklaring vid förlust */}
                      {isLost && o.has_quote && (
                        <div style={{ marginTop: 10 }}>
                          <div
                            style={{
                              display: "flex",
                              gap: 18,
                              fontFamily: "JetBrains Mono, monospace",
                              fontSize: 10,
                              color: "rgba(255,255,255,0.65)",
                              letterSpacing: 0.5,
                              marginBottom: 8,
                            }}
                          >
                            <span>
                              Ditt pris:{" "}
                              <strong style={{ color: "#fda594" }}>
                                {o.quote_offered_price !== null ? SEK(o.quote_offered_price) + " kr" : "—"}
                              </strong>
                            </span>
                            <span>
                              Leveranstid:{" "}
                              <strong style={{ color: "#fff" }}>
                                {o.quote_offered_delivery_days ?? "—"} dagar
                              </strong>
                              {o.quote_offered_delivery_days !== null && o.expected_delivery_days
                                ? ` (kunden ville ${o.expected_delivery_days})`
                                : ""}
                            </span>
                            {o.quote_pitch_quality !== null && (
                              <span>
                                Pitch-kvalitet:{" "}
                                <strong style={{ color: "#fff" }}>
                                  {Math.round(o.quote_pitch_quality * 100)}%
                                </strong>
                              </span>
                            )}
                            {o.quote_accept_probability !== null && (
                              <span>
                                Chans till ja:{" "}
                                <strong style={{ color: "#fda594" }}>
                                  {Math.round(o.quote_accept_probability * 100)}%
                                </strong>
                              </span>
                            )}
                          </div>
                          {o.quote_decision_explanation && (
                            <div
                              style={{
                                fontFamily: "Source Serif 4, Georgia, serif",
                                fontSize: 13,
                                fontStyle: "italic",
                                color: "rgba(255,255,255,0.85)",
                                lineHeight: 1.55,
                                padding: "10px 12px",
                                background: "rgba(0,0,0,0.18)",
                                borderLeft: "2px solid #fda594",
                                borderRadius: 4,
                              }}
                            >
                              {o.quote_decision_explanation}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Förfallna har ingen quote · förklara att de aldrig
                       * lämnade offert i tid. */}
                      {isExpired && (
                        <div
                          style={{
                            marginTop: 8,
                            fontFamily: "Source Serif 4, Georgia, serif",
                            fontSize: 13,
                            fontStyle: "italic",
                            color: "rgba(255,255,255,0.6)",
                          }}
                        >
                          Du hann aldrig lämna offert innan kunden tröttnade och valde någon annan.
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {opps.length === 0 && (
            <div className="biz-empty">
              Inga offertförfrågningar än — pipeline-motorn drar in nya kunder
              över tid. Tittar du senare har det dykt upp fler.
            </div>
          )}
        </div>

        {/* === Aside · 4 side-cards (rykte / vunnen-andel / Echo / pipeline) === */}
        <aside>
          <div
            className="side-card"
            style={{ borderColor: "rgba(99,102,241,0.25)" }}
          >
            <div
              className="side-card-eye"
              style={{ color: "#c7d2fe" }}
            >
              Ryktet driver pipelinen
            </div>
            <div className="side-card-h">
              {wonCount > 0 ? wonCount * 8 + 50 : 50}{" "}
              <em style={{ color: "#c7d2fe" }}>av 100</em>
            </div>
            <div className="side-card-meta">
              {wonCount > 0
                ? `+ ${wonCount * 4} efter ${wonCount} vunna offerter. Ryktet ↑ → fler förfrågningar.`
                : "Vinn din första offert för att börja bygga ryktet."}
            </div>
            <div
              style={{
                marginTop: 14,
                height: 6,
                background: "rgba(255,255,255,0.06)",
                borderRadius: 100,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  background: "linear-gradient(90deg, #818cf8, #c7d2fe)",
                  width: `${Math.min(100, (wonCount > 0 ? wonCount * 8 + 50 : 50))}%`,
                  borderRadius: 100,
                }}
              />
            </div>
          </div>

          <div className="side-card">
            <div className="side-card-eye">Vunnen-andel</div>
            <div className="side-card-h">
              {winPct !== null ? `${winPct} %` : "—"}{" "}
              <em>
                ({wonCount} av {totalDecided})
              </em>
            </div>
            <div className="side-card-meta">
              {winPct !== null && winPct >= 50
                ? "Du ligger högt — kan höja priset något utan att förlora kunder."
                : winPct !== null
                ? "Branschen IT-tjänster har snitt 35 %. Sänkt pris eller bättre pitch."
                : "Lämna offerter för att räkna vunnen-andel."}
            </div>
          </div>

          {nya.length > 0 && (
            <div
              className="side-card"
              style={{
                background: "rgba(251,191,36,0.06)",
                borderColor: "rgba(251,191,36,0.25)",
              }}
            >
              <div
                className="side-card-eye"
                style={{ color: "#fbbf24" }}
              >
                Echo · taktiskt
              </div>
              <div className="side-card-h">
                Lämna pris i <em>mitten</em> av spannet
              </div>
              <div className="side-card-meta">
                Riktpris från Konsumentverkets schablon. Med {winPct ?? "—"} %
                vunnen-andel kan du gå mot mitten — ej alltid lägsta. Pitch-
                texten är minst lika viktig som priset.
              </div>
            </div>
          )}

          <div className="side-card">
            <div className="side-card-eye">AI-avgör för pipelinen</div>
            <div className="side-card-h">
              Branschmix bygger på din historik
            </div>
            <div className="side-card-meta">
              När du levererar tjänst med 4+ stjärnor → branschmix-vikt höjs.
              Pipeline-modellen genererar fler liknande förfrågningar nästa
              vecka.
            </div>
          </div>
        </aside>
      </div>

      {/* === Pedagogik === */}
      <div className="peda" style={{ marginTop: 26 }}>
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Pris är <em>förhandling</em>, inte gissning.
        </div>
        <p className="peda-prose">
          Riktpris från <strong>Konsumentverkets schablon</strong>. Du anpassar
          efter <em>kvalitet</em> (din historik), <em>komplexitet</em>
          (timmar du tror) och <em>marknad</em> (branschens vunnen-andel).
          Acceptansmodellen i appen räknar deterministiskt — eleven kan alltid
          få förklarat varför kunden tackat ja eller nej.
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>Riktpris</strong>Konsumentverkets schablon per bransch + ort.
          </li>
          <li>
            <strong>Pitch-faktor</strong>AI bedömer din offert-text som
            matchningsfaktor (0-1).
          </li>
          <li>
            <strong>Rykte</strong>Kvalitet av tidigare leveranser. Driver
            pipeline.
          </li>
          <li>
            <strong>Pipeline-vikt</strong>Branschmix bygger på din historik.
            Levererar du IT → fler IT-jobb.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">Riktpris</span>
          <span className="peda-concept">Vunnen-andel</span>
          <span className="peda-concept">Konvertering</span>
          <span className="peda-concept">Kundlivstidsvärde</span>
          <span className="peda-concept">Pipeline-mix</span>
        </div>
        <div className="peda-tip">
          Klicka "Skapa offert" på en NY-rad. Du får skriva en pitch (AI
          bedömer 0-1) + sätta pris. Sen avgör programmets acceptansmodell —
          inte LLM. Det är pedagogiskt avgörande: läraren kan alltid förklara
          varför.
        </div>
      </div>

      {editing && (
        <QuoteModal
          opp={editing}
          onClose={(refreshed) => {
            setEditing(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </BizActorShell>
  );
}


function QuoteModal({
  opp, onClose,
}: { opp: Opportunity; onClose: (refreshed: boolean) => void }) {
  // Vy-läge när eleven redan har lämnat offert: visa SUBMITTED värden
  // i stället för defaults så pris/dagar matchar det som faktiskt
  // skickades. Tidigare fyllde input-fälten alltid på market_price/
  // expected_delivery_days vilket gjorde att eleven trodde att deras
  // egna värden inte sparades.
  const isReadOnly = opp.has_quote;
  const initialPrice = (opp.has_quote && opp.quote_offered_price !== null)
    ? opp.quote_offered_price.toString()
    : opp.market_price.toString();
  const initialDays = (opp.has_quote && opp.quote_offered_delivery_days !== null)
    ? opp.quote_offered_delivery_days.toString()
    : opp.expected_delivery_days.toString();
  const initialPitch = (opp.has_quote && opp.quote_pitch_text) || "";

  const [price, setPrice] = useState(initialPrice);
  const [days, setDays] = useState(initialDays);
  const [pitch, setPitch] = useState(initialPitch);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<Quote | null>(null);
  const [impact, setImpact] = useState<import("./TimeCapacityWidget").ImpactPreview | null>(null);

  // Hämta tier-prediktion vid mount (bara om vi kan svara)
  useEffect(() => {
    if (isReadOnly) return;
    import("@/api/client").then(({ api }) =>
      api<import("./TimeCapacityWidget").ImpactPreview>(
        `/v2/foretag/capacity/preview-impact/${opp.id}`,
      ).then(setImpact).catch(() => undefined)
    );
  }, [opp.id, isReadOnly]);

  async function submit() {
    setErr(null);
    setSubmitting(true);
    try {
      const q = await bizEngineApi.submitQuote(opp.id, {
        offered_price: parseInt(price, 10),
        offered_delivery_days: parseInt(days, 10),
        pitch_text: pitch.trim() || undefined,
      });
      setResult(q);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(result !== null)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 540, width: "100%",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>
          {isReadOnly ? "Din offert · " : "Lämna offert · "}{opp.customer_name}
        </h2>
        {isReadOnly && (
          <div style={{
            padding: "10px 14px", marginBottom: 14,
            background:
              opp.status === "won"
                ? "rgba(110,231,183,0.08)"
                : opp.status === "lost"
                  ? "rgba(220,76,43,0.06)"
                  : "rgba(99,102,241,0.06)",
            border: `1px solid ${
              opp.status === "won"
                ? "rgba(110,231,183,0.30)"
                : opp.status === "lost"
                  ? "rgba(220,76,43,0.30)"
                  : "rgba(99,102,241,0.25)"
            }`,
            borderRadius: 6,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11, fontWeight: 700, letterSpacing: 1.4,
            color: opp.status === "won"
              ? "#6ee7b7"
              : opp.status === "lost"
                ? "#fda594"
                : "#c7d2fe",
          }}>
            {opp.status === "won"
              ? "✓ DU VANN · uppdraget är ett pågående jobb (öppna /v2/foretag/jobb)"
              : opp.status === "lost"
                ? "✗ DU FÖRLORADE · se motivering nedan"
                : "● VÄNTAR · kunden har inte beslutat än"}
          </div>
        )}
        {isReadOnly && opp.quote_decision_explanation && (
          <div style={{
            padding: "12px 14px", marginBottom: 14,
            background: "rgba(0,0,0,0.20)",
            borderLeft: `2px solid ${opp.status === "won" ? "#6ee7b7" : "#fda594"}`,
            borderRadius: 4,
            fontFamily: "Source Serif 4, Georgia, serif",
            fontStyle: "italic",
            fontSize: 13.5,
            color: "rgba(255,255,255,0.85)",
            lineHeight: 1.55,
          }}>
            {opp.quote_decision_explanation}
          </div>
        )}
        <div
          style={{
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.2)",
            borderRadius: 6,
            padding: "12px 14px",
            marginTop: 10,
          }}
        >
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9.5,
              color: "#818cf8",
              fontWeight: 700,
              letterSpacing: 1.4,
              marginBottom: 4,
            }}
          >
            UPPDRAGET · {(opp.customer_segment || "privat").toUpperCase()}
            {opp.industry_tag ? ` · ${opp.industry_tag.toUpperCase()}` : ""}
          </div>
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 14,
              fontWeight: 700,
              color: "#fff",
              marginBottom: 4,
            }}
          >
            {opp.title}
          </div>
          {opp.description && (
            <div
              style={{
                fontFamily: "Inter, sans-serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.85)",
                lineHeight: 1.55,
              }}
            >
              {opp.description}
            </div>
          )}
        </div>
        <p style={{ color: "#aab", fontSize: "0.85rem", marginTop: 14 }}>
          Riktpris{" "}
          <strong style={{ color: "#fbbf24" }}>{SEK(opp.market_price)} kr</strong>
          {" · "}förväntad leverans{" "}
          <strong style={{ color: "#fff" }}>{opp.expected_delivery_days} dagar</strong>
          {" · "}deadline {opp.deadline_on}
        </p>

        {impact && result === null && (
          <ImpactPreviewBox preview={impact} />
        )}

        {result === null ? (
          <>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              {isReadOnly ? "Pris du erbjöd" : "Ditt pris (kr exkl moms)"}
              <input
                type="number"
                value={price}
                onChange={e => setPrice(e.target.value)}
                style={{
                  ...inputStyle,
                  opacity: isReadOnly ? 0.7 : 1,
                  background: isReadOnly ? "rgba(255,255,255,0.04)" : (inputStyle as React.CSSProperties).background,
                }}
                readOnly={isReadOnly}
              />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              {isReadOnly ? "Leveranstid du erbjöd (dagar)" : "Leveranstid (dagar)"}
              <input
                type="number"
                value={days}
                onChange={e => setDays(e.target.value)}
                style={{
                  ...inputStyle,
                  opacity: isReadOnly ? 0.7 : 1,
                }}
                readOnly={isReadOnly}
              />
            </label>
            <label style={{ color: "white", display: "block", marginTop: 12 }}>
              {isReadOnly ? "Din pitch" : "Din pitch (frivilligt — höjer dina chanser)"}
              <textarea
                value={pitch}
                onChange={e => setPitch(e.target.value)}
                rows={4}
                placeholder={isReadOnly ? "Ingen pitch lämnad." : "Vad gör just er bra? Varför ska kunden välja er?"}
                style={{ ...inputStyle, fontFamily: "inherit", opacity: isReadOnly ? 0.7 : 1 }}
                readOnly={isReadOnly}
              />
            </label>
            {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              {!isReadOnly && (
                <button onClick={submit} disabled={submitting} style={btnPrimary}>
                  {submitting ? "Skickar…" : "Skicka offert"}
                </button>
              )}
              <button onClick={() => onClose(false)} style={btnGhost}>
                {isReadOnly ? "Stäng" : "Avbryt"}
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{
              padding: 14, borderRadius: 8,
              background: "rgba(34,197,94,0.1)",
              border: "1px solid rgba(34,197,94,0.3)",
              marginTop: 16,
            }}>
              <h3 style={{ color: "#6ee7b7", margin: "0 0 8px" }}>
                Offerten är skickad!
              </h3>
              <p style={{ color: "white", margin: 0, fontSize: "0.9rem" }}>
                Pris: <strong>{SEK(result.offered_price)} kr</strong> ·
                Leverans: <strong>{result.offered_delivery_days} dagar</strong>
              </p>
              {result.pitch_quality !== null && (
                <p style={{ color: "#aab", margin: "8px 0 0", fontSize: "0.85rem" }}>
                  AI-bedömd pitch-kvalitet:{" "}
                  <strong style={{ color: "white" }}>
                    {(result.pitch_quality * 100).toFixed(0)}%
                  </strong>
                </p>
              )}
              <p style={{
                color: "rgba(255,255,255,0.8)",
                margin: "12px 0 0", fontSize: "0.85rem",
              }}>
                Kunden bestämmer sig de närmaste timmarna · auto-motorn
                rullar fram veckorna i bakgrunden. Kolla in igen lite senare.
              </p>
            </div>
            <button
              onClick={() => onClose(true)}
              style={{ ...btnPrimary, marginTop: 16 }}
            >
              Klar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


// === BIZ JOBB ===

export function BizJobb() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [delivering, setDelivering] = useState<Job | null>(null);

  function refresh() {
    bizEngineApi.listJobs(filter || undefined)
      .then(setJobs)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); /* eslint-disable-line */ }, [filter]);

  const STATUS_LABEL: Record<string, string> = {
    in_progress: "Pågår",
    delivered: "Levererat",
    invoiced: "Fakturerat",
    paid: "Betalt",
    disputed: "Tvist",
  };
  const STATUS_COLOR: Record<string, string> = {
    in_progress: "#fbbf24",
    delivered: "#818cf8",
    invoiced: "#a78bfa",
    paid: "#6ee7b7",
    disputed: "#fda594",
  };

  return (
    <BizActorShell pillLabel="Aktör · biz · Pågående jobb" title={<>Leverera <em>med kvalitet</em>.</>} subtitle="Vunna offerter blir jobb · leverera och fakturera">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[
          ["", "Alla"], ["in_progress", "Pågår"], ["delivered", "Levererade"],
          ["paid", "Betalda"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            style={{
              padding: "6px 12px", borderRadius: 6,
              border: "1px solid rgba(99,102,241,0.3)",
              background: filter === v
                ? "rgba(99,102,241,0.25)" : "transparent",
              color: "#c7d2fe", cursor: "pointer", fontSize: "0.85rem",
            }}
          >{l}</button>
        ))}
      </div>

      {jobs.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga jobb än. Vinn en offert först!
        </p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {jobs.map(j => (
            <JobCard
              key={j.id}
              job={j}
              statusLabel={STATUS_LABEL[j.status] || j.status}
              statusColor={STATUS_COLOR[j.status] || "white"}
              onDeliver={() => setDelivering(j)}
            />
          ))}
        </div>
      )}

      {delivering && (
        <DeliverModal
          job={delivering}
          onClose={(refreshed) => {
            setDelivering(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </BizActorShell>
  );
}


function JobCard({
  job, statusLabel, statusColor, onDeliver,
}: {
  job: Job;
  statusLabel: string;
  statusColor: string;
  onDeliver: () => void;
}) {
  // Live-tick · uppdatera progress var minut så timern syns rörlig.
  // Servern räknar progress_pct vid läsning, men UI:n vill kännas
  // levande så vi räknar om lokalt mellan API-anrop.
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (job.status !== "in_progress") return;
    const id = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(id);
  }, [job.status]);

  const startMs = new Date(job.started_on + "T08:00:00").getTime();
  const endMs = new Date(job.expected_complete_on + "T17:00:00").getTime();
  const totalMs = Math.max(1, endMs - startMs);
  const elapsedMs = Math.max(0, now - startMs);
  const livePct = job.status === "in_progress"
    ? Math.min(100, Math.round((elapsedMs / totalMs) * 100))
    : job.progress_pct;
  const remainingMs = endMs - now;
  const days = Math.floor(Math.abs(remainingMs) / 86_400_000);
  const hours = Math.floor((Math.abs(remainingMs) % 86_400_000) / 3_600_000);
  const isOverdueLive = job.status === "in_progress" && remainingMs < 0;

  const barColor = isOverdueLive
    ? "#dc4c2b"
    : livePct > 85 ? "#fbbf24" : "#6ee7b7";

  return (
    <div style={{
      padding: 16,
      borderRadius: 10,
      background: job.is_klass_pool
        ? "linear-gradient(135deg, rgba(251,191,36,0.08), rgba(15,21,37,0.55))"
        : "rgba(15,21,37,0.55)",
      border: `1px solid ${
        job.is_klass_pool
          ? "rgba(251,191,36,0.35)"
          : "rgba(99,102,241,0.15)"
      }`,
    }}>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
        {job.is_klass_pool && (
          <span style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9, fontWeight: 700, letterSpacing: 1.4,
            color: "#fbbf24",
            background: "rgba(251,191,36,0.18)",
            padding: "3px 8px", borderRadius: 4,
          }}>⭐ KLASS-POOL</span>
        )}
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
            {job.title}
          </div>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)", marginTop: 2 }}>
            {job.customer_name}
          </div>
        </div>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "#fbbf24", fontWeight: 700 }}>
          {SEK(job.agreed_price)} kr
        </span>
        <span style={{ color: statusColor, fontSize: 11, fontFamily: "JetBrains Mono, monospace", letterSpacing: 1 }}>
          {statusLabel.toUpperCase()}
        </span>
      </div>

      {job.status === "in_progress" && (
        <div style={{ marginTop: 14 }}>
          <div style={{
            display: "flex", gap: 14, fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, color: "rgba(255,255,255,0.65)", letterSpacing: 0.6,
            marginBottom: 6,
          }}>
            <span>⏱ {job.estimated_hours} h totalt · {job.hours_per_week} h/v</span>
            <span style={{ color: barColor, fontWeight: 700 }}>
              {isOverdueLive
                ? `⚠ FÖRSENAD ${days} d ${hours} h`
                : `${days} d ${hours} h kvar`}
            </span>
            <span style={{ marginLeft: "auto" }}>
              start {job.started_on} · deadline {job.expected_complete_on}
            </span>
          </div>
          <div style={{
            height: 8,
            background: "rgba(255,255,255,0.08)",
            borderRadius: 100,
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%",
              width: `${livePct}%`,
              background: barColor,
              transition: "width 0.5s",
            }} />
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
            <button onClick={onDeliver} style={btnPrimary}>
              Leverera + skapa kund + faktura →
            </button>
          </div>
        </div>
      )}

      {job.status !== "in_progress" && (
        <div style={{
          marginTop: 12,
          display: "flex", gap: 14, alignItems: "baseline",
          fontFamily: "JetBrains Mono, monospace", fontSize: 10,
          color: "rgba(255,255,255,0.55)",
        }}>
          {job.delivered_on && <span>levererat {job.delivered_on}</span>}
          {job.quality_score !== null && (
            <span>kvalitet <strong style={{ color: "#fff" }}>{job.quality_score}/100</strong></span>
          )}
          {job.invoice_id && (
            <span>
              · faktura skapad ·{" "}
              <a href="/v2/foretag/fakturor" style={{ color: "#fbbf24" }}>
                öppna /v2/foretag/fakturor →
              </a>
            </span>
          )}
        </div>
      )}
    </div>
  );
}


type QuizQ = {
  id: number;
  category: string;
  text: string;
  options: Array<{ key: string; text: string; level: string }>;
};

type QuizFeedback = {
  question_id: number;
  question_text: string;
  your_answer_level: "good" | "mid" | "bad";
  your_answer_text: string;
  best_answer_text: string;
  explanation: string;
};

const CATEGORY_LABEL: Record<string, string> = {
  kvalitet: "Kvalitet",
  kommunikation: "Kommunikation",
  tid: "Tidshantering",
  etik: "Etik",
  teknik: "Tekniskt omdöme",
};

function DeliverModal({
  job, onClose,
}: { job: Job; onClose: (refreshed: boolean) => void }) {
  const [questions, setQuestions] = useState<QuizQ[] | null>(null);
  // index över aktuell fråga (0/1/2)
  const [step, setStep] = useState(0);
  // Sparade svar per fråga · "good"/"mid"/"bad" baserat på vilken
  // option eleven valde (a/b/c i UI mappar till level via shuffled-options).
  const [answers, setAnswers] = useState<Array<"good" | "mid" | "bad" | null>>([null, null, null]);
  const [submitting, setSubmitting] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [done, setDone] = useState<{
    invoice_number: string | null;
    quality_score: number;
    feedback: QuizFeedback[];
  } | null>(null);

  // Hämta 3 frågor när modal öppnas
  useEffect(() => {
    bizEngineApi.getQualityQuiz(job.id)
      .then(r => setQuestions(r.questions as QuizQ[]))
      .catch(e => setLoadErr(String((e as Error).message || e)));
  }, [job.id]);

  function pickOption(level: "good" | "mid" | "bad") {
    setAnswers(prev => {
      const next = [...prev];
      next[step] = level;
      return next;
    });
    // Auto-avancera till nästa fråga eller till submit-läge
    if (step < 2) {
      setTimeout(() => setStep(s => s + 1), 200);
    }
  }

  async function submit() {
    if (answers.some(a => a === null)) return;
    setSubmitting(true);
    setSubmitErr(null);
    try {
      const r = await bizEngineApi.submitDeliveryQuiz(job.id, {
        answers: answers as Array<"good" | "mid" | "bad">,
        create_invoice: true,
      });
      setDone({
        invoice_number: r.invoice_number,
        quality_score: r.quality_score,
        feedback: r.feedback,
      });
    } catch (e) {
      setSubmitErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  const allAnswered = answers.every(a => a !== null);
  const currentQ = questions?.[step];

  return (
    <div
      onClick={() => onClose(done !== null)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
        overflowY: "auto",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 560, width: "100%",
          maxHeight: "90vh", overflowY: "auto",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>
          Leverera · {job.title}
        </h2>
        <p style={{ color: "#aab", fontSize: "0.85rem" }}>
          {job.customer_name} · {SEK(job.agreed_price)} kr
        </p>

        {done === null ? (
          <>
            {loadErr && (
              <div style={{ color: "#fda594", marginTop: 16 }}>
                Kunde inte hämta quiz: {loadErr}
              </div>
            )}
            {!questions && !loadErr && (
              <p style={{ color: "#aab", marginTop: 16 }}>Hämtar frågor…</p>
            )}
            {questions && currentQ && !allAnswered && (
              <>
                {/* Steg-indikator */}
                <div style={{
                  display: "flex", gap: 6, marginTop: 18, marginBottom: 14,
                }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{
                      flex: 1, height: 4, borderRadius: 2,
                      background: i <= step
                        ? (answers[i] !== null ? "#6ee7b7" : "#818cf8")
                        : "rgba(255,255,255,0.1)",
                    }} />
                  ))}
                </div>
                <div style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
                  color: "rgba(255,255,255,0.55)",
                  marginBottom: 8,
                }}>
                  FRÅGA {step + 1} AV 3 · {CATEGORY_LABEL[currentQ.category] || currentQ.category.toUpperCase()}
                </div>
                <p style={{
                  color: "white",
                  fontSize: "1rem",
                  fontFamily: "Source Serif 4, Georgia, serif",
                  lineHeight: 1.5,
                  marginTop: 0,
                }}>
                  {currentQ.text}
                </p>
                <div style={{
                  display: "flex", flexDirection: "column", gap: 10,
                  marginTop: 16,
                }}>
                  {currentQ.options.map(opt => (
                    <button
                      key={opt.key}
                      onClick={() => pickOption(opt.level as "good" | "mid" | "bad")}
                      style={{
                        textAlign: "left",
                        padding: "12px 14px",
                        borderRadius: 8,
                        border: "1px solid rgba(99,102,241,0.3)",
                        background: "rgba(99,102,241,0.05)",
                        color: "white",
                        fontSize: 14,
                        fontFamily: "Source Serif 4, Georgia, serif",
                        cursor: "pointer",
                        lineHeight: 1.5,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "rgba(99,102,241,0.15)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "rgba(99,102,241,0.05)";
                      }}
                    >
                      <span style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 11, fontWeight: 700,
                        color: "#fbbf24", marginRight: 10,
                      }}>{opt.key.toUpperCase()}.</span>
                      {opt.text}
                    </button>
                  ))}
                </div>
                {step > 0 && (
                  <button
                    onClick={() => setStep(s => s - 1)}
                    style={{
                      marginTop: 14,
                      background: "transparent",
                      border: "none",
                      color: "rgba(255,255,255,0.5)",
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    ← Tillbaka till fråga {step}
                  </button>
                )}
              </>
            )}
            {questions && allAnswered && (
              <>
                <div style={{
                  marginTop: 16, padding: 14,
                  background: "rgba(99,102,241,0.08)",
                  border: "1px solid rgba(99,102,241,0.3)",
                  borderRadius: 8,
                }}>
                  <div style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
                    color: "#c7d2fe", marginBottom: 8,
                  }}>
                    KLAR · 3 AV 3 BESVARADE
                  </div>
                  <p style={{
                    color: "white", fontSize: 13.5, margin: 0,
                    fontFamily: "Source Serif 4, Georgia, serif",
                  }}>
                    Tryck "Leverera" för att skicka. Kvalitets-poängen
                    räknas ut från dina svar och påverkar rykte +
                    chans till repetitionsorder. Du får en pedagogisk
                    förklaring efter leveransen.
                  </p>
                </div>
                {submitErr && (
                  <div style={{ color: "#fda594", marginTop: 12 }}>
                    {submitErr}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                  <button onClick={submit} disabled={submitting} style={btnPrimary}>
                    {submitting ? "Levererar…" : "Leverera + skapa faktura"}
                  </button>
                  <button
                    onClick={() => { setStep(0); setAnswers([null, null, null]); }}
                    style={btnGhost}
                  >
                    Ändra svar
                  </button>
                </div>
              </>
            )}
          </>
        ) : (
          <div>
            {/* Kvalitets-score · färgkod baserad på utfall */}
            <div style={{
              padding: 14, borderRadius: 8,
              background: done.quality_score >= 80
                ? "rgba(34,197,94,0.1)"
                : done.quality_score >= 50
                  ? "rgba(251,191,36,0.1)"
                  : "rgba(220,76,43,0.1)",
              border: `1px solid ${
                done.quality_score >= 80
                  ? "rgba(34,197,94,0.3)"
                  : done.quality_score >= 50
                    ? "rgba(251,191,36,0.3)"
                    : "rgba(220,76,43,0.3)"
              }`,
              marginTop: 16,
            }}>
              <div style={{
                display: "flex", alignItems: "baseline",
                justifyContent: "space-between", marginBottom: 8,
              }}>
                <h3 style={{
                  color: done.quality_score >= 80
                    ? "#6ee7b7"
                    : done.quality_score >= 50
                      ? "#fbbf24"
                      : "#fda594",
                  margin: 0,
                }}>
                  Levererat ✓
                </h3>
                <div style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 18, fontWeight: 700,
                  color: done.quality_score >= 80
                    ? "#6ee7b7"
                    : done.quality_score >= 50
                      ? "#fbbf24"
                      : "#fda594",
                }}>
                  {done.quality_score}/100
                </div>
              </div>
              <p style={{ color: "white", margin: 0, fontSize: "0.9rem" }}>
                Kunden <strong>{job.customer_name}</strong> är upplagd
                som ny kund i bolaget och faktura{" "}
                <strong>{done.invoice_number}</strong> är skickad.
              </p>
              <p style={{
                color: "rgba(255,255,255,0.7)",
                margin: "8px 0 0", fontSize: "0.85rem",
              }}>
                Kunden betalar inom 30 dagar. Du kan följa fakturan i{" "}
                <a href="/v2/foretag/fakturor" style={{ color: "#fbbf24" }}>
                  /v2/foretag/fakturor
                </a>.
              </p>
            </div>

            {/* Pedagogisk feedback per quiz-fråga */}
            <div style={{ marginTop: 18 }}>
              <div style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
                color: "rgba(255,255,255,0.55)",
                marginBottom: 10,
              }}>
                LÄRDOMAR FRÅN DENNA LEVERANS
              </div>
              {done.feedback.map((fb, i) => {
                const isGood = fb.your_answer_level === "good";
                const isBad = fb.your_answer_level === "bad";
                return (
                  <div key={fb.question_id} style={{
                    padding: 12, marginBottom: 10,
                    borderRadius: 6,
                    background: "rgba(255,255,255,0.03)",
                    borderLeft: `3px solid ${
                      isGood ? "#6ee7b7"
                      : isBad ? "#fda594"
                      : "#fbbf24"
                    }`,
                  }}>
                    <div style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9.5, fontWeight: 700,
                      color: "rgba(255,255,255,0.5)",
                      marginBottom: 4,
                    }}>
                      FRÅGA {i + 1} ·{" "}
                      {isGood ? "BRA SVAR"
                       : isBad ? "DÅLIGT SVAR"
                       : "OK SVAR"}
                    </div>
                    <div style={{
                      color: "white", fontSize: 13,
                      fontFamily: "Source Serif 4, Georgia, serif",
                      marginBottom: 6, lineHeight: 1.45,
                    }}>
                      {fb.question_text}
                    </div>
                    <div style={{
                      fontSize: 12,
                      color: "rgba(255,255,255,0.7)",
                      marginBottom: 4,
                    }}>
                      <strong style={{ color: "rgba(255,255,255,0.5)" }}>
                        Du valde:
                      </strong>{" "}
                      {fb.your_answer_text}
                    </div>
                    {!isGood && (
                      <div style={{
                        fontSize: 12,
                        color: "rgba(110,231,183,0.85)",
                        marginBottom: 6,
                      }}>
                        <strong style={{ color: "#6ee7b7" }}>
                          Bästa svar:
                        </strong>{" "}
                        {fb.best_answer_text}
                      </div>
                    )}
                    <div style={{
                      fontSize: 11.5,
                      color: "rgba(255,255,255,0.6)",
                      lineHeight: 1.5,
                      marginTop: 6,
                      paddingTop: 6,
                      borderTop: "1px dashed rgba(255,255,255,0.1)",
                    }}>
                      {fb.explanation}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <a
                href="/v2/foretag/fakturor"
                style={{ ...btnPrimary, textDecoration: "none" }}
              >
                Öppna fakturor →
              </a>
              <button onClick={() => onClose(true)} style={btnGhost}>
                Klar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// === BIZ MARKNAD ===

const MARKETING_KINDS = [
  { value: "social", label: "Sociala medier", base: 1500 },
  { value: "flygblad", label: "Flygblad", base: 2500 },
  { value: "google", label: "Google-annonser", base: 4000 },
  { value: "sponsring", label: "Sponsring", base: 6000 },
  { value: "event", label: "Event/mässa", base: 8000 },
];

export function BizMarknad() {
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  function refresh() {
    bizEngineApi.listMarketing()
      .then(setCampaigns)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  return (
    <BizActorShell pillLabel="Aktör · biz · Marknadsföring" title={<>Synas är <em>säljbart</em>.</>} subtitle="Kampanjer som höjer pipeline-vikten · AI bedömer copy">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <button onClick={() => setShowAdd(true)} style={{ ...btnPrimary, marginBottom: 16 }}>
        + Skapa kampanj
      </button>

      {campaigns.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga kampanjer än. Marknadsföring höjer pipeline-genereringen.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {campaigns.map(c => (
            <div
              key={c.id}
              style={{
                background: "rgba(15,21,37,0.6)",
                border: "1px solid rgba(99,102,241,0.18)",
                borderRadius: 10, padding: 16,
                opacity: c.active ? 1 : 0.6,
              }}
            >
              <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}>
                <div>
                  <div style={{
                    fontSize: "0.7rem",
                    fontFamily: "JetBrains Mono, monospace",
                    color: "#818cf8", letterSpacing: 1.2,
                    textTransform: "uppercase",
                  }}>
                    {MARKETING_KINDS.find(k => k.value === c.kind)?.label || c.kind}
                    {c.active && " · AKTIV"}
                  </div>
                  <h3 style={{ color: "white", margin: "4px 0 0" }}>
                    {c.title}
                  </h3>
                  <div style={{ color: "#aab", fontSize: "0.85rem" }}>
                    {c.started_on} → {c.ends_on} · {SEK(c.cost)} kr
                  </div>
                </div>
                {c.ai_quality_factor !== null && (
                  <div style={{
                    textAlign: "right",
                    fontSize: "0.85rem",
                  }}>
                    <div style={{ color: "#818cf8" }}>AI-kvalitet</div>
                    <div style={{
                      color: c.ai_quality_factor >= 1.2 ? "#6ee7b7"
                        : c.ai_quality_factor <= 0.8 ? "#fda594" : "white",
                      fontWeight: 700, fontSize: "1.1rem",
                    }}>
                      ×{c.ai_quality_factor.toFixed(2)}
                    </div>
                  </div>
                )}
              </div>
              {c.copy_text && (
                <p style={{
                  color: "rgba(255,255,255,0.7)",
                  fontSize: "0.85rem", margin: "8px 0 0",
                  fontStyle: "italic",
                }}>
                  "{c.copy_text}"
                </p>
              )}
              {c.ai_feedback && (
                <p style={{
                  color: "#a78bfa", fontSize: "0.8rem", margin: "8px 0 0",
                }}>
                  AI: {c.ai_feedback}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <MarketingModal onClose={(r) => {
          setShowAdd(false);
          if (r) refresh();
        }} />
      )}
    </BizActorShell>
  );
}


function MarketingModal({ onClose }: { onClose: (refreshed: boolean) => void }) {
  const [kind, setKind] = useState("social");
  const [title, setTitle] = useState("");
  const [copyText, setCopyText] = useState("");
  const [cost, setCost] = useState("1500");
  const [duration, setDuration] = useState("4");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const k = MARKETING_KINDS.find(x => x.value === kind);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      await bizEngineApi.createMarketing({
        kind,
        title,
        copy_text: copyText.trim() || undefined,
        cost: parseInt(cost, 10),
        duration_weeks: parseInt(duration, 10),
      });
      onClose(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(false)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 540, width: "100%",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>Skapa kampanj</h2>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Typ
          <select
            value={kind}
            onChange={e => {
              setKind(e.target.value);
              const k2 = MARKETING_KINDS.find(x => x.value === e.target.value);
              if (k2) setCost(k2.base.toString());
            }}
            style={inputStyle}
          >
            {MARKETING_KINDS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Rubrik
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="t.ex. Sommarkampanj 2026"
            style={inputStyle}
          />
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Copy / kampanjtext (AI-bedöms)
          <textarea
            value={copyText}
            onChange={e => setCopyText(e.target.value)}
            rows={4}
            placeholder="Skriv din reklamtext här. Konkret målgrupp + tydlig CTA = högre kvalitet."
            style={{ ...inputStyle, fontFamily: "inherit" }}
          />
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Budget (kr)
          <input
            type="number"
            value={cost}
            onChange={e => setCost(e.target.value)}
            style={inputStyle}
          />
          <div style={{ color: "#aab", fontSize: "0.75rem" }}>
            Förslag för {k?.label}: {SEK(k?.base || 1500)} kr
          </div>
        </label>

        <label style={{ color: "white", display: "block", marginTop: 12 }}>
          Varaktighet (veckor)
          <input
            type="number" min="1" max="12"
            value={duration}
            onChange={e => setDuration(e.target.value)}
            style={inputStyle}
          />
        </label>

        {err && <div style={{ color: "#fda594", marginTop: 8 }}>{err}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            onClick={submit}
            disabled={submitting || !title.trim()}
            style={btnPrimary}
          >
            {submitting ? "Skapar…" : "Starta kampanj"}
          </button>
          <button onClick={() => onClose(false)} style={btnGhost}>
            Avbryt
          </button>
        </div>
      </div>
    </div>
  );
}


// === BIZ BESLUT ===

const DECISION_TEMPLATES = [
  {
    kind: "hire_part_time",
    label: "Anställ deltid",
    monthly: 18000, oneTime: 0, capacity: 1, rep: 0,
    desc: "+1 leveranskapacitet, 18 000 kr/mån i lönekostnad.",
  },
  {
    kind: "wellness",
    label: "Friskvårdsbidrag",
    monthly: 500, oneTime: 0, capacity: 0, rep: 3,
    desc: "+3 rykte (medarbetarnöjdhet), 500 kr/mån.",
  },
  {
    kind: "car_lease",
    label: "Leasa bil",
    monthly: 4500, oneTime: 5000, capacity: 0, rep: 0,
    desc: "Låser upp körnings-jobb. 4 500 kr/mån + 5 000 kr engångs.",
  },
  {
    kind: "insurance",
    label: "Företagsförsäkring",
    monthly: 800, oneTime: 0, capacity: 0, rep: 0,
    desc: "Skyddar mot slumpevent (-90 % skada). 800 kr/mån.",
    insurance_kind: "egendom",
  },
  {
    kind: "new_office",
    label: "Större lokal",
    monthly: 8000, oneTime: 12000, capacity: 1, rep: 5,
    desc: "+5 rykte + 1 kapacitet. 8 000 kr/mån + 12 000 engångs.",
  },
];

export function BizBeslut() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);

  function refresh() {
    bizEngineApi.listDecisions()
      .then(setDecisions)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  return (
    <BizActorShell pillLabel="Verktyg · biz · Beslut" title={<>Strategiska <em>val</em>.</>} subtitle="Anställa · friskvård · leasing · försäkring">
      {err && <div style={{ color: "#fda594" }}>{err}</div>}
      <button onClick={() => setPicking(true)} style={{ ...btnPrimary, marginBottom: 16 }}>
        + Nytt beslut
      </button>

      {decisions.length === 0 ? (
        <p style={{ color: "rgba(255,255,255,0.5)" }}>
          Inga beslut än. Anställa, friskvård, leasing, försäkring eller ny
          lokal — varje val påverkar spelmotorn.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {decisions.map(d => (
            <DecisionCard
              key={d.id}
              decision={d}
              onEnd={async () => {
                if (confirm("Avsluta detta beslut?")) {
                  await bizEngineApi.endDecision(d.id);
                  refresh();
                }
              }}
            />
          ))}
        </div>
      )}

      {picking && (
        <DecisionPicker onClose={(r) => {
          setPicking(false);
          if (r) refresh();
        }} />
      )}
    </BizActorShell>
  );
}


function DecisionCard({
  decision, onEnd,
}: { decision: Decision; onEnd: () => void }) {
  const tmpl = DECISION_TEMPLATES.find(t => t.kind === decision.kind);
  return (
    <div
      style={{
        background: "rgba(15,21,37,0.6)",
        border: "1px solid rgba(99,102,241,0.18)",
        borderRadius: 10, padding: 16,
        opacity: decision.active ? 1 : 0.5,
      }}
    >
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
      }}>
        <div>
          <div style={{
            fontSize: "0.7rem",
            fontFamily: "JetBrains Mono, monospace",
            color: "#818cf8", letterSpacing: 1.2,
            textTransform: "uppercase",
          }}>
            {tmpl?.label || decision.kind}{decision.active && " · AKTIVT"}
          </div>
          <h3 style={{ color: "white", margin: "4px 0 0" }}>
            {decision.title}
          </h3>
          <div style={{ color: "#aab", fontSize: "0.85rem", marginTop: 4 }}>
            Sedan {decision.started_on}
            {decision.ends_on && ` → ${decision.ends_on}`}
            {" · "}
            {decision.monthly_cost > 0 && `${SEK(decision.monthly_cost)} kr/mån `}
            {decision.capacity_delta !== 0 &&
              `· kapacitet ${decision.capacity_delta > 0 ? "+" : ""}${decision.capacity_delta} `}
            {decision.reputation_delta !== 0 &&
              `· rykte ${decision.reputation_delta > 0 ? "+" : ""}${decision.reputation_delta}`}
          </div>
        </div>
        {decision.active && (
          <button onClick={onEnd} style={btnDanger}>
            Avsluta
          </button>
        )}
      </div>
    </div>
  );
}


function DecisionPicker({ onClose }: { onClose: (refreshed: boolean) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function pick(t: typeof DECISION_TEMPLATES[number]) {
    setSubmitting(true);
    setErr(null);
    try {
      await bizEngineApi.createDecision({
        kind: t.kind,
        title: t.label,
        monthly_cost: t.monthly,
        one_time_cost: t.oneTime,
        capacity_delta: t.capacity,
        reputation_delta: t.rep,
        insurance_kind: (t as { insurance_kind?: string }).insurance_kind,
      });
      onClose(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
      setSubmitting(false);
    }
  }

  return (
    <div
      onClick={() => onClose(false)}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.7)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(99,102,241,0.4)",
          borderRadius: 12, padding: 24, maxWidth: 600, width: "100%",
          maxHeight: "85vh", overflowY: "auto",
        }}
      >
        <h2 style={{ color: "white", marginTop: 0 }}>Välj beslut</h2>

        {err && <div style={{ color: "#fda594", marginBottom: 8 }}>{err}</div>}

        <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
          {DECISION_TEMPLATES.map(t => (
            <button
              key={t.kind}
              onClick={() => pick(t)}
              disabled={submitting}
              style={{
                background: "rgba(99,102,241,0.08)",
                border: "1px solid rgba(99,102,241,0.3)",
                borderRadius: 8, padding: 14,
                color: "white", textAlign: "left",
                cursor: submitting ? "not-allowed" : "pointer",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>{t.label}</div>
              <div style={{ color: "#aab", fontSize: "0.85rem", marginTop: 4 }}>
                {t.desc}
              </div>
            </button>
          ))}
        </div>

        <button
          onClick={() => onClose(false)}
          style={{ ...btnGhost, marginTop: 16 }}
        >
          Avbryt
        </button>
      </div>
    </div>
  );
}


// === BIZ LEVERANTÖRER ===

export function BizLeverantorer() {
  const [invoices, setInvoices] = useState<SupplierInvoice[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [paying, setPaying] = useState<number | null>(null);

  function refresh() {
    bizEngineApi.listSupplierInvoices(undefined)
      .then(setInvoices)
      .catch((e) => setErr(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  async function pay(id: number) {
    setPaying(id);
    try {
      await bizEngineApi.paySupplierInvoice(id);
      refresh();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setPaying(null);
    }
  }

  // Föreslå BAS-konton baserat på leverantörens beskrivning. Pedagogiskt:
  // ungefär samma kategoriserings-mönster som prototypen rad 5860-5910.
  function basAccountsFor(si: SupplierInvoice): string {
    const lower = `${si.sender_name} ${si.description}`.toLowerCase();
    if (lower.includes("bolagsverket") || lower.includes("avgift") || lower.includes("anders lind"))
      return "6991 Övriga avgifter";
    if (lower.includes("möbler") || lower.includes("skrivbord") || lower.includes("dator"))
      return "1220 Inventarier (avskr 5 år)";
    if (lower.includes("hyra") || lower.includes("lokal"))
      return "5010 Lokalhyra / 2641 Moms in";
    if (lower.includes("loopia") || lower.includes("webb") || lower.includes("hosting"))
      return "5610 Datakostn / 2641 Moms in";
    if (lower.includes("adobe") || lower.includes("bokio") || lower.includes("software"))
      return "5610 / 2641 (auto-bokad)";
    return "5610 / 2641 (förslag)";
  }

  // is_overdue räknas backend-side mot SPEL-tid · använd INTE
  // new Date() (= real-tid maj medan eleven är på spel-januari).
  const open = invoices.filter((i) => i.status === "open");
  const paid = invoices.filter((i) => i.status === "paid");
  const overdue = open.filter((i) => i.is_overdue);
  const dueThisWeek = open
    .reduce((acc, i) => acc + i.amount_excl_vat, 0);
  const vatThisWeek = Math.round(dueThisWeek * 0.20); // 25 % moms av 1.25-multipel

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Leverantörer"
      title={<>Inkommande <em>fakturor</em>.</>}
      subtitle={
        invoices.length === 0
          ? "Inga leverantörsfakturor än"
          : `${open.length} oöppnade · ${paid.length} bokförda${
              overdue.length > 0 ? ` · ${overdue.length} förfallna` : ""
            }`
      }
      meta={
        <>
          Att betala denna v: <strong>{SEK(dueThisWeek)} kr</strong>
          <br />
          Avdragsgill moms: <strong>{SEK(vatThisWeek)} kr</strong>
          <br />
          Ohanterade: <strong>{open.length}</strong>
        </>
      }
    >
      {err && <div className="biz-error">{err}</div>}

      <div className="section-eye" style={{ color: "#c7d2fe" }}>
        Leverantörsfakturor
      </div>
      {invoices.length === 0 ? (
        <div className="biz-empty">
          Inga leverantörsfakturor just nu. Allt är betalt eller så har
          läraren inte skickat ut några än · auto-motorn drar in nya
          över tid.
        </div>
      ) : (
        <div className="biz-table-grid">
          <div
            className="biz-table-grid-row head"
            style={{
              gridTemplateColumns:
                "36px 60px 1.6fr 1.2fr 100px 100px 80px",
            }}
          >
            <span></span>
            <span>#</span>
            <span>Leverantör / vad</span>
            <span>Bokföringsförslag</span>
            <span>Belopp</span>
            <span>Status</span>
            <span></span>
          </div>
          {invoices.map((si) => {
            const isOverdue = si.status === "open" && si.is_overdue;
            const isOpen = si.status === "open";
            const fromTeacher = si.source === "teacher";
            return (
              <div
                key={si.id}
                className={`biz-table-grid-row${isOverdue || (isOpen && fromTeacher) ? " alert" : ""}`}
                style={{
                  gridTemplateColumns:
                    "36px 60px 1.6fr 1.2fr 100px 100px 80px",
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: isOpen ? "#dc4c2b" : "transparent",
                    margin: "0 auto",
                  }}
                />
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: isOpen ? "#dc4c2b" : "rgba(255,255,255,0.4)",
                  }}
                >
                  L{String(si.id).padStart(3, "0")}
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: "Source Serif 4, Georgia, serif",
                      fontSize: 14,
                      color: "#fff",
                      fontWeight: 700,
                    }}
                  >
                    {si.sender_name}
                    {fromTeacher && (
                      <em
                        style={{
                          color: "#fbbf24",
                          fontSize: 10,
                          marginLeft: 6,
                          fontStyle: "italic",
                        }}
                      >
                        (LÄRARE)
                      </em>
                    )}
                  </div>
                  <div
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9,
                      color: "rgba(255,255,255,0.4)",
                      marginTop: 2,
                    }}
                  >
                    {si.description}
                    {isOverdue && (
                      <span style={{ color: "#dc4c2b", marginLeft: 6 }}>
                        · förfallen {si.due_on}
                      </span>
                    )}
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: "rgba(255,255,255,0.55)",
                  }}
                >
                  {basAccountsFor(si)}
                </span>
                <span
                  style={{
                    fontFamily: "Source Serif 4, Georgia, serif",
                    fontStyle: "italic",
                    color: isOpen ? "#dc4c2b" : "#fff",
                    fontWeight: 700,
                  }}
                >
                  {SEK(si.amount_excl_vat)} kr
                </span>
                <span
                  className={`biz-status ${
                    si.status === "paid" ? "paid" : "overdue"
                  }`}
                >
                  {si.status === "paid" ? "Bokförd" : "Ohanterad"}
                </span>
                {isOpen ? (
                  <button
                    onClick={() => pay(si.id)}
                    disabled={paying === si.id}
                    className="biz-btn solid"
                    style={{ padding: "4px 10px", fontSize: 10 }}
                  >
                    {paying === si.id ? "…" : "Betala"}
                  </button>
                ) : (
                  <span></span>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="peda">
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Avdragsgill <em>moms</em> är realpengar.
        </div>
        <p className="peda-prose">
          Varje leverantörsfaktura har 25 % moms — den får du tillbaka från
          Skatteverket nästa redovisningsperiod (eller dras från utgående
          moms). Loopia 1 188 kr = 950 ex moms + 238 in. Du redovisar 238
          som <em>ingående moms</em>. Att inte hantera fakturor → missar
          avdrag → dyrare företag.
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>Ingående moms</strong>Det du betalat. Får tillbaka.
          </li>
          <li>
            <strong>Utgående moms</strong>Det du tagit på dina fakturor.
            Betalar in.
          </li>
          <li>
            <strong>Bokföringsförslag</strong>AI föreslår konto. Du kan
            säga emot.
          </li>
          <li>
            <strong>Avskrivning</strong>Inventarier &gt; 5 000 kr fördelas
            på 5 år, inte direkt-bokat.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">Avdragsgill moms</span>
          <span className="peda-concept">BAS-kontoplan</span>
          <span className="peda-concept">Avskrivning</span>
          <span className="peda-concept">Periodisering</span>
        </div>
        <div className="peda-tip">
          Lärare kan skicka pedagogiska simulerade fakturor — det är samma
          flöde som leverantörs-faktura-utskick i lärar-vyn. Lärare →
          biz-postlåda → eleven hanterar.
        </div>
      </div>
    </BizActorShell>
  );
}


// === Shared styles ===

const inputStyle: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 4,
  padding: "8px 10px", borderRadius: 6,
  border: "1px solid rgba(99,102,241,0.3)",
  background: "rgba(15,21,37,0.5)", color: "white",
  fontSize: "0.95rem",
};

const btnPrimary: React.CSSProperties = {
  background: "rgba(99,102,241,0.25)",
  border: "1px solid rgba(99,102,241,0.5)",
  color: "white", padding: "8px 16px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.9rem", fontWeight: 600,
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(99,102,241,0.3)",
  color: "#c7d2fe", padding: "8px 16px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.9rem",
};

const btnDanger: React.CSSProperties = {
  background: "rgba(248,113,113,0.18)",
  border: "1px solid rgba(248,113,113,0.4)",
  color: "#fda594", padding: "6px 12px", borderRadius: 6,
  cursor: "pointer", fontSize: "0.85rem",
};
