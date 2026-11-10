export type DownloadArtifact = {
  url: string;
  filename: string;
};

export function createTextDownload(
  content: string,
  mimeType: string,
  filename: string,
): DownloadArtifact | null {
  const blob = new Blob([content], { type: mimeType });
  if (!blob.size) return null;
  return { url: URL.createObjectURL(blob), filename };
}

export async function createVerifiedPngDownload(
  dataUrl: string,
  filename: string,
): Promise<DownloadArtifact | null> {
  const match = /^data:image\/png;base64,([A-Za-z0-9+/]+={0,2})$/.exec(dataUrl);
  if (!match) return null;

  try {
    const binary = atob(match[1]);
    if (!binary) return null;
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const blob = new Blob([bytes], { type: "image/png" });
    const bitmap = await createImageBitmap(blob);
    const valid = bitmap.width > 0 && bitmap.height > 0;
    bitmap.close();
    return valid ? { url: URL.createObjectURL(blob), filename } : null;
  } catch {
    return null;
  }
}

export async function verifyImageBlob(blob: Blob): Promise<boolean> {
  try {
    const bitmap = await createImageBitmap(blob);
    const valid = bitmap.width > 0 && bitmap.height > 0;
    bitmap.close();
    return valid;
  } catch {
    return false;
  }
}

export function verifyPdfHeader(bytes: Uint8Array): boolean {
  return bytes.length >= 5 &&
    bytes[0] === 0x25 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x44 &&
    bytes[3] === 0x46 &&
    bytes[4] === 0x2d;
}

export function revokeDownloads(downloads: DownloadArtifact[]) {
  downloads.forEach(({ url }) => URL.revokeObjectURL(url));
}
