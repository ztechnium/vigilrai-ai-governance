import { describe, expect, it } from "vitest";
import { postLoginPath, welcomeDestination } from "@/lib/welcome-gate";

describe("welcome gate", () => {
  it("sends a new organization to the full-screen wizard", () => {
    expect(postLoginPath(false, false)).toBe("/welcome");
    expect(
      welcomeDestination({
        isPlatform: false,
        welcomeCompleted: false,
        pathname: "/dashboard",
      }),
    ).toBe("/welcome");
  });

  it("leaves a completed organization on the normal app shell", () => {
    expect(postLoginPath(false, true)).toBe("/app/onboarding");
    expect(
      welcomeDestination({
        isPlatform: false,
        welcomeCompleted: true,
        pathname: "/dashboard",
      }),
    ).toBeNull();
    expect(
      welcomeDestination({
        isPlatform: false,
        welcomeCompleted: true,
        pathname: "/welcome",
      }),
    ).toBe("/app/onboarding");
  });

  it("does not send platform operators through the wizard", () => {
    expect(postLoginPath(true, false)).toBe("/dashboard");
    expect(
      welcomeDestination({
        isPlatform: true,
        welcomeCompleted: false,
        pathname: "/dashboard",
      }),
    ).toBeNull();
  });
});
