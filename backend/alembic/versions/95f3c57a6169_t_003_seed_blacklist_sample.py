"""T-003 seed blacklist sample

Revision ID: 95f3c57a6169
Revises: 22613ba59100
Create Date: 2026-08-17 15:28:08.486527

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "95f3c57a6169"
down_revision: Union[str, None] = "22613ba59100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# 40 DỮ LIỆU GIẢ PHỤC VỤ KIỂM THỬ
# PHONE         -> E.164
# DOMAIN        -> domain đã chuẩn hóa
# URL           -> URL đã chuẩn hóa
# BANK_ACCOUNT  -> số tài khoản giả
# ============================================================

BLACKLIST_ENTITIES = [
    # --------------------------------------------------------
    # PHONE - 10 mẫu
    # --------------------------------------------------------
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000001",
        "source": "MANUAL",
        "confidence": 95,
        "report_count": 8,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000002",
        "source": "COMMUNITY",
        "confidence": 85,
        "report_count": 5,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000003",
        "source": "COMMUNITY",
        "confidence": 80,
        "report_count": 4,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000004",
        "source": "PUBLIC_FEED",
        "confidence": 90,
        "report_count": 7,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000005",
        "source": "MANUAL",
        "confidence": 75,
        "report_count": 3,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000006",
        "source": "COMMUNITY",
        "confidence": 70,
        "report_count": 2,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000007",
        "source": "PUBLIC_FEED",
        "confidence": 88,
        "report_count": 6,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000008",
        "source": "MANUAL",
        "confidence": 92,
        "report_count": 9,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000009",
        "source": "COMMUNITY",
        "confidence": 65,
        "report_count": 1,
        "is_active": False,
        "note": "Dữ liệu mẫu kiểm thử, đã vô hiệu hóa.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "PHONE",
        "normalized_value": "+84900000010",
        "source": "PUBLIC_FEED",
        "confidence": 82,
        "report_count": 4,
        "is_active": True,
        "note": "Dữ liệu mẫu kiểm thử.",
    },

    # --------------------------------------------------------
    # DOMAIN - 10 mẫu
    # --------------------------------------------------------
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "bank-login-001.example",
        "source": "MANUAL",
        "confidence": 95,
        "report_count": 10,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "bank-login-002.example",
        "source": "COMMUNITY",
        "confidence": 90,
        "report_count": 7,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "account-verify-001.example",
        "source": "PUBLIC_FEED",
        "confidence": 88,
        "report_count": 6,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "account-verify-002.example",
        "source": "COMMUNITY",
        "confidence": 85,
        "report_count": 5,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "gift-notice-001.example",
        "source": "MANUAL",
        "confidence": 80,
        "report_count": 4,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "gift-notice-002.example",
        "source": "PUBLIC_FEED",
        "confidence": 78,
        "report_count": 3,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "online-job-001.example",
        "source": "COMMUNITY",
        "confidence": 75,
        "report_count": 3,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "online-job-002.example",
        "source": "MANUAL",
        "confidence": 82,
        "report_count": 4,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "payment-alert-001.example",
        "source": "PUBLIC_FEED",
        "confidence": 87,
        "report_count": 5,
        "is_active": True,
        "note": "Domain giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "DOMAIN",
        "normalized_value": "payment-alert-002.example",
        "source": "COMMUNITY",
        "confidence": 72,
        "report_count": 2,
        "is_active": False,
        "note": "Domain giả phục vụ kiểm thử, đã vô hiệu hóa.",
    },

    # --------------------------------------------------------
    # URL - 10 mẫu
    # --------------------------------------------------------
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://bank-login-001.example/verify",
        "source": "MANUAL",
        "confidence": 95,
        "report_count": 8,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://bank-login-002.example/login",
        "source": "COMMUNITY",
        "confidence": 90,
        "report_count": 6,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://account-verify-001.example/confirm",
        "source": "PUBLIC_FEED",
        "confidence": 88,
        "report_count": 5,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://account-verify-002.example/otp",
        "source": "MANUAL",
        "confidence": 92,
        "report_count": 7,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://gift-notice-001.example/reward",
        "source": "COMMUNITY",
        "confidence": 80,
        "report_count": 4,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://gift-notice-002.example/claim",
        "source": "PUBLIC_FEED",
        "confidence": 78,
        "report_count": 3,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://online-job-001.example/register",
        "source": "COMMUNITY",
        "confidence": 75,
        "report_count": 3,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://online-job-002.example/task",
        "source": "MANUAL",
        "confidence": 85,
        "report_count": 5,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://payment-alert-001.example/payment",
        "source": "PUBLIC_FEED",
        "confidence": 87,
        "report_count": 6,
        "is_active": True,
        "note": "URL giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "URL",
        "normalized_value": "https://payment-alert-002.example/confirm",
        "source": "COMMUNITY",
        "confidence": 70,
        "report_count": 2,
        "is_active": False,
        "note": "URL giả phục vụ kiểm thử, đã vô hiệu hóa.",
    },

    # --------------------------------------------------------
    # BANK_ACCOUNT - 10 mẫu
    # --------------------------------------------------------
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000001",
        "source": "MANUAL",
        "confidence": 95,
        "report_count": 9,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000002",
        "source": "COMMUNITY",
        "confidence": 90,
        "report_count": 7,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000003",
        "source": "PUBLIC_FEED",
        "confidence": 85,
        "report_count": 5,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000004",
        "source": "MANUAL",
        "confidence": 88,
        "report_count": 6,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000005",
        "source": "COMMUNITY",
        "confidence": 80,
        "report_count": 4,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000006",
        "source": "PUBLIC_FEED",
        "confidence": 75,
        "report_count": 3,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000007",
        "source": "MANUAL",
        "confidence": 92,
        "report_count": 8,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000008",
        "source": "COMMUNITY",
        "confidence": 82,
        "report_count": 4,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000009",
        "source": "PUBLIC_FEED",
        "confidence": 68,
        "report_count": 2,
        "is_active": False,
        "note": "Số tài khoản giả phục vụ kiểm thử, đã vô hiệu hóa.",
    },
    {
        "id": uuid.uuid4(),
        "entity_type": "BANK_ACCOUNT",
        "normalized_value": "900000000010",
        "source": "MANUAL",
        "confidence": 86,
        "report_count": 5,
        "is_active": True,
        "note": "Số tài khoản giả phục vụ kiểm thử.",
    },
]


blacklist_entity_table = sa.table(
    "blacklist_entity",
    sa.column("id", sa.UUID()),
    sa.column("entity_type", sa.String()),
    sa.column("normalized_value", sa.String()),
    sa.column("source", sa.String()),
    sa.column("confidence", sa.Integer()),
    sa.column("report_count", sa.Integer()),
    sa.column("is_active", sa.Boolean()),
    sa.column("note", sa.Text()),
)


def upgrade() -> None:
    op.bulk_insert(
        blacklist_entity_table,
        BLACKLIST_ENTITIES,
    )


def downgrade() -> None:
    ids = [item["id"] for item in BLACKLIST_ENTITIES]

    op.execute(
        sa.text(
            """
            DELETE FROM blacklist_entity
            WHERE id = ANY(:ids)
            """
        ).bindparams(
            sa.bindparam(
                "ids",
                type_=sa.ARRAY(sa.UUID()),
            )
        ).params(
            ids=ids
        )
    )