import type { ApiResponse } from "./types";

export async function getCsrfToken(): Promise<string> {
  const response = await fetch("/api/accounts/csrf/", { credentials: "include" });
  const data = (await response.json()) as ApiResponse;
  if (!response.ok || !data.csrfToken) {
    throw new Error("Unable to initialize secure registration.");
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
  const data = (await response.json()) as ApiResponse;
  return { response, data };
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to connect to server.";
}
