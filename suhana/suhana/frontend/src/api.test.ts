import { beforeEach, describe, expect, it, vi } from "vitest";
import { getCsrfToken, postJson, responseErrorMessage } from "./api";

describe("API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a CSRF token from a JSON response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ csrfToken: "token" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(getCsrfToken()).resolves.toBe("token");
  });

  it("handles non-JSON server errors without throwing while parsing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>error</html>", {
        status: 500,
        headers: { "Content-Type": "text/html" },
      }),
    );

    await expect(postJson("/api/test/", {}, "token")).resolves.toMatchObject({
      response: { status: 500 },
      data: {},
    });
  });

  it("reports HTTP status when an error response is not JSON instead of hiding it", () => {
    const response = new Response("<html>error</html>", { status: 500 });

    expect(responseErrorMessage(response, {}, "Comparison request"))
      .toBe("Comparison request failed (HTTP 500).");
    expect(responseErrorMessage(
      new Response(JSON.stringify({ message: "Invalid image." }), { status: 400 }),
      { message: "Invalid image." },
      "Comparison request",
    )).toBe("Invalid image.");
  });
});
