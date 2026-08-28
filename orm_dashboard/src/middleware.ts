import { NextRequest, NextResponse } from "next/server";

// Redirects unauthenticated requests to /login (TASK_AUTH.md fix #5).
// This only checks for the session cookie's PRESENCE -- it's httpOnly so
// middleware can't read its value, and doesn't need to: the cookie is
// opaque anyway (core/security.py), so real validation happens on the
// backend via /auth/me and every API call's get_current_user dependency.
// A present-but-expired/revoked cookie still gets past this check and is
// rejected by the backend instead -- that's a 401 the dashboard's own
// fetch error states already handle, not a security gap.
const SESSION_COOKIE_NAME = "orm_session";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isPublicPath = pathname === "/login" || pathname === "/";
  const isStaticAsset =
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    /\.[a-zA-Z0-9]+$/.test(pathname);

  if (isPublicPath || isStaticAsset) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api).*)"],
};
