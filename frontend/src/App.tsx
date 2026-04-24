import { Navigate, Route, Routes } from "react-router-dom";
import { BackendSetup } from "./components/BackendSetup";
import { ImpersonationBanner } from "./components/ImpersonationBanner";
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
import Utility from "./pages/Utility";
import TibberCallback from "./pages/TibberCallback";
import Teacher from "./pages/Teacher";
import StudentDetail from "./pages/StudentDetail";
import Onboarding from "./pages/Onboarding";
import MyBatches from "./pages/MyBatches";
import AllBatches from "./pages/AllBatches";
import EkoDashboard from "./pages/EkoDashboard";
import AssignmentMatrix from "./pages/AssignmentMatrix";
import MortgageDecision from "./pages/MortgageDecision";
import Messages from "./pages/Messages";

export default function App() {
  const {
    isAuthenticated, loading, initialized, backendError,
    role, asStudent, studentMeta,
  } = useAuth();
  if (loading) return <div className="h-full grid place-items-center text-slate-700">Laddar…</div>;
  if (initialized === null) return <BackendSetup error={backendError ?? undefined} />;
  if (!isAuthenticated) return <Login />;

  // Elev som inte är klar med onboarding → tvingas dit
  if (
    role === "student" && studentMeta && !studentMeta.onboarding_completed
  ) {
    return <Onboarding />;
  }

  // Lärare utan vald elev → bara lärarpanelen syns (ingen sidebar mot elevdata)
  const teacherRootOnly = role === "teacher" && !asStudent;

  return (
    <div className="h-full flex flex-col md:flex-row">
      {!teacherRootOnly && <Sidebar />}
      <main className="flex-1 overflow-y-auto">
        {!teacherRootOnly && <MobileTopBar />}
        {role === "teacher" && asStudent && <ImpersonationBanner />}
        <Routes>
          {teacherRootOnly ? (
            <>
              <Route path="/teacher" element={<Teacher />} />
              <Route path="/teacher/students/:studentId" element={<StudentDetail />} />
              <Route path="/teacher/all-batches" element={<AllBatches />} />
              <Route path="/teacher/matrix" element={<AssignmentMatrix />} />
              <Route path="/mortgage/:assignmentId" element={<MortgageDecision />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="*" element={<Navigate to="/teacher" replace />} />
            </>
          ) : (
            <>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/teacher" element={<Teacher />} />
              <Route path="/teacher/students/:studentId" element={<StudentDetail />} />
              <Route path="/teacher/all-batches" element={<AllBatches />} />
              <Route path="/teacher/matrix" element={<AssignmentMatrix />} />
              <Route path="/mortgage/:assignmentId" element={<MortgageDecision />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="/my-batches" element={<MyBatches />} />
              <Route
                path="/dashboard"
                element={role === "student" ? <EkoDashboard /> : <Dashboard />}
              />
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
              <Route path="/utility" element={<Utility />} />
              <Route path="/tax" element={<Tax />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/Callback" element={<TibberCallback />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </>
          )}
        </Routes>
      </main>
    </div>
  );
}
