import { useEffect, useRef, useState } from "react";
import { createTextDownload, type DownloadArtifact } from "../downloadUtils";

type ImageDetails = {
  format: string;
  mimeType: string;
  width: number;
  height: number;
};

type AnalyzerOptions = {
  units: Array<"Bytes" | "KB" | "MB" | "GB">;
  standard: "decimal" | "binary";
  originalSize: boolean;
  dimensions: boolean;
  aspectRatio: boolean;
  format: boolean;
  mimeType: boolean;
};

type AnalyzerStatus = "idle" | "processing" | "success" | "error";
const MAX_IMAGE_SIZE_BYTES = 25 * 1024 * 1024;

const initialOptions: AnalyzerOptions = {
  units: ["Bytes", "KB", "MB"],
  standard: "decimal",
  originalSize: true,
  dimensions: true,
  aspectRatio: true,
  format: true,
  mimeType: true,
};

const signatures: Array<{ bytes: number[]; format: string; mimeType: string }> = [
  { bytes: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], format: "PNG", mimeType: "image/png" },
  { bytes: [0xff, 0xd8, 0xff], format: "JPEG", mimeType: "image/jpeg" },
  { bytes: [0x47, 0x49, 0x46, 0x38, 0x37, 0x61], format: "GIF", mimeType: "image/gif" },
  { bytes: [0x47, 0x49, 0x46, 0x38, 0x39, 0x61], format: "GIF", mimeType: "image/gif" },
];

function detectedImageType(bytes: Uint8Array) {
  const signature = signatures.find(({ bytes: prefix }) =>
    prefix.every((byte, index) => bytes[index] === byte),
  );
  if (signature) return signature;
  if (
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  ) {
    return { format: "WEBP", mimeType: "image/webp" };
  }
  return null;
}

function formatSize(bytes: number, unit: AnalyzerOptions["units"][number], standard: AnalyzerOptions["standard"]) {
  const divisor = standard === "decimal" ? 1_000 : 1_024;
  const power = { Bytes: 0, KB: 1, MB: 2, GB: 3 }[unit];
  return `${(bytes / divisor ** power).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${unit}`;
}

function greatestCommonDivisor(first: number, second: number): number {
  return second === 0 ? first : greatestCommonDivisor(second, first % second);
}

function analyzerRows(file: File, details: ImageDetails, options: AnalyzerOptions) {
  const rows: Array<[string, string]> = [];
  if (options.originalSize) {
    options.units.forEach((unit) => rows.push([
      `Original size (${unit})`,
      formatSize(file.size, unit, options.standard),
    ]));
  }
  if (options.dimensions) rows.push(["Dimensions", `${details.width} × ${details.height} px`]);
  if (options.aspectRatio) {
    const divisor = greatestCommonDivisor(details.width, details.height);
    rows.push(["Aspect ratio", `${details.width / divisor}:${details.height / divisor}`]);
  }
  if (options.format) rows.push(["Detected format", details.format]);
  if (options.mimeType) rows.push(["MIME type", details.mimeType]);
  return rows;
}

export default function ImageSizeAnalyzer() {
  const [file, setFile] = useState<File | null>(null);
  const [details, setDetails] = useState<ImageDetails | null>(null);
  const [status, setStatus] = useState<AnalyzerStatus>("idle");
  const [error, setError] = useState("");
  const [options, setOptions] = useState(initialOptions);
  const [reportDownload, setReportDownload] = useState<DownloadArtifact | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const analysisRun = useRef(0);

  useEffect(() => {
    if (reportDownload) return () => URL.revokeObjectURL(reportDownload.url);
  }, [reportDownload]);

  useEffect(() => {
    if (previewUrl) return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  async function selectFile(selectedFile: File | null) {
    const run = ++analysisRun.current;
    setFile(selectedFile);
    setDetails(null);
    setError("");
    setReportDownload(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!selectedFile) {
      setPreviewUrl("");
      setStatus("idle");
      return;
    }
    if (selectedFile.size > MAX_IMAGE_SIZE_BYTES) {
      setPreviewUrl("");
      setError("Choose an image that is 25 MB or smaller.");
      setStatus("error");
      return;
    }

    setPreviewUrl(URL.createObjectURL(selectedFile));
    setStatus("processing");
    try {
      const header = new Uint8Array(await selectedFile.slice(0, 12).arrayBuffer());
      const type = detectedImageType(header);
      if (!type) {
        throw new Error("The file content is not a supported PNG, JPEG, GIF, or WEBP image.");
      }
      const bitmap = await createImageBitmap(selectedFile);
      const decoded = {
        format: type.format,
        mimeType: type.mimeType,
        width: bitmap.width,
        height: bitmap.height,
      };
      bitmap.close();
      if (run !== analysisRun.current) return;
      setDetails(decoded);
      setStatus("success");
      const report = createReport(selectedFile, decoded, options);
      setReportDownload(report);
    } catch {
      if (run === analysisRun.current) {
        setError("The selected file is not a valid, readable PNG, JPEG, GIF, or WEBP image.");
        setStatus("error");
      }
    }
  }

  function createReport(imageFile: File, imageDetails: ImageDetails, selectedOptions: AnalyzerOptions) {
    const dataRows = analyzerRows(imageFile, imageDetails, selectedOptions);
    if (!dataRows.length) return null;
    const rows = [["Property", "Value"], ...dataRows];
    const csv = rows.map((row) =>
      row.map((value) => `"${value.replaceAll('"', '""')}"`).join(","),
    ).join("\r\n");
    return createTextDownload(
      `${csv}\r\n`,
      "text/csv;charset=utf-8",
      "image-analysis.csv",
    );
  }

  function updateOptions(nextOptions: AnalyzerOptions) {
    setOptions(nextOptions);
    if (file && details) {
      setReportDownload(createReport(file, details, nextOptions));
      setError("");
      setStatus("success");
    }
  }

  function resetOptions() {
    updateOptions(initialOptions);
  }

  function toggleUnit(unit: AnalyzerOptions["units"][number], checked: boolean) {
    const units = checked
      ? [...options.units, unit]
      : options.units.filter((selected) => selected !== unit);
    updateOptions({ ...options, units });
  }

  const displayRows = file && details ? analyzerRows(file, details, options) : [];

  return (
    <section className="image-analyzer" aria-labelledby="image-analyzer-title">
      <div>
        <h2 id="image-analyzer-title">Image Size Analyzer</h2>
        <p className="helper-text">
          Inspect PNG, JPEG, GIF, or WEBP images up to 25 MB. Choose an image to see its preview,
          exact byte count, dimensions, aspect ratio, detected format, and MIME type. Then adjust
          the display options; the results and optional CSV report update immediately. Image data
          stays in your browser. Decimal uses 1,000 and binary uses 1,024 bytes per KB.
        </p>
      </div>
      <label htmlFor="analyzer-image">Image file</label>
      <input
        id="analyzer-image"
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        onChange={(event) => void selectFile(event.currentTarget.files?.[0] ?? null)}
      />
      {file && (
        <button type="button" className="secondary-button analyzer-clear" onClick={() => {
          void selectFile(null);
          if (inputRef.current) inputRef.current.value = "";
        }}>
          Remove selected image
        </button>
      )}

      <fieldset className="analyzer-options" disabled={status === "processing"}>
        <legend>Display options</legend>
        <div className="analyzer-option-group">
          <strong>Display units</strong>
          {(["Bytes", "KB", "MB", "GB"] as const).map((unit) =>
            <label key={unit}>
              <input type="checkbox" checked={options.units.includes(unit)}
                onChange={(event) => toggleUnit(unit, event.currentTarget.checked)} />
              {unit}
            </label>)}
        </div>
        <div className="analyzer-option-group">
          <strong>Conversion standard</strong>
          {(["decimal", "binary"] as const).map((standard) =>
            <label key={standard}>
              <input type="radio" name="analyzer-standard" checked={options.standard === standard}
                onChange={() => updateOptions({ ...options, standard })} />
              {standard === "decimal" ? "Decimal (1000)" : "Binary (1024)"}
            </label>)}
        </div>
        <div className="analyzer-option-group">
          <strong>Information to display</strong>
          {([
            ["originalSize", "Original file size"],
            ["dimensions", "Width and height"],
            ["aspectRatio", "Aspect ratio"],
            ["format", "Detected image format"],
            ["mimeType", "MIME type"],
          ] as const).map(([field, label]) =>
            <label key={field}>
              <input type="checkbox" checked={options[field]}
                onChange={(event) => updateOptions({ ...options, [field]: event.currentTarget.checked })} />
              {label}
            </label>)}
          <label className="analyzer-option-disabled">
            <input type="checkbox" disabled />
            Estimated compressed size (no reliable estimate available)
          </label>
        </div>
        <div className="analyzer-option-actions">
          <button type="button" className="secondary-button" onClick={resetOptions}>Reset Options</button>
        </div>
      </fieldset>

      {status === "processing" && <p className="result-panel" role="status">Validating image...</p>}
      {error && <p className="result-panel" role="alert">{error}</p>}
      {status === "success" && file && details && (
        <>
          {!displayRows.length &&
            <p className="helper-text">Select at least one information option to create an analysis report.</p>}
          <div className="analyzer-result">
            <img src={previewUrl} alt={`Preview of ${file.name}`} />
            <dl>
              <div><dt>File</dt><dd>{file.name}</dd></div>
              {displayRows.map(([label, value]) =>
                <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
              {file.type && file.type !== details.mimeType &&
                <div><dt>Browser-reported MIME</dt><dd>{file.type} (content signature used)</dd></div>}
            </dl>
          </div>
          <div className="tool-downloads" aria-label="Image analyzer downloads">
            {reportDownload &&
              <a href={reportDownload.url} download={reportDownload.filename}>Download analysis report (CSV)</a>}
            <a href={previewUrl} download={file.name}>Download original image</a>
          </div>
        </>
      )}
    </section>
  );
}
