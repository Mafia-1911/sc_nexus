"""Jobs (04 §7): `POST …` → 202 + job id; clients poll `GET /jobs/{id}`. The worker (M2)
consumes the `job.queued` outbox topic; until then jobs stay queued."""

from __future__ import annotations

from typing import Any

from cportal_core.enums import JobStatus
from cportal_core.ids import new_id
from cportal_core.models import Job, OutboxEvent
from sqlalchemy.orm import Session

from cportal_api.schemas import JobAccepted


def enqueue(session: Session, kind: str, params: dict[str, Any]) -> JobAccepted:
    job = Job(id=new_id(), kind=kind, params=params, status=JobStatus.QUEUED.value)
    session.add(job)
    session.add(OutboxEvent(topic="job.queued", payload={"job_id": str(job.id), "kind": kind}))
    session.commit()
    return JobAccepted(job_id=job.id, status=job.status, poll=f"/api/v1/jobs/{job.id}")
