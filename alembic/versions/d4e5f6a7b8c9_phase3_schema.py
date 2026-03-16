"""Phase 3 schema: organizations, rule_sets, scope_results, recommendations, payments, admin_notes, assessment_claims, audit_events

Revision ID: d4e5f6a7b8c9
Revises: c071221dc443
Create Date: 2025-03-12

Note: questions.rule_set_id migration deferred - questions remain in code. See SCHEMA-DESIGN-PHASE3.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c071221dc443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # 1. Organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # 2. Add organization_id to users (batch for SQLite)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_users_organization", "organizations", ["organization_id"], ["id"])
        batch_op.create_index("ix_users_organization_id", ["organization_id"])

    # 3. Rule sets
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("environment_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework", "environment_type", "version", name="uq_rule_sets_framework_env_version"),
    )
    op.create_index("ix_rule_sets_framework_env", "rule_sets", ["framework", "environment_type"])
    op.execute("""
        INSERT INTO rule_sets (framework, environment_type, version, is_active)
        VALUES ('pci_dss', 'ecommerce', 1, 1),
               ('pci_dss', 'pos', 1, 1),
               ('pci_dss', 'payment_platform', 1, 1)
    """)

    # 4. Update assessments (batch for SQLite)
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("framework", sa.String(50), nullable=True, server_default="pci_dss"))
        batch_op.add_column(sa.Column("rule_set_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("anonymous_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_assessments_organization", "organizations", ["organization_id"], ["id"])
        batch_op.create_foreign_key("fk_assessments_rule_set", "rule_sets", ["rule_set_id"], ["id"])
        batch_op.create_index("ix_assessments_anonymous_id", ["anonymous_id"], unique=True)
        batch_op.create_index("ix_assessments_organization_id", ["organization_id"])
        batch_op.create_index("ix_assessments_created_at", ["created_at"])

    op.execute("UPDATE assessments SET framework = 'pci_dss' WHERE framework IS NULL")

    # 5. Scope results
    op.create_table(
        "scope_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("scope_level", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("in_scope", sa.JSON(), nullable=False),
        sa.Column("out_of_scope", sa.JSON(), nullable=False),
        sa.Column("risk_areas", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", name="uq_scope_results_assessment"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scope_results_assessment_id", "scope_results", ["assessment_id"])

    # Migrate scope_result from assessments
    if conn.dialect.name == "sqlite":
        op.execute("""
            INSERT INTO scope_results (assessment_id, scope_level, summary, in_scope, out_of_scope, risk_areas, computed_at)
            SELECT id, json_extract(scope_result,'$.scope_level'), json_extract(scope_result,'$.summary'),
                   COALESCE(json_extract(scope_result,'$.in_scope'), '[]'),
                   COALESCE(json_extract(scope_result,'$.out_of_scope'), '[]'),
                   COALESCE(json_extract(scope_result,'$.risk_areas'), '[]'),
                   updated_at
            FROM assessments WHERE scope_result IS NOT NULL AND status = 'completed'
        """)
    else:
        op.execute("""
            INSERT INTO scope_results (assessment_id, scope_level, summary, in_scope, out_of_scope, risk_areas, computed_at)
            SELECT id, scope_result->>'scope_level', scope_result->>'summary',
                   COALESCE(scope_result->'in_scope','[]'::json), COALESCE(scope_result->'out_of_scope','[]'::json),
                   COALESCE(scope_result->'risk_areas','[]'::json), updated_at
            FROM assessments WHERE scope_result IS NOT NULL AND status = 'completed'
        """)

    # 6. Recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recommendations_assessment_id", "recommendations", ["assessment_id"])

    # 7. Payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_stripe_session", "payments", ["stripe_checkout_session_id"], unique=True)

    # 8. Update reports
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("generated_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_reports_payment", "payments", ["payment_id"], ["id"])
        batch_op.create_index("ix_reports_payment_id", ["payment_id"])

    # 9. Admin notes
    op.create_table(
        "admin_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_admin_notes_assessment_id", "admin_notes", ["assessment_id"])

    # 10. Assessment claims
    op.create_table(
        "assessment_claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_assessment_claims_token"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_assessment_claims_token", "assessment_claims", ["token"], unique=True)

    # 11. Audit events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    # 12. Update consulting_leads
    with op.batch_alter_table("consulting_leads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_consulting_leads_user", "users", ["user_id"], ["id"])
        batch_op.create_foreign_key("fk_consulting_leads_assessment", "assessments", ["assessment_id"], ["id"])
        batch_op.create_foreign_key("fk_consulting_leads_organization", "organizations", ["organization_id"], ["id"])
        batch_op.create_index("ix_consulting_leads_created_at", ["created_at"])


def downgrade() -> None:
    with op.batch_alter_table("consulting_leads", schema=None) as batch_op:
        batch_op.drop_index("ix_consulting_leads_created_at", if_exists=True)
        batch_op.drop_constraint("fk_consulting_leads_organization", type_="foreignkey")
        batch_op.drop_constraint("fk_consulting_leads_assessment", type_="foreignkey")
        batch_op.drop_constraint("fk_consulting_leads_user", type_="foreignkey")
        batch_op.drop_column("organization_id")

    op.drop_table("audit_events")
    op.drop_table("assessment_claims")
    op.drop_table("admin_notes")

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index("ix_reports_payment_id", if_exists=True)
        batch_op.drop_constraint("fk_reports_payment", type_="foreignkey")
        batch_op.drop_column("payment_id")
        batch_op.drop_column("generated_at")

    op.drop_table("payments")
    op.drop_table("recommendations")
    op.drop_table("scope_results")

    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_index("ix_assessments_created_at", if_exists=True)
        batch_op.drop_index("ix_assessments_organization_id", if_exists=True)
        batch_op.drop_index("ix_assessments_anonymous_id", if_exists=True)
        batch_op.drop_constraint("fk_assessments_rule_set", type_="foreignkey")
        batch_op.drop_constraint("fk_assessments_organization", type_="foreignkey")
        batch_op.drop_column("claimed_at")
        batch_op.drop_column("anonymous_id")
        batch_op.drop_column("rule_set_id")
        batch_op.drop_column("framework")
        batch_op.drop_column("organization_id")

    op.drop_table("rule_sets")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_organization_id", if_exists=True)
        batch_op.drop_constraint("fk_users_organization", type_="foreignkey")
        batch_op.drop_column("organization_id")

    op.drop_index("ix_organizations_slug", "organizations")
    op.drop_table("organizations")
