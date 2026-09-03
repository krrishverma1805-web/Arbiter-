import { demo } from "@/lib/demo";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// Replays the captured event sequence from the real run as SSE, paced so the
// /live investigation view animates the way it did during the actual run.
export function GET() {
  const enc = new TextEncoder();
  const { records, frames } = demo.stream;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (type: string, data: unknown) =>
        controller.enqueue(
          enc.encode(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`),
        );
      const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

      // a burst of ingest ticks for the counter animation
      const ticks = Math.min(30, records);
      for (let i = 0; i < ticks; i++) {
        send("RECORD_INGESTED", { type: "RECORD_INGESTED", seq: i });
        await sleep(70);
      }

      for (const f of frames) {
        const t = (f.type as string) || "message";
        send(t, f);
        // agent turns land slower so you can read them
        await sleep(
          t === "AGENT_INTERACTION"
            ? 1400
            : t.startsWith("AGENT_") || t === "RUN_COMPLETED"
              ? 700
              : t === "EXCEPTION_OPENED" || t === "EXCEPTION_CLASSIFIED"
                ? 220
                : 90,
        );
      }

      send("done", {});
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}
