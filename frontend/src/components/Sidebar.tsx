import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Briefcase,
  CalendarPlus,
  CircleDollarSign,
  FileDown,
  GraduationCap,
  Home,
  Inbox,
  MessageCircle,
  BookOpen,
  GitBranch,
  MessagesSquare,
  Trophy,
  Landmark,
  Link2,
  Menu,
  MessageSquare,
  Paperclip,
  Settings as Cog,
  Upload,
  Receipt,
  CalculatorIcon,
  PiggyBank,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/hooks/useAuth";

type NavItem = { to: string; label: string; icon: typeof Home };

const ALL_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/transactions", label: "Transaktioner", icon: Receipt },
  { to: "/import", label: "Importera", icon: Upload },
  { to: "/budget", label: "Budget", icon: CircleDollarSign },
  { to: "/salaries", label: "Lön", icon: Briefcase },
  { to: "/upcoming", label: "Kommande", icon: CalendarPlus },
  { to: "/attachments", label: "Bildunderlag", icon: Paperclip },
  { to: "/transfers", label: "Överföringar", icon: Link2 },
  { to: "/chat", label: "AI-chatt", icon: MessageSquare },
  { to: "/scenarios", label: "Scenarion", icon: CalculatorIcon },
  { to: "/loans", label: "Lån", icon: Landmark },
  { to: "/funds", label: "Fonder & ISK", icon: PiggyBank },
  { to: "/utility", label: "Förbrukning", icon: Activity },
  { to: "/tax", label: "Skatt", icon: BarChart3 },
  { to: "/reports", label: "Rapporter", icon: FileDown },
  { to: "/settings", label: "Inställningar", icon: Cog },
];

// Elev-vyn döljer importera/AI-chat/inställningar och lägger till
// Dina dokument-sidan. Lärare-impersonation visar fortfarande hela
// menyn så de kan se elevens hela värld.
const STUDENT_HIDDEN = new Set(["/import", "/chat", "/settings", "/funds"]);

function NavItems({ onClick }: { onClick?: () => void }) {
  const { role, asStudent } = useAuth();
  const isStudent = role === "student";
  const isTeacherViewing = role === "teacher" && Boolean(asStudent);

  let items: NavItem[];
  if (isStudent) {
    items = [
      { to: "/modules", label: "Din kursplan", icon: GitBranch },
      { to: "/achievements", label: "Prestationer", icon: Trophy },
      { to: "/my-batches", label: "Dina dokument", icon: Inbox },
      { to: "/messages", label: "Meddelanden", icon: MessageCircle },
      { to: "/peer-review", label: "Kamratrespons", icon: MessagesSquare },
      ...ALL_ITEMS.filter((i) => !STUDENT_HIDDEN.has(i.to)),
      { to: "/docs", label: "Hjälp & guide", icon: BookOpen },
    ];
  } else if (isTeacherViewing) {
    items = [
      { to: "/teacher", label: "Tillbaka till lärare", icon: GraduationCap },
      { to: "/my-batches", label: "Elevens dokument", icon: Inbox },
      ...ALL_ITEMS,
    ];
  } else {
    items = ALL_ITEMS;
  }

  return (
    <>
      {items.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          onClick={onClick}
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-2.5 px-3 py-2 text-sm transition-colors border-l-2",
              isActive
                ? "bg-paper text-ink border-ink font-semibold"
                : "text-[#555] hover:bg-paper border-transparent",
            )
          }
        >
          <it.icon className="w-4 h-4" />
          {it.label}
        </NavLink>
      ))}
    </>
  );
}

function Brand() {
  const { role, schoolMode } = useAuth();
  const isStudent = role === "student";
  const title = schoolMode || isStudent ? "Ekonomilabbet" : "Hembudget";
  const subtitle = isStudent
    ? "Övning – inte riktiga pengar"
    : schoolMode
    ? "Lärarpanel"
    : "Lokalt · Nemotron Nano 3";
  return (
    <div className="p-5 border-b border-rule">
      <Link
        to={isStudent ? "/my-batches" : "/dashboard"}
        className="flex items-center gap-2.5"
      >
        <svg width="24" height="24" viewBox="0 0 40 40" aria-hidden="true">
          <circle cx="20" cy="20" r="18" fill="none" stroke="#111217" strokeWidth="2" />
          <text x="20" y="26" textAnchor="middle" fontFamily="Spectral" fontWeight="800" fontSize="18">
            {schoolMode || isStudent ? "Ek" : "Hb"}
          </text>
        </svg>
        <span className="serif text-lg leading-none">{title}</span>
      </Link>
      <div className="eyebrow mt-2.5">{subtitle}</div>
    </div>
  );
}

export function Sidebar() {
  // Desktop-sidebar — dold på mobil
  return (
    <aside className="hidden md:flex md:flex-col w-60 shrink-0 border-r border-rule bg-white">
      <Brand />
      <nav className="py-3 flex-1 overflow-y-auto">
        <NavItems />
      </nav>
      <UserFooter />
    </aside>
  );
}

function UserFooter({ onAction }: { onAction?: () => void } = {}) {
  const { role, asStudent, impersonate, logout } = useAuth();
  const isStudent = role === "student";
  const isImpersonating = role === "teacher" && Boolean(asStudent);

  function doLogout() {
    if (!confirm("Logga ut?")) return;
    logout();
    onAction?.();
    window.location.href = "/";
  }

  function stopImpersonating() {
    impersonate(null);
    onAction?.();
    window.location.href = "/teacher";
  }

  return (
    <div className="border-t border-rule p-4 space-y-2 text-sm">
      <div className="eyebrow">
        {isStudent ? "Inloggad som elev" : isImpersonating ? "Visar elev" : "Inloggad lärare"}
      </div>
      {isImpersonating && (
        <button
          onClick={stopImpersonating}
          className="w-full text-left btn-outline rounded-md px-3 py-2 text-sm"
        >
          ← Tillbaka till lärare
        </button>
      )}
      <button
        onClick={doLogout}
        className="w-full text-left text-[#666] hover:text-ink hover:bg-paper px-3 py-2 transition-colors"
      >
        Logga ut
      </button>
    </div>
  );
}

export function MobileTopBar() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { role, schoolMode } = useAuth();
  const isStudent = role === "student";
  const currentItem = ALL_ITEMS.find((i) =>
    location.pathname.startsWith(i.to),
  );

  return (
    <>
      <div className="md:hidden sticky top-0 z-30 flex items-center gap-3 bg-white border-b border-rule px-3 h-12">
        <button
          onClick={() => setOpen(true)}
          className="p-2 -ml-2 text-ink"
          aria-label="Meny"
        >
          <Menu className="w-5 h-5" />
        </button>
        <Link
          to={isStudent ? "/my-batches" : "/dashboard"}
          className="serif text-base flex items-center gap-1.5 text-ink"
        >
          <svg width="18" height="18" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx="20" cy="20" r="18" fill="none" stroke="#111217" strokeWidth="2.5" />
            <text x="20" y="27" textAnchor="middle" fontFamily="Spectral" fontWeight="800" fontSize="18">
              {schoolMode || isStudent ? "Ek" : "Hb"}
            </text>
          </svg>
          {schoolMode || isStudent ? "Ekonomilabbet" : "Hembudget"}
        </Link>
        {currentItem && (
          <span className="ml-auto text-xs eyebrow">{currentItem.label}</span>
        )}
      </div>

      {open && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-ink/40"
          onClick={() => setOpen(false)}
        >
          <div
            className="absolute left-0 top-0 bottom-0 w-64 bg-white border-r border-rule overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pr-2">
              <Brand />
              <button
                onClick={() => setOpen(false)}
                className="p-2 text-ink"
                aria-label="Stäng"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="py-3">
              <NavItems onClick={() => setOpen(false)} />
            </nav>
            <UserFooter onAction={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
