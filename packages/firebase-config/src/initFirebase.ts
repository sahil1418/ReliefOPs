/**
 * Web Firebase SDK init (re-exportable from the workspace).
 * Mirrors apps/web/lib/firebase.ts but consumable by other web targets.
 */
import { initializeApp, getApp, getApps, type FirebaseApp } from "firebase/app";

export type FirebaseClientConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  storageBucket: string;
  messagingSenderId: string;
  appId: string;
  databaseURL: string;
};

export function initFirebaseClient(config: FirebaseClientConfig): FirebaseApp {
  return getApps().length ? getApp() : initializeApp(config);
}

export const PROJECT_ID = "relief-logistics" as const;
export const REGION = "us-central1" as const;
export const FIRESTORE_LOCATION = "nam5" as const;

export const EMULATOR_HOSTS = {
  auth: "127.0.0.1:9099",
  firestore: { host: "127.0.0.1", port: 8080 },
  database: { host: "127.0.0.1", port: 9000 },
  storage: { host: "127.0.0.1", port: 9199 },
  functions: { host: "127.0.0.1", port: 5001 },
  pubsub: "127.0.0.1:8085",
  ui: "http://127.0.0.1:4000",
} as const;
