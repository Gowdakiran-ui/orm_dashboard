"""Guard: a task dispatched BY NAME must resolve to a queue some worker consumes.

celery_app.send_task(name, ...) ignores the queue on the task's decorator and only reads task_routes. A task missing from
task_routes lands in Celery's default "celery" queue. That is how seed_and_backfill_client (onboarding seeding + backfill) and the
counterfeit scans silently never ran. This test reads the source only (no Redis, no database):

  * every send_task(...) / _send(...) call under app/ with a constant task name,
  * task_routes in app/core/celery_app.py,
  * every `-Q` flag of every worker in docker-compose.yml,

and fails when a name-dispatched task would resolve to a queue no worker consumes.
"""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
COMPOSE = ROOT.parent / "docker-compose.yml"


def _task_routes() -> dict:
    from app.core.celery_app import celery_app
    routes = celery_app.conf.task_routes or {}
    return {name: (cfg.get("queue") if isinstance(cfg, dict) else None) for name, cfg in routes.items()}


def _consumed_queues() -> set:
    if not COMPOSE.exists():
        pytest.skip("docker-compose.yml not available (tests run outside the repo checkout)")
    queues = set()
    for m in re.finditer(r'"-Q",\s*"([^"]+)"', COMPOSE.read_text(encoding="utf-8")):
        queues.update(q.strip() for q in m.group(1).split(",") if q.strip())
    return queues


def _by_name_dispatches():
    """(file, line, task name or None, explicit queue or None) for each send_task / _send call."""
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if called not in ("send_task", "_send"):
                continue
            first = node.args[0]
            name = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            queue = None
            for kw in node.keywords:
                if kw.arg == "queue" and isinstance(kw.value, ast.Constant):
                    queue = kw.value.value
            found.append((path.relative_to(ROOT).as_posix(), node.lineno, name, queue, ast.unparse(first)))
    return found


def test_compose_parses_worker_queues():
    consumed = _consumed_queues()
    assert {"io_queue", "cpu_queue", "nlp_queue", "aggregation_queue", "pipeline_queue"} <= consumed
    # safety net: the default queue is consumed, so an unrouted task still runs instead of waiting forever
    assert "celery" in consumed


def test_every_name_dispatched_task_resolves_to_a_consumed_queue():
    routes, consumed, problems = _task_routes(), _consumed_queues(), []
    calls = _by_name_dispatches()
    assert any(n == "app.workers.backfill_tasks.seed_and_backfill_client" for _, _, n, _, _ in calls), "parser found no onboarding dispatch"
    for rel, line, name, queue, expr in calls:
        if name is None:
            # the generic wrapper (_send in backfill_tasks.py) passes **kwargs through; its callers are checked by name instead
            if queue is None and not (rel.endswith("backfill_tasks.py") and expr == "name"):
                problems.append(f"{rel}:{line} sends a non-constant task name ({expr}) with no explicit queue")
            elif queue is not None and queue not in consumed:
                problems.append(f"{rel}:{line} {expr} -> queue {queue!r} that no worker consumes")
            continue
        resolved = queue or routes.get(name) or "celery"
        if resolved not in consumed:
            problems.append(f"{rel}:{line} {name} -> {resolved!r}, a queue no worker consumes")
        if queue is None and name not in routes:
            problems.append(f"{rel}:{line} {name} has no entry in task_routes (it would use the default queue)")
    assert not problems, "\n".join(problems)


def test_onboarding_seeding_task_is_routed_to_io_queue():
    assert _task_routes().get("app.workers.backfill_tasks.seed_and_backfill_client") == "io_queue"
