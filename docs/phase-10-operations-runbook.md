# Phase 10 - Operations, retention va rollout

## Cau hinh

```env
CONNECTOR_EVENT_RETENTION_DAYS=7
CONNECTOR_PROCESSING_TIMEOUT_SECONDS=300
NOVA_ROLLOUT_PERCENT=5
NOVA_ROLLBACK_DEAD_JOBS_THRESHOLD=5
NOVA_ROLLBACK_P95_LATENCY_MS=20000
```

`NOVA_ROLLOUT_PERCENT` chia cohort on dinh theo `user_id`; mot user khong bi doi qua
lai agentic/legacy giua cac request. `0` la rollback toan bo, `100` la rollout toan bo.

## Endpoint admin

- `GET /v1/operations/status`: queue, dead jobs, oldest pending, p95 chat latency,
  rollout percent va rollback recommendation.
- `GET /v1/operations/retention/preview`: chi dem ban ghi se xoa, khong thay doi DB.
- `POST /v1/operations/retention/run`: xoa event terminal/link code cu va recover job
  `PROCESSING` bi ket. Chi ADMIN duoc goi.

## Quy trinh rollout

1. Chay benchmark va security integration.
2. Dat 5%, theo doi it nhat mot chu ky luu luong du dai.
3. Neu khong co leak/fallback tang va p95 trong nguong, tang 25%.
4. Lap lai human review truoc 100%.
5. Neu status bao rollback hoac co privacy incident, dat `NOVA_ROLLOUT_PERCENT=0`
   va restart backend. Connector co kill switch rieng va van giu tat neu chua live pilot.

Khong tu dong xoa event `RECEIVED/RETRY/PENDING`; retention chi xoa event terminal
`PROCESSED/DEAD` cu hon cutoff.
