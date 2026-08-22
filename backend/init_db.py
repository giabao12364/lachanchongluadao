"""Tao tables va seed data ban dau cho database."""
from app.core.database import Base, engine, SessionLocal
from app.models import db_models  # noqa: F401 - import de SQLAlchemy biet models
from datetime import datetime
import uuid

print("[1/3] Tao tables (neu chua co)...")
Base.metadata.create_all(bind=engine)
print("      OK: Da tao/xac nhan tables.")

db = SessionLocal()
try:
    print("[2/3] Kiem tra va tao ScoringRule mac dinh (neu chua co)...")
    from app.models.db_models import ScoringRule, ScamPattern
    count_rules = db.query(ScoringRule).count()
    if count_rules == 0:
        default_rules = [
            ScoringRule(id=uuid.uuid4(), rule_code="RULE_LINK", rule_name="Chua link kiem cho",
                        description="Noi dung chua link url kiem tra tinh an toan", category="LINK",
                        score_value=15.0, condition_pattern=r"https?://", is_active=True, priority=10),
            ScoringRule(id=uuid.uuid4(), rule_code="RULE_OTP", rule_name="YeU cau OTP",
                        description="Noi dung yeu cau nhap OTP", category="PHISHING",
                        score_value=40.0, condition_pattern=r"OTP|m[aả]? x[áa]c th?c", is_active=True, priority=20),
            ScoringRule(id=uuid.uuid4(), rule_code="RULE_BANK", rule_name="Ke hoach tai chinh/ngan hang",
                        description="Co the la lua dao tai chinh ngan hang", category="PHISHING",
                        score_value=30.0, condition_pattern=r"ng[aâ]n h[aà]ng|t[aà]i kho?a?n|chuy?e?n kho?a?n|STK",
                        is_active=True, priority=15),
            ScoringRule(id=uuid.uuid4(), rule_code="RULE_AUTHORITY", rule_name="Gia mao co quan quyen luc",
                        description="Gia mao cong an, vien kiem sat, toa an", category="IMPERSONATION",
                        score_value=35.0, condition_pattern=r"c[oô]ng an|vi[eê]n ki[eê]m s[aá]t|t[oô]a [aâ]n|quy[eê]n l[uụ]c",
                        is_active=True, priority=18),
        ]
        for r in default_rules:
            db.add(r)
        db.commit()
        print(f"      OK: Da them {len(default_rules)} ScoringRule mac dinh.")
    else:
        print(f"      OK: Da co {count_rules} ScoringRule, bo qua.")

    print("[3/3] Kiem tra va tao ScamPattern mau (neu chua co)...")
    count_patterns = db.query(ScamPattern).count()
    if count_patterns == 0:
        default_patterns = [
            ScamPattern(id=uuid.uuid4(), title="Giả mạo cơ quan quyền lực", category="IMPERSONATION",
                        image_url=None,
                        description="Kẻ gian giả mạo công an, viện kiểm sát, tòa án, báo cáo bạn có liên quan đến vụ án, yêu cầu chuyển tiền để giải quyết nhanh.",
                        signs="1. Tự gọi là công an/kiểm sát/toa án\n2. Đe dọa khởi tố/bắt giữ\n3. Yêu cầu chuyển tiền 'nộp bảo lãnh'\n4. Yêu cầu không nói với ai",
                        example_content="Dạ em là công an huyện XXX, anh chị có liên quan đến vụ rửa tiền, vui lòng chuyển 50tr vào tài khoản STK XXX để được giải quyết.",
                        recommended_action="1. GẮC LẠI ĐIỆN THOẠI NGAY LẬP TỨC\n2. Gọi 113 để xác minh\n3. TUYỆT ĐỐI không chuyển tiền cho bất kỳ ai",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
            ScamPattern(id=uuid.uuid4(), title="Lừa đảo tín dụng/ngân hàng giả mạo", category="BANK_PHISH",
                        image_url=None,
                        description="Kẻ gian gửi SMS/link giả mạo ngân hàng, yêu cầu xác minh thông tin, cập nhật tài khoản hoặc OTP.",
                        signs="1. Link trông giống ngân hàng nhưng URL khác thường\n2. Yêu cầu nhập OTP/Mat khau\n3. Đe dọa khóa tài khoản nếu không làm",
                        example_content="Vietcombank thong bao tai khoan cua quy vi se bi khoa trong 24h. Vui long cap nhat tai khoan tai: https://fake-vcb-example.com/update",
                        recommended_action="1. KHÔNG bấm link trong SMS/email\n2. Truy cập app/website chính thức của ngân hàng\n3. Gọi tổng đài chính thức để xác minh",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
            ScamPattern(id=uuid.uuid4(), title="Lừa đảo mua bán online", category="ONLINE_SHOP",
                        image_url=None,
                        description="Quảng cáo giá quá rẻ, yêu cầu chuyển khoản cọc trước rồi block liên lạc.",
                        signs="1. Giá rẻ bất thường (30-50% thị trường)\n2. Chỉ chấp nhận chuyển khoản trước\n3. Shop mới tạo, ít đánh giá\n4. Lý do 'hàng tồn kho', 'thanh lý'",
                        example_content="Iphone 15 Pro Max gia 3 trieu dong, can thanh ly gap. Moi nguoi quan tam chuyen khoan 500k coc de giu hang.",
                        recommended_action="1. So sánh giá với thị trường (rẻ quá là lừa đảo!)\n2. Giao hàng COD: nhận hàng mới trả tiền\n3. Mua trên sàn uy tín, không giao dịch ngoài messenger",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
            ScamPattern(id=uuid.uuid4(), title="Lừa đảo tình cảm (dating scam)", category="DATING",
                        image_url=None,
                        description="Kẻ gian tạo hồ sơ đẹp, tán tỉnh, rồi gạ gẫm gặp khó khăn cần tiền gấp.",
                        signs="1. Nhanh chóng nói yêu, kết hôn\n2. Không bao giờ gặp mặt/video call\n3. Cuộc sống quá 'hoàn hảo'\n4. Gặp gia cảnh liên tục cần tiền",
                        example_content="Ong xa oi, me em vua vao benh vien phau thuat, em can them 20 trieu cho phi benh vien. Ong giup em voi, ve em se tra lai ngay.",
                        recommended_action="1. KHÔNG bao giờ chuyển tiền cho người chưa gặp mặt\n2. Yêu cầu video call thường xuyên\n3. Nếu bị dính vào, chat để lấy bằng chứng, báo công an ngay",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
            ScamPattern(id=uuid.uuid4(), title="Lừa đảo tuyển dụng làm việc online", category="FAKE_JOB",
                        image_url=None,
                        description="Tuyển dụng công việc lương cao nhẹ nhàng, yêu cầu nộp phí, mở tài khoản rồi chiếm đoạt tiền.",
                        signs="1. Thu nhập cao, làm việc tại nhà, không cần kinh nghiệm\n2. Yêu cầu nộp phí đặt cọc/hồ sơ\n3. Hướng dẫn 'rủ rê bạn bè' (đa cấp)\n4. Hệ thống điểm thưởng kiểu tiền ảo",
                        example_content="TUYEN DUNG NHAN VIEN ONLINE, LUONG 25-50TR/THANG. Lam tai nha, khong can kinh nghiem. Chi can nap 500k mo tai khoan la bat dau duoc ngay!",
                        recommended_action="1. Bất kỳ công việc nào yêu cầu NỘP PHÍ trước là LỪA ĐẢO 99%\n2. Không tải app từ link không rõ nguồn gốc\n3. Kiểm tra thông tin công ty trên mạng trước khi ứng tuyển",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
            ScamPattern(id=uuid.uuid4(), title="Lừa đảo gọi nhỡ/nhắn tin nhỡ bạn bè", category="WRONG_NUMBER",
                        image_url=None,
                        description="Gọi/nhắn tin sai số, sau đó tán tỉnh kết bạn dài ngày rồi gạ gẫm tiền.",
                        signs="1. 'Nhầm số' nhưng duy trì liên lạc\n2. Nhanh chóng thân thiết\n3. Cuộc sống có nhiều drama, gặp may rủi liên tục\n4. Cuối cùng cũng cần tiền",
                        example_content="A oi, e nhan tin nham so roi nhung thay anh rat thu vi, chung ta lam ban nha. Hom sau e gap kho, can 5tr...",
                        recommended_action="1. Nếu tin nhắn/số lạ tán tỉnh nhanh → CẨN THẬN CAO\n2. KHÔNG chia sẻ thông tin cá nhân, ngân hàng\n3. Khi gặp yêu cầu tiền → CHẤT ĐỂN LIÊN LẠC",
                        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()),
        ]
        for p in default_patterns:
            db.add(p)
        db.commit()
        print(f"      OK: Da them {len(default_patterns)} ScamPattern mau.")
    else:
        print(f"      OK: Da co {count_patterns} ScamPattern, bo qua.")

    print("\n========================================")
    print("  HOAN TAT! Database da san sang.")
    print("========================================")
finally:
    db.close()
