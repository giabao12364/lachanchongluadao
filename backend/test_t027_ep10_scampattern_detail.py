"""
T-027 FR-03 EP-10 — Test tự động GET /scam-patterns/{id} (chi tiết)
===================================================================
Yêu cầu T-027:
  - ID sai định dạng (không phải UUID) → 400 INVALID_ID
  - ID đúng UUID nhưng KHÔNG tồn tại → 404 SCAM_PATTERN_NOT_FOUND
  - ID tồn tại nhưng is_active=false (NHÁP, thiếu khối) → 404 (ẨN, KHÔNG public)
  - ID tồn tại, is_active=true, đủ 3 khối → 200 OK, đủ 8 fields, 3 khối không rỗng

Chạy:
  cd e:\lachanchongluadao\backend
  docker compose exec -e ENV=dev web python /app/test_t027_ep10_scampattern_detail.py
"""
import sys
import uuid

from app.core.database import SessionLocal
from app.models.db_models import ScamPattern

PASS_CNT = 0
FAIL_CNT = 0
FAIL_LOG = []


def case(name, cond, detail=""):
    global PASS_CNT, FAIL_CNT
    if cond:
        PASS_CNT += 1
        print(f"  ✅ PASS  {name}")
    else:
        FAIL_CNT += 1
        msg = f"  ❌ FAIL  {name}" + (f"  | {detail}" if detail else "")
        FAIL_LOG.append(msg)
        print(msg)


# ---- Setup TestClient ----
try:
    from fastapi.testclient import TestClient
    from app.main import app
    _CLIENT = TestClient(app)
    _HEAD = {"X-Device-Uid": "t027-test-device-001"}
except Exception as e:
    print(f"[FATAL] Không thể tạo TestClient app.main: {e}")
    sys.exit(1)


def _ep10(pattern_id):
    return _CLIENT.get(f"/api/v1/scam-patterns/{pattern_id}", headers=_HEAD)


def _code_from_body(body: dict) -> str:
    """Lấy code từ body L3.4 root {code, message, extra}."""
    if isinstance(body, dict) and isinstance(body.get("code"), str):
        return str(body["code"])
    return ""


def _cleanup(db):
    """Xóa các hàng test T-027 đã insert dựa trên title LIKE '[T027-%'"""
    try:
        db.query(ScamPattern).filter(ScamPattern.title.like("[T027-%")).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")


# ================================================================
# TC0 — ID sai định dạng (không phải UUID) → 400 INVALID_ID
# ================================================================
print("\n=== TC0 — [T-027.1] ID sai định dạng 'NOT-A-UUID!!!' → 400 INVALID_ID ===")
r0 = _ep10("NOT-A-UUID!!!")
case("status = 400", r0.status_code == 400,
     f"actual={r0.status_code} text={r0.text[:150]}")
try:
    b0 = r0.json()
    code0 = _code_from_body(b0)
    case("code = INVALID_ID (L3.4 root {code,message,extra})",
         code0 == "INVALID_ID",
         f"actual code={code0!r} body={b0}")
except Exception as e:
    case("body parseable + code INVALID_ID", False,
         f"parse err={e} text={r0.text[:200]}")


# ================================================================
# TC1 — ID đúng định dạng UUID nhưng KHÔNG tồn tại → 404 SCAM_PATTERN_NOT_FOUND
# ================================================================
print("\n=== TC1 — [T-027.2] ID UUID không tồn tại → 404 SCAM_PATTERN_NOT_FOUND ===")
fake_id = str(uuid.uuid4())  # UUID ngẫu nhiên, chắc chắn không có trong DB
r1 = _ep10(fake_id)
case("status = 404", r1.status_code == 404,
     f"actual={r1.status_code} text={r1.text[:150]}")
try:
    b1 = r1.json()
    code1 = _code_from_body(b1)
    case("code = SCAM_PATTERN_NOT_FOUND (L3.4)",
         code1 == "SCAM_PATTERN_NOT_FOUND",
         f"actual code={code1!r} body={b1}")
except Exception as e:
    case("body parseable + code SCAM_PATTERN_NOT_FOUND", False,
         f"parse err={e} text={r1.text[:200]}")


# ================================================================
# TC2 — ID tồn tại nhưng is_active=false (NHÁP thiếu khối) → 404 (ẨN)
# ================================================================
print("\n=== TC2 — [T-027.3] Draft is_active=false (thiếu 3 khối) → 404 ẨN ===")
_db2 = SessionLocal()
DRAFT_ID = None
try:
    _cleanup(_db2)
    draft = ScamPattern(
        title="[T027-DRAFT] Nháp thiếu khối — phải ẩn trên EP-10",
        category="Mạo danh",
        description="Mẫu nháp test T-027 TC2 — EP-10 phải 404, không được public",
        signs=None,
        example_content=None,
        recommended_action=None,
        is_active=False,
    )
    _db2.add(draft)
    _db2.flush()
    DRAFT_ID = str(draft.id)
    _db2.commit()
except Exception as e:
    _db2.rollback()
    case("insert NHÁP thiếu 3 khối thành công (ORM)", False, f"exception={e}")
finally:
    _db2.close()

case("insert NHÁP thiếu 3 khối thành công (ORM) — có DRAFT_ID",
     DRAFT_ID is not None, f"DRAFT_ID={DRAFT_ID}")

if DRAFT_ID:
    r2 = _ep10(DRAFT_ID)
    case("EP-10 status = 404 (ẨN nháp, KHÔNG public) — dù ID TỒN TẠI trong DB",
         r2.status_code == 404,
         f"actual={r2.status_code} text={r2.text[:150]}")
    try:
        b2 = r2.json()
        code2 = _code_from_body(b2)
        case("EP-10 code = SCAM_PATTERN_NOT_FOUND (draft ẩn giống not found)",
             code2 == "SCAM_PATTERN_NOT_FOUND",
             f"actual code={code2!r} body={b2}")
    except Exception as e:
        case("body parseable + code SCAM_PATTERN_NOT_FOUND", False,
             f"parse err={e} text={r2.text[:200]}")


# ================================================================
# TC3 — ID ACTIVE đủ 3 khối → 200 OK, đủ 8 fields, 3 khối không rỗng
# ================================================================
print("\n=== TC3 — [T-027.4] Active đủ 3 khối → 200 OK đủ fields + 3 khối hợp lệ ===")
ACTIVE_ID = None
_db3 = SessionLocal()
try:
    active = ScamPattern(
        title="[T027-ACTIVE] Mạo danh Công an A01 đòi chuyển tiền giữ tài sản",
        category="Mạo danh",
        description="Test T-027 TC3 — active đầy đủ 3 khối signs/example/recommended",
        signs="S1. Người lạ gọi điện tự giới thiệu là Công an A01\nS2. Đòi thông tin CCCD/STK ngân hàng\nS3. Đe dọa bắt giữ nếu không làm theo",
        example_content="VD: 'Anh Chí đây là trung tá A01, em bị dính hồ sơ ma túy, chuyển 200tr vào tài khoản 007 giữ, 1 tiếng trả lại.'",
        recommended_action="RA1. KHÔNG cung cấp OTP / số thẻ / CCCD\nRA2. CÚNG máy ngay, không lý luận\nRA3. Chụp màn hình + gửi tin nhắn về 5657 để đối chiếu",
        is_active=True,
    )
    _db3.add(active)
    _db3.flush()
    ACTIVE_ID = str(active.id)
    _db3.commit()
except Exception as e:
    _db3.rollback()
    case("insert ACTIVE đầy đủ 3 khối hợp lệ thành công", False, f"exception={e}")
finally:
    _db3.close()

case("insert ACTIVE đủ 3 khối thành công (ORM) — có ACTIVE_ID",
     ACTIVE_ID is not None, f"ACTIVE_ID={ACTIVE_ID}")

if ACTIVE_ID:
    r3 = _ep10(ACTIVE_ID)
    case("EP-10 status = 200", r3.status_code == 200,
         f"actual={r3.status_code} text={r3.text[:200]}")
    try:
        b3 = r3.json()
        required_fields = [
            "id", "title", "category", "image_url",
            "signs", "example_content", "recommended_action",
            "created_at",
        ]
        missing_fields = [f for f in required_fields if f not in b3]
        case("đủ 8 fields trong body (id, title, category, image_url, 3 khối, created_at)",
             len(missing_fields) == 0,
             f"missing={missing_fields} keys=list(b3.keys())")
        if len(missing_fields) == 0:
            case("id trả về trùng với ACTIVE_ID đã insert",
                 str(b3["id"]) == ACTIVE_ID,
                 f"response.id={b3['id']!r} expected={ACTIVE_ID!r}")
            case("signs KHÔNG NULL / rỗng (BR-03-2 active phải đủ khối)",
                 isinstance(b3.get("signs"), str) and b3["signs"].strip() != "",
                 f"actual signs={b3.get('signs')!r}")
            case("example_content KHÔNG NULL / rỗng (BR-03-2 active phải đủ khối)",
                 isinstance(b3.get("example_content"), str) and b3["example_content"].strip() != "",
                 f"actual example_content={b3.get('example_content')!r}")
            case("recommended_action KHÔNG NULL / rỗng (BR-03-2 active phải đủ khối)",
                 isinstance(b3.get("recommended_action"), str) and b3["recommended_action"].strip() != "",
                 f"actual recommended_action={b3.get('recommended_action')!r}")
            case("created_at ISO string kết thúc bằng 'Z' (UTC)",
                 isinstance(b3.get("created_at"), str) and b3["created_at"].endswith("Z"),
                 f"actual created_at={b3.get('created_at')!r}")
    except Exception as e:
        case("body parseable + đủ fields + 3 khối hợp lệ", False,
             f"parse err={e} text={r3.text[:200]}")


# ================================================================
# Cleanup test rows
# ================================================================
_db4 = SessionLocal()
try:
    _cleanup(_db4)
    print("\n[CLEANUP] Đã xóa toàn bộ rows title LIKE '[T027-%' khỏi scam_pattern.")
except Exception as e:
    print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")
finally:
    _db4.close()


# ================================================================
# Tổng kết
# ================================================================
print("\n" + "=" * 80)
print(f"KET QUA:  PASS = {PASS_CNT}   |   FAIL = {FAIL_CNT}")
if FAIL_LOG:
    print("\n[DANH SACH TEST FAIL]:")
    for m in FAIL_LOG:
        print("   ", m)
    print("\n=> CHƯA PASS T-027, sửa các mục trên rồi chạy lại.")
    sys.exit(1)
else:
    print("✅ T-027: Tat ca test case PASSED! (EP-10 chi tiết: 400/404 draft ẩn / 200 đủ 3 khối)")
    sys.exit(0)
