import { Link } from "react-router-dom";
import {
  AlertTriangle, BarChart3, Briefcase, GraduationCap,
  Home, Lightbulb, MessageCircle, PiggyBank, Receipt, Sparkles,
  TrendingUp, Users,
} from "lucide-react";
import DashboardPreview from "@/components/landing/DashboardPreview";
import BudgetDemo from "@/components/landing/BudgetDemo";
import PdfImportDemo from "@/components/landing/PdfImportDemo";
import TeacherDemo from "@/components/landing/TeacherDemo";

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50">
      <Header />
      <Hero />
      <WhySection />
      <FeaturesSection />
      <FlowSection />
      <CtaSection />
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-brand-600 font-bold text-lg">
          <Sparkles className="w-5 h-5" />
          Ekonomilabbet
        </div>
        <nav className="flex items-center gap-3 text-sm">
          <a href="#funktioner" className="text-slate-700 hover:text-brand-600">
            Funktioner
          </a>
          <a href="#sa-funkar-det" className="text-slate-700 hover:text-brand-600">
            Så funkar det
          </a>
          <Link
            to="/login"
            className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2"
          >
            Logga in
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16 md:py-20 grid md:grid-cols-2 gap-10 items-center">
      <div>
        <div className="inline-flex items-center gap-2 bg-brand-100 text-brand-700 rounded-full px-4 py-1 text-sm mb-6 animate-fadein">
          <GraduationCap className="w-4 h-4" />
          Privatekonomi för skolan
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-slate-900 leading-tight animate-fadeup">
          Lär eleverna hantera sin
          <span className="text-brand-600"> riktiga ekonomi</span>
          <br />– innan de möter den på riktigt.
        </h1>
        <p className="mt-6 text-lg text-slate-600 animate-fadeup delay-100">
          Ekonomilabbet är en interaktiv simulator där varje elev får en egen
          simulerad vardag — yrke, lön, skatt, hyra, lån, räkningar. De lär
          sig budgetera, spara och förstå när livet inte går som planerat.
        </p>
        <div className="mt-8 flex flex-wrap gap-3 animate-fadeup delay-200">
          <Link
            to="/login/teacher"
            className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-medium shadow-lg hover:shadow-xl transition-all"
          >
            Kom igång som lärare
          </Link>
          <Link
            to="/login/student"
            className="bg-white border-2 border-slate-300 hover:border-brand-500 text-slate-700 rounded-lg px-6 py-3 font-medium"
          >
            Jag är elev
          </Link>
        </div>
      </div>
      <div className="animate-fadeup delay-300">
        <DashboardPreview />
      </div>
    </section>
  );
}

function WhySection() {
  const stats = [
    { num: "4 av 10", label: "unga klarar inte en oväntad räkning på 2 000 kr" },
    { num: "60%", label: "av elever har aldrig läst en lönespecifikation" },
    { num: "1 timme", label: "räcker för att prova grunderna i Ekonomilabbet" },
  ];
  return (
    <section className="bg-white border-y border-slate-200 py-16">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 text-brand-600 text-sm font-medium mb-2">
            <AlertTriangle className="w-4 h-4" /> Problem
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900">
            Ekonomi är ett livskunskapsämne.<br />Och det saknas i skolan.
          </h2>
          <p className="mt-4 text-slate-600 max-w-2xl mx-auto">
            Svenska unga lämnar skolan utan grundläggande kunskaper om skatt,
            sparande, lån och budget. Först när de flyttar hemifrån möter de
            verkligheten — ofta för sent.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {stats.map((s, i) => (
            <div
              key={i}
              className="bg-gradient-to-br from-brand-50 to-white border border-brand-100 rounded-xl p-6 text-center hover:shadow-md transition-shadow"
            >
              <div className="text-4xl font-bold text-brand-600 mb-2">
                {s.num}
              </div>
              <div className="text-sm text-slate-700">{s.label}</div>
            </div>
          ))}
        </div>
        <div className="mt-10 bg-emerald-50 border-l-4 border-emerald-500 rounded p-5 flex gap-4">
          <Lightbulb className="w-8 h-8 text-emerald-600 shrink-0" />
          <div>
            <h3 className="font-semibold text-emerald-900 mb-1">
              Lär genom att göra — inte genom att läsa om det
            </h3>
            <p className="text-sm text-emerald-900">
              Eleven får egen simulerad inkomst, egna räkningar, egen lön varje
              månad. Precis som i livet utanför klassrummet. Varje val har
              konsekvenser som syns i deras budget.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
function FeaturesSection() {
  const features = [
    {
      icon: <Briefcase className="w-6 h-6" />,
      title: "Unik elev-profil",
      body: "Varje elev får ett slumpat yrke, arbetsgivare, lön, stad och livssituation. Ingen annan i klassen har samma.",
      color: "brand",
    },
    {
      icon: <Receipt className="w-6 h-6" />,
      title: "Riktiga PDF:er",
      body: "Läraren genererar kontoutdrag, lönespec, lån och kreditkortsfakturor som eleverna själva importerar.",
      color: "emerald",
    },
    {
      icon: <PiggyBank className="w-6 h-6" />,
      title: "Budget mot verklighet",
      body: "Eleven sätter sin egen månadsbudget baserat på Konsumentverkets 2026-siffror — sedan jämförs den mot faktiska köp.",
      color: "amber",
    },
    {
      icon: <Home className="w-6 h-6" />,
      title: "Bolåne-beslut",
      body: "Historiska räntor från Riksbanken. Eleven väljer rörlig eller bunden — systemet visar facit efter horisonten.",
      color: "rose",
    },
    {
      icon: <AlertTriangle className="w-6 h-6" />,
      title: "Livet händer",
      body: "Diskmaskin går sönder. Sjukdagar sänker lönen. Julshopping exploderar. Eleverna får öva på att hantera oväntat.",
      color: "purple",
    },
    {
      icon: <Users className="w-6 h-6" />,
      title: "Familjer",
      body: "Två elever kan dela ekonomi — sambo-hushåll med gemensam budget, räkningar och sparmål.",
      color: "sky",
    },
    {
      icon: <BarChart3 className="w-6 h-6" />,
      title: "Lärarens översikt",
      body: "Klassöversikt med status per elev och uppdrag. Facit för varje kategorisering — grönt/rött på en blick.",
      color: "brand",
    },
    {
      icon: <MessageCircle className="w-6 h-6" />,
      title: "Feedback-chat",
      body: "Eleven kan ställa frågor direkt till läraren. Läraren svarar + ger feedback på enskilda transaktioner.",
      color: "emerald",
    },
    {
      icon: <TrendingUp className="w-6 h-6" />,
      title: "Sparmål & uppdrag",
      body: "Läraren sätter tydliga uppdrag: 'spara 2 000 kr', 'balansera månaden', 'kategorisera alla köp'. Statusen uppdateras automatiskt.",
      color: "amber",
    },
  ];

  return (
    <section id="funktioner" className="max-w-6xl mx-auto px-6 py-16">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 text-brand-600 text-sm font-medium mb-2">
          <Sparkles className="w-4 h-4" /> Funktioner
        </div>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900">
          Allt du behöver för att göra ekonomi begripligt
        </h2>
        <p className="mt-4 text-slate-600 max-w-2xl mx-auto">
          Från första lönen till komplexa bolåneval — varje funktion är byggd
          för att eleven ska lära genom handling.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {features.map((f, i) => (
          <FeatureCard key={i} {...f} />
        ))}
      </div>
    </section>
  );
}

function FeatureCard({
  icon, title, body, color,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    brand: "bg-brand-100 text-brand-600",
    emerald: "bg-emerald-100 text-emerald-600",
    amber: "bg-amber-100 text-amber-600",
    rose: "bg-rose-100 text-rose-600",
    purple: "bg-purple-100 text-purple-600",
    sky: "bg-sky-100 text-sky-600",
  };
  return (
    <div className="group bg-white border border-slate-200 rounded-xl p-5 hover:border-brand-400 hover:shadow-lg transition-all duration-300">
      <div
        className={`inline-flex w-12 h-12 rounded-lg items-center justify-center mb-3 ${
          colorMap[color] ?? "bg-brand-100 text-brand-600"
        } group-hover:scale-110 transition-transform`}
      >
        {icon}
      </div>
      <h3 className="font-semibold text-slate-900 mb-1">{title}</h3>
      <p className="text-sm text-slate-600 leading-relaxed">{body}</p>
    </div>
  );
}
function FlowSection() {
  const blocks = [
    {
      num: "01",
      title: "Eleven får en egen vardag",
      body: "Yrke, lön, bostad, lån — allt slumpas unikt per elev. Dashboarden visar nettolön, utgifter, sparande och budget mot verkligheten i realtid.",
      color: "bg-brand-500",
      demo: <DashboardPreview />,
    },
    {
      num: "02",
      title: "Verkliga dokument att jobba med",
      body: "Läraren trycker 'generera' — eleven får kontoutdrag, lönespec, lånebesked och kortfakturor som PDF:er och importerar själv.",
      color: "bg-emerald-500",
      demo: <PdfImportDemo />,
    },
    {
      num: "03",
      title: "Budget möter verklighet",
      body: "Eleven sätter en månadsbudget enligt Konsumentverkets 2026-siffror. När en trasig diskmaskin slår till syns följderna direkt.",
      color: "bg-amber-500",
      demo: <BudgetDemo />,
    },
    {
      num: "04",
      title: "Läraren ser hela klassen",
      body: "Matris över alla elever och uppdrag. Kategoriseringsfacit per tx. Chatt för feedback. Allt du behöver för att följa upp.",
      color: "bg-rose-500",
      demo: <TeacherDemo />,
    },
  ];

  return (
    <section id="sa-funkar-det" className="bg-slate-900 text-white py-20">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 text-brand-300 text-sm font-medium mb-2">
            <Sparkles className="w-4 h-4" /> Så funkar det
          </div>
          <h2 className="text-3xl md:text-4xl font-bold">
            Se plattformen i rörelse
          </h2>
          <p className="text-slate-400 mt-3 max-w-xl mx-auto">
            Fyra nyckel-ögonblick i Ekonomilabbet — precis så elever och
            lärare faktiskt använder det.
          </p>
        </div>

        <div className="space-y-20">
          {blocks.map((b, i) => (
            <div
              key={b.num}
              className={`grid md:grid-cols-2 gap-10 items-center ${
                i % 2 === 1 ? "md:[&>div:first-child]:order-2" : ""
              }`}
            >
              <div>
                <div
                  className={`${b.color} inline-flex w-14 h-14 rounded-full items-center justify-center text-xl font-bold mb-4 shadow-lg`}
                >
                  {b.num}
                </div>
                <h3 className="text-2xl font-bold mb-3">{b.title}</h3>
                <p className="text-slate-300 leading-relaxed">{b.body}</p>
              </div>
              <div>{b.demo}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
function CtaSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20 text-center">
      <div className="bg-gradient-to-br from-brand-500 to-brand-700 rounded-3xl p-10 md:p-14 shadow-2xl text-white">
        <GraduationCap className="w-12 h-12 mx-auto mb-4 text-brand-100" />
        <h2 className="text-3xl md:text-4xl font-bold mb-3">
          Kom igång på under en minut
        </h2>
        <p className="text-brand-100 max-w-xl mx-auto mb-8">
          Skapa ditt lärarkonto, lägg till din första klass och testa flödet
          själv. Helt gratis under beta-perioden.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            to="/login/teacher"
            className="bg-white hover:bg-slate-50 text-brand-700 rounded-lg px-8 py-3 font-semibold shadow-lg hover:shadow-xl transition-all"
          >
            Skapa lärarkonto
          </Link>
          <Link
            to="/login/student"
            className="bg-brand-800 hover:bg-brand-900 text-white rounded-lg px-8 py-3 font-semibold border-2 border-brand-400"
          >
            Elev-inloggning
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-8 mt-16">
      <div className="max-w-6xl mx-auto px-6 text-center text-sm text-slate-500">
        <div className="font-semibold text-slate-700 mb-1">Ekonomilabbet</div>
        <div>
          En öppen utbildningsplattform för privatekonomi. Byggd med ❤ för
          svenska skolor.
        </div>
      </div>
    </footer>
  );
}
