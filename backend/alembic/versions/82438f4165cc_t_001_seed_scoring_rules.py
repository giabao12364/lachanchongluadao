"""T-001 seed scoring rules

Revision ID: 82438f4165cc
Revises: 3b1b816ddd54
Create Date: 2026-08-17 14:46:21.919147

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82438f4165cc'
down_revision: Union[str, None] = '3b1b816ddd54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCORING_RULES = [
    {
        "id": uuid.uuid4(),
        "rule_code": "R_SHORT_URL",
        "description": "Link rút gọn (bit.ly, tinyurl, t.co...)",
        "pattern": r"(bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|ow\.ly|cutt\.ly|rebrand\.ly)",
        "pattern_type": "regex",
        "score": 25,
        "reason_text": "Đường link này được rút gọn để che giấu địa chỉ thật.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_URGENCY",
        "description": "Từ khóa khẩn cấp/đe dọa",
        "pattern": "trong vòng 24h,trong 24 giờ,khẩn cấp,ngay lập tức,sẽ bị khóa,hết hạn hôm nay",
        "pattern_type": "keyword_list",
        "score": 20,
        "reason_text": "Tin nhắn tạo cảm giác gấp gáp để bạn không kịp suy nghĩ kỹ.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_ACCOUNT_THREAT",
        "description": "Đe dọa khóa/xác minh tài khoản",
        "pattern": "tài khoản của bạn bị khóa,tài khoản sẽ bị khóa,tài khoản của bạn sẽ bị khóa,xác minh tài khoản,xác minh ngay,tạm khóa tài khoản",
        "pattern_type": "keyword_list",
        "score": 25,
        "reason_text": "Tin nhắn đe dọa khóa tài khoản để khiến bạn lo lắng và làm theo.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_PRIZE",
        "description": "Trúng thưởng/quà bất ngờ",
        "pattern": "chúc mừng bạn đã trúng,trúng thưởng,quà tặng bất ngờ,bạn đã trúng,nhận thưởng",
        "pattern_type": "keyword_list",
        "score": 25,
        "reason_text": "Thông báo trúng thưởng bất ngờ là chiêu lừa phổ biến.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_ASK_OTP",
        "description": "Yêu cầu OTP/mật khẩu",
        "pattern": "mã otp,cung cấp mã otp,mã xác minh,gửi mã cho,đọc mã otp",
        "pattern_type": "keyword_list",
        "score": 40,
        "reason_text": "Tin nhắn yêu cầu cung cấp mã OTP hoặc mật khẩu — không bao giờ nên chia sẻ.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_ASK_TRANSFER",
        "description": "Yêu cầu chuyển tiền/đặt cọc",
        "pattern": "chuyển tiền,đóng phí,đặt cọc,phí nhận thưởng,nộp phí trước",
        "pattern_type": "keyword_list",
        "score": 30,
        "reason_text": "Tin nhắn yêu cầu chuyển tiền hoặc đặt cọc trước khi nhận điều gì đó.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_IMPERSONATE_BANK",
        "description": "Mạo danh ngân hàng/cơ quan",
        "pattern": "vietcombank,techcombank,bidv,agribank,vietinbank,sacombank,ngân hàng thông báo",
        "pattern_type": "keyword_list",
        "score": 30,
        "reason_text": "Tin nhắn giả danh ngân hàng hoặc cơ quan để tạo lòng tin.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_LOOKALIKE_DOMAIN",
        "description": "Domain giả mạo thương hiệu",
        "pattern": r"(vietcombank|techcombank|bidv|agribank)-?[a-z0-9]*\.(top|xyz|icu|tk|info|online)",
        "pattern_type": "regex",
        "score": 35,
        "reason_text": "Địa chỉ trang web giả giống tên ngân hàng nhưng không phải trang thật.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_SUSPICIOUS_TLD",
        "description": "TLD rủi ro (.top .xyz .icu .tk)",
        "pattern": ".top,.xyz,.icu,.tk,.info,.online,.club,.work",
        "pattern_type": "tld_list",
        "score": 15,
        "reason_text": "Địa chỉ trang web dùng đuôi lạ thường gặp ở các trang lừa đảo.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_BANK_ACCOUNT",
        "description": "Có số tài khoản ngân hàng",
        "pattern": r"(stk|số tài khoản|tk số)\s*[:\-]?\s*\d{6,20}",
        "pattern_type": "regex",
        "score": 15,
        "reason_text": "Tin nhắn có kèm số tài khoản ngân hàng để yêu cầu chuyển tiền.",
        "is_active": True,
    },
    {
        "id": uuid.uuid4(),
        "rule_code": "R_JOB_SCAM",
        "description": 'Mẫu "việc nhẹ lương cao"',
        "pattern": "việc nhẹ lương cao,làm nhiệm vụ nhận hoa hồng,việc làm tại nhà thu nhập cao,việc làm tại nhà,cộng tác viên online,thu nhập cao,lương cao",
        "pattern_type": "keyword_list",
        "score": 25,
        "reason_text": "Mẫu quảng cáo việc nhẹ lương cao là chiêu lừa đảo phổ biến.",
        "is_active": True,
    },
]


scoring_rule_table = sa.table(
    "scoring_rule",
    sa.column("id", sa.UUID()),
    sa.column("rule_code", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("pattern", sa.Text()),
    sa.column("pattern_type", sa.String()),
    sa.column("score", sa.Integer()),
    sa.column("reason_text", sa.Text()),
    sa.column("is_active", sa.Boolean()),
)


def upgrade() -> None:
    op.bulk_insert(scoring_rule_table, SCORING_RULES)


def downgrade() -> None:
    op.execute(
        scoring_rule_table.delete().where(
            scoring_rule_table.c.rule_code.in_(
                [rule["rule_code"] for rule in SCORING_RULES]
            )
        )
    )
