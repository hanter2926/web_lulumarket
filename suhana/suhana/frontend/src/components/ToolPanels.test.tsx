import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ToolPanels from "./ToolPanels";

const props = {
  active: "compare" as const,
  loading: false,
  csrfReady: true,
  conversion: { value: "1", from: "gb", to: "mb" },
  conversionResult: "",
  conversionStatus: "idle" as const,
  conversionDownload: null,
  comparisonStatus: "idle" as const,
  comparisonDownloads: [],
  compressionStatus: "idle" as const,
  compressionResult: null,
  comparisonResult: "",
  imageComparison: null,
  pdfComparison: null,
  canCancelComparison: false,
  canCancelCompression: false,
  resetForm: { email: "", otp: "", password: "" },
  resetRequested: false,
  onConversion: vi.fn(),
  onComparison: vi.fn(),
  onCompression: vi.fn(),
  onCancelComparison: vi.fn(),
  onCancelCompression: vi.fn(),
  onResetRequest: vi.fn(),
  onResetConfirm: vi.fn(),
  onConversionChange: vi.fn(),
  onResetChange: vi.fn(),
};

describe("ToolPanels", () => {
  it("requires and exposes both comparison uploads", () => {
    render(<ToolPanels {...props} />);

    expect(screen.getByLabelText("First file")).toHaveAttribute("accept", expect.stringContaining("application/pdf"));
    expect(screen.getByLabelText("Second file")).toBeRequired();
    fireEvent.submit(screen.getByRole("button", { name: "Compare files" }).closest("form")!);
    expect(props.onComparison).toHaveBeenCalled();
  });

  it("renders PDF page visual results and overlays", () => {
    render(
      <ToolPanels
        {...props}
        comparisonStatus="success"
        comparisonDownloads={[
          { url: "blob:report", filename: "comparison-report.csv" },
          { url: "blob:page-difference", filename: "pdf-page-1-difference.png" },
        ]}
        pdfComparison={{
          first: { page_count: 1, has_text_layer: true, scanned_likely: false },
          second: { page_count: 1, has_text_layer: true, scanned_likely: false },
          text_differences: 1,
          visual_differences: 1,
          page_results: [{
            page: 1,
            text_same: false,
            visual: { difference_percentage: 12.5, differing_pixels: 1, overlay_png: "data:image/png;base64,test" },
          }],
        }}
      />,
    );

    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByAltText("Difference overlay for page 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download pdf-page-1-difference.png" })).toBeInTheDocument();
  });

  it("renders pixel-level image differences and an overlay preview", () => {
    render(
      <ToolPanels
        {...props}
        comparisonStatus="success"
        comparisonDownloads={[
          { url: "blob:report", filename: "comparison-report.csv" },
          { url: "blob:frame-difference", filename: "image-frame-1-difference.png" },
        ]}
        imageComparison={{
          first: {
            dimensions: [2, 2],
            format: "PNG",
            animated: false,
            frame_count: 1,
            has_alpha: true,
          },
          second: {
            dimensions: [2, 2],
            format: "PNG",
            animated: false,
            frame_count: 1,
            has_alpha: true,
          },
          first_format: "PNG",
          second_format: "PNG",
          animated: false,
          frame_count_difference: 0,
          frame_results: [{
            frame: 1,
            status: "compared",
            visual: {
              same_dimensions: true,
              differing_pixels: 2,
              difference_percentage: 50,
              overlay_png: "data:image/png;base64,test",
            },
          }],
          visual_differences: 1,
          same_visual: false,
        }}
      />,
    );

    expect(screen.getByText("2 differing pixels · 50%")).toBeInTheDocument();
    expect(screen.getByAltText("Difference overlay for frame 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download image-frame-1-difference.png" })).toBeInTheDocument();
  });

  it("allows cancellation while a comparison is running", () => {
    render(<ToolPanels {...props} loading canCancelComparison />);

    fireEvent.click(screen.getByRole("button", { name: "Cancel comparison" }));

    expect(props.onCancelComparison).toHaveBeenCalled();
  });

  it("shows a real downloadable compression result", () => {
    render(
      <ToolPanels
        {...props}
        active="compress"
        compressionResult={{
          message: "Compression complete. Reduced by 25.0%.",
          inputBytes: 400,
          outputBytes: 300,
          downloadUrl: "blob:compressed-output",
          filename: "image_compressed.png",
          contentType: "image/png",
        }}
        compressionStatus="success"
      />,
    );

    expect(screen.getByLabelText("Upload a file")).toHaveAttribute("accept", expect.stringContaining("application/pdf"));
    expect(screen.getByRole("link", { name: "Download compressed image" })).toHaveAttribute(
      "download",
      "image_compressed.png",
    );
    expect(screen.getByText(
      "Original: 400 bytes (400 bytes) · Compressed: 300 bytes (300 bytes)",
    )).toBeInTheDocument();
    expect(screen.getByText("Space saved: 100 bytes (25.0%).")).toBeInTheDocument();
  });

  it("reports honestly when compression increases the file size", () => {
    render(
      <ToolPanels
        {...props}
        active="compress"
        compressionResult={{
          message: "Compression complete. Output is 25.0% larger than the input.",
          inputBytes: 400,
          outputBytes: 500,
          downloadUrl: "blob:compressed-output",
          filename: "image_compressed.png",
        }}
        compressionStatus="success"
      />,
    );

    expect(screen.getByText(
      "Size increased by 100 bytes (25.0%); no space was saved.",
    )).toBeInTheDocument();
  });

  it("does not expose compression output downloads before verified success", () => {
    render(
      <ToolPanels
        {...props}
        active="compress"
        compressionStatus="processing"
        compressionResult={{
          message: "Compressing...",
          downloadUrl: "blob:stale-output",
          filename: "old.png",
        }}
      />,
    );

    expect(screen.queryByRole("link", { name: "Download compressed image" })).not.toBeInTheDocument();
  });

  it("offers custom target presets and settings for verified image input", async () => {
    const onCompressionInputChange = vi.fn();
    render(
      <ToolPanels
        {...props}
        active="compress"
        onCompressionInputChange={onCompressionInputChange}
      />,
    );
    const png = new File([
      new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    ], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Upload a file"), { target: { files: [png] } });

    expect(await screen.findByLabelText("Desired output size")).toBeInTheDocument();
    expect(screen.getByLabelText("JPEG output quality")).toBeInTheDocument();
    expect(screen.getByLabelText("Maximum width in pixels (optional)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "1 MB" }));
    expect(screen.getByLabelText("Desired output size")).toHaveValue(1);
    expect(screen.getByDisplayValue("MB")).toBeInTheDocument();
    expect(onCompressionInputChange).toHaveBeenCalled();
  });

  it("labels PDF compression downloads separately", () => {
    render(
      <ToolPanels
        {...props}
        active="compress"
        compressionStatus="success"
        compressionResult={{
          message: "Compression complete.",
          downloadUrl: "blob:compressed-pdf",
          filename: "report_compressed.pdf",
          contentType: "application/pdf",
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "Download compressed PDF" })).toHaveAttribute(
      "download",
      "report_compressed.pdf",
    );
  });

  it("only exposes conversion downloads after successful conversion", () => {
    const { rerender } = render(<ToolPanels {...props} active="converter" />);
    expect(screen.queryByRole("link", { name: "Download conversion report" })).not.toBeInTheDocument();

    rerender(
      <ToolPanels
        {...props}
        active="converter"
        conversionStatus="success"
        conversionResult="1000 MB"
        conversionDownload={{ url: "blob:conversion", filename: "unit-conversion.csv" }}
      />,
    );
    expect(screen.getByRole("link", { name: "Download conversion report" })).toHaveAttribute(
      "download",
      "unit-conversion.csv",
    );
  });

  it("hides stale comparison downloads during processing and on failure", () => {
    const downloads = [{ url: "blob:report", filename: "comparison-report.csv" }];
    const { rerender } = render(
      <ToolPanels {...props} comparisonStatus="processing" comparisonDownloads={downloads} />,
    );
    expect(screen.queryByRole("link", { name: "Download comparison-report.csv" })).not.toBeInTheDocument();

    rerender(
      <ToolPanels
        {...props}
        comparisonStatus="error"
        comparisonResult="Comparison failed."
        comparisonDownloads={downloads}
      />,
    );
    expect(screen.queryByRole("link", { name: "Download comparison-report.csv" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Comparison failed.");
  });
});
