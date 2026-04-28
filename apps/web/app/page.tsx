import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="max-w-3xl text-center">
        <p className="mb-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Google Solution Challenge 2026
        </p>
        <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">
          ReliefOps
        </h1>
        <p className="mt-4 text-xl text-muted-foreground">
          AI dispatcher that turns chaos into coordinated relief in the first
          72&nbsp;hours of a disaster.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <span className="rounded-full border px-3 py-1 text-xs">SDG 2</span>
          <span className="rounded-full border px-3 py-1 text-xs">SDG 3</span>
          <span className="rounded-full border px-3 py-1 text-xs">SDG 9</span>
          <span className="rounded-full border px-3 py-1 text-xs">SDG 11</span>
          <span className="rounded-full border px-3 py-1 text-xs">SDG 13</span>
        </div>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/dashboard"
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90"
          >
            Open Admin Dashboard
          </Link>
          <Link
            href="/login"
            className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-background px-6 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            Sign in
          </Link>
        </div>
        <p className="mt-12 text-xs text-muted-foreground">
          COMMIT 1 — monorepo bootstrap. Auth flows arrive in COMMIT 3.
        </p>
      </div>
    </main>
  );
}
