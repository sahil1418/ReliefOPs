"use client";

import dynamic from "next/dynamic";

// Leaflet hits `window` on import; force client-side render.
export const LiveShipmentMapDynamic = dynamic(
  () => import("@/components/map/LiveShipmentMap").then((m) => m.LiveShipmentMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[420px] w-full items-center justify-center rounded-md border bg-muted/40 text-sm text-muted-foreground">
        Loading map…
      </div>
    ),
  },
);

export default LiveShipmentMapDynamic;
