"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  AlertTriangle,
  Truck,
  Warehouse,
  Users,
  BarChart3,
  ShieldAlert,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/disasters", label: "Disasters", icon: AlertTriangle },
  { href: "/shipments", label: "Shipments", icon: Truck },
  { href: "/warehouses", label: "Warehouses", icon: Warehouse },
  { href: "/volunteers", label: "Volunteers", icon: Users },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/disruptions", label: "Disruptions ML", icon: ShieldAlert },
  { href: "/copilot", label: "Copilot", icon: Sparkles },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 border-r bg-card md:flex md:flex-col">
      <div className="border-b p-6">
        <Link href="/dashboard" className="flex items-baseline gap-2">
          <span className="text-lg font-semibold tracking-tight">ReliefOps</span>
          <span className="text-xs text-muted-foreground">v0.1</span>
        </Link>
        <p className="mt-1 text-xs text-muted-foreground">AI disaster logistics</p>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
