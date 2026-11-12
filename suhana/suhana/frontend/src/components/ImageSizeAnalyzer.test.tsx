import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ImageSizeAnalyzer from "./ImageSizeAnalyzer";

const pngSignature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

describe("ImageSizeAnalyzer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports actual bytes, decimal units, dimensions and detected format without uploading", async () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:local-image"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({
      width: 3,
      height: 2,
      close: vi.fn(),
    }));
    const file = new File([new Uint8Array([...pngSignature, 1, 2, 3])], "sample.png", {
      type: "image/jpeg",
    });
    render(<ImageSizeAnalyzer />);

    fireEvent.change(screen.getByLabelText("Image file"), { target: { files: [file] } });

    expect(await screen.findByText("11 Bytes")).toBeInTheDocument();
    expect(screen.getByText("0.011 KB")).toBeInTheDocument();
    expect(screen.getByText("0.000011 MB")).toBeInTheDocument();
    expect(screen.getByText("3 × 2 px")).toBeInTheDocument();
    expect(screen.getByText("PNG")).toBeInTheDocument();
    expect(screen.getByText("image/png")).toBeInTheDocument();
    expect(screen.getByText(/image\/jpeg/)).toHaveTextContent("content signature used");
    expect(createImageBitmap).toHaveBeenCalledWith(file);
    expect(screen.getByRole("link", { name: "Download analysis report (CSV)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download original image" })).toHaveAttribute(
      "download",
      "sample.png",
    );
  });

  it("reports invalid content and lets the user remove the selected image", async () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:local-image"),
      revokeObjectURL: vi.fn(),
    });
    const inputFile = new File(["not an image"], "invalid.png", { type: "image/png" });
    render(<ImageSizeAnalyzer />);

    fireEvent.change(screen.getByLabelText("Image file"), { target: { files: [inputFile] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("not a valid, readable");

    fireEvent.click(screen.getByRole("button", { name: "Remove selected image" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Remove selected image" })).not.toBeInTheDocument();
  });

  it("rejects images larger than the documented limit before decoding", async () => {
    const decode = vi.fn();
    vi.stubGlobal("createImageBitmap", decode);
    const file = new File([new Uint8Array(25 * 1024 * 1024 + 1)], "oversize.png", {
      type: "image/png",
    });
    render(<ImageSizeAnalyzer />);

    fireEvent.change(screen.getByLabelText("Image file"), { target: { files: [file] } });

    expect(await screen.findByRole("alert")).toHaveTextContent("25 MB or smaller");
    expect(decode).not.toHaveBeenCalled();
  });

  it("updates displayed values and the report immediately when display settings change", async () => {
    const reports: Blob[] = [];
    let urlId = 0;
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn((blob: Blob) => {
        reports.push(blob);
        urlId += 1;
        return `blob:local-${urlId}`;
      }),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({
      width: 4,
      height: 2,
      close: vi.fn(),
    }));
    const file = new File([new Uint8Array([...pngSignature, ...new Array(101).fill(0)])], "sample.png");
    render(<ImageSizeAnalyzer />);

    fireEvent.change(screen.getByLabelText("Image file"), { target: { files: [file] } });
    expect(await screen.findByRole("link", { name: "Download original image" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Binary (1024)"));

    expect(await screen.findByText("0.106445 KB")).toBeInTheDocument();
    expect(await reports[reports.length - 1].text()).toContain('"Original size (KB)","0.106445 KB"');

    fireEvent.click(screen.getByRole("button", { name: "Reset Options" }));
    expect(await screen.findByText("0.109 KB")).toBeInTheDocument();
    expect(screen.getByText("2:1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download analysis report (CSV)" })).toBeInTheDocument();
    expect(await reports[reports.length - 1].text()).toContain('"Original size (KB)","0.109 KB"');
  });
});
