// Shared types between web (Next.js) and any future TS clients.
// COMMIT 1: only the API response envelope so web↔api wiring has a typed contract.
// COMMIT 4+ will add Firestore document types (Shipment, Disaster, etc.) mirrored
// from the Pydantic models in apps/api/src/modules/.../models.py.
export type ApiResponse<T> =
  | { data: T; error: null }
  | { data: null; error: { code: string; message: string; details?: unknown } };

export type Role =
  | "super_admin"
  | "ngo_admin"
  | "coordinator"
  | "volunteer"
  | "beneficiary"
  | "viewer";
