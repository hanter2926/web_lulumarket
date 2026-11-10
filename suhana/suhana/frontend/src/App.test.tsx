import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

describe("registration submission", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("does not submit duplicate registration requests while one is in flight", async () => {
    vi.stubEnv("DEV", false);
    const csrfResponse = {
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ csrfToken: "csrf-token" }),
    };
    const pendingRegistration = new Promise<Response>(() => {});
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(csrfResponse)
      .mockReturnValueOnce(pendingRegistration);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const submit = await screen.findByRole("button", { name: "Create account" });
    await waitFor(() => expect(submit).toBeEnabled());

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "new-user" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "StrongPassword123!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "StrongPassword123!" },
    });

    const form = screen.getByLabelText("Username").closest("form");
    fireEvent.submit(form!);
    fireEvent.submit(form!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/accounts/register/");
  });
});
