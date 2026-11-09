import { useEffect, useState } from "react";
import "./App.css";

type RegistrationStep = "register" | "verify" | "success" | "login" | "logged-in";
type ActiveView = "auth" | "converter" | "compare";

type ApiResponse = {
  success?: boolean;
  message?: string;
  csrfToken?: string;
  email?: string;
  wait_seconds?: number;
  result?: number;
};

const initialForm = {
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
};

const initialLoginForm = {
  identifier: "",
  password: "",
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
  const [loginForm, setLoginForm] = useState(initialLoginForm);
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<RegistrationStep>("register");
  const [activeView, setActiveView] = useState<ActiveView>("auth");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [csrfToken, setCsrfToken] = useState("");
  const [conversion, setConversion] = useState({
    value: "1",
    from: "gb",
    to: "mb",
  });
  const [conversionResult, setConversionResult] = useState("");
  const [comparisonResult, setComparisonResult] = useState("");

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

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!csrfToken) {
      setMessage("Security token is not ready. Please try again.");
      return;
    }

    setLoading(true);
    try {
      const { response, data } = await postJson(
        "/api/accounts/login/",
        loginForm,
        csrfToken,
      );

      if (!response.ok || !data.success) {
        setMessage(data.message ?? "Login failed.");
        return;
      }

      setStep("logged-in");
      setLoginForm(initialLoginForm);
      setMessage(data.message ?? "Login successful.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    setLoading(true);
    setMessage("");
    try {
      const { response, data } = await postJson("/api/accounts/logout/", {}, csrfToken);

      if (!response.ok || !data.success) {
        setMessage(data.message ?? "Logout failed.");
        return;
      }

      setStep("login");
      setMessage(data.message ?? "Logout successful.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleConversion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setConversionResult("");
    try {
      const { response, data } = await postJson(
        "/api/tools/convert/",
        conversion,
        csrfToken,
      );
      if (!response.ok || !data.success) {
        setConversionResult(data.message ?? "Conversion failed.");
        return;
      }
      setConversionResult(`${data.result} ${conversion.to.toUpperCase()}`);
    } catch (error: unknown) {
      setConversionResult(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleComparison(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    if (!formData.get("first") || !formData.get("second")) {
      setComparisonResult("Choose two files before comparing.");
      return;
    }

    setLoading(true);
    setComparisonResult("");
    try {
      const response = await fetch("/api/tools/compare/", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: formData,
      });
      const data = (await response.json()) as ApiResponse & {
        comparison?: {
          same_content: boolean;
          same_type: boolean;
          first: { name: string; size_bytes: number; content_type: string };
          second: { name: string; size_bytes: number; content_type: string };
        };
      };
      if (!response.ok || !data.success || !data.comparison) {
        setComparisonResult(data.message ?? "Comparison failed.");
        return;
      }
      const result = data.comparison;
      setComparisonResult(
        result.same_content
          ? "The files have identical content."
          : `The files are different. Types match: ${result.same_type ? "yes" : "no"}.`,
      );
    } catch (error: unknown) {
      setComparisonResult(error instanceof Error ? error.message : "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app">
      <section className="register-card" aria-labelledby="page-title">
        <nav className="tool-nav" aria-label="Suhana tools">
          <button type="button" className={activeView === "auth" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("auth")}>Account</button>
          <button type="button" className={activeView === "converter" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("converter")}>Unit converter</button>
          <button type="button" className={activeView === "compare" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("compare")}>Compare files</button>
        </nav>
        <p className="eyebrow">WELCOME TO</p>
        <h1 id="page-title">Suhana</h1>
        <p className="subtitle">
          {activeView === "converter" && "Convert digital storage units"}
          {activeView === "compare" && "Compare image and PDF files"}
          {activeView === "auth" && (
            <>
          {step === "register" && "Create your account"}
          {step === "verify" && "Verify your email"}
          {step === "success" && "Your account is ready"}
          {step === "login" && "Welcome back"}
          {step === "logged-in" && "You are signed in"}
            </>
          )}
        </p>

        {activeView === "converter" && (
          <form onSubmit={handleConversion}>
            <label htmlFor="conversion-value">Value</label>
            <input id="conversion-value" type="number" min="0" step="any"
              value={conversion.value}
              onChange={(event) => setConversion((current) => ({ ...current, value: event.target.value }))}
              required />
            <label htmlFor="conversion-from">From</label>
            <select id="conversion-from" value={conversion.from}
              onChange={(event) => setConversion((current) => ({ ...current, from: event.target.value }))}>
              <option value="bit">Bit</option><option value="byte">Byte</option>
              <option value="kb">KB</option><option value="mb">MB</option>
              <option value="gb">GB</option><option value="tb">TB</option>
            </select>
            <label htmlFor="conversion-to">To</label>
            <select id="conversion-to" value={conversion.to}
              onChange={(event) => setConversion((current) => ({ ...current, to: event.target.value }))}>
              <option value="bit">Bit</option><option value="byte">Byte</option>
              <option value="kb">KB</option><option value="mb">MB</option>
              <option value="gb">GB</option><option value="tb">TB</option>
            </select>
            <button type="submit" disabled={loading || !csrfToken}>
              {loading ? "Converting..." : "Convert"}
            </button>
            {conversionResult && <p className="result-panel" role="status">{conversionResult}</p>}
          </form>
        )}

        {activeView === "compare" && (
          <form onSubmit={handleComparison}>
            <p className="helper-text">Supported formats: PNG, JPEG, GIF, WEBP, and PDF. Maximum 25 MB per file.</p>
            <label htmlFor="first-file">First file</label>
            <input id="first-file" name="first" type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required />
            <label htmlFor="second-file">Second file</label>
            <input id="second-file" name="second" type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required />
            <button type="submit" disabled={loading || !csrfToken}>
              {loading ? "Comparing..." : "Compare files"}
            </button>
            {comparisonResult && <p className="result-panel" role="status">{comparisonResult}</p>}
          </form>
        )}

        {activeView === "auth" && (
        <>
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

        {step === "register" && (
          <button type="button" className="secondary-button"
            onClick={() => setStep("login")} disabled={loading}>
            Already have an account? Sign in
          </button>
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
            <button type="button" onClick={() => setStep("login")}>Continue to login</button>
          </div>
        )}

        {step === "login" && (
          <form onSubmit={handleLogin}>
            <label htmlFor="login-identifier">Username or email</label>
            <input id="login-identifier" type="text" autoComplete="username"
              value={loginForm.identifier}
              onChange={(event) => setLoginForm((current) => ({
                ...current,
                identifier: event.target.value,
              }))} required />
            <label htmlFor="login-password">Password</label>
            <input id="login-password" type="password" autoComplete="current-password"
              value={loginForm.password}
              onChange={(event) => setLoginForm((current) => ({
                ...current,
                password: event.target.value,
              }))} required />
            <button type="submit" disabled={loading || !csrfToken}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
            <button type="button" className="secondary-button"
              onClick={() => setStep("register")} disabled={loading}>
              Create a new account
            </button>
          </form>
        )}

        {step === "logged-in" && (
          <div className="success-panel">
            <p>You are signed in and can continue using Suhana.</p>
            <button type="button" onClick={handleLogout} disabled={loading}>
              {loading ? "Signing out..." : "Sign out"}
            </button>
          </div>
        )}
        </>
        )}

        {activeView === "auth" && message && <p className="status-message" role="status">{message}</p>}
      </section>
    </main>
  );
}

export default App;
