import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createTextDownload,
  createVerifiedPngDownload,
  verifyImageBlob,
  verifyPdfHeader,
} from "./downloadUtils";

describe("download utilities", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a downloadable report only for non-empty content", () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:report"),
    });

    expect(createTextDownload("", "text/csv", "report.csv")).toBeNull();
    expect(createTextDownload("name,value\r\nresult,42", "text/csv", "report.csv")).toEqual({
      url: "blob:report",
      filename: "report.csv",
    });
  });

  it("exposes a difference image only after PNG decoding succeeds", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({
      width: 2,
      height: 2,
      close,
    }));
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:difference"),
    });
    const png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAFElEQVR4nGPkE1NgAAMmCMXAwAAABPIASPzuJswAAAAASUVORK5CYII=";

    await expect(createVerifiedPngDownload(png, "difference.png")).resolves.toEqual({
      url: "blob:difference",
      filename: "difference.png",
    });
    await expect(createVerifiedPngDownload("data:image/png;base64,invalid***", "bad.png"))
      .resolves.toBeNull();
    expect(close).toHaveBeenCalledOnce();
  });

  it("validates decoded images and PDF signatures", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({
      width: 1,
      height: 1,
      close: vi.fn(),
    }));

    expect(await verifyImageBlob(new Blob(["image"]))).toBe(true);
    expect(verifyPdfHeader(new TextEncoder().encode("%PDF-1.7"))).toBe(true);
    expect(verifyPdfHeader(new TextEncoder().encode("not pdf"))).toBe(false);
  });
});
