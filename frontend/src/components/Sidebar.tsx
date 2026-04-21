import { NavLink } from "react-router-dom";
import {
  BarChart3,
  CircleDollarSign,
  FileDown,
  Home,
  LineChart,
  Landmark,
  MessageSquare,
  Settings as Cog,
  Upload,
  Receipt,
  CalculatorIcon,
} from "lucide-react";
import clsx from "clsx";

const ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/transactions", label: "Transaktioner", icon: Receipt },
  { to: "/import", label: "Importera", icon: Upload },
  { to: "/budget", label: "Budget", icon: CircleDollarSign },
  { to: "/chat", label: "AI-chatt", icon: MessageSquare },
  { to: "/scenarios", label: "Scenarion", icon: CalculatorIcon },
  { to: "/loans", label: "Lån", icon: Landmark },
  { to: "/tax", label: "Skatt", icon: BarChart3 },
  { to: "/reports", label: "Rapporter", icon: FileDown },
  { to: "/settings", label: "Inställningar", icon: Cog },
];

export function Sidebar() {
  return (
    <aside className="w-60 shrink-0 border-r border-slate-200 bg-white">
      <div className="p-4">
        <div className="flex items-center gap-2 text-brand-600 font-semibold text-lg">
          <LineChart className="w-5 h-5" />
          Hembudget
        </div>
        <div className="text-xs text-slate-400 mt-0.5">Lokalt • Nemotron Nano 3</div>
      </div>
      <nav className="px-2 space-y-1">
        {ITEMS.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
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
      </nav>
    </aside>
  );
}
