# Phase 8 - Zalo OA pilot runbook

## Pham vi da ho tro

- Tin nhan van ban 1:1 gui den Zalo Official Account.
- Lien ket Zalo user voi tai khoan Academic Assistant bang `link <ma>` dung mot lan.
- Chuyen event da chuan hoa vao webhook noi bo co HMAC, PostgreSQL outbox va worker rieng.
- Reply text ve dung `external_user_id`; citation duoc doi thanh deep link web.
- Event trung duoc loai bang `(platform, external_event_id)`.

Khong ho tro attachment, voice, template message hay automation tai khoan Zalo ca nhan.
GMF co code gate de test fixture nhung `ZALO_GMF_ENABLED=false` cho toi khi Zalo cap
capability cho OA/App cu the.

## Cau hinh

```env
ZALO_CONNECTOR_ENABLED=false
ZALO_GMF_ENABLED=false
ZALO_OA_ACCESS_TOKEN=
ZALO_OA_ID=
ZALO_INTERNAL_API_BASE=http://127.0.0.1:8001
ZALO_CALLBACK_SECRET=
CONNECTOR_WEBHOOK_SECRET=
PUBLIC_WEB_URL=https://example.edu
```

Token OA va callback secret phai nam trong secret manager, khong commit/log. Endpoint
adapter phai dat sau HTTPS/reverse proxy va proxy phai gan header
`X-Nova-Callback-Secret`. Khi Zalo cung cap contract xac minh provider rieng cho OA da
duyet, bo sung validator do truoc khi bat production.

## Khoi dong pilot

1. Tao App + OA va xin quyen OpenAPI tren Zalo Developers.
2. Cau hinh callback HTTPS toi `POST /zalo/webhook` cua `run_zalo_webhook.py`.
3. Dat secret, giu `ZALO_GMF_ENABLED=false`, sau do bat `ZALO_CONNECTOR_ENABLED=true`.
4. Chay backend API.
5. Chay `python scripts/run_zalo_webhook.py` sau reverse proxy HTTPS.
6. Chay `python scripts/run_zalo_worker.py` nhu mot process always-on.
7. User tao code tren web cho platform `zalo`, sau do nhan OA: `link <ma>`.
8. Theo doi `/v1/connectors/events/audit`, queue retry/dead va kill switch.

## Gate GMF

Chi bat `ZALO_GMF_ENABLED=true` khi co du ca bon dieu kien:

- OA/App that hien thi capability GMF va duoc phep gui/nhan group message.
- Payload webhook that duoc luu thanh fixture da redact va parser contract pass.
- Da xac minh cach mention Nova va binding group-course bang owner RBAC.
- Test group privacy xac nhan khong nap mastery, deadline, cau sai va private memory.

Neu thieu mot gate, san pham chi ho tro OA 1:1 va dua link ve web/group.

## Rollback

Dat `ZALO_CONNECTOR_ENABLED=false`, dung webhook adapter va worker. Event da nhan van
nam trong audit/outbox; khong xoa de tranh xu ly trung khi khoi phuc.
