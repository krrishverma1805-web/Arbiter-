import { NextResponse } from "next/server";
import { demo } from "@/lib/demo";

export const dynamic = "force-static";

export function GET() {
  return NextResponse.json(demo.datasets);
}
