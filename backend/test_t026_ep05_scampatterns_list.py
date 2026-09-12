"""
T-026 FR-03 EP-05 — Test tự động GET /scam-patterns (v2)
========================================================
Yêu cầu BR:
  - T-026.1: tìm kiếm không dấu (Tiếng Việt ko dấu match text có dấu)
  - T-026.2: lọc category flexible (ko dấu/có dấu/UPPER/lower/dash/underscore đều OK)
  - T-026.3: phân trang cursor chuẩn (limit, next_cursor, invalid = 400)
  - T-026.4: rỗng / exception graceful (items=[], next_cursor=null / HTTP 500 message rõ)
Chạy:
  cd e:\lachanchongluadao\\backend
  docker compose exec web python /app/test_t026_ep05_scampatterns_list.py
"""
import sys

from sqlalchemy import func, or_

from app.core.database import SessionLocal
from app.core.utils import strip_diacritics, normalize_category_token
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
    _HEAD = {"X-Device-Uid": "t026-test-device-001"}
except Exception as e:
    print(f"[FATAL] Không thể tạo TestClient app.main: {e}")
    sys.exit(1)


def _ep05(params):
    return _CLIENT.get("/api/v1/scam-patterns", params=params, headers=_HEAD)


def _cleanup(db):
    """Xóa các hàng test T-026 đã insert dựa trên title LIKE '[T026-%'"""
    try:
        db.query(ScamPattern).filter(ScamPattern.title.like("[T026-%")).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")


def _code_from_body(body: dict) -> str:
    """Phân tích code lỗi đúng format L3.4 root {code,message,extra}.

    Handler app.core.exceptions.register_exception_handlers wrap tất cả
    HTTPException thành root-level { code, message, extra }.
    """
    if not isinstance(body, dict):
        return ""
    # L3.4 root {code, message, extra}
    if isinstance(body.get("code"), str):
        return str(body["code"])
    # Fallback nếu sau này có format {detail: {code, message}}
    if isinstance(body.get("detail"), dict) and isinstance(body["detail"].get("code"), str):
        return str(body["detail"]["code"])
    # Fallback detail string
    if isinstance(body.get("detail"), str):
        return ""
    return ""


# ================================================================
# TC0 — Utils T-026 chuẩn
# ================================================================
print("\n=== TC0 — Utils T-026 chuẩn ===")
case(
    "strip_diacritics bỏ dấu chính xác",
    strip_diacritics("Mạo Danh CÔNG AN A06") == "Mao Danh CONG AN A06",
    f"got={strip_diacritics('Mạo Danh CÔNG AN A06')!r}",
)
case(
    "normalize_category_token flexible Mao-Danh -> mao_danh",
    normalize_category_token("  Mạo-Danh  ") == "mao_danh",
    f"got={normalize_category_token('  Mạo-Danh  ')!r}",
)
case(
    "normalize_category_token MAO_DANH -> mao_danh",
    normalize_category_token("MAO_DANH") == "mao_danh",
    f"got={normalize_category_token('MAO_DANH')!r}",
)


# ================================================================
# TC1 — INSERT 9 active (3 cat × 3) + 1 draft bằng ORM (bỏ created_by_device_uid)
# ================================================================
CATEGORIES_MAP = {"A": "Mạo danh", "B": "Lừa đảo đầu tư", "C": "Đòi nợ"}
TITLES = {
    "A": [
        ("[T026-A1] Mạo danh Công an A06 đòi tài khoản điều hành", "Mẫu test 1 cat A: công quyền"),
        ("[T026-A2] Mạo danh ngân hàng BIDV SMS OTP lừa đảo", "Mẫu test 2 cat A: OTP"),
        ("[T026-A3] Mạo danh Bưu điện VN thu phí nhập khẩu", "Mẫu test 3 cat A: Bưu điện"),
    ],
    "B": [
        ("[T026-B1] Đầu tư BĐS Dubai lãi 25% năm", "Mẫu 1 đầu tư ROI cam kết"),
        ("[T026-B2] Quỹ cổ phiếu VNINDEX 90% tín hiệu", "Mẫu 2 đầu tư quỹ"),
        ("[T026-B3] MLM ma trận F0=3 bạn 100tr/tháng", "Mẫu 3 MLM"),
    ],
    "C": [
        ("[T026-C1] Công ty Đồng Nai Điều hành đòi nợ 120tr", "Mẫu 1 đòi nợ công ty"),
        ("[T026-C2] Đe dọa đến nhà hoi nợ + đồng đội", "Mẫu 2 đòi nợ cầm thù"),
        ("[T026-C3] Bưu điện phạt thuế 83tr 24h thư nội bộ", "Mẫu 3 thuế 24h"),
    ],
}


_SEEDED_ACTIVE_IDS = set()
_SEEDED_DRAFT_ID = None
_SEEDED_FAILED = False

print("\n=== TC1 — DB seed ORM 9 active + 1 draft ===")
_db = SessionLocal()
try:
    _cleanup(_db)

    # Draft (is_active=False) — KHÔNG cần đủ 3 khối
    draft = ScamPattern(
        title="[T026-TEST] Nháp thiếu khối (không public)",
        category="Mạo danh",
        description="Mẫu nháp test filter is_active=false",
        signs=None,
        example_content=None,
        recommended_action=None,
        is_active=False,
    )
    _db.add(draft)
    _db.flush()
    _SEEDED_DRAFT_ID = draft.id

    seq = 0
    from datetime import datetime, timedelta
    base_ts = datetime(2026, 9, 1, 10, 0, 0)

    for letter, items in TITLES.items():
        for title, desc in items:
            seq += 1
            signs = f"S{seq}.1 - Dấu hiệu mẫu {seq}"
            example_content = f"VD mẫu {seq}: Nội dung vi phạm mẫu {seq}"
            recommended_action = (
                f"RA{seq}. KHÔNG chuyển tiền, không cung cấp OTP, "
                f"chụp màn hình gửi tin nhắn về số 5657."
            )
            obj = ScamPattern(
                title=title,
                category=CATEGORIES_MAP[letter],
                description=desc,
                signs=signs,
                example_content=example_content,
                recommended_action=recommended_action,
                is_active=True,
                created_at=base_ts + timedelta(hours=seq),
                updated_at=base_ts + timedelta(hours=seq),
            )
            _db.add(obj)
            _db.flush()
            _SEEDED_ACTIVE_IDS.add(str(obj.id))
    _db.commit()

    case(
        f"inserted {len(_SEEDED_ACTIVE_IDS)} active + 1 draft OK (ORM, không cần created_by_device_uid)",
        len(_SEEDED_ACTIVE_IDS) == 9 and _SEEDED_DRAFT_ID is not None,
        f"active_count={len(_SEEDED_ACTIVE_IDS)} draft_id_null={_SEEDED_DRAFT_ID is None}",
    )
    if len(_SEEDED_ACTIVE_IDS) != 9 or _SEEDED_DRAFT_ID is None:
        _SEEDED_FAILED = True
except Exception as e:
    _db.rollback()
    case(
        "inserted 9 active + 1 draft OK (ORM)",
        False,
        f"exception type={type(e).__name__} msg={e}",
    )
    _SEEDED_FAILED = True
finally:
    _db.close()


# ================================================================
# Early exit nếu seed FAIL (chạy TC3-TC8 vô ích, chỉ sinh FAIL rác)
# ================================================================
if _SEEDED_FAILED:
    print("\n[EARLY EXIT] Seed thất bại, không thể kiểm tra các TC3..TC8 → Cleanup rồi dừng.")
    _db2 = SessionLocal()
    try:
        _cleanup(_db2)
    finally:
        _db2.close()
    print("\n" + "=" * 80)
    print(f"KET QUA:  PASS = {PASS_CNT}   |   FAIL = {FAIL_CNT}")
    for m in FAIL_LOG:
        print("   ", m)
    sys.exit(1)


# ================================================================
# TC2 — [T-026.4] Empty result -> 200 items=[] + next_cursor=null (KHÔNG 500)
# ================================================================
print("\n=== TC2 — [T-026.4] Empty search 0 match => 200 OK items=[] next_cursor=null ===")
r_empty = _ep05({"q": "XYZ_KHONG_TON_TAI_999999", "limit": 20})
case("status = 200 (không 500)", r_empty.status_code == 200,
     f"actual={r_empty.status_code} text={r_empty.text[:150]}")
try:
    body_empty = r_empty.json()
    case("items = []", isinstance(body_empty.get("items"), list) and len(body_empty["items"]) == 0,
         f"items = {body_empty.get('items')}")
    case("next_cursor = None", body_empty.get("next_cursor") is None,
         f"next_cursor = {body_empty.get('next_cursor')}")
except Exception as e:
    case("json parseable + fields OK", False, f"parse err={e} text={r_empty.text[:200]}")


# ================================================================
# TC3 — [T-026.1] Search KHÔNG DẤU "mao danh a06" => A1 match
# ================================================================
print("\n=== TC3 — [T-026.1] Search KHÔNG DẤU 'mao danh a06' match Mạo danh A06 CÓ DẤU ===")
r_noacc = _ep05({"q": "mao danh a06"})
case("status 200", r_noacc.status_code == 200, f"actual={r_noacc.status_code}")
titles_noacc = [i.get("title", "") for i in (r_noacc.json().get("items") or [])]
case("tìm được 1 bản chứa [T026-A1]",
     any("[T026-A1]" in t for t in titles_noacc),
     f"actual titles={titles_noacc}")
case("số lượng tìm được = 1 (chỉ A1 match)",
     len(titles_noacc) == 1,
     f"actual len={len(titles_noacc)} titles={titles_noacc}")


# ================================================================
# TC4 — [T-026.1] Search CÓ DẤU + KHÔNG public draft
# ================================================================
print("\n=== TC4 — [T-026.1] Search CÓ DẤU 'Đòi nợ đồng đội' => [T026-C2] + KHÔNG public draft ===")
r_acc = _ep05({"q": "Đòi nợ  đồng đội"})
case("status 200", r_acc.status_code == 200, f"actual={r_acc.status_code}")
titles_acc = [i.get("title", "") for i in (r_acc.json().get("items") or [])]
case("tìm được [T026-C2] Đe dọa đến nhà hoi nợ + đồng đội",
     any("[T026-C2]" in t for t in titles_acc),
     f"actual titles={titles_acc}")
case("không có draft '[T026-TEST] Nháp thiếu khối' (is_active=false) trong kết quả",
     not any("Nháp thiếu khối" in t for t in titles_acc),
     "Phát hiện draft lọt vào list => filter is_active=false LỖI!")


# ================================================================
# TC5 — [T-026.2] Filter category flexible 3 formats
# ================================================================
print("\n=== TC5 — [T-026.2] Filter category flexible (3 dạng input đều == 3 mẫu A) ===")
variants = [
    ("Mạo danh", "có dấu + khoảng trắng"),
    ("mao-danh",  "không dấu + dash"),
    ("MAO_DANH",  "UPPER + underscore"),
]
all_ok = True
for user_input, label in variants:
    r_cat = _ep05({"category": user_input})
    case(
        f"cat filter {user_input!r} ({label}) status=200",
        r_cat.status_code == 200,
        f"actual={r_cat.status_code}",
    )
    titles_cat = [i.get("title", "") for i in (r_cat.json().get("items") or [])]
    # Chỉ giữ các hàng T-026 (không đếm seed cũ user đã insert)
    t026_titles_in_cat = [t for t in titles_cat if t.startswith("[T026-A")]
    count_match = len(t026_titles_in_cat)
    case(
        f"cat filter {user_input!r} ({label}) → 3 mẫu T-026 [T026-A1..A3] (Mạo danh)",
        count_match == 3,
        f"count_match_t026={count_match} titles={t026_titles_in_cat}",
    )
    if count_match != 3:
        all_ok = False
    for other_prefix in ("[T026-B", "[T026-C"):
        if any(t.startswith(other_prefix) for t in titles_cat):
            all_ok = False
            case(
                f"cat filter {user_input!r} ({label}) KHÔNG lẫn cat khác",
                False,
                f"phát hiện {other_prefix} trong titles={titles_cat}",
            )
case("Tất cả 3 dạng category filter đều PASS", all_ok)


# ================================================================
# TC6 — [T-026.3] Phân trang limit=2 + next_cursor duyệt hết 9 active T-026
# ================================================================
print("\n=== TC6 — [T-026.3] Phân trang limit=2 duyệt hết 9 active T-026 ===")
expected_ids = set(_SEEDED_ACTIVE_IDS)
case("expected = 9 active T-026", len(expected_ids) == 9,
     f"actual expected_ids count={len(expected_ids)}")

seen_ids = []
cursor = None
total_pages = 0
page_idx = 0
while True:
    params = {"limit": 2, "q": "T026"}
    if cursor:
        params["cursor"] = cursor
    r_page = _ep05(params)
    case(f"page {page_idx} status=200", r_page.status_code == 200,
         f"actual={r_page.status_code}")
    body_p = r_page.json()
    items = body_p.get("items") or []
    cursor = body_p.get("next_cursor")
    # Giữ lại id T-026 mình insert (không đếm seed cũ)
    for p in items:
        pid = str(p.get("id", ""))
        if pid in expected_ids:
            seen_ids.append(pid)
    if page_idx < 4:
        # Lưu ý: nếu có seed cũ lẫn vào thì len(items) >2 vẫn có thể có, nên không assert cứng
        pass
    total_pages += 1
    page_idx += 1
    if cursor is None:
        break

case(
    "unique seen = 9, không lặp, không thiếu (đầy đủ 9 id T-026 active)",
    len(set(seen_ids)) == 9 and sorted(set(seen_ids)) == sorted(expected_ids),
    f"unique_seen={len(set(seen_ids))} seen={len(seen_ids)} expected={len(expected_ids)} missing={sorted(expected_ids - set(seen_ids))}",
)
case(
    "total pages = 5 (limit=2, 9 items: 2+2+2+2+1)",
    total_pages == 5,
    f"actual pages={total_pages}",
)


# ================================================================
# TC7 — Cursor invalid -> 400 code INVALID_CURSOR (L3.4 root-level)
# ================================================================
print("\n=== TC7 — Cursor invalid -> 400 code INVALID_CURSOR ===")
r_bad = _ep05({"cursor": "NOT_A_VALID_BASE64!!!!"})
case("status = 400", r_bad.status_code == 400,
     f"actual={r_bad.status_code} text={r_bad.text[:150]}")
try:
    body_bad = r_bad.json()
    code = _code_from_body(body_bad)
    case(
        "code = INVALID_CURSOR (L3.4 root {code,message,extra})",
        code == "INVALID_CURSOR",
        f"actual code={code!r} body={body_bad}",
    )
except Exception as e:
    case("body parseable + có code INVALID_CURSOR", False,
         f"parse err={e} text={r_bad.text[:200]}")


# ================================================================
# TC8 — Combine search không dấu + category flexible (2 filter cùng lúc)
# ================================================================
print("\n=== TC8 — Combine q='OTP lua dao' (ko dấu) + category='  mao-danh  ' (dash+space) ===")
r_cb = _ep05({
    "q": "OTP lua dao T026",
    "category": "  mao-danh  ",
    "limit": 20,
})
case("status 200", r_cb.status_code == 200, f"actual={r_cb.status_code}")
titles_cb = [i.get("title", "") for i in (r_cb.json().get("items") or [])]
case(
    "chỉ tìm được 1 bản [T026-A2] Mạo danh ngân hàng BIDV SMS OTP lừa đảo",
    len(titles_cb) == 1 and any("[T026-A2]" in t for t in titles_cb),
    f"actual titles={titles_cb}",
)


# ================================================================
# Cleanup test rows
# ================================================================
_db3 = SessionLocal()
try:
    _cleanup(_db3)
    print("\n[CLEANUP] Đã xóa toàn bộ rows title LIKE '[T026-%' khỏi scam_pattern.")
except Exception as e:
    print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")
finally:
    _db3.close()


# ================================================================
# Tổng kết
# ================================================================
print("\n" + "=" * 80)
print(f"KET QUA:  PASS = {PASS_CNT}   |   FAIL = {FAIL_CNT}")
if FAIL_LOG:
    print("\n[DANH SACH TEST FAIL]:")
    for m in FAIL_LOG:
        print("   ", m)
    print("\n=> CHƯA PASS T-026, sửa các mục trên rồi chạy lại.")
    sys.exit(1)
else:
    print("✅ T-026: Tat ca test case PASSED! (EP-05 search không dấu + category flexible + pagination + empty-safe)")
    sys.exit(0)
