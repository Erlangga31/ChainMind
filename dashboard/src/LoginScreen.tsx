import { useState } from "react";
import { translate, type Language } from "./i18n";

type LoginScreenProps = {
  language: Language;
  darkTheme: boolean;
  largeText: boolean;
  highContrast: boolean;
  showDemoAccounts: boolean;
  loading: boolean;
  error: string;
  onLanguageChange: (language: Language) => void;
  onThemeChange: () => void;
  onLargeTextChange: () => void;
  onHighContrastChange: () => void;
  onBack: () => void;
  onSignIn: () => void;
};

const agentKeys = ["welcomeAgentMonitoring", "welcomeAgentLogistics", "welcomeAgentProcurement", "welcomeAgentOrchestrator"];

export function LoginScreen({
  language,
  darkTheme,
  largeText,
  highContrast,
  showDemoAccounts,
  loading,
  error,
  onLanguageChange,
  onThemeChange,
  onLargeTextChange,
  onHighContrastChange,
  onBack,
  onSignIn,
}: LoginScreenProps) {
  const [copyMessage, setCopyMessage] = useState("");
  const t = (key: string) => translate(language, key);

  async function copyUsername(username: string) {
    if (!navigator.clipboard?.writeText) {
      setCopyMessage(t("loginClipboardUnavailable"));
      return;
    }
    try {
      await navigator.clipboard.writeText(username);
      setCopyMessage(t("loginUsernameCopied"));
    } catch {
      setCopyMessage(t("loginClipboardUnavailable"));
    }
  }

  return (
    <main className="entry-page h-[100dvh] min-h-0 overflow-hidden bg-canvas text-ink">
      <header className="relative z-10 flex min-h-16 items-center justify-between gap-3 px-4 py-3 sm:px-7">
        <button type="button" className="flex items-center gap-3 rounded-lg text-left focus-visible:outline" onClick={onBack}>
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400 font-black text-ink">C</span>
          <span className="font-bold tracking-[0.14em]">CHAINMIND</span>
          <span className="sr-only">{t("loginBack")}</span>
        </button>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div role="group" aria-label={t("language")} className="flex gap-1">
            {(["id", "en"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={language === value} onClick={() => onLanguageChange(value)} className="entry-tool-button">{value.toUpperCase()}</button>
            ))}
          </div>
          <button type="button" aria-label={t("welcomeTheme")} aria-pressed={darkTheme} onClick={onThemeChange} className="entry-tool-button">{darkTheme ? "☀" : "☾"}</button>
          <button type="button" aria-label={t("largeText")} aria-pressed={largeText} onClick={onLargeTextChange} className="entry-tool-button">A+</button>
          <button type="button" aria-label={t("highContrast")} aria-pressed={highContrast} onClick={onHighContrastChange} className="entry-tool-button">◐</button>
        </div>
      </header>

      <div className="relative mx-auto grid h-[calc(100dvh-8rem)] min-h-0 max-w-7xl grid-cols-1 gap-4 px-3 pb-3 sm:px-6 lg:grid-cols-[1.05fr_.95fr] lg:gap-8 lg:px-10">
        <section className="entry-login-brand relative hidden min-h-0 flex-col justify-center overflow-hidden rounded-[2rem] p-8 text-white shadow-2xl lg:flex lg:p-10" aria-labelledby="login-brand-title">
          <svg className="absolute inset-0 h-full w-full opacity-30" viewBox="0 0 760 800" aria-hidden="true">
            <path d="M-40 580 C120 410 230 710 370 510 S560 350 820 470 M80 -30 C180 180 350 220 380 450 S520 680 650 830" fill="none" stroke="#99f6e4" strokeWidth="2" />
            <g fill="#5eead4"><circle cx="80" cy="540" r="6" /><circle cx="370" cy="510" r="6" /><circle cx="570" cy="410" r="6" /><circle cx="380" cy="450" r="6" /></g>
          </svg>
          <div className="relative">
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-teal-200">{t("welcomeEyebrow")}</p>
            <h1 id="login-brand-title" className="mt-4 text-4xl font-black">ChainMind</h1>
            <p className="mt-2 text-lg font-semibold text-teal-100">Autonomous Disruption Resolver</p>
            <p className="mt-5 max-w-xl text-sm leading-6 text-slate-200">{t("welcomeValue")}</p>
            <ul className="mt-7 grid gap-2 text-sm text-slate-100">
              <li>✓ {t("loginBenefitRisk")}</li>
              <li>✓ {t("loginBenefitSuppliers")}</li>
              <li>✓ {t("loginBenefitApproval")}</li>
            </ul>
            <ol className="mt-8 grid grid-cols-4 gap-2" aria-label={t("welcomeFlowTitle")}>
              {agentKeys.map((key, index) => (
                <li key={key} className="min-w-0 rounded-xl border border-white/20 bg-white/10 p-3 backdrop-blur">
                  <span className="text-[10px] font-bold text-teal-200">0{index + 1}</span>
                  <span className="mt-1 block truncate text-xs font-semibold">{t(`${key}Title`)}</span>
                </li>
              ))}
            </ol>
            <p className="mt-5 max-w-xl text-xs leading-5 text-teal-100">{t("welcomeApprovalNote")}</p>
          </div>
        </section>

        <section className="entry-login-panel flex min-h-0 flex-col justify-center overflow-y-auto rounded-[2rem] p-4 sm:p-7 lg:p-10" aria-labelledby="login-title">
          <button type="button" onClick={onBack} className="mb-5 w-fit rounded-lg px-2 py-1 text-sm font-semibold text-teal-800 hover:underline dark:text-teal-200">
            ← {t("loginBack")}
          </button>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-200">{t("loginEyebrow")}</p>
          <h2 id="login-title" className="mt-2 text-3xl font-black text-ink sm:text-4xl">{t("signInTitle")}</h2>
          <p className="mt-3 max-w-lg text-sm leading-6 text-slate-600 dark:text-slate-300">{t("signInDescription")}</p>

          {error && (
            <div role="alert" aria-live="polite" className="mt-5 flex items-start gap-3 rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-900">
              <span aria-hidden="true">!</span>
              <div><p className="font-bold">{t("loginErrorTitle")}</p><p className="mt-1">{error}</p></div>
            </div>
          )}
          {showDemoAccounts && (
            <section className="mt-6 rounded-2xl border border-slate-200 bg-white/75 p-4 dark:border-slate-700 dark:bg-slate-900/50" aria-labelledby="demo-account-title">
              <h3 id="demo-account-title" className="font-bold text-ink">{t("loginDemoAccounts")}</h3>
              <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">{t("loginDemoHint")}</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-bold text-ink">viewer</p>
                    <button type="button" className="text-xs font-semibold text-teal-700 underline dark:text-teal-200" onClick={() => void copyUsername("viewer")}>{t("loginCopyUsername")}</button>
                  </div>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("loginViewerRole")}</p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-bold text-ink">approver</p>
                    <button type="button" className="text-xs font-semibold text-teal-700 underline dark:text-teal-200" onClick={() => void copyUsername("approver")}>{t("loginCopyUsername")}</button>
                  </div>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("loginApproverRole")}</p>
                </div>
              </div>
              <p className="mt-3 text-xs font-medium text-slate-600 dark:text-slate-300">{t("loginDemoCredentialHint")}</p>
              {copyMessage && <p role="status" className="mt-2 text-xs font-semibold text-teal-800 dark:text-teal-200">{copyMessage}</p>}
            </section>
          )}

          {error && (
            <button type="button" onClick={onSignIn} disabled={loading} className="entry-primary-button mt-5 w-full disabled:cursor-wait disabled:opacity-70">
              {loading ? t("loginRedirecting") : t("loginRetry")}
            </button>
          )}
          {!error && (
            <button type="button" onClick={onSignIn} disabled={loading} className="entry-primary-button mt-6 w-full disabled:cursor-wait disabled:opacity-70">
              {loading ? <><span className="entry-spinner" aria-hidden="true" />{t("loginRedirecting")}</> : t("signIn")}
            </button>
          )}
          <p className="mt-5 text-center text-xs text-slate-500">{t("loginSandboxNote")}</p>
        </section>
      </div>
      <footer className="relative flex h-8 items-center justify-between px-4 text-xs text-slate-500 sm:px-8">
        <span>ChainMind v1.1.1</span>
        <span>{t("welcomeFooter")}</span>
      </footer>
    </main>
  );
}
