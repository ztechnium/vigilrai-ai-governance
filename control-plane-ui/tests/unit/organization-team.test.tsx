import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OrganizationTeamPage from "@/app/(app)/organization/team/page";

const {
  orgState,
  authState,
  listOrganizationTeam,
  listOrganizationDepartments,
  inviteOrganizationTeammate,
  getUsers,
  getRoles,
  getRbacContext,
} = vi.hoisted(() => ({
  orgState: {
    isLoading: false,
    activeOrganization: {
      id: "org-a",
      org_key: "acme",
      name: "Acme",
      status: "ACTIVE",
      roles: ["ORGANIZATION_ADMIN"],
    } as {
      id: string;
      org_key: string;
      name: string;
      status: string;
      roles: string[];
    } | null,
  },
  listOrganizationTeam: vi.fn(),
  listOrganizationDepartments: vi.fn(),
  inviteOrganizationTeammate: vi.fn(),
  getUsers: vi.fn(),
  getRoles: vi.fn(),
  getRbacContext: vi.fn(),
  authState: { isPlatformAdmin: false },
}));

vi.mock("@/lib/api", () => ({
  ACTIVE_ORG_STORAGE_KEY: "rai.cp.activeOrganizationId",
  listOrganizationTeam: (...args: unknown[]) => listOrganizationTeam(...args),
  listOrganizationDepartments: (...args: unknown[]) => listOrganizationDepartments(...args),
  inviteOrganizationTeammate: (...args: unknown[]) => inviteOrganizationTeammate(...args),
  getUsers: (...args: unknown[]) => getUsers(...args),
  getRoles: (...args: unknown[]) => getRoles(...args),
  getRbacContext: (...args: unknown[]) => getRbacContext(...args),
}));

vi.mock("@/lib/hooks/use-auth", () => ({
  useOrganization: () => ({
    activeOrganization: orgState.activeOrganization,
    setActiveOrganization: vi.fn(),
    isLoading: orgState.isLoading,
  }),
  useAuth: () => ({ isPlatformAdmin: authState.isPlatformAdmin }),
}));

describe("Organization team page", () => {
  beforeEach(() => {
    orgState.isLoading = false;
    orgState.activeOrganization = {
      id: "org-a",
      org_key: "acme",
      name: "Acme",
      status: "ACTIVE",
      roles: ["ORGANIZATION_ADMIN"],
    };
    listOrganizationTeam.mockReset();
    listOrganizationDepartments.mockReset();
    inviteOrganizationTeammate.mockReset();
    authState.isPlatformAdmin = false;
    listOrganizationDepartments.mockResolvedValue({
      data: {
        organization_id: "org-a",
        items: [
          {
            id: "dept-marketing",
            organization_id: "org-a",
            name: "Marketing",
            description: "Brand, campaigns, and communications.",
            sort_order: 0,
          },
        ],
      },
    });
    window.localStorage.clear();
    window.localStorage.setItem("rai.cp.activeOrganizationId", "org-foreign");
  });

  it("lists teammates for the instance", async () => {
    listOrganizationTeam.mockResolvedValue({
      data: {
        items: [
          {
            id: "m-1",
            user_id: "user-jane",
            user_name: "Jane Doe",
            user_email: "jane@acme.com",
            role: "ORGANIZATION_ADMIN",
            status: "ACTIVE",
            valid_from: null,
            valid_until: null,
            created_by: "user-jane",
            created_at: null,
            department_id: "dept-marketing",
            department_name: "Marketing",
          },
          {
            id: "m-2",
            user_id: "user-bob",
            user_name: "Bob Other",
            user_email: "bob@other.com",
            role: "RAI_OFFICER",
            status: "ACTIVE",
            valid_from: null,
            valid_until: null,
            created_by: "user-bob",
            created_at: null,
          },
        ],
      },
    });

    render(<OrganizationTeamPage />);

    expect((await screen.findAllByText("Jane Doe")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bob Other").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Team records outside this organization were withheld."),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send invite" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Department" })).toBeInTheDocument();
    expect(screen.getByTestId("organization-hierarchy")).toHaveTextContent("Marketing");
    expect(screen.getByRole("button", { name: "Edit Organization admin" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" }).length).toBeGreaterThan(0);
    expect(window.localStorage.getItem("rai.cp.activeOrganizationId")).toBe("org-a");
    expect(listOrganizationTeam).toHaveBeenCalled();
  });

  it("hides invites for members who are not organization admins", async () => {
    orgState.activeOrganization = {
      id: "org-a",
      org_key: "acme",
      name: "Acme",
      status: "ACTIVE",
      roles: ["RAI_OFFICER"],
    };
    listOrganizationTeam.mockResolvedValue({ data: { organization_id: "org-a", items: [] } });

    render(<OrganizationTeamPage />);

    await waitFor(() => {
      expect(screen.getByText(/An organization admin sends invites/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Send invite" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });

  it("does not load a team when the user has no organization membership", async () => {
    orgState.activeOrganization = null;

    render(<OrganizationTeamPage />);

    expect(await screen.findByText("Organization membership required")).toBeInTheDocument();
    expect(listOrganizationTeam).not.toHaveBeenCalled();
  });

  it("shows the access tab for a platform admin", async () => {
    authState.isPlatformAdmin = true;
    listOrganizationTeam.mockResolvedValue({ data: { items: [] } });
    listOrganizationDepartments.mockResolvedValue({ data: { items: [] } });
    getUsers.mockResolvedValue({
      data: [
        {
          user_id: "user-1",
          name: "Ada Admin",
          email: "ada@example.com",
          status: "active",
          roles: ["admin"],
        },
      ],
    });
    getRoles.mockResolvedValue({
      data: [{ role_id: "admin", name: "Admin", permissions: ["users:read"] }],
    });
    getRbacContext.mockResolvedValue({
      data: { selected_role: "admin", permissions: ["users:read"], available_roles: [] },
    });

    render(<OrganizationTeamPage />);

    expect(screen.getByRole("tab", { name: "Access" })).toBeInTheDocument();
    screen.getByRole("tab", { name: "Access" }).click();
    expect(await screen.findByText("Platform users")).toBeInTheDocument();
    expect(await screen.findByText("Ada Admin")).toBeInTheDocument();
  });
});
