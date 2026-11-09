import type { FormEvent } from "react";
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
};

export default function StoragePanel(props: Props) {
  return <div className="workspace-panel">
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
            <button type="button" className="danger-button" onClick={() => props.onDeleteFile(file.id)}>Delete</button>
          </span>
        </li>)}</ul>
      </div>
    </div>
  </div>;
}
