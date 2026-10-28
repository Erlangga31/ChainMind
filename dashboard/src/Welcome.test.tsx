import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WelcomeScreen } from "./Welcome";

function renderWelcome(language: "id" | "en" = "id") {
  const onGetStarted = vi.fn();
  const onLanguageChange = vi.fn();
  const onThemeChange = vi.fn();
  const onLargeTextChange = vi.fn();
  const onHighContrastChange = vi.fn();
  render(
    <WelcomeScreen
      language={language}
      darkTheme={false}
      largeText={false}
      highContrast={false}
      onLanguageChange={onLanguageChange}
      onThemeChange={onThemeChange}
      onLargeTextChange={onLargeTextChange}
      onHighContrastChange={onHighContrastChange}
      onGetStarted={onGetStarted}
    />,
  );
  return { onGetStarted, onLanguageChange, onThemeChange, onLargeTextChange, onHighContrastChange };
}

describe("Welcome screen", () => {
  it("shows Indonesian product value and proceeds to login", () => {
    const { onGetStarted } = renderWelcome();

    expect(screen.getByRole("heading", { name: "ChainMind" })).toBeInTheDocument();
    expect(screen.getByText(/Ubah sinyal gangguan menjadi rencana respons/)).toBeInTheDocument();
    expect(screen.getByText("Mode simulasi")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mulai" }));

    expect(onGetStarted).toHaveBeenCalledOnce();
  });

  it("opens the four-agent explanation and calls the display controls", () => {
    const controls = renderWelcome();

    fireEvent.click(screen.getByRole("button", { name: "Lihat cara kerja" }));
    expect(screen.getByRole("dialog", { name: /Dari gangguan hingga proposal/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Monitoring" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Logistics" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Procurement" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Orchestrator" })).toBeInTheDocument();
    expect(screen.getByText(/harus ditinjau dan disetujui manusia/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ganti tema terang atau gelap" }));
    fireEvent.click(screen.getByRole("button", { name: "Teks lebih besar" }));
    fireEvent.click(screen.getByRole("button", { name: "Kontras tinggi" }));
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(controls.onThemeChange).toHaveBeenCalledOnce();
    expect(controls.onLargeTextChange).toHaveBeenCalledOnce();
    expect(controls.onHighContrastChange).toHaveBeenCalledOnce();
    expect(controls.onLanguageChange).toHaveBeenCalledWith("en");
  });

  it("renders the English value statement and trust chips", () => {
    renderWelcome("en");

    expect(screen.getByRole("button", { name: "Get started" })).toBeInTheDocument();
    expect(screen.getByText(/Turn a disruption signal into a clear, data-backed response plan/)).toBeInTheDocument();
    expect(screen.getByText("Human-in-the-loop")).toBeInTheDocument();
    expect(screen.getByText("Sandbox mode")).toBeInTheDocument();
  });
});
