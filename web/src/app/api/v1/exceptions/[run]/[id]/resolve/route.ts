import { NextResponse } from "next/server";

// The hosted demo is read-only — a resolve is acknowledged but nothing is
// written. Run the real stack (`make up`) to resolve and draft rules for real.
export function POST() {
  return NextResponse.json({ ok: true, demo: true });
}
