import { cn } from "@/lib/utils";

const styles: Record<string, string> = {
  critical: "bg-red-100 text-red-700 ring-red-600/20",
  high: "bg-amber-100 text-amber-700 ring-amber-600/20",
  medium: "bg-yellow-100 text-yellow-700 ring-yellow-600/20",
  low: "bg-slate-100 text-slate-700 ring-slate-600/20",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset capitalize",
        styles[severity] ?? styles.low,
      )}
    >
      {severity}
    </span>
  );
}

const disasterStatusStyles: Record<string, string> = {
  active: "bg-red-100 text-red-700",
  contained: "bg-amber-100 text-amber-700",
  closed: "bg-slate-100 text-slate-600",
};

export function DisasterStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        disasterStatusStyles[status] ?? disasterStatusStyles.closed,
      )}
    >
      {status}
    </span>
  );
}

const urgencyDotColors: Record<number, string> = {
  5: "bg-red-500",
  4: "bg-amber-500",
  3: "bg-yellow-500",
  2: "bg-slate-400",
  1: "bg-slate-300",
};

export function UrgencyDot({ urgency }: { urgency: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cn("inline-block h-2 w-2 rounded-full", urgencyDotColors[urgency] ?? urgencyDotColors[1])} />
      {urgency}
    </span>
  );
}
