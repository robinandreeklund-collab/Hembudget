import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";

function RedirectModuleToV2() {
  const { moduleId } = useParams<{ moduleId: string }>();
  return <Navigate to={`/v2/moduler/${moduleId}`} replace />;
}

// === V1 → V2 redirects ===
// V1-frontenden är avvecklad; alla gamla paths skickas till V2-motsvarigheten.
function RedirectV1Student() {
  const { studentId } = useParams<{ studentId: string }>();
  return <Navigate to={`/teacher/v2/elev/${studentId}`} replace />;
}
function RedirectV1Module() {
  const { moduleId } = useParams<{ moduleId: string }>();
  return <Navigate to={`/teacher/v2/modul/${moduleId}`} replace />;
}
function RedirectV1Mortgage() {
  // V2 har ingen direkt motsvarighet för bolåneuppdrag-link (uppdraget
  // visas via /v2/uppdrag som lista). Skicka till hub som fallback.
  return <Navigate to="/v2/uppdrag" replace />;
}

// Roll-medveten root/catchall-redirect: lärare → /teacher/v2,
// elev/demo → /v2/hub. Används som fallback för okända paths
// och som ny / -route. Undviker buggen där lärare loggar in från
// /login/teacher och hamnar på /v2/hub via catchall.
function RoleAwareHomeRedirect() {
  const { role } = useAuth();
  if (role === "teacher") return <Navigate to="/teacher/v2" replace />;
  // Elev: gå via V2RootRedirect som kollar v2_onboarding_completed_at och
  // skickar till /v2/onboarding om den inte är gjord — annars /v2/hub.
  // Tidigare hårdkodades /v2/hub här, vilket skickade nya elever direkt
  // in i dashbornen utan att gå via onboardingen.
  return <V2RootRedirect />;
}
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
import { TeacherForetagOverviewPage } from "./v2/TeacherForetagOverviewPage";
import { TeacherArbetsformedlingenOverviewPage } from "./v2/TeacherArbetsformedlingenOverviewPage";
import { TeacherInsuranceOverviewPage } from "./v2/TeacherInsuranceOverviewPage";
import { ForsakringarV2 } from "./v2/ForsakringarV2";
import { TeacherUtilityOverviewPage } from "./v2/TeacherUtilityOverviewPage";
import { ForbrukningV2 } from "./v2/ForbrukningV2";
import { TeacherRentalOverviewPage } from "./v2/TeacherRentalOverviewPage";
import { BoendemarknadV2 } from "./v2/BoendemarknadV2";
import { ArbetsformedlingenV2 } from "./v2/ArbetsformedlingenV2";
import { TeacherClassesV2 } from "./v2/TeacherClassesV2";
import { TeacherTimeOnTaskV2 } from "./v2/TeacherTimeOnTaskV2";
import { TeacherRubricsV2 } from "./v2/TeacherRubricsV2";
import { TeacherAiPromptsV2 } from "./v2/TeacherAiPromptsV2";
import { AllabolagV2 } from "./v2/AllabolagV2";
import { ModuleViewV2 } from "./v2/ModuleViewV2";
import {
  BizBokforing, BizFakturor, BizLon, BizMoms,
  BizBolagsskatt, BizInstallningar,
} from "./v2/biz/BizPages";
import { BizArsredovisning } from "./v2/biz/BizArsredovisning";
import {
  BizOfferter, BizJobb, BizMarknad, BizBeslut, BizLeverantorer,
} from "./v2/biz/BizGameMotorPages";
import { BizBank } from "./v2/biz/BizBank";
import { TeacherForetagKlassPage } from "./v2/TeacherForetagKlassPage";
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
import { BankIDConfirmV2 } from "./v2/BankIDConfirmV2";
import { TeacherMariaOverviewPage } from "./v2/TeacherMariaOverviewPage";
import { TeacherBankIDOverviewPage } from "./v2/TeacherBankIDOverviewPage";
import { TxV2 } from "./v2/TxV2";
import { MeddelandenV2 } from "./v2/MeddelandenV2";
import { PortfolioV2 } from "./v2/PortfolioV2";
import { TeacherMessagesOverviewPage } from "./v2/TeacherMessagesOverviewPage";
import { TeacherPortfolioOverviewPage } from "./v2/TeacherPortfolioOverviewPage";
import { MailDetailV2 } from "./v2/MailDetailV2";
import { UppdragV2 } from "./v2/UppdragV2";
import { TeacherUppdragOverviewPage } from "./v2/TeacherUppdragOverviewPage";
import { KompetensV2 } from "./v2/KompetensV2";
import { TeacherKompetensOverviewPage } from "./v2/TeacherKompetensOverviewPage";
import { GuideProvider } from "./v2/guides/GuideContext";
import { GuideOverlay } from "./v2/guides/GuideOverlay";
import { V2Topbar } from "./v2/V2Topbar";
import { V2DevFooter } from "./v2/V2DevFooter";
import { EchoDrawer } from "./v2/EchoDrawer";
import { MalV2 } from "./v2/MalV2";
import { PostladanV2 } from "./v2/PostladanV2";
import { HandelserV2 } from "./v2/HandelserV2";
import { HuvudbokV2 } from "./v2/HuvudbokV2";
import { V2Bootstrap } from "./v2/V2Bootstrap";
import { V2RootRedirect } from "./v2/V2RootRedirect";
// REMOVED V1: import { DashboardV2Guard } from "./v2/DashboardV2Guard";
import { V2DevSwitcher } from "./v2/V2DevSwitcher";
import { V2RosterPage } from "./v2/V2RosterPage";
import { TeacherHubV2 } from "./v2/TeacherHubV2";
import { TeacherStudentDetailV2 } from "./v2/TeacherStudentDetailV2";
import { TeacherReflectionsV2 } from "./v2/TeacherReflectionsV2";
import { TeacherMailboxV2 } from "./v2/TeacherMailboxV2";
import { TeacherMariaListV2 } from "./v2/TeacherMariaListV2";
import { TeacherPedagogicsV2 } from "./v2/TeacherPedagogicsV2";
import { TeacherCreateStudentV2 } from "./v2/TeacherCreateStudentV2";
import { TeacherStudentHistoryV2 } from "./v2/TeacherStudentHistoryV2";
import { TeacherModuleLibraryV2 } from "./v2/TeacherModuleLibraryV2";
import { TeacherModuleEditV2 } from "./v2/TeacherModuleEditV2";
// REMOVED V1: import Dashboard from "./pages/Dashboard";
// REMOVED V1: import Transactions from "./pages/Transactions";
// REMOVED V1: import Budget from "./pages/Budget";
// REMOVED V1: import Chat from "./pages/Chat";
// REMOVED V1: import Scenarios from "./pages/Scenarios";
// REMOVED V1: import Loans from "./pages/Loans";
// REMOVED V1: import Transfers from "./pages/Transfers";
// REMOVED V1: import Upcoming from "./pages/Upcoming";
// REMOVED V1: import Tax from "./pages/Tax";
// REMOVED V1: import Reports from "./pages/Reports";
// REMOVED V1: import Settings from "./pages/Settings";
import Login from "./pages/Login";
// REMOVED V1: import Import from "./pages/Import";
// REMOVED V1: import Funds from "./pages/Funds";
// REMOVED V1: import Investments from "./pages/Investments";
// REMOVED V1: import TeacherCredit from "./pages/TeacherCredit";
// REMOVED V1: import TeacherInvestments from "./pages/TeacherInvestments";
// REMOVED V1: import TeacherWellbeing from "./pages/TeacherWellbeing";
// REMOVED V1: import Salaries from "./pages/Salaries";
// REMOVED V1: import Arbetsgivare from "./pages/Arbetsgivare";
import Bank from "./pages/Bank";
// REMOVED V1: import TeacherNegotiations from "./pages/TeacherNegotiations";
// REMOVED V1: import Attachments from "./pages/Attachments";
// REMOVED V1: import Utility from "./pages/Utility";
import TibberCallback from "./pages/TibberCallback";
// REMOVED V1: import Teacher from "./pages/Teacher";
// REMOVED V1: import StudentDetail from "./pages/StudentDetail";
import Onboarding from "./pages/Onboarding";
// REMOVED V1: import MyBatches from "./pages/MyBatches";
// REMOVED V1: import AllBatches from "./pages/AllBatches";
// REMOVED V1: import AssignmentMatrix from "./pages/AssignmentMatrix";
// REMOVED V1: import MortgageDecision from "./pages/MortgageDecision";
// REMOVED V1: import Messages from "./pages/Messages";
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
// REMOVED V1: import MyAchievements from "./pages/MyAchievements";
// REMOVED V1: import MyModules from "./pages/MyModules";
// REMOVED V1: import TeacherModules from "./pages/TeacherModules";
// REMOVED V1: import TeacherModuleEdit from "./pages/TeacherModuleEdit";
// REMOVED V1: import TeacherReflections from "./pages/TeacherReflections";
// REMOVED V1: import TeacherRubrics from "./pages/TeacherRubrics";
// REMOVED V1: import TeacherTimeOnTask from "./pages/TeacherTimeOnTask";
// REMOVED V1: import PeerReview from "./pages/PeerReview";
// REMOVED V1: import AdminAI from "./pages/AdminAI";
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
        {/* V2 BankID-mobil-confirm · samma princip som /bank/sign — */}
        {/* PUBLIK route, scannas via QR från desktop-bankid-vyn */}
        <Route
          path="/v2/bankid/confirm/:token"
          element={<BankIDConfirmV2 />}
        />
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

  // V2 är aktivt på alla /v2/* och /teacher/* — då visas V2DevFooter
  // istället för den gamla feta dev-bannern. Echo-drawern mountas
  // ALLTID (oavsett path) eftersom topbaren har Echo-knappen och
  // drawern måste vara mountad för att lyssna på 'echo-open'-eventet.
  // V1 är AVVECKLAD · alla autentiserade vyer renderar nu V2-skalet,
  // även /dashboard, /, catchall och legacy-redirects. Tidigare blixtrade
  // V1 Sidebar/paper-bg under tiden RoleAwareHomeRedirect hann skicka
  // eleven till /v2/hub. Vi behåller useLocation() bara för att tvinga
  // re-render vid path-change så routes hänger med konsekvent.
  useLocation();
  const isV2Path = true;

  return (
    <GuideProvider>
    <div className={isV2Path ? "v2-shell" : "h-full flex flex-col"}>
      <DemoBanner />
      {!isV2Path && <V2DevSwitcher />}
      <GuideOverlay />
      <EchoDrawer />
      {isV2Path && (
        <V2DevFooter
          role={role || "student"}
          isSuperAdmin={!!v2Status?.is_super_admin}
        />
      )}
      {/* App-nivå V2Topbar · single instance · stays put under flip
       * (matchar prototyp där .topbar är utanför .app som flips).
       * Per-page <V2Topbar> är no-ops via singleton-mönster i komponenten. */}
      {isV2Path && (
        <V2Topbar
          status={{
            role: role || "student",
            is_super_admin: !!v2Status?.is_super_admin,
          }}
        />
      )}
      <div className={isV2Path ? "v2-flip-perspective" : "flex-1 flex flex-col md:flex-row min-h-0"}>
      {!isV2Path && <Sidebar />}
      <main
        className={isV2Path ? "v2-flip-target" : "flex-1 overflow-y-auto"}
        id={isV2Path ? "v2-flip-target" : undefined}
      >
        {!isV2Path && <MobileTopBar />}
        {role === "teacher" && asStudent && <ImpersonationBanner />}
        <Routes>
          {/* "/" går genom V2RootRedirect: super-admin auto-routas till
              /v2/hub, studenter utan v2-onboarding till /v2/onboarding,
              övriga till /dashboard (v1). */}
          <Route path="/" element={<V2RootRedirect />} />
          {/* === V1-redirects · alla gamla paths skickas till V2-motsvarigheten ===
              V1-frontenden är avvecklad. Endast publika routes (login,
              docs, /bank/sign etc.) ligger kvar i den ej-inloggade rendern. */}
          <Route path="/teacher" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/students/:studentId" element={<RedirectV1Student />} />
          <Route path="/teacher/all-batches" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/matrix" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/modules" element={<Navigate to="/teacher/v2/moduler" replace />} />
          <Route path="/teacher/modules/:moduleId" element={<RedirectV1Module />} />
          <Route path="/teacher/reflections" element={<Navigate to="/teacher/v2/reflektioner" replace />} />
          <Route path="/teacher/rubrics" element={<Navigate to="/teacher/v2/rubrics" replace />} />
          <Route path="/teacher/time-on-task" element={<Navigate to="/teacher/v2/time-on-task" replace />} />
          <Route path="/teacher/negotiations" element={<Navigate to="/teacher/v2/maria" replace />} />
          <Route path="/teacher/admin-ai" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/investments" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/credit" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/teacher/wellbeing" element={<Navigate to="/teacher/v2" replace />} />
          <Route path="/peer-review" element={<Navigate to="/v2/hub" replace />} />
          <Route path="/my-batches" element={<Navigate to="/v2/hub" replace />} />
          <Route path="/messages" element={<Navigate to="/v2/meddelanden" replace />} />
          <Route path="/modules" element={<Navigate to="/v2/moduler" replace />} />
          <Route path="/modules/:moduleId" element={<RedirectModuleToV2 />} />
          <Route path="/achievements" element={<Navigate to="/v2/portfolio" replace />} />
          <Route path="/mortgage/:assignmentId" element={<RedirectV1Mortgage />} />

          {/* Publika info-sidor (auth-läge har dem också) */}
          <Route path="/demo/scroll-story" element={<ScrollStoryDemo />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/larguider" element={<Lararguider />} />
          <Route path="/lgr22" element={<Lgr22 />} />
          <Route path="/rubriker" element={<Rubriker />} />
          <Route path="/echo" element={<EchoAi />} />
          {/* === V2 (numera default) === */}
          <Route path="/v2" element={<V2Bootstrap />} />
          <Route path="/v2/onboarding" element={<OnboardingV2 />} />
          <Route path="/v2/hub" element={<HubV2 />} />
          <Route path="/v2/banken" element={<BankV2 />} />
          <Route path="/v2/budget" element={<BudgetV2 />} />
          <Route path="/v2/arbetsgivaren" element={<ArbetsgivarenV2 />} />
          <Route path="/v2/skatten" element={<SkattenV2 />} />
          <Route path="/v2/lan" element={<LanV2 />} />
          <Route path="/v2/forsakringar" element={<ForsakringarV2 />} />
          <Route path="/v2/handelser" element={<HandelserV2 />} />
          <Route path="/v2/huvudbok" element={<HuvudbokV2 />} />
          <Route path="/v2/forbrukning" element={<ForbrukningV2 />} />
          {/* Boendemarknaden — wrapper med tabbar för hyra + köp/sälj.
              /v2/hyresvarden är bakåt-kompat-alias så befintliga länkar
              fortsätter fungera. */}
          <Route path="/v2/boendemarknad" element={<BoendemarknadV2 />} />
          <Route path="/v2/hyresvarden" element={<BoendemarknadV2 />} />
          {/* Aktör 10 · Arbetsförmedlingen (Sprint 6 · A1-A5) */}
          <Route path="/v2/arbetsformedlingen" element={<ArbetsformedlingenV2 />} />
          <Route path="/v2/pension" element={<PensionV2 />} />
          <Route path="/v2/avanza" element={<AvanzaV2 />} />
          <Route path="/v2/aktier" element={<AktierV2 />} />
          <Route path="/v2/bokforing" element={<BokforingV2 />} />
          <Route path="/v2/moduler" element={<ModulerV2 />} />
          {/* Bug #12 · Modul-detalj v2 */}
          <Route path="/v2/moduler/:moduleId" element={<ModuleViewV2 />} />
          {/* Bug #7-utbyggnad · Företagsläget · 6 vyer */}
          {/* Allabolag · klass-skopig scoreboard */}
          <Route path="/v2/allabolag" element={<AllabolagV2 />} />
          {/* Årsredovisning · AI Bolagsverket */}
          <Route path="/v2/foretag/arsredovisning" element={<BizArsredovisning />} />
          <Route path="/v2/foretag/bokforing" element={<BizBokforing />} />
          <Route path="/v2/foretag/fakturor" element={<BizFakturor />} />
          <Route path="/v2/foretag/lon" element={<BizLon />} />
          <Route path="/v2/foretag/moms" element={<BizMoms />} />
          <Route path="/v2/foretag/bolagsskatt" element={<BizBolagsskatt />} />
          <Route path="/v2/foretag/installningar" element={<BizInstallningar />} />
          <Route path="/v2/foretag/offerter" element={<BizOfferter />} />
          <Route path="/v2/foretag/jobb" element={<BizJobb />} />
          <Route path="/v2/foretag/marknad" element={<BizMarknad />} />
          <Route path="/v2/foretag/beslut" element={<BizBeslut />} />
          <Route path="/v2/foretag/leverantorer" element={<BizLeverantorer />} />
          <Route path="/v2/foretag/bank" element={<BizBank />} />
          <Route path="/teacher/v2/foretag-klass" element={<TeacherForetagKlassPage />} />
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
          <Route
            path="/v2/bankid/confirm/:token"
            element={<BankIDConfirmV2 />}
          />
          <Route path="/v2/tx/:txId" element={<TxV2 />} />
          <Route path="/v2/meddelanden" element={<MeddelandenV2 />} />
          <Route path="/v2/portfolio" element={<PortfolioV2 />} />
          <Route
            path="/v2/kompetens/:competencyId"
            element={<KompetensV2 />}
          />
          <Route path="/v2/uppdrag" element={<UppdragV2 />} />
          <Route
            path="/v2/postladan/:mailId"
            element={<MailDetailV2 />}
          />
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
          <Route
            path="/teacher/v2/uppdrag/:studentId"
            element={<TeacherUppdragOverviewPage />}
          />
          <Route
            path="/teacher/v2/foretag/:studentId"
            element={<TeacherForetagOverviewPage />}
          />
          <Route
            path="/teacher/v2/arbetsformedlingen/:studentId"
            element={<TeacherArbetsformedlingenOverviewPage />}
          />
          <Route
            path="/teacher/v2/kompetens/:studentId/:competencyId"
            element={<TeacherKompetensOverviewPage />}
          />
          <Route path="/v2/mal" element={<MalV2 />} />
          <Route path="/v2/postladan" element={<PostladanV2 />} />
          <Route path="/teacher/v2" element={<TeacherHubV2 />} />
          <Route
            path="/teacher/v2/roster"
            element={<V2RosterPage />}
          />
          <Route
            path="/teacher/v2/elev/:studentId"
            element={<TeacherStudentDetailV2 />}
          />
          <Route
            path="/teacher/v2/reflektioner"
            element={<TeacherReflectionsV2 />}
          />
          <Route
            path="/teacher/v2/postlador"
            element={<TeacherMailboxV2 />}
          />
          <Route
            path="/teacher/v2/maria"
            element={<TeacherMariaListV2 />}
          />
          <Route
            path="/teacher/v2/pedagogik"
            element={<TeacherPedagogicsV2 />}
          />
          <Route
            path="/teacher/v2/skapa"
            element={<TeacherCreateStudentV2 />}
          />
          {/* Bug #1 · Klass-hantering */}
          <Route
            path="/teacher/v2/klasser"
            element={<TeacherClassesV2 />}
          />
          {/* Bug #16 · Time-on-task v2 */}
          <Route
            path="/teacher/v2/time-on-task"
            element={<TeacherTimeOnTaskV2 />}
          />
          {/* Bug #17 · Rubrics v2 */}
          <Route
            path="/teacher/v2/rubrics"
            element={<TeacherRubricsV2 />}
          />
          {/* Lärar-AI-laboratorium · /teacher/v2/ai-prompts */}
          <Route
            path="/teacher/v2/ai-prompts"
            element={<TeacherAiPromptsV2 />}
          />
          <Route
            path="/teacher/v2/historik/:studentId"
            element={<TeacherStudentHistoryV2 />}
          />
          <Route
            path="/teacher/v2/moduler"
            element={<TeacherModuleLibraryV2 />}
          />
          <Route
            path="/teacher/v2/modul/:moduleId"
            element={<TeacherModuleEditV2 />}
          />
          {/* === V1 elev-routes · alla redirectas till V2 === */}
          <Route path="/dashboard" element={<RoleAwareHomeRedirect />} />
          <Route path="/transactions" element={<Navigate to="/v2/banken" replace />} />
          <Route path="/import" element={<Navigate to="/v2/banken" replace />} />
          <Route path="/budget" element={<Navigate to="/v2/budget" replace />} />
          <Route path="/chat" element={<Navigate to="/v2/hub" replace />} />
          <Route path="/scenarios" element={<Navigate to="/v2/simulator" replace />} />
          <Route path="/loans" element={<Navigate to="/v2/lan" replace />} />
          <Route path="/funds" element={<Navigate to="/v2/avanza" replace />} />
          <Route path="/investments" element={<Navigate to="/v2/avanza" replace />} />
          <Route path="/transfers" element={<Navigate to="/v2/banken" replace />} />
          <Route path="/upcoming" element={<Navigate to="/v2/banken" replace />} />
          <Route path="/salaries" element={<Navigate to="/v2/arbetsgivaren" replace />} />
          <Route path="/arbetsgivare" element={<Navigate to="/v2/arbetsgivaren" replace />} />
          <Route path="/bank" element={<Navigate to="/v2/banken" replace />} />
          {/* /bank/sign behåller V1-Bank-komponenten — det är en publik
              sign-vy som scannas via QR från desktop. Ingen V2-motsvarighet
              ännu eftersom flödet är specifikt för QR-mobil-confirm. */}
          <Route path="/bank/sign" element={<Bank />} />
          <Route path="/attachments" element={<Navigate to="/v2/banken" replace />} />
          <Route path="/utility" element={<Navigate to="/v2/forbrukning" replace />} />
          <Route path="/tax" element={<Navigate to="/v2/skatten" replace />} />
          <Route path="/reports" element={<Navigate to="/v2/portfolio" replace />} />
          <Route path="/settings" element={<Navigate to="/v2/hub" replace />} />
          <Route path="/Callback" element={<TibberCallback />} />
          <Route path="*" element={<RoleAwareHomeRedirect />} />
        </Routes>
      </main>
      </div>
    </div>
    </GuideProvider>
  );
}
