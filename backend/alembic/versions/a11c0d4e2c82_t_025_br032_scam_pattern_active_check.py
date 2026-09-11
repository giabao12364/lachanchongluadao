"""T-025 BR-03-2: scam_pattern is_active=true bắt buộc đủ 3 khối signs/example_content/recommended_action

Các thay đổi trong file migration này (toàn bộ thuộc task T-025):
1. Đổi 3 cột signs, example_content, recommended_action từ NOT NULL → NULLABLE
   (để có thể lưu bản nháp is_active=false thiếu 1 trong 3 khối).
2. Tiền xử lý: nếu có record nào đang is_active=true mà 1 trong 3 khối rỗng
   → tạm gắn is_active=false (nếu không bước 3 tạo CheckConstraint sẽ FAIL).
3. Tạo CheckConstraint `ck_scam_pattern_active_requires_3blocks` ở DB level:
   is_active=true ⇒ 3 khối không được rỗng (kể cả chỉ khoảng trắng).

Revision ID: a11c0d4e2c82
Revises: 2b03ad67bea2
Create Date: 2026-09-05 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a11c0d4e2c82'
down_revision: Union[str, None] = '2b03ad67bea2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===============================================================
    # Bước 1 — Cho phép 3 cột nhận giá trị NULL / rỗng (lưu nháp được)
    # ===============================================================
    op.alter_column('scam_pattern', 'signs',
                    existing_type=sa.Text(),
                    nullable=True)
    op.alter_column('scam_pattern', 'example_content',
                    existing_type=sa.Text(),
                    nullable=True)
    op.alter_column('scam_pattern', 'recommended_action',
                    existing_type=sa.Text(),
                    nullable=True)

    # ===============================================================
    # Bước 2 — Tiền xử lý dữ liệu cũ:
    # Nếu có hàng nào đang is_active=true mà 1 khối rỗng → chuyển về nháp
    # (nếu không bước 3 tạo CheckConstraint sẽ FAILED do vi phạm ràng buộc)
    # ===============================================================
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        UPDATE scam_pattern
        SET is_active = false, updated_at = NOW()
        WHERE is_active = true
          AND (signs IS NULL
               OR example_content IS NULL
               OR recommended_action IS NULL
               OR BTRIM(signs) = ''
               OR BTRIM(example_content) = ''
               OR BTRIM(recommended_action) = '');
        """
    ))

    # ===============================================================
    # Bước 3 — Tạo ràng buộc DB level:
    # BR-03-2: is_active=true ⇒ đủ 3 khối (không rỗng, không chỉ khoảng trắng)
    # ===============================================================
    op.create_check_constraint(
        "ck_scam_pattern_active_requires_3blocks",
        "scam_pattern",
        """NOT (
            is_active = true
            AND (signs IS NULL
                 OR example_content IS NULL
                 OR recommended_action IS NULL
                 OR BTRIM(signs) = ''
                 OR BTRIM(example_content) = ''
                 OR BTRIM(recommended_action) = '')
        )""",
    )


def downgrade() -> None:
    # Bước ngược 3: Xóa check constraint
    op.drop_constraint(
        "ck_scam_pattern_active_requires_3blocks",
        "scam_pattern",
        type_="check",
    )

    # Bước ngược 2 (tùy chọn an toàn):
    # Nếu có hàng nào đang có giá trị NULL → thay bằng chuỗi rỗng
    # trước khi set lại NOT NULL (nếu không ALTER COLUMN SET NOT NULL sẽ fail)
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        UPDATE scam_pattern
        SET signs              = COALESCE(signs, ''),
            example_content    = COALESCE(example_content, ''),
            recommended_action = COALESCE(recommended_action, '')
        WHERE signs IS NULL
           OR example_content IS NULL
           OR recommended_action IS NULL;
        """
    ))

    # Bước ngược 1: Trở lại NOT NULL như schema ban đầu
    op.alter_column('scam_pattern', 'recommended_action',
                    existing_type=sa.Text(),
                    nullable=False)
    op.alter_column('scam_pattern', 'example_content',
                    existing_type=sa.Text(),
                    nullable=False)
    op.alter_column('scam_pattern', 'signs',
                    existing_type=sa.Text(),
                    nullable=False)
