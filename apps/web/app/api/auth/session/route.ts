/**
 * Session-cookie minter — bridges client-side Firebase Auth to the middleware gate.
 *
 * POST /api/auth/session  body: { idToken: string }
 *   Sets HttpOnly `__session` cookie containing the ID token (1h TTL — same as token).
 *   The web middleware checks for cookie *presence* only.
 *   FastAPI verifies the actual token signature on every protected call.
 *
 * DELETE /api/auth/session
 *   Clears the cookie.
 *
 * Why not full `next-firebase-auth-edge` cookie verification yet? It needs a real
 * service-account private key inlined into edge env vars. We don't have one in
 * emulator mode. A real private key gets wired in COMMIT 10 alongside Cloud Run.
 */
import { type NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "__session";
const COOKIE_MAX_AGE_SECONDS = 60 * 60; // 1h, matches Firebase ID token lifetime

export async function POST(req: NextRequest) {
  let body: { idToken?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { data: null, error: { code: "INVALID_BODY", message: "Body must be JSON." } },
      { status: 400 },
    );
  }

  const idToken = body.idToken?.trim();
  if (!idToken) {
    return NextResponse.json(
      { data: null, error: { code: "MISSING_TOKEN", message: "idToken is required." } },
      { status: 400 },
    );
  }

  const res = NextResponse.json({ data: { ok: true }, error: null });
  res.cookies.set({
    name: COOKIE_NAME,
    value: idToken,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: COOKIE_MAX_AGE_SECONDS,
  });
  return res;
}

export async function DELETE(_req: NextRequest) {
  const res = NextResponse.json({ data: { ok: true }, error: null });
  res.cookies.set({
    name: COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return res;
}
