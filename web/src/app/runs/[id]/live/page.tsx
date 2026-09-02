import { LiveRun } from "@/components/LiveRun";

export const dynamic = "force-dynamic";

export default async function LiveRunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LiveRun runId={id} />;
}
