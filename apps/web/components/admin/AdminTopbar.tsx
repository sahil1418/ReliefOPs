"use client";

import { SignOutButton } from "@/components/auth/SignOutButton";
import { useAuth } from "@/components/providers/AuthProvider";

export function AdminTopbar({ title }: { title?: string }) {
  const auth = useAuth();
  const name =
    auth.status === "authenticated"
      ? auth.user.displayName ?? auth.user.email ?? auth.user.uid
      : "Loading…";
  const role = auth.status === "authenticated" ? auth.user.role ?? "(no role)" : "";

  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div>
        {title ? <h1 className="text-2xl font-semibold tracking-tight">{title}</h1> : null}
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right text-xs">
          <div className="font-medium">{name}</div>
          <div className="text-muted-foreground">{role}</div>
        </div>
        <SignOutButton />
      </div>
    </header>
  );
}
