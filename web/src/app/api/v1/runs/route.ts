import { NextResponse } from "next/server";
import { demo } from "@/lib/demo";

// GET /v1/runs — the run list. POST /v1/runs — the hosted demo can't execute a
// fresh reconciliation, so it points every "reconcile" at the pre-seeded run.
export function GET() {
  return NextResponse.json(demo.runs);
}

export function POST() {
  return NextResponse.json({ job_id: 1, ...demo.run }, { status: 202 });
}
