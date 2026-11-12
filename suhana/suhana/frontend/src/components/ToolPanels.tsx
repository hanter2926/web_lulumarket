import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import type { ImageComparisonResult, PdfComparisonResult } from "../types";
import type { DownloadArtifact } from "../downloadUtils";

type ToolStatus = "idle" | "file_selected" | "processing" | "success" | "error";
type ComparisonSelection = {
  filename: string;
  size: number;
  mimeType: string;
  previewUrl: string;
  error: string;
};
const MAX_TOOL_FILE_SIZE_BYTES = 25 * 1024 * 1024;

type Props = {
  active: "reset" | "converter" | "compare" | "compress";
  loading: boolean;
  csrfReady: boolean;
  conversion: { value: string; from: string; to: string; standard: "decimal" | "binary" };
  conversionResult: string;
  conversionStatus: ToolStatus;
  conversionDownload: DownloadArtifact | null;
  comparisonStatus: ToolStatus;
  comparisonDownloads: DownloadArtifact[];
  compressionStatus: ToolStatus;
  compressionResult: {
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
  } | null;
  comparisonResult: string;
  imageComparison: ImageComparisonResult | null;
  pdfComparison: PdfComparisonResult | null;
  canCancelComparison: boolean;
  canCancelCompression: boolean;
  resetForm: { email: string; otp: string; password: string };
  resetRequested: boolean;
  onConversion: (event: FormEvent<HTMLFormElement>) => void;
  onComparison: (event: FormEvent<HTMLFormElement>) => void;
  onCompression: (event: FormEvent<HTMLFormElement>) => void;
  onComparisonInputChange?: () => void;
  onCompressionInputChange?: () => void;
  onCancelComparison: () => void;
  onCancelCompression: () => void;
  onResetRequest: (event: FormEvent<HTMLFormElement>) => void;
  onResetConfirm: (event: FormEvent<HTMLFormElement>) => void;
  onConversionChange: (
    field: "value" | "from" | "to" | "standard",
    value: string,
  ) => void;
  onResetChange: (field: "email" | "otp" | "password", value: string) => void;
};

const units = ["bit", "byte", "kb", "mb", "gb", "tb"];

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ["KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = -1;
  do {
    value /= 1024;
    unitIndex += 1;
  } while (value >= 1024 && unitIndex < units.length - 1);
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatCompressionChange(inputBytes: number, outputBytes: number) {
  const difference = inputBytes - outputBytes;
  const percentage = inputBytes > 0
    ? ((Math.abs(difference) / inputBytes) * 100).toFixed(1)
    : "0.0";
  if (difference > 0) {
    return `Space saved: ${difference.toLocaleString()} bytes (${percentage}%).`;
  }
  if (difference < 0) {
    return `Size increased by ${Math.abs(difference).toLocaleString()} bytes (${percentage}%); no space was saved.`;
  }
  return "No space saved: 0 bytes (0.0%).";
}

function UnitSelect({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  return <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
    {units.map((unit) => <option value={unit} key={unit}>{unit === "bit" ? "Bit" : unit === "byte" ? "Byte" : unit.toUpperCase()}</option>)}
  </select>;
}

export default function ToolPanels(props: Props) {
  const [compressionFile, setCompressionFile] = useState<File | null>(null);
  const [compressionKind, setCompressionKind] = useState<"image" | "pdf" | "unknown">("unknown");
  const [compressionFormat, setCompressionFormat] = useState("");
  const [compressionPreview, setCompressionPreview] = useState("");
  const [compressionSelectionError, setCompressionSelectionError] = useState("");
  const [targetSize, setTargetSize] = useState("100");
  const [targetUnit, setTargetUnit] = useState<"KB" | "MB">("KB");
  const [gifWithoutTarget, setGifWithoutTarget] = useState(false);
  const [detectingCompressionFile, setDetectingCompressionFile] = useState(false);
  const compressionSelectionRun = useRef(0);
  const [comparisonSelections, setComparisonSelections] = useState<
    [ComparisonSelection | null, ComparisonSelection | null]
  >([null, null]);
  const comparisonSelectionRuns = useRef([0, 0]);
  const comparisonPreviewUrls = useRef<[string, string]>(["", ""]);

  useEffect(() => {
    if (compressionPreview) return () => URL.revokeObjectURL(compressionPreview);
  }, [compressionPreview]);

  useEffect(() => () => {
    comparisonPreviewUrls.current.forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
  }, []);

  async function selectComparisonFile(index: 0 | 1, event: ChangeEvent<HTMLInputElement>) {
    const run = ++comparisonSelectionRuns.current[index];
    const file = event.currentTarget.files?.[0] ?? null;
    props.onComparisonInputChange?.();
    if (!file) {
      const previousUrl = comparisonPreviewUrls.current[index];
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      comparisonPreviewUrls.current[index] = "";
      setComparisonSelections((current) => {
        const next = [...current] as typeof current;
        next[index] = null;
        return next;
      });
      return;
    }

    let selection: ComparisonSelection;
    if (file.size > MAX_TOOL_FILE_SIZE_BYTES) {
      selection = {
        filename: file.name,
        size: file.size,
        mimeType: "",
        previewUrl: "",
        error: "Each comparison file must be 25 MB or smaller.",
      };
    } else {
      try {
        const bytes = new Uint8Array(await file.slice(0, 12).arrayBuffer());
        if (run !== comparisonSelectionRuns.current[index]) return;
        const starts = (prefix: number[]) =>
          prefix.every((byte, position) => bytes[position] === byte);
        const type = starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
          ? "image/png"
          : bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
            ? "image/jpeg"
            : starts([0x47, 0x49, 0x46, 0x38]) &&
              (bytes[4] === 0x37 || bytes[4] === 0x39) &&
              bytes[5] === 0x61
              ? "image/gif"
              : String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
                String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
                ? "image/webp"
                : String.fromCharCode(...bytes.slice(0, 5)) === "%PDF-"
                  ? "application/pdf"
                  : "";
        selection = {
          filename: file.name,
          size: file.size,
          mimeType: type,
          previewUrl: "",
          error: type ? "" : "This file is not a supported PNG, JPEG, GIF, WEBP, or PDF.",
        };
      } catch {
        selection = {
          filename: file.name,
          size: file.size,
          mimeType: "",
          previewUrl: "",
          error: "The selected file could not be read. Choose it again.",
        };
      }
    }
    if (run !== comparisonSelectionRuns.current[index]) return;
    if (selection.mimeType.startsWith("image/")) {
      selection.previewUrl = URL.createObjectURL(file);
    }
    const previousUrl = comparisonPreviewUrls.current[index];
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    comparisonPreviewUrls.current[index] = selection.previewUrl;
    setComparisonSelections((current) => {
      const next = [...current] as typeof current;
      next[index] = selection;
      return next;
    });
  }

  async function selectCompressionFile(event: ChangeEvent<HTMLInputElement>) {
    const run = ++compressionSelectionRun.current;
    const file = event.currentTarget.files?.[0] ?? null;
    setCompressionFile(file);
    setCompressionKind("unknown");
    setCompressionFormat("");
    setCompressionPreview("");
    setCompressionSelectionError("");
    setGifWithoutTarget(false);
    setDetectingCompressionFile(Boolean(file));
    props.onCompressionInputChange?.();
    if (!file) return;
    if (file.size > MAX_TOOL_FILE_SIZE_BYTES) {
      setDetectingCompressionFile(false);
      setCompressionSelectionError("Choose a file that is 25 MB or smaller.");
      return;
    }
    let bytes: Uint8Array;
    try {
      bytes = new Uint8Array(await file.slice(0, 12).arrayBuffer());
    } catch {
      if (run === compressionSelectionRun.current) {
        setDetectingCompressionFile(false);
        setCompressionSelectionError("The selected file could not be read. Choose it again.");
      }
      return;
    }
    if (run !== compressionSelectionRun.current) return;
    const starts = (signature: number[]) =>
      signature.every((byte, index) => bytes[index] === byte);
    const isWebp = bytes.length >= 12 &&
      String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
    const isImage = starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]) ||
      starts([0xff, 0xd8, 0xff]) ||
      starts([0x47, 0x49, 0x46, 0x38, 0x37, 0x61]) ||
      starts([0x47, 0x49, 0x46, 0x38, 0x39, 0x61]) ||
      isWebp;
    if (isImage) {
      setCompressionKind("image");
      setCompressionFormat(starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
        ? "PNG"
        : starts([0xff, 0xd8, 0xff])
          ? "JPEG"
          : starts([0x47, 0x49, 0x46, 0x38, 0x37, 0x61]) ||
            starts([0x47, 0x49, 0x46, 0x38, 0x39, 0x61])
            ? "GIF"
            : "WEBP");
      setCompressionPreview(URL.createObjectURL(file));
    } else if (String.fromCharCode(...bytes.slice(0, 5)) === "%PDF-") {
      setCompressionKind("pdf");
    }
    setDetectingCompressionFile(false);
  }

  function invalidateCompressionResult(update?: () => void) {
    update?.();
    props.onCompressionInputChange?.();
  }

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
      <p className="helper-text">
        Convert bit, byte, KB, MB, GB, or TB. Enter a value, choose the source and result units,
        then select decimal (base 1,000) or binary (base 1,024). Zero is allowed; negative and
        non-numeric values are rejected.
      </p>
      <label htmlFor="conversion-value">Value</label>
      <input id="conversion-value" type="number" min="0" step="any" value={props.conversion.value}
        onChange={(event) => props.onConversionChange("value", event.target.value)} required />
      <label htmlFor="conversion-from">From</label>
      <UnitSelect id="conversion-from" value={props.conversion.from} onChange={(value) => props.onConversionChange("from", value)} />
      <label htmlFor="conversion-to">To</label>
      <UnitSelect id="conversion-to" value={props.conversion.to} onChange={(value) => props.onConversionChange("to", value)} />
      <fieldset className="analyzer-options conversion-standards">
        <legend>Conversion standard</legend>
        <label>
          <input type="radio" name="conversion-standard" checked={props.conversion.standard === "decimal"}
            onChange={() => props.onConversionChange("standard", "decimal")} />
          Decimal (1 KB = 1,000 bytes)
        </label>
        <label>
          <input type="radio" name="conversion-standard" checked={props.conversion.standard === "binary"}
            onChange={() => props.onConversionChange("standard", "binary")} />
          Binary (1 KB = 1,024 bytes)
        </label>
      </fieldset>
      <button type="submit" disabled={props.loading || !props.csrfReady}>{props.loading ? "Converting..." : "Convert"}</button>
      {props.conversionStatus === "processing" && <p className="result-panel" role="status">Converting...</p>}
      {props.conversionResult && <p className="result-panel" role={props.conversionStatus === "error" ? "alert" : "status"}>{props.conversionResult}</p>}
      {props.conversionStatus === "success" && props.conversionDownload &&
        <a href={props.conversionDownload.url} download={props.conversionDownload.filename}>
          Download conversion report
        </a>}
  </form>;
  if (props.active === "compress") return <form onSubmit={props.onCompression}>
      <p className="helper-text">
        Upload a PNG, JPEG, GIF, WEBP, or PDF (maximum 25 MB). For still images, choose an output
        target in KB or MB, quality, output format, and optional maximum dimensions. The result
        shows actual size and savings, then provides the verified output download. PDF settings
        preserve page count; image-only target and quality controls do not apply. Animated PNG and
        WEBP are not supported.
      </p>
      <label htmlFor="compression-file">Upload a file</label>
      <input id="compression-file" name="file" type="file"
        accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required
        onChange={(event) => void selectCompressionFile(event)} />
      {compressionSelectionError && <p className="result-panel" role="alert">{compressionSelectionError}</p>}
      {compressionPreview && <div className="compression-preview">
        <p>Image preview: {compressionFile?.name}</p>
        <img src={compressionPreview} alt="Selected image preview" />
        {compressionFile && <p>Original size: {formatBytes(compressionFile.size)}</p>}
      </div>}
      {compressionKind === "image" && compressionFormat === "GIF" && <label className="compression-aspect-option">
        <input type="checkbox" checked={gifWithoutTarget}
          onChange={(event) => invalidateCompressionResult(() => setGifWithoutTarget(event.target.checked))} />
        Compress GIF without target-size controls (preserves animation)
      </label>}
      {compressionKind === "image" && gifWithoutTarget &&
        <p className="helper-text">
          The GIF will be re-encoded with its animation preserved. A custom target or resizing
          cannot be applied to animated GIFs; the output size will be reported honestly.
        </p>}
      {compressionKind === "image" && !gifWithoutTarget && <>
        <fieldset className="compression-options" disabled={props.loading}>
          <legend>Image compression settings</legend>
          <label htmlFor="compression-target">Desired output size</label>
          <div className="compression-target">
            <input id="compression-target" name="target_size" type="number" min="0.001"
              step="any" value={targetSize}
              onChange={(event) => invalidateCompressionResult(() => setTargetSize(event.target.value))}
              required />
            <select id="compression-target-unit" name="target_unit" value={targetUnit}
              onChange={(event) => invalidateCompressionResult(() => setTargetUnit(event.target.value as "KB" | "MB"))}>
              <option value="KB">KB</option>
              <option value="MB">MB</option>
            </select>
          </div>
          <div className="compression-presets" aria-label="Quick target sizes">
            {[
              ["50", "KB"], ["100", "KB"], ["200", "KB"], ["500", "KB"],
              ["1", "MB"], ["2", "MB"],
            ].map(([size, unit]) => <button key={`${size}-${unit}`} type="button"
              className="secondary-button"
              onClick={() => invalidateCompressionResult(() => {
                setTargetSize(size);
                setTargetUnit(unit as "KB" | "MB");
              })}>
              {size} {unit}
            </button>)}
          </div>
          <label htmlFor="compression-format">Output format</label>
          <select id="compression-format" name="output_format" defaultValue="original"
            onChange={() => props.onCompressionInputChange?.()}>
            <option value="original">Keep original format</option>
            <option value="jpeg">JPEG</option>
            <option value="png">PNG</option>
            <option value="webp">WEBP</option>
            {compressionFormat === "GIF" && <option value="gif">GIF</option>}
          </select>
          <label htmlFor="compression-quality">JPEG output quality</label>
          <input id="compression-quality" name="quality" type="range" min="20" max="100"
            defaultValue="85" onChange={() => props.onCompressionInputChange?.()} />
          <label htmlFor="compression-width">Maximum width in pixels (optional)</label>
          <input id="compression-width" name="width" type="number" min="1" max="8192"
            onChange={() => props.onCompressionInputChange?.()} />
          <label htmlFor="compression-height">Maximum height in pixels (optional)</label>
          <input id="compression-height" name="height" type="number" min="1" max="8192"
            onChange={() => props.onCompressionInputChange?.()} />
          <input type="hidden" name="maintain_aspect_ratio" value="false" />
          <label className="compression-aspect-option">
            <input type="checkbox" name="maintain_aspect_ratio" value="true" defaultChecked
              onChange={() => props.onCompressionInputChange?.()} />
            Maintain aspect ratio
          </label>
          <p className="helper-text">
            JPEG quality is adjustable. PNG and WEBP use lossless encoding. Transparency is
            preserved for PNG and WEBP; JPEG uses a white background.
          </p>
        </fieldset>
      </>}
      {compressionKind === "pdf" && <p className="helper-text">
        PDF optimization preserves the page count. Image-only target and quality settings do not apply.
      </p>}
      {props.compressionStatus === "processing" && <p className="result-panel" role="status">
        Processing your file in the isolated worker...
      </p>}
      <button type="submit" disabled={props.loading || !props.csrfReady || !compressionFile ||
        detectingCompressionFile || Boolean(compressionSelectionError)}>
        {props.loading ? "Compressing..." : "Compress file"}
      </button>
      {props.canCancelCompression && <button type="button" onClick={props.onCancelCompression}>
        Cancel compression
      </button>}
      {props.compressionResult && <div className="result-panel" role={props.compressionStatus === "error" ? "alert" : "status"}>
        <p>{props.compressionResult.message}</p>
        {props.compressionResult.inputBytes !== undefined &&
          props.compressionResult.outputBytes !== undefined &&
          <p>
            Original: {formatBytes(props.compressionResult.inputBytes)} ({props.compressionResult.inputBytes.toLocaleString()} bytes)
            {" "}· Compressed: {formatBytes(props.compressionResult.outputBytes)} ({props.compressionResult.outputBytes.toLocaleString()} bytes)
          </p>}
        {props.compressionResult.inputBytes !== undefined &&
          props.compressionResult.outputBytes !== undefined &&
          <p>
            {formatCompressionChange(
              props.compressionResult.inputBytes,
              props.compressionResult.outputBytes,
            )}
          </p>}
        {props.compressionResult.targetBytes != null &&
          <p>
            Requested target: {formatBytes(props.compressionResult.targetBytes)} ·
            {" "}{props.compressionResult.targetReached
              ? "Target reached."
              : "Target could not be reached; this is the closest valid output."}
          </p>}
        {props.compressionResult.width && props.compressionResult.height &&
          <p>Output dimensions: {props.compressionResult.width} × {props.compressionResult.height} px</p>}
        {props.compressionResult.quality != null &&
          <p>JPEG quality used: {props.compressionResult.quality}%</p>}
        {props.compressionStatus === "success" && props.compressionResult.contentType?.startsWith("image/") &&
          props.compressionResult.downloadUrl && <div className="compression-preview">
            <p>Compressed image preview</p>
            <img src={props.compressionResult.downloadUrl} alt="Compressed image preview" />
          </div>}
        {props.compressionStatus === "success" &&
          props.compressionResult.downloadUrl && props.compressionResult.filename &&
          <a href={props.compressionResult.downloadUrl} download={props.compressionResult.filename}>
            {props.compressionResult.contentType === "application/pdf"
              ? "Download compressed PDF"
              : "Download compressed image"}
          </a>}
      </div>}
  </form>;
  return <form onSubmit={props.onComparison}>
      <p className="helper-text">
        Compare two PNG, JPEG, GIF, WEBP, or PDF files (maximum 25 MB each). Choose one file in
        each field, then compare: images are checked pixel by pixel and PDFs by page text and
        rendered appearance. The results include previews and a downloadable report; generated
        image or page-difference overlays can also be downloaded.
      </p>
      <label htmlFor="first-file">First file</label>
      <input id="first-file" name="first" type="file" accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required
        onChange={(event) => void selectComparisonFile(0, event)} />
      {comparisonSelections[0] && <ComparisonFilePreview selection={comparisonSelections[0]} />}
      <label htmlFor="second-file">Second file</label>
      <input id="second-file" name="second" type="file" accept="image/png,image/jpeg,image/gif,image/webp,application/pdf" required
        onChange={(event) => void selectComparisonFile(1, event)} />
      {comparisonSelections[1] && <ComparisonFilePreview selection={comparisonSelections[1]} />}
      <button type="submit" disabled={props.loading || !props.csrfReady ||
        !comparisonSelections[0]?.mimeType || !comparisonSelections[1]?.mimeType}>
        {props.loading ? "Comparing..." : "Compare files"}
      </button>
      {props.canCancelComparison && <button type="button" onClick={props.onCancelComparison}>Cancel comparison</button>}
      {props.comparisonResult && <p className="result-panel" role={props.comparisonStatus === "error" ? "alert" : "status"}>{props.comparisonResult}</p>}
      {props.comparisonStatus === "success" && props.comparisonDownloads.length > 0 &&
        <section className="tool-downloads" aria-label="Comparison downloads">
          {props.comparisonDownloads.map((download) =>
            <a key={download.filename} href={download.url} download={download.filename}>
              Download {download.filename}
            </a>)}
        </section>}
      {props.comparisonStatus === "success" && props.imageComparison && <section className="image-results" aria-label="Image comparison details">
        <p>
          First: {props.imageComparison.first_format} {props.imageComparison.first.dimensions.join(" x ")}.
          {" "}Second: {props.imageComparison.second_format} {props.imageComparison.second.dimensions.join(" x ")}.
        </p>
        <p>
          {props.imageComparison.same_visual
            ? "No pixel-level visual differences found."
            : `${props.imageComparison.visual_differences} frame(s) have visual differences.`}
        </p>
        {props.imageComparison.frame_results.map((frame) => <article className="image-frame-result" key={frame.frame}>
          <strong>Frame {frame.frame}</strong>
          {frame.status !== "compared" && <span>Frame {frame.status} in the second image.</span>}
          {frame.visual && <>
            <span>
              {frame.visual.same_dimensions
                ? `${frame.visual.differing_pixels ?? 0} differing pixels · ${frame.visual.difference_percentage}%`
                : "Frame dimensions differ; all pixels are treated as different."}
            </span>
            {frame.visual.overlay_png &&
              <img src={frame.visual.overlay_png} alt={`Difference overlay for frame ${frame.frame}`} />}
          </>}
        </article>)}
      </section>}
      {props.comparisonStatus === "success" && props.pdfComparison && <section className="pdf-results" aria-label="PDF comparison details">
        <p>
          First PDF: {props.pdfComparison.first.page_count} pages;
          {" "}{props.pdfComparison.first.has_text_layer ? "text layer detected" : "no text layer detected"}.
          {" "}Second PDF: {props.pdfComparison.second.page_count} pages;
          {" "}{props.pdfComparison.second.has_text_layer ? "text layer detected" : "no text layer detected"}.
          {" "}Text differences: {props.pdfComparison.text_differences};
          {" "}visual differences: {props.pdfComparison.visual_differences}.
        </p>
        {props.pdfComparison.page_results.map((page) => <article className="pdf-page-result" key={page.page}>
          <strong>Page {page.page}</strong>
          <span>{page.status ?? (page.text_same ? "Text identical" : "Text differs")}</span>
          {page.visual && <span>Visual difference: {page.visual.difference_percentage}%</span>}
          {page.visual?.overlay_png && <img src={page.visual.overlay_png} alt={`Difference overlay for page ${page.page}`} />}
        </article>)}
      </section>}
  </form>;
}

function ComparisonFilePreview({ selection }: { selection: ComparisonSelection }) {
  if (selection.error) {
    return <p className="result-panel" role="alert">{selection.error}</p>;
  }
  return <div className="compression-preview">
    <p>{selection.filename} · {selection.mimeType} · {formatBytes(selection.size)}</p>
    {selection.previewUrl && <img src={selection.previewUrl} alt={`Preview of ${selection.filename}`} />}
  </div>;
}
