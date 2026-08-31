# Ke hoach phat trien Nova Agentic RAG, Personalization va Omnichannel

> Trang thai: **DA HOAN THANH CODE PHASE 1-8, 10-11; PHASE 9 TAM HOAN CHO CREDENTIALS**  
> Cap nhat: 2026-08-31  
> Pham vi: Agentic RAG 2-step, kien thuc pho thong, ca nhan hoa, Discord, Zalo, Messenger

## 1. Muc tieu

Xay Nova thanh mot tro ly hoc thuat co hoi thoai tu nhien hon nhung van dam bao:

- Noi dung theo mon hoc duoc neo vao tai lieu da duyet va co citation.
- Kien thuc pho thong an toan nhu `1 + 1`, dinh nghia co ban, chitchat van duoc tra loi.
- Nova biet nen tra loi **dieu gi** truoc khi quyet dinh **noi nhu the nao**.
- Cach giai thich phu hop voi trinh do, lich su hoc va so thich cua tung nguoi.
- Cung mot Nova core co the phuc vu Web, Discord, Zalo va Messenger.
- Du lieu ca nhan khong bi lo trong group chat hoac sang tai khoan khac.
- Co fallback, eval, audit va rollout tung buoc; khong thay toan bo pipeline trong mot lan.

## 2. Ngoai pham vi giai doan dau

- Khong cho agent tu do lap vo han hoac tu goi tool khong gioi han.
- Khong cho Nova tu dong ghi nho moi noi dung nguoi dung noi.
- Khong tu dong gui diem, mastery, bai chua nop vao group chat.
- Khong dong bo toan bo lich su group ben thu ba vao kho du lieu hoc tap.
- Khong thay PostgreSQL/pgvector bang vector store ben ngoai khi chua co so lieu chung minh can thiet.
- Khong trien khai voice tren Discord/Zalo/Messenger trong phase dau.
- Khong cam ket `@Nova` tren nen tang neu API chinh thuc/tai khoan ung dung chua duoc cap quyen.

## 3. Hien trang he thong

### 3.1 RAG hien tai

```text
Input
  -> Guardrail rule + Moderation
  -> Router Agent
  -> Query rewrite/khoi phuc dau (neu can)
  -> Embedding
  -> Vector search + PostgreSQL Full-text search
  -> RRF
  -> Top chunks
  -> Build system prompt
  -> Mot lan goi LLM sinh cau tra loi
  -> Citation + luu Message
```

Day la **Hybrid RAG tuyen tinh**, chua phai Agentic RAG 2-step. Thanh phan tot nen giu:

- ACL loc tai lieu ngay trong SQL.
- Tai lieu phai `APPROVED` moi duoc retrieval.
- Vector + full-text + RRF phu hop voi tieng Viet va tu khoa ky thuat.
- Router da co `RAG_QUESTION`, `SOCRATIC_REQUEST`, `CHITCHAT`, `OFF_TOPIC`,
  `GENERAL_KNOWLEDGE`, `SYSTEM_QUESTION`, `ACTION_REQUEST`.
- SSE streaming, citation verifier, audit tool va role policy da ton tai.
- `StudentContext` da co mastery, bai tap, cau sai, deadline.

### 3.2 Van de can sua truoc Agentic RAG

Frontend hien ep tab Hoi dap cua sinh vien thanh `RAG_QUESTION`. Vi vay router khong co co
hoi chon `GENERAL_KNOWLEDGE`; cau `1 + 1 bang may?` van bi day vao retrieval. Can doi:

- Chi force `SOCRATIC_REQUEST` khi nguoi dung chu dong chon tab Gia su.
- Tab Hoi dap gui `force_category = null`, de backend router quyet dinh.
- Instructor van de router tu nhan dien `ACTION_REQUEST`.

## 4. Kien truc dich

```text
Web / Discord / Zalo / Messenger
                 |
          Channel Adapter
                 |
      Normalize + Identity Link
                 |
 Guardrail + Role + Privacy Scope
                 |
          Intent Router
       /       |        \
 General   Academic    Action
 answer      query      tools
              |
      Bounded Retrieval Agent
              |
       STEP 1: Evidence Planner
              |
      Policy/Schema Validator
              |
       STEP 2: Response Composer
              |
 Citation verifier + Output guardrail
              |
         Channel Formatter
```

### Nguyen tac “agentic”

Agentic o day co nghia la model duoc quyen lua chon chien luoc tim kiem va lap ke hoach
tra loi trong mot pham vi **bi gioi han**, khong co nghia la vong lap tu do:

- Toi da 2 dot retrieval.
- Toi da 3 truy van con trong moi dot.
- Chi doc tai lieu ma ACL backend cho phep.
- Planner khong duoc thuc thi tool ghi du lieu.
- Composer khong duoc them claim moi ngoai plan.
- Moi nhanh co timeout va fallback ve pipeline cu.

## 5. Phan loai che do tra loi

Them `answer_mode` doc lap voi `intent`:

| answer_mode | Nguon | Khi dung | Citation |
|---|---|---|---|
| `grounded` | Tai lieu lop | Noi dung mon hoc, quy dinh, de/bai tap | Bat buoc cho claim dung tai lieu |
| `general` | Kien thuc pho thong cua model | 1+1, chitchat, kien thuc co ban an toan | Khong gia citation |
| `mixed` | Tai lieu + kien thuc pho thong | Tai lieu co mot phan, can bo sung nen | Danh dau ro phan nao tu tai lieu |
| `socratic` | Tai lieu + learner model | Nguoi hoc can goi mo | Citation khi dung tai lieu |
| `refuse` | Khong tra loi noi dung | Injection, doc hai, lech muc dich | Khong |
| `action` | Tool co RBAC | Xem/tac dong du lieu he thong | Audit, xac nhan neu ghi |

Khong cho `mixed/general` doi voi:

- Dap an bai tap/de thi chua cong bo.
- Diem, deadline, quy dinh lop.
- Thong tin ca nhan hoac thong tin quan tri.
- Cau hoi ma mot cau tra loi chung co the mau thuan chinh sach lop.

## 6. Step 1 — Evidence Planner

### 6.1 Trach nhiem

Planner nhan:

- Cau hoi goc va search query da chuan hoa.
- Tom tat conversation + 6–10 messages gan nhat.
- Role/effective role, course scope, channel privacy.
- Top retrieval candidates da co chunk ID, document ID, page, score.
- Personalization context da duoc policy loc.

Planner tra ve **Structured Output** theo JSON Schema, khong tra prose tu do.

### 6.2 Contract de xuat

```json
{
  "intent": "explain_concept",
  "answer_mode": "grounded",
  "needs_second_retrieval": false,
  "follow_up_queries": [],
  "claims": [
    {
      "claim_id": "c1",
      "point": "Python la ngon ngu lap trinh bac cao",
      "evidence_chunk_ids": [120, 145],
      "confidence": "high"
    }
  ],
  "missing_information": [],
  "must_not_say": [],
  "teaching_strategy": "definition_then_example",
  "response_style": {
    "depth": "beginner",
    "tone": "friendly",
    "length": "short",
    "language": "vi"
  }
}
```

### 6.3 Cong nghe

- OpenAI SDK dang co trong backend.
- Structured Outputs voi JSON Schema va `strict=true`.
- Pydantic model `EvidencePlan` de validate lan hai o server.
- Model duoc cau hinh bang env, khong hard-code de A/B test.
- Ban dau giu model re/nhanh dang dung (`gpt-4o-mini`) lam baseline; chi nang model
  neu eval cho thay planner sai evidence/answer mode.

### 6.4 Vi sao khong chi dung prompt JSON thuong

JSON mode chi dam bao JSON hop le, khong dam bao dung schema. Structured Outputs phu hop
hon cho giao dien giua hai agent vi co the test field, enum va invariant. Official OpenAI
documentation cung khuyen nghi JSON Schema thay cho JSON mode cu.

### 6.5 Validator bat buoc sau planner

Backend phai tu kiem tra:

- Tat ca `evidence_chunk_ids` nam trong candidates da retrieval.
- Chunk van qua ACL tai thoi diem validate.
- `grounded` co claim thi claim phai co evidence.
- `general` khong duoc mang citation gia.
- `mixed` phai phan biet grounded/general claim.
- `needs_second_retrieval=true` chi duoc chap nhan neu chua het budget.
- Planner loi/timeout/schema invalid: fallback ve legacy grounded RAG.

## 7. Bounded Retrieval Agent

### 7.1 Dot 1

1. Rewrite theo conversation de xu ly cau noi tiep nhu “phan tren thi sao?”.
2. Khoi phuc dau tieng Viet khi heuristic kich hoat.
3. Sinh toi da 3 search query:
   - semantic query;
   - keyword/thuật ngu query;
   - course-specific query neu da chon lop.
4. Hybrid search tung query.
5. RRF hop nhat, deduplicate theo chunk/document.
6. Rerank top 20 thanh top 6–8.

### 7.2 Reranker

Lua chon khuyen nghi cho MVP: LLM rerank theo batch bang Structured Output vi he thong
da co OpenAI, corpus nho va can reasoning tieng Viet. Cac thay the:

| Lua chon | Uu diem | Nhuoc diem | Khi dung |
|---|---|---|---|
| LLM rerank | Hieu ngu nghia/cau tiep noi tot | Them latency/chi phi | MVP, corpus nho |
| Cross-encoder self-host | Re, on dinh, nhanh khi co GPU | Van hanh model, Viet/Anh can benchmark | Luu luong lon |
| Cohere/Voyage rerank | API chuyen dung, chat luong tot | Them vendor/chi phi/data processor | Khi eval chung minh loi ich |
| Khong rerank | Don gian | Top chunks nhieu nhieu | Baseline/fallback |

Khong thay pgvector bang OpenAI Vector Store trong phase nay. PostgreSQL hien cho phep ACL
pre-filter, document-course mapping, citation va transaction tai mot noi. Vector Store la
phuong an thay the neu muon giam code ingestion/retrieval, nhung can danh gia lai ACL,
vendor lock-in, chi phi va migration.

### 7.3 Dot 2 tuy chon

Planner chi duoc yeu cau dot 2 khi:

- Cac claim chinh thieu evidence.
- Query mo ho/can tach khia canh.
- Ket qua xung dot.

Dot 2 khong duoc dung de vuot ACL. Sau dot 2, planner chay lai mot lan cuoi; khong lap tiep.

## 8. Step 2 — Response Composer

Composer nhan `EvidencePlan`, evidence duoc phep, conversation context va style policy.
No khong nhan toan bo candidates bi loai.

Quy tac:

- Khong them factual claim moi ngoai `claims`.
- Tra loi thang vao cau hoi; khong chao lai moi turn.
- Dung ngon ngu cua nguoi hoi, giu thuat ngu Anh–Viet dung.
- Co the dung cau noi chuyen tu nhien (“Dung roi”, “Cho nay de nham o…”) neu hop ngu canh.
- Khong noi “dua tren tai lieu” lap lai neu citation da the hien ro.
- Neu `general`, noi binh thuong va khong bao “tai lieu khong du thong tin”.
- Neu `mixed`, gan nhan ngan gon cho phan bo sung kien thuc chung.
- Stream SSE ngay khi composer bat dau sinh.

Sau composer:

1. Kiem tra citation/quote.
2. Kiem tra claim co nam trong plan.
3. Output moderation.
4. Luu `evidence_plan`, model version, latency va cost de audit/eval.

## 9. Personalization

### 9.1 Bon lop context

1. **Learning state**: mastery, cau sai, bai da/chua nop, deadline.
2. **Conversation memory**: summary, topic dang noi, pending question.
3. **Explicit preferences**: ngan/chi tiet, vi du/code/so do, ngon ngu.
4. **Policy context**: effective role, course, private/group, capability.

### 9.2 Schema de xuat

`user_learning_preference`

- `user_id` PK/FK.
- `preferred_language`.
- `explanation_depth`: beginner/intermediate/advanced/auto.
- `response_length`: short/medium/detailed/auto.
- `example_style`: code/analogy/step_by_step/auto.
- `updated_at`, `source`: explicit/inferred.

`conversation_memory`

- `conversation_id`.
- `summary`, `covered_concepts`, `open_questions` JSONB.
- `last_summarized_message_id`, `updated_at`.

`agent_turn_plan`

- `message_id`, `answer_mode`, `planner_model`, `plan_json` JSONB.
- `retrieval_rounds`, `latency_ms`, `token_usage`, `created_at`.

### 9.3 Chinh sach ghi nho

- Preference explicit duoc luu khi user noi ro “tu gio…”.
- Preference inferred chi la tam thoi hoac can nhieu tin hieu; co UI cho xem/xoa.
- Khong luu suy doan nhay cam ve nang luc, suc khoe, gioi tinh, tai chinh.
- Learning state tinh tu du lieu chinh thuc, khong cho LLM tu ghi mastery.
- Co nut “Xoa so thich cua Nova” va audit ai/logic nao da ghi.

### 9.4 Personalization trong group

- Group prompt khong chua diem, mastery, cau sai, deadline ca nhan.
- Chi dung role, ngon ngu va style khong nhay cam.
- Cau “diem cua toi?” trong group: tra loi rieng/deep link, khong cong khai.
- Giang vien khong duoc doc conversation rieng cua sinh vien qua connector.

## 10. Omnichannel core

### 10.1 Message envelope chung

```json
{
  "platform": "discord",
  "external_event_id": "...",
  "external_user_id": "...",
  "channel_id": "...",
  "thread_id": "...",
  "is_group": true,
  "mentioned_nova": true,
  "text": "Python la gi?",
  "attachments": [],
  "timestamp": "..."
}
```

### 10.2 Bang du lieu

`external_identity`

- `(platform, external_user_id)` unique.
- `app_user_id`, `verified_at`, `revoked_at`.
- Lien ket bang ma mot lan tao trong web; khong map theo ten hien thi/email tu y.

`external_channel_binding`

- `(platform, channel_id)` unique.
- `course_id`, `created_by`, `is_active`, `privacy_mode`.
- Chi instructor owner/admin duoc bind group vao lop.

`external_conversation`

- Platform/channel/thread -> `conversation_id`.
- `scope`: private/group.
- Group conversation khong gan doc quyen vao mot `Conversation.user_id` nhu hien tai.

`external_message_event`

- `external_event_id` unique de idempotency.
- Sender, payload hash, status, retry_count, error, timestamps.
- Payload raw co TTL/nguyen tac toi thieu hoa du lieu.

### 10.3 Xu ly webhook/queue

Webhook phai verify signature, ghi event va ACK nhanh. Worker xu ly Nova sau do.

MVP khuyen nghi: **PostgreSQL outbox/job table + worker** vi da co PostgreSQL, khong them
Redis/Celery ngay. Claim job bang `FOR UPDATE SKIP LOCKED`, retry exponential va dead-letter.

Thay the:

- Redis + RQ/Arq: latency tot, de queue; them ha tang.
- Celery: manh cho workflow lon; qua nang cho MVP.
- Cloud queue (SQS/Cloud Tasks): ben vung; vendor-specific.
- FastAPI BackgroundTasks: chi demo, co the mat job khi process restart — khong dung production.

## 11. Trien khai tung nen tang

### 11.1 Discord — uu tien 1

Cong nghe:

- Discord Application + Bot.
- Gateway WebSocket worker de nhan `MESSAGE_CREATE` va `@Nova` trong server.
- Discord REST API de reply vao message/thread.
- Alternative: HTTP Interactions + `/nova` slash command, de deploy hon nhung khong dung
  dung trai nghiem `@Nova`.

Discord cho phep app nhan noi dung tin nhan ma bot duoc mention ngay ca khi khong co quyen
doc moi message; vi vay cau hinh mac dinh la chi xu ly mention/DM, khong nghe trom ca kenh.

Flow:

1. Instructor link Discord identity tren web.
2. Invite bot vao server.
3. `/nova-bind CS101-PY` trong channel, backend kiem tra owner.
4. Thanh vien `@Nova ...`.
5. Adapter bo mention, resolve identity/course, goi Nova core.
6. Reply co citation link ve document viewer web.

### 11.2 Zalo — uu tien 2

- Zalo Official Account + App + webhook.
- OA OpenAPI cho tin nhan hai chieu.
- Danh muc tai lieu hien co `Nhom chat - GMF`; can spike tai khoan OA that de xac minh
  eligibility, mention payload va han muc truoc khi chot `@Nova` trong group.
- Token OA luu secret manager, co rotation; verify webhook theo tai lieu tai thoi diem code.
- Neu GMF khong duoc cap: fallback 1:1 OA + link group/web.

### 11.3 Messenger — uu tien 3

- Meta App + Facebook Page + Messenger webhook.
- Phase dau: inbox 1:1 cua Page.
- Group mention chi trien khai neu san pham/quyen app chinh thuc cua Meta tai thoi diem do
  ho tro dung loai group can dung; khong dung automation tai khoan ca nhan.
- App Review, privacy policy, data deletion callback va webhook signature la gate bat buoc.

## 12. Bao mat va privacy

- Moi connector request vao Nova core phai co `ActorContext` da xac minh; khong tin role,
  course ID hay user ID tu text/event.
- Identity link bang one-time code het han 5 phut, hash trong DB, dung mot lan.
- Bind channel voi course can instructor ownership.
- ACL retrieval van chay trong SQL sau khi resolve actor/course.
- Group conversation khong duoc nap private personalization.
- Tool ghi van xac nhan hai buoc; tren group chi hien preview, xac nhan trong web/private.
- Verify signature/timestamp, idempotency, rate limit theo platform/user/channel.
- Secret connector chi nam trong env/secret manager, khong log token.
- Log payload da redact; retention policy ro rang.
- Outbound `allowed_mentions`/tuong duong phai tat mention ngoai y muon.
- Co kill switch tung connector va tung channel.

## 13. Thay doi backend de xuat

```text
backend/app/
  agentic_rag/
    orchestrator.py
    schemas.py
    retrieval_agent.py
    evidence_planner.py
    plan_validator.py
    response_composer.py
    policies.py
  personalization/
    context_builder.py
    preference_service.py
    memory_service.py
    schemas.py
  connectors/
    common/
      envelope.py
      identity.py
      outbox.py
    discord/
    zalo/
    messenger/
```

Khong viet lai `academic_agent/agent.py` mot lan. Tao orchestrator moi sau feature flag va
tai su dung guardrail, retrieval, role policy, tool executor. Khi eval dat, moi rut gon
legacy path.

## 14. Feature flags va cau hinh

- `NOVA_AGENTIC_RAG_ENABLED=false`.
- `NOVA_AGENTIC_RAG_PERCENT=0` de canary.
- `NOVA_PLANNER_MODEL=...`.
- `NOVA_COMPOSER_MODEL=...`.
- `NOVA_MAX_RETRIEVAL_ROUNDS=2`.
- `NOVA_MAX_SUBQUERIES=3`.
- `NOVA_GENERAL_KNOWLEDGE_ENABLED=false`.
- `DISCORD_CONNECTOR_ENABLED=false`, tuong tu Zalo/Messenger.

Khong ghi ten model vao migration/database policy. Ghim version model trong production neu
can reproducibility, va luu model thuc te tren moi turn de eval.

## 15. API contracts moi

- `POST /v1/chat/stream`: giu tuong thich; them event tuy chon `planning` va metadata done.
- `GET/PATCH /v1/nova/preferences/me`.
- `DELETE /v1/nova/preferences/me`.
- `POST /v1/connectors/link-code`.
- `POST /v1/connectors/{platform}/webhook`.
- `POST /v1/connectors/{platform}/channels/bind`.
- `DELETE /v1/connectors/{platform}/channels/{id}/bind`.
- Instructor endpoint xem binding/audit, khong xem private chat content.

Khong expose `EvidencePlan` day du cho client mac dinh; no co the chua noi dung policy va
du lieu context. UI chi nhan answer mode, citations va trang thai can thiet.

## 16. Observability va chi phi

Do rieng:

- Router, rewrite, embedding, search, rerank, planner, second retrieval, composer.
- Token/cost theo model va channel.
- Planner schema failure, invalid evidence, fallback rate.
- Grounded claim coverage va citation validity.
- First-token latency va total latency.
- Connector webhook ACK, queue delay, retry/dead-letter.

Muc tieu ban dau khong dat con so tuyet doi khi chua benchmark. Gate rollout:

- p95 first-token khong tang qua 35% so voi baseline.
- Planner fallback < 2%.
- Citation precision >= baseline hien tai.
- Cross-account/cross-course leak = 0 trong test.
- Chi phi/turn khong vuot budget duoc chot sau benchmark 100–500 turn.

Toi uu:

- Guardrail/router/context load song song.
- Planner output ngan va schema co dinh.
- Composer chi nhan top evidence da chot.
- Cache embedding/retrieval cho query lap lai theo course/document version.
- Prompt prefix on dinh de tan dung prompt caching khi model/API ho tro.

## 17. Eval va test

### 17.1 Dataset toi thieu

- 30 grounded questions co expected chunks.
- 20 general knowledge (`1+1`, ngay thang, dinh nghia co ban).
- 20 mixed/no-evidence cases.
- 20 conversational follow-ups.
- 20 Socratic cases theo mastery thap/cao.
- 20 prompt injection/jailbreak.
- 20 role/privacy cases.
- 15 group cases co yeu cau du lieu ca nhan.
- 10 connector duplicate/retry/out-of-order cases moi platform.

### 17.2 Chi so

- Route/answer-mode accuracy.
- Retrieval recall@k, MRR/nDCG sau rerank.
- Claim-evidence entailment.
- Citation precision/coverage.
- Faithfulness, answer relevance, conversational naturalness.
- Personalization appropriateness, privacy violation rate.
- Latency, cost, fallback rate.

LLM judge chi la mot tin hieu; phai co rule assertions va bo golden do nguoi danh gia.

### 17.3 Security tests bat buoc

- User A mo conversation/user memory cua B -> 404.
- Student thu bind channel vao course -> 403.
- Group hoi diem cua mot sinh vien -> khong lo.
- External ID gia/one-time code dung lai -> reject.
- Webhook signature sai/replay/duplicate -> reject/idempotent.
- Prompt injection trong message va trong document -> khong vuot policy/ACL.

## 18. Lo trinh trien khai

### Phase 0 — Baseline va feature flags

- Dong bang dataset/eval, do pipeline hien tai.
- Them config/flag va metrics.
- Khong thay hanh vi production.

**Gate:** co report baseline, rollback test thanh cong.

### Phase 1 — Router va general knowledge

- Bo force RAG o tab Hoi dap.
- Hoan thien policy `general/grounded/mixed`.
- Test `1+1`, chitchat, Python co/khong co tai lieu.

**Gate:** general knowledge dung, khong lam lo dap an/quy dinh lop.

### Phase 2 — Evidence Planner mot retrieval round

- Pydantic schema + Structured Output.
- Planner, validator, persistence `agent_turn_plan`.
- Composer van dung retrieval hien tai.
- Fallback legacy.

**Gate:** schema success, citation/faithfulness >= baseline.

### Phase 3 — Bounded Retrieval Agent va rerank

- Multi-query, dedup, rerank, optional round 2.
- Budget/timeout/circuit breaker.

**Gate:** recall/relevance tang co y nghia; latency/chi phi trong budget.

### Phase 4 — Composer va conversation quality

- Tach prompt style khoi evidence policy.
- Stream, claim validator, eval tu nhien.
- A/B voi legacy.

**Gate:** human eval tot hon, khong giam faithfulness.

### Phase 5 — Personalization

- Preference API/UI, memory summary incremental.
- Context builder va privacy scope.
- UI xem/xoa memory/preferences.

**Gate:** dung preference, khong leak group/cross-user.

### Phase 6 — Omnichannel foundation

- Schema identity/channel/outbox.
- Link code, webhook verification, worker, audit/admin UI.
- Mock connector contract tests.

**Gate:** idempotency, retry, revoke, privacy tests pass.

### Phase 7 — Discord pilot

- Gateway worker, mention-only, bind course, reply citation.
- Pilot mot server/lop, kill switch.

**Gate:** van hanh 1–2 tuan khong leak, retry on dinh, chi phi chap nhan.

### Phase 8 — Zalo OA/GMF pilot

- Spike eligibility/payload/hạn mức.
- OA webhook, identity link, group neu duoc cap.

**Gate:** app/OA duoc phep va test that; neu khong, chi 1:1.

**Trang thai 2026-08-31:** da hoan thanh adapter, webhook bridge, identity link, outbox
worker, OA REST client va benchmark cho 1:1. Connector va GMF deu tat mac dinh. GMF chi
duoc bat sau khi OA/App that duoc Zalo cap capability va fixture payload chinh thuc da
qua contract/security test; hien chua tuyen bo dat gate live pilot.

### Phase 9 — Messenger Page pilot

- Page inbox, webhook/app review/data deletion.
- Group chi lam neu API chinh thuc cho phep.

### Phase 10 — Hardening va rollout

- Load test, runbook, alert, retention, cost dashboard.
- Canary 5% -> 25% -> 100%, rollback theo metric.

**Trang thai 2026-08-31:** da co cohort rollout on dinh theo user, operations status
admin-only, p95 latency/dead-job rollback signal, retention preview/run va phuc hoi outbox
bi ket sau worker crash. Code/eval dat gate; rollout production van can du lieu van hanh that.

### Phase 11 — Tro ly giang vien chuyen biet (lam sau cac phase tren)

Phase nay khong dung chung learner prompt cua sinh vien. Nova phai nhan dung
`global_role`, `effective_role` trong lop dang chon va chi nap capability phu hop.

- Tao knowledge base rieng cho giang vien gom: huong dan su dung he thong, quy trinh tai
  lieu/duyet tai lieu, quan ly lop, bai tap, thong ke va cac loi thuong gap.
- Tach retrieval scope `system_support`, `teaching_support` va `course_content`; cau hoi
  ve thao tac he thong uu tien knowledge base giang vien thay vi tai lieu hoc cua sinh vien.
- Xay Instructor Context gom analytics tong hop, sinh vien can ho tro, nhom manh/yeu,
  concept gap, bai chua nop va xu huong cua lop. Du lieu ca nhan chi mo khi giang vien hoi
  dich danh va backend xac minh quyen so huu lop.
- Sinh goi y lo trinh giang day, noi dung can on lai, bai tap bo sung va cach chia nhom;
  moi khuyen nghi phai neu ro du lieu nao dan den khuyen nghi, khong tu suy dien ve nguoi hoc.
- Sua role contract xuyen suot Router -> Planner -> Composer -> Tool Registry. Tai khoan
  `INSTRUCTOR` khong duoc nhan cau tra loi kieu "hay lien he giang vien" khi dang thao tac
  trong lop minh so huu.
- Neu mot giang vien la hoc vien trong lop khac, `effective_role` cua lop do van la
  `STUDENT`; capability giang vien chi con cho cac lop ho so huu.
- Tao benchmark rieng theo role va kiem thu bat buoc: instructor/student cung mot cau hoi
  nhan cau tra loi dung vai tro, khong lo chat rieng, khong truy cap cheo lop, khong tu dong
  liet ke chi tiet ca nhan hang loat.

**Gate:** role accuracy 100% tren bo test policy, cross-role/cross-course leak = 0, cau hoi
ho tro he thong va khuyen nghi giang day dat human review truoc khi rollout.

**Trang thai 2026-08-31:** da tach System Knowledge theo `audience_scope`, seed KB ho tro
giang vien, nap Instructor Context tong hop, them tool goi y lo trinh giang day va giu
chi tiet ca nhan sau owner RBAC. Automated/integration gate dat; human review production
van la dieu kien rollout.

## 19. Thu tu migration du kien

1. `agent_turn_plan`.
2. `user_learning_preference`.
3. `conversation_memory`.
4. `external_identity`.
5. `external_channel_binding`.
6. `external_conversation` va mo rong conversation scope.
7. `external_message_event`/outbox.

Moi migration co downgrade, index, unique/check constraint va backfill ro rang. Khong doi
`Conversation.user_id` thanh nullable ngay; them group scope theo kieu additive, migrate,
roi moi siết invariant moi de khong pha chat web.

## 20. Rui ro va giam thieu

| Rui ro | Giam thieu |
|---|---|
| Hai LLM call tang latency | Planner ngan, model re, parallel truoc retrieval, fallback/canary |
| Planner “chot” claim sai | Schema + evidence ID validation + eval + composer khong them claim |
| Mixed mode lam model bua | Policy cam cho assessment/rules/private data; gan nhan source |
| Personalization gay kho chiu | Explicit preferences, UI xem/xoa, inferred memory han che |
| Ro du lieu trong group | Group privacy scope, private redirect, test adversarial |
| Connector gui trung | Event ID unique + outbox idempotent |
| Token webhook bi lo | Secret manager, rotation, redact logs |
| Vendor/API thay doi | Adapter interface, feature flag, contract test, kill switch |
| Chi phi vuot | Per-turn budget, model config, metrics, quota theo channel/course |

## 21. Cac quyet dinh can duyet truoc khi code

1. Cho phep `mixed` hay phase dau chi `grounded/general`?
2. General knowledge co bat cho ca sinh vien va giang vien khong?
3. Preference inferred co duoc luu lau hay chi explicit?
4. Group co cho Nova tra loi thong tin lop tong hop hay chi kien thuc tai lieu?
5. Chon Discord Gateway `@Nova` hay slash command de MVP nhanh hon?
6. Chap nhan them mot worker always-on cho Discord khong?
7. Retention raw webhook payload bao lau (de xuat 7 ngay hoac khong luu body sau xu ly)?
8. Budget latency/cost moi turn chap nhan duoc la bao nhieu?

## 22. De xuat chot cua toi

- Trien khai phase 0–2 truoc; chua lam connector cho toi khi Agent Core on dinh.
- MVP chi `grounded` va `general`; hoan `mixed` den khi co eval claim-level tot.
- Khong dung LangGraph/Agents SDK o phase dau: flow co gioi han va FastAPI hien tai du de
  orchestration ro rang, de test va it dependency. Xem lai khi co nhieu agent/parallel tool
  graph phuc tap that su.
- Giu PostgreSQL + pgvector + full-text + RRF; them rerank sau benchmark.
- Structured Outputs cho planner, SSE cho composer.
- Chi luu preference explicit trong ban dau.
- Discord mention-only la connector dau tien; Zalo OA/GMF sau khi spike; Messenger Page 1:1 sau cung.
- Group tuyet doi khong dung private learner context.

## 23. Tai lieu tham khao chinh thuc

- OpenAI API quickstart, tools, streaming va Agents SDK:
  https://platform.openai.com/docs/quickstart/make-your-first-api-request
- OpenAI Structured Outputs / JSON Schema:
  https://platform.openai.com/docs/api-reference/evals/deleteRun?lang=python
- OpenAI Vector Stores (phuong an thay the, khong phai lua chon MVP):
  https://platform.openai.com/docs/api-reference/vector-stores?lang=python
- OpenAI data controls (can xem lai khi chot retention/store):
  https://platform.openai.com/docs/models/default-usage-policies-by-endpoint
- Discord Gateway va Message Content Intent:
  https://docs.discord.com/developers/events/gateway
- Discord Bots:
  https://docs.discord.com/developers/platform/bots
- Discord Message/Allowed Mentions:
  https://docs.discord.com/developers/resources/message
- Zalo Developer / OA / GMF / Webhook:
  https://developers.zalo.me/docs
