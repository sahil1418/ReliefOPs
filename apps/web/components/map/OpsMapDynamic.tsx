"use client";

import dynamic from "next/dynamic";

export const OpsMapDynamic = dynamic(
  () => import("@/components/map/OpsMap").then((m) => m.OpsMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[480px] w-full items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-sm text-slate-400">
        Loading operations map…
      </div>
    ),
  },
);

export default OpsMapDynamic;
