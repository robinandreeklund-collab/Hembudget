/**
 * Notif-bell · klickbar topbar-ikon med badge + drawer + toast.
 *
 * - Pollar /v2/notifications var 30:e sekund (live-känsla)
 * - Visar badge med unread-count
 * - Drawer med flikar (Alla / Olästa / kind-grupper)
 * - Toast slår upp när NY notif dyker upp sedan föregående poll
 *
 * Ses i prototypens elev.html .notif-bell + .notif-drawer + .notif-toast.
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2Notification,
  type V2NotificationsResponse,
  type V2NotifKind,
} from "./api";
import "./notif.css";

const POLL_INTERVAL_MS = 30_000;

const KIND_LABEL: Record<V2NotifKind, string> = {
  teacher: "Lärare",
  uppdrag: "Uppdrag",
  echo: "Echo",
  modul: "Modul",
  bank: "Bank",
  social: "Klass",
  system: "System",
};

type Tab = "all" | "unread" | V2NotifKind;

type Toast = {
  notif: V2Notification;
  shownAt: number;
};

export function NotifBell() {
  const [data, setData] = useState<V2NotificationsResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("all");
  const [toast, setToast] = useState<Toast | null>(null);
  const seenIds = useRef<Set<string>>(new Set());
  const firstLoad = useRef(true);
  const navigate = useNavigate();

  async function load() {
    try {
      const next = await v2Api.notifications();
      // Hitta nya notiser (förutom första load)
      if (!firstLoad.current) {
        const newOnes = next.items.filter(
          (n) => !seenIds.current.has(n.id) && n.unread,
        );
        if (newOnes.length > 0) {
          // Visa nyaste som toast
          setToast({ notif: newOnes[0], shownAt: Date.now() });
          window.setTimeout(() => {
            setToast((t) =>
              t && t.shownAt + 7000 <= Date.now() ? null : t,
            );
          }, 7100);
        }
      }
      next.items.forEach((n) => seenIds.current.add(n.id));
      firstLoad.current = false;
      setData(next);
    } catch {
      // tyst fel — bell visar bara senaste lyckade payload
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, []);

  // Stäng vid Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const unread = data?.summary.unread_count || 0;
  const items = data?.items || [];
  const filtered =
    activeTab === "all"
      ? items
      : activeTab === "unread"
      ? items.filter((n) => n.unread)
      : items.filter((n) => n.kind === activeTab);

  function handleNotifClick(n: V2Notification) {
    // 1. Optimistisk UI · sätt unread=false direkt så badge sjunker
    //    utan att vänta på round-trip / nästa poll.
    if (n.unread) {
      setData((prev) => {
        if (!prev) return prev;
        const items = prev.items.map((it) =>
          it.id === n.id ? { ...it, unread: false } : it,
        );
        const unread_count = items.filter((it) => it.unread).length;
        return {
          ...prev,
          items,
          summary: { ...prev.summary, unread_count },
        };
      });
      // 2. Persistera read-state i backend (eld and forget · backend
      //    är idempotent. Felfall fångas av nästa poll som återställer.)
      v2Api.notifMarkRead(n.id).catch(() => {
        // tyst — nästa poll synkar
      });
    }
    setOpen(false);
    if (n.target_route) navigate(n.target_route);
  }

  async function handleMarkAllRead() {
    // Optimistisk: rensa alla unread direkt
    setData((prev) => {
      if (!prev) return prev;
      const items = prev.items.map((it) => ({ ...it, unread: false }));
      return {
        ...prev,
        items,
        summary: { ...prev.summary, unread_count: 0 },
      };
    });
    try {
      await v2Api.notifMarkAllRead();
    } catch {
      // Nästa poll synkar
    }
  }

  function handleToastClick() {
    if (!toast) return;
    const route = toast.notif.target_route;
    setToast(null);
    if (route) navigate(route);
  }

  return (
    <>
      <button
        type="button"
        className={`notif-bell${unread > 0 ? " has-unread" : ""}`}
        onClick={() => setOpen((s) => !s)}
        aria-label={`Notiser (${unread} olästa)`}
        aria-expanded={open}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
        </svg>
        {unread > 0 && (
          <span className="notif-count">{unread > 99 ? "99+" : unread}</span>
        )}
      </button>

      {open && createPortal(
        <>
          <div className="notif-scrim" onClick={() => setOpen(false)} />
          <aside className="notif-drawer" role="dialog" aria-label="Notiser">
            <div className="notif-drawer-head">
              <div>
                <div className="notif-drawer-eye">Notiser</div>
                <div className="notif-drawer-meta">
                  {unread} olästa ·{" "}
                  {data?.summary.new_today_count || 0} nya idag
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {unread > 0 && (
                  <button
                    type="button"
                    onClick={handleMarkAllRead}
                    title="Markera alla som lästa"
                    style={{
                      background: "transparent",
                      border: "1px solid var(--line-strong)",
                      color: "var(--text-mid)",
                      fontFamily: "var(--mono)",
                      fontSize: 9.5,
                      letterSpacing: "1px",
                      textTransform: "uppercase",
                      padding: "6px 10px",
                      borderRadius: 100,
                      cursor: "pointer",
                    }}
                  >
                    ✓ Alla
                  </button>
                )}
                <button
                  className="notif-drawer-close"
                  onClick={() => setOpen(false)}
                  aria-label="Stäng"
                >
                  ×
                </button>
              </div>
            </div>

            <div className="notif-drawer-actions">
              <NotifTab
                label="Alla"
                count={items.length}
                active={activeTab === "all"}
                onClick={() => setActiveTab("all")}
              />
              <NotifTab
                label="Olästa"
                count={unread}
                active={activeTab === "unread"}
                onClick={() => setActiveTab("unread")}
              />
              {Object.entries(data?.summary.by_kind || {}).map(
                ([k, count]) => (
                  <NotifTab
                    key={k}
                    label={KIND_LABEL[k as V2NotifKind] || k}
                    count={count as number}
                    active={activeTab === k}
                    onClick={() => setActiveTab(k as V2NotifKind)}
                  />
                ),
              )}
            </div>

            <div className="notif-list">
              {filtered.length === 0 ? (
                <div className="notif-empty">
                  Inga notiser{activeTab !== "all" ? " i denna kategori" : ""}.
                </div>
              ) : (
                filtered.map((n) => (
                  <NotifItem
                    key={n.id}
                    notif={n}
                    onClick={() => handleNotifClick(n)}
                  />
                ))
              )}
            </div>
          </aside>
        </>,
        document.body,
      )}

      {toast && createPortal(
        <div
          className="notif-toast show"
          role="status"
          onClick={handleToastClick}
        >
          <div className="notif-toast-eye">
            ● Live · ny händelse
          </div>
          <div className="notif-toast-title">{toast.notif.title}</div>
          <div
            className="notif-toast-body"
            dangerouslySetInnerHTML={{ __html: toast.notif.body }}
          />
        </div>,
        document.body,
      )}
    </>
  );
}

function NotifTab({
  label, count, active, onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`notif-tab${active ? " active" : ""}`}
      onClick={onClick}
    >
      {label} <span className="count">{count}</span>
    </button>
  );
}

function NotifItem({
  notif, onClick,
}: {
  notif: V2Notification;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`notif-item ${notif.unread ? "unread" : ""}`}
      onClick={onClick}
    >
      <div className={`notif-icon ${notif.kind}`}>{notif.icon}</div>
      <div className="notif-item-body">
        <div className="notif-time">{notif.time_label}</div>
        <div className="notif-title">{notif.title}</div>
        <div
          className="notif-body"
          dangerouslySetInnerHTML={{ __html: notif.body }}
        />
      </div>
    </button>
  );
}
