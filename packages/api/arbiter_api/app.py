"""The FastAPI app (docs/20 §1).

Routes:
  GET  /healthz  /readyz
  GET  /v1/specs                         list recon specs
  GET  /v1/datasets                      list available datasets
  POST /v1/runs                          {spec, dataset, no_ai?, model?} -> run
  GET  /v1/runs                          list runs
  GET  /v1/runs/{id}                     run detail (+ counts, terminal hash)
  GET  /v1/runs/{id}/scorecard           matching + agent scorecard
  GET  /v1/runs/{id}/matches             paginated
  GET  /v1/runs/{id}/exceptions          ranked by $ impact
  GET  /v1/runs/{id}/verify              recompute the hash chain
  GET  /v1/runs/{id}/replay              reproduce from the event log
  GET  /v1/runs/{id}/stream              SSE progress (tail of the event log)
  GET  /v1/exceptions/{run_id}/{id}      the evidence-drawer payload
  POST /v1/exceptions/{run_id}/{id}/resolve   {action, detail} -> RESOLUTION_APPLIED
  POST /v1/uploads                       multipart CSV/XLSX -> {upload_id}
  GET  /v1/jobs  GET /v1/jobs/{id}       async job status
  GET  /v1/me    GET /metrics            principal · Prometheus metrics

Every request is authenticated (API key; dev allows no key), tenant-scoped,
rate-limited, and logged with an X-Request-Id (arbiter_api.auth / ratelimit / obs).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from arbiter_engine.bench import score_run
from arbiter_engine.events.fold import fold_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import ChainBroken, EventStore
from arbiter_engine.money import format_minor
from arbiter_engine.replay import replay as do_replay
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from arbiter_api import __version__, obs
from arbiter_api.auth import current_principal, current_store, has_role, resolve, set_current
from arbiter_api.deps import DATASETS_DIR, ENV, SPECS_DIR
from arbiter_api.ratelimit import limiter

obs.configure()
obs.configure_sentry()
app = FastAPI(title="Arbiter API", version=__version__)
obs.configure_tracing(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(obs.middleware)


@app.get("/metrics")
def metrics():  # type: ignore[no-untyped-def]
    return obs.metrics_response()


_PUBLIC = ("/healthz", "/readyz", "/metrics", "/docs", "/openapi.json", "/redoc")


@app.middleware("http")
async def _gate(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.url.path in _PUBLIC:
        return await call_next(request)
    principal = resolve(request.headers.get("authorization"))
    if principal is None:
        return JSONResponse(
            status_code=401,
            content={"title": "unauthorized", "detail": "a valid API key is required"},
        )
    set_current(principal)

    is_write = request.method not in ("GET", "HEAD", "OPTIONS")
    ok, retry = limiter.allow(f"{principal.org_id}:{principal.subject}", write=is_write)
    if not ok:
        return JSONResponse(
            status_code=429,
            content={"title": "rate limited", "detail": f"retry in {retry:.1f}s"},
            headers={"Retry-After": str(int(retry) + 1)},
        )
    return await call_next(request)


def get_store() -> EventStore:
    """The store scoped to the current request's tenant."""
    return current_store()


def _require(role: str) -> None:
    if not has_role(role):
        raise _problem(403, "forbidden", f"this action requires the '{role}' role")


def _problem(status: int, title: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"title": title, "detail": detail})


# --------------------------------------------------------------------- health
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    try:
        get_store().runs()
        return {"ready": True, "env": ENV}
    except Exception as exc:  # noqa: BLE001
        raise _problem(503, "not ready", str(exc)) from exc


# --------------------------------------------------------------------- specs / datasets
@app.get("/v1/specs")
def list_specs() -> dict[str, Any]:
    return {"specs": [{"name": p.stem, "path": str(p)} for p in sorted(SPECS_DIR.glob("*.yaml"))]}


@app.get("/v1/datasets")
def list_datasets() -> dict[str, Any]:
    out = []
    for d in sorted(DATASETS_DIR.rglob("manifest.json")):
        try:
            out.append({"name": d.parent.name, "path": str(d.parent), **json.loads(d.read_text())})
        except json.JSONDecodeError:
            continue
    return {"datasets": out}


# --------------------------------------------------------------------- runs
class RunRequest(BaseModel):
    spec: str
    dataset: str
    no_ai: bool = False
    model: str | None = None
    rerun: bool = False


@app.get("/v1/me")
def whoami() -> dict[str, Any]:
    p = current_principal()
    return {"org_id": p.org_id, "subject": p.subject, "role": p.role}


@app.post("/v1/uploads", status_code=201)
async def create_upload(request: Request) -> dict[str, Any]:
    _require("analyst")
    from starlette.datastructures import UploadFile

    from arbiter_api.storage import UploadError, storage

    form = await request.form()
    files: list[tuple[str, bytes]] = []
    for value in form.getlist("files"):
        if isinstance(value, UploadFile):
            files.append((value.filename or "file", await value.read()))
    try:
        upload_id = storage.save(current_principal().org_id, files)
    except UploadError as e:
        raise _problem(422, "bad upload", str(e)) from e
    return {"upload_id": upload_id, "dataset": f"upload:{upload_id}", "files": len(files)}


@app.get("/v1/uploads")
def list_uploads() -> dict[str, Any]:
    from arbiter_api.storage import storage

    return {"uploads": storage.list_ids(current_principal().org_id)}


@app.post("/v1/runs", status_code=202)
def start_run(req: RunRequest, request: Request) -> Any:
    _require("analyst")
    from arbiter_api import idempotency, jobs
    from arbiter_api.resolve import resolve_dataset, resolve_spec

    org = current_principal().org_id
    idem = request.headers.get("idempotency-key", "")
    try:
        cached = idempotency.lookup(org, idem, req.model_dump())
    except ValueError as e:
        raise _problem(409, "idempotency conflict", str(e)) from e
    if cached is not None:
        return JSONResponse(status_code=cached[0], content=cached[1])

    if resolve_spec(req.spec) is None:
        raise _problem(404, "spec not found", req.spec)
    if resolve_dataset(org, req.dataset) is None:
        raise _problem(404, "dataset not found", req.dataset)

    job_id = jobs.enqueue(org, "run", req.model_dump())
    if jobs.ASYNC:
        body: dict[str, Any] = {"job_id": job_id, "status": "queued"}
        idempotency.store(org, idem, req.model_dump(), 202, body)
        return body
    job = jobs.get(job_id, org)
    assert job is not None
    jobs.run_one(job)
    done = jobs.get(job_id, org)
    if done is None or done.status != "done" or done.run_id is None:
        raise _problem(500, "run failed", (done.error if done else "") or "unknown error")
    body = {"job_id": job_id, **_run_summary(done.run_id)}
    idempotency.store(org, idem, req.model_dump(), 202, body)
    return body


@app.get("/v1/jobs")
def list_jobs() -> dict[str, Any]:
    from arbiter_api import jobs

    org = current_principal().org_id
    return {
        "jobs": [
            {"id": j.id, "kind": j.kind, "status": j.status, "run_id": j.run_id, "error": j.error}
            for j in jobs.recent(org)
        ]
    }


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: int) -> dict[str, Any]:
    from arbiter_api import jobs

    j = jobs.get(job_id, current_principal().org_id)
    if j is None:
        raise _problem(404, "job not found", str(job_id))
    return {
        "id": j.id,
        "kind": j.kind,
        "status": j.status,
        "attempts": j.attempts,
        "run_id": j.run_id,
        "error": j.error,
    }


@app.get("/v1/runs")
def list_runs() -> dict[str, Any]:
    store = get_store()
    runs = []
    for rid in store.runs():
        proj = fold_run(store, rid)
        runs.append(
            {
                "run_id": rid,
                "status": proj.status,
                "records": proj.record_count,
                "matches": len(proj.matches),
                "exceptions": len(proj.exceptions),
            }
        )
    return {"runs": runs}


@app.get("/v1/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    return _run_summary(run_id)


@app.get("/v1/runs/{run_id}/scorecard")
def run_scorecard(run_id: str) -> dict[str, Any]:
    from arbiter_api import cache

    store = get_store()
    proj = _proj_or_404(run_id)
    dataset_dir = _dataset_dir_for(store, run_id)
    if dataset_dir is None:
        raise _problem(422, "no dataset", "cannot locate the dataset for this run")

    def _compute() -> dict[str, Any]:
        agent_events = [
            (t, p) for t, p in store.iter_payloads(run_id) if str(t).startswith("AGENT_")
        ]
        wallclock = 0
        for ev in store.events(run_id):
            if ev.type == EventType.RUN_COMPLETED:
                wallclock = int(json.loads(ev.meta).get("wallclock_ms", 0))
        card = score_run(
            proj,
            dataset_dir,
            spec_name=(proj.config_hash or "spec"),
            wallclock_ms=wallclock,
            replay_hash_match=store.verify(run_id)["intact"],
            agent_events=agent_events,
        )
        return card.to_dict()

    if not proj.completed:
        return _compute()
    thash = store.verify(run_id)["terminal_hash"]
    org = current_principal().org_id
    return cast(
        dict[str, Any],
        cache.get_or_set(
            cache.scoped(org, "scorecard", run_id, thash), cache.default_ttl(), _compute
        ),
    )


@app.get("/v1/runs/{run_id}/matches")
def run_matches(run_id: str, limit: int = Query(100, le=500), offset: int = 0) -> dict[str, Any]:
    proj = _proj_or_404(run_id)
    rows = [m.model_dump(mode="json") for m in proj.matches[offset : offset + limit]]
    return {"total": len(proj.matches), "matches": rows}


@app.get("/v1/runs/{run_id}/exceptions")
def run_exceptions(
    run_id: str, category: str | None = None, status: str | None = None
) -> dict[str, Any]:
    proj = _proj_or_404(run_id)
    excs = proj.exceptions
    if category:
        excs = [e for e in excs if e.category == category]
    if status:
        excs = [e for e in excs if e.status == status]
    return {
        "total": len(excs),
        "exceptions": [
            {
                **e.model_dump(mode="json"),
                "impact_display": format_minor(e.amount_impact_minor),
            }
            for e in excs
        ],
    }


@app.get("/v1/runs/{run_id}/verify")
def run_verify(run_id: str) -> dict[str, Any]:
    try:
        return get_store().verify(run_id)
    except ChainBroken as exc:
        raise _problem(409, "chain broken", str(exc)) from exc


@app.get("/v1/runs/{run_id}/replay")
def run_replay(run_id: str) -> dict[str, Any]:
    try:
        res = do_replay(get_store(), run_id)
    except ChainBroken as exc:
        raise _problem(409, "chain broken", str(exc)) from exc
    return {
        "run_id": res.run_id,
        "intact": res.intact,
        "events": res.events,
        "terminal_hash": res.terminal_hash,
        "ok": res.ok,
    }


def _stream_frame(ev: Any) -> dict[str, Any]:
    """A compact, UI-shaped view of one event for the streaming investigation
    view (docs/28 §5) — enough to choreograph the agent's thinking, no more."""
    p = json.loads(ev.payload)
    base = {"seq": ev.seq, "type": ev.type, "ts": ev.ts}
    if ev.type == EventType.AGENT_INVESTIGATION_STARTED:
        return {**base, "exception_id": p.get("exception_id"), "category": p.get("category")}
    if ev.type == EventType.AGENT_INTERACTION:
        return {
            **base,
            "exception_id": p.get("exception_id"),
            "turn": p.get("turn"),
            "text": p.get("text", ""),
            "tool_calls": [tc.get("name") for tc in p.get("tool_calls", [])],
            "stop_reason": p.get("stop_reason"),
        }
    if ev.type == EventType.AGENT_PROPOSAL_CREATED:
        g = p.get("grounding") or {}
        return {
            **base,
            "exception_id": p.get("exception_id"),
            "category": p.get("category"),
            "explanation": p.get("explanation", ""),
            "grounded_confidence": g.get("grounded_confidence"),
        }
    if ev.type == EventType.AGENT_ESCALATED:
        return {
            **base,
            "exception_id": p.get("exception_id"),
            "question": p.get("question", ""),
            "reason": p.get("reason"),
        }
    if ev.type == EventType.EXCEPTION_OPENED:
        exc = p.get("exception", {})
        return {
            **base,
            "exception_id": exc.get("id"),
            "category": exc.get("category"),
            "impact_minor": exc.get("amount_impact_minor"),
        }
    if ev.type == EventType.RUN_COMPLETED:
        return {**base, "counts": p.get("counts", {})}
    return base


@app.get("/v1/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request) -> StreamingResponse:
    store = get_store()
    try:
        after = int(request.headers.get("last-event-id", "-1"))
    except ValueError:
        after = -1

    async def gen() -> Any:
        seen = 0
        for tick in range(1200):  # ~120s cap
            events = store.events(run_id)
            for ev in events[seen:]:
                if ev.seq <= after:
                    continue
                frame = _stream_frame(ev)
                yield f"id: {ev.seq}\nevent: {ev.type}\ndata: {json.dumps(frame)}\n\n"
            seen = len(events)
            # the pipeline is done once RUN_COMPLETED is on the log; later events
            # (resolutions on the same run) don't reopen it.
            if any(e.type == EventType.RUN_COMPLETED for e in events):
                yield "event: done\ndata: {}\n\n"
                return
            if tick % 100 == 0:  # heartbeat so proxies keep the connection open
                yield ": ping\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.websocket("/v1/runs/{run_id}/ws")
async def run_ws(ws: WebSocket, run_id: str) -> None:
    """Live presence + fan-out for the cockpit (docs/28 §5). Query params:
    `key` (API key in prod), `name` (display name). Messages out:
    `{type:"presence",viewers:[…]}` and `{type:"exception_resolved",…}`."""
    import uuid as _uuid

    from arbiter_api.auth import resolve
    from arbiter_api.presence import _Member, hub

    key = ws.query_params.get("key")
    principal = resolve(f"Bearer {key}" if key else None)
    if principal is None:
        await ws.close(code=1008)
        return
    await ws.accept()
    viewer_id = _uuid.uuid4().hex[:8]
    name = (ws.query_params.get("name") or principal.subject)[:40]

    async def send(msg: dict[str, Any]) -> None:
        await ws.send_json(msg)

    member = _Member(viewer_id=viewer_id, name=name, send=send)
    await ws.send_json({"type": "hello", "viewer_id": viewer_id})
    await hub.join(principal.org_id, run_id, member)
    try:
        while True:
            await ws.receive_text()  # client keepalives; we don't act on them
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(principal.org_id, run_id, viewer_id)


# --------------------------------------------------------------------- exceptions
@app.get("/v1/exceptions/{run_id}/{exception_id}")
def exception_detail(run_id: str, exception_id: str) -> dict[str, Any]:
    proj = _proj_or_404(run_id)
    exc = next((e for e in proj.exceptions if e.id == exception_id), None)
    if exc is None:
        raise _problem(404, "exception not found", exception_id)
    recs = {r.id: r for r in proj.records}
    records = [
        {
            **recs[rid].model_dump(mode="json"),
            "amount_display": format_minor(recs[rid].amount_minor),
        }
        for rid in exc.record_ids
        if rid in recs
    ]
    utrs = {
        recs[rid].external_ids.get("settlement_utr")
        for rid in exc.record_ids
        if rid in recs and recs[rid].external_ids.get("settlement_utr")
    }
    decomps = [d.model_dump(mode="json") for d in proj.decompositions if d.settlement_utr in utrs]

    # the agent's step-by-step trace for this exception, for the cockpit's
    # streaming investigation view (docs/28 §5)
    trace: list[dict[str, Any]] = []
    for t, p in get_store().iter_payloads(run_id):
        if t == EventType.AGENT_INTERACTION and p.get("exception_id") == exception_id:
            trace.append(
                {
                    "turn": p.get("turn"),
                    "text": p.get("text", ""),
                    "tool_calls": [tc.get("name") for tc in p.get("tool_calls", [])],
                    "stop_reason": p.get("stop_reason"),
                }
            )

    return {
        "exception": exc.model_dump(mode="json"),
        "records": records,
        "decompositions": decomps,
        "candidates": [c.model_dump(mode="json") for c in exc.candidates],
        "agent_proposal": exc.agent_proposal,
        "agent_escalation": exc.agent_escalation,
        "agent_trace": trace,
    }


class ResolveRequest(BaseModel):
    action: str
    detail: str = ""
    actor: str = "human:api"
    category: str | None = None


@app.post("/v1/exceptions/{run_id}/{exception_id}/resolve")
def resolve_exception(run_id: str, exception_id: str, req: ResolveRequest, request: Request) -> Any:
    _require("analyst")
    from arbiter_api import idempotency

    org = current_principal().org_id
    idem = request.headers.get("idempotency-key", "")
    key_payload = {"run_id": run_id, "exception_id": exception_id, **req.model_dump()}
    try:
        cached = idempotency.lookup(org, idem, key_payload)
    except ValueError as e:
        raise _problem(409, "idempotency conflict", str(e)) from e
    if cached is not None:
        return JSONResponse(status_code=cached[0], content=cached[1])

    store = get_store()
    proj = _proj_or_404(run_id)
    exc = next((e for e in proj.exceptions if e.id == exception_id), None)
    if exc is None:
        raise _problem(404, "exception not found", exception_id)
    store.append(
        run_id,
        EventType.RESOLUTION_APPLIED,
        {
            "exception_id": exception_id,
            "action": req.action,
            "detail": req.detail,
            "actor": req.actor,
            "prior_status": exc.status,
            "category": req.category,
        },
    )
    from arbiter_engine.learn import draft_rule_from_resolution

    draft = draft_rule_from_resolution(exc, req.action, category=req.category)
    if draft is not None:
        store.append(run_id, EventType.RULE_DRAFTED, draft)

    try:  # opt-in global pattern library (docs/28 §3 item 15) — no-op unless enabled
        from arbiter_engine.learn.global_patterns import contribute

        recs = [r for r in proj.records if r.id in exc.record_ids]
        contribute(org, exc, recs, req.action)
    except Exception:  # noqa: BLE001
        pass
    body = {
        "ok": True,
        "exception_id": exception_id,
        "action": req.action,
        "drafted_rule": draft,
    }
    idempotency.store(org, idem, key_payload, 200, body)

    from arbiter_api.presence import hub

    hub.broadcast_soon(
        org,
        run_id,
        {
            "type": "exception_resolved",
            "exception_id": exception_id,
            "action": req.action,
            "by": req.actor,
        },
    )
    return body


@app.get("/v1/runs/{run_id}/rules/pending")
def pending_rules_route(run_id: str) -> dict[str, Any]:
    from arbiter_engine.learn import pending_rules

    _proj_or_404(run_id)
    spec_path = _spec_path_for(get_store(), run_id)
    if spec_path is None:
        raise _problem(422, "no spec", "cannot locate the spec for this run")
    return {"pending": pending_rules(get_store(), run_id, spec_path)}


class MergeRequest(BaseModel):
    rule_ids: list[str] | None = None
    approved_by: str = "human:api"


@app.post("/v1/runs/{run_id}/rules/merge")
def merge_rules_route(run_id: str, req: MergeRequest) -> dict[str, Any]:
    _require("admin")
    from arbiter_engine.learn import merge_rules

    _proj_or_404(run_id)
    spec_path = _spec_path_for(get_store(), run_id)
    if spec_path is None:
        raise _problem(422, "no spec", "cannot locate the spec for this run")
    return merge_rules(get_store(), run_id, spec_path, req.rule_ids, approved_by=req.approved_by)


# --------------------------------------------------------------------- helpers
def _proj_or_404(run_id: str):  # type: ignore[no-untyped-def]
    proj = fold_run(get_store(), run_id)
    if not proj.started:
        raise _problem(404, "run not found", run_id)
    return proj


def _run_summary(run_id: str) -> dict[str, Any]:
    store = get_store()
    proj = _proj_or_404(run_id)
    v = store.verify(run_id)
    return {
        "run_id": run_id,
        "status": proj.status,
        "records": proj.record_count,
        "by_source": proj.by_source(),
        "matches": len(proj.matches),
        "matched_records": len(proj.matched_record_ids),
        "exceptions": len(proj.exceptions),
        "quarantined": proj.quarantined,
        "pii_dropped": proj.pii_dropped,
        "events": v["events"],
        "terminal_hash": v["terminal_hash"],
    }


def _spec_path_for(store: Any, run_id: str) -> Path | None:
    name = None
    for t, p in store.iter_payloads(run_id):
        if t == EventType.RUN_STARTED:
            name = p["spec_name"]
            break
    if name is None:
        return None
    cand = SPECS_DIR / f"{name}.yaml"
    return cand if cand.exists() else None


def _dataset_dir_for(store: Any, run_id: str) -> Path | None:
    # the run doesn't store the dataset path; find the manifest whose hash matches
    dh = None
    for t, p in store.iter_payloads(run_id):
        if t == EventType.RUN_STARTED:
            dh = p["dataset_hash"]
            break
    if dh is None:
        return None
    from arbiter_engine.run import _dataset_hash

    for manifest in DATASETS_DIR.rglob("manifest.json"):
        d = manifest.parent
        if any(d.glob("*.csv")) and _dataset_hash(d) == dh:
            return d
    return None
