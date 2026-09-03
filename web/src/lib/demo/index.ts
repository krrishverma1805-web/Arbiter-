// A frozen snapshot of a real `arbiter run` (f7e810ba) — 1,672 records, the
// investigation agent pointed at gpt-4o. The hosted demo serves this so anyone
// can open the cockpit and see the complete agent working without a backend.
// Regenerate with `scripts/snapshot.sh` against a live API.
import datasets from "./datasets.json";
import drawers from "./drawers.json";
import exceptions from "./exceptions.json";
import run from "./run.json";
import runs from "./runs.json";
import scorecard from "./scorecard.json";
import specs from "./specs.json";
import stream from "./stream.json";
import verify from "./verify.json";

export const DEMO_RUN_ID = run.run_id;

export const demo = {
  specs,
  datasets,
  runs,
  run,
  scorecard,
  exceptions,
  verify,
  stream: stream as { records: number; frames: Array<Record<string, unknown>> },
  drawer: (id: string) =>
    (drawers as Record<string, unknown>)[id] ?? null,
};
