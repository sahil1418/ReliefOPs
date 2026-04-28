/**
 * Next.js middleware — gates admin routes behind a Firebase session cookie.
 *
 * COMMIT 2: minimal cookie presence check — full `next-firebase-auth-edge`
 * verification (with refresh-token rotation) lands in COMMIT 3 alongside the
 * `/api/login` and `/api/logout` routes that mint the cookie.
 *
 * Why not call `next-firebase-auth-edge` here yet? It needs the service-account
 * private key inlined into edge env vars, which only makes sense once we have
 * a real service account file. Until then, presence of the session cookie is a
 * sufficient signal — the actual ID token is verified server-side by FastAPI
 * on every protected API call.
 */
import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "__session";

const PROTECTED_PREFIXES = ["/dashboard", "/disasters", "/shipments", "/warehouses", "/copilot", "/analytics", "/volunteers"];
const AUTH_PAGES = ["/login"];

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/health|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  if (isProtected && !hasSession) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthPage && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  return NextResponse.next();
}
