# Discord pilot runbook

## Trang thai

Code pilot da san sang, mac dinh tat. Can Discord Bot Token that va mot server test rieng
truoc khi bat pilot.

## 1. Tao Discord application

1. Tao application va bot trong Discord Developer Portal.
2. Khong dung user token/self-bot.
3. Cai app vao server pilot voi scope `bot` va `applications.commands`.
4. Quyen toi thieu: View Channels, Send Messages va Read Message History.
5. Khong bat privileged `MESSAGE_CONTENT` intent cho mention-only pilot. Discord van cap
   content cua DM va message direct-mention bot.

Tai lieu chinh thuc:

- https://docs.discord.com/developers/events/gateway
- https://docs.discord.com/developers/events/gateway-events
- https://docs.discord.com/developers/resources/message

## 2. Cau hinh secret

```env
DISCORD_CONNECTOR_ENABLED=true
DISCORD_BOT_TOKEN=<secret>
DISCORD_BOT_USER_ID=<optional>
CONNECTOR_WEBHOOK_SECRET=<random-secret-rieng>
DISCORD_INTERNAL_API_BASE=http://127.0.0.1:8001
PUBLIC_WEB_URL=https://your-web.example
```

Token chi dat trong secret manager/env cua gateway worker, khong dua vao frontend, log
hoac commit.

## 3. Chay ba process

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
.\.venv\Scripts\python.exe scripts\run_discord_gateway.py
.\.venv\Scripts\python.exe scripts\run_discord_worker.py
```

Gateway chi nhan event va enqueue nhanh. Worker moi goi Nova va Discord REST; restart
Gateway khong lam mat event da ghi vao PostgreSQL.

## 4. Lien ket danh tinh

1. User dang nhap web va tao link code qua `POST /v1/connectors/link-code` voi platform
   `discord` (UI link se bo sung khi pilot duoc duyet).
2. User DM bot: `link <code>` trong vong 5 phut.
3. Code chi dung mot lan; Discord ID khong the chuyen sang tai khoan khac bang code moi.

## 5. Bind lop

Giang vien da link identity go slash command ngay trong kenh:

```text
/nova-bind course_code:CS101-PY
```

Backend chi chap nhan owner cua lop hoac admin. Binding mac dinh `MENTION_ONLY`.

## 6. Test pilot

- Tin nhan thuong trong group: Nova im lang.
- `@Nova Python la gi?`: Nova reply dung message, khong ping lai user/everyone/role.
- DM Nova: tra loi duoc sau khi link identity.
- Citation mo ve document viewer web.
- Revoke identity tren web: message moi bi 403/khong enqueue.
- Gui lai cung Discord message ID: chi co mot event va mot outbox job.

## 7. Rollback va su co

1. Dat `DISCORD_CONNECTOR_ENABLED=false`.
2. Dung Gateway va worker; backend/web tiep tuc hoat dong binh thuong.
3. Xem `GET /v1/connectors/events/audit` bang admin de kiem tra RETRY/DEAD.
4. Revoke bot token ngay neu nghi bi lo; cap token moi trong secret manager.
5. Unbind channel neu bind nham lop.

## Gate pilot that

- Mot server test, mot lop, 1-2 tuan.
- Cross-user/cross-course leak = 0.
- Duplicate reply = 0.
- Dead-letter duoc dieu tra, khong tu retry vo han.
- Chi phi va latency chap nhan duoc truoc khi mo server tiep theo.
