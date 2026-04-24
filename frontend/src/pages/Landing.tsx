import { Link } from "react-router-dom";
import { GraduationCap, Sparkles } from "lucide-react";

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
    <section className="max-w-6xl mx-auto px-6 py-16 md:py-24 text-center">
      <div className="inline-flex items-center gap-2 bg-brand-100 text-brand-700 rounded-full px-4 py-1 text-sm mb-6 animate-fadein">
        <GraduationCap className="w-4 h-4" />
        Privatekonomi för skolan
      </div>
      <h1 className="text-4xl md:text-6xl font-bold text-slate-900 leading-tight animate-fadeup">
        Lär eleverna hantera sin
        <span className="text-brand-600"> riktiga ekonomi</span>
        <br />– innan de möter den på riktigt.
      </h1>
      <p className="mt-6 text-lg text-slate-600 max-w-2xl mx-auto animate-fadeup delay-100">
        Ekonomilabbet är en interaktiv simulator där varje elev får en egen
        simulerad vardag — yrke, lön, skatt, hyra, lån, räkningar. De lär sig
        budgetera, spara och förstå vad som händer när livet inte går som
        planerat.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3 animate-fadeup delay-200">
        <Link
          to="/login"
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-medium shadow-lg hover:shadow-xl transition-all"
        >
          Kom igång som lärare
        </Link>
        <Link
          to="/login"
          className="bg-white border-2 border-slate-300 hover:border-brand-500 text-slate-700 rounded-lg px-6 py-3 font-medium"
        >
          Jag är elev
        </Link>
      </div>
    </section>
  );
}

function WhySection() { return null; }
function FeaturesSection() { return null; }
function FlowSection() { return null; }
function CtaSection() { return null; }

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
