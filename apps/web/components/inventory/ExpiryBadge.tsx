import { cn } from "@/lib/utils";

const styles = {
  expired: "bg-red-100 text-red-700",
  urgent: "bg-amber-100 text-amber-700",
  soon: "bg-yellow-100 text-yellow-700",
  ok: "bg-emerald-100 text-emerald-700",
};

export function ExpiryBadge({ daysToExpiry }: { daysToExpiry: number }) {
  let label: string;
  let style: string;
  if (daysToExpiry <= 0) {
    label = "Expired";
    style = styles.expired;
  } else if (daysToExpiry <= 3) {
    label = `${daysToExpiry}d left`;
    style = styles.urgent;
  } else if (daysToExpiry <= 14) {
    label = `${daysToExpiry}d left`;
    style = styles.soon;
  } else {
    label = `${daysToExpiry}d`;
    style = styles.ok;
  }
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        style,
      )}
    >
      {label}
    </span>
  );
}
