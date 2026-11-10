import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ToolPanels from "./ToolPanels";

const props = {
  active: "compare" as const,
  loading: false,
  csrfReady: true,
  conversion: { value: "1", from: "gb", to: "mb" },
  conversionResult: "",
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
  });

  it("renders pixel-level image differences and an overlay preview", () => {
    render(
      <ToolPanels
        {...props}
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
        }}
      />,
    );

    expect(screen.getByLabelText("File")).toHaveAttribute("accept", expect.stringContaining("application/pdf"));
    expect(screen.getByRole("link", { name: "Download image_compressed.png" })).toHaveAttribute(
      "download",
      "image_compressed.png",
    );
    expect(screen.getByText(
      "Original: 400 bytes (400 bytes) · Compressed: 300 bytes (300 bytes)",
    )).toBeInTheDocument();
  });
});
