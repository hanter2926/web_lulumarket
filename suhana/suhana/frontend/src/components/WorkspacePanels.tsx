import type { ApiResponse, ReportItem } from "../types";

export function DashboardPanel({ dashboard, onFiles, onHistory }: {
  dashboard: ApiResponse | null;
  onFiles: () => void;
  onHistory: () => void;
}) {
  return <div className="workspace-panel">
    <h2>Welcome, {dashboard?.username ?? "user"}</h2>
    <p>{dashboard?.file_count ?? 0} files in your workspace.</p>
    {dashboard?.storage && <p>Plan: <strong>{dashboard.storage.plan}</strong> · {dashboard.storage.used_bytes} / {dashboard.storage.quota_bytes} bytes used.</p>}
    <div className="action-grid">
      <button type="button" onClick={onFiles}>Manage files</button>
      <button type="button" onClick={onHistory}>View history</button>
    </div>
  </div>;
}

export function HistoryPanel({ reports }: { reports: ReportItem[] }) {
  return <div className="workspace-panel">
    {reports.length ? reports.map((report) => <article className="report-card" key={report.id}>
      <strong>{report.first_name} vs {report.second_name}</strong>
      <span>{report.result.same_content ? "Identical content" : "Differences found"} · {new Date(report.created_at).toLocaleString()}</span>
    </article>) : <p>No saved comparison reports yet.</p>}
  </div>;
}

export function PlansPanel() {
  return <div className="workspace-panel plan-grid">
    <article className="plan-card"><h2>Free</h2><p>Starter storage for personal comparisons.</p><strong>Upgrade-ready</strong></article>
    <article className="plan-card featured"><h2>Pro</h2><p>Higher quota and room for larger workspaces.</p><strong>Payment integration coming later</strong></article>
  </div>;
}
