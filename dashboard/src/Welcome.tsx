import { useState } from "react";
import { translate, type Language } from "./i18n";

type WelcomeScreenProps = {
  language: Language;
  darkTheme: boolean;
  largeText: boolean;
  highContrast: boolean;
  onLanguageChange: (language: Language) => void;
  onThemeChange: () => void;
  onLargeTextChange: () => void;
  onHighContrastChange: () => void;
  onGetStarted: () => void;
};

const agentCards = [
  ["welcomeAgentMonitoring", "01"],
  ["welcomeAgentLogistics", "02"],
  ["welcomeAgentProcurement", "03"],
  ["welcomeAgentOrchestrator", "04"],
] as const;

export function WelcomeScreen({
  language,
  darkTheme,
  largeText,
  highContrast,
  onLanguageChange,
  onThemeChange,
  onLargeTextChange,
  onHighContrastChange,
  onGetStarted,
}: WelcomeScreenProps) {
  const [showFlow, setShowFlow] = useState(false);
  const t = (key: string) => translate(language, key);

  return (
    <main className="entry-page relative flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-canvas text-ink">
      <svg className="entry-network pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="entry-line" x1="0" x2="1">
            <stop offset="0" stopColor="#0f766e" stopOpacity=".05" />
            <stop offset=".5" stopColor="#14b8a6" stopOpacity=".38" />
            <stop offset="1" stopColor="#38bdf8" stopOpacity=".08" />
          </linearGradient>
        </defs>
        <path d="M-50 610 C240 420 340 810 650 590 S1050 340 1500 560" fill="none" stroke="url(#entry-line)" strokeWidth="2" />
        <path d="M-80 700 C200 510 430 850 710 640 S1130 480 1520 640" fill="none" stroke="url(#entry-line)" strokeWidth="1.5" />
        <path d="M140 0 C260 220 450 250 530 480 S880 690 1010 900" fill="none" stroke="url(#entry-line)" strokeWidth="1.5" />
        <g fill="#14b8a6" opacity=".55">
          <circle cx="142" cy="535" r="5" /><circle cx="530" cy="480" r="5" />
          <circle cx="650" cy="590" r="5" /><circle cx="1010" cy="510" r="5" />
          <circle cx="1170" cy="430" r="5" /><circle cx="1010" cy="900" r="5" />
        </g>
      </svg>

      <header className="relative z-10 flex shrink-0 items-center justify-between gap-3 px-4 py-4 sm:px-8 lg:px-12">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-400 text-lg font-black text-ink shadow-lg">C</span>
          <span className="font-bold tracking-[0.16em]">CHAINMIND</span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2" aria-label={t("welcomePreferences")}>
          <div role="group" aria-label={t("language")} className="flex gap-1">
            {(["id", "en"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={language === value} onClick={() => onLanguageChange(value)} className="entry-tool-button">
                {value.toUpperCase()}
              </button>
            ))}
          </div>
          <button type="button" aria-label={t("welcomeTheme")} aria-pressed={darkTheme} onClick={onThemeChange} className="entry-tool-button">
            {darkTheme ? "☀" : "☾"}
          </button>
          <button type="button" aria-label={`${t("largeText")} A+`} aria-pressed={largeText} onClick={onLargeTextChange} className="entry-tool-button">A+</button>
          <button type="button" aria-label={t("highContrast")} aria-pressed={highContrast} onClick={onHighContrastChange} className="entry-tool-button">◐</button>
        </div>
      </header>

      <div className="relative z-10 mx-auto flex min-h-0 w-full max-w-7xl flex-1 items-center px-4 pb-5 sm:px-8 lg:px-12">
        <section className="entry-glass w-full rounded-[2rem] p-6 sm:p-10 lg:p-14" aria-labelledby="welcome-title">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-teal-500/25 bg-teal-500/10 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-teal-800 dark:text-teal-200">
            <span className="h-2 w-2 rounded-full bg-teal-500" aria-hidden="true" />
            {t("welcomeEyebrow")}
          </p>
          <h1 id="welcome-title" className="max-w-3xl text-4xl font-black tracking-tight text-ink sm:text-6xl lg:text-7xl">ChainMind</h1>
          <p className="mt-3 text-lg font-semibold text-teal-800 dark:text-teal-200 sm:text-2xl">Autonomous Disruption Resolver</p>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600 dark:text-slate-300 sm:text-lg">{t("welcomeValue")}</p>

          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={onGetStarted} className="entry-primary-button">
              {t("welcomeGetStarted")} <span aria-hidden="true">→</span>
            </button>
            <button type="button" onClick={() => setShowFlow(true)} className="entry-secondary-button">
              {t("welcomeSeeFlow")}
            </button>
          </div>

          <ul className="mt-9 flex flex-wrap gap-2" aria-label={t("welcomeTrust")}>
            {["welcomeTrustApproval", "welcomeTrustCloud", "welcomeTrustSandbox"].map((key) => (
              <li key={key} className="rounded-full border border-slate-300/70 bg-white/70 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:bg-slate-900/50 dark:text-slate-200 sm:text-sm">
                {t(key)}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <footer className="relative z-10 flex shrink-0 flex-wrap justify-between gap-2 px-4 pb-4 text-xs text-slate-500 sm:px-8 lg:px-12">
        <span>ChainMind v1.1.1</span>
        <span>{t("welcomeFooter")}</span>
      </footer>

      {showFlow && (
        <div className="entry-overlay fixed inset-0 z-30 grid place-items-center p-4" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setShowFlow(false);
        }}>
          <section role="dialog" aria-modal="true" aria-labelledby="welcome-flow-title" className="entry-dialog w-full max-w-5xl rounded-3xl p-5 shadow-2xl sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-bold uppercase tracking-widest text-teal-700 dark:text-teal-300">{t("welcomeFlowEyebrow")}</p>
                <h2 id="welcome-flow-title" className="mt-2 text-2xl font-bold text-ink">{t("welcomeFlowTitle")}</h2>
              </div>
              <button type="button" aria-label={t("welcomeClose")} onClick={() => setShowFlow(false)} className="entry-tool-button">×</button>
            </div>
            <div className="mt-6 grid max-h-[58dvh] gap-3 overflow-y-auto sm:grid-cols-2 lg:grid-cols-4">
              {agentCards.map(([key, number]) => (
                <article key={key} className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-900/70">
                  <span className="text-xs font-bold tracking-widest text-teal-700 dark:text-teal-300">{number}</span>
                  <h3 className="mt-3 font-bold text-ink">{t(`${key}Title`)}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{t(`${key}Description`)}</p>
                </article>
              ))}
            </div>
            <p className="mt-5 rounded-xl border border-amber-400/40 bg-amber-400/10 p-4 text-sm leading-6 text-ink">{t("welcomeApprovalNote")}</p>
            <div className="mt-5 flex justify-end">
              <button type="button" className="entry-primary-button" onClick={() => setShowFlow(false)}>{t("welcomeClose")}</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
