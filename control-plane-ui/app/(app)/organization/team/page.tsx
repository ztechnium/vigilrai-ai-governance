"use client";

import { useEffect, useMemo, useState } from "react";
import { FilterToolbar, MetricStrip } from "@/components/console/page-parts";
import { KpiCard } from "@/components/kpi-card";
import { FormField } from "@/components/registry/form-field";
import { Panel } from "@/components/registry/panel";
import { SectionHeader } from "@/components/section-header";
import { StatusBadge } from "@/components/registry/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  ACTIVE_ORG_STORAGE_KEY,
  deleteOrganizationMembership,
  inviteOrganizationTeammate,
  listOrganizationDepartments,
  listOrganizationTeam,
  removeOrganizationPerson,
  updateOrganizationMembership,
  assignUserRoles,
  createRole,
  createUser,
  deleteUser,
  getRbacContext,
  getRoles,
  getUsers,
  updateRolePermissions,
} from "@/lib/api";
import { useOrganization, useAuth } from "@/lib/hooks/use-auth";
import { Tabs } from "@/components/ui/tabs";
import type {
  Department,
  OrganizationMembership,
  RbacContext,
  RoleSummary,
  UserSummary,
} from "@/lib/types";

const OPEN_ORG_STATUSES = new Set(["ACTIVE", "PROVISIONING"]);

const TEAM_ROLES = [
  { value: "RAI_OFFICER", label: "RAI officer" },
  { value: "ORGANIZATION_ADMIN", label: "Organization admin" },
  { value: "BUSINESS_OWNER", label: "Business owner" },
  { value: "TECHNICAL_OWNER", label: "Technical owner" },
  { value: "AI_SYSTEM_OWNER", label: "AI system owner" },
  { value: "RISK_COMPLIANCE_REVIEWER", label: "Risk and compliance" },
  { value: "INCIDENT_MANAGER", label: "Incident manager" },
  { value: "BUSINESS_APPROVER", label: "Business approver" },
  { value: "AUDITOR", label: "Auditor" },
] as const;

const ROLE_LABELS = Object.fromEntries(TEAM_ROLES.map((role) => [role.value, role.label]));

const MEMBERSHIP_STATUSES = ["ACTIVE", "INVITED", "SUSPENDED", "REVOKED"] as const;

type Person = {
  userId: string;
  name: string;
  email: string;
  roles: OrganizationMembership[];
};

type IssuedCredential = {
  email: string;
  password: string;
};

function roleLabel(role: string) {
  return ROLE_LABELS[role] ?? role.replace(/_/g, " ").toLowerCase();
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  const letters = parts.map((part) => part[0]?.toUpperCase() ?? "").join("");
  return letters || "?";
}

function groupPeople(memberships: OrganizationMembership[]): Person[] {
  const people = new Map<string, Person>();
  for (const membership of memberships) {
    const current = people.get(membership.user_id);
    if (current) {
      current.roles.push(membership);
      if (!current.email && membership.user_email) current.email = membership.user_email;
      if (current.name === membership.user_id && membership.user_name) {
        current.name = membership.user_name;
      }
      continue;
    }
    people.set(membership.user_id, {
      userId: membership.user_id,
      name: membership.user_name?.trim() || membership.user_id,
      email: membership.user_email?.trim() || "",
      roles: [membership],
    });
  }
  return Array.from(people.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function personDepartment(person: Person) {
  const match = person.roles.find((membership) => membership.department_id);
  return {
    id: match?.department_id ?? null,
    name: match?.department_name?.trim() || null,
  };
}

function OrganizationHierarchy({
  organizationName,
  departments,
  people,
}: {
  organizationName: string;
  departments: Department[];
  people: Person[];
}) {
  const assigned = new Set<string>();
  const groups = departments.map((department) => {
    const members = people.filter((person) => personDepartment(person).id === department.id);
    for (const person of members) assigned.add(person.userId);
    return { department, members };
  });
  const unassigned = people.filter((person) => !assigned.has(person.userId));

  return (
    <div data-testid="organization-hierarchy" className="text-sm">
      <p className="font-semibold text-ink-900">{organizationName}</p>
      <ul className="mt-3 space-y-3 border-l border-base-200 pl-4">
        {groups.map(({ department, members }) => (
          <li key={department.id}>
            <p className="font-medium text-ink-900">{department.name}</p>
            {department.description ? (
              <p className="text-xs text-ink-500">{department.description}</p>
            ) : null}
            <ul className="mt-2 space-y-1 border-l border-base-200 pl-4">
              {members.length === 0 ? (
                <li className="text-xs text-ink-400">No team members</li>
              ) : (
                members.map((person) => (
                  <li key={person.userId} className="text-ink-700">
                    {person.name}
                    {person.email ? <span className="text-ink-400"> · {person.email}</span> : null}
                  </li>
                ))
              )}
            </ul>
          </li>
        ))}
        {unassigned.length > 0 ? (
          <li>
            <p className="font-medium text-ink-900">Unassigned</p>
            <ul className="mt-2 space-y-1 border-l border-base-200 pl-4">
              {unassigned.map((person) => (
                <li key={person.userId} className="text-ink-700">
                  {person.name}
                </li>
              ))}
            </ul>
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function toggleValue(values: string[], value: string) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function CheckGrid({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  if (options.length === 0) {
    return <p className="text-sm text-ink-500">No {label.toLowerCase()} are available yet.</p>;
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {options.map((option) => (
        <label
          key={option}
          className="flex items-center gap-2 rounded-md border border-base-200 px-3 py-2 text-sm text-ink-800"
        >
          <input
            type="checkbox"
            checked={selected.includes(option)}
            onChange={() => onChange(toggleValue(selected, option))}
          />
          <span className="truncate">{option}</span>
        </label>
      ))}
    </div>
  );
}

function AccessPanel() {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [rbac, setRbac] = useState<RbacContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [section, setSection] = useState<"people" | "roles">("people");
  const [newUser, setNewUser] = useState({
    user_id: "",
    name: "",
    email: "",
    roles: [] as string[],
  });
  const [newRole, setNewRole] = useState({ role_id: "", name: "", permissions: [] as string[] });
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [selectedRolePermissions, setSelectedRolePermissions] = useState<string[]>([]);

  const permissionOptions = useMemo(() => {
    const values = new Set<string>(rbac?.permissions ?? []);
    for (const role of roles) {
      for (const permission of role.permissions ?? []) values.add(permission);
    }
    return Array.from(values).sort();
  }, [rbac, roles]);
  const roleOptions = useMemo(() => roles.map((role) => role.role_id), [roles]);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [usersRes, rolesRes, rbacRes] = await Promise.all([
        getUsers(),
        getRoles(),
        getRbacContext(),
      ]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
      setRbac(rbacRes.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users and roles");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreateUser = async () => {
    setError("");
    setMessage("");
    try {
      await createUser({
        user_id: newUser.user_id.trim(),
        name: newUser.name.trim(),
        email: newUser.email.trim(),
        roles: newUser.roles,
      });
      setMessage("User created.");
      setNewUser({ user_id: "", name: "", email: "", roles: [] });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    }
  };

  const handleAssignRoles = async () => {
    if (!selectedUserId) {
      setError("Select a user first.");
      return;
    }
    setError("");
    setMessage("");
    try {
      await assignUserRoles(selectedUserId, selectedUserRoles);
      setMessage("User roles updated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign roles");
    }
  };

  const handleDeleteUser = async (userId: string, userName: string) => {
    if (
      !window.confirm(
        `Delete user "${userName}" (${userId})? This removes their credentials, roles, and memberships.`,
      )
    ) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await deleteUser(userId);
      if (selectedUserId === userId) {
        setSelectedUserId("");
        setSelectedUserRoles([]);
      }
      setMessage("User deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete user");
    }
  };

  const handleCreateRole = async () => {
    setError("");
    setMessage("");
    try {
      await createRole({
        role_id: newRole.role_id.trim(),
        name: newRole.name.trim(),
        permissions: newRole.permissions,
      });
      setMessage("Role created.");
      setNewRole({ role_id: "", name: "", permissions: [] });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create role");
    }
  };

  const handleUpdateRolePermissions = async () => {
    if (!selectedRoleId) {
      setError("Select a role first.");
      return;
    }
    setError("");
    setMessage("");
    try {
      await updateRolePermissions(selectedRoleId, selectedRolePermissions);
      setMessage("Role permissions updated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update role permissions");
    }
  };

  return (
    <div className="space-y-4">
      {rbac && (
        <Panel
          title="Current session"
          description={rbac.permissions.join(", ") || "No effective permissions."}
        >
          <p className="text-sm text-ink-600">
            Platform roles control the admin console. Membership roles control the product.
          </p>
        </Panel>
      )}
      {error && (
        <div className="rounded-lg border border-danger-500/30 bg-danger-100 px-4 py-3 text-sm text-danger-700">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-lg border border-accent-500/30 bg-accent-100 px-4 py-3 text-sm text-accent-700">
          {message}
        </div>
      )}
      <Tabs
        tabs={["People", "Roles"]}
        active={section === "roles" ? "Roles" : "People"}
        onChange={(value) => setSection(value === "Roles" ? "roles" : "people")}
      />
      {loading && <p className="text-sm text-ink-500">Loading users and roles…</p>}
      {!loading && section === "people" && (
        <>
          <Panel title="Add a user" description="Create a platform account and choose its roles.">
            <div className="grid gap-4 md:grid-cols-3">
              <FormField label="User id" required>
                <Input
                  value={newUser.user_id}
                  onChange={(event) =>
                    setNewUser((prev) => ({ ...prev, user_id: event.target.value }))
                  }
                />
              </FormField>
              <FormField label="Name" required>
                <Input
                  value={newUser.name}
                  onChange={(event) =>
                    setNewUser((prev) => ({ ...prev, name: event.target.value }))
                  }
                />
              </FormField>
              <FormField label="Email" required>
                <Input
                  type="email"
                  value={newUser.email}
                  onChange={(event) =>
                    setNewUser((prev) => ({ ...prev, email: event.target.value }))
                  }
                />
              </FormField>
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-400">Roles</p>
              <CheckGrid
                label="Roles"
                options={roleOptions}
                selected={newUser.roles}
                onChange={(roles) => setNewUser((prev) => ({ ...prev, roles }))}
              />
            </div>
            <div className="mt-4">
              <Button onClick={() => void handleCreateUser()}>Add user</Button>
            </div>
          </Panel>
          <Panel title="Platform users">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-base-200 text-left text-xs uppercase text-ink-400">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Email</th>
                    <th className="py-2 pr-4">Roles</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.user_id} className="border-b border-base-100">
                      <td className="py-3 pr-4">
                        <button
                          type="button"
                          className="font-medium text-accent-700 hover:underline"
                          onClick={() => {
                            setSelectedUserId(user.user_id);
                            setSelectedUserRoles(user.roles);
                          }}
                        >
                          {user.name}
                        </button>
                      </td>
                      <td className="py-3 pr-4 text-ink-600">{user.email}</td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((role) => (
                            <Badge key={role} variant="accent">
                              {role}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        <StatusBadge status={user.status} />
                      </td>
                      <td className="py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void handleDeleteUser(user.user_id, user.name)}
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="Update user roles"
            description={
              selectedUserId ? `Selected user: ${selectedUserId}` : "Select a user from the table."
            }
          >
            <CheckGrid
              label="Roles"
              options={roleOptions}
              selected={selectedUserRoles}
              onChange={setSelectedUserRoles}
            />
            <div className="mt-4">
              <Button onClick={() => void handleAssignRoles()}>Save roles</Button>
            </div>
          </Panel>
        </>
      )}
      {!loading && section === "roles" && (
        <>
          <Panel
            title="Add a role"
            description="Name the role and choose the permissions it grants."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <FormField label="Role id" required>
                <Input
                  value={newRole.role_id}
                  onChange={(event) =>
                    setNewRole((prev) => ({ ...prev, role_id: event.target.value }))
                  }
                />
              </FormField>
              <FormField label="Name" required>
                <Input
                  value={newRole.name}
                  onChange={(event) =>
                    setNewRole((prev) => ({ ...prev, name: event.target.value }))
                  }
                />
              </FormField>
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                Permissions
              </p>
              <CheckGrid
                label="Permissions"
                options={permissionOptions}
                selected={newRole.permissions}
                onChange={(permissions) => setNewRole((prev) => ({ ...prev, permissions }))}
              />
            </div>
            <div className="mt-4">
              <Button onClick={() => void handleCreateRole()}>Add role</Button>
            </div>
          </Panel>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {roles.map((role) => (
              <Panel
                key={role.role_id}
                title={role.name}
                description={role.description || role.role_id}
                actions={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedRoleId(role.role_id);
                      setSelectedRolePermissions(role.permissions ?? []);
                    }}
                  >
                    Edit
                  </Button>
                }
              >
                <div className="flex flex-wrap gap-1">
                  {(role.permissions ?? []).map((permission) => (
                    <Badge key={permission} variant="neutral">
                      {permission}
                    </Badge>
                  ))}
                </div>
              </Panel>
            ))}
          </div>
          <Panel
            title="Update role permissions"
            description={
              selectedRoleId ? `Selected role: ${selectedRoleId}` : "Choose a role to edit."
            }
          >
            <CheckGrid
              label="Permissions"
              options={permissionOptions}
              selected={selectedRolePermissions}
              onChange={setSelectedRolePermissions}
            />
            <div className="mt-4">
              <Button onClick={() => void handleUpdateRolePermissions()}>Save permissions</Button>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

export default function OrganizationTeamPage() {
  const { activeOrganization, isLoading: orgLoading } = useOrganization();
  const { isPlatformAdmin } = useAuth();
  const [tab, setTab] = useState<"team" | "access">("team");
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [credential, setCredential] = useState<IssuedCredential | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("RAI_OFFICER");
  const [departmentId, setDepartmentId] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState("RAI_OFFICER");
  const [editStatus, setEditStatus] = useState("ACTIVE");
  const [actingId, setActingId] = useState<string | null>(null);

  const orgId = activeOrganization?.id ?? "";
  const orgOpen = Boolean(activeOrganization && OPEN_ORG_STATUSES.has(activeOrganization.status));
  const canInvite = Boolean(orgOpen && activeOrganization?.roles.includes("ORGANIZATION_ADMIN"));

  useEffect(() => {
    if (orgLoading) return;
    if (!activeOrganization) {
      setMemberships([]);
      setDepartments([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, activeOrganization.id);
    Promise.all([listOrganizationTeam(), listOrganizationDepartments().catch(() => null)])
      .then(([res, departmentsRes]) => {
        if (cancelled) return;
        setError(null);
        setMemberships(res.data.items);
        setDepartments(departmentsRes?.data.items ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setMemberships([]);
        setDepartments([]);
        setError(err instanceof Error ? err.message : "Failed to load team members");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [orgLoading, activeOrganization]);

  const people = useMemo(() => groupPeople(memberships), [memberships]);
  const visiblePeople = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return people.filter((person) => {
      const matchesRole =
        !roleFilter || person.roles.some((membership) => membership.role === roleFilter);
      if (!matchesRole) return false;
      if (!needle) return true;
      return (
        person.name.toLowerCase().includes(needle) ||
        person.email.toLowerCase().includes(needle) ||
        person.roles.some((membership) => roleLabel(membership.role).includes(needle))
      );
    });
  }, [people, query, roleFilter]);

  const adminCount = people.filter((person) =>
    person.roles.some(
      (membership) => membership.role === "ORGANIZATION_ADMIN" && membership.status === "ACTIVE",
    ),
  ).length;
  const activeCount = memberships.filter((membership) => membership.status === "ACTIVE").length;

  const onInvite = async () => {
    if (!canInvite || !orgId || !email.trim() || !fullName.trim() || !departmentId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    setCredential(null);
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    const selectedDepartment = departments.find((department) => department.id === departmentId);
    try {
      const res = await inviteOrganizationTeammate({
        email: email.trim(),
        full_name: fullName.trim(),
        role,
        department_id: departmentId,
      });
      const parts = [
        res.data.user.created
          ? `Created an account for ${res.data.user.email}.`
          : `Added ${res.data.user.email} to ${activeOrganization?.name ?? "this organization"}.`,
        `Role: ${roleLabel(role)}.`,
        selectedDepartment ? `Department: ${selectedDepartment.name}.` : "",
      ].filter(Boolean);
      if (res.data.verification_email_sent) {
        parts.push("Verification email sent.");
      } else if (res.data.verification_email_error) {
        parts.push("Verification email is waiting on mail delivery.");
      }
      setMessage(parts.join(" "));
      if (res.data.temporary_password) {
        setCredential({ email: res.data.user.email, password: res.data.temporary_password });
      }
      setEmail("");
      setFullName("");
      const refreshed = await listOrganizationTeam();
      setMemberships(refreshed.data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to invite member");
    } finally {
      setBusy(false);
    }
  };

  const refreshTeam = async () => {
    if (!orgId) return;
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    const refreshed = await listOrganizationTeam();
    setMemberships(
      refreshed.data.items.filter((membership) => membership.organization_id === orgId),
    );
  };

  const onSaveMembership = async (membershipId: string) => {
    if (!canInvite) return;
    setActingId(membershipId);
    setError(null);
    setMessage(null);
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    try {
      const res = await updateOrganizationMembership(membershipId, {
        role: editRole,
        status: editStatus,
      });
      if (res.data.organization_id !== orgId) {
        setError("The update was not applied to the active organization.");
        return;
      }
      setMessage(`Updated ${roleLabel(res.data.role)} for this organization.`);
      setEditingId(null);
      await refreshTeam();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update member");
    } finally {
      setActingId(null);
    }
  };

  const onDeleteMembership = async (membership: OrganizationMembership, personName: string) => {
    if (!canInvite) return;
    const confirmed = window.confirm(
      `Remove the ${roleLabel(membership.role)} role from ${personName} in ${activeOrganization?.name ?? "this organization"}?`,
    );
    if (!confirmed) return;
    setActingId(membership.id);
    setError(null);
    setMessage(null);
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    try {
      const res = await deleteOrganizationMembership(membership.id);
      if (res.data.organization_id !== orgId) {
        setError("The role was not removed from the active organization.");
        return;
      }
      setMessage(`Removed ${roleLabel(membership.role)} from ${personName}.`);
      setEditingId(null);
      await refreshTeam();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove role");
    } finally {
      setActingId(null);
    }
  };

  const onRemovePerson = async (person: Person) => {
    if (!canInvite) return;
    const confirmed = window.confirm(
      `Remove ${person.name} from ${activeOrganization?.name ?? "this organization"}? Their account stays available to other organizations.`,
    );
    if (!confirmed) return;
    setActingId(person.userId);
    setError(null);
    setMessage(null);
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    try {
      const res = await removeOrganizationPerson(person.userId);
      if (res.data.organization_id !== orgId) {
        setError("The person was not removed from the active organization.");
        return;
      }
      setMessage(`Removed ${person.name} from ${activeOrganization?.name ?? "this organization"}.`);
      setEditingId(null);
      await refreshTeam();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member");
    } finally {
      setActingId(null);
    }
  };

  const copyPassword = async () => {
    if (!credential) return;
    try {
      await navigator.clipboard.writeText(credential.password);
      setMessage(`Temporary password copied for ${credential.email}.`);
    } catch {
      setError("Copy the temporary password from the credential card.");
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Organization"
        title="Team & roles"
        subtitle={
          activeOrganization
            ? `People, memberships, and platform access for ${activeOrganization.name}.`
            : "People, memberships, and platform access."
        }
        actions={
          activeOrganization ? (
            <Badge variant="accent">{activeOrganization.name}</Badge>
          ) : (
            <Badge variant="neutral">No organization</Badge>
          )
        }
      />

      {error && (
        <div className="rounded-lg border border-danger-500/30 bg-danger-100 px-4 py-3 text-sm text-danger-700">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-lg border border-accent-500/30 bg-accent-100 px-4 py-3 text-sm text-accent-700">
          {message}
        </div>
      )}

      {isPlatformAdmin && (
        <Tabs
          tabs={["Team", "Access"]}
          active={tab === "access" ? "Access" : "Team"}
          onChange={(value) => setTab(value === "Access" ? "access" : "team")}
        />
      )}

      {(tab === "team" || !isPlatformAdmin) && (
        <>
          {!orgLoading && !activeOrganization && (
            <Panel
              title="Organization membership required"
              description="Team management stays inside an organization you belong to."
            >
              <p className="text-sm text-ink-500">
                Sign in with an account that has an active organization membership. This page uses
                that membership and does not accept another tenant id.
              </p>
            </Panel>
          )}

          {activeOrganization && (
            <>
              <MetricStrip>
                <KpiCard title="People" value={loading ? "—" : String(people.length)} />
                <KpiCard title="Active roles" value={loading ? "—" : String(activeCount)} />
                <KpiCard title="Organization admins" value={loading ? "—" : String(adminCount)} />
                <KpiCard title="Organization" value={activeOrganization.status} />
              </MetricStrip>

              {credential && (
                <Panel
                  title="Temporary password"
                  description={`Shown once for ${credential.email}. Share it through a private channel.`}
                  actions={
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => void copyPassword()}>
                        Copy
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setCredential(null)}>
                        Dismiss
                      </Button>
                    </div>
                  }
                >
                  <p className="font-mono text-sm text-ink-900">{credential.password}</p>
                </Panel>
              )}

              {canInvite ? (
                <Panel
                  title="Invite a teammate"
                  description={`The new membership is created in ${activeOrganization.name}.`}
                >
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <FormField label="Full name" required>
                      <Input
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                        placeholder="Jane Doe"
                        autoComplete="name"
                      />
                    </FormField>
                    <FormField label="Work email" required>
                      <Input
                        type="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        placeholder="jane@company.com"
                        autoComplete="email"
                      />
                    </FormField>
                    <FormField label="Role">
                      <Select
                        value={role}
                        onChange={(event) => setRole(event.target.value)}
                        aria-label="Role"
                      >
                        {TEAM_ROLES.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                    <FormField label="Department" required>
                      <Select
                        value={departmentId}
                        onChange={(event) => setDepartmentId(event.target.value)}
                        aria-label="Department"
                      >
                        <option value="">Select a department</option>
                        {departments.map((department) => (
                          <option key={department.id} value={department.id}>
                            {department.name}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                  </div>
                  <div className="mt-4 flex justify-end">
                    <Button
                      onClick={() => void onInvite()}
                      disabled={busy || !email.trim() || !fullName.trim() || !departmentId}
                    >
                      {busy ? "Inviting…" : "Send invite"}
                    </Button>
                  </div>
                  <p className="mt-3 text-xs text-ink-400">
                    New accounts receive a one-time temporary password here, plus a verification
                    email when delivery is configured. Organization admins assign governance roles
                    only.
                  </p>
                </Panel>
              ) : (
                <Panel
                  title="Invites"
                  description="Adding teammates requires an organization admin membership."
                >
                  <p className="text-sm text-ink-500">
                    {orgOpen
                      ? `You can review the ${activeOrganization.name} directory. An organization admin sends invites.`
                      : `${activeOrganization.name} is ${activeOrganization.status.toLowerCase()}, so new invites are paused.`}
                  </p>
                </Panel>
              )}

              <Panel
                title="Organization"
                description="Departments and the team members inside each one."
              >
                {loading ? (
                  <p className="text-sm text-ink-500">Loading organization structure…</p>
                ) : (
                  <OrganizationHierarchy
                    organizationName={activeOrganization.name}
                    departments={departments}
                    people={people}
                  />
                )}
              </Panel>

              <Panel
                title="Directory"
                description={
                  loading
                    ? "Loading members of this organization."
                    : `${visiblePeople.length} of ${people.length} people in ${activeOrganization.name}.`
                }
              >
                <div className="-mx-4 -mb-4 border-t border-base-200">
                  <FilterToolbar
                    value={query}
                    onChange={setQuery}
                    placeholder="Search name, email, or role"
                    filters={[
                      {
                        label: "Role",
                        value: roleFilter,
                        onChange: setRoleFilter,
                        options: TEAM_ROLES.map((option) => ({
                          value: option.value,
                          label: option.label,
                        })),
                      },
                    ]}
                  />
                  {loading ? (
                    <p className="px-4 py-6 text-sm text-ink-500">Loading team members…</p>
                  ) : visiblePeople.length === 0 ? (
                    <p className="px-4 py-8 text-sm text-ink-500">
                      {people.length === 0
                        ? "This organization has no members yet."
                        : "No people match this search."}
                    </p>
                  ) : (
                    <ul className="divide-y divide-base-200">
                      {visiblePeople.map((person) => (
                        <li
                          key={person.userId}
                          data-testid={`member-${person.userId}`}
                          className="flex flex-col gap-3 px-4 py-3"
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                            <div className="flex min-w-0 flex-1 items-center gap-3">
                              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-100 text-xs font-semibold text-accent-700">
                                {initials(person.name)}
                              </div>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-ink-900">
                                  {person.name}
                                </p>
                                <p className="truncate text-xs text-ink-500">
                                  {person.email || "Email unavailable"}
                                  {personDepartment(person).name
                                    ? ` · ${personDepartment(person).name}`
                                    : ""}
                                </p>
                              </div>
                            </div>
                            <div className="flex flex-col items-start gap-2 sm:items-end">
                              <div className="flex flex-wrap items-center gap-1.5">
                                {person.roles.map((membership) => (
                                  <Badge key={membership.id} variant="neutral">
                                    {roleLabel(membership.role)}
                                  </Badge>
                                ))}
                                {Array.from(
                                  new Set(person.roles.map((membership) => membership.status)),
                                ).map((status) => (
                                  <StatusBadge key={`${person.userId}-${status}`} status={status} />
                                ))}
                              </div>
                              {canInvite && (
                                <div className="flex flex-wrap gap-2">
                                  {person.roles.map((membership) => (
                                    <Button
                                      key={membership.id}
                                      variant="outline"
                                      size="sm"
                                      onClick={() => {
                                        setEditingId(membership.id);
                                        setEditRole(membership.role);
                                        setEditStatus(membership.status);
                                      }}
                                    >
                                      Edit {roleLabel(membership.role)}
                                    </Button>
                                  ))}
                                  <Button
                                    variant="danger"
                                    size="sm"
                                    disabled={actingId === person.userId}
                                    onClick={() => void onRemovePerson(person)}
                                  >
                                    Remove
                                  </Button>
                                </div>
                              )}
                            </div>
                          </div>
                          {canInvite &&
                            person.roles
                              .filter((membership) => membership.id === editingId)
                              .map((membership) => (
                                <div
                                  key={`${membership.id}-edit`}
                                  className="grid w-full gap-3 border-t border-base-200 pt-3 md:grid-cols-[1fr_1fr_auto]"
                                >
                                  <FormField label="Role">
                                    <Select
                                      aria-label={`Role for ${person.name}`}
                                      value={editRole}
                                      onChange={(event) => setEditRole(event.target.value)}
                                    >
                                      {TEAM_ROLES.map((option) => (
                                        <option key={option.value} value={option.value}>
                                          {option.label}
                                        </option>
                                      ))}
                                    </Select>
                                  </FormField>
                                  <FormField label="Status">
                                    <Select
                                      aria-label={`Status for ${person.name}`}
                                      value={editStatus}
                                      onChange={(event) => setEditStatus(event.target.value)}
                                    >
                                      {MEMBERSHIP_STATUSES.map((status) => (
                                        <option key={status} value={status}>
                                          {status.toLowerCase()}
                                        </option>
                                      ))}
                                    </Select>
                                  </FormField>
                                  <div className="flex items-end gap-2">
                                    <Button
                                      size="sm"
                                      disabled={actingId === membership.id}
                                      onClick={() => void onSaveMembership(membership.id)}
                                    >
                                      Save
                                    </Button>
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      disabled={actingId === membership.id}
                                      onClick={() =>
                                        void onDeleteMembership(membership, person.name)
                                      }
                                    >
                                      Remove role
                                    </Button>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => setEditingId(null)}
                                    >
                                      Cancel
                                    </Button>
                                  </div>
                                </div>
                              ))}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Panel>
            </>
          )}
        </>
      )}
      {tab === "access" && isPlatformAdmin && <AccessPanel />}
    </div>
  );
}
