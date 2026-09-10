import re
from sqlalchemy.orm import Session
from app.models.db_models import ScoringRule


_DIACRITIC_MAP = {
    "á": "a", "à": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "é": "e", "è": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "í": "i", "ì": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "ó": "o", "ò": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "ú": "u", "ù": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "ý": "y", "ỳ": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "đ": "d",
}


def _strip_diacritics(text: str) -> str:
    if not text:
        return ""
    out_chars = []
    for ch in text:
        low = ch.lower()
        mapped = _DIACRITIC_MAP.get(low)
        if mapped is not None:
            out_chars.append(mapped if low == ch else mapped)
            if ch.isupper() and mapped:
                out_chars[-1] = mapped.upper()
        else:
            out_chars.append(ch)
    return "".join(out_chars)


CORE_RULES = [
    {
        "rule_code": "R_FAKE_POLICE_A06",
        "score": 45,
        "pattern": r"(a06|cuc\s*canh\s*sat|cong\s*an|vien\s*kiem\s*sat|toi\s*pham\s*kinh\s*te|rua\s*tien|tam\s*giu|bat\s*tam\s*giam|tai\s*khoan\s*dieu\s*hanh|khong\s*duoc\s*tuyen\s*bo)",
        "reason_text": "Mạo danh cơ quan công quyền (Công an / A06 / Viện kiểm sát) đe dọa bắt giữ, rửa tiền, chuyển tiền vào tài khoản điều hành — CHẮC CHẮN LỪA ĐẢO.",
    },
    {
        "rule_code": "R_POLICE_SEIZED_DEPOSIT",
        "score": 35,
        "pattern": r"(nop\s*phi\s*tam\s*giu|nop\s*tam\s*giam\s*\d+tr|tai\s*khoan\s*tam\s*giu|chuyen\s*tien\s*(vao|sang)\s*tai\s*khoan\s*(tam\s*giu|dieu\s*hanh|noi\s*bo)|dung\s*(tuyen\s*bo|noi\s*voi)\s*(bat\s*ky\s*ai|nguoi\s*than))",
        "reason_text": "Yêu cầu nộp tiền vào tài khoản tạm giữ / điều hành + cấm thông báo người thân — 100% lừa đảo mạo danh công an.",
    },
    {
        "rule_code": "R_FAKE_RELATIVE_BORROW",
        "score": 45,
        "pattern": r"(mat\s*dien\s*thoai|nhan\s*tin\s*tu\s*so\s*moi|day\s*la\s*(minh|an|lan|hong|hien|thao|mai|tuan|khanh|nam)|chac\s*ban\s*\d+tr|chac\s*em\s*\d+tr|chac\s*anh\s*\d+tr|chac\s*chi\s*\d+tr|tai\s*nan|cap\s*cuu|benh\s*vien\s*[abc]\s*,|dung\s*goi\s*dien\s*cho\s*con|dung\s*goi\s*dien\s*cho\s*anh\s*chau|hoc\s*phi\s*con\s*thieu|vi\s*phat\s*can\s*nop)",
        "reason_text": "Mạo danh người thân / bạn bè qua số mới, lý do khẩn cấp (tai nạn, cấp cứu, học phí, mượn gấp, đổi sim).",
    },
    {
        "rule_code": "R_DEBT_COLLECTION_THREAT",
        "score": 40,
        "pattern": r"(con\s*no\s*\d+tr|den\s*han\s*tra\s*no|chuyen\s*tien\s*(vao|sang)\s*stk|cong\s*ty\s*dieu\s*hanh|dong\s*thap\s*dieu\s*hanh|thu\s*truong\s*(cong\s*ty|cong\s*ty\s*dieu\s*hanh)|den\s*nha\s*hoi\s*no|co\s*(dong\s*doi|canh\s*sat|em\s*anh)\s*theo)",
        "reason_text": "Đòi nợ khống, tự xưng công ty điều hành, đe dọa đến nhà kèm người theo + yêu cầu chuyển STK — lừa đảo chiếm đoạt.",
    },
    {
        "rule_code": "R_OTP_REQUEST_STRONG",
        "score": 40,
        "pattern": r"(ma\s*(otp|xac\s*minh|xac\s*nhan)|otp|ma\s*ot\s*\d+\s*so)[\s\S]{0,80}(cung\s*cap|gui|dua|cho|nhap\s*vao|doc\s*ma|bao\s*ma|xac\s*nhan\s*ma|chia\s*se|\d{5,6}\s*de\s*(huy|xac\s*nhan|kiem\s*soat))",
        "reason_text": "Yêu cầu cung cấp / chia sẻ / đọc / nhập mã OTP — Không bao giờ chia sẻ.",
    },
    {
        "rule_code": "R_OTP_6DIGIT_CONTEXT",
        "score": 25,
        "pattern": r"(ma\s*(otp|xac\s*minh)\s*(la|so)?\s*\d{4,6}|\d{4,6}\s*(la\s*)?ma\s*(otp|xac\s*minh))",
        "reason_text": "Tin nhắn chứa / yêu cầu mã OTP dạng 4-6 chữ số kèm ngữ cảnh xác minh.",
    },
    {
        "rule_code": "R_ROMANCE_FINANCIAL_REQUEST",
        "score": 35,
        "pattern": r"(anh\s*yeu|em\s*yeu|chao\s*(anh|chi)\s*,|em\s*ten\s*\w+\s*\d+t\s*o\s*)[\s\S]{0,200}(chuyen\s*(anh|chi|em)\s*giup|ho\s*tro\s*(em|anh|chi)\s*\d+tr|con\s*thieu\s*\d+tr|(chuyen|gui)\s*ti?e?n\s*vao\s*stk|chuyen\s*(em|anh)\s*\d+tr\s*(stk|tai\s*khoan))",
        "reason_text": "Khiêu dâm / hẹn hò online sau đó đòi chuyển tiền / học phí / viện phí — Romance Scam.",
    },
    {
        "rule_code": "R_COURIER_IMPORT_FEE",
        "score": 40,
        "pattern": r"(buu\s*dien|grab\s*express|shopee\s*express|giaohangnhanh|goi\s*hang\s*nhap\s*khau|phi\s*rut\s*ho|phi\s*nhan\s*hang|chuyen\s*phi\s*\d+tr|goi\s*hang\s*se\s*bi\s*huy|can\s*tra\s*phi)[\s\S]{0,140}(stk|so\s*tai\s*khoan|tk\s*\d|chuyen\s*khoan|xac\s*nhan\s*nhan\s*hang)",
        "reason_text": "Thông báo có hàng cần nhận và yêu cầu nộp phí ship / nhập khẩu trước — thường kèm STK, hủy đơn nếu không làm.",
    },
    {
        "rule_code": "R_TAX_DEBT_THREAT",
        "score": 35,
        "pattern": r"(tong\s*cuc\s*thue|hskd\s*cua\s*ban|thue\s*phat|quy\s*dinh\s*nop\s*trong\s*\d+h|noi\s*bo\s*thue|can\s*nop\s*phi\s*\d{2,3}(tr|ty))",
        "reason_text": "Mạo danh Tổng cục Thuế đe dọa nộp phạt tiền thuế khổng lồ vào tài khoản nội bộ — lừa đảo.",
    },
    {
        "rule_code": "R_BANK_SMS_BRANDNAME_PHISHING",
        "score": 45,
        "pattern": r"(\[(vietcombank|vcb|sacombank|scb|bidv|agribank|vietinbank|techcombank|tcb|shb|mbbank|mb|vpbank|acb|tpbank|hdseb|seabank)\])[\s\S]{0,200}(bi\s*khoa|se\s*bi\s*khoa|khoa\s*tai\s*khoan|doi\s*mat\s*khau|xac\s*minh|dang\s*nhap\s*tren\s*thiet\s*bi|giao\s*dich\s*nghi\s*ngo|link\s*\S+\.\S+|kiem\s*soat\s*quyen\s*loi|nhap\s*(ma\s*)?[Oo][Tt]\s*\d+\s*\d+|huy\s*giao\s*dich)",
        "reason_text": "SMS brandname ngân hàng cảnh báo khẩn cấp (tài khoản bị khóa, đăng nhập lạ) kèm link giả / mã OTP hủy — lừa đảo chiếm đoạt.",
    },
    {
        "rule_code": "R_VISA_CARD_UNAUTH_TXN",
        "score": 45,
        "pattern": r"(the\s*(visa|master|atm|ngan\s*hang|thanh\s*toan)|atm\s*\d{4}[\.\s]*\d{4}|thanh\s*toan\s*\d{4}[\.\s]*xxxx|atm\s*\d{4,}[\.\s]*[xX]{3,})[\s\S]{0,150}(bi\s*rut\s*\d|da\s*duoc\s*them\s*\d|da\s*bi\s*rut|giao\s*dich\s*cua\s*quy\s*khach|goi\s*\d{3,}|nhap\s*otp|nhap\s*ma\s*\d+\s*so|kiem\s*soat\s*tai\s*san|huy\s*giao\s*dich|goi\s*den\s*\d{4,})",
        "reason_text": "Thông báo giao dịch không ủy quyền (thêm / rút tiền lớn) trên thẻ + yêu cầu gọi / OTP / hủy giao dịch — lừa đảo chiếm thẻ.",
    },
    {
        "rule_code": "R_FAKE_DELIVERY_APK",
        "score": 45,
        "pattern": r"(file\s*dinh\s*kem|don\s*hang|phieu\s*gui\s*hang|ve\s*don\s*hang|thong\s*bao\s*don\s*hang)[\s\S]{0,150}(\.apk|tai\s*xuong\s*file|mo\s*file\s*xem|phan\s*mem\s*xem\s*don|xem\s*anh\s*\S+\.\S+|tap\s*tin\s*din\s*kem)",
        "reason_text": "Giả dạng file đơn hàng / hóa đơn đính kèm định dạng .APK / link lạ (virus / malware đánh cắp thông tin).",
    },
    {
        "rule_code": "R_PRIZE_LUCKY_DRAW_FEE",
        "score": 40,
        "pattern": r"(chuc\s*mung\s*(ban|sdt|khach\s*hang|quy\s*khach)\s*da\s*trung|trung\s*giai\s*(nhat|nhi|ba)|trung\s*(xe\s*sh|xe\s*may|dienthoai|dien\s*thoai|tien\s*mat|voucher\s*\d+tr|chuong\s*trinh\s*\w+\s+thanh\s+lich))[\s\S]{0,220}(phi\s*van\s*hanh|phi\s*ho\s*so|thue\s*thu\s*nhap|nop\s*phi\s*truoc|chuyen\s*khoan\s*\d+tr|gui\s*phi|stk|nhap\s*ma\s*\d+\s*so\s*de\s*nhan\s*thuong|xac\s*thuc\s*the|nhan\s*thuong\s*tai\s*\S+\.\S+)",
        "reason_text": "Thông báo trúng thưởng lớn (xe, tiền, điện thoại, voucher) + yêu cầu nộp phí / nhập mã xác thực thẻ / link nhận thưởng.",
    },
    {
        "rule_code": "R_INVESTMENT_GUARANTEED",
        "score": 40,
        "pattern": r"(dau\s*tu\s*(bds|chung\s*khoan|forex|ai\s*trading|tien\s*ao|crypto|dubai|my|singapore)|cam\s*ket\s*loi\s*nhuan|bao\s*loi|loi\s*nhuan\s*\d+%\s*\/\s*(thang|nam)|loi\s*nhuan\s*\d+%\s*(thang|nam)|dam\s*bao\s*lai\s*thap\s*nhat\s*\d+%\s*\/\s*(thang|nam)|gui\s*\d+tr\s*nhan\s*\d+tr\s*(moi\s*thang|thang))",
        "reason_text": "Cam kết lợi nhuận cao bất thường (đầu tư BDS Dubai, CK, AI trading, tiền ảo, ‘lãi thấp nhất X%/tháng’) — mô hình lừa đảo chiếm đoạt.",
    },
    {
        "rule_code": "R_ASK_BANK_CREDENTIALS",
        "score": 45,
        "pattern": r"(gui\s*anh\s*cccd|so\s*tai\s*khoan\s*ngan\s*hang|stk\s*ngan\s*hang)[\s\S]{0,150}(ma\s*pin|pin\s*\d+\s*so|mat\s*khau\s*\d+\s*so|de\s*chuyen\s*luong\s*thu\s*nghiem|ma\s*pin\s*6\s*so)",
        "reason_text": "Yêu cầu gửi CCCD + Số TK ngân hàng + Mã PIN / Mật khẩu / Mã PIN 6 số — chiếm đoạt tài khoản ngân hàng.",
    },
    {
        "rule_code": "R_MLM_MATRIX_SCHEME",
        "score": 25,
        "pattern": r"(kinh\s*doanh\s*mang|cau\s*truc\s*ma\s*tran|m[0o]\s*\d+\s*=\s*\d+\s*ban|gioi\s*thieu\s*\d+\s*ban\s*(co\s*thu\s*nhap|nhan\s*hoa\s*hong)|nhan\s*hoa\s*hong\s*tu\s*f\d+)",
        "reason_text": "Dấu hiệu mô hình đa cấp (MLM), ma trận, hoa hồng theo tầng F0-Fn — nguy cơ lừa đảo.",
    },
    {
        "rule_code": "R_SURVEY_GIFT_OFFER",
        "score": 25,
        "pattern": r"(khao\s*sat|hoan\s*tat\s*khao\s*sat|mystery\s*shopper|khao\s*sat\s*vien\s*mat\s*lai)[\s\S]{0,150}(nhan\s*(ngay|qua|the\s*cao|qua\s*tang|voucher\s*\d+k|thuong\s*\d+k)|danh\s*gia\s*chat\s*luong)",
        "reason_text": "Lời mời khảo sát / đánh giá / mystery shopper kèm quà tặng / thẻ cào — mẫu thu thập dữ liệu cá nhân.",
    },
    {
        "rule_code": "R_UNSOLICITED_VIP_GIFT",
        "score": 30,
        "pattern": r"(uu\s*dai\s*vip|khach\s*hang\s*vip|khach\s*hang\s*den\s*than|khach\s*hang\s*dac\s*biet)[\s\S]{0,160}(nhan\s*(qua|tang|thuong)\s*\d{1,3}(tr|k|nghin|trieu))[\s\S]{0,120}(tai\s*app|nhap\s*ma\s*\w+|xac\s*thuc\s*thong\s*tin)",
        "reason_text": "Thông báo VIP / khách hàng đến thân tặng thưởng lớn + yêu cầu tải app / nhập mã / xác thực — lừa đảo chiếm tài khoản.",
    },
    {
        "rule_code": "R_BRAND_VOUCHER_LUCKY_DRAW",
        "score": 30,
        "pattern": r"(coca\s*cola|pepsi|vinamilk|vietcombank|samsung|apple|dien\s*may\s*xanh|nguyen\s*kim|fpt\s*shop|the\s*gioi\s*di\s*dong|mobifone|vinaphone|viettel|nike|adidas)\s*[\s\S]{0,80}(tang\s*voucher|voucher\s*\d{1,3}(tr|trieu|nghin|k)|khach\s*hang\s*may\s*man|nhan\s*qua\s*(ngay|tai)\s*link|khuyen\s*mai\s*\d+\s*nam\s*tai\s*viet\s*nam)",
        "reason_text": "Mạo danh thương hiệu lớn tặng voucher cực lớn / khách hàng may mắn — lừa đảo link / thông tin cá nhân.",
    },
    {
        "rule_code": "R_BUSINESS_PROPOSAL_ROI",
        "score": 25,
        "pattern": r"(co\s*du\s*an\s*hop\s*tac\s*kinh\s*doanh|toi\s*la\s*nguyen\s*van|du\s*an\s*\w+)[\s\S]{0,140}(loi\s*nhuan\s*du\s*bao\s*\d+%\s*\/\s*quy|loi\s*nhuan\s*\d+%\s*(quy|nam|thang)|hay\s*goi\s*dien\s*de\s*trao\s*doi\s*them|lien\s*he\s*de\s*chi\s*tiet)",
        "reason_text": "Lời đề nghị hợp tác kinh doanh chung + lợi nhuận dự báo (%) + gọi điện trao đổi — dấu hiệu lừa đảo mạo danh đối tác.",
    },
    {
        "rule_code": "R_PERSONAL_BORROW_PROMISE_REPAY",
        "score": 30,
        "pattern": r"(chao\s*(anh|chi)\s*,|em\s*ten\s*\w+\s*\d+t\s*o\s*\w+|gioi\s*thieu\s*minh\s*la)[\s\S]{0,200}(ho\s*tro\s*\w+\s*\d+tr\s*duoc\s*khong|chuyen\s*(giup|cho)\s*em\s*\d+tr|cho\s*em\s*muon\s*\d+tr|em\s*se\s*tra\s*lai\s*sau|tra\s*lai\s*(sau|ngay))",
        "reason_text": "Người lạ tự giới thiệu + yêu cầu mượn tiền vài triệu + hứa trả lại sau — Romance / tình cảm lừa đảo.",
    },
    {
        "rule_code": "R_ASK_CCCD_PHOTO",
        "score": 30,
        "pattern": r"(gui\s*anh|gui\s*so|cccd|can\s*cuoc\s*cong\s*dan|mat\s*truoc\s*mat\s*sau|mat\s*truoc\s*&amp;\s*mat\s*sau|anh\s*chan\s*dung|chan\s*dung\s*cccd)[\s\S]{0,120}(dang\s*ky|xac\s*thuc\s*thanh\s*vien|xac\s*nhan\s*thong\s*tin|de\s*chuyen\s*luong)",
        "reason_text": "Yêu cầu gửi ảnh CCCD mặt trước / sau + ảnh chân dung cho mục đích đăng ký / xác minh — rủi ro đánh cắp định danh.",
    },
    {
        "rule_code": "R_LOOKALIKE_SUSPICIOUS_DOMAIN",
        "score": 40,
        "pattern": r"(vietcombank|vcb|techcombank|tcb|bidv|agribank|vietinbank|sacombank|scb|shb|mbbank|mb|vpbank|acb|tpbank|momo|vnpay|vinamilk|vietjetair|vietjet|movenpick)[\s\S]{0,20}\.(top|xyz|icu|tk|info|online|club|work|site|click|link|monster|buzz|cyou|webcam|press|vn|app)",
        "reason_text": "Domain giả mạo thương hiệu (ngân hàng, ví điện tử, hãng lớn) dùng TLD lạ (.top, .xyz, .tk, .click...) — 90% là lừa đảo.",
    },
    {
        "rule_code": "R_JOB_SCAM_FEE",
        "score": 40,
        "pattern": r"(tuyen\s*(nhan\s*vien|c[tv]v|cong\s*tac\s*vien|nhan\s*su|nvsv)\s*(online|tai\s*nha|ha\s*noi\s*\/\s*hcm)|viec\s*lam\s*tai\s*nha|luong\s*\d+[-]?\d*\s*tr\s*\/\s*thang)[\s\S]{0,200}(nop\s*phi\s*(tap\s*huan|dang\s*ky|ho\s*so|co\s*vanchuyen|xac\s*nhan)|phi\s*tap\s*huan|ung\s*tien\s*mua\s*hang|dat\s*coc\s*\d+tr|chuyen\s*khoan\s*\d+tr|stk\s*\d+|gui\s*(cccd|anh\s*chan\s*dung|ma\s*pin|thong\s*tin\s*the))",
        "reason_text": "Tuyển dụng việc làm tại nhà / CTV / NVSV + yêu cầu nộp phí / STK / PIN thẻ — 99% lừa đảo chốt đơn / chiếm đoạt.",
    },
    {
        "rule_code": "R_FAKE_HOTEL_AIRLINE_PROMO",
        "score": 25,
        "pattern": r"(movenpick|khach\s*san\s*5sao|dat\s*phong\s*\d+\s*dem|khuyen\s*mai\s*tet\s*0d|ve\s*may\s*bay\s*0d|chon\s*mua\s*ve\s*gia\s*tot)[\s\S]{0,120}(xac\s*nhan\s*va\s*thanh\s*toan|boi\s*thuong\s*\d+%|huy\s*phong|nhap\s*thong\s*tin|link\s*\S+\.\S+)",
        "reason_text": "Khuyến mãi quá tốt (ve 0đ, phòng khách sạn 5 sao giá rẻ) — rủi ro đánh cắp thẻ tín dụng / lừa đảo thanh toán.",
    },
    {
        "rule_code": "R_LOAN_SCAM_FEES",
        "score": 30,
        "pattern": r"(vay\s*onl|vay\s*tien\s*online|tra\s*gop\s*khong\s*the\s*chap|lai\s*suat\s*0[,\.]?\d*%\s*\/\s*thang|duyet\s*tuy\s*toc|giai\s*ngan\s*\d+phut)[\s\S]{0,150}(nhap\s*sai\s*so\s*tai\s*khoan|phi\s*sua\s*ho\s*so|phi\s*xac\s*minh|mo\s*khoa\s*so\s*tai|nop\s*phi\s*truoc)",
        "reason_text": "Vay tiền online lãi suất 0% / duyệt nhanh + viện lý do phí sửa hồ sơ / mở khóa — lừa đảo.",
    },
    {
        "rule_code": "R_BANK_IMPERSONATION_PRO",
        "score": 30,
        "pattern": r"(momo|vpbank|acb|tpbank|seabank|hdseb|pvcombank|ocb|shb\s*|shinhan|woori|msb|pg\s*bank|uob|standard\s*chartered|vietnam\s*bank\s*for|vib|abbank|cimb|vnpay|momo:|vnpay:)[\s\S]{0,120}(thong\s*bao|xac\s*minh|tai\s*khoan|doi\s*mat\s*khau|gia\s*han\s*the|cap\s*quyen\s*sms|chuong\s*trinh\s+\w+)",
        "reason_text": "Mạo danh các ngân hàng khác (MOMO, VPBank, ACB, TPBank, VNPAY…) + hành động nhạy cảm — nghi vấn lừa đảo.",
    },
    {
        "rule_code": "R_SHORT_URL_EXPANDED",
        "score": 20,
        "pattern": r"\b(bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|ow\.ly|cutt\.ly|rebrand\.ly|shorte\.st|buff\.ly|adf\.ly|bc\.vc|j\.gs|q\.gl|rlu\.ru|moourl\.com|s2r\.co|bit\.do|mcaf\.ee|aka\.ms|post\.gy|me\.gl|fb\.gg|zalo\.me|zpshare|vn\.gl)\b\/?\S*",
        "reason_text": "Sử dụng link rút gọn (bit.ly / tinyurl / vn.gl …) — thường dùng để che giấu domain thật của trang lừa đảo.",
    },
    {
        "rule_code": "R_URGENCY_TIMED",
        "score": 20,
        "pattern": r"(trong\s*\d+\s*(gio|phut|tieng|h)|gio\s*[\s\S]{0,10}(het\s*han|khoa|huy|toi\s*han)|dieu\s*khoan\s*\d+tieng|doi\s*mat\s*khau\s*ngay|xac\s*minh\s*ngay|ngay\s*lap\s*tuc|gui\s*ngay|chuyen\s*ngay|trong\s*vong\s*\d+\s*(gio|phut))",
        "reason_text": "Yêu cầu thực hiện gấp (xử lý trong N phút / giờ) — hạn chế thời gian suy nghĩ là đặc điểm lừa đảo.",
    },
]


def _match_keyword_list(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    text_lower = _strip_diacritics(normalized_text).lower()
    for kw in pattern.split(","):
        kw = _strip_diacritics(kw.strip()).lower()
        if not kw:
            continue
        if kw in text_lower:
            return True
    return False


def _match_regex(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    safe_text = _strip_diacritics(normalized_text)
    try:
        return re.search(pattern, safe_text, re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return _strip_diacritics(pattern).lower() in safe_text.lower()


def _match_tld_list(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    safe_text = _strip_diacritics(normalized_text)
    tlds = [t.strip().lstrip(".").lower() for t in pattern.split(",") if t.strip()]
    if not tlds:
        return False
    tld_group = "|".join(re.escape(t) for t in tlds)
    tld_regex = r"\." + tld_group + r"(?:[\s/!?.,;:]|$)"
    try:
        return re.search(tld_regex, safe_text, re.IGNORECASE) is not None
    except re.error:
        return False


def _match_core_rule(normalized_text: str, rule: dict) -> bool:
    pattern = rule.get("pattern") or ""
    if not pattern:
        return False
    safe_text = _strip_diacritics(normalized_text)
    try:
        return re.search(pattern, safe_text, re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return False


_NEGATIVE_SAFE_HINTS = [
    r"so\s*du\s*tk",
    r"so\s*du\s*tai\s*khoan",
    r"giao\s*dich\s*cuoi\s*:",
    r"giao\s*dich\s*\(?.*\)\s*(thanh\s*cong|thanh\s*toan|chuyen\s*khoan)",
    r"so\s*du\s*(tk|tai\s*khoan)[\s\S]{0,60}giao\s*dich\s*cuoi",
]


def _is_safe_bank_balance_text(normalized_text: str) -> bool:
    """
    Tin số dư tài khoản hoặc thông báo giao dịch cuối từ ngân hàng KHÔNG phải lừa đảo.
    Nếu text match TÍCH CỰC (có “số dư TK” hoặc “giao dịch cuối” + nội dung số tk) và không có từ KHỐNG (link / xác minh / otp / doi mat khau),
    trả về True để loại trừ các rule ngân hàng cơ bản.
    """
    safe = _strip_diacritics(normalized_text).lower()
    positive_match = any(
        re.search(hint, safe, re.IGNORECASE) for hint in _NEGATIVE_SAFE_HINTS
    )
    if not positive_match:
        return False
    negative_flags = [
        r"link\s*\S+\.\S+", r"https?://", r"\.apk", r"ma\s*otp[^:]*\b(cung|nhap|bao|doc|gui|chia)",
        r"xac\s*minh\s*tai\s*khoan", r"doi\s*mat\s*khau", r"bi\s*khoa", r"se\s*bi\s*khoa",
        r"stk\s*\d{6,}", r"chuyen\s*khoan\s*(vao|sang)\s*\S", r"de\s*(nhan|xac\s*nhan)\s*(qua|thuong|gia)",
        r"khong\s*nhap\s*link|nhap\s*(ma\s*)?otp",
    ]
    has_flag = any(re.search(pat, safe, re.IGNORECASE) for pat in negative_flags)
    return not has_flag


_GENUINE_OTP_HINTS = [
    r"(khong|dung|tuong\s*doi)\s*(chia\s*se|bao\s*cho|chia\s*se\s*voi)\s*(bat\s*ky\s*ai|nguoi\s*than|ai\s*khac|mot\s*ai)",
    r"ma\s*otp\s*(xac\s*nhan|xac\s*minh)\s*chuyen\s*khoan",
    r"tu\s*tk\s*\d[\d\.\s]*\s*den\s*(tk\s*)?\d[\d\.\s]*",
    r"giao\s*dich\s*(chuyen\s*khoan|thanh\s*toan|rut\s*tien)\s*(tu|den|so\s*du)",
]


def _is_genuine_bank_otp_notice(normalized_text: str) -> bool:
    """
    Tin OTP CHÍNH THỨC từ ngân hàng / ví (VNPAY, MOMO…) có đặc điểm:
      - “KHÔNG chia sẻ / đừng báo cho ai”
      - “Mã OTP xác nhận chuyển khoản”
      - “Từ TK 0421... đến TK 0888...”
      - “Giao dịch chuyển khoản/thanh toán/rút tiền … số dư …”
    Nếu match → KHÔNG tính OTP_REQUEST / OTP_6DIGIT_CONTEXT cho tin này.
    """
    text = _strip_diacritics(normalized_text).lower()
    hits = sum(1 for hint in _GENUINE_OTP_HINTS if re.search(hint, text, re.IGNORECASE))
    return hits >= 1


def run_rule_engine(normalized_text: str, db: Session) -> dict:
    """
    Tầng 3: Nạp scoring_rule từ DB (hoạt động CÓ dấu / không dấu nhờ strip_diacritics)
            + chạy bộ CORE_RULES regex cứng (đảm bảo bắt các mẫu lừa đảo phổ biến dù DB có đầy đủ hay không).
    Hỗ trợ 3 pattern_type: keyword_list | regex | tld_list.
    """
    is_safe_bank = _is_safe_bank_balance_text(normalized_text)
    is_genuine_otp = _is_genuine_bank_otp_notice(normalized_text)
    matched_reasons_map: dict[str, dict] = {}

    db_rules = db.query(ScoringRule).filter(ScoringRule.is_active == True).order_by(ScoringRule.score.desc()).all()
    for rule in db_rules:
        pattern = rule.pattern or ""
        score_val = int(rule.score or 0)
        ptype = (rule.pattern_type or "keyword_list").strip().lower()
        matched = False

        if ptype == "keyword_list":
            matched = _match_keyword_list(normalized_text, pattern)
        elif ptype == "regex":
            matched = _match_regex(normalized_text, pattern)
        elif ptype == "tld_list":
            matched = _match_tld_list(normalized_text, pattern)
        else:
            matched = _match_keyword_list(normalized_text, pattern)

        if matched:
            rule_code = rule.rule_code or f"R_DB_{id(rule)}"
            if is_safe_bank and rule_code in ("R_IMPERSONATE_BANK", "R_ACCOUNT_THREAT", "R_LOOKALIKE_DOMAIN", "R_ASK_OTP", "R_PRIZE"):
                continue
            if is_genuine_otp and rule_code in ("R_ASK_OTP", "R_PRIZE"):
                continue
            existing = matched_reasons_map.get(rule_code)
            if existing is None or int(existing.get("score") or 0) < score_val:
                matched_reasons_map[rule_code] = {
                    "source": "RULE",
                    "text": (rule.reason_text or rule.description or f"Phát hiện dấu hiệu {rule_code}").strip(),
                    "rule_code": rule_code,
                    "score": score_val,
                }

    for rule in CORE_RULES:
        rule_code = rule["rule_code"]
        score_val = int(rule.get("score") or 0)
        if not _match_core_rule(normalized_text, rule):
            continue
        if is_safe_bank and rule_code in (
            "R_BANK_SMS_BRANDNAME_PHISHING",
            "R_VISA_CARD_UNAUTH_TXN",
            "R_BANK_IMPERSONATION_PRO",
            "R_URGENCY_TIMED",
            "R_ACCOUNT_THREAT",
            "R_PRIZE_LUCKY_DRAW_FEE",
            "R_OTP_REQUEST_STRONG",
            "R_OTP_6DIGIT_CONTEXT",
        ):
            continue
        if is_genuine_otp and rule_code in (
            "R_OTP_REQUEST_STRONG",
            "R_OTP_6DIGIT_CONTEXT",
            "R_VISA_CARD_UNAUTH_TXN",
            "R_BANK_SMS_BRANDNAME_PHISHING",
        ):
            continue
        existing = matched_reasons_map.get(rule_code)
        if existing is None or int(existing.get("score") or 0) < score_val:
            matched_reasons_map[rule_code] = {
                "source": "RULE",
                "text": (rule.get("reason_text") or rule.get("description") or rule_code).strip(),
                "rule_code": rule_code,
                "score": score_val,
            }

    matched_reasons = list(matched_reasons_map.values())
    raw_rule_score = sum(int(r.get("score") or 0) for r in matched_reasons)
    final_rule_score = min(100, raw_rule_score)
    return {"rule_score": final_rule_score, "reasons": matched_reasons}
