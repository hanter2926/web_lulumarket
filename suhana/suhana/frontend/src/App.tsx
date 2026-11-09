import { useEffect, useState } from "react";
import "./App.css";

type RegistrationStep = "register" | "verify" | "success";

type ApiResponse = {
  success?: boolean;
  message?: string;
  csrfToken?: string;
  email?: string;
  wait_seconds?: number;
};

const initialForm = {
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
};

async function getCsrfToken(): Promise<string> {
  const response = await fetch("/api/accounts/csrf/", {
    credentials: "include",
  });
  const data = (await response.json()) as ApiResponse;

  if (!response.ok || !data.csrfToken) {
    throw new Error("Unable to initialize secure registration.");
  }

  return data.csrfToken;
}

async function postJson(
  url: string,
  payload: Record<string, string>,
  csrfToken: string,
): Promise<{ response: Response; data: ApiResponse }> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    credentials: "include",
    body: JSON.stringify(payload),
  });

  const data = (await response.json()) as ApiResponse;
  return { response, data };
}

function App() {
  const [form, setForm] = useState(initialForm);
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<RegistrationStep>("register");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [csrfToken, setCsrfToken] = useState("");

  useEffect(() => {
    getCsrfToken()
      .then(setCsrfToken)
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
      });
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) {
      return;
    }

    const timer = window.setInterval(() => {
      setResendCooldown((seconds) => Math.max(seconds - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [resendCooldown]);

  function updateField(field: keyof typeof initialForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleRegister(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (form.password !== form.confirmPassword) {
      setMessage("Passwords do not match.");
      return;
    }

    if (!csrfToken) {
      setMessage("Security token is not ready. Please try again.");
      return;
    }

    setLoading(true);
    try {
      const { response, data } = await postJson(
        "/api/accounts/register/",
        {
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
        },
        csrfToken,
      );

      if (!response.ok || !data.success) {
        setMessage(data.message ?? "Registration failed.");
        return;
      }

      setStep("verify");
      setResendCooldown(60);
      setMessage(data.message ?? "OTP sent successfully. Please check your email.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!/^\d{6}$/.test(otp)) {
      setMessage("Enter a valid 6-digit OTP.");
      return;
    }

    setLoading(true);
    try {
      const { response, data } = await postJson(
        "/api/accounts/verify-otp/",
        { email: form.email.trim(), otp },
        csrfToken,
      );

      if (!response.ok || !data.success) {
        setMessage(data.message ?? "OTP verification failed.");
        return;
      }

      setStep("success");
      setForm(initialForm);
      setOtp("");
      setMessage(data.message ?? "Your account was created successfully.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (resendCooldown > 0 || loading) {
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      const { response, data } = await postJson(
        "/api/accounts/resend-otp/",
        { email: form.email.trim() },
        csrfToken,
      );

      if (!response.ok || !data.success) {
        setResendCooldown(data.wait_seconds ?? 0);
        setMessage(data.message ?? "Unable to resend OTP.");
        return;
      }

      setResendCooldown(60);
      setMessage(data.message ?? "A new OTP was sent.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app">
      <section className="register-card" aria-labelledby="page-title">
        <p className="eyebrow">WELCOME TO</p>
        <h1 id="page-title">Suhana</h1>
        <p className="subtitle">
          {step === "register" && "Create your account"}
          {step === "verify" && "Verify your email"}
          {step === "success" && "Your account is ready"}
        </p>

        {step === "register" && (
          <form onSubmit={handleRegister}>
            <label htmlFor="username">Username</label>
            <input id="username" type="text" autoComplete="username" value={form.username}
              onChange={(event) => updateField("username", event.target.value)} required />
            <label htmlFor="email">Email address</label>
            <input id="email" type="email" autoComplete="email" value={form.email}
              onChange={(event) => updateField("email", event.target.value)} required />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="new-password" value={form.password}
              onChange={(event) => updateField("password", event.target.value)} required />
            <label htmlFor="confirm-password">Confirm password</label>
            <input id="confirm-password" type="password" autoComplete="new-password"
              value={form.confirmPassword}
              onChange={(event) => updateField("confirmPassword", event.target.value)} required />
            <button type="submit" disabled={loading || !csrfToken}>
              {loading ? "Please wait..." : "Create account"}
            </button>
          </form>
        )}

        {step === "verify" && (
          <form onSubmit={handleVerify}>
            <p className="helper-text">Enter the 6-digit code sent to {form.email}.</p>
            <label htmlFor="otp">Verification code</label>
            <input id="otp" type="text" inputMode="numeric" autoComplete="one-time-code"
              maxLength={6} pattern="\d{6}" value={otp}
              onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} required />
            <button type="submit" disabled={loading}>
              {loading ? "Verifying..." : "Verify email"}
            </button>
            <button type="button" className="secondary-button" onClick={handleResend}
              disabled={loading || resendCooldown > 0}>
              {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend OTP"}
            </button>
          </form>
        )}

        {step === "success" && (
          <div className="success-panel">
            <p>Your email has been verified and your account was created.</p>
            <button type="button" onClick={() => setStep("register")}>Continue to login</button>
          </div>
        )}

        {message && <p className="status-message" role="status">{message}</p>}
      </section>
    </main>
  );
}

export default App;
