import type { FormEvent } from "react";
import type { PdfComparisonResult } from "../types";

type Props = {
  active: "reset" | "converter" | "compare";
  loading: boolean;
  csrfReady: boolean;
  conversion: { value: string; from: string; to: string };
  conversionResult: string;
  comparisonResult: string;
  pdfComparison: PdfComparisonResult | null;
  canCancelComparison: boolean;
  resetForm: { email: string; otp: string; password: string };
  resetRequested: boolean;
  onConversion: (event: FormEvent<HTMLFormElement>) => void;
  onComparison: (event: FormEvent<HTMLFormElement>) => void;
  onCancelComparison: () => void;
  onResetRequest: (event: FormEvent<HTMLFormElement>) => void;
  onResetConfirm: (event: FormEvent<HTMLFormElement>) => void;
  onConversionChange: (field: "value" | "from" | "to", value: string) => void;
  onResetChange: (field: "email" | "otp" | "password", value: string) => void;
};

const units = ["bit", "byte", "kb", "mb", "gb", "tb"];

function UnitSelect({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  return <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
    {units.map((unit) => <option value={unit} key={unit}>{unit === "bit" ? "Bit" : unit === "byte" ? "Byte" : unit.toUpperCase()}</option>)}
  </select>;
}

export default function ToolPanels(props: Props) {
  if (props.active === "reset") return (
    <form onSubmit={props.resetRequested ? props.onResetConfirm : props.onResetRequest}>
      <label htmlFor="reset-email">Email</label>
      <input id="reset-email" type="email" value={props.resetForm.email}
        onChange={(event) => props.onResetChange("email", event.target.value)} required />
      {props.resetRequested && <><label htmlFor="reset-otp">OTP</label>
        <input id="reset-otp" inputMode="numeric" maxLength={6} value={props.resetForm.otp}
          onChange={(event) => props.onResetChange("otp", event.target.value.replace(/\D/g, ""))} required />
        <label htmlFor="reset-password">New password</label>
        <input id="reset-password" type="password" autoComplete="new-password" value={props.resetForm.password}
          onChange={(event) => props.onResetChange("password", event.target.value)} required /></>}
      <button type="submit" disabled={props.loading || !props.csrfReady}>{props.resetRequested ? "Reset password" : "Send reset OTP"}</button>
    </form>
  );
  if (props.active === "converter") return <form onSubmit={props.onConversion}>
      <label htmlFor="conversion-value">Value</label>
      <input id="conversion-value" type="number" min="0" step="any" value={props.conversion.value}
        onChange={(event) => props.onConversionChange("value", event.target.value)} required />
      <label htmlFor="conversion-from">From</label>
      <UnitSelect id="conversion-from" value={props.conversion.from} onChange={(value) => props.onConversionChange("from", value)} />
      <label htmlFor="conversion-to">To</label>
      <UnitSelect id="conversion-to" value={props.conversion.to} onChange={(value) => props.onConversionChange("to", value)} />
      <button type="submit" disabled={props.loading || !props.csrfReady}>{props.loading ? "Converting..." : "Convert"}</button>
      {props.conversionResult && <p className="result-panel" role="status">{props.conversionResult}</p>}
  </form>;
  return <form onSubmit={props.onComparison}>
      <p className="helper-text">Supported formats: PNG, JPEG, GIF, WEBP, and PDF. Maximum 25 MB per file.</p>
      <label htmlFor="first-file">First file</label>
      <input id="first-file" name="first" type="file" accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required />
      <label htmlFor="second-file">Second file</label>
      <input id="second-file" name="second" type="file" accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required />
      <button type="submit" disabled={props.loading || !props.csrfReady}>{props.loading ? "Comparing..." : "Compare files"}</button>
      {props.canCancelComparison && <button type="button" onClick={props.onCancelComparison}>Cancel comparison</button>}
      {props.comparisonResult && <p className="result-panel" role="status">{props.comparisonResult}</p>}
      {props.pdfComparison && <section className="pdf-results" aria-label="PDF comparison details">
        {props.pdfComparison.page_results.map((page) => <article className="pdf-page-result" key={page.page}>
          <strong>Page {page.page}</strong>
          <span>{page.status ?? (page.text_same ? "Text identical" : "Text differs")}</span>
          {page.visual && <span>Visual difference: {page.visual.difference_percentage}%</span>}
          {page.visual?.overlay_png && <img src={page.visual.overlay_png} alt={`Difference overlay for page ${page.page}`} />}
        </article>)}
      </section>}
  </form>;
}
