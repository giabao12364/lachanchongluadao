"""T-002 seed app config

Revision ID: 22613ba59100
Revises: 82438f4165cc
Create Date: 2026-08-17 15:11:23.614071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22613ba59100'
down_revision: Union[str, None] = '82438f4165cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_CONFIG = [
    {
        "key": "threshold.nghi_ngo",
        "value": "30",
        "value_type": "int",
    },
    {
        "key": "threshold.nguy_hiem",
        "value": "70",
        "value_type": "int",
    },
    {
        "key": "ai.weight",
        "value": "0.6",
        "value_type": "float",
    },
    {
        "key": "ai.timeout_seconds",
        "value": "5",
        "value_type": "int",
    },
    {
        "key": "ratelimit.anonymous_hourly",
        "value": "20",
        "value_type": "int",
    },
    {
        "key": "ratelimit.user_hourly",
        "value": "100",
        "value_type": "int",
    },
    {
        "key": "retention.content_days",
        "value": "30",
        "value_type": "int",
    },
    {
        "key": "ai.system_prompt",
        "value": """Bạn là chuyên gia phân tích lừa đảo trực tuyến tại Việt Nam.
Nhiệm vụ: đánh giá nội dung người dùng gửi có dấu hiệu lừa đảo không.
QUY TẮC BẮT BUỘC:
- Chỉ phân tích nội dung được cung cấp. Không suy đoán thông tin không có.
- Nếu không chắc chắn, hãy nghiêng về CẢNH BÁO (thà báo dư hơn bỏ sót).
- Lý do phải viết bằng tiếng Việt đơn giản, cho người 65+ tuổi đọc hiểu được.
- Không dùng thuật ngữ kỹ thuật.
- CHỈ trả về JSON thuần, không markdown, không giải thích thêm.
Định dạng trả về:
{"score": <0-100>, "reasons": ["<lý do 1>", "<lý do 2>"]}
Thang điểm: 0-29 = không có dấu hiệu; 30-69 = đáng ngờ; 70-100 = rất có thể lừa đảo.
Tối đa 3 lý do, mỗi lý do dưới 25 từ.
User message: normalized_text của lượt quét.""",
        "value_type": "string",
    },
    {
        "key": "blacklist.hard_override_confidence",
        "value": "90",
        "value_type": "int",
    },
    {
        "key": "report.auto_active_threshold",
        "value": "3",
        "value_type": "int",
    },
    {
        "key": "report.community_confidence",
        "value": "70",
        "value_type": "int",
    },
    {
        "key": "ratelimit.report_hourly",
        "value": "5",
        "value_type": "int",
    },
    {
        "key": "otp.ttl_seconds",
        "value": "300",
        "value_type": "int",
    },
    {
        "key": "otp.max_send_per_10min",
        "value": "3",
        "value_type": "int",
    },
    {
        "key": "otp.max_wrong_attempts",
        "value": "5",
        "value_type": "int",
    },
    {
        "key": "recommended_action.an_toan",
        "value": "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân.",
        "value_type": "string",
    },
    {
        "key": "recommended_action.nghi_ngo",
        "value": "Có dấu hiệu đáng ngờ. Đừng bấm link và đừng cung cấp thông tin. Hãy hỏi lại người thân hoặc gọi số tổng đài chính thức.",
        "value_type": "string",
    },
    {
        "key": "recommended_action.nguy_hiem",
        "value": "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp mã OTP. Hãy xóa tin nhắn và chặn số này.",
        "value_type": "string",
    },
]


app_config_table = sa.table(
    "app_config",
    sa.column("key", sa.String(length=100)),
    sa.column("value", sa.Text()),
    sa.column("value_type", sa.String(length=20)),
)


def upgrade() -> None:
    op.bulk_insert(app_config_table, APP_CONFIG)


def downgrade() -> None:
    keys = [item["key"] for item in APP_CONFIG]

    op.execute(
        sa.text(
            "DELETE FROM app_config WHERE key = ANY(:keys)"
        ).bindparams(
            keys=keys
        )
    )