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
  Landmark,
  Link2,
  LineChart,
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
              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm",
              isActive
                ? "bg-brand-50 text-brand-700 font-medium"
                : "text-slate-600 hover:bg-slate-50",
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
  // I school-mode = Ekonomilabbet för alla (elev + lärare).
  // I desktop-mode = Hembudget.
  const title = schoolMode || isStudent ? "Ekonomilabbet" : "Hembudget";
  const subtitle = isStudent
    ? "Övning – inte riktiga pengar"
    : schoolMode
    ? "Lärarpanel"
    : "Lokalt • Nemotron Nano 3";
  return (
    <div className="p-4">
      <Link
        to={isStudent ? "/my-batches" : "/dashboard"}
        className="flex items-center gap-2 text-brand-600 font-semibold text-lg"
      >
        {isStudent || schoolMode ? (
          <GraduationCap className="w-5 h-5" />
        ) : (
          <LineChart className="w-5 h-5" />
        )}
        {title}
      </Link>
      <div className="text-xs text-slate-600 mt-0.5">{subtitle}</div>
    </div>
  );
}

export function Sidebar() {
  // Desktop-sidebar — dold på mobil
  return (
    <aside className="hidden md:block w-60 shrink-0 border-r border-slate-200 bg-white">
      <Brand />
      <nav className="px-2 space-y-1 pb-6">
        <NavItems />
      </nav>
    </aside>
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
      <div className="md:hidden sticky top-0 z-30 flex items-center gap-3 bg-white border-b border-slate-200 px-3 h-12">
        <button
          onClick={() => setOpen(true)}
          className="p-2 -ml-2 text-slate-600"
          aria-label="Meny"
        >
          <Menu className="w-5 h-5" />
        </button>
        <Link
          to={isStudent ? "/my-batches" : "/dashboard"}
          className="font-semibold text-brand-600 flex items-center gap-1.5"
        >
          {isStudent || schoolMode ? (
            <GraduationCap className="w-4 h-4" />
          ) : (
            <LineChart className="w-4 h-4" />
          )}
          {isStudent || schoolMode ? "Ekonomilabbet" : "Hembudget"}
        </Link>
        {currentItem && (
          <span className="ml-auto text-sm text-slate-700">{currentItem.label}</span>
        )}
      </div>

      {open && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-slate-900/40"
          onClick={() => setOpen(false)}
        >
          <div
            className="absolute left-0 top-0 bottom-0 w-64 bg-white shadow-lg overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pr-2">
              <Brand />
              <button
                onClick={() => setOpen(false)}
                className="p-2 text-slate-600"
                aria-label="Stäng"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="px-2 space-y-1 pb-6">
              <NavItems onClick={() => setOpen(false)} />
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
