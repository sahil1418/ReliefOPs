/**
 * Client-side auth helpers + `useCurrentUser` hook.
 *
 * The shape returned matches what FastAPI puts in UserClaims so the web and API
 * stay aligned (`role`, `orgId`, `uid`, etc.).
 */
"use client";

import { useEffect, useState } from "react";
import {
  GoogleAuthProvider,
  RecaptchaVerifier,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signInWithPhoneNumber,
  signInWithPopup,
  signOut as fbSignOut,
  type ConfirmationResult,
  type User,
} from "firebase/auth";

import { firebaseAuth } from "@/lib/firebase";

import type { Role } from "@relief/shared-types";

export type CurrentUser = {
  uid: string;
  email: string | null;
  displayName: string | null;
  phone: string | null;
  role: Role | null;
  orgId: string | null;
  emailVerified: boolean;
};

export type AuthState =
  | { status: "loading"; user: null }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "anonymous"; user: null };

function decodeClaims(user: User, idTokenResult: { claims: Record<string, unknown> }): CurrentUser {
  const claims = idTokenResult.claims;
  return {
    uid: user.uid,
    email: user.email,
    displayName: user.displayName,
    phone: user.phoneNumber,
    role: (claims.role as Role | undefined) ?? null,
    orgId: (claims.orgId as string | undefined) ?? null,
    emailVerified: user.emailVerified,
  };
}

async function syncSessionCookie(user: User | null): Promise<void> {
  if (!user) {
    await fetch("/api/auth/session", { method: "DELETE" });
    return;
  }
  const idToken = await user.getIdToken(/* forceRefresh */ false);
  await fetch("/api/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idToken }),
  });
}

/**
 * React hook returning the current user (or null) and a stable status.
 * Subscribes to Firebase's onIdTokenChanged so it picks up sign-in, sign-out,
 * and the 1-hour ID-token rotation. Each rotation also re-syncs the session cookie.
 */
export function useCurrentUser(): AuthState {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  useEffect(() => {
    const auth = firebaseAuth();
    return onIdTokenChanged(auth, async (user) => {
      try {
        await syncSessionCookie(user);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[auth] session cookie sync failed", err);
      }
      if (!user) {
        setState({ status: "anonymous", user: null });
        return;
      }
      const tokenResult = await user.getIdTokenResult();
      setState({ status: "authenticated", user: decodeClaims(user, tokenResult) });
    });
  }, []);

  return state;
}

// ── Imperative actions invoked from form submit handlers ─────────────────────

export async function signInWithEmail(email: string, password: string): Promise<CurrentUser> {
  const cred = await signInWithEmailAndPassword(firebaseAuth(), email, password);
  await syncSessionCookie(cred.user);
  const tokenResult = await cred.user.getIdTokenResult();
  return decodeClaims(cred.user, tokenResult);
}

export async function signInWithGoogle(): Promise<CurrentUser> {
  const provider = new GoogleAuthProvider();
  const cred = await signInWithPopup(firebaseAuth(), provider);
  await syncSessionCookie(cred.user);
  const tokenResult = await cred.user.getIdTokenResult();
  return decodeClaims(cred.user, tokenResult);
}

let _recaptcha: RecaptchaVerifier | null = null;
export function getInvisibleRecaptcha(containerId: string): RecaptchaVerifier {
  if (_recaptcha) return _recaptcha;
  _recaptcha = new RecaptchaVerifier(firebaseAuth(), containerId, { size: "invisible" });
  return _recaptcha;
}

export async function startPhoneSignIn(
  e164PhoneNumber: string,
  recaptchaContainerId: string,
): Promise<ConfirmationResult> {
  const verifier = getInvisibleRecaptcha(recaptchaContainerId);
  return signInWithPhoneNumber(firebaseAuth(), e164PhoneNumber, verifier);
}

export async function confirmPhoneSignIn(
  confirmation: ConfirmationResult,
  code: string,
): Promise<CurrentUser> {
  const cred = await confirmation.confirm(code);
  await syncSessionCookie(cred.user);
  const tokenResult = await cred.user.getIdTokenResult();
  return decodeClaims(cred.user, tokenResult);
}

export async function signOut(): Promise<void> {
  await fbSignOut(firebaseAuth());
  await syncSessionCookie(null);
}

/**
 * Returns the current ID token for outgoing API calls. Forces refresh if expired.
 * Returns `null` when there's no signed-in user.
 */
export async function getIdToken(): Promise<string | null> {
  const user = firebaseAuth().currentUser;
  if (!user) return null;
  return user.getIdToken();
}
