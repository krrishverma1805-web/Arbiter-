import { api, type Scorecard } from "@/lib/api";
import { Cockpit } from "@/components/Cockpit";
import { demo } from "@/lib/demo";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const isDemo = !process.env.ARBITER_API_URL;
  const [run, scorecard, exceptions] = isDemo
    ? [demo.run, demo.scorecard as unknown as Scorecard, demo.exceptions.exceptions]
    : await Promise.all([
        api.run(id),
        api.scorecard(id).catch(() => null),
        api.exceptions(id).then((r) => r.exceptions),
      ]);

  return <Cockpit runId={id} run={run} scorecard={scorecard} initialExceptions={exceptions} />;
}
