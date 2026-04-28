import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { ShipmentsTable } from "@/components/shipments/ShipmentsTable";

export default function ShipmentsPage() {
  return (
    <>
      <AdminTopbar title="Shipments" />
      <main className="flex-1 space-y-6 p-6">
        <p className="text-sm text-muted-foreground">
          Real-time view of all shipments visible to your role. Updates stream from Firestore — no
          page refresh needed when status changes.
        </p>
        <ShipmentsTable />
      </main>
    </>
  );
}
