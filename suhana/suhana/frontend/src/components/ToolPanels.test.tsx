import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ToolPanels from "./ToolPanels";

const props = {
  active: "compare" as const,
  loading: false,
  csrfReady: true,
  conversion: { value: "1", from: "gb", to: "mb" },
  conversionResult: "",
  comparisonResult: "",
  pdfComparison: null,
  resetForm: { email: "", otp: "", password: "" },
  resetRequested: false,
  onConversion: vi.fn(),
  onComparison: vi.fn(),
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
});
