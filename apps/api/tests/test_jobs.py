import json
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.jobs.runner import JobContext, JobRunner
from app.models import Job, JobKind, JobStatus, Video

TERMINAL = {"succeeded", "failed", "cancelled"}


def wait_for(client: TestClient, job_id: str, states: set[str] = TERMINAL, timeout: float = 5):  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in states:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job stuck in {job['status']}")


def runner(client: TestClient) -> JobRunner:
    return client.app.state.jobs  # type: ignore[attr-defined, no-any-return]


def start(client: TestClient, video_id: str, kind: str = "indexing"):  # type: ignore[no-untyped-def]
    return client.post(f"/v1/videos/{video_id}/jobs", json={"kind": kind})


def blocking_handler(started: threading.Event, release: threading.Event):  # type: ignore[no-untyped-def]
    def handler(ctx: JobContext) -> None:
        started.set()
        while not release.wait(0.01):
            ctx.checkpoint()

    return handler


def test_job_runs_to_completion(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    res = start(client, vid["id"])
    assert res.status_code == 202
    job = res.json()
    assert job["status"] in {"queued", "running", "succeeded"}
    done = wait_for(client, job["id"])
    assert done["status"] == "succeeded"
    assert done["progress"] == 1.0
    assert done["startedAt"] and done["finishedAt"]
    assert [j["id"] for j in client.get(f"/v1/videos/{vid['id']}/jobs").json()] == [job["id"]]


def test_start_validation(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    assert start(client, "nope").status_code == 404
    assert start(client, vid["id"], "probe").status_code == 400  # no handler registered
    assert start(client, vid["id"], "bogus").status_code == 422
    assert client.get("/v1/jobs/nope").status_code == 404
    assert client.get("/v1/videos/nope/jobs").status_code == 404


def test_active_job_is_reused(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    started, release = threading.Event(), threading.Event()
    runner(client).handlers[JobKind.indexing] = blocking_handler(started, release)
    try:
        first = start(client, vid["id"])
        assert first.status_code == 202
        assert started.wait(2)
        again = start(client, vid["id"])
        assert again.status_code == 200
        assert again.json()["id"] == first.json()["id"]
    finally:
        release.set()
    assert wait_for(client, first.json()["id"])["status"] == "succeeded"


def test_cancel_running_job(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    started, release = threading.Event(), threading.Event()
    runner(client).handlers[JobKind.indexing] = blocking_handler(started, release)
    job = start(client, vid["id"]).json()
    assert started.wait(2)
    assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code == 202
    assert wait_for(client, job["id"])["status"] == "cancelled"
    assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code == 409  # already finished
    assert client.post("/v1/jobs/nope/cancel").status_code == 404


def test_cancel_queued_job_never_runs(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    a, b = upload("a.mp4").json(), upload("b.mp4").json()
    started, release = threading.Event(), threading.Event()
    ran: list[str] = []

    def handler(ctx: JobContext) -> None:
        ran.append(ctx.video_id)
        blocking_handler(started, release)(ctx)

    runner(client).handlers[JobKind.indexing] = handler
    try:
        first = start(client, a["id"]).json()
        assert started.wait(2)
        queued = start(client, b["id"]).json()  # single worker: this one waits
        assert client.get(f"/v1/jobs/{queued['id']}").json()["status"] == "queued"
        assert client.post(f"/v1/jobs/{queued['id']}/cancel").status_code == 202
    finally:
        release.set()
    assert wait_for(client, first["id"])["status"] == "succeeded"
    assert wait_for(client, queued["id"])["status"] == "cancelled"
    assert ran == [a["id"]]


def test_failing_handler_marks_job_failed(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()

    def boom(_: JobContext) -> None:
        raise RuntimeError("detector crashed")

    runner(client).handlers[JobKind.indexing] = boom
    job = wait_for(client, start(client, vid["id"]).json()["id"])
    assert job["status"] == "failed"
    assert job["error"] == "detector crashed"


def test_events_stream_progress_until_done(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()

    def slowish(ctx: JobContext) -> None:
        for i in range(4):
            time.sleep(0.15)
            ctx.report((i + 1) / 4)

    runner(client).handlers[JobKind.indexing] = slowish
    job = start(client, vid["id"]).json()
    events: list[dict[str, Any]] = []
    with client.stream("GET", f"/v1/jobs/{job['id']}/events") as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        for line in res.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert events[-1]["status"] == "succeeded"
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert len(events) >= 2  # saw at least one intermediate update


def test_events_for_unknown_job(client: TestClient) -> None:
    assert client.get("/v1/jobs/nope/events").status_code == 404


def test_deleting_video_cancels_its_job(client: TestClient, upload) -> None:  # type: ignore[no-untyped-def]
    vid = upload().json()
    started, release = threading.Event(), threading.Event()
    runner(client).handlers[JobKind.indexing] = blocking_handler(started, release)
    job = start(client, vid["id"]).json()
    assert started.wait(2)
    assert client.delete(f"/v1/videos/{vid['id']}").status_code == 204
    assert client.get(f"/v1/jobs/{job['id']}").status_code == 404  # cascaded
    time.sleep(0.2)  # the worker notices the cancel and exits without errors
    assert not runner(client)._cancel_flags


def test_recover_fails_jobs_left_by_a_previous_process(client: TestClient) -> None:
    factory = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as s:
        v = Video(name="x", filename="x.mp4", stored_path="videos/x.mp4", size_bytes=1)
        v.jobs.append(Job(kind=JobKind.indexing, status=JobStatus.running))
        v.jobs.append(Job(kind=JobKind.probe, status=JobStatus.succeeded))
        s.add(v)
        s.commit()
        vid = v.id
    assert runner(client).recover() == 1
    jobs = {j["kind"]: j for j in client.get(f"/v1/videos/{vid}/jobs").json()}
    assert jobs["indexing"]["status"] == "failed"
    assert "restart" in jobs["indexing"]["error"]
    assert jobs["probe"]["status"] == "succeeded"


@pytest.mark.parametrize("value", [-1, 0.5, 2])
def test_progress_is_clamped(value: float) -> None:
    seen: list[float] = []
    ctx = JobContext("j", "v", threading.Event(), seen.append)
    ctx.report(value)
    assert seen == [min(max(value, 0.0), 1.0)]
