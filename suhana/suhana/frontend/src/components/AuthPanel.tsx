import type { FormEvent } from "react";
import type { RegistrationStep } from "../types";

type Props = {
  step: RegistrationStep;
  loading: boolean;
  csrfReady: boolean;
  form: { username: string; email: string; password: string; confirmPassword: string };
  loginForm: { identifier: string; password: string };
  otp: string;
  resendCooldown: number;
  onRegister: (event: FormEvent<HTMLFormElement>) => void;
  onVerify: (event: FormEvent<HTMLFormElement>) => void;
  onResend: () => void;
  onLogin: (event: FormEvent<HTMLFormElement>) => void;
  onLogout: () => void;
  onFieldChange: (field: keyof Props["form"], value: string) => void;
  onOtpChange: (value: string) => void;
  onLoginChange: (field: keyof Props["loginForm"], value: string) => void;
  onStepChange: (step: RegistrationStep) => void;
  onReset: () => void;
};

export default function AuthPanel(props: Props) {
  const { step, loading } = props;
  return (
    <>
      {step === "register" && (
        <form onSubmit={props.onRegister}>
          <label htmlFor="username">Username</label>
          <input id="username" type="text" autoComplete="username" value={props.form.username}
            onChange={(event) => props.onFieldChange("username", event.target.value)} required />
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="email" value={props.form.email}
            onChange={(event) => props.onFieldChange("email", event.target.value)} required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="new-password" value={props.form.password}
            onChange={(event) => props.onFieldChange("password", event.target.value)} required />
          <label htmlFor="confirm-password">Confirm password</label>
          <input id="confirm-password" type="password" autoComplete="new-password"
            value={props.form.confirmPassword}
            onChange={(event) => props.onFieldChange("confirmPassword", event.target.value)} required />
          <button type="submit" disabled={loading || !props.csrfReady}>
            {loading ? "Please wait..." : "Create account"}
          </button>
        </form>
      )}
      {step === "register" && <button type="button" className="secondary-button"
        onClick={() => props.onStepChange("login")} disabled={loading}>Already have an account? Sign in</button>}
      {step === "verify" && (
        <form onSubmit={props.onVerify}>
          <p className="helper-text">Enter the 6-digit code sent to {props.form.email}.</p>
          <label htmlFor="otp">Verification code</label>
          <input id="otp" type="text" inputMode="numeric" autoComplete="one-time-code"
            maxLength={6} pattern="\d{6}" value={props.otp}
            onChange={(event) => props.onOtpChange(event.target.value.replace(/\D/g, ""))} required />
          <button type="submit" disabled={loading}>{loading ? "Verifying..." : "Verify email"}</button>
          <button type="button" className="secondary-button" onClick={props.onResend}
            disabled={loading || props.resendCooldown > 0}>
            {props.resendCooldown > 0 ? `Resend in ${props.resendCooldown}s` : "Resend OTP"}
          </button>
        </form>
      )}
      {step === "success" && <div className="success-panel">
        <p>Your email has been verified and your account was created.</p>
        <button type="button" onClick={() => props.onStepChange("login")}>Continue to login</button>
      </div>}
      {step === "login" && (
        <form onSubmit={props.onLogin}>
          <label htmlFor="login-identifier">Username or email</label>
          <input id="login-identifier" type="text" autoComplete="username" value={props.loginForm.identifier}
            onChange={(event) => props.onLoginChange("identifier", event.target.value)} required />
          <label htmlFor="login-password">Password</label>
          <input id="login-password" type="password" autoComplete="current-password" value={props.loginForm.password}
            onChange={(event) => props.onLoginChange("password", event.target.value)} required />
          <button type="submit" disabled={loading || !props.csrfReady}>{loading ? "Signing in..." : "Sign in"}</button>
          <button type="button" className="secondary-button" onClick={() => props.onStepChange("register")} disabled={loading}>Create a new account</button>
          <button type="button" className="secondary-button" onClick={props.onReset}>Forgot password?</button>
        </form>
      )}
      {step === "logged-in" && <div className="success-panel">
        <p>You are signed in and can continue using Suhana.</p>
        <button type="button" onClick={props.onLogout} disabled={loading}>{loading ? "Signing out..." : "Sign out"}</button>
      </div>}
    </>
  );
}
