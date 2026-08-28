"""Script test Pipeline Rule Engine (T-013 / FR-01 / BR-01-10).

Chạy trong Docker:   docker compose exec backend python /app/test_pipeline.py
Chạy trong venv:     .\\venv\\Scripts\\python.exe test_pipeline.py
"""
import os
import sys

from app.core.database import SessionLocal
from app.services.pipeline import execute_scan_pipeline


def assert_score(desc, actual, expected):
    ok = actual == expected
    sym = "✅" if ok else "❌"
    print(f"  {sym} {desc}: {actual} / mong đợi {expected}")
    return ok


def assert_in(desc, haystack, needle):
    ok = needle.lower() in haystack.lower()
    sym = "✅" if ok else "❌"
    print(f"  {sym} {desc}: tìm thấy '{needle}'? {ok}")
    return ok


def main():
    print("=" * 70)
    print("🧪 TEST PIPELINE SCAN - T-013 Rule Engine (BR-01-10)")
    print("=" * 70)

    db = SessionLocal()
    try:
        # --- Test case 1: Mẫu VIETCOMBANK BÁO KHÓA TK (Mẫu spec) ---
        t1 = "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"
        print(f"\n📝 TEST 1 (Spec mẫu): {t1}\n")
        r1 = execute_scan_pipeline(t1, db)
        rc1 = r1.get("reasons", [])
        codes1 = sorted([x.get("rule_code") for x in rc1])

        all_pass = True
        all_pass &= assert_score("Final score (trần 100)", r1["final_score"], 100)
        all_pass &= assert_score("Risk level", r1["risk_level"], "NGUY_HIEM")
        for required_rule in ["R_IMPERSONATE_BANK", "R_ACCOUNT_THREAT", "R_URGENCY", "R_SHORT_URL"]:
            all_pass &= assert_in(f"Rule match có {required_rule}", " ".join(codes1), required_rule)
        expected_sum = 30 + 25 + 20 + 25
        print(f"  💡 Tổng điểm 4 rule: R_IMPERSONATE_BANK(30)+R_ACCOUNT_THREAT(25)+R_URGENCY(20)+R_SHORT_URL(25) = {expected_sum} => min(100, {expected_sum}) = 100 (trần)")
        print(f"  💡 Khuyến nghị: {r1['recommended_action']}")
        print(f"  💡 Danh sách lý do ({len(rc1)} mục):")
        for r in rc1:
            print(f"     - [{r['rule_code']}] +{r['score']}đ: {r['text']}")

        # --- Test case 2: OTP / Mật khẩu ---
        t2 = "Mã OTP của quý khách là 582631, vui lòng cung cấp mã để chúng tôi hỗ trợ chuyển khoản."
        print(f"\n📝 TEST 2 (OTP scam): {t2}\n")
        r2 = execute_scan_pipeline(t2, db)
        rc2 = r2.get("reasons", [])
        all_pass &= assert_score("Có OTP score", r2["final_score"] >= 40, True)
        all_pass &= assert_in("Phát hiện R_ASK_OTP", " ".join([x["rule_code"] for x in rc2]), "R_ASK_OTP")

        # --- Test case 3: An toàn ---
        t3 = "Chào bạn, hôm nay thời tiết đẹp, chúng ta đi chơi nhé. Liên lạc số 0912345678"
        print(f"\n📝 TEST 3 (An toàn): {t3}\n")
        r3 = execute_scan_pipeline(t3, db)
        all_pass &= assert_score("Risk level an toàn", r3["risk_level"], "AN_TOAN")
        all_pass &= assert_score("Score thấp", r3["final_score"] <= 15, True)

        # --- Test case 4: Việc nhẹ lương cao + Số TK ---
        t4 = "Tuyển dụng việc làm tại nhà lương 25tr/tháng, nộp hồ sơ STK 1234567890 (MBBank), yêu cầu chốt nhanh."
        print(f"\n📝 TEST 4 (Tuyển dụng + STK): {t4}\n")
        r4 = execute_scan_pipeline(t4, db)
        rc4 = r4.get("reasons", [])
        codes4 = " ".join([x["rule_code"] for x in rc4])
        all_pass &= assert_in("R_JOB_SCAM", codes4, "R_JOB_SCAM")
        all_pass &= assert_in("R_BANK_ACCOUNT", codes4, "R_BANK_ACCOUNT")
        all_pass &= assert_score("Score nghi ngờ trở lên", r4["final_score"] >= 40, True)

        print("\n" + "=" * 70)
        if all_pass:
            print("✅ TẤT CẢ TEST CASE THÀNH CÔNG! Pipeline BR-01-10 hoạt động đúng spec")
            print("=" * 70)
            return 0
        else:
            print("❌ CÓ TEST CASE THẤT BẠI, xem chi tiết ở trên và kiểm tra lại rule pattern.")
            print("=" * 70)
            return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
