import { cn } from "@/lib/utils";

type Status = "created" | "assigned" | "in_transit" | "delivered" | "failed";

const styles: Record<Status, string> = {
  created: "bg-slate-100 text-slate-700",
  assigned: "bg-blue-100 text-blue-700",
  in_transit: "bg-amber-100 text-amber-700",
  delivered: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

const labels: Record<Status, string> = {
  created: "Created",
  assigned: "Assigned",
  in_transit: "In transit",
  delivered: "Delivered",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: string }) {
  const key = (status in styles ? status : "created") as Status;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        styles[key],
      )}
    >
      {labels[key]}
    </span>
  );
}

const priorityStyles: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-amber-100 text-amber-700",
  normal: "bg-slate-100 text-slate-700",
};

export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        priorityStyles[priority] ?? priorityStyles.normal,
      )}
    >
      {priority}
    </span>
  );
}
