import { Navigate, Route, Routes } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { useAuth } from "./hooks/useAuth";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Budget from "./pages/Budget";
import Chat from "./pages/Chat";
import Scenarios from "./pages/Scenarios";
import Loans from "./pages/Loans";
import Tax from "./pages/Tax";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Import from "./pages/Import";

export default function App() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div className="h-full grid place-items-center text-slate-500">Laddar…</div>;
  if (!isAuthenticated) return <Login />;

  return (
    <div className="h-full flex">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/import" element={<Import />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}
