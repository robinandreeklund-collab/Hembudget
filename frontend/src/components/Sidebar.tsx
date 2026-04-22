import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  BarChart3,
  CalendarPlus,
  CircleDollarSign,
  FileDown,
  Home,
  Landmark,
  Link2,
  LineChart,
  Menu,
  MessageSquare,
  Settings as Cog,
  Upload,
  Receipt,
  CalculatorIcon,
  X,
} from "lucide-react";
import clsx from "clsx";

const ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/transactions", label: "Transaktioner", icon: Receipt },
  { to: "/import", label: "Importera", icon: Upload },
  { to: "/budget", label: "Budget", icon: CircleDollarSign },
  { to: "/upcoming", label: "Kommande", icon: CalendarPlus },
  { to: "/transfers", label: "Överföringar", icon: Link2 },
  { to: "/chat", label: "AI-chatt", icon: MessageSquare },
  { to: "/scenarios", label: "Scenarion", icon: CalculatorIcon },
  { to: "/loans", label: "Lån", icon: Landmark },
  { to: "/tax", label: "Skatt", icon: BarChart3 },
  { to: "/reports", label: "Rapporter", icon: FileDown },
  { to: "/settings", label: "Inställningar", icon: Cog },
];

function NavItems({ onClick }: { onClick?: () => void }) {
  return (
    <>
      {ITEMS.map((it) => (
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
  return (
    <div className="p-4">
      <Link to="/dashboard" className="flex items-center gap-2 text-brand-600 font-semibold text-lg">
        <LineChart className="w-5 h-5" />
        Hembudget
      </Link>
      <div className="text-xs text-slate-600 mt-0.5">Lokalt • Nemotron Nano 3</div>
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
  const currentItem = ITEMS.find((i) => location.pathname.startsWith(i.to));

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
        <Link to="/dashboard" className="font-semibold text-brand-600 flex items-center gap-1.5">
          <LineChart className="w-4 h-4" />
          Hembudget
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
