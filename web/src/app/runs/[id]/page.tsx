import { api } from "@/lib/api";
import { Cockpit } from "@/components/Cockpit";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [run, scorecard, exceptions] = await Promise.all([
    api.run(id),
    api.scorecard(id).catch(() => null),
    api.exceptions(id).then((r) => r.exceptions),
  ]);

  return <Cockpit runId={id} run={run} scorecard={scorecard} initialExceptions={exceptions} />;
}
