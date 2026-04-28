"use client";

import dynamic from "next/dynamic";

export const FleetMapDynamic = dynamic(
  () => import("@/components/map/FleetMap").then((m) => m.FleetMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[400px] w-full items-center justify-center rounded-md border bg-muted/40 text-sm text-muted-foreground">
        Loading fleet map…
      </div>
    ),
  },
);

export default FleetMapDynamic;
