"""add omnichannel identity, binding, event and outbox foundation"""

from alembic import op

revision = "20260831_0025"
down_revision = "20260831_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE external_identity_link_code (
            id BIGSERIAL PRIMARY KEY, app_user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            platform VARCHAR(20) NOT NULL, code_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_link_code_platform CHECK (platform IN ('mock','discord','zalo','messenger'))
        )
    """)
    op.execute("CREATE INDEX ix_link_code_user_platform ON external_identity_link_code(app_user_id, platform)")
    op.execute("""
        CREATE TABLE external_identity (
            id BIGSERIAL PRIMARY KEY, platform VARCHAR(20) NOT NULL, external_user_id VARCHAR(255) NOT NULL,
            app_user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            verified_at TIMESTAMPTZ NOT NULL DEFAULT now(), revoked_at TIMESTAMPTZ,
            CONSTRAINT ck_external_identity_platform CHECK (platform IN ('mock','discord','zalo','messenger')),
            CONSTRAINT uq_external_identity_platform_user UNIQUE(platform, external_user_id),
            CONSTRAINT uq_external_identity_app_platform UNIQUE(app_user_id, platform)
        )
    """)
    op.execute("""
        CREATE TABLE external_channel_binding (
            id BIGSERIAL PRIMARY KEY, platform VARCHAR(20) NOT NULL, channel_id VARCHAR(255) NOT NULL,
            course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
            created_by BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            privacy_mode VARCHAR(20) NOT NULL DEFAULT 'MENTION_ONLY', is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_channel_binding_platform CHECK (platform IN ('mock','discord','zalo','messenger')),
            CONSTRAINT ck_channel_binding_privacy CHECK (privacy_mode IN ('MENTION_ONLY','PRIVATE_ONLY')),
            CONSTRAINT uq_channel_binding_platform_channel UNIQUE(platform, channel_id)
        )
    """)
    op.execute("CREATE INDEX ix_channel_binding_course ON external_channel_binding(course_id)")
    op.execute("""
        CREATE TABLE external_conversation (
            id BIGSERIAL PRIMARY KEY, platform VARCHAR(20) NOT NULL, channel_id VARCHAR(255) NOT NULL,
            thread_id VARCHAR(255) NOT NULL DEFAULT '', scope VARCHAR(10) NOT NULL,
            conversation_id BIGINT REFERENCES conversation(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_external_conversation_scope CHECK (scope IN ('PRIVATE','GROUP')),
            CONSTRAINT uq_external_conversation_scope UNIQUE(platform, channel_id, thread_id)
        )
    """)
    op.execute("""
        CREATE TABLE external_message_event (
            id BIGSERIAL PRIMARY KEY, platform VARCHAR(20) NOT NULL, external_event_id VARCHAR(255) NOT NULL,
            external_user_id VARCHAR(255) NOT NULL, channel_id VARCHAR(255) NOT NULL,
            thread_id VARCHAR(255) NOT NULL DEFAULT '', payload_hash VARCHAR(64) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'RECEIVED', retry_count INTEGER NOT NULL DEFAULT 0,
            error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), processed_at TIMESTAMPTZ,
            CONSTRAINT uq_external_event_platform_id UNIQUE(platform, external_event_id)
        )
    """)
    op.execute("""
        CREATE TABLE connector_outbox (
            id BIGSERIAL PRIMARY KEY, event_id BIGINT NOT NULL UNIQUE REFERENCES external_message_event(id) ON DELETE CASCADE,
            payload TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT now(), locked_at TIMESTAMPTZ, last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX ix_connector_outbox_claim ON connector_outbox(status, available_at, id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS connector_outbox")
    op.execute("DROP TABLE IF EXISTS external_message_event")
    op.execute("DROP TABLE IF EXISTS external_conversation")
    op.execute("DROP TABLE IF EXISTS external_channel_binding")
    op.execute("DROP TABLE IF EXISTS external_identity")
    op.execute("DROP TABLE IF EXISTS external_identity_link_code")
