import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LoginScreen } from "./LoginScreen";

function renderLogin(overrides: Partial<React.ComponentProps<typeof LoginScreen>> = {}) {
  const props: React.ComponentProps<typeof LoginScreen> = {
    language: "id",
    darkTheme: false,
    largeText: false,
    highContrast: false,
    showDemoAccounts: true,
    loading: false,
    error: "",
    onLanguageChange: vi.fn(),
    onThemeChange: vi.fn(),
    onLargeTextChange: vi.fn(),
    onHighContrastChange: vi.fn(),
    onBack: vi.fn(),
    onSignIn: vi.fn(),
    ...overrides,
  };
  render(<LoginScreen {...props} />);
  return props;
}

describe("Login screen", () => {
  it("explains mock-only roles without asking for or storing a password", () => {
    renderLogin();

    expect(screen.getByRole("heading", { name: "Masuk ke menara kendali" })).toBeInTheDocument();
    expect(screen.getByText("Akses hanya-baca")).toBeInTheDocument();
    expect(screen.getByText(/Dapat meninjau dan menyetujui/)).toBeInTheDocument();
    expect(screen.getByText(/password demo/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Salin username" })).toHaveLength(2);
  });

  it("shows loading and inline error accessibly and returns to welcome", () => {
    const onBack = vi.fn();
    const onSignIn = vi.fn();
    renderLogin({ loading: true, error: "Identity provider is unavailable.", onBack, onSignIn });

    expect(screen.getByRole("alert")).toHaveTextContent("Identity provider is unavailable.");
    expect(screen.getByRole("button", { name: "Menghubungkan ke penyedia identitas…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Kembali ke sambutan" }));
    expect(onBack).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Menghubungkan ke penyedia identitas…" }));
    expect(onSignIn).not.toHaveBeenCalled();
  });

  it("hides demo accounts outside the local mock/sandbox mode", () => {
    renderLogin({ showDemoAccounts: false });

    expect(screen.queryByRole("heading", { name: "Akun demo" })).not.toBeInTheDocument();
  });
});
