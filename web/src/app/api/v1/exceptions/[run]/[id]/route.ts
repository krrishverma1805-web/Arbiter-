import { NextResponse } from "next/server";
import { demo } from "@/lib/demo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ run: string; id: string }> },
) {
  const { id } = await params;
  const d = demo.drawer(id);
  if (!d) return NextResponse.json({ detail: "not found" }, { status: 404 });
  return NextResponse.json(d);
}
