/**
 * Firebase Web SDK initialization (browser-side).
 *
 * Auto-routes to local emulators when NEXT_PUBLIC_USE_EMULATORS === "true".
 * Server-side auth is handled by next-firebase-auth-edge in middleware.ts.
 */
import { initializeApp, getApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  connectAuthEmulator,
  type Auth,
} from "firebase/auth";
import {
  getFirestore,
  connectFirestoreEmulator,
  type Firestore,
} from "firebase/firestore";
import {
  getDatabase,
  connectDatabaseEmulator,
  type Database,
} from "firebase/database";
import {
  getStorage,
  connectStorageEmulator,
  type FirebaseStorage,
} from "firebase/storage";

export const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "demo-api-key",
  authDomain:
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ??
    "relief-logistics.firebaseapp.com",
  projectId:
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "relief-logistics",
  storageBucket:
    process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ??
    "relief-logistics.appspot.com",
  messagingSenderId:
    process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "0",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "demo-app-id",
  databaseURL:
    process.env.NEXT_PUBLIC_FIREBASE_DATABASE_URL ??
    "https://relief-logistics-default-rtdb.firebaseio.com",
} as const;

const useEmulators = process.env.NEXT_PUBLIC_USE_EMULATORS === "true";

let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;
let _db: Firestore | null = null;
let _rtdb: Database | null = null;
let _storage: FirebaseStorage | null = null;
let _emulatorsConnected = false;

export function firebaseApp(): FirebaseApp {
  if (_app) return _app;
  _app = getApps().length ? getApp() : initializeApp(firebaseConfig);
  return _app;
}

function maybeConnectEmulators(): void {
  if (_emulatorsConnected || !useEmulators || typeof window === "undefined") {
    return;
  }
  if (_auth) connectAuthEmulator(_auth, "http://127.0.0.1:9099", { disableWarnings: true });
  if (_db) connectFirestoreEmulator(_db, "127.0.0.1", 8080);
  if (_rtdb) connectDatabaseEmulator(_rtdb, "127.0.0.1", 9000);
  if (_storage) connectStorageEmulator(_storage, "127.0.0.1", 9199);
  _emulatorsConnected = true;
  // eslint-disable-next-line no-console
  console.info("[firebase] connected to local emulator suite");
}

export function firebaseAuth(): Auth {
  if (!_auth) {
    _auth = getAuth(firebaseApp());
    maybeConnectEmulators();
  }
  return _auth;
}

export function firebaseDb(): Firestore {
  if (!_db) {
    _db = getFirestore(firebaseApp());
    maybeConnectEmulators();
  }
  return _db;
}

export function firebaseRtdb(): Database {
  if (!_rtdb) {
    _rtdb = getDatabase(firebaseApp());
    maybeConnectEmulators();
  }
  return _rtdb;
}

export function firebaseStorage(): FirebaseStorage {
  if (!_storage) {
    _storage = getStorage(firebaseApp());
    maybeConnectEmulators();
  }
  return _storage;
}
