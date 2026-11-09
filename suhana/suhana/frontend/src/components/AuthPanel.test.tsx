import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AuthPanel from "./AuthPanel";

const callbacks = {
  onRegister: vi.fn(),
  onVerify: vi.fn(),
  onResend: vi.fn(),
  onLogin: vi.fn(),
  onLogout: vi.fn(),
  onFieldChange: vi.fn(),
  onOtpChange: vi.fn(),
  onLoginChange: vi.fn(),
  onStepChange: vi.fn(),
  onReset: vi.fn(),
};

const common = {
  loading: false,
  csrfReady: true,
  form: { username: "", email: "", password: "", confirmPassword: "" },
  loginForm: { identifier: "", password: "" },
  otp: "",
  resendCooldown: 0,
  ...callbacks,
};

describe("AuthPanel", () => {
  it("renders the registration form and submits through its callback", () => {
    render(<AuthPanel {...common} step="register" />);

    expect(screen.getByLabelText("Username")).toBeRequired();
    fireEvent.submit(screen.getByRole("button", { name: "Create account" }).closest("form")!);
    expect(callbacks.onRegister).toHaveBeenCalled();
  });

  it("disables resend during the cooldown", () => {
    render(<AuthPanel {...common} step="verify" resendCooldown={12} />);

    expect(screen.getByRole("button", { name: "Resend in 12s" })).toBeDisabled();
  });
});
