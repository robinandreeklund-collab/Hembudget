import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import {
  Activity,
  BarChart3,
  Briefcase,
  Building2,
  CalendarPlus,
  CircleDollarSign,
  Clock,
  FileDown,
  Files,
  Grid3x3,
  GraduationCap,
  Home,
  Inbox,
  ListChecks,
  MessageCircle,
  BookOpen,
  GitBranch,
  MessagesSquare,
  PenSquare,
  ShieldCheck,
  Trophy,
  Landmark,
  Link2,
  Menu,
  MessageSquare,
  Paperclip,
  Settings as Cog,
  Upload,
  Users,
  Receipt,
  CalculatorIcon,
  PiggyBank,
  TrendingUp,
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
  { to: "/arbetsgivare", label: "Arbetsgivare", icon: Building2 },
  { to: "/upcoming", label: "Kommande", icon: CalendarPlus },
  { to: "/attachments", label: "Bildunderlag", icon: Paperclip },
  { to: "/transfers", label: "Överföringar", icon: Link2 },
  { to: "/chat", label: "AI-chatt", icon: MessageSquare },
  { to: "/scenarios", label: "Scenarion", icon: CalculatorIcon },
  { to: "/loans", label: "Lån", icon: Landmark },
  { to: "/funds", label: "Fonder & ISK", icon: PiggyBank },
  { to: "/investments", label: "Aktier", icon: TrendingUp },
  { to: "/utility", label: "Förbrukning", icon: Activity },
  { to: "/tax", label: "Skatt", icon: BarChart3 },
  { to: "/reports", label: "Rapporter", icon: FileDown },
  { to: "/settings", label: "Inställningar", icon: Cog },
];

// Lärar-specifika sidor som tidigare låg som knapprad i Teacher.tsx —
// nu samlade i sidebaren under egen rubrik så vyn blir städad.
const TEACHER_ITEMS: NavItem[] = [
  { to: "/teacher", label: "Klassen", icon: Users },
  { to: "/teacher/matrix", label: "Klassöversikt", icon: Grid3x3 },
  { to: "/teacher/modules", label: "Kursmoduler", icon: GraduationCap },
  { to: "/teacher/reflections", label: "Reflektioner", icon: PenSquare },
  { to: "/teacher/rubrics", label: "Rubric-mallar", icon: ListChecks },
  { to: "/teacher/time-on-task", label: "Time on task", icon: Clock },
  { to: "/teacher/all-batches", label: "Alla PDF:er", icon: Files },
  { to: "/messages", label: "Meddelanden", icon: MessageCircle },
];

// Elev-vyn döljer importera/inställningar och lägger till Dina dokument
// och AI-chatt-sidor. Lärare-impersonation visar fortfarande hela
// menyn så de kan se elevens hela värld.
// /chat visas alltid för elever — sidan själv visar "Ej aktiverat"-
// state om lärarens ai_enabled är av eller dagskvoten är 0.
const STUDENT_HIDDEN = new Set(["/import", "/settings"]);

interface NotificationCounts {
  messages: number;
  batches: number;
  assignments: number;
  peer_review: number;
  total: number;
}

interface SectionDef {
  title?: string;
  items: NavItem[];
}


function NavItems({ onClick }: { onClick?: () => void }) {
  const { role, asStudent, schoolMode } = useAuth();
  const isStudent = role === "student";
  const isTeacher = role === "teacher";
  const isTeacherViewing = isTeacher && Boolean(asStudent);
  const isTeacherHome = isTeacher && !asStudent && schoolMode;

  // Super-admin-flagga — låter oss visa /teacher/admin-ai i sidebaren
  // bara för dem som faktiskt har åtkomst. Endpoint:en är gated så
  // andra lärare får 403, men vi vill inte visa länken i onödan.
  const adminQ = useQuery({
    queryKey: ["sidebar-admin-check"],
    queryFn: () => api<{ is_super_admin: boolean }>("/admin/ai/me"),
    enabled: isTeacherHome,
    retry: false,
  });
  const isSuperAdmin = Boolean(adminQ.data?.is_super_admin);

  // Pollar olästa-räknare var 30 sek. Bara för elev/impersonering —
  // läraren har sin egen vy. Fail-soft: badges visas inte om endpoint
  // saknas.
  const notifQ = useQuery({
    queryKey: ["sidebar-notifications"],
    queryFn: () => api<NotificationCounts>("/student/notifications/counts"),
    refetchInterval: 30_000,
    enabled: isStudent || isTeacherViewing,
    retry: false,
  });
  const counts = notifQ.data;

  // Mappa nav-path → vilket fält i counts som visar badge
  const badgeFor: Record<string, keyof NotificationCounts | undefined> = {
    "/messages": "messages",
    "/my-batches": "batches",
    "/modules": "assignments",
    "/peer-review": "peer_review",
  };

  let sections: SectionDef[];
  if (isStudent) {
    sections = [{
      items: [
        { to: "/modules", label: "Din kursplan", icon: GitBranch },
        { to: "/achievements", label: "Prestationer", icon: Trophy },
        { to: "/my-batches", label: "Dina dokument", icon: Inbox },
        { to: "/messages", label: "Meddelanden", icon: MessageCircle },
        { to: "/peer-review", label: "Kamratrespons", icon: MessagesSquare },
        ...ALL_ITEMS.filter((i) => !STUDENT_HIDDEN.has(i.to)),
        { to: "/docs", label: "Hjälp & guide", icon: BookOpen },
      ],
    }];
  } else if (isTeacherViewing) {
    sections = [{
      items: [
        { to: "/teacher", label: "Tillbaka till lärare", icon: GraduationCap },
        { to: "/my-batches", label: "Elevens dokument", icon: Inbox },
        ...ALL_ITEMS,
      ],
    }];
  } else if (isTeacherHome) {
    // Lärar-vyn: dela menyn i två sektioner — Lärarverktyg + Hushåll
    // (eget konto). Tidigare låg lärarverktygen som knapprad i
    // Teacher.tsx; nu samlade här så vyn håller samma struktur som
    // resten av plattformen.
    const teacherItems = [...TEACHER_ITEMS];
    if (isSuperAdmin) {
      teacherItems.push({
        to: "/teacher/admin-ai", label: "Super-admin", icon: ShieldCheck,
      });
    }
    teacherItems.push({
      to: "/docs", label: "Guide", icon: BookOpen,
    });
    sections = [
      { title: "Lärarverktyg", items: teacherItems },
      { title: "Eget konto", items: ALL_ITEMS },
    ];
  } else {
    sections = [{ items: ALL_ITEMS }];
  }

  function renderItem(it: NavItem) {
    const badgeKey = badgeFor[it.to];
    const count = badgeKey && counts ? counts[badgeKey] : 0;
    return (
      <NavLink
        key={it.to}
        to={it.to}
        end={it.to === "/teacher"}
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
        <span className="flex-1">{it.label}</span>
        {count > 0 && (
          <span
            className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-semibold"
            title={`${count} oläst${count === 1 ? "" : "a"}`}
          >
            {count > 99 ? "99+" : count}
          </span>
        )}
      </NavLink>
    );
  }

  return (
    <>
      {sections.map((sec, idx) => (
        <div key={idx} className={idx > 0 ? "mt-3 pt-3 border-t border-rule" : ""}>
          {sec.title && (
            <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
              {sec.title}
            </div>
          )}
          {sec.items.map(renderItem)}
        </div>
      ))}
    </>
  );
}

function Brand() {
  const { role, schoolMode, teacherMeta } = useAuth();
  const isStudent = role === "student";
  const isFamily = teacherMeta?.is_family_account === true;
  const title = schoolMode || isStudent ? "Ekonomilabbet" : "Hembudget";
  const subtitle = isStudent
    ? "Övning – inte riktiga pengar"
    : schoolMode
    ? (isFamily ? "Familjepanel" : "Lärarpanel")
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
  const { role, asStudent, impersonate, logout, teacherMeta } = useAuth();
  const isStudent = role === "student";
  const isImpersonating = role === "teacher" && Boolean(asStudent);
  const isFamily = teacherMeta?.is_family_account === true;
  const adminLabel = isFamily ? "förälder" : "lärare";
  const studentLabel = isFamily ? "barn" : "elev";

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
        {isStudent
          ? `Inloggad som ${studentLabel}`
          : isImpersonating
          ? `Visar ${studentLabel}`
          : `Inloggad ${adminLabel}`}
      </div>
      {isImpersonating && (
        <button
          onClick={stopImpersonating}
          className="w-full text-left btn-outline rounded-md px-3 py-2 text-sm"
        >
          ← Tillbaka till {adminLabel}
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
