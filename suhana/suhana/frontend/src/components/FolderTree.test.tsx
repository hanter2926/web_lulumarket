import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FolderTree from "./FolderTree";

describe("FolderTree", () => {
  it("renders nested folders and reports selection", () => {
    const onSelect = vi.fn();
    render(
      <FolderTree
        folders={[
          { id: 1, name: "Reports", parent_id: null },
          { id: 2, name: "2026", parent_id: 1 },
        ]}
        selectedFolderId={null}
        onSelect={onSelect}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "📁 2026" }));
    fireEvent.click(screen.getByRole("button", { name: "Root" }));
    expect(onSelect).toHaveBeenNthCalledWith(1, 2);
    expect(onSelect).toHaveBeenNthCalledWith(2, null);
  });
});
