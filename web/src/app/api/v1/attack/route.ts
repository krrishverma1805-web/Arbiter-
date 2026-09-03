import { NextResponse } from "next/server";
import { demo } from "@/lib/demo";

// The hosted demo has no Python backend — it serves the frozen output of
// `arbiter attack --json` against the seed dataset. A real deployment proxies
// POST /v1/attack to the API.
export function POST() {
  const scenarios = demo.attack as Array<Record<string, unknown>>;
  return NextResponse.json({
    scenarios,
    contained: scenarios.filter((s) => s.verdict === "CONTAINED").length,
    unsafe: scenarios.filter((s) => s.verdict === "UNSAFE").length,
    rupees_unaccounted_minor: scenarios.reduce(
      (sum, s) => sum + (s.rupees_unaccounted_minor as number),
      0,
    ),
  });
}
