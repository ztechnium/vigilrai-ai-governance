import { describe, expect, it } from "vitest";
import { hasPlatformAdminAccess, tenantHasNavRole } from "@/lib/platform-roles";

describe("platform role helpers", () => {
  it("treats legacy bootstrap admin as platform admin", () => {
    expect(hasPlatformAdminAccess(["admin"])).toBe(true);
    expect(hasPlatformAdminAccess(["platform_admin"])).toBe(true);
    expect(hasPlatformAdminAccess(["platform_support"])).toBe(false);
    expect(hasPlatformAdminAccess([])).toBe(false);
  });

  it("maps RAI Officer / General Admin to tenant enums for AI Systems nav", () => {
    expect(tenantHasNavRole("RAI Officer", ["RAI_OFFICER"])).toBe(true);
    expect(tenantHasNavRole("RAI Officer", ["ORGANIZATION_ADMIN"])).toBe(true);
    expect(tenantHasNavRole("General Admin", ["ORGANIZATION_ADMIN"])).toBe(true);
    expect(tenantHasNavRole("RAI Officer", ["AUDITOR"])).toBe(false);
    expect(tenantHasNavRole("General Admin", [])).toBe(false);
  });

  it("does not default-allow Business Approver without a tenant enum", () => {
    expect(tenantHasNavRole("Business Approver", [])).toBe(false);
    expect(tenantHasNavRole("Business Approver", ["BUSINESS_APPROVER"])).toBe(true);
  });

  it("shows AI Systems nav roles for org admin membership from /auth/me", () => {
    const membershipRoles = ["ORGANIZATION_ADMIN"];
    expect(
      ["RAI Officer", "General Admin"].some((role) => tenantHasNavRole(role, membershipRoles)),
    ).toBe(true);
  });
});
