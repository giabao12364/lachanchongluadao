import uuid
import sys
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.db_models import ScamPattern


SEED_PATTERNS = [
    {
        "title": "Giả danh Công an, Viện kiểm sát đe dọa liên quan vụ án",
        "category": "mao_danh",
        "image_url": "https://storage.googleapis.com/lachanchongluadao/patterns/giadanh_congan.png",
        "description": "Kẻ gian giả danh cán bộ Công an, Viện kiểm sát gọi điện đe dọa nạn nhân liên quan đến đường dây tội phạm và yêu cầu chuyển tiền xác minh.",
        "signs": "- Cuộc gọi từ số điện thoại lạ hoặc giả mạo đầu số cơ quan công quyền.\n- Thông báo nạn nhân đang bị điều tra về hành vi rửa tiền, buôn lậu.\n- Yêu cầu giữ bí mật tuyệt đối, không được kể với người thân.\n- Yêu cầu chuyển toàn bộ tiền vào 'tài khoản tạm giữ của cơ quan điều tra'.",
        "example_content": "Tôi là Trung úy Nguyễn Văn A, cán bộ Cục Cảnh sát điều tra. Tài khoản ngân hàng của anh/chị đang liên quan đến đường dây rửa tiền 5 tỷ đồng. Yêu cầu chuyển ngay số tiền hiện có sang STK 1023xxxxxx của Ngân hàng Nhà nước để phục vụ công tác kiểm toán, nếu không sẽ ra lệnh bắt tạm giam trong ngày.",
        "recommended_action": "- Cơ quan Công an, Viện kiểm sát KHÔNG bao giờ làm việc qua điện thoại và KHÔNG yêu cầu chuyển tiền.\n- Tuyệt đối không làm theo hướng dẫn, không chuyển tiền.\n- Cúp máy lập tức và báo cho cơ quan Công an gần nhất.",
        "is_active": True
    },
    {
        "title": "Tuyển cộng tác viên chốt đơn hàng online chiết khấu cao",
        "category": "tuyen_dung",
        "is_active": True,
        "description": "Chiêu trò tuyển cộng tác viên làm việc tại nhà với thu nhập hấp dẫn, dụ dỗ nạp tiền chốt đơn rồi chiếm đoạt.",
        "signs": "- Quảng cáo việc nhẹ lương cao, chỉ cần điện thoại/máy tính chốt đơn trên Shopee, Lazada, TikTok.\n- Trả hoa hồng sòng phẳng cho 1-2 đơn hàng giá trị nhỏ đầu tiên để tạo niềm tin.\n- Đơn hàng tiếp theo có giá trị lớn hơn nhiều, ép nạp thêm tiền với lý do 'lỗi hệ thống', 'chưa đủ cú pháp'.",
        "example_content": "Tuyển 5 CTV chốt đơn Shopee tại nhà. Lương 300k - 800k/ngày. Đơn 1: Chuyển 200k nhận lại 240k. Đơn 2: Chuyển 10 triệu nhận 12.5 triệu. Tuy nhiên khi nạp 10 triệu, hệ thống báo 'Lỗi cú pháp', yêu cầu nạp thêm 20 triệu để giải ngân toàn bộ.",
        "recommended_action": "- Cảnh giác với tất cả công việc tuyển dụng yêu cầu nạp tiền cọc hoặc ứng tiền mua hàng trước.\n- Không chuyển tiền cho người tuyển dụng lạ trên mạng xã hội."
    },
    {
        "title": "Giả danh Ngân hàng gửi SMS Brandname chứa link phishing",
        "category": "mao_danh",
        "is_active": True,
        "description": "Kẻ lừa đảo chèn tin nhắn giả mạo vào luồng SMS Brandname của ngân hàng nhằm đánh cắp thông tin tài khoản.",
        "signs": "- Tin nhắn hiển thị trùng tên Brandname ngân hàng thật (VCB, MBBank, Agribank...).\n- Nội dung cảnh báo khẩn cấp: tài khoản bị khóa, đăng nhập lạ, cập nhật sinh trắc học.\n- Chứa đường link giả mạo gần giống website thật (ví dụ: vietcombank-smartbanking.top).",
        "example_content": "[Vietcombank]: Tai khoan cua Quy khach hien tai bi khoi tao tren thiet bi khac. Neu khong phai ban thao tac, vui long truy cap https://vcb-digibank-security.info de xac minh va huy lenh.",
        "recommended_action": "- Ngân hàng KHÔNG bao giờ gửi SMS kèm đường link yêu cầu đăng nhập tài khoản.\n- Tuyệt đối không nhấp vào đường link trong tin nhắn và không cung cấp mã OTP/mật khẩu."
    },
    {
        "title": "Thông báo trúng thưởng tri ân từ các thương hiệu lớn",
        "category": "trung_thuong",
        "is_active": True,
        "description": "Gửi thông báo trúng thưởng giá trị cao và yêu cầu nạn nhân nộp các khoản phí trước khi nhận quà.",
        "signs": "- Thông báo trúng thưởng xe máy, điện thoại cao cấp dù không tham gia chương trình nào.\n- Bắt buộc nộp các khoản 'phí vận chuyển', 'thuế thu nhập cá nhân' hoặc 'phí hồ sơ' trước.",
        "example_content": "Chúc mừng SĐT 0912xxx888 đã may mắn trúng 01 xe máy SH 125i từ chương trình 'Tri ân khách hàng Điện Máy Xanh'. Vui lòng chuyển 2.500.000 VNĐ phí hồ sơ và vận chuyển vào STK 9988xxx để nhận giải.",
        "recommended_action": "- Bất kỳ chương trình trúng thưởng nào yêu cầu nộp tiền trước đều là lừa đảo.\n- Xác minh trực tiếp với hotline chính thức của thương hiệu."
    },
    {
        "title": "Bẫy vay tiền online lãi suất siêu thấp, duyệt cấp tốc",
        "category": "tin_dung_den",
        "is_active": True,
        "description": "Quảng cáo ứng dụng/web vay tiền duyệt siêu nhanh nhưng sau đó viện lý do sai hồ sơ để thu phí liên tục.",
        "signs": "- Cho vay tiền không cần thế chấp, lãi suất siêu rẻ, giải ngân trong 5 phút.\n- Sau khi bấm vay, app báo 'Thành công' nhưng tiền không về tài khoản.\n- Nhân viên hỗ trợ báo do nhập sai số tài khoản/ngân hàng và yêu cầu nạp 'phí sửa hồ sơ'.",
        "example_content": "Khoản vay 50.000.000đ đã được duyệt. Tuy nhiên do bạn nhập sai số tài khoản ngân hàng nhận tiền, hệ thống bị tạm khóa. Vui lòng chuyển 5.000.000đ phí xác minh để mở khóa tiền vay.",
        "recommended_action": "- Chỉ vay tiền tại các tổ chức tín dụng được Ngân hàng Nhà nước cấp phép.\n- Không chuyển bất kỳ khoản phí nào trước khi nhận được tiền vay."
    },
    {
        "title": "Mạo danh nhân viên viễn thông hỗ trợ nâng cấp SIM 4G/5G",
        "category": "mao_danh",
        "is_active": True,
        "description": "Lừa đảo nâng cấp SIM miễn phí tại nhà nhằm chiếm đoạt quyền kiểm soát SIM và nhận mã OTP ngân hàng.",
        "signs": "- Gọi điện tự xưng là nhân viên Viettel, Vinaphone, MobiFone hỗ trợ nâng cấp SIM 4G/5G miễn phí.\n- Yêu cầu nhắn tin theo cú pháp thay đổi phôi SIM do kẻ gian cung cấp.",
        "example_content": "Chào anh/chị, em là nhân viên Viettel. Để tránh bị gián đoạn dịch vụ, anh/chị vui lòng soạn tin nhắn theo cú pháp: TP <mã_phôi_sim> gửi 901 để được nâng cấp 5G miễn phí.",
        "recommended_action": "- Không làm theo hướng dẫn nhắn tin đổi phôi SIM từ người lạ.\n- Thực hiện chuyển đổi SIM trực tiếp tại các điểm giao dịch chính thức của nhà mạng."
    },
    {
        "title": "Đầu tư tài chính, chứng khoán, tiền điện tử cam kết bao lời",
        "category": "dau_tu",
        "is_active": True,
        "description": "Lôi kéo tham gia các sàn giao dịch ảo, cam kết lợi nhuận cố định siêu cao rồi khóa tài khoản chiếm đoạt tiền.",
        "signs": "- Mời vào các nhóm Zalo/Telegram có nhiều 'chuyên gia' đọc lệnh chuẩn xác.\n- Cam kết lợi nhuận 10% - 30%/tháng, bao nạp rút và không rủi ro.\n- Thời gian đầu cho rút tiền nhỏ rất nhanh, đến khi nạp số tiền lớn thì chặn rút.",
        "example_content": "Đầu tư AI Trading Forex 4.0, lợi nhuận 3%/ngày. Nạp 10 triệu rút được ngay 11.5 triệu sau 24h. Nhưng khi nạp 200 triệu, sàn báo 'Hệ thống bảo trì' hoặc yêu cầu đóng 30% thuế lợi nhuận mới cho rút.",
        "recommended_action": "- Tuyệt đối không đầu tư vào các sàn giao dịch không rõ nguồn gốc, chưa được pháp luật Việt Nam công nhận.\n- Cảnh giác với tất cả các mô hình hứa hẹn lợi nhuận cao bất thường."
    },
    {
        "title": "Mạo danh người thân, bạn bè nhắn tin vay tiền khẩn cấp",
        "category": "mao_danh",
        "is_active": True,
        "description": "Hack tài khoản mạng xã hội hoặc tạo tài khoản giả mạo người thân để nhắn tin mượn tiền gấp.",
        "signs": "- Nhắn tin qua Facebook, Zalo với lý do khẩn cấp: tai nạn, cấp cứu, hết tiền khi di chuyển.\n- Dùng chiêu trò Deepfake gọi video ngắn vài giây rồi báo mạng yếu cúp máy.\n- Tên tài khoản ngân hàng nhận tiền không phải tên của người thân.",
        "example_content": "Alo bạn ơi, tớ đang đi đường thì bị va chạm giao thông cần chuyển gấp 5 triệu trả tiền viện phí. Số tài khoản khác tên vì tớ nhờ tài khoản của bác sĩ tiếp nhận điều trị...",
        "recommended_action": "- Gọi điện thoại thông thường (qua sóng di động) để xác minh lại chính chủ.\n- Không chuyển tiền vào tài khoản đứng tên người lạ."
    },
    {
        "title": "Thông báo phạt nguội vi phạm giao thông qua điện thoại",
        "category": "mao_danh",
        "is_active": True,
        "description": "Giả danh Cảnh sát giao thông gọi điện yêu cầu nộp tiền phạt nguội trực tuyến để chiếm đoạt tiền.",
        "signs": "- Gọi điện thông báo phương tiện của bạn vi phạm giao thông đã quá hạn xử lý.\n- Đe dọa sẽ bị tước bằng lái, khóa tài khoản hoặc xử lý hình sự.\n- Yêu cầu nộp tiền phạt qua link liên kết hoặc chuyển khoản trực tiếp.",
        "example_content": "Cục Cảnh sát giao thông thông báo: Xe ô tô biển số xxA-xxxxx của bạn đã vi phạm vượt đèn đỏ ngày 15/05. Vui lòng bấm phím 9 để nộp phạt trực tuyến hoặc truy cập http://csgt-phatnguoi.site.",
        "recommended_action": "- Cơ quan Cảnh sát giao thông KHÔNG gọi điện thông báo phạt nguội và KHÔNG yêu cầu chuyển khoản nộp phạt.\n- Tra cứu phạt nguội tại Cổng thông tin Cục Cảnh sát giao thông (csgt.vn)."
    },
    {
        "title": "Dịch vụ 'Giải cứu' lấy lại tiền đã bị lừa đảo trực tuyến",
        "category": "lua_dao_dich_vu",
        "is_active": True,
        "description": "Đóng giả luật sư, chuyên gia an ninh mạng cam kết lấy lại tiền bị lừa nhưng thực chất là lừa đảo lần hai.",
        "signs": "- Đăng bài quảng cáo trên Facebook/TikTok nhận hỗ trợ thu hồi tiền bị treo trên ứng dụng lừa đảo.\n- Yêu cầu nạn nhân ứng trước 'phí hồ sơ', 'phí phần mềm hack' hoặc 'phí uỷ quyền luật sư'.",
        "example_content": "Văn phòng Luật sư A hỗ trợ nạn nhân bị lừa đảo chốt đơn, sàn đầu tư lấy lại 100% tiền bị treo. Phí dịch vụ 5% thanh toán sau khi lấy lại tiền, nhưng yêu cầu nạp trước 2 triệu tiền phí lập hồ sơ công an.",
        "recommended_action": "- Không tin bất kỳ dịch vụ 'lấy lại tiền lừa đảo' nào trên mạng xã hội.\n- Chỉ có cơ quan Công an mới có thẩm quyền điều tra và xử lý các vụ án lừa đảo."
    }
]


def seed_scam_patterns():
    db: Session = SessionLocal()
    try:
        print("🚀 Bắt đầu nạp dữ liệu seed cho scam_pattern...")
        added_count = 0
        
        for pattern_data in SEED_PATTERNS:
            # Kiểm tra trùng lặp dựa trên title
            existing = db.query(ScamPattern).filter(ScamPattern.title == pattern_data["title"]).first()
            if not existing:
                pattern = ScamPattern(
                    id=uuid.uuid4(),
                    title=pattern_data["title"],
                    category=pattern_data["category"],
                    image_url=pattern_data.get("image_url"),
                    description=pattern_data["description"],
                    signs=pattern_data["signs"],
                    example_content=pattern_data["example_content"],
                    recommended_action=pattern_data["recommended_action"],
                    is_active=pattern_data["is_active"]
                )
                db.add(pattern)
                added_count += 1
        
        db.commit()
        print(f"✅ Đã nạp thành công {added_count} bài viết scam_pattern (is_active=True, đủ 3 khối)!")
    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi khi nạp dữ liệu seed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_scam_patterns()