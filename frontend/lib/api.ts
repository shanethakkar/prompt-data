// Resolve a backend path. In production the browser calls the Render backend directly
// (NEXT_PUBLIC_API_BASE, via CORS) so long SSE streams avoid the Vercel proxy; local dev
// leaves it unset and uses the Next /api rewrite (see next.config.ts).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

export function apiUrl(path: string): string {
  return API_BASE ? `${API_BASE}${path}` : `/api${path}`;
}
