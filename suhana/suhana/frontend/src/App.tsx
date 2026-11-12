import { useEffect, useRef, useState } from "react";
import "./App.css";
import AuthPanel from "./components/AuthPanel";
import ImageSizeAnalyzer from "./components/ImageSizeAnalyzer";
import ToolPanels from "./components/ToolPanels";
import StoragePanel from "./components/StoragePanel";
import { DashboardPanel, HistoryPanel, PlansPanel } from "./components/WorkspacePanels";
import { errorMessage, getCsrfToken, postJson, readJson, responseErrorMessage } from "./api";
import {
  createTextDownload,
  createVerifiedPngDownload,
  revokeDownloads,
  verifyImageBlob,
  verifyPdfHeader,
  type DownloadArtifact,
} from "./downloadUtils";
import type {
  ActiveView,
  ApiResponse,
  ComparisonResponse,
  CompressionHistoryItem,
  ImageComparisonResult,
  PdfComparisonResult,
  RegistrationStep,
} from "./types";

type ToolStatus = "idle" | "file_selected" | "processing" | "success" | "error";

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

const pageTitles: Record<ActiveView, string> = {
  auth: "Account",
  dashboard: "Dashboard",
  storage: "Files",
  history: "History",
  converter: "Unit Converter",
  "image-size": "Image Size Analyzer",
  compare: "Compare Files",
  compress: "Compress Files",
  plans: "Plans",
  reset: "Password Reset",
};

function csvRow(values: Array<string | number | boolean | null>) {
  return values.map((value) => {
    const text = value === null ? "" : String(value);
    const safeText = /^[=+\-@]/.test(text) ? `'${text}` : text;
    return `"${safeText.replaceAll('"', '""')}"`;
  }).join(",");
}

function comparisonCsv(result: NonNullable<ComparisonResponse["comparison"]>) {
  const rows = [
    csvRow(["Metric", "Value"]),
    csvRow(["Same content", result.same_content]),
    csvRow(["Same format", result.same_type]),
    csvRow(["First file", result.first.name]),
    csvRow(["First format", result.first.content_type]),
    csvRow(["First size bytes", result.first.size_bytes]),
    csvRow(["Second file", result.second.name]),
    csvRow(["Second format", result.second.content_type]),
    csvRow(["Second size bytes", result.second.size_bytes]),
  ];
  if (result.image_comparison) {
    rows.push(
      csvRow(["Comparison", "Pixel-level image comparison"]),
      csvRow(["Same visual", result.image_comparison.same_visual]),
      csvRow(["Visual differences", result.image_comparison.visual_differences]),
    );
    result.image_comparison.frame_results.forEach((frame) => {
      rows.push(csvRow([
        `Frame ${frame.frame}`,
        frame.status,
        frame.visual?.differing_pixels ?? "",
        frame.visual?.difference_percentage ?? "",
      ]));
    });
  }
  if (result.pdf_comparison) {
    rows.push(
      csvRow(["Comparison", "PDF page comparison"]),
      csvRow(["First page count", result.pdf_comparison.first.page_count]),
      csvRow(["Second page count", result.pdf_comparison.second.page_count]),
      csvRow(["Text differences", result.pdf_comparison.text_differences]),
      csvRow(["Visual differences", result.pdf_comparison.visual_differences]),
    );
    result.pdf_comparison.page_results.forEach((page) => {
      rows.push(csvRow([
        `Page ${page.page}`,
        page.status ?? (page.text_same ? "Text identical" : "Text differs"),
        page.visual?.difference_percentage ?? "",
        page.visual?.differing_pixels ?? "",
      ]));
    });
  }
  return `${rows.join("\r\n")}\r\n`;
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
    standard: "decimal" as "decimal" | "binary",
  });
  const [conversionResult, setConversionResult] = useState("");
  const [conversionStatus, setConversionStatus] = useState<ToolStatus>("idle");
  const [conversionDownload, setConversionDownload] = useState<DownloadArtifact | null>(null);
  const [comparisonResult, setComparisonResult] = useState("");
  const [comparisonStatus, setComparisonStatus] = useState<ToolStatus>("idle");
  const [comparisonDownloads, setComparisonDownloads] = useState<DownloadArtifact[]>([]);
  const [compressionResult, setCompressionResult] = useState<{
    message: string;
    inputBytes?: number;
    outputBytes?: number;
    downloadUrl?: string;
    filename?: string;
    contentType?: string;
    targetBytes?: number | null;
    targetReached?: boolean | null;
    width?: number | null;
    height?: number | null;
    quality?: number | null;
  } | null>(null);
  const [compressionStatus, setCompressionStatus] = useState<ToolStatus>("idle");
  const [pdfComparison, setPdfComparison] = useState<PdfComparisonResult | null>(null);
  const [imageComparison, setImageComparison] = useState<ImageComparisonResult | null>(null);
  const [activeComparisonJob, setActiveComparisonJob] = useState<{
    statusUrl: string;
    cancelUrl: string;
    token: string;
  } | null>(null);
  const [activeCompressionJob, setActiveCompressionJob] = useState<{
    statusUrl: string;
    cancelUrl: string;
    token: string;
  } | null>(null);
  const [dashboard, setDashboard] = useState<ApiResponse | null>(null);
  const [files, setFiles] = useState<ApiResponse["files"]>([]);
  const [folders, setFolders] = useState<ApiResponse["folders"]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<number | null>(null);
  const [reports, setReports] = useState<ApiResponse["reports"]>([]);
  const [compressions, setCompressions] = useState<CompressionHistoryItem[]>([]);
  const [resetForm, setResetForm] = useState({ email: "", otp: "", password: "" });
  const [resetRequested, setResetRequested] = useState(false);
  const registrationInFlight = useRef(false);
  const conversionInFlight = useRef(false);
  const comparisonInFlight = useRef(false);
  const compressionInFlight = useRef(false);
  const comparisonRun = useRef(0);
  const compressionRun = useRef(0);
  const conversionRun = useRef(0);

  const updateFormField = (field: keyof typeof initialForm, value: string) =>
    setForm((current) => ({ ...current, [field]: value }));

  useEffect(() => {
    if (
      import.meta.env.DEV &&
      ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
      Boolean(window.location.port) &&
      window.location.port !== "5174"
    ) {
      const canonicalUrl = new URL(window.location.href);
      canonicalUrl.port = "5174";
      window.location.replace(canonicalUrl.toString());
      return;
    }

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

  useEffect(() => {
    const downloadUrl = compressionResult?.downloadUrl;
    if (!downloadUrl) return;
    return () => URL.revokeObjectURL(downloadUrl);
  }, [compressionResult?.downloadUrl]);

  useEffect(() => () => {
    if (conversionDownload) URL.revokeObjectURL(conversionDownload.url);
  }, [conversionDownload]);

  useEffect(() => () => revokeDownloads(comparisonDownloads), [comparisonDownloads]);

  async function handleRegister(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (registrationInFlight.current) {
      return;
    }
    setMessage("");

    if (form.password !== form.confirmPassword) {
      setMessage("Passwords do not match.");
      return;
    }

    if (!csrfToken) {
      setMessage("Security token is not ready. Please try again.");
      return;
    }

    registrationInFlight.current = true;
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
        setMessage(
          data.message ??
            (response.status === 403
              ? "Registration was blocked by security validation. Refresh the page and try again."
              : `Registration failed (HTTP ${response.status}).`),
        );
        return;
      }

      setStep("verify");
      setResendCooldown(60);
      setMessage(data.message ?? "OTP sent successfully. Please check your email.");
    } catch (error: unknown) {
      setMessage(errorMessage(error));
    } finally {
      registrationInFlight.current = false;
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
      setCompressions([]);
      setSelectedFolderId(null);
      setPdfComparison(null);
      setImageComparison(null);
      setMessage(data.message ?? "Logout successful.");
    } catch (error: unknown) {
      setMessage(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function handleConversion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (conversionInFlight.current) return;
    conversionInFlight.current = true;
    const run = ++conversionRun.current;
    if (conversionDownload) {
      URL.revokeObjectURL(conversionDownload.url);
      setConversionDownload(null);
    }
    setLoading(true);
    setConversionStatus("processing");
    setConversionResult("");
    try {
      const { response, data } = await postJson(
        "/api/tools/convert/",
        conversion,
        csrfToken,
      );
      if (run !== conversionRun.current) return;
      if (!response.ok || !data.success) {
        setConversionStatus("error");
        setConversionResult(responseErrorMessage(response, data, "Conversion"));
        return;
      }
      setConversionResult(`${data.result} ${conversion.to.toUpperCase()}`);
      const report = createTextDownload(
        `value,from,to,standard,result\r\n${csvRow([
          conversion.value,
          conversion.from,
          conversion.to,
          conversion.standard,
          data.result ?? "",
        ])}\r\n`,
        "text/csv;charset=utf-8",
        "unit-conversion.csv",
      );
      if (!report) throw new Error("The conversion report could not be generated.");
      setConversionDownload(report);
      setConversionStatus("success");
    } catch (error: unknown) {
      if (run === conversionRun.current) {
        setConversionStatus("error");
        setConversionResult(errorMessage(error));
      }
    } finally {
      if (run === conversionRun.current) {
        conversionInFlight.current = false;
        setLoading(false);
      }
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
        if (response.ok) {
          setReports(data.reports ?? []);
          setCompressions(data.compressions ?? []);
        }
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

  async function handleRenameFile(id: number, currentName: string) {
    const name = window.prompt("New file name", currentName);
    if (!name?.trim()) return;
    try {
      const response = await fetch(`/api/storage/files/${id}/rename/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: new URLSearchParams({ name: name.trim() }),
      });
      const data = await readJson(response);
      setMessage(data.message ?? (response.ok ? "File renamed." : "Unable to rename file."));
      if (response.ok) await loadFiles();
    } catch (error: unknown) {
      setMessage(errorMessage(error));
    }
  }

  async function handleMoveFile(id: number, folderId: number | null) {
    try {
      const response = await fetch(`/api/storage/files/${id}/move/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: new URLSearchParams({ folder: folderId === null ? "" : String(folderId) }),
      });
      const data = await readJson(response);
      setMessage(data.message ?? (response.ok ? "File moved." : "Unable to move file."));
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
    if (comparisonInFlight.current) return;
    const run = ++comparisonRun.current;
    setComparisonDownloads([]);
    setComparisonResult("");
    setPdfComparison(null);
    setImageComparison(null);
    const formData = new FormData(event.currentTarget);
    const firstFile = formData.get("first");
    const secondFile = formData.get("second");
    if (!(firstFile instanceof File) || !(secondFile instanceof File) ||
        firstFile.size === 0 || secondFile.size === 0) {
      setLoading(false);
      setComparisonStatus("error");
      setComparisonResult("Choose two files before comparing.");
      return;
    }
    comparisonInFlight.current = true;
    setLoading(true);
    setComparisonStatus("processing");
    setActiveComparisonJob(null);
    let pendingDownloads: DownloadArtifact[] = [];
    try {
      const response = await fetch("/api/tools/compare/", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: formData,
      });
      const data = (await readJson(response)) as ComparisonResponse;
      if (run !== comparisonRun.current) return;
      if (!response.ok || !data.success || !data.status_url || !data.cancel_url || !data.job_token) {
        setComparisonStatus("error");
        setComparisonResult(responseErrorMessage(response, data, "Comparison request"));
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
        if (run !== comparisonRun.current) return;
        if (!statusResponse.ok || !statusData.status) {
          setComparisonStatus("error");
          setComparisonResult(responseErrorMessage(statusResponse, statusData, "Comparison status check"));
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
          setComparisonStatus("idle");
          setComparisonResult(statusData.stage ?? "Comparison cancelled.");
          return;
        }
        if (state === "failed" || !statusData.comparison) {
          setComparisonStatus("error");
          setComparisonResult(statusData.message ?? statusData.stage ?? "Comparison failed.");
          return;
        }
        if (state !== "completed") {
          setComparisonStatus("error");
          setComparisonResult("The worker returned an unknown comparison state.");
          return;
        }
        completed = statusData;
        break;
      }

      const result = completed.comparison;
      if (!result) {
        setComparisonStatus("error");
        setComparisonResult("Comparison finished without a result.");
        return;
      }
      const report = createTextDownload(
        comparisonCsv(result),
        "text/csv;charset=utf-8",
        "comparison-report.csv",
      );
      if (!report) throw new Error("The comparison report could not be generated.");
      const downloads: DownloadArtifact[] = [report];
      pendingDownloads = downloads;
      if (result.pdf_comparison) {
        const pdf = result.pdf_comparison;
        setPdfComparison(pdf);
        for (const page of pdf.page_results) {
          if (!page.visual?.overlay_png) continue;
          const overlay = await createVerifiedPngDownload(
            page.visual.overlay_png,
            `pdf-page-${page.page}-difference.png`,
          );
          if (run !== comparisonRun.current) {
            revokeDownloads([report, ...downloads.slice(1)]);
            return;
          }
          if (overlay) downloads.push(overlay);
        }
        setComparisonResult(
          `${pdf.text_differences} page text difference(s), ${pdf.visual_differences} visual difference(s). ` +
          `Pages: ${pdf.first.page_count} vs ${pdf.second.page_count}.`,
        );
      } else if (result.image_comparison) {
        const image = result.image_comparison;
        setImageComparison(image);
        for (const frame of image.frame_results) {
          if (!frame.visual?.overlay_png) continue;
          const overlay = await createVerifiedPngDownload(
            frame.visual.overlay_png,
            `image-frame-${frame.frame}-difference.png`,
          );
          if (run !== comparisonRun.current) {
            revokeDownloads([report, ...downloads.slice(1)]);
            return;
          }
          if (overlay) downloads.push(overlay);
        }
        setComparisonResult(
          image.same_visual
            ? "No pixel-level visual differences were found."
            : `${image.visual_differences} frame(s) have pixel-level visual differences.`,
        );
      } else {
        setComparisonResult(
          result.same_content
            ? "The files have identical content."
            : `The files are different. Types match: ${result.same_type ? "yes" : "no"}.`,
        );
      }
      if (run === comparisonRun.current) {
        setComparisonDownloads(downloads);
        setComparisonStatus("success");
      } else {
        revokeDownloads(downloads);
      }
    } catch (error: unknown) {
      revokeDownloads(pendingDownloads);
      if (run === comparisonRun.current) {
        setComparisonStatus("error");
        setComparisonResult(errorMessage(error));
      }
    } finally {
      if (run === comparisonRun.current) {
        comparisonInFlight.current = false;
        setLoading(false);
        setActiveComparisonJob(null);
      }
    }
  }

  function handleComparisonInputChange() {
    comparisonRun.current += 1;
    comparisonInFlight.current = false;
    setLoading(false);
    setComparisonStatus("file_selected");
    setComparisonResult("");
    setImageComparison(null);
    setPdfComparison(null);
    setActiveComparisonJob(null);
    setComparisonDownloads([]);
  }

  async function handleCompression(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (compressionInFlight.current) return;
    const run = ++compressionRun.current;
    setCompressionResult(null);
    const formData = new FormData(event.currentTarget);
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setLoading(false);
      setCompressionStatus("error");
      setCompressionResult({ message: "Choose a non-empty file to compress." });
      return;
    }

    compressionInFlight.current = true;
    setLoading(true);
    setCompressionStatus("processing");
    setCompressionResult({ message: "Uploading file to the private processing queue..." });
    setActiveCompressionJob(null);
    try {
      const response = await fetch("/api/tools/compress/", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: formData,
      });
      const accepted = await readJson(response);
      if (run !== compressionRun.current) {
        if (response.ok && accepted.status_url && accepted.cancel_url && accepted.job_token) {
          void postCompressionCancellation({
            cancelUrl: accepted.cancel_url,
            token: accepted.job_token,
          }).catch((error: unknown) => {
            console.error("Could not cancel an obsolete compression job.", error);
          });
        }
        return;
      }
      if (!response.ok || !accepted.success || !accepted.status_url || !accepted.cancel_url || !accepted.job_token) {
        setCompressionStatus("error");
        setCompressionResult({
          message: responseErrorMessage(response, accepted, "Compression request"),
        });
        return;
      }

      const activeJob = {
        statusUrl: accepted.status_url,
        cancelUrl: accepted.cancel_url,
        token: accepted.job_token,
      };
      setActiveCompressionJob(activeJob);
      setCompressionResult({ message: "Compression queued." });

      let completed: ApiResponse | null = null;
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        const statusResponse = await fetch(activeJob.statusUrl, {
          headers: { "X-Job-Token": activeJob.token },
          credentials: "include",
        });
        const statusData = await readJson(statusResponse);
        if (run !== compressionRun.current) return;
        if (!statusResponse.ok || !statusData.status) {
          setCompressionStatus("error");
          setCompressionResult({
            message: responseErrorMessage(statusResponse, statusData, "Compression status check"),
          });
          return;
        }
        if (statusData.state === "queued" || statusData.state === "processing") {
          setCompressionResult({ message: statusData.stage ?? "Compressing file..." });
          continue;
        }
        if (statusData.state === "cancelled") {
          setCompressionStatus("idle");
          setCompressionResult({ message: statusData.stage ?? "Compression cancelled." });
          return;
        }
        if (statusData.state === "failed" || !statusData.compression || !statusData.download_url) {
          setCompressionStatus("error");
          setCompressionResult({
            message: statusData.message ?? statusData.stage ?? "Compression failed.",
          });
          return;
        }
        if (statusData.state !== "completed") {
          setCompressionStatus("error");
          setCompressionResult({ message: "The worker returned an unknown compression state." });
          return;
        }
        completed = statusData;
        break;
      }

      const compression = completed?.compression;
      const downloadUrl = completed?.download_url;
      if (!compression || !downloadUrl) {
        throw new Error("The compression worker returned incomplete output details.");
      }
      const downloadResponse = await fetch(downloadUrl, {
        headers: { "X-Job-Token": activeJob.token },
        credentials: "include",
      });
      if (!downloadResponse.ok) {
        const downloadError = await readJson(downloadResponse);
        setCompressionStatus("error");
        setCompressionResult({
          message: responseErrorMessage(downloadResponse, downloadError, "Compressed output download"),
        });
        return;
      }
      const blob = await downloadResponse.blob();
      if (blob.size !== compression.output_bytes || blob.size === 0) {
        throw new Error("The downloaded file size did not match the validated compression result.");
      }
      const verified = compression.content_type === "application/pdf"
        ? verifyPdfHeader(new Uint8Array(await blob.slice(0, 5).arrayBuffer()))
        : await verifyImageBlob(blob);
      if (!verified) {
        throw new Error("The downloaded output could not be opened as the expected file type.");
      }
      if (run !== compressionRun.current) return;
      const actualReduction = compression.input_bytes - blob.size;
      const sizeChange = actualReduction > 0
        ? ` Reduced by ${((actualReduction / compression.input_bytes) * 100).toFixed(1)}%.`
        : actualReduction < 0
          ? ` Output is ${((Math.abs(actualReduction) / compression.input_bytes) * 100).toFixed(1)}% larger than the input.`
          : " Output size is unchanged.";
      const targetReached = compression.target_bytes == null
        ? null
        : blob.size <= compression.target_bytes;
      const targetMessage = compression.target_bytes == null
        ? ""
        : targetReached
          ? " Requested output size reached."
          : " The target is below the smallest valid output under the selected format and quality limits; the closest valid output is provided.";
      setCompressionResult({
        message: `Compression complete.${sizeChange}${targetMessage}`,
        inputBytes: compression.input_bytes,
        outputBytes: blob.size,
        downloadUrl: URL.createObjectURL(blob),
        filename: compression.filename,
        contentType: compression.content_type,
        targetBytes: compression.target_bytes,
        targetReached,
        width: compression.width,
        height: compression.height,
        quality: compression.quality,
      });
      setCompressionStatus("success");
    } catch (error: unknown) {
      if (run === compressionRun.current) {
        setCompressionStatus("error");
        setCompressionResult({ message: errorMessage(error) });
      }
    } finally {
      if (run === compressionRun.current) {
        compressionInFlight.current = false;
        setLoading(false);
        setActiveCompressionJob(null);
      }
    }
  }

  function handleCompressionInputChange() {
    if (activeCompressionJob) {
      void postCompressionCancellation(activeCompressionJob).catch((error: unknown) => {
        console.error("Could not cancel an obsolete compression job.", error);
      });
    }
    compressionRun.current += 1;
    compressionInFlight.current = false;
    setLoading(false);
    setCompressionStatus("file_selected");
    setCompressionResult(null);
    setActiveCompressionJob(null);
  }

  async function postCompressionCancellation(job: {
    cancelUrl: string;
    token: string;
  }) {
    const response = await fetch(job.cancelUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "X-Job-Token": job.token,
      },
      credentials: "include",
    });
    const data = await readJson(response);
    if (!response.ok) {
      throw new Error(data.message ?? "Unable to cancel compression.");
    }
    return data;
  }

  async function cancelCompression() {
    if (!activeCompressionJob) return;
    const run = compressionRun.current;
    try {
      const data = await postCompressionCancellation(activeCompressionJob);
      if (run !== compressionRun.current) return;
      setCompressionResult({
        message: data.status === "cancelled"
          ? "Compression cancelled."
          : "Cancellation requested. The worker is stopping safely.",
      });
    } catch (error: unknown) {
      if (run === compressionRun.current) {
        setCompressionResult({ message: errorMessage(error) });
      }
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
      <section className={`register-card register-card-${activeView}`} aria-labelledby="page-title">
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
          <button type="button" className={activeView === "image-size" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("image-size")}>Image size analyzer</button>
          <button type="button" className={activeView === "compare" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("compare")}>Compare files</button>
          <button type="button" className={activeView === "compress" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("compress")}>Compress files</button>
          <button type="button" className={activeView === "plans" ? "nav-active" : "nav-button"}
            onClick={() => setActiveView("plans")}>Plans</button>
        </nav>
        <p className="eyebrow">SUHANA FILE WORKSPACE</p>
        <h1 id="page-title">{pageTitles[activeView]}</h1>
        <p className="subtitle">
          {activeView === "converter" && "Convert digital storage units"}
          {activeView === "image-size" && "Inspect image size and dimensions"}
          {activeView === "compare" && "Compare image and PDF files"}
          {activeView === "compress" && "Compress and download a file"}
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

        <div className={`view-content view-${activeView}`}>
          {activeView === "image-size" && <ImageSizeAnalyzer />}
          {activeView === "dashboard" && <DashboardPanel dashboard={dashboard}
            onFiles={() => openView("storage")} onHistory={() => openView("history")} />}
          {activeView === "storage" && <StoragePanel csrfReady={Boolean(csrfToken)} loading={loading}
            selectedFolderId={selectedFolderId} folders={folders ?? []} files={files ?? []}
            onSelectFolder={(id) => { setSelectedFolderId(id); void loadFiles(id); }}
            onCreateFolder={createFolder} onRenameFolder={renameFolder} onDeleteFolder={deleteFolder}
            onUpload={handleUpload} onDeleteFile={handleDeleteFile}
            onRenameFile={handleRenameFile} onMoveFile={handleMoveFile} />}
          {activeView === "history" && <HistoryPanel reports={reports ?? []}
            compressions={compressions} />}
          {activeView === "plans" && <PlansPanel />}

          {activeView === "reset" && <ToolPanels active="reset" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} compressionResult={compressionResult}
          conversionStatus={conversionStatus} conversionDownload={conversionDownload}
          comparisonStatus={comparisonStatus} comparisonDownloads={comparisonDownloads}
          compressionStatus={compressionStatus}
          comparisonResult={comparisonResult} imageComparison={imageComparison} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          canCancelCompression={Boolean(activeCompressionJob)} onCancelCompression={cancelCompression}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onCompression={handleCompression}
          onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => {
            conversionRun.current += 1;
            conversionInFlight.current = false;
            setLoading(false);
            setConversionStatus("file_selected");
            setConversionResult("");
            if (conversionDownload) URL.revokeObjectURL(conversionDownload.url);
            setConversionDownload(null);
            setConversion((current) => ({ ...current, [field]: value }));
          }}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}
        {activeView === "converter" && <ToolPanels active="converter" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} compressionResult={compressionResult}
          conversionStatus={conversionStatus} conversionDownload={conversionDownload}
          comparisonStatus={comparisonStatus} comparisonDownloads={comparisonDownloads}
          compressionStatus={compressionStatus}
          comparisonResult={comparisonResult} imageComparison={imageComparison} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          canCancelCompression={Boolean(activeCompressionJob)} onCancelCompression={cancelCompression}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onCompression={handleCompression}
          onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => {
            conversionRun.current += 1;
            conversionInFlight.current = false;
            setLoading(false);
            setConversionStatus("file_selected");
            setConversionResult("");
            if (conversionDownload) URL.revokeObjectURL(conversionDownload.url);
            setConversionDownload(null);
            setConversion((current) => ({ ...current, [field]: value }));
          }}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}
        {activeView === "compare" && <ToolPanels active="compare" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} compressionResult={compressionResult}
          conversionStatus={conversionStatus} conversionDownload={conversionDownload}
          comparisonStatus={comparisonStatus} comparisonDownloads={comparisonDownloads}
          compressionStatus={compressionStatus}
          comparisonResult={comparisonResult} imageComparison={imageComparison} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          canCancelCompression={Boolean(activeCompressionJob)} onCancelCompression={cancelCompression}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onCompression={handleCompression}
          onComparisonInputChange={handleComparisonInputChange}
          onCompressionInputChange={handleCompressionInputChange}
          onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => {
            conversionRun.current += 1;
            conversionInFlight.current = false;
            setLoading(false);
            setConversionStatus("file_selected");
            setConversionResult("");
            if (conversionDownload) URL.revokeObjectURL(conversionDownload.url);
            setConversionDownload(null);
            setConversion((current) => ({ ...current, [field]: value }));
          }}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}
        {activeView === "compress" && <ToolPanels active="compress" loading={loading} csrfReady={Boolean(csrfToken)}
          conversion={conversion} conversionResult={conversionResult} compressionResult={compressionResult}
          conversionStatus={conversionStatus} conversionDownload={conversionDownload}
          comparisonStatus={comparisonStatus} comparisonDownloads={comparisonDownloads}
          compressionStatus={compressionStatus}
          comparisonResult={comparisonResult} imageComparison={imageComparison} pdfComparison={pdfComparison}
          canCancelComparison={Boolean(activeComparisonJob)} onCancelComparison={cancelComparison}
          canCancelCompression={Boolean(activeCompressionJob)} onCancelCompression={cancelCompression}
          resetForm={resetForm} resetRequested={resetRequested} onConversion={handleConversion}
          onComparison={handleComparison} onCompression={handleCompression}
          onComparisonInputChange={handleComparisonInputChange}
          onCompressionInputChange={handleCompressionInputChange}
          onResetRequest={handleResetRequest} onResetConfirm={handleResetConfirm}
          onConversionChange={(field, value) => {
            conversionRun.current += 1;
            conversionInFlight.current = false;
            setLoading(false);
            setConversionStatus("file_selected");
            setConversionResult("");
            if (conversionDownload) URL.revokeObjectURL(conversionDownload.url);
            setConversionDownload(null);
            setConversion((current) => ({ ...current, [field]: value }));
          }}
          onResetChange={(field, value) => setResetForm((current) => ({ ...current, [field]: value }))} />}

          {activeView === "auth" && <AuthPanel step={step} loading={loading} csrfReady={Boolean(csrfToken)}
          form={form} loginForm={loginForm} otp={otp} resendCooldown={resendCooldown}
          onRegister={handleRegister} onVerify={handleVerify} onResend={handleResend}
          onLogin={handleLogin} onLogout={handleLogout} onFieldChange={updateFormField}
          onOtpChange={setOtp}
          onLoginChange={(field, value) => setLoginForm((current) => ({ ...current, [field]: value }))}
          onStepChange={setStep} onReset={() => setActiveView("reset")} />}

          {activeView === "auth" && message && <p className="status-message" role="status">{message}</p>}
        </div>
      </section>
    </main>
  );
}

export default App;
