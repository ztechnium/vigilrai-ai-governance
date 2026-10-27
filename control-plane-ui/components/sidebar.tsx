"use client";

import { useMemo, useState, type ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  Ban,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  ClipboardList,
  DoorClosed,
  Eye,
  Coins,
  FileBarChart,
  FilePen,
  FileSearch,
  Fingerprint,
  Flag,
  Flame,
  FlaskConical,
  Gauge,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  Library,
  Lightbulb,
  ListTodo,
  Menu,
  MessagesSquare,
  Network,
  OctagonAlert,
  Package,
  Play,
  Radio,
  Rocket,
  Scale,
  ScanText,
  ScrollText,
  Search,
  Settings,
  Shield,
  ShieldCheck,
  Siren,
  SlidersHorizontal,
  Terminal,
  UserCog,
  Users,
  X,
  type LucideProps,
} from "lucide-react";
import { navSections, type NavIcon } from "@/lib/nav";
import { useAuth, useOrganization, usePermissions } from "@/lib/hooks/use-auth";
import { tenantHasNavRole } from "@/lib/platform-roles";
import { cn } from "@/lib/utils";

type IconComponent = ComponentType<LucideProps>;

const NAV_ICONS: Record<NavIcon, IconComponent> = {
  "layout-dashboard": LayoutDashboard,
  rocket: Rocket,
  network: Network,
  library: Library,
  "shield-check": ShieldCheck,
  scale: Scale,
  fingerprint: Fingerprint,
  "messages-square": MessagesSquare,
  "file-search": FileSearch,
  "check-circle": CheckCircle2,
  search: Search,
  terminal: Terminal,
  activity: Activity,
  gauge: Gauge,
  "alert-triangle": AlertTriangle,
  "circle-alert": CircleAlert,
  radio: Radio,
  siren: Siren,
  "octagon-alert": OctagonAlert,
  lightbulb: Lightbulb,
  "scan-text": ScanText,
  "flask-conical": FlaskConical,
  play: Play,
  "door-closed": DoorClosed,
  "file-pen": FilePen,
  "clipboard-check": ClipboardCheck,
  "sliders-horizontal": SlidersHorizontal,
  "clipboard-list": ClipboardList,
  flame: Flame,
  ban: Ban,
  package: Package,
  "list-todo": ListTodo,
  "building-2": Building2,
  "layout-grid": LayoutGrid,
  chart: ChartNoAxesCombined,
  eye: Eye,
  shield: Shield,
  users: Users,
  "user-cog": UserCog,
  "key-round": KeyRound,
  flag: Flag,
  settings: Settings,
  "scroll-text": ScrollText,
  "file-bar-chart": FileBarChart,
  coins: Coins,
};

function GateMark() {
  return (
    <svg aria-hidden viewBox="0 0 36 36" className="size-9 shrink-0">
      <path
        d="M4 7h8l6 7 6-7h8M4 29h8l6-7 6 7h8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <circle cx="18" cy="18" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="m16.4 18 1.1 1.1 2.3-2.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { isPlatformAdmin, organizations } = useAuth();
  const { activeOrganization } = useOrganization();
  const { tenant } = usePermissions();

  const userRoles = useMemo(() => {
    if (tenant?.roles?.length) return tenant.roles;
    if (activeOrganization?.roles?.length) return activeOrganization.roles;
    const fromMemberships = organizations.flatMap((org) => org.roles || []);
    return Array.from(new Set(fromMemberships));
  }, [tenant?.roles, activeOrganization?.roles, organizations]);

  const hasRole = (requiredRole: string): boolean => {
    if (isPlatformAdmin) return true;
    return tenantHasNavRole(requiredRole, userRoles);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed left-3 top-3 z-30 rounded-md border border-base-200 bg-base-50 p-2 text-ink-500 lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-5" aria-hidden />
      </button>
      {open && (
        <button
          type="button"
          aria-label="Close navigation overlay"
          className="fixed inset-0 z-30 bg-base-900/80 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-base-200 bg-base-800 text-ink-700 transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-[68px] items-center gap-3 border-b border-base-200 px-4 text-accent-600">
          <GateMark />
          <div>
            <div className="text-base font-bold text-ink-900">VIGILRAI</div>
            <div className="text-[9px] font-semibold tracking-wide text-ink-400">
              AI CONTROL & ASSURANCE
            </div>
          </div>
          <button
            type="button"
            className="ml-auto text-ink-400 lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-2">
          {navSections.map((section) => {
            const visibleItems = section.items.filter((item) => {
              if (item.roles && item.roles.length > 0) {
                if (!item.roles.some((role) => hasRole(role))) return false;
              }
              if (item.platformOnly && !isPlatformAdmin) return false;
              return true;
            });
            if (visibleItems.length === 0) return null;

            return (
              <div className="mb-5" key={section.label}>
                <p className="px-2 pb-2 text-[9px] font-semibold uppercase tracking-wide text-ink-400">
                  {section.label}
                </p>
                {visibleItems.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = NAV_ICONS[item.icon];
                  const className = cn(
                    "mb-0.5 flex h-9 items-center gap-2 rounded-md border-l-2 px-3 text-sm transition-colors",
                    active
                      ? "border-accent-600 bg-base-700 font-medium text-ink-900"
                      : "border-transparent text-ink-500 hover:bg-base-700 hover:text-ink-900",
                  );
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={className}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {active && <span className="size-1.5 shrink-0 rounded-full bg-accent-600" />}
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <div className="border-t border-base-200 p-3 text-xs text-ink-400">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent-500" />
            Control plane operational
          </div>
        </div>
      </aside>
    </>
  );
}
