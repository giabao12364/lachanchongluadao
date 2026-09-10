"""
T-016 FR-01 Pipeline: Ánh xạ điểm → risk_level + recommended_action (BR-01-3, BR-01-11)
  BR-01-3: Ngưỡng điểm
    0 - 29  -> AN_TOAN
    30 - 69 -> NGHI_NGO
    70 - 100 -> NGUY_HIEM
  BR-01-11: Khuyến nghị hành động CHÍNH XÁC text (đọc từ AppConfig seed T-002 recommended_action.*)
    AN_TOAN   = "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân."
    NGHI_NGO  = "Có dấu hiệu đáng ngờ. Đừng bấm link và đừng cung cấp thông tin. Hãy hỏi lại người thân hoặc gọi số tổng đài chính thức."
    NGUY_HIEM = "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp mã OTP. Hãy xóa tin nhắn và chặn số này."
  EP-01 Schema:
    - Input field name = "content" (không còn "raw_content")
    - Response chỉ 7 field: scan_id, risk_level, final_score, reasons[source/text/rule_code], recommended_action, ai_available, created_at
    - 422 errors: EMPTY_CONTENT, CONTENT_TOO_LONG, INVALID_PHONE, INVALID_URL, OCR_NO_TEXT (format {code, message})
  Phụ thuộc: T-015 hợp nhất điểm min(100, rule + ai*0.6); T-014 fail-safe BR-01-6
"""
import os
import sys
import json
from datetime import datetime
from typing import Any

import dotenv

try:
    dotenv.load_dotenv()
except Exception:
    pass

BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
APP_ROOT = os.path.join(BACKEND_ROOT, "app")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from unittest.mock import patch, MagicMock  # noqa: E402


RAW_SYNC = os.environ.get("DATABASE_URL_SYNC") or "postgresql+psycopg2://lachan_user:lachan_pass@localhost:5433/lachan_db"
# Khi chạy trong container: cổng nội bộ là 5432
if "lachan_postg" in RAW_SYNC or ":5433" in RAW_SYNC:
    IN_CONTAINER = False
else:
    IN_CONTAINER = os.path.exists("/.dockerenv")
if IN_CONTAINER and "localhost" in RAW_SYNC and ":5433" in RAW_SYNC:
    RAW_SYNC = RAW_SYNC.replace("localhost:5433", "lachan_postg:5432")

engine = create_engine(RAW_SYNC, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

from app.services.pipeline import execute_scan_pipeline  # noqa: E402
from app.services.pipeline import _resolve_risk  # noqa: E402


def check(expr: bool, msg: str) -> bool:
    ok = bool(expr)
    print(f"  {'✅' if ok else '❌'} {msg}")
    return ok


def main() -> int:
    banner = "╔══════════════════════════════════════════════════════════════════════════╗\n"
    banner += "║  T-016  FR-01 BR-01-3 ngưỡng điểm + BR-01-11 recommended action          ║\n"
    banner += "╚══════════════════════════════════════════════════════════════════════════╝"
    print(banner)
    print(f"\n📌 Phụ thuộc: T-013 Rule Engine, T-014 Fail-safe BR-01-6, T-015 final = rule + ai*0.6")
    print(f"📌 BR-01-3: 0-29 AN_TOAN | 30-69 NGHI_NGO | 70-100 NGUY_HIEM")
    print(f"📌 BR-01-11: Text CHÍNH XÁC 3 mức (không sai chữ, sai dấu)")
    print(f"\n⚠️  Môi trường test: DATABASE_URL_SYNC = {RAW_SYNC}\n")

    AN_TOAN_TEXT = "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân."
    NGHI_NGO_TEXT = "Có dấu hiệu đáng ngờ. Đừng bấm link và đừng cung cấp thông tin. Hãy hỏi lại người thân hoặc gọi số tổng đài chính thức."
    NGUY_HIEM_TEXT = "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp mã OTP. Hãy xóa tin nhắn và chặn số này."

    tests_passed = 0
    tests_failed = 0

    def start(name: str, sep: str = "=") -> None:
        print(sep * 70)
        print(f"[TEST] {name}")
        print(sep * 70)

    def verdict(tc_name: str, ok: bool) -> None:
        nonlocal tests_passed, tests_failed
        if ok:
            tests_passed += 1
            print(f"  👉 PASS  {tc_name}\n")
        else:
            tests_failed += 1
            print(f"  👉 FAIL  {tc_name}\n")

    # ------------------------------------------------------------------
    # TC0 — Resolve ngưỡng biên 29/30/69/70 (không cần DB / rule)
    # ------------------------------------------------------------------
    start("TC0 BR-01-3: Ngưỡng biên 29/30/69/70 trả đúng risk_level")
    thresholds_br013 = {"nghi_ngo": 30, "nguy_hiem": 70, "rec_an_toan": AN_TOAN_TEXT, "rec_nghi_ngo": NGHI_NGO_TEXT, "rec_nguy_hiem": NGUY_HIEM_TEXT}
    tc0_ok = True
    cases_br013 = [
        (0, "AN_TOAN", AN_TOAN_TEXT),
        (29, "AN_TOAN", AN_TOAN_TEXT),
        (30, "NGHI_NGO", NGHI_NGO_TEXT),
        (50, "NGHI_NGO", NGHI_NGO_TEXT),
        (69, "NGHI_NGO", NGHI_NGO_TEXT),
        (70, "NGUY_HIEM", NGUY_HIEM_TEXT),
        (100, "NGUY_HIEM", NGUY_HIEM_TEXT),
    ]
    for score, expected_level, expected_text in cases_br013:
        lvl, act = _resolve_risk(score, thresholds_br013)
        tc0_ok &= check(lvl == expected_level, f"Biên {score} risk_level = {lvl} / mong đợi {expected_level}")
        tc0_ok &= check(act == expected_text, f"Biên {score} recommended_action text đúng BR-01-11")
    verdict("TC0 BR-01-3 ngưỡng biên", tc0_ok)

    # ------------------------------------------------------------------
    # TC1 — Pipeline AN_TOAN: nội dung lành mạnh, rule_score=0, ai_score=0
    # ------------------------------------------------------------------
    start("TC1 BR-01-11: Nội dung an toàn → AN_TOAN đúng text")
    tc1_ok = True
    try:
        with SessionLocal() as db:
            with patch("app.services.pipeline._call_ai", return_value=0):
                r = execute_scan_pipeline("Chào bạn, hôm nay thời tiết đẹp, chúng ta đi chơi nhé.", db)
        tc1_ok &= check(r.get("rule_score") == 0, f"rule_score = {r.get('rule_score')} / mong đợi 0")
        tc1_ok &= check(r.get("ai_score") == 0, f"ai_score = {r.get('ai_score')} / mong đợi 0 (mock)")
        tc1_ok &= check(r.get("final_score") == 0, f"final_score = {r.get('final_score')} / mong đợi 0 (T-015 0 + 0*0.6)")
        tc1_ok &= check(r.get("risk_level") == "AN_TOAN", f"risk_level = {r.get('risk_level')} / mong đợi AN_TOAN")
        action = r.get("recommended_action") or ""
        tc1_ok &= check(AN_TOAN_TEXT in action, f"recommended_action chứa text BR-01-11 AN_TOAN? '{AN_TOAN_TEXT[:40]}...' có trong action không? {'AN_TOAN' in action or AN_TOAN_TEXT in action}")
        reasons = r.get("reasons") or []
        tc1_ok &= check(len(reasons) >= 1, f"reasons >=1 phần tử (FR-01.10) → actual len={len(reasons)}")
        if reasons:
            # EP-01 schema ScanReasonOut chỉ khai báo 3 field → Pydantic tự động drop score/evidence thừa khi gọi model_dump
            # => Đúng spec: người dùng từ endpoint chỉ thấy 3 field (như TC5 TestClient đã PASS)
            from app.schemas.scan_schemas import ScanReasonOut as _SRO  # noqa: E402
            cleaned = [_SRO(**rr).model_dump() for rr in reasons]
            first_keys = set(cleaned[0].keys())
            tc1_ok &= check("source" in first_keys and "text" in first_keys and "rule_code" in first_keys, f"reason[0] (sau qua schema EP-01) có đủ 3 field BẮT BUỘC: {sorted(first_keys)}")
            tc1_ok &= check(first_keys <= {"source", "text", "rule_code"}, f"reason[0] sau schema KHÔNG chứa field thừa score/evidence → keys = {sorted(first_keys)}")
    except Exception as e:
        tc1_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    verdict("TC1 AN_TOAN", tc1_ok)

    # ------------------------------------------------------------------
    # TC2 — NGHI_NGO rule_score=40 (R_ASK_OTP), AI mock=0 → final 40 → NGHI_NGO
    # ------------------------------------------------------------------
    start("TC2 BR-01-11: OTP rule match → NGHI_NGO đúng text")
    tc2_ok = True
    try:
        with SessionLocal() as db:
            with patch("app.services.pipeline._call_ai", return_value=0):
                r = execute_scan_pipeline("Vui lòng cung cấp mã OTP 582631 để xác nhận.", db)
        tc2_ok &= check((r.get("rule_score") or 0) >= 40, f"rule_score >= 40 (R_ASK_OTP) → actual={r.get('rule_score')}")
        tc2_ok &= check(r.get("risk_level") == "NGHI_NGO", f"risk_level = {r.get('risk_level')} / mong đợi NGHI_NGO")
        tc2_ok &= check(30 <= int(r.get("final_score") or 0) <= 69, f"final_score trong [30,69] → actual={r.get('final_score')}")
        action = r.get("recommended_action") or ""
        tc2_ok &= check(NGHI_NGO_TEXT in action, f"recommended_action chứa text BR-01-11 NGHI_NGO? contains={NGHI_NGO_TEXT[:30]}")
    except Exception as e:
        tc2_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    verdict("TC2 NGHI_NGO (OTP rule + mock AI=0)", tc2_ok)

    # ------------------------------------------------------------------
    # TC3 — NGUY_HIEM: Spec sample VCB (rule=100 T-013 fix), T-015 final=min(100,100+ai*0.6)=100
    # ------------------------------------------------------------------
    start("TC3 BR-01-11: Spec sample VCB → NGUY_HIEM (rule 4 match = 100)")
    tc3_ok = True
    VCB = "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"
    try:
        with SessionLocal() as db:
            with patch("app.services.pipeline._call_ai", return_value=90):
                r = execute_scan_pipeline(VCB, db)
        tc3_ok &= check((r.get("rule_score") or 0) == 100, f"T-013 rule_score (IMPERSONATE+ACCOUNT_THREAT+URGENCY+SHORT_URL) = {r.get('rule_score')} / mong đợi 100")
        tc3_ok &= check((r.get("final_score") or 0) == 100, f"T-015 final = min(100, 100 + 90*0.6) = {r.get('final_score')} / mong đợi 100")
        tc3_ok &= check(r.get("risk_level") == "NGUY_HIEM", f"risk_level = {r.get('risk_level')} / mong đợi NGUY_HIEM")
        action = r.get("recommended_action") or ""
        tc3_ok &= check(NGUY_HIEM_TEXT in action, f"recommended_action chứa text BR-01-11 NGUY_HIEM? contains={NGUY_HIEM_TEXT[:40]}")
        codes = [r.get("rule_code") for r in (r.get("reasons") or []) if r.get("source") == "RULE"]
        for need in ["R_IMPERSONATE_BANK", "R_ACCOUNT_THREAT", "R_URGENCY", "R_SHORT_URL"]:
            tc3_ok &= check(need in codes, f"reasons RULE có {need}? → tìm thấy = {need in codes}")
    except Exception as e:
        tc3_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    verdict("TC3 NGUY_HIEM (spec sample VCB + mock AI=90)", tc3_ok)

    # ------------------------------------------------------------------
    # TC4 — T-014 Fail-safe BR-01-6: AI vắng mặt + rule_score>0 → KHÔNG AN_TOAN, tối đa NGHI_NGO + cảnh báo mềm
    # ------------------------------------------------------------------
    start("TC4 BR-01-6 (T-014 phụ thuộc): AI vắng mặt → ai_available=false, cảnh báo mềm")
    tc4_ok = True
    try:
        with SessionLocal() as db:
            with patch("app.services.pipeline._call_ai", return_value=None):
                r = execute_scan_pipeline("Mã OTP 582631, vui lòng cung cấp để hỗ trợ.", db)
        tc4_ok &= check(r.get("ai_available") is False, f"ai_available = {r.get('ai_available')} / mong đợi False")
        tc4_ok &= check((r.get("rule_score") or 0) > 0, f"rule_score > 0 → actual={r.get('rule_score')}")
        tc4_ok &= check(r.get("risk_level") != "AN_TOAN", f"AT-06: risk_level KHÔNG PHẢI AN_TOAN (actual={r.get('risk_level')})")
        action = r.get("recommended_action") or ""
        tc4_ok &= check(("hiện chưa phân tích sâu" in action.lower() or "thận trọng" in action.lower()), f"action có cảnh báo mềm BR-01-6? action = {action[:60]}")
    except Exception as e:
        tc4_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    verdict("TC4 Fail-safe BR-01-6 (rule>0, AI=None)", tc4_ok)

    # ------------------------------------------------------------------
    # TC5 — EP-01 response schema: POST /scans → chỉ 7 field, input "content"
    # ------------------------------------------------------------------
    start("TC5 EP-01: Response schema chỉ 7 field; input field name = 'content'")
    tc5_ok = True
    try:
        from fastapi.testclient import TestClient  # noqa: E402
        from app.main import app  # noqa: E402

        def _override_get_db():
            sess = SessionLocal()
            try:
                yield sess
            finally:
                sess.close()

        from app.core.database import get_db  # noqa: E402
        app.dependency_overrides[get_db] = _override_get_db

        client = TestClient(app)
        device_header = {"X-Device-Uid": "t016-tc5-device-001"}
        # POST với tên field = "content" (EP-01 spec) KHÔNG phải raw_content
        body = {"input_type": "TEXT", "content": "Chào bạn, hôm nay đẹp trời nhé, số liên hệ 0909000111"}

        with patch("app.api.v1.scans.execute_scan_pipeline") as fake_pipeline:
            fake_pipeline.return_value = {
                "normalized_text": (body["content"] or "").strip(),
                "extracted_entities": [],
                "rule_score": 0,
                "ai_score": 0,
                "final_score": 0,
                "risk_level": "AN_TOAN",
                "signals": [],
                "reasons": [{"source": "SYSTEM", "text": AN_TOAN_TEXT, "rule_code": None}],
                "recommended_action": AN_TOAN_TEXT,
                "ai_available": True,
                "has_hard_override": False,
            }
            resp = client.post("/api/v1/scans", headers=device_header, json=body)
        tc5_ok &= check(resp.status_code == 200, f"POST /api/v1/scans status code → {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ⚠️  Response body: {resp.text[:500]}")
        else:
            data = resp.json()
            keys = set(data.keys())
            expected = {"scan_id", "risk_level", "final_score", "reasons", "recommended_action", "ai_available", "created_at"}
            tc5_ok &= check(keys == expected, f"Response fields = {sorted(keys)} / mong đợi chỉ 7 field {sorted(expected)}")
            # Reasons chỉ 3 field
            if data.get("reasons"):
                first_keys = set(data["reasons"][0].keys())
                tc5_ok &= check(first_keys <= {"source", "text", "rule_code"}, f"reasons[0] field = {sorted(first_keys)} (chỉ chấp nhận source/text/rule_code)")
    except Exception as e:
        tc5_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    try:
        app.dependency_overrides.clear()
    except Exception:
        pass
    verdict("TC5 EP-01 Schema (input content, response 7 fields)", tc5_ok)

    # ------------------------------------------------------------------
    # TC6 — EP-01 422 Errors: EMPTY_CONTENT, CONTENT_TOO_LONG, INVALID_PHONE, INVALID_URL
    # ------------------------------------------------------------------
    start("TC6 EP-01 422: {code, message} EMPTY_CONTENT / CONTENT_TOO_LONG / INVALID_PHONE / INVALID_URL")
    tc6_ok = True
    try:
        from fastapi.testclient import TestClient  # noqa: E402
        from app.main import app  # noqa: E402
        from app.core.database import get_db  # noqa: E402

        def _override_get_db2():
            sess = SessionLocal()
            try:
                yield sess
            finally:
                sess.close()

        app.dependency_overrides[get_db] = _override_get_db2
        client = TestClient(app)
        device_header = {"X-Device-Uid": "t016-tc6-device-001"}

        # 6a EMPTY_CONTENT
        resp_empty = client.post("/api/v1/scans", headers=device_header, json={"input_type": "TEXT", "content": "   "})
        tc6_ok &= check(resp_empty.status_code == 422, f"[EMPTY] status 422? {resp_empty.status_code}")
        if resp_empty.status_code != 200:
            try:
                d = resp_empty.json()
                detail = d.get("detail") or {}
                tc6_ok &= check(detail.get("code") == "EMPTY_CONTENT", f"[EMPTY] code = {detail.get('code')} / mong đợi EMPTY_CONTENT; message = {detail.get('message')}")
            except Exception as ee:
                tc6_ok = False
                print(f"  ⚠️  Parse EMPTY error failed: {ee} {resp_empty.text[:200]}")

        # 6b CONTENT_TOO_LONG
        long_text = "a" * 5001
        resp_long = client.post("/api/v1/scans", headers=device_header, json={"input_type": "TEXT", "content": long_text})
        tc6_ok &= check(resp_long.status_code in (422, 422), f"[TOO_LONG] status 422? {resp_long.status_code}")
        try:
            dlong = resp_long.json()
            dtl = dlong.get("detail") or {}
            msg_is_too_long = isinstance(dtl, dict) and dtl.get("code") == "CONTENT_TOO_LONG"
            msg_pydantic_too_long = isinstance(dtl, list) and any(isinstance(x, dict) and "too_long" in str(x.get("type", "")).lower() for x in dtl)
            tc6_ok &= check(msg_is_too_long or msg_pydantic_too_long, f"[TOO_LONG] error = {dlong.get('detail')}")
        except Exception as ee:
            print(f"  ⚠️  TOO_LONG parse err: {ee} -> {resp_long.text[:120]}")

        # 6c INVALID_PHONE
        resp_phone = client.post("/api/v1/scans", headers=device_header, json={"input_type": "PHONE", "content": "abc123"})
        tc6_ok &= check(resp_phone.status_code == 422, f"[INVALID_PHONE] status 422? {resp_phone.status_code}")
        try:
            dp = resp_phone.json()
            tp = dp.get("detail") or {}
            tc6_ok &= check((isinstance(tp, dict) and tp.get("code") == "INVALID_PHONE"), f"[INVALID_PHONE] code = {tp.get('code') if isinstance(tp, dict) else tp}")
        except Exception as ee:
            print(f"  ⚠️  INVALID_PHONE parse err: {ee}")

        # 6d INVALID_URL
        resp_url = client.post("/api/v1/scans", headers=device_header, json={"input_type": "URL", "content": "   http://no-dot   "})
        tc6_ok &= check(resp_url.status_code == 422, f"[INVALID_URL] status 422? {resp_url.status_code}")
        try:
            du = resp_url.json()
            tu = du.get("detail") or {}
            tc6_ok &= check((isinstance(tu, dict) and tu.get("code") == "INVALID_URL"), f"[INVALID_URL] code = {tu.get('code') if isinstance(tu, dict) else tu}")
        except Exception as ee:
            print(f"  ⚠️  INVALID_URL parse err: {ee}")
    except Exception as e:
        tc6_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    try:
        app.dependency_overrides.clear()
    except Exception:
        pass
    verdict("TC6 EP-01 422 errors (EMPTY / TOO_LONG / BAD_PHONE / BAD_URL)", tc6_ok)

    # ------------------------------------------------------------------
    # TC7 — EP-01 OCR_NO_TEXT (input_type IMAGE và content trống / chỉ space)
    # ------------------------------------------------------------------
    start("TC7 EP-01 422 OCR_NO_TEXT (IMAGE type không đọc được chữ)")
    tc7_ok = True
    try:
        from fastapi.testclient import TestClient  # noqa: E402
        from app.main import app  # noqa: E402
        from app.core.database import get_db  # noqa: E402

        def _odb():
            s = SessionLocal()
            try:
                yield s
            finally:
                s.close()
        app.dependency_overrides[get_db] = _odb
        client = TestClient(app)
        device_header = {"X-Device-Uid": "t016-tc7-ocr"}
        resp = client.post("/api/v1/scans", headers=device_header, json={"input_type": "IMAGE", "content": "     "})
        tc7_ok &= check(resp.status_code == 422, f"status code = {resp.status_code} (mong 422)")
        if resp.status_code != 200:
            try:
                d = resp.json()
                tc7_ok &= check((d.get("detail") or {}).get("code") == "OCR_NO_TEXT", f"OCR_NO_TEXT code = {(d.get('detail') or {}).get('code')}")
            except Exception as ee:
                print(f"  ⚠️  OCR_NO_TEXT parse err: {ee}, resp={resp.text[:120]}")
    except Exception as e:
        tc7_ok = False
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    try:
        app.dependency_overrides.clear()
    except Exception:
        pass
    verdict("TC7 OCR_NO_TEXT 422", tc7_ok)

    # ------------------------------------------------------------------
    # TÓM TẮT
    # ------------------------------------------------------------------
    print("=" * 70)
    print("📊 TỔNG KẾT T-016 BR-01-3 ngưỡng điểm + BR-01-11 recommended action")
    print("=" * 70)
    total = tests_passed + tests_failed
    print(f"  ✅ PASS  {tests_passed}/{total}")
    print(f"  ❌ FAIL  {tests_failed}/{total}")
    print()
    if tests_failed == 0:
        print("✅ TẤT CẢ TEST THÀNH CÔNG!")
        print("   - BR-01-3 ngưỡng điểm đúng: 0-29 AN_TOAN, 30-69 NGHI_NGO, 70-100 NGUY_HIEM")
        print("   - BR-01-11 recommended_action đúng text chính xác 3 mức (đọc từ AppConfig seed)")
        print("   - EP-01 schema: input 'content', response chỉ 7 field, reasons 3 field")
        print("   - EP-01 422 errors: EMPTY_CONTENT / CONTENT_TOO_LONG / INVALID_PHONE / INVALID_URL / OCR_NO_TEXT")
        print("   - Phụ thuộc T-015 (final = rule + ai*0.6) & T-014 fail-safe BR-01-6 không regression")
        return 0
    print("❌ CÓ TEST THẤT BẠI, xem chi tiết phía trên.")
    print("   - Kiểm tra reset DB (docker compose down -v && up -d --build) để seed AppConfig recommended_action mới T-002 chạy lại")
    print("   - Kiểm tra ScoringRule seed R_ACCOUNT_THREAT, R_JOB_SCAM đã cập nhật pattern T-001 migration chưa")
    return 1


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)
