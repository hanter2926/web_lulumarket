import type { FolderItem } from "../types";

type Props = {
  folders: FolderItem[];
  selectedFolderId: number | null;
  onSelect: (id: number | null) => void;
  onRename: (id: number, name: string) => void;
  onDelete: (id: number) => void;
};

function FolderNode({
  folder,
  folders,
  selectedFolderId,
  onSelect,
  onRename,
  onDelete,
}: Props & { folder: FolderItem }) {
  const children = folders.filter((item) => item.parent_id === folder.id);
  return (
    <div className="folder-node">
      <div className="folder-row">
        <button type="button" className={selectedFolderId === folder.id ? "folder-selected" : ""}
          onClick={() => onSelect(folder.id)}>📁 {folder.name}</button>
        <button type="button" className="folder-action" onClick={() => onRename(folder.id, folder.name)}
          aria-label={`Rename ${folder.name}`}>Rename</button>
        <button type="button" className="folder-action danger-button" onClick={() => onDelete(folder.id)}
          aria-label={`Delete ${folder.name}`}>Delete</button>
      </div>
      {children.map((child) => (
        <div className="folder-child" key={child.id}>
          <FolderNode folder={child} folders={folders} selectedFolderId={selectedFolderId}
            onSelect={onSelect} onRename={onRename} onDelete={onDelete} />
        </div>
      ))}
    </div>
  );
}

export default function FolderTree(props: Props) {
  return (
    <nav className="folder-tree" aria-label="Folder tree">
      <button type="button" className={props.selectedFolderId === null ? "folder-selected" : ""}
        onClick={() => props.onSelect(null)}>Root</button>
      {props.folders.filter((folder) => folder.parent_id === null).map((folder) => (
        <FolderNode key={folder.id} folder={folder} {...props} />
      ))}
    </nav>
  );
}
