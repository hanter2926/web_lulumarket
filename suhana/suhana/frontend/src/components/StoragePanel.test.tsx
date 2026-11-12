import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoragePanel from "./StoragePanel";

describe("StoragePanel", () => {
  it("offers download, rename, and folder move actions for each file", () => {
    const onRenameFile = vi.fn();
    const onMoveFile = vi.fn();
    render(
      <StoragePanel
        csrfReady
        loading={false}
        selectedFolderId={null}
        folders={[
          { id: 2, name: "Reports", parent_id: null },
          { id: 3, name: "2026", parent_id: 2 },
        ]}
        files={[{
          id: 7,
          name: "notes.txt",
          size_bytes: 12,
          content_type: "text/plain",
          folder_id: null,
        }]}
        onSelectFolder={vi.fn()}
        onCreateFolder={vi.fn()}
        onRenameFolder={vi.fn()}
        onDeleteFolder={vi.fn()}
        onUpload={vi.fn()}
        onDeleteFile={vi.fn()}
        onRenameFile={onRenameFile}
        onMoveFile={onMoveFile}
      />,
    );

    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "/api/storage/files/7/download/",
    );
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(onRenameFile).toHaveBeenCalledWith(7, "notes.txt");

    fireEvent.change(screen.getByLabelText("Move notes.txt to folder"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(onMoveFile).toHaveBeenCalledWith(7, 3);
  });
});
