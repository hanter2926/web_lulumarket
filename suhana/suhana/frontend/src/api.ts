import type { ApiResponse } from "./types";

export async function readJson(response: Response): Promise<ApiResponse> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return {};
  }
  try {
    return (await response.json()) as ApiResponse;
  } catch {
    return {};
  }
}

export async function getCsrfToken(): Promise<string> {
  const response = await fetch("/api/accounts/csrf/", { credentials: "include" });
  const data = await readJson(response);
  if (!response.ok || !data.csrfToken) {
    throw new Error(data.message ?? "Unable to initialize secure registration.");
  }
  return data.csrfToken;
}

export async function postJson(
  url: string,
  payload: Record<string, string>,
  csrfToken: string,
): Promise<{ response: Response; data: ApiResponse }> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await readJson(response);
  return { response, data };
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to connect to server.";
}
