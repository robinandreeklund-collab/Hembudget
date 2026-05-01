import { Navigate, Route, Routes } from "react-router-dom";
import { BackendSetup } from "./components/BackendSetup";
import { ImpersonationBanner } from "./components/ImpersonationBanner";
import { MobileTopBar, Sidebar } from "./components/Sidebar";
import { useAuth } from "./hooks/useAuth";
import { OnboardingV2 } from "./v2/OnboardingV2";
import { HubV2 } from "./v2/HubV2";
import { BankV2 } from "./v2/BankV2";
import { BudgetV2 } from "./v2/BudgetV2";
import { ArbetsgivarenV2 } from "./v2/ArbetsgivarenV2";
import { SkattenV2 } from "./v2/SkattenV2";
import { LanV2 } from "./v2/LanV2";
import { TeacherCreditOverviewPage } from "./v2/TeacherCreditOverviewPage";
import { TeacherTaxOverviewPage } from "./v2/TeacherTaxOverviewPage";
import { TeacherEmployerOverviewPage } from "./v2/TeacherEmployerOverviewPage";
import { TeacherInsuranceOverviewPage } from "./v2/TeacherInsuranceOverviewPage";
import { ForsakringarV2 } from "./v2/ForsakringarV2";
import { TeacherUtilityOverviewPage } from "./v2/TeacherUtilityOverviewPage";
import { ForbrukningV2 } from "./v2/ForbrukningV2";
import { TeacherRentalOverviewPage } from "./v2/TeacherRentalOverviewPage";
import { HyresvardenV2 } from "./v2/HyresvardenV2";
import { PensionV2 } from "./v2/PensionV2";
import { AvanzaV2 } from "./v2/AvanzaV2";
import { AktierV2 } from "./v2/AktierV2";
import { TeacherPensionOverviewPage } from "./v2/TeacherPensionOverviewPage";
import { TeacherAvanzaOverviewPage } from "./v2/TeacherAvanzaOverviewPage";
import { BokforingV2 } from "./v2/BokforingV2";
import { TeacherBokforingOverviewPage } from "./v2/TeacherBokforingOverviewPage";
import { ModulerV2 } from "./v2/ModulerV2";
import { TeacherModulerOverviewPage } from "./v2/TeacherModulerOverviewPage";
import { SimulatorV2 } from "./v2/SimulatorV2";
import { LanekalkylatorV2 } from "./v2/LanekalkylatorV2";
import { TeacherSimulatorOverviewPage } from "./v2/TeacherSimulatorOverviewPage";
import { FeedbackV2 } from "./v2/FeedbackV2";
import { TeacherFeedbackOverviewPage } from "./v2/TeacherFeedbackOverviewPage";
import { MariaV2 } from "./v2/MariaV2";
import { BankIDV2 } from "./v2/BankIDV2";
import { TeacherMariaOverviewPage } from "./v2/TeacherMariaOverviewPage";
import { TeacherBankIDOverviewPage } from "./v2/TeacherBankIDOverviewPage";
import { TxV2 } from "./v2/TxV2";
import { MeddelandenV2 } from "./v2/MeddelandenV2";
import { PortfolioV2 } from "./v2/PortfolioV2";
import { TeacherMessagesOverviewPage } from "./v2/TeacherMessagesOverviewPage";
import { TeacherPortfolioOverviewPage } from "./v2/TeacherPortfolioOverviewPage";
import { MalV2 } from "./v2/MalV2";
import { PostladanV2 } from "./v2/PostladanV2";
import { V2Bootstrap } from "./v2/V2Bootstrap";
import { V2RootRedirect } from "./v2/V2RootRedirect";
import { DashboardV2Guard } from "./v2/DashboardV2Guard";
import { V2DevSwitcher } from "./v2/V2DevSwitcher";
import { V2RosterPage } from "./v2/V2RosterPage";
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
import Terms from "./pages/Terms";
import Faq from "./pages/Faq";
import Lararguider from "./pages/Lararguider";
import Lgr22 from "./pages/Lgr22";
import Rubriker from "./pages/Rubriker";
import EchoAi from "./pages/EchoAi";
import ScrollStoryDemo from "./pages/ScrollStoryDemo";
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
import { useEffect, useState } from "react";
import { v2Api, type V2Status } from "./v2/api";

export default function App() {
  const {
    isAuthenticated, loading, initialized, backendError,
    role, asStudent, studentMeta,
  } = useAuth();

  // V2-status hämtas parallellt med studentMeta. Om eleven har v2_enabled
  // ska vi inte visa v1-onboardingen utan låta routes ta över → /dashboard
  // → DashboardV2Guard → /v2/onboarding (eller /v2/hub om klar).
  const [v2Status, setV2Status] = useState<V2Status | null>(null);
  const [v2Loaded, setV2Loaded] = useState(false);

  // Rensa lärar-dev-flaggan v2_force_v1 så fort en elev loggar in.
  // Annars läcker flaggan från en lärare som klickade "Tvinga v1" i
  // samma webbläsare → eleven hamnar i v1 trots att v2_enabled är på.
  // Lärar-flaggan är ett dev-verktyg och ska aldrig påverka elev-routing.
  useEffect(() => {
    if (isAuthenticated && role === "student") {
      try {
        window.localStorage.removeItem("v2_force_v1");
      } catch {
        // localStorage kan vara avstängt i privat-läge — ignorera
      }
    }
  }, [isAuthenticated, role]);

  useEffect(() => {
    if (isAuthenticated && role === "student") {
      v2Api.status()
        .then(setV2Status)
        .catch(() => undefined)
        .finally(() => setV2Loaded(true));
    } else {
      setV2Loaded(true);
    }
  }, [isAuthenticated, role]);
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
        <Route path="/demo/scroll-story" element={<ScrollStoryDemo />} />
        {/* /bank/sign är PUBLIK — telefonen som skannar QR:en behöver
            INTE vara inloggad. Sessionstoken + PIN är säkerheten.
            Samma route i båda blocken så att inloggade lärare/föräldrar
            också når sign-vyn utan att kicks tillbaka till /dashboard. */}
        <Route path="/bank/sign" element={<Bank />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/faq" element={<Faq />} />
        <Route path="/larguider" element={<Lararguider />} />
        <Route path="/lgr22" element={<Lgr22 />} />
        <Route path="/rubriker" element={<Rubriker />} />
        <Route path="/echo" element={<EchoAi />} />
        {/* Fallback: behåll gamla kombinerade Login-komponenten som extra
            backup i fall något djuplänkar dit */}
        <Route path="/login/legacy" element={<Login />} />
        <Route path="*" element={<LandingSwitch />} />
      </Routes>
    );
  }

  // Visa laddningsindikator tills v2-status är klar — annars riskerar
  // vi att v1-onboarding flashar för v2-elever (race condition).
  if (role === "student" && !v2Loaded) {
    return <div className="h-full grid place-items-center text-slate-700">Laddar…</div>;
  }

  // Elev som inte är klar med onboarding → tvingas dit
  // UNDANTAG: om eleven har v2_enabled, skip v1-onboarding och låt
  // DashboardV2Guard routa till /v2/onboarding istället.
  if (
    role === "student" && studentMeta && !studentMeta.onboarding_completed
    && !v2Status?.v2_eligible
  ) {
    return (
      <>
        <DemoBanner />
        <Onboarding />
      </>
    );
  }

  // V2-elev som inte gjort v2-onboarding → tvinga dit
  // (redundant med DashboardV2Guard men säkrare)
  if (
    role === "student" && v2Status?.v2_eligible
    && !v2Status.v2_onboarding_completed
  ) {
    // Låt routes köra · V2RootRedirect → /v2/onboarding
  }

  // Lärar-vyn använder nu samma sidebar som resten av plattformen
  // (sektioner: Lärarverktyg + Eget konto). Tidigare doldes hela
  // sidebaren när läraren inte valt elev — då var knappraden i
  // Teacher.tsx enda navigationen, vilket var inkonsekvent.

  return (
    <div className="h-full flex flex-col">
      <DemoBanner />
      <V2DevSwitcher />
      <div className="flex-1 flex flex-col md:flex-row min-h-0">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <MobileTopBar />
        {role === "teacher" && asStudent && <ImpersonationBanner />}
        <Routes>
          {/* "/" går genom V2RootRedirect: super-admin auto-routas till
              /v2/hub, studenter utan v2-onboarding till /v2/onboarding,
              övriga till /dashboard (v1). */}
          <Route path="/" element={<V2RootRedirect />} />
          <Route path="/teacher" element={<Teacher />} />
          <Route path="/teacher/students/:studentId" element={<StudentDetail />} />
          <Route path="/teacher/all-batches" element={<AllBatches />} />
          <Route path="/teacher/matrix" element={<AssignmentMatrix />} />
          <Route path="/mortgage/:assignmentId" element={<MortgageDecision />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/demo/scroll-story" element={<ScrollStoryDemo />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/larguider" element={<Lararguider />} />
          <Route path="/lgr22" element={<Lgr22 />} />
          <Route path="/rubriker" element={<Rubriker />} />
          <Route path="/echo" element={<EchoAi />} />
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
          {/* === V2 (parallell migration) === */}
          <Route path="/v2" element={<V2Bootstrap />} />
          <Route path="/v2/onboarding" element={<OnboardingV2 />} />
          <Route path="/v2/hub" element={<HubV2 />} />
          <Route path="/v2/banken" element={<BankV2 />} />
          <Route path="/v2/budget" element={<BudgetV2 />} />
          <Route path="/v2/arbetsgivaren" element={<ArbetsgivarenV2 />} />
          <Route path="/v2/skatten" element={<SkattenV2 />} />
          <Route path="/v2/lan" element={<LanV2 />} />
          <Route path="/v2/forsakringar" element={<ForsakringarV2 />} />
          <Route path="/v2/forbrukning" element={<ForbrukningV2 />} />
          <Route path="/v2/hyresvarden" element={<HyresvardenV2 />} />
          <Route path="/v2/pension" element={<PensionV2 />} />
          <Route path="/v2/avanza" element={<AvanzaV2 />} />
          <Route path="/v2/aktier" element={<AktierV2 />} />
          <Route path="/v2/bokforing" element={<BokforingV2 />} />
          <Route path="/v2/moduler" element={<ModulerV2 />} />
          <Route path="/v2/simulator" element={<SimulatorV2 />} />
          <Route
            path="/v2/lanekalkylator"
            element={<LanekalkylatorV2 />}
          />
          <Route path="/v2/feedback" element={<FeedbackV2 />} />
          <Route path="/v2/maria" element={<MariaV2 />} />
          <Route
            path="/v2/bankid/:sessionId"
            element={<BankIDV2 />}
          />
          <Route path="/v2/tx/:txId" element={<TxV2 />} />
          <Route path="/v2/meddelanden" element={<MeddelandenV2 />} />
          <Route path="/v2/portfolio" element={<PortfolioV2 />} />
          <Route
            path="/teacher/v2/credit/:studentId"
            element={<TeacherCreditOverviewPage />}
          />
          <Route
            path="/teacher/v2/tax/:studentId"
            element={<TeacherTaxOverviewPage />}
          />
          <Route
            path="/teacher/v2/employer/:studentId"
            element={<TeacherEmployerOverviewPage />}
          />
          <Route
            path="/teacher/v2/insurance/:studentId"
            element={<TeacherInsuranceOverviewPage />}
          />
          <Route
            path="/teacher/v2/utility/:studentId"
            element={<TeacherUtilityOverviewPage />}
          />
          <Route
            path="/teacher/v2/rental/:studentId"
            element={<TeacherRentalOverviewPage />}
          />
          <Route
            path="/teacher/v2/pension/:studentId"
            element={<TeacherPensionOverviewPage />}
          />
          <Route
            path="/teacher/v2/avanza/:studentId"
            element={<TeacherAvanzaOverviewPage />}
          />
          <Route
            path="/teacher/v2/bokforing/:studentId"
            element={<TeacherBokforingOverviewPage />}
          />
          <Route
            path="/teacher/v2/moduler/:studentId"
            element={<TeacherModulerOverviewPage />}
          />
          <Route
            path="/teacher/v2/simulator/:studentId"
            element={<TeacherSimulatorOverviewPage />}
          />
          <Route
            path="/teacher/v2/feedback/:studentId"
            element={<TeacherFeedbackOverviewPage />}
          />
          <Route
            path="/teacher/v2/maria/:studentId"
            element={<TeacherMariaOverviewPage />}
          />
          <Route
            path="/teacher/v2/bankid/:studentId"
            element={<TeacherBankIDOverviewPage />}
          />
          <Route
            path="/teacher/v2/messages/:studentId"
            element={<TeacherMessagesOverviewPage />}
          />
          <Route
            path="/teacher/v2/portfolio/:studentId"
            element={<TeacherPortfolioOverviewPage />}
          />
          <Route path="/v2/mal" element={<MalV2 />} />
          <Route path="/v2/postladan" element={<PostladanV2 />} />
          <Route path="/teacher/v2" element={<V2RosterPage />} />
          {/* /dashboard har en V2-guard: super-admin och elever med
              v2_enabled redirectas till /v2/hub. Övriga får v1. */}
          <Route path="/dashboard" element={<DashboardV2Guard><Dashboard /></DashboardV2Guard>} />
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
