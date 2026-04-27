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
import Investments from "./pages/Investments";
import TeacherCredit from "./pages/TeacherCredit";
import TeacherInvestments from "./pages/TeacherInvestments";
import TeacherWellbeing from "./pages/TeacherWellbeing";
import Salaries from "./pages/Salaries";
import Arbetsgivare from "./pages/Arbetsgivare";
import Bank from "./pages/Bank";
import TeacherNegotiations from "./pages/TeacherNegotiations";
import Attachments from "./pages/Attachments";
import Utility from "./pages/Utility";
import TibberCallback from "./pages/TibberCallback";
import Teacher from "./pages/Teacher";
import StudentDetail from "./pages/StudentDetail";
import Onboarding from "./pages/Onboarding";
import MyBatches from "./pages/MyBatches";
import AllBatches from "./pages/AllBatches";
import AssignmentMatrix from "./pages/AssignmentMatrix";
import MortgageDecision from "./pages/MortgageDecision";
import Messages from "./pages/Messages";
import LandingSwitch from "./pages/LandingSwitch";
import LoginChoice from "./pages/LoginChoice";
import TeacherLogin from "./pages/TeacherLogin";
import TeacherSignup from "./pages/TeacherSignup";
import ParentSignup from "./pages/ParentSignup";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import StudentLogin from "./pages/StudentLogin";
import DemoChoice from "./pages/DemoChoice";
import Docs from "./pages/Docs";
import MyAchievements from "./pages/MyAchievements";
import MyModules from "./pages/MyModules";
import ModuleView from "./pages/ModuleView";
import TeacherModules from "./pages/TeacherModules";
import TeacherModuleEdit from "./pages/TeacherModuleEdit";
import TeacherReflections from "./pages/TeacherReflections";
import TeacherRubrics from "./pages/TeacherRubrics";
import TeacherTimeOnTask from "./pages/TeacherTimeOnTask";
import PeerReview from "./pages/PeerReview";
import AdminAI from "./pages/AdminAI";
import { DemoBanner } from "./components/DemoBanner";

export default function App() {
  const {
    isAuthenticated, loading, initialized, backendError,
    role, asStudent, studentMeta,
  } = useAuth();
  if (loading) return <div className="h-full grid place-items-center text-slate-700">Laddar…</div>;
  if (initialized === null) return <BackendSetup error={backendError ?? undefined} />;
  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/" element={<LandingSwitch />} />
        <Route path="/login" element={<LoginChoice />} />
        <Route path="/login/teacher" element={<TeacherLogin />} />
        <Route path="/signup/teacher" element={<TeacherSignup />} />
        <Route path="/signup/parent" element={<ParentSignup />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/login/student" element={<StudentLogin />} />
        <Route path="/demo" element={<DemoChoice />} />
        <Route path="/docs" element={<Docs />} />
        {/* Fallback: behåll gamla kombinerade Login-komponenten som extra
            backup i fall något djuplänkar dit */}
        <Route path="/login/legacy" element={<Login />} />
        <Route path="*" element={<LandingSwitch />} />
      </Routes>
    );
  }

  // Elev som inte är klar med onboarding → tvingas dit
  if (
    role === "student" && studentMeta && !studentMeta.onboarding_completed
  ) {
    return (
      <>
        <DemoBanner />
        <Onboarding />
      </>
    );
  }

  // Lärar-vyn använder nu samma sidebar som resten av plattformen
  // (sektioner: Lärarverktyg + Eget konto). Tidigare doldes hela
  // sidebaren när läraren inte valt elev — då var knappraden i
  // Teacher.tsx enda navigationen, vilket var inkonsekvent.

  return (
    <div className="h-full flex flex-col">
      <DemoBanner />
      <div className="flex-1 flex flex-col md:flex-row min-h-0">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <MobileTopBar />
        {role === "teacher" && asStudent && <ImpersonationBanner />}
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/teacher" element={<Teacher />} />
          <Route path="/teacher/students/:studentId" element={<StudentDetail />} />
          <Route path="/teacher/all-batches" element={<AllBatches />} />
          <Route path="/teacher/matrix" element={<AssignmentMatrix />} />
          <Route path="/mortgage/:assignmentId" element={<MortgageDecision />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/modules" element={<MyModules />} />
          <Route path="/modules/:moduleId" element={<ModuleView />} />
          <Route path="/achievements" element={<MyAchievements />} />
          <Route path="/teacher/modules" element={<TeacherModules />} />
          <Route path="/teacher/modules/:moduleId" element={<TeacherModuleEdit />} />
          <Route path="/teacher/reflections" element={<TeacherReflections />} />
          <Route path="/teacher/rubrics" element={<TeacherRubrics />} />
          <Route path="/teacher/time-on-task" element={<TeacherTimeOnTask />} />
          <Route path="/teacher/negotiations" element={<TeacherNegotiations />} />
          <Route path="/teacher/admin-ai" element={<AdminAI />} />
          <Route path="/teacher/investments" element={<TeacherInvestments />} />
          <Route path="/teacher/credit" element={<TeacherCredit />} />
          <Route path="/teacher/wellbeing" element={<TeacherWellbeing />} />
          <Route path="/peer-review" element={<PeerReview />} />
          <Route path="/my-batches" element={<MyBatches />} />
          {/* Dashboard är nu gemensam för elev + lärare-impersonering.
              De pedagogiska EkoDashboard-bitarna (greeting, budget-bars,
              oväntade utgifter, uppdrag, streak, mastery) ligger som
              StudentPedagogyCards-komponent högst upp i Dashboard.tsx
              så elev + lärar-vy aldrig divergerar. */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/import" element={<Import />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/funds" element={<Funds />} />
          <Route path="/investments" element={<Investments />} />
          <Route path="/transfers" element={<Transfers />} />
          <Route path="/upcoming" element={<Upcoming />} />
          <Route path="/salaries" element={<Salaries />} />
          <Route path="/arbetsgivare" element={<Arbetsgivare />} />
          <Route path="/bank" element={<Bank />} />
          <Route path="/bank/sign" element={<Bank />} />
          <Route path="/attachments" element={<Attachments />} />
          <Route path="/utility" element={<Utility />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/Callback" element={<TibberCallback />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
      </div>
    </div>
  );
}
