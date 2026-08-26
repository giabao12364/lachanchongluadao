"""
PhoneCarrierService — FR-02, BR-02-1, BR-02-2

Xác định nhà mạng theo đầu số điện thoại VN.
Dữ liệu quy hoạch đầu số (tĩnh trong code/config), KHÔNG phải điểm số
chấm rủi ro -> không thuộc phạm vi KT-03 (cấm hardcode ngưỡng/điểm).
Input: số điện thoại đã chuẩn hóa E.164 (VD: +84912345678)
Output: tên nhà mạng, hoặc "Không xác định" nếu đầu số chưa có trong bảng
"""

# Đầu số 3 chữ số -> tên nhà mạng.
PREFIX_TO_CARRIER: dict[str, str] = {
    # Viettel
    "032": "Viettel", "033": "Viettel", "034": "Viettel", "035": "Viettel",
    "036": "Viettel", "037": "Viettel", "038": "Viettel", "039": "Viettel",
    "086": "Viettel", "096": "Viettel", "097": "Viettel", "098": "Viettel",

    # Vinaphone
    "081": "Vinaphone", "082": "Vinaphone", "083": "Vinaphone",
    "084": "Vinaphone", "085": "Vinaphone", "088": "Vinaphone",
    "091": "Vinaphone", "094": "Vinaphone",

    # Mobifone
    "070": "Mobifone", "076": "Mobifone", "077": "Mobifone",
    "078": "Mobifone", "079": "Mobifone", "089": "Mobifone",
    "090": "Mobifone", "093": "Mobifone",

    # Vietnamobile
    "052": "Vietnamobile", "056": "Vietnamobile", "058": "Vietnamobile",
    "092": "Vietnamobile",

    # Gmobile
    "059": "Gmobile", "099": "Gmobile",

    # Itelecom
    "087": "Itelecom",

    # Reddi
    "055": "Reddi",
}

UNKNOWN_CARRIER = "Không xác định"


def get_carrier(e164_phone: str) -> str:
    """
    Xác định nhà mạng từ số điện thoại đã chuẩn hóa E.164.
    Args:
        e164_phone: Số dạng "+84xxxxxxxxx" (đã qua normalize_phone_to_e164).

    Returns:
        Tên nhà mạng, hoặc "Không xác định" nếu đầu số chưa có trong bảng
        (BR-02-2: không báo lỗi, vẫn tiếp tục tra blacklist).
    """
    if not e164_phone or not e164_phone.startswith("+84"):
        return UNKNOWN_CARRIER

    digits_after_84 = e164_phone[3:]  # "912345678"
    if len(digits_after_84) < 2:
        return UNKNOWN_CARRIER

    # Tái tạo đầu số dạng nội địa 0xy: "+8491..." -> "091"
    prefix = "0" + digits_after_84[:2]
    return PREFIX_TO_CARRIER.get(prefix, UNKNOWN_CARRIER)