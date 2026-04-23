import { Navigate, Route, Routes } from "react-router-dom";
import { BackendSetup } from "./components/BackendSetup";
import { MobileTopBar, Sidebar } from "./components/Sidebar";
import { useAuth } from "./hooks/useAuth";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Budget from "./pages/Budget";
import Chat from "./pages/Chat";
import Scenarios from "./pages/Scenarios";
import Loans from "./pages/Loans";
import Transfers from "./pages/Transfers";
import Upcoming from "./pages/Upcoming";
import Tax from "./pages/Tax";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Import from "./pages/Import";
import Funds from "./pages/Funds";
import Salaries from "./pages/Salaries";
import Attachments from "./pages/Attachments";

export default function App() {
  const { isAuthenticated, loading, initialized, backendError } = useAuth();
  if (loading) return <div className="h-full grid place-items-center text-slate-700">Laddar…</div>;
  // Om /status inte gick att nå alls → backend-URL behöver konfigureras
  if (initialized === null) return <BackendSetup error={backendError ?? undefined} />;
  if (!isAuthenticated) return <Login />;

  return (
    <div className="h-full flex flex-col md:flex-row">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <MobileTopBar />
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/import" element={<Import />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/funds" element={<Funds />} />
          <Route path="/transfers" element={<Transfers />} />
          <Route path="/upcoming" element={<Upcoming />} />
          <Route path="/salaries" element={<Salaries />} />
          <Route path="/attachments" element={<Attachments />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}
