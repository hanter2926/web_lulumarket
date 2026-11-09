import { useEffect, useState } from "react";
import "./App.css";

type RegistrationStep = "register" | "verify" | "success" | "login" | "logged-in";
type ActiveView = "auth" | "dashboard" | "storage" | "converter" | "compare" | "history" | "reset" | "plans";

type ApiResponse = {
  success?: boolean;
  message?: string;
  csrfToken?: string;
  email?: string;
  wait_seconds?: number;
  result?: number;
  username?: string;
  storage?: { used_bytes: number; quota_bytes: number; plan: string } | null;
  file_count?: number;
  recent_files?: Array<{ id: number; name: string; size_bytes: number; content_type: string }>;
  files?: Array<{ id: number; name: string; size_bytes: number; content_type: string; folder_id: number | null }>;
  reports?: Array<{ id: number; first_name: string; second_name: string; comparison_type: string; result: { same_content: boolean }; created_at: string }>;
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
  const [dashboard, setDashboard] = useState<ApiResponse | null>(null);
  const [files, setFiles] = useState<ApiResponse["files"]>([]);
  const [reports, setReports] = useState<ApiResponse["reports"]>([]);
  const [resetForm, setResetForm] = useState({ email: "", otp: "", password: "" });
  const [resetRequested, setResetRequested] = useState(false);

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
      openView("dashboard");
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

  async function loadDashboard() {
      const response = await fetch("/api/storage/dashboard/", { credentials: "include" });
      const data = (await response.json()) as ApiResponse;
      if (response.ok) setDashboard(data);
  }

  async function loadFiles() {
      const response = await fetch("/api/storage/files/", { credentials: "include" });
      const data = (await response.json()) as ApiResponse;
      if (response.ok) setFiles(data.files ?? []);
  }

  async function loadReports() {
      const response = await fetch("/api/tools/reports/", { credentials: "include" });
      const data = (await response.json()) as ApiResponse;
      if (response.ok) setReports(data.reports ?? []);
  }

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      setLoading(true);
      try {
        const response = await fetch("/api/storage/files/upload/", {
          method: "POST", headers: { "X-CSRFToken": csrfToken },
          credentials: "include", body: formData,
        });
        const data = (await response.json()) as ApiResponse;
        setMessage(data.message ?? (response.ok ? "File uploaded." : "Upload failed."));
        if (response.ok) await loadFiles();
      } finally {
        setLoading(false);
      }
  }

  async function handleDeleteFile(id: number) {
      if (!window.confirm("Delete this file permanently?")) return;
      const response = await fetch(`/api/storage/files/${id}/delete/`, {
        method: "POST", headers: { "X-CSRFToken": csrfToken }, credentials: "include",
      });
      const data = (await response.json()) as ApiResponse;
      setMessage(data.message ?? "File deleted.");
      if (response.ok) await loadFiles();
  }

  async function handleResetRequest(event: React.FormEvent<HTMLFormElement>) {
      event.preventDefault();
      const { response, data } = await postJson("/api/accounts/password-reset/request/",
        { email: resetForm.email }, csrfToken);
      setMessage(data.message ?? "Reset request submitted.");
      if (response.ok) setResetRequested(true);
  }

  async function handleResetConfirm(event: React.FormEvent<HTMLFormElement>) {
      event.preventDefault();
      const { response, data } = await postJson("/api/accounts/password-reset/confirm/",
        resetForm, csrfToken);
      setMessage(data.message ?? "Password reset complete.");
      if (response.ok) { setResetRequested(false); setActiveView("auth"); setStep("login"); }
  }

  function openView(view: ActiveView) {
    setActiveView(view);
    if (view === "dashboard") void loadDashboard();
    if (view === "storage") void loadFiles();
    if (view === "history") void loadReports();
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
          {step === "logged-in" && <>
            <button type="button" className={activeView === "dashboard" ? "nav-active" : "nav-button"} onClick={() => openView("dashboard")}>Dashboard</button>
            <button type="button" className={activeView === "storage" ? "nav-active" : "nav-button"} onClick={() => openView("storage")}>Files</button>
            <button type="button" className={activeView === "history" ? "nav-active" : "nav-button"} onClick={() => openView("history")}>History</button>
          </>}
          <button type="button" className={activeView === "converter" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("converter")}>Unit converter</button>
          <button type="button" className={activeView === "compare" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("compare")}>Compare files</button>
          <button type="button" className={activeView === "plans" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("plans")}>Plans</button>
        </nav>
        <p className="eyebrow">WELCOME TO</p>
        <h1 id="page-title">Suhana</h1>
        <p className="subtitle">
          {activeView === "converter" && "Convert digital storage units"}
          {activeView === "compare" && "Compare image and PDF files"}
          {activeView === "dashboard" && "Your Suhana workspace"}
          {activeView === "storage" && "Private cloud storage"}
          {activeView === "history" && "Saved comparison reports"}
          {activeView === "reset" && "Reset your password"}
          {activeView === "plans" && "Storage plans"}
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

        {activeView === "dashboard" && (
          <div className="workspace-panel">
            <h2>Welcome, {dashboard?.username ?? "user"}</h2>
            <p>{dashboard?.file_count ?? 0} files in your workspace.</p>
            {dashboard?.storage && <p>Plan: <strong>{dashboard.storage.plan}</strong> · {dashboard.storage.used_bytes} / {dashboard.storage.quota_bytes} bytes used.</p>}
            <div className="action-grid">
              <button type="button" onClick={() => openView("storage")}>Manage files</button>
              <button type="button" onClick={() => openView("history")}>View history</button>
            </div>
          </div>
        )}

        {activeView === "storage" && (
          <div className="workspace-panel">
            <form onSubmit={handleUpload}>
              <label htmlFor="stored-file">Upload a file</label>
              <input id="stored-file" name="file" type="file" required />
              <button type="submit" disabled={loading || !csrfToken}>{loading ? "Uploading..." : "Upload"}</button>
            </form>
            <ul className="file-list">{files?.map((file) => <li key={file.id}>
              <span>{file.name} <small>{file.size_bytes} bytes</small></span>
              <span>
                <a href={`/api/storage/files/${file.id}/download/`} target="_blank" rel="noreferrer">Download</a>
                <button type="button" className="danger-button" onClick={() => handleDeleteFile(file.id)}>Delete</button>
              </span>
            </li>)}</ul>
          </div>
        )}

        {activeView === "history" && (
          <div className="workspace-panel">
            {reports?.length ? reports.map((report) => <article className="report-card" key={report.id}>
              <strong>{report.first_name} vs {report.second_name}</strong>
              <span>{report.result.same_content ? "Identical content" : "Differences found"} · {new Date(report.created_at).toLocaleString()}</span>
            </article>) : <p>No saved comparison reports yet.</p>}
          </div>
        )}

        {activeView === "plans" && (
          <div className="workspace-panel plan-grid">
            <article className="plan-card"><h2>Free</h2><p>Starter storage for personal comparisons.</p><strong>Upgrade-ready</strong></article>
            <article className="plan-card featured"><h2>Pro</h2><p>Higher quota and room for larger workspaces.</p><strong>Payment integration coming later</strong></article>
          </div>
        )}

        {activeView === "reset" && (
          <form onSubmit={resetRequested ? handleResetConfirm : handleResetRequest}>
            <label htmlFor="reset-email">Email</label>
            <input id="reset-email" type="email" value={resetForm.email} onChange={(event) => setResetForm({ ...resetForm, email: event.target.value })} required />
            {resetRequested && <>
              <label htmlFor="reset-otp">OTP</label>
              <input id="reset-otp" inputMode="numeric" maxLength={6} value={resetForm.otp} onChange={(event) => setResetForm({ ...resetForm, otp: event.target.value.replace(/\D/g, "") })} required />
              <label htmlFor="reset-password">New password</label>
              <input id="reset-password" type="password" autoComplete="new-password" value={resetForm.password} onChange={(event) => setResetForm({ ...resetForm, password: event.target.value })} required />
            </>}
            <button type="submit" disabled={loading || !csrfToken}>{resetRequested ? "Reset password" : "Send reset OTP"}</button>
          </form>
        )}

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
            <button type="button" className="secondary-button" onClick={() => setActiveView("reset")}>Forgot password?</button>
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
