import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Next.js 16: renamed from `middleware` to `proxy`.
// Forward the pathname as a REQUEST header so generateMetadata in (app)/layout.tsx
// can resolve the correct page title on SSR/refresh. It must be set on the
// request (via NextResponse.next({ request })), not the response — server
// components read incoming request headers, so a response header is invisible
// to generateMetadata (which is why refresh fell back to the bare "Kairos" title).
export function proxy(req: NextRequest) {
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", req.nextUrl.pathname);
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next|favicon|logo|sw\\.js).*)"],
};
