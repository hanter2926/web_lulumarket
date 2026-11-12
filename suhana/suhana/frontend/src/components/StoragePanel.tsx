import { useState, type FormEvent } from "react";
import FolderTree from "./FolderTree";
import type { FileItem, FolderItem } from "../types";

type Props = {
  csrfReady: boolean;
  loading: boolean;
  selectedFolderId: number | null;
  folders: FolderItem[];
  files: FileItem[];
  onSelectFolder: (id: number | null) => void;
  onCreateFolder: () => void;
  onRenameFolder: (id: number, name: string) => void;
  onDeleteFolder: (id: number) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
  onDeleteFile: (id: number) => void;
  onRenameFile: (id: number, name: string) => void;
  onMoveFile: (id: number, folderId: number | null) => void;
};

export default function StoragePanel(props: Props) {
  const [moveTargets, setMoveTargets] = useState<Record<number, string>>({});

  return <div className="workspace-panel">
    <p className="helper-text">
      Store private files up to 25 MB each, organize them in nested folders, rename or move them,
      and download or delete them. Your account quota is shown on the Dashboard.
    </p>
    <div className="storage-toolbar">
      <button type="button" onClick={props.onCreateFolder} disabled={!props.csrfReady}>New folder</button>
      <span>{props.selectedFolderId === null ? "Root folder" : `Folder #${props.selectedFolderId}`}</span>
      {props.selectedFolderId !== null && <button type="button" className="secondary-button"
        onClick={() => props.onSelectFolder(null)}>Back to root</button>}
    </div>
    <div className="folder-layout">
      <FolderTree folders={props.folders} selectedFolderId={props.selectedFolderId}
        onSelect={props.onSelectFolder} onRename={props.onRenameFolder} onDelete={props.onDeleteFolder} />
      <div>
        <form onSubmit={props.onUpload}>
          <label htmlFor="stored-file">Upload a file</label>
          <input id="stored-file" name="file" type="file" required />
          {props.selectedFolderId !== null && <input type="hidden" name="folder" value={props.selectedFolderId} />}
          <button type="submit" disabled={props.loading || !props.csrfReady}>{props.loading ? "Uploading..." : "Upload"}</button>
        </form>
        <ul className="file-list">{props.files.map((file) => <li key={file.id}>
          <span>{file.name} <small>{file.size_bytes} bytes</small></span>
          <span>
            <a href={`/api/storage/files/${file.id}/download/`} target="_blank" rel="noreferrer">Download</a>
            <button type="button" className="folder-action"
              onClick={() => props.onRenameFile(file.id, file.name)} disabled={props.loading}>
              Rename
            </button>
            <label className="file-move-label" htmlFor={`move-file-${file.id}`}>Move to</label>
            <select id={`move-file-${file.id}`}
              aria-label={`Move ${file.name} to folder`}
              value={moveTargets[file.id] ?? String(file.folder_id ?? "")}
              onChange={(event) => setMoveTargets((current) => ({
                ...current,
                [file.id]: event.target.value,
              }))}
              disabled={props.loading}>
              <option value="">Root</option>
              {props.folders.map((folder) =>
                <option key={folder.id} value={folder.id}>
                  {folder.name} (#{folder.id})
                </option>)}
            </select>
            <button type="button" className="folder-action"
              onClick={() => props.onMoveFile(file.id, moveTargets[file.id] ? Number(moveTargets[file.id]) : null)}
              disabled={props.loading ||
                (moveTargets[file.id] ?? String(file.folder_id ?? "")) === String(file.folder_id ?? "")}>
              Move
            </button>
            <button type="button" className="danger-button" onClick={() => props.onDeleteFile(file.id)}
              disabled={props.loading}>Delete</button>
          </span>
        </li>)}</ul>
      </div>
    </div>
  </div>;
}
