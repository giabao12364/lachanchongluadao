"""Script test T-015: FR-01 Pipeline hợp nhất điểm BR-01-2.

BR-01-2 — Điểm tổng hợp:
  Khi không có chốt chặn cứng (blacklist hard override):
    final_score = min(100, rule_score + ai_score × 0.6)
  → AI là cố vấn, không phải quan tòa (AI score bị nhân 0.6 → chỉ cộng thêm,
    không được phép tự làm nội dung thành "NGUY_HIEM" nếu rule_score thấp).

Phụ thuộc T-013 (Rule Engine, BR-01-10) + T-014 (AI, Fail-safe BR-01-6).

Chạy trong Docker (DB đã seed sẵn, cổng 5432 nội bộ, mock _call_ai không cần key):
    docker compose exec backend python /app/test_t015_br012_final_score.py

Chạy trong venv local (cần .env có DATABASE_URL_SYNC cổng 5433):
    .\\venv\\Scripts\\python.exe test_t015_br012_final_score.py
"""
import os
import sys
from unittest.mock import patch

from app.core.database import SessionLocal
from app.services.pipeline import execute_scan_pipeline


def green(s):
    return f"\033[92m{s}\033[0m"


def red(s):
    return f"\033[91m{s}\033[0m"


def yellow(s):
    return f"\033[93m{s}\033[0m"


def assert_eq(desc, actual, expected):
    ok = actual == expected
    print(f"  {'✅' if ok else '❌'} {desc}: {actual} / mong đợi {expected}")
    return ok


def assert_ge(desc, actual, expected):
    ok = actual >= expected
    print(f"  {'✅' if ok else '❌'} {desc}: {actual} >= {expected}")
    return ok


def assert_true(desc, cond):
    print(f"  {'✅' if cond else '❌'} {desc}")
    return bool(cond)


def _run_with_ai_score(raw_content: str, db, mock_ai_score: int | None):
    """Chạy execute_scan_pipeline và mock _call_ai trả về mock_ai_score."""
    with patch(
        "app.services.pipeline._call_ai",
        return_value=mock_ai_score,
    ):
        return execute_scan_pipeline(raw_content, db)


def test_0_spec_sample_vietcombank():
    """
    TC1: Spec sample T-013 + BR-01-2
      Input: "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"
      Rule: R_IMPERSONATE_BANK(30)+R_ACCOUNT_THREAT(25)+R_URGENCY(20)+R_SHORT_URL(25) = 100 (trần)
      AI: 90 → ×0.6 = 54
      BR-01-2: final_score = min(100, 100 + 54) = 100
      Output: NGUY_HIEM
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 0] Spec mẫu VCB: rule=100 + AI=90 → min(100,154)=100 (trần)"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"
        r = _run_with_ai_score(t, db, mock_ai_score=90)
        all_pass = True
        all_pass &= assert_eq("rule_score (T-013 BR-01-10)", r["rule_score"], 100)
        all_pass &= assert_eq("ai_score (mock)", r["ai_score"], 90)
        all_pass &= assert_eq("ai_available=true (mock có trả)", r["ai_available"], True)
        # ai_contrib = 90 * 0.6 = 54
        # final = 100 + 54 = 154 → min(100,154) = 100
        all_pass &= assert_eq("final_score (BR-01-2)", r["final_score"], 100)
        all_pass &= assert_eq("risk_level", r["risk_level"], "NGUY_HIEM")
        print(f"  💡 Công thức: min(100, {r['rule_score']} + {r['ai_score']}*0.6) = min(100, {r['rule_score'] + int(r['ai_score']*0.6)}) = {r['final_score']}")
        return all_pass
    finally:
        db.close()


def test_1_ai_only_rule_low():
    """
    TC2: AI là cố vấn không phải quan tòa.
      Rule_score = 0 (nội dung an toàn hoàn toàn nhưng AI vẫn nghi ngờ cao).
      AI = 100 (tối đa)
      BR-01-2: final_score = 0 + 100*0.6 = 60 → NGHI_NGO (chưa chạm 70 nguy_hiểm)
      → Chứng minh AI không thể tự biến thành NGUY_HIEM nếu rule không match.
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 1] AI cố vấn, KHÔNG phải quan tòa: rule=0 + AI=100 → 60 (NGHI_NGO, không NGUY_HIEM)"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "Chào bạn, hôm nay thời tiết đẹp nhé."
        r = _run_with_ai_score(t, db, mock_ai_score=100)
        all_pass = True
        all_pass &= assert_eq("rule_score=0", r["rule_score"], 0)
        all_pass &= assert_eq("ai_score=100 (mock)", r["ai_score"], 100)
        # 0 + 100*0.6 = 60
        all_pass &= assert_eq("final_score = 0 + 100*0.6 = 60", r["final_score"], 60)
        # 60 < 70 → KHÔNG NGUY_HIEM
        all_pass &= assert_eq("risk_level = NGHI_NGO (chưa đạt nguy_hiểm)", r["risk_level"], "NGHI_NGO")
        all_pass &= assert_true("ai_available=true", r["ai_available"])
        print(f"  💡 Công thức: min(100, {r['rule_score']} + {r['ai_score']}*0.6) = {r['final_score']}")
        print(f"  💡 AI không thể tự biến thành NGUY_HIEM nếu rule không match (đúng mô tả BR-01-2).")
        return all_pass
    finally:
        db.close()


def test_2_mix_rule_and_ai():
    """
    TC3: Rule=50 + AI=100 → final = 50 + 60 = 110 → min(100,110) = 100 → NGUY_HIEM.
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 2] Hợp nhất Rule + AI: 50 + 100*0.6 = 110 → min 100"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "Mã OTP của quý khách là 582631, vui lòng cung cấp mã."
        r = _run_with_ai_score(t, db, mock_ai_score=100)
        all_pass = True
        all_pass &= assert_ge("rule_score >= 40 (R_ASK_OTP)", r["rule_score"], 40)
        # 50 + 60 = 110 → 100
        all_pass &= assert_eq("final_score min(100, rule+60) = 100", r["final_score"], 100)
        all_pass &= assert_eq("risk_level = NGUY_HIEM", r["risk_level"], "NGUY_HIEM")
        print(f"  💡 rule_score={r['rule_score']}, ai_score={r['ai_score']}, ai_contrib={int(r['ai_score']*0.6)}, final={r['final_score']}")
        return all_pass
    finally:
        db.close()


def test_3_no_ai_failsafe_keeps_rule():
    """
    TC4: T-014 fail-safe BR-01-6: AI vắng mặt → final_score = rule_score (vì ai_contrib=0).
         AI score không làm gì cả, rule vẫn giữ nguyên giá trị.
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 3] AI vắng mặt (T-014): ai_score=None → final = rule_score (ai_contrib=0)"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "Mã OTP của quý khách là 582631, vui lòng cung cấp mã."
        r = _run_with_ai_score(t, db, mock_ai_score=None)
        all_pass = True
        rule_s = r["rule_score"]
        all_pass &= assert_eq("ai_score=None (mock)", r["ai_score"], None)
        all_pass &= assert_eq("ai_available=false", r["ai_available"], False)
        # Ai không có, final_score tối thiểu = rule_score (có thể bumped lên nghi_ngo 30 nếu rule>0 + risk thấp)
        # Nhưng điểm phải >= rule_score (không bị giảm đi)
        all_pass &= assert_ge(f"final_score >= rule_score ({rule_s})", r["final_score"], rule_s)
        # AT-06: nếu rule_score>0 + AI vắng mặt → KHÔNG AN_TOAN
        if rule_s > 0:
            all_pass &= assert_true("AT-06: risk_level != AN_TOAN", r["risk_level"] != "AN_TOAN")
        print(f"  💡 rule_score={r['rule_score']}, ai_score={r['ai_score']}, final_score={r['final_score']}")
        return all_pass
    finally:
        db.close()


def test_4_mid_case_nguoi_hiem():
    """
    TC5: Rule=50, AI=50 → 50 + 30 = 80. Nguy_hiểm_threshold=70 → NGUY_HIEM.
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 4] Rule=50 + AI=50 → 50+30=80 (>=70 → NGUY_HIEM)"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "Mã OTP của quý khách là 582631, vui lòng cung cấp mã."
        r = _run_with_ai_score(t, db, mock_ai_score=50)
        all_pass = True
        rule_s = r["rule_score"]
        ai_s = r["ai_score"]
        ai_contrib = int(ai_s * 0.6)
        expected = min(100, rule_s + ai_contrib)
        all_pass &= assert_eq(f"final_score={expected} (rule+ai*0.6)", r["final_score"], expected)
        all_pass &= assert_eq("risk_level=NGUY_HIEM (>=70)", r["risk_level"], "NGUY_HIEM")
        print(f"  💡 {rule_s} + {ai_s}×0.6 = {rule_s} + {ai_contrib} = {rule_s + ai_contrib} → min(100, ...) = {r['final_score']}")
        return all_pass
    finally:
        db.close()


def test_5_benign_no_rule_no_ai_score():
    """
    TC6: Nội dung lành mạnh: rule=0, AI=0 → final=0+0=0 → AN_TOAN (ai_available=true).
    """
    print("\n" + "=" * 70)
    print(yellow("[TEST 5] An toàn hoàn toàn: rule=0 + AI=0 → 0 → AN_TOAN"))
    print("=" * 70)
    db = SessionLocal()
    try:
        t = "Chào bạn, hôm nay thời tiết đẹp nhé."
        r = _run_with_ai_score(t, db, mock_ai_score=0)
        all_pass = True
        all_pass &= assert_eq("rule_score=0", r["rule_score"], 0)
        all_pass &= assert_eq("ai_score=0", r["ai_score"], 0)
        all_pass &= assert_eq("final_score=0", r["final_score"], 0)
        all_pass &= assert_eq("risk_level=AN_TOAN", r["risk_level"], "AN_TOAN")
        all_pass &= assert_eq("ai_available=true", r["ai_available"], True)
        return all_pass
    finally:
        db.close()


def main():
    print()
    print(green("╔══════════════════════════════════════════════════════════════════════════╗"))
    print(green("║  T-015  FR-01 Pipeline hợp nhất điểm BR-01-2: min(100, rule + ai*0.6)    ║"))
    print(green("╚══════════════════════════════════════════════════════════════════════════╝"))
    print()
    print("📌 Phụ thuộc:")
    print("   - T-010 (Normalizer): trim + NFC + lowercase (đã chạy đầu pipeline)")
    print("   - T-013 (Rule Engine BR-01-10): nạp scoring_rule từ DB và cộng điểm rule_score")
    print("   - T-014 (AI Fail-safe BR-01-6): timeout/retry + AI vắng mặt → fail-safe")
    print("📌 BR-01-2: AI là CỐ VẤN, không phải quan tòa (nhân điểm AI với 0.6)")
    print("   Công thức khi không có hard-override: final_score = min(100, rule_score + ai_score × 0.6)")
    print("   (AppConfig key `ai.weight` = 0.6 theo seed T-002, `pipeline.max_final_score` = 100)")
    print()
    os.environ.pop("AI_API_KEY", None)
    print("⚠️  Môi trường test: _call_ai được MOCK → không gọi OpenAI thật → test nhanh và xác định.")

    results = []
    results.append(("TC0: Spec sample VCB rule=100 + AI=90 → 100 trần", test_0_spec_sample_vietcombank()))
    results.append(("TC1: AI cố vấn (rule=0, AI=100 → 60, KHÔNG nguy_hiểm)", test_1_ai_only_rule_low()))
    results.append(("TC2: rule>=40 + AI=100 → 100 trần → nguy_hiểm", test_2_mix_rule_and_ai()))
    results.append(("TC3: AI vắng mặt (None) → final >= rule, fail-safe", test_3_no_ai_failsafe_keeps_rule()))
    results.append(("TC4: rule=?, AI=50 → rule + 30 → ≥70 → nguy_hiểm", test_4_mid_case_nguoi_hiem()))
    results.append(("TC5: rule=0 + AI=0 → 0 → an_toàn", test_5_benign_no_rule_no_ai_score()))

    print("\n" + "=" * 70)
    print("📊 TỔNG KẾT T-015 BR-01-2")
    print("=" * 70)
    all_ok = True
    for name, ok in results:
        sym = green("✅ PASS") if ok else red("❌ FAIL")
        print(f"  {sym}  {name}")
        all_ok &= bool(ok)

    print()
    if all_ok:
        print(green("✅ TẤT CẢ TEST THÀNH CÔNG! T-015 hợp nhất điểm BR-01-2 đúng spec."))
        print()
        print("  ✔ final_score = min(100, rule_score + ai_score × ai.weight)")
        print("  ✔ ai.weight = 0.6 (AppConfig seed T-002 `ai.weight`)")
        print("  ✔ AI là cố vấn (× 0.6), KHÔNG tự làm NGUY_HIEM nếu rule không match")
        print("  ✔ Fail-safe T-014: AI vắng mặt → final >= rule_score, không giảm điểm")
        print("  ✔ Spec sample T-013 (100) + AI=90 → trần 100 đúng ví dụ spec")
        print("  ✔ Phụ thuộc T-013, T-014 đều hoạt động ổn định, không regression.")
        return 0
    else:
        print(red("❌ CÓ TEST THẤT BẠI. Kiểm tra chi tiết ở trên."))
        print(red("   - Kiểm tra AppConfig seed T-002 `ai.weight` còn là 0.6 không?"))
        print(red("   - Kiểm tra `rule_score` của nội dung sample match đúng BR-01-10 không?"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
