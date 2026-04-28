import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { ShipmentDetail } from "@/components/shipments/ShipmentDetail";

export default function ShipmentDetailPage({ params }: { params: { id: string } }) {
  return (
    <>
      <AdminTopbar title="Shipment detail" />
      <main className="flex-1 p-6">
        <ShipmentDetail shipmentId={params.id} />
      </main>
    </>
  );
}
