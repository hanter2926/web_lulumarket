import { useEffect, useState } from "react";
import "./App.css";
import AuthPanel from "./components/AuthPanel";
import ToolPanels from "./components/ToolPanels";
import StoragePanel from "./components/StoragePanel";
import { DashboardPanel, HistoryPanel, PlansPanel } from "./components/WorkspacePanels";
import { errorMessage, getCsrfToken, postJson, readJson } from "./api";
import type { ActiveView, ApiResponse, ComparisonResponse, PdfComparisonResult, RegistrationStep } from "./types";

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
  const [pdfComparison, setPdfComparison] = useState<PdfComparisonResult | null>(null);
  const [activeComparisonJob, setActiveComparisonJob] = useState<{
    statusUrl: string;
    cancelUrl: string;
    token: string;
  } | null>(null);
  const [dashboard, setDashboard] = useState<ApiResponse | null>(null);
  const [files, setFiles] = useState<ApiResponse["files"]>([]);
  const [folders, setFolders] = useState<ApiResponse["folders"]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<number | null>(null);
  const [reports, setReports] = useState<ApiResponse["reports"]>([]);
  const [resetForm, setResetForm] = useState({ email: "", otp: "", password: "" });
  const [resetRequested, setResetRequested] = useState(false);

  const updateFormField = (field: keyof typeof initialForm, value: string) =>
    setForm((current) => ({ ...current, [field]: value }));

  useEffect(() => {
    getCsrfToken()
      .then(setCsrfToken)
      .catch((error: unknown) => {
        setMessage(errorMessage(error));
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
        setMessage(data.message ?? `Registration failed (HTTP ${response.status}).`);
        return;
      }

      setStep("verify");
      setResendCooldown(60);
      setMessage(data.message ?? "OTP sent successfully. Please check your email.");
    } catch (error: unknown) {
      setMessage(errorMessage(error));
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
      setMessage(errorMessage(error));
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
      setMessage(errorMessage(error));
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
      setMessage(errorMessage(error));
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
      setActiveView("auth");
      setDashboard(null);
      setFiles([]);
      setFolders([]);
      setReports([]);
      setSelectedFolderId(null);
      setPdfComparison(null);
      setMessage(data.message ?? "Logout successful.");
    } catch (error: unknown) {
      setMessage(errorMessage(error));
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
      setConversionResult(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadDashboard() {
      try {
        const response = await fetch("/api/storage/dashboard/", { credentials: "include" });
        const data = await readJson(response);
        if (response.ok) setDashboard(data);
        else setMessage(data.message ?? "Unable to load dashboard.");
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  async function loadFiles(folderId = selectedFolderId) {
      try {
        const query = folderId === null ? "" : `?folder=${folderId}`;
        const response = await fetch(`/api/storage/files/${query}`, { credentials: "include" });
        const data = await readJson(response);
        if (response.ok) setFiles(data.files ?? []);
        else setMessage(data.message ?? "Unable to load files.");
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  async function loadFolders() {
      try {
        const response = await fetch("/api/storage/folders/tree/", { credentials: "include" });
        const data = await readJson(response);
        if (response.ok) setFolders(data.folders ?? []);
        else setMessage(data.message ?? "Unable to load folders.");
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  async function loadReports() {
      try {
        const response = await fetch("/api/tools/reports/", { credentials: "include" });
        const data = await readJson(response);
        if (response.ok) setReports(data.reports ?? []);
        else setMessage(data.message ?? "Unable to load comparison history.");
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
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
        const data = await readJson(response);
        setMessage(data.message ?? (response.ok ? "File uploaded." : "Upload failed."));
        if (response.ok) await loadFiles();
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      } finally {
        setLoading(false);
      }
  }

  async function handleDeleteFile(id: number) {
      if (!window.confirm("Delete this file permanently?")) return;
      try {
        const response = await fetch(`/api/storage/files/${id}/delete/`, {
          method: "POST", headers: { "X-CSRFToken": csrfToken }, credentials: "include",
        });
        const data = await readJson(response);
        setMessage(data.message ?? (response.ok ? "File deleted." : "Unable to delete file."));
        if (response.ok) await loadFiles();
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  async function handleResetRequest(event: React.FormEvent<HTMLFormElement>) {
      event.preventDefault();
      try {
        const { response, data } = await postJson("/api/accounts/password-reset/request/",
          { email: resetForm.email }, csrfToken);
        setMessage(data.message ?? "Reset request submitted.");
        if (response.ok) setResetRequested(true);
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  async function handleResetConfirm(event: React.FormEvent<HTMLFormElement>) {
      event.preventDefault();
      try {
        const { response, data } = await postJson("/api/accounts/password-reset/confirm/",
          resetForm, csrfToken);
        setMessage(data.message ?? "Password reset complete.");
        if (response.ok) { setResetRequested(false); setActiveView("auth"); setStep("login"); }
      } catch (error: unknown) {
        setMessage(errorMessage(error));
      }
  }

  function openView(view: ActiveView) {
    setActiveView(view);
    if (view === "dashboard") void loadDashboard();
    if (view === "storage") {
      void loadFiles();
      void loadFolders();
    }
    if (view === "history") void loadReports();
  }

  async function createFolder() {
    const name = window.prompt("Folder name");
    if (!name?.trim()) return;
    const body = new URLSearchParams({ name: name.trim() });
    if (selectedFolderId !== null) body.set("parent", String(selectedFolderId));
    const response = await fetch("/api/storage/folders/", {
      method: "POST", headers: { "X-CSRFToken": csrfToken }, credentials: "include", body,
    });
    const data = (await response.json()) as ApiResponse;
    setMessage(data.message ?? (response.ok ? "Folder created." : "Unable to create folder."));
    if (response.ok) await loadFolders();
  }

  async function renameFolder(folderId: number, currentName: string) {
    const name = window.prompt("New folder name", currentName);
    if (!name?.trim()) return;
    const body = new URLSearchParams({ name: name.trim() });
    const response = await fetch(`/api/storage/folders/${folderId}/rename/`, {
      method: "POST", headers: { "X-CSRFToken": csrfToken }, credentials: "include", body,
    });
    const data = (await response.json()) as ApiResponse;
    setMessage(data.message ?? "Folder updated.");
    if (response.ok) await loadFolders();
  }

  async function deleteFolder(folderId: number) {
    if (!window.confirm("Delete this folder and all nested files?")) return;
    const response = await fetch(`/api/storage/folders/${folderId}/delete/`, {
      method: "POST", headers: { "X-CSRFToken": csrfToken }, credentials: "include",
    });
    const data = (await response.json()) as ApiResponse;
    setMessage(data.message ?? "Folder deleted.");
    if (response.ok) {
      setSelectedFolderId(null);
      await Promise.all([loadFolders(), loadFiles(null)]);
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
    setPdfComparison(null);
    setActiveComparisonJob(null);
    try {
      const response = await fetch("/api/tools/compare/", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: formData,
      });
      const data = (await readJson(response)) as ComparisonResponse;
      if (!response.ok || !data.success || !data.status_url || !data.cancel_url || !data.job_token) {
        setComparisonResult(data.message ?? "Comparison failed.");
        return;
      }
      const activeJob = {
        statusUrl: data.status_url,
        cancelUrl: data.cancel_url,
        token: data.job_token,
      };
      setActiveComparisonJob(activeJob);
      setComparisonResult("Comparison queued. Processing...");

      let completed: ComparisonResponse;
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        const statusResponse = await fetch(activeJob.statusUrl, {
          headers: { "X-Job-Token": activeJob.token },
          credentials: "include",
        });
        const statusData = (await readJson(statusResponse)) as ComparisonResponse;
        if (!statusResponse.ok || !statusData.status) {
          setComparisonResult(statusData.message ?? "Unable to check comparison status.");
          return;
        }
        const state = statusData.state ?? (
          statusData.status === "running"
            ? "processing"
            : statusData.status === "succeeded"
              ? "completed"
              : statusData.status
        );
        if (state === "queued" || state === "processing") {
          setComparisonResult(statusData.stage ?? (
            state === "processing" ? "Comparing files..." : "Comparison queued..."
          ));
          continue;
        }
        if (state === "cancelled") {
          setComparisonResult(statusData.stage ?? "Comparison cancelled.");
          return;
        }
        if (state === "failed" || !statusData.comparison) {
          setComparisonResult(statusData.message ?? statusData.stage ?? "Comparison failed.");
          return;
        }
        if (state !== "completed") {
          setComparisonResult("The worker returned an unknown comparison state.");
          return;
        }
        completed = statusData;
        break;
      }

      const result = completed.comparison;
      if (!result) {
        setComparisonResult("Comparison finished without a result.");
        return;
      }
      if (result.pdf_comparison) {
        const pdf = result.pdf_comparison;
        setPdfComparison(pdf);
        setComparisonResult(
          `${pdf.text_differences} page text difference(s), ${pdf.visual_differences} visual difference(s). ` +
          `Pages: ${pdf.first.page_count} vs ${pdf.second.page_count}.`,
        );
      } else {
        setComparisonResult(
          result.same_content
            ? "The files have identical content."
            : `The files are different. Types match: ${result.same_type ? "yes" : "no"}.`,
        );
      }
    } catch (error: unknown) {
      setComparisonResult(errorMessage(error));
    } finally {
      setLoading(false);
      setActiveComparisonJob(null);
    }
  }

  async function cancelComparison() {
    if (!activeComparisonJob) return;
    try {
      const response = await fetch(activeComparisonJob.cancelUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
          "X-Job-Token": activeComparisonJob.token,
        },
        credentials: "include",
      });
      const data = await readJson(response);
      if (!response.ok) {
        setComparisonResult(data.message ?? "Unable to cancel comparison.");
      } else {
        setComparisonResult(
          data.status === "cancelled"
            ? "Comparison cancelled."
            : "Cancellation requested. The worker is stopping safely.",
        );
      }
    } catch (error: unknown) {
      setComparisonResult(errorMessage(error));
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

        {activeView === "dashboard" && <DashboardPanel dashboard={dashboard}
          onFiles={() => openView("storage")} onHistory={() => openView("history")} />}
        {activeView === "storage" && <StoragePanel csrfReady={Boolean(csrfToken)} loading={loading}
          selectedFolderId={selectedFolderId} folders={folders ?? []} files={files ?? []}
          onSelectFolder={(id) => { setSelectedFolderId(id); void loadFiles(id); }}
          onCreateFolder={createFolder} onRenameFolder={renameFolder} onDeleteFolder={deleteFolder}
          onUpload={handleUpload} onDeleteFile={handleDeleteFile} />}
        {activeView === "history" && <HistoryPanel reports={reports ?? []} />}
        {activeView === "plans" && <PlansPanel />}

        {activeView === "reset" && <ToolPanels active="reset" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} comparisonResult={comparisonResult} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => setConversion((current) => ({ ...current, [field]: value }))}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}
        {activeView === "converter" && <ToolPanels active="converter" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} comparisonResult={comparisonResult} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => setConversion((current) => ({ ...current, [field]: value }))}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}
        {activeView === "compare" && <ToolPanels active="compare" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} comparisonResult={comparisonResult} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => setConversion((current) => ({ ...current, [field]: value }))}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}

        {activeView === "auth" && <AuthPanel step={step} loading={loading} csrfReady={Boolean(csrfToken)}
          form={form} loginForm={loginForm} otp={otp} resendCooldown={resendCooldown}
          onRegister={handleRegister} onVerify={handleVerify} onResend={handleResend}
          onLogin={handleLogin} onLogout={handleLogout} onFieldChange={updateFormField}
          onOtpChange={setOtp}
          onLoginChange={(field, value) => setLoginForm((current) => ({ ...current, [field]: value }))}
          onStepChange={setStep} onReset={() => setActiveView("reset")} />}

        {activeView === "auth" && message && <p className="status-message" role="status">{message}</p>}
      </section>
    </main>
  );
}

export default App;
