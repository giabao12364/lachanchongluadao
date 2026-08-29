"""Tao tables va seed data ban dau theo schema MỚI từ Spec Master Build-Spec v2.0.

Auto-detect DB cũ: Nếu bảng tồn tại có column tên cũ (condition_pattern, entity_value, risk_level...)
hoặc thiếu cột mới (pattern/normalized_value/platform/confidence...) → DROP hết bảng + recreate 100%
→ Không cần ALTER rườm rà, không cần alembic downgrade, match model db_models.py 100%.
"""
from app.core.database import Base, engine, SessionLocal
from app.models import db_models  # noqa: F401
from sqlalchemy import inspect, text
from datetime import datetime
import uuid


def _need_full_rebuild(inspector, tables_expected):
    """Return True nếu phát hiện schema cũ mismatch với spec mới → DROP+CREATE lại từ đầu."""
    existing_tables = set(inspector.get_table_names())
    if not (existing_tables & tables_expected):
        return False
    bad_markers = {
        "scoring_rule": ["condition_pattern", "score_value", "rule_name", "category", "priority"],
        "scan_entity": ["entity_value", "matched_blacklist_id", "risk_level"],
        "scan_signal": ["signal_code", "signal_name", "score_contribution", "description", "severity", "rule_id"],
        "scan_result": ["total_score", "summary", "is_scam", "confidence"],
        "scan_request": ["scan_type", "content_hash", "client_ip", "user_agent"],
        "blacklist_entity": ["entity_value", "risk_level", "source", "description"],
        "scam_report": ["reporter_id", "title", "scam_type", "loss_amount", "currency", "evidence_urls", "contact_info", "report_count", "first_seen_at", "last_seen_at", "reviewed_at", "review_note"],
        "app_user": ["full_name", "email", "avatar_url", "password_hash", "is_verified", "role"],
        "device": ["device_id", "device_name", "os_type", "os_version", "app_version", "fcm_token", "is_active", "last_login_at"],
        "otp_request": ["otp_code", "is_used", "used_at"],
        "scam_pattern": [],
        "app_config": ["description", "is_public", "config_key", "config_value", "config_type"],
    }
    missing_required = {
        "scoring_rule": ["pattern", "pattern_type", "reason_text"],
        "scan_entity": ["raw_value", "normalized_value"],
        "scan_signal": ["source", "rule_code", "reason_text", "evidence"],
        "scan_result": ["rule_score", "ai_score", "ai_available", "has_hard_override"],
        "scan_request": ["device_id", "normalized_text", "status"],
        "blacklist_entity": ["normalized_value", "confidence", "note"],
        "scam_report": ["entity_type", "normalized_value", "status"],
        "app_user": ["display_name"],
        "device": ["device_uid", "platform"],
        "otp_request": ["otp_hash", "purpose", "attempt_count", "consumed_at"],
        "scam_pattern": ["signs", "example_content", "recommended_action"],
        "app_config": [],
    }
    for tbl in tables_expected:
        if tbl not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(tbl)}
        old = bad_markers.get(tbl, [])
        if cols & set(old):
            return True
        need = missing_required.get(tbl, [])
        if need and not (set(need) <= cols):
            return True
    return False


print("[1/4] Kiem tra schema scoring_rule & tables (tự động DROP nếu là schema cũ)...")
inspector = inspect(engine)
expected_tables = {
    "app_user", "device", "scan_request", "scan_entity", "scan_signal", "scan_result",
    "blacklist_entity", "scoring_rule", "app_config", "scam_report", "scam_pattern", "otp_request",
}
if _need_full_rebuild(inspector, expected_tables):
    print("     ⚠️  Phát hiện DB schema cũ (không match spec 12 bảng). DROP toàn bộ 12 bảng + enums cũ để tạo lại từ đầu.")
    with engine.begin() as conn:
        conn.execute(text("SET client_min_messages TO WARNING"))
        for tbl in sorted(expected_tables, reverse=True):
            conn.execute(text(f'DROP TABLE IF EXISTS "{tbl}" CASCADE'))
        conn.commit()
    print("     ✅ Đã DROP sạch 12 bảng schema cũ.")
Base.metadata.create_all(bind=engine)
print("     ✅ Đã tạo/xác nhận 12 bảng theo đúng spec mới.")

db = SessionLocal()
try:
    print("[2/4] Seed 11 ScoringRule BR-01-10 (xóa cũ, tạo mới)...")
    from app.models.db_models import ScoringRule, ScamPattern, AppConfig
    count_rules = db.query(ScoringRule).count()
    if count_rules > 0:
        print(f"     INFO: DB đã có {count_rules} rule cũ. Xóa sạch để tạo lại 11 rule.")
        db.query(ScoringRule).delete()
        db.commit()

    default_rules = [
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_SHORT_URL",
            description="Nội dung chứa link rút gọn (bit.ly, tinyurl, t.co, cutt.ly...) - rất thường dùng trong lừa đảo",
            pattern="bit.ly,tinyurl.com,t.co,cutt.ly,goo.gl,ow.ly,is.gd,buff.ly,rebrand.ly,tiny.cc,clk.shopee,s.shopee,zalo.me,fb.me,wa.me",
            pattern_type="keyword_list",
            score=25, is_active=True,
            reason_text="Thông báo chứa link rút gọn (bit.ly, t.co...) – đây là dấu hiệu phổ biến của lừa đảo, tuyệt đối không bấm nếu không chắc chắn nguồn gốc.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_URGENCY",
            description="Nội dung yêu cầu thao tác gấp, đe dọa sẽ xảy ra hậu quả xấu nếu không làm",
            pattern="trong vòng 24h,24h,24 giờ,ngay lập tức,khẩn cấp,sẽ bị khóa,không trễ hạn,hết hạn,đe dọa,bảo mật,liền tay,ngay bây giờ,sớm nhất,gấp gáp",
            pattern_type="keyword_list",
            score=20, is_active=True,
            reason_text="Nội dung dùng từ ngữ khẩn cấp, đe dọa để gây hoảng loạn và ép bạn thao tác vội vàng – hãy bình tĩnh và kiểm tra lại nguồn gốc.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_ACCOUNT_THREAT",
            description="Lừa đảo đe dọa khóa/xác minh tài khoản để hỏi thông tin nhạy cảm",
            pattern="tài khoản của bạn bị khóa,tài khoản của bạn sẽ bị khóa,bị đình chỉ,tài khoản bị hạn chế,khóa tài khoản của bạn,xác minh tài khoản,cập nhật thông tin tài khoản,xác thực tài khoản",
            pattern_type="keyword_list",
            score=25, is_active=True,
            reason_text="Đe dọa khóa/xác minh tài khoản để ép bạn tiết lộ thông tin nhạy cảm – dấu hiệu lừa đảo phổ biến.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_PRIZE",
            description="Thông báo trúng thưởng, nhận quà mà không tham gia chương trình nào",
            pattern="chúc mừng bạn đã trúng,trúng thưởng,quà tặng bất ngờ,bạn đã trúng,nhận thưởng,trúng giải,giải thưởng,iPhone,Samsung Galaxy,điện thoại tặng",
            pattern_type="keyword_list",
            score=25, is_active=True,
            reason_text="Thông báo trúng thưởng/quà tặng bất ngờ là chiêu lừa đảo phổ biến để chiêu dụ nạn nhân nộp phí/nhập thông tin.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_ASK_OTP",
            description="Yêu cầu chia sẻ OTP, mật khẩu, mã xác minh - LỪA ĐẢO 100% nếu yêu cầu đọc/chia sẻ qua điện thoại",
            pattern="mã otp,cung cấp mã otp,mã xác minh,gửi mã cho,đọc mã otp,nhập mã otp,yêu cầu mã otp,chia sẻ otp,mã bảo mật,mật khẩu của bạn,mã 6 chữ số",
            pattern_type="keyword_list",
            score=40, is_active=True,
            reason_text="Tin nhắn yêu cầu cung cấp mã OTP hoặc mật khẩu – TUYỆT ĐỐI không chia sẻ, đây chắc chắn là lừa đảo.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_ASK_TRANSFER",
            description="Lừa đảo yêu cầu chuyển khoản, nộp tiền, đặt cọc để nhận thưởng hoặc giải quyết vấn đề",
            pattern="chuyển tiền,đóng phí,đặt cọc,phí nhận thưởng,nộp phí trước,chuyển khoản,nộp tiền,đặt trước,chi trả trước,phí xử lý,phí ship,nạp tiền",
            pattern_type="keyword_list",
            score=30, is_active=True,
            reason_text="Tin nhắn yêu cầu chuyển tiền hoặc đặt cọc trước khi nhận điều gì đó – dấu hiệu lừa đảo phổ biến.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_IMPERSONATE_BANK",
            description="Giả mạo tên ngân hàng/cơ quan nhà nước để tạo lòng tin",
            pattern="vietcombank,techcombank,bidv,agribank,vietinbank,sacombank,ngân hàng thông báo,vcb,momo,zalopay,công an,viện kiểm sát,tòa án,quyền lực,thuế,soi chống tin,kscn",
            pattern_type="keyword_list",
            score=30, is_active=True,
            reason_text="Tin nhắn giả danh ngân hàng hoặc cơ quan quyền lực để tạo lòng tin – hãy gọi tổng đài chính thức để xác minh.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_LOOKALIKE_DOMAIN",
            description="Website giả mạo thương hiệu (vietcombank-vn, bidv-login...) - domain gõ giống nhưng không phải trang thật",
            pattern=r"(vietcombank|techcombank|bidv|agribank|vietinbank|sacombank|momo|zalopay|shopee|lazada|tiki|facebook|tiktok|instagram)[^\s]*\.(?!com\.vn|vn|com\.sg|my|jp|net|org)[a-z]{2,}(?:/|$)",
            pattern_type="regex",
            score=35, is_active=True,
            reason_text="Địa chỉ trang web giả giống tên thương hiệu nhưng không phải trang thật – tuyệt đối không nhập thông tin cá nhân/OTP.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_SUSPICIOUS_TLD",
            description="Website dùng tên miền rủi ro không phải .com / .vn / .com.vn thường gặp lừa đảo",
            pattern=".top,.xyz,.icu,.tk,.info,.online,.club,.work,.ru,.cn,.cc,.ga,.ml,.cf,.gq,.site,.biz",
            pattern_type="tld_list",
            score=15, is_active=True,
            reason_text="Địa chỉ trang web dùng đuôi lạ thường gặp ở các trang lừa đảo – hãy kiểm tra kỹ nguồn gốc trước khi thao tác.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_BANK_ACCOUNT",
            description="Nội dung chứa STK/số tài khoản ngân hàng (6-20 chữ số) - cần kiểm tra kỹ người nhận",
            pattern=r"(stk|số? tài khoản|tài khoản nhận|account number)\s*[:#]?\s*\d{6,20}|\b\d{9,16}\b",
            pattern_type="regex",
            score=15, is_active=True,
            reason_text="Tin nhắn có kèm số tài khoản ngân hàng – hãy xác minh kỹ người nhận trước khi chuyển khoản.",
        ),
        ScoringRule(
            id=uuid.uuid4(), rule_code="R_JOB_SCAM",
            description="Lừa đảo tuyển dụng công việc nhẹ lương cao/làm nhiệm vụ nhận hoa hồng - đa cấp",
            pattern="việc nhẹ lương cao,làm nhiệm vụ nhận hoa hồng,việc làm tại nhà thu nhập cao,công việc online,nhận hoa hồng,thưởng đơn hàng,làm thêm tại nhà,rủ rê bạn bè,kiếm tiền online nhanh,đa cấp,nhiệm vụ",
            pattern_type="keyword_list",
            score=25, is_active=True,
            reason_text="Mẫu tuyển dụng việc nhẹ lương cao là chiêu lừa đảo phổ biến, thường liên quan đến đa cấp hoặc chiếm đoạt tiền nộp trước.",
        ),
    ]
    for r in default_rules:
        db.add(r)
    db.commit()
    print(f"     ✅ Đã xóa + tạo lại {len(default_rules)} ScoringRule theo đúng BR-01-10.")

    print("[3/4] Seed AppConfig ngưỡng mặc định (nếu chưa có) - L0.3 mục 7 cấm hardcode:")
    thresholds = [
        ("threshold.nghi_ngo", "40", "int", "Ngưỡng tối thiểu để xếp mức Nghi ngờ (default 40)"),
        ("threshold.nguy_hiem", "80", "int", "Ngưỡng tối thiểu để xếp mức Nguy hiểm (default 80)"),
        ("pipeline.ai_weight", "0.6", "float", "Hệ số nhân điểm AI khi kết hợp với rule score (default 0.6)"),
        ("pipeline.max_final_score", "100", "int", "Trần điểm cuối cùng (default 100)"),
        ("report.auto_blacklist_reports", "3", "int", "Số report độc lập đủ để auto-active blacklist (DD-06)"),
        ("report.auto_blacklist_confidence", "70", "int", "Confidence gán khi auto-active blacklist (DD-06)"),
        ("otp.expire_minutes", "5", "int", "Thời gian hết hạn OTP (phút)"),
        ("otp.max_attempts", "5", "int", "Số lần thử OTP tối đa trước khi vô hiệu hóa"),
    ]
    seeded_cfg = 0
    for k, v, vt, desc in thresholds:
        exist = db.query(AppConfig).filter(AppConfig.key == k).first()
        if exist is None:
            db.add(AppConfig(key=k, value=v, value_type=vt))
            seeded_cfg += 1
    db.commit()
    print(f"     ✅ Đã seed {seeded_cfg} AppConfig ngưỡng (bỏ qua {len(thresholds)-seeded_cfg} key đã tồn tại).")

    print("[4/4] Seed ScamPattern mẫu mới từ app/db/seed_scam_patterns.py (FR-03)...")
    from app.models.db_models import ScamPattern
    count_old = db.query(ScamPattern).count()
    if count_old > 0:
        print(f"     → DB đang có {count_old} ScamPattern cũ. XÓA SẠCH để nạp 10 mẫu MỚI từ seed_scam_patterns.py...")
        db.query(ScamPattern).delete()
        db.commit()
        print(f"     ✅ Đã xóa {count_old} ScamPattern cũ.")
    from app.db.seed_scam_patterns import seed_scam_patterns
    seed_scam_patterns()
    count_new = db.query(ScamPattern).count()
    print(f"     ✅ Tổng ScamPattern trong DB sau seed: {count_new} (mong đợi 10 mẫu đủ 3 khối, is_active=True)")

    print("\n========================================")
    print("  HOÀN TẤT! Schema 12 bảng + Seed data hoàn thành.")
    print("========================================")
finally:
    db.close()
