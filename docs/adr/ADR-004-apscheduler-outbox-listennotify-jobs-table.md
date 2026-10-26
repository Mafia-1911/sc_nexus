# ADR-004: APScheduler + outbox + LISTEN/NOTIFY; jobs table

Status: accepted   Date: 2026-10-26

**Context:** schedules (GDELT 15 min … PortWatch daily), event fan-out between capabilities, and
heavy work that must not run inside API reads (02 §10, 04 §7).

**Decision:** The worker runs APScheduler. Domain writes that others care about insert an
`outbox_event` in the same transaction; the worker LISTENs and dispatches idempotent handlers.
`POST …` endpoints for heavy work create a `job` row plus a `job.queued` outbox event and
return 202 with a poll URL (implemented in M1; the worker consumes them in M2).

**Alternatives considered:** Celery/Redis or Kafka (extra services without measured throughput
needs).

**Consequences:** + no broker to run; + exactly the transactional guarantees the outbox gives.
− At-least-once delivery, so handlers must be idempotent. Revisit above ~50 jobs/s.
