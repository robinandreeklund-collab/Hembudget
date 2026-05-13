/**
 * V2 Händelser · sociala events + klasskompis-bjudningar.
 *
 * Visar:
 *  - Pending events (StudentEvent · status=pending) i scope-DB
 *  - Inkomna klasskompis-bjudningar (ClassEventInvite · master-DB)
 *  - Historik (de senaste accepterade/nekade events)
 *
 * Eleven kan:
 *  - Acceptera ett event (skapar Transaction + applicerar wellbeing-delta)
 *  - Neka (negativ social-impact om socialt event utan sparande-skäl)
 *  - Bjuda klasskompis (för events med social_invite_allowed=true)
 *  - Svara på inbjudan (accepta/neka)
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2EventItem,
  type V2InviteItem,
  type V2ClassmateItem,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./handelser.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const months = [
    "jan", "feb", "mar", "apr", "maj", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
  ];
  return `${d.getDate()} ${months[d.getMonth()]}`;
};

const CATEGORY_LABEL: Record<string, string> = {
  social: "Socialt",
  family: "Familj",
  culture: "Kultur",
  sport: "Sport",
  opportunity: "Chans",
  unexpected: "Oförutsett",
  mat: "Mat",
  lifestyle: "Livsstil",
};

const CATEGORY_ICON: Record<string, string> = {
  social: "♥",
  family: "✦",
  culture: "♪",
  sport: "▲",
  opportunity: "★",
  unexpected: "!",
  mat: "◉",
  lifestyle: "✧",
};

export function HandelserV2() {
  const [pending, setPending] = useState<V2EventItem[]>([]);
  const [history, setHistory] = useState<V2EventItem[]>([]);
  const [invites, setInvites] = useState<V2InviteItem[]>([]);
  const [classmates, setClassmates] = useState<V2ClassmateItem[]>([]);
  const [invitesEnabled, setInvitesEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"pending" | "invites" | "history">(
    "pending",
  );

  // Invite-modal state
  const [inviteForEvent, setInviteForEvent] = useState<V2EventItem | null>(
    null,
  );
  const [selectedClassmates, setSelectedClassmates] = useState<Set<number>>(
    new Set(),
  );
  const [inviteMessage, setInviteMessage] = useState<string>("");

  const navigate = useNavigate();

  function refresh() {
    // Hämta varje endpoint INDIVIDUELLT — annars dör hela vyn vid
    // första 410/500. Visa partial state istället för "kunde inte ladda".
    v2Api.eventsPending()
      .then((p) => setPending(p.events))
      .catch(() => setPending([]));
    v2Api.eventsHistory(20)
      .then((h) => setHistory(h.events.filter((e) => e.status !== "pending")))
      .catch(() => setHistory([]));
    v2Api.eventInvitations()
      .then((i) => setInvites(i.invitations))
      .catch(() => setInvites([]));
    v2Api.eventClassmates()
      .then((c) => {
        setClassmates(c.classmates);
        setInvitesEnabled(c.invites_enabled);
      })
      .catch(() => {
        setClassmates([]);
        setInvitesEnabled(false);
      });
    setError(null);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleAccept(ev: V2EventItem) {
    setBusy(ev.id);
    setFeedback(null);
    try {
      const res = await v2Api.eventAccept(ev.id);
      setFeedback(`✓ ${res.pedagogical_note}`);
      refresh();
    } catch (e) {
      setFeedback(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDecline(ev: V2EventItem, reason?: string) {
    setBusy(ev.id);
    setFeedback(null);
    try {
      const res = await v2Api.eventDecline(ev.id, reason);
      setFeedback(`✓ ${res.pedagogical_note}`);
      refresh();
    } catch (e) {
      setFeedback(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleInviteRespond(inv: V2InviteItem, accept: boolean) {
    setBusy(inv.id);
    setFeedback(null);
    try {
      await v2Api.eventInviteRespond(inv.id, accept);
      setFeedback(
        accept
          ? `✓ Du tackade ja till ${inv.event_title}.`
          : `✓ Du tackade nej till ${inv.event_title}.`,
      );
      refresh();
    } catch (e) {
      setFeedback(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  function openInviteModal(ev: V2EventItem) {
    setInviteForEvent(ev);
    setSelectedClassmates(new Set());
    setInviteMessage("");
  }

  async function submitInvites() {
    if (!inviteForEvent || selectedClassmates.size === 0) return;
    setBusy(inviteForEvent.id);
    setFeedback(null);
    try {
      const res = await v2Api.eventInviteClassmates(
        inviteForEvent.id,
        Array.from(selectedClassmates),
        inviteMessage || undefined,
      );
      setFeedback(
        `✓ Bjudningar skickade till ${res.created} klasskompis${
          res.created === 1 ? "" : "ar"
        }.`,
      );
      setInviteForEvent(null);
      setSelectedClassmates(new Set());
      setInviteMessage("");
      refresh();
    } catch (e) {
      setFeedback(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />
      <div className="shell">
        <a
          href="#"
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/v2/hub");
          }}
        >
          ← Tillbaka till pentagonen
        </a>
        <div className="actor-head">
          <div>
            <span className="pill warm">Aktör · Händelser</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Händelser — <em>livet sker, du väljer</em>.
            </h1>
            <p className="actor-sub">
              Sociala bjudningar, oförutsedda kostnader, och chanser. Varje
              beslut påverkar din pentagon — ekonomi, hälsa, social, fritid,
              trygghet.
            </p>
          </div>
          <div className="actor-meta">
            Att hantera{" "}
            <strong>{pending.length + invites.length}</strong>
            <br />
            Beslutade <strong>{history.length}</strong>
          </div>
        </div>

        {error && (
          <div className="hand-error">
            Kunde inte ladda: {error}
          </div>
        )}

        {feedback && (
          <div
            className={`hand-feedback ${
              feedback.startsWith("Fel") ? "fail" : "ok"
            }`}
          >
            {feedback}
          </div>
        )}

        <div className="hand-tabs">
          <button
            className={`hand-tab${activeTab === "pending" ? " active" : ""}`}
            onClick={() => setActiveTab("pending")}
            type="button"
          >
            Pending {pending.length > 0 && <em>{pending.length}</em>}
          </button>
          <button
            className={`hand-tab${activeTab === "invites" ? " active" : ""}`}
            onClick={() => setActiveTab("invites")}
            type="button"
          >
            Bjudningar {invites.length > 0 && <em>{invites.length}</em>}
          </button>
          <button
            className={`hand-tab${activeTab === "history" ? " active" : ""}`}
            onClick={() => setActiveTab("history")}
            type="button"
          >
            Historik
          </button>
        </div>

        {activeTab === "pending" && (
          <div className="hand-list">
            {pending.length === 0 ? (
              <div className="hand-empty">
                Inga pending händelser just nu. Spelet seedar nya
                händelser varje vecka — kom tillbaka.
              </div>
            ) : (
              pending.map((ev) => (
                <article key={ev.id} className={`hand-card cat-${ev.category}`}>
                  <div className="hand-card-head">
                    <span className="hand-card-icon">
                      {CATEGORY_ICON[ev.category] || "●"}
                    </span>
                    <div>
                      <div className="hand-card-cat">
                        {CATEGORY_LABEL[ev.category] || ev.category}
                        {ev.source === "classmate_invite"
                          && " · från klasskompis"}
                      </div>
                      <div className="hand-card-title">{ev.title}</div>
                    </div>
                    <div className="hand-card-cost">
                      {ev.cost > 0
                        ? `${SEK(ev.cost)} kr`
                        : "ingen kostnad"}
                    </div>
                  </div>
                  <div className="hand-card-body">{ev.description}</div>
                  <div className="hand-card-meta">
                    <span>Deadline: <em>{SHORT_DATE(ev.deadline)}</em></span>
                    {ev.proposed_date && (
                      <span>Föreslaget: {SHORT_DATE(ev.proposed_date)}</span>
                    )}
                    {!ev.declinable && (
                      <span className="warn">
                        Oförutsedd kostnad — går inte att neka
                      </span>
                    )}
                  </div>
                  <div className="hand-card-actions">
                    <button
                      type="button"
                      className="cta-btn"
                      disabled={busy === ev.id}
                      onClick={() => handleAccept(ev)}
                    >
                      {busy === ev.id ? "…" : "Acceptera"}
                    </button>
                    {ev.declinable && (
                      <>
                        <button
                          type="button"
                          className="cta-btn ghost"
                          disabled={busy === ev.id}
                          onClick={() => handleDecline(ev)}
                        >
                          Neka
                        </button>
                        <button
                          type="button"
                          className="cta-btn ghost"
                          disabled={busy === ev.id}
                          onClick={() =>
                            handleDecline(ev, "valde sparande")
                          }
                        >
                          Neka — spara istället
                        </button>
                      </>
                    )}
                    {ev.social_invite_allowed && invitesEnabled
                      && classmates.length > 0 && (
                        <button
                          type="button"
                          className="cta-btn ghost"
                          onClick={() => openInviteModal(ev)}
                        >
                          Bjud klasskompis
                        </button>
                      )}
                  </div>
                </article>
              ))
            )}
          </div>
        )}

        {activeTab === "invites" && (
          <div className="hand-list">
            {invites.length === 0 ? (
              <div className="hand-empty">
                Inga inkomna bjudningar just nu.
              </div>
            ) : (
              invites.map((inv) => (
                <article key={inv.id} className="hand-card cat-social invite">
                  <div className="hand-card-head">
                    <span className="hand-card-icon">♥</span>
                    <div>
                      <div className="hand-card-cat">
                        Bjudning från <strong>{inv.from_name}</strong>
                      </div>
                      <div className="hand-card-title">{inv.event_title}</div>
                    </div>
                    <div className="hand-card-cost">
                      {inv.swish_amount && inv.swish_amount > 0
                        ? `${SEK(inv.swish_amount)} kr`
                        : "gratis för dig"}
                    </div>
                  </div>
                  {inv.message && (
                    <div className="hand-card-body invite-msg">
                      "{inv.message}"
                    </div>
                  )}
                  <div className="hand-card-meta">
                    <span>Deadline: <em>{SHORT_DATE(inv.deadline)}</em></span>
                    {inv.proposed_date && (
                      <span>Datum: {SHORT_DATE(inv.proposed_date)}</span>
                    )}
                    <span>
                      Kostnadsdelning:{" "}
                      {inv.cost_split_model === "split" && "50/50"}
                      {inv.cost_split_model === "inviter_pays"
                        && "bjudaren bjuder"}
                      {inv.cost_split_model === "each_pays_own"
                        && "var och en betalar sin del"}
                    </span>
                  </div>
                  <div className="hand-card-actions">
                    <button
                      type="button"
                      className="cta-btn"
                      disabled={busy === inv.id}
                      onClick={() => handleInviteRespond(inv, true)}
                    >
                      Ja, jag kommer
                    </button>
                    <button
                      type="button"
                      className="cta-btn ghost"
                      disabled={busy === inv.id}
                      onClick={() => handleInviteRespond(inv, false)}
                    >
                      Nej, kan inte
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        )}

        {activeTab === "history" && (
          <div className="hand-list">
            {history.length === 0 ? (
              <div className="hand-empty">
                Ingen historik än. Dina beslut samlas här.
              </div>
            ) : (
              history.map((ev) => (
                <article
                  key={ev.id}
                  className={`hand-card cat-${ev.category} status-${ev.status}`}
                >
                  <div className="hand-card-head">
                    <span className="hand-card-icon">
                      {CATEGORY_ICON[ev.category] || "●"}
                    </span>
                    <div>
                      <div className="hand-card-cat">
                        {CATEGORY_LABEL[ev.category] || ev.category}
                      </div>
                      <div className="hand-card-title">{ev.title}</div>
                    </div>
                    <div
                      className={`hand-card-status ${ev.status}`}
                    >
                      {ev.status === "accepted" && "✓ Tackade ja"}
                      {ev.status === "declined" && "✗ Tackade nej"}
                      {ev.status === "expired" && "⊘ Missade"}
                    </div>
                  </div>
                  <div className="hand-card-meta">
                    <span>{SHORT_DATE(ev.deadline)}</span>
                    {ev.cost > 0 && <span>{SEK(ev.cost)} kr</span>}
                  </div>
                </article>
              ))
            )}
          </div>
        )}

        {/* INVITE-MODAL */}
        {inviteForEvent && (
          <div className="hand-modal-bg" onClick={() => setInviteForEvent(null)}>
            <div className="hand-modal" onClick={(e) => e.stopPropagation()}>
              <div className="hand-modal-head">
                <h2>Bjud klasskompis · {inviteForEvent.title}</h2>
                <button
                  type="button"
                  className="cta-btn ghost"
                  onClick={() => setInviteForEvent(null)}
                >
                  Stäng
                </button>
              </div>
              <p className="hand-modal-help">
                Välj en eller flera klasskompisar att bjuda. De får ett
                meddelande i sina notiser och kan tacka ja eller nej.
              </p>
              <div className="hand-classmate-list">
                {classmates.map((c) => (
                  <label key={c.student_id} className="hand-classmate-row">
                    <input
                      type="checkbox"
                      checked={selectedClassmates.has(c.student_id)}
                      onChange={(e) => {
                        const next = new Set(selectedClassmates);
                        if (e.target.checked) next.add(c.student_id);
                        else next.delete(c.student_id);
                        setSelectedClassmates(next);
                      }}
                    />
                    <span>{c.display_name}</span>
                    {c.class_label && (
                      <em className="hand-classmate-label">
                        {c.class_label}
                      </em>
                    )}
                  </label>
                ))}
                {classmates.length === 0 && (
                  <div className="hand-empty">
                    Du har inga klasskompisar registrerade än.
                  </div>
                )}
              </div>
              <div style={{ marginTop: 12 }}>
                <label className="hand-form-label">
                  Meddelande (frivilligt)
                </label>
                <textarea
                  value={inviteMessage}
                  onChange={(e) => setInviteMessage(e.target.value)}
                  className="hand-textarea"
                  rows={3}
                  placeholder="Hej, vill du följa med på..."
                />
              </div>
              <div className="hand-modal-actions">
                <button
                  type="button"
                  className="cta-btn"
                  disabled={
                    selectedClassmates.size === 0
                    || busy === inviteForEvent.id
                  }
                  onClick={submitInvites}
                >
                  Skicka {selectedClassmates.size > 0
                    && `(${selectedClassmates.size})`}
                </button>
                <button
                  type="button"
                  className="cta-btn ghost"
                  onClick={() => setInviteForEvent(null)}
                >
                  Avbryt
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
