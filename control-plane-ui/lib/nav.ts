/**
 * Navigation configuration for the Control Plane UI.
 *
 * Role names here are for UX filtering only and map to server-derived permissions.
 * The backend is authoritative for all authorization decisions.
 */

export type NavIcon =
  | "layout-dashboard"
  | "rocket"
  | "network"
  | "library"
  | "shield-check"
  | "scale"
  | "fingerprint"
  | "messages-square"
  | "file-search"
  | "check-circle"
  | "search"
  | "terminal"
  | "activity"
  | "gauge"
  | "alert-triangle"
  | "circle-alert"
  | "radio"
  | "siren"
  | "octagon-alert"
  | "lightbulb"
  | "scan-text"
  | "flask-conical"
  | "play"
  | "door-closed"
  | "file-pen"
  | "clipboard-check"
  | "sliders-horizontal"
  | "clipboard-list"
  | "flame"
  | "ban"
  | "package"
  | "list-todo"
  | "building-2"
  | "layout-grid"
  | "chart"
  | "eye"
  | "shield"
  | "users"
  | "user-cog"
  | "key-round"
  | "flag"
  | "settings"
  | "scroll-text"
  | "file-bar-chart"
  | "coins";

type NavRole = string;

export interface NavItem {
  label: string;
  href: string;
  icon: NavIcon;
  roles: NavRole[];
  /** Platform-only surfaces (all-tenant admin). Hidden for tenant RAI officers. */
  platformOnly?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

const ALL_ROLES: NavRole[] = [
  "Prompt Requester",
  "Prompt Author",
  "Business Approver",
  "RAI Officer",
  "Risk Officer",
  "Incident Manager",
  "RAG Domain Owner",
  "RAG Approver",
  "General Admin",
  "Auditor",
];

const REGISTRY_ROLES: NavRole[] = ["RAI Officer", "General Admin"];
const FINOPS_ROLES: NavRole[] = [
  "RAI Officer",
  "Risk Officer",
  "Auditor",
  "General Admin",
  "Business Approver",
];

const PORTFOLIO_ROLES: NavRole[] = [
  "General Admin",
  "RAI Officer",
  "Risk Officer",
  "Auditor",
  "Business Approver",
];

export const navSections: NavSection[] = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: "layout-dashboard", roles: ALL_ROLES },
      { label: "Reports", href: "/reports", icon: "file-bar-chart", roles: ALL_ROLES },
      { label: "Onboarding", href: "/app/onboarding", icon: "rocket", roles: ALL_ROLES },
    ],
  },
  {
    label: "Build & Govern",
    items: [
      { label: "AI Systems", href: "/governance/registry", icon: "network", roles: REGISTRY_ROLES },
      {
        label: "Resource Catalog",
        href: "/governance/registry/catalog",
        icon: "library",
        roles: REGISTRY_ROLES,
      },
      {
        label: "Policy Library",
        href: "/governance/policies",
        icon: "shield-check",
        roles: [...REGISTRY_ROLES, "Business Approver"],
      },
      {
        label: "RAI Rules",
        href: "/governance/rai-rules",
        icon: "scale",
        roles: ["RAI Officer", "General Admin"],
      },
    ],
  },
  {
    label: "Runtime",
    items: [
      {
        label: "Runtime Identities",
        href: "/governance/runtime-identities",
        icon: "fingerprint",
        roles: REGISTRY_ROLES,
      },
      {
        label: "Trajectories",
        href: "/runtime/trajectories",
        icon: "file-search",
        roles: ["General Admin", "Auditor", "RAI Officer", "Business Approver"],
      },
      {
        label: "Approvals",
        href: "/governance/approvals",
        icon: "check-circle",
        roles: [...REGISTRY_ROLES, "Business Approver"],
      },
      {
        label: "Audit Explorer",
        href: "/runtime/audit",
        icon: "search",
        roles: ["General Admin", "Auditor", "RAI Officer"],
      },
    ],
  },
  {
    label: "Risk",
    items: [
      {
        label: "Overview",
        href: "/risk",
        icon: "activity",
        roles: ["General Admin", "Auditor", "RAI Officer", "Business Approver"],
      },
      {
        label: "Budgets",
        href: "/risk/budgets",
        icon: "gauge",
        roles: ["General Admin", "RAI Officer"],
      },
      {
        label: "Findings",
        href: "/risk/findings",
        icon: "circle-alert",
        roles: ["General Admin", "Auditor", "RAI Officer"],
      },
      {
        label: "Monitoring",
        href: "/risk/monitoring",
        icon: "radio",
        roles: ["General Admin", "RAI Officer"],
      },
      {
        label: "Emergency Controls",
        href: "/risk/emergency",
        icon: "octagon-alert",
        roles: ["General Admin", "RAI Officer"],
      },
      {
        label: "Content Evaluation",
        href: "/risk/content-evaluator",
        icon: "scan-text",
        roles: ["General Admin", "RAI Officer"],
      },
    ],
  },
  {
    label: "FinOps",
    items: [{ label: "Overview", href: "/finops", icon: "coins", roles: FINOPS_ROLES }],
  },
  {
    label: "Portfolio",
    items: [{ label: "Overview", href: "/portfolio", icon: "chart", roles: PORTFOLIO_ROLES }],
  },
  {
    label: "Organization",
    items: [
      {
        label: "Team & roles",
        href: "/organization/team",
        icon: "users",
        roles: ["General Admin", "RAI Officer"],
      },
      {
        label: "API Keys",
        href: "/administration/api-keys",
        icon: "key-round",
        roles: ["General Admin"],
        platformOnly: true,
      },
      {
        label: "Settings",
        href: "/settings",
        icon: "settings",
        roles: ["General Admin", "RAI Officer"],
      },
      {
        label: "Webhooks",
        href: "/settings/webhooks",
        icon: "settings",
        roles: ["General Admin", "RAI Officer"],
      },
    ],
  },
];
