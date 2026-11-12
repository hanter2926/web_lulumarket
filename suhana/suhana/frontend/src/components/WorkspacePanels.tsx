import type { ApiResponse, CompressionHistoryItem, ReportItem } from "../types";

export function DashboardPanel({ dashboard, onFiles, onHistory }: {
  dashboard: ApiResponse | null;
  onFiles: () => void;
  onHistory: () => void;
}) {
  return <div className="workspace-panel">
    <h2>Welcome, {dashboard?.username ?? "user"}</h2>
    <p>{dashboard?.file_count ?? 0} files in your workspace.</p>
    {dashboard?.storage && <section aria-label="Storage usage">
      <p>Plan: <strong>{dashboard.storage.plan}</strong></p>
      <p>Total storage: {dashboard.storage.quota_bytes.toLocaleString()} bytes</p>
      <p>Used: {dashboard.storage.used_bytes.toLocaleString()} bytes</p>
      <p>Available: {dashboard.storage.available_bytes.toLocaleString()} bytes</p>
      <progress
        max={dashboard.storage.quota_bytes || 1}
        value={Math.min(dashboard.storage.used_bytes, dashboard.storage.quota_bytes)}
        aria-label="Storage used"
      />
    </section>}
    <section>
      <h2>Recent files</h2>
      {dashboard?.recent_files?.length
        ? <ul className="file-list">{dashboard.recent_files.map((file) =>
          <li key={file.id}><span>{file.name} <small>{file.size_bytes.toLocaleString()} bytes</small></span></li>)}</ul>
        : <p>No files uploaded yet.</p>}
    </section>
    <section>
      <h2>Recent activity</h2>
      {dashboard?.recent_activities?.length
        ? <ul className="file-list">{dashboard.recent_activities.map((activity, index) =>
          <li key={`${activity.type}-${activity.created_at}-${index}`}>
            <span>{activity.description} <small>{new Date(activity.created_at).toLocaleString()}</small></span>
          </li>)}</ul>
        : <p>No recent processing activity.</p>}
    </section>
    <div className="action-grid">
      <button type="button" onClick={onFiles}>Manage files</button>
      <button type="button" onClick={onHistory}>View history</button>
    </div>
  </div>;
}

export function HistoryPanel({
  reports,
  compressions,
}: {
  reports: ReportItem[];
  compressions: CompressionHistoryItem[];
}) {
  return <div className="workspace-panel">
    <section>
      <h2>Comparisons</h2>
      {reports.length ? reports.map((report) => <article className="report-card" key={report.id}>
        <strong>{report.first_name} vs {report.second_name}</strong>
        <span>{report.result.same_content ? "Identical content" : "Differences found"} · {new Date(report.created_at).toLocaleString()}</span>
      </article>) : <p>No saved comparison reports yet.</p>}
    </section>
    <section>
      <h2>Compressions</h2>
      {compressions.length ? compressions.map((compression) => <article className="report-card" key={compression.id}>
        <strong>{compression.first_name}</strong>
        <span>
          {compression.result.content_type} · {compression.result.input_bytes.toLocaleString()} →{" "}
          {compression.result.output_bytes.toLocaleString()} bytes · {new Date(compression.created_at).toLocaleString()}
        </span>
      </article>) : <p>No saved compression records yet.</p>}
      <p>Image analysis runs only in your browser and is not saved to account history.</p>
    </section>
  </div>;
}

export function PlansPanel() {
  return <div className="workspace-panel plan-grid">
    <article className="plan-card"><h2>Free</h2><p>Starter storage for personal comparisons.</p><strong>Available now</strong></article>
    <article className="plan-card featured"><h2>Pro</h2><p>Higher quota and room for larger workspaces.</p><strong>Contact support to upgrade</strong></article>
  </div>;
}
