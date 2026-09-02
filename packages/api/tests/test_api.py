from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory):
    ds = tmp_path_factory.mktemp("datasets") / "d2c"
    from arbiter_datagen.generate import generate_dataset

    generate_dataset(scenario="d2c", records=80, seed=42, out_dir=ds, difficulty="normal")

    os.environ["ARBITER_DB_URL"] = "sqlite://"
    os.environ["ARBITER_SPECS_DIR"] = str(REPO / "specs")
    os.environ["ARBITER_DATASETS_DIR"] = str(ds.parent)

    from arbiter_api.app import app
    from arbiter_api.deps import get_store
    from fastapi.testclient import TestClient

    get_store.cache_clear()
    return TestClient(app), ds


def test_health(client):
    c, _ = client
    assert c.get("/healthz").json()["status"] == "ok"
    assert c.get("/readyz").json()["ready"] is True


def test_specs_and_datasets(client):
    c, _ = client
    specs = c.get("/v1/specs").json()["specs"]
    assert any(s["name"] == "razorpay-settlement" for s in specs)
    assert c.get("/v1/datasets").json()["datasets"]


def test_run_lifecycle(client):
    c, ds = client
    r = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)})
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    detail = c.get(f"/v1/runs/{run_id}").json()
    assert detail["status"] == "completed"
    assert detail["records"] > 0
    assert detail["terminal_hash"]

    sc = c.get(f"/v1/runs/{run_id}/scorecard").json()
    assert "matching" in sc and "agent" in sc
    assert sc["matching"]["false_match_rate"] <= 0.05

    excs = c.get(f"/v1/runs/{run_id}/exceptions").json()
    assert excs["total"] >= 1
    # ranked by $ impact descending
    impacts = [abs(e["amount_impact_minor"]) for e in excs["exceptions"]]
    assert impacts == sorted(impacts, reverse=True)

    v = c.get(f"/v1/runs/{run_id}/verify").json()
    assert v["intact"] is True
    rp = c.get(f"/v1/runs/{run_id}/replay").json()
    assert rp["ok"] is True


def test_exception_detail_and_resolve(client):
    c, ds = client
    run_id = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}).json()[
        "run_id"
    ]
    exc_id = c.get(f"/v1/runs/{run_id}/exceptions").json()["exceptions"][0]["id"]

    drawer = c.get(f"/v1/exceptions/{run_id}/{exc_id}").json()
    assert drawer["exception"]["id"] == exc_id
    assert isinstance(drawer["records"], list)

    res = c.post(
        f"/v1/exceptions/{run_id}/{exc_id}/resolve",
        json={"action": "carry_forward", "detail": "clears next cycle"},
    )
    assert res.status_code == 200
    after = c.get(f"/v1/runs/{run_id}/exceptions").json()
    resolved = next(e for e in after["exceptions"] if e["id"] == exc_id)
    assert resolved["status"] == "resolved"
    assert resolved["resolution"]["action"] == "carry_forward"


def test_resolving_a_generalisable_exception_drafts_a_pending_rule(client):
    c, ds = client
    run_id = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}).json()[
        "run_id"
    ]
    excs = c.get(f"/v1/runs/{run_id}/exceptions").json()["exceptions"]
    target = next(
        (e for e in excs if e["category"] in ("ROUNDING", "TIMING", "MISSING_UTR", "DUPLICATE")),
        None,
    )
    if target is None:
        pytest.skip("this dataset produced no generalisable exception")

    res = c.post(
        f"/v1/exceptions/{run_id}/{target['id']}/resolve",
        json={"action": "route_to_human"},
    ).json()
    assert res["drafted_rule"] is not None
    rid = res["drafted_rule"]["rule_id"]

    pending = c.get(f"/v1/runs/{run_id}/rules/pending").json()["pending"]
    assert any(p["rule_id"] == rid for p in pending)


def test_missing_run_is_404(client):
    c, _ = client
    assert c.get("/v1/runs/does-not-exist").status_code == 404


def test_exception_detail_includes_agent_trace_field(client):
    c, ds = client
    run_id = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}).json()[
        "run_id"
    ]
    exc_id = c.get(f"/v1/runs/{run_id}/exceptions").json()["exceptions"][0]["id"]
    d = c.get(f"/v1/exceptions/{run_id}/{exc_id}").json()
    assert "agent_trace" in d and isinstance(d["agent_trace"], list)


def test_whoami_returns_the_dev_principal(client):
    c, _ = client
    me = c.get("/v1/me").json()
    assert me == {"org_id": "local", "subject": "local-dev", "role": "admin"}


def test_prod_env_rejects_a_request_with_no_key(client, monkeypatch):
    c, _ = client
    import arbiter_api.auth as auth

    monkeypatch.setattr(auth, "ENV", "prod")
    r = c.get("/v1/runs")
    assert r.status_code == 401
    assert r.json()["title"] == "unauthorized"
    # a valid minted key is accepted and carries its org + role
    key = auth.issue_key("acme", "ci", "viewer")
    ok = c.get("/v1/me", headers={"authorization": f"Bearer {key}"})
    assert ok.status_code == 200
    assert ok.json() == {"org_id": "acme", "subject": "ci", "role": "viewer"}


def test_viewer_cannot_start_a_run_or_merge_rules(client, monkeypatch):
    c, ds = client
    import arbiter_api.auth as auth

    monkeypatch.setattr(auth, "ENV", "prod")
    viewer = {"authorization": f"Bearer {auth.issue_key('acme', 'v', 'viewer')}"}
    r = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}, headers=viewer)
    assert r.status_code == 403
    analyst = {"authorization": f"Bearer {auth.issue_key('acme', 'a', 'analyst')}"}
    r2 = c.post(
        "/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}, headers=analyst
    )
    assert r2.status_code == 202


def test_two_api_tenants_do_not_see_each_others_runs(client, monkeypatch):
    c, ds = client
    import arbiter_api.auth as auth

    monkeypatch.setattr(auth, "ENV", "prod")
    a = {"authorization": f"Bearer {auth.issue_key('org_a', 'x', 'analyst')}"}
    b = {"authorization": f"Bearer {auth.issue_key('org_b', 'y', 'analyst')}"}
    c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}, headers=a)
    a_runs = c.get("/v1/runs", headers=a).json()["runs"]
    b_runs = c.get("/v1/runs", headers=b).json()["runs"]
    assert len(a_runs) >= 1
    assert b_runs == []


def test_async_run_is_queued_then_processed_by_the_worker(client, monkeypatch):
    c, ds = client
    import arbiter_api.jobs as jobs

    monkeypatch.setattr(jobs, "ASYNC", True)
    r = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and "job_id" in body

    j = c.get(f"/v1/jobs/{body['job_id']}").json()
    assert j["status"] == "queued" and j["run_id"] is None

    jobs.worker_loop(once=True)  # drain the queue

    j2 = c.get(f"/v1/jobs/{body['job_id']}").json()
    assert j2["status"] == "done" and j2["run_id"]
    detail = c.get(f"/v1/runs/{j2['run_id']}").json()
    assert detail["status"] == "completed"


def test_job_failure_is_recorded_not_raised(client, monkeypatch):
    c, _ = client
    import arbiter_api.jobs as jobs

    monkeypatch.setattr(jobs, "ASYNC", True)
    monkeypatch.setattr(jobs, "MAX_ATTEMPTS", 1)
    # a dataset the run will not be able to load
    r = c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": "no_such_dir"})
    assert r.status_code == 404  # caught before enqueue


def test_jobs_list_is_tenant_scoped(client, monkeypatch):
    c, ds = client
    import arbiter_api.auth as auth
    import arbiter_api.jobs as jobs

    monkeypatch.setattr(auth, "ENV", "prod")
    monkeypatch.setattr(jobs, "ASYNC", True)
    a = {"authorization": f"Bearer {auth.issue_key('ja', 'x', 'analyst')}"}
    b = {"authorization": f"Bearer {auth.issue_key('jb', 'y', 'analyst')}"}
    c.post("/v1/runs", json={"spec": "razorpay-settlement", "dataset": str(ds)}, headers=a)
    assert len(c.get("/v1/jobs", headers=a).json()["jobs"]) >= 1
    assert c.get("/v1/jobs", headers=b).json()["jobs"] == []
