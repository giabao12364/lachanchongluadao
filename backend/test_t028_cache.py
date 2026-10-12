"""
T-028 FR-03 — Test tự động Cache Redis + Invalidation cho EP-05 & EP-10
=======================================================================
Yêu cầu T-028:
  TC1 EP-05: Call 1 X-Cache: MISS  → Call 2 X-Cache: HIT (giảm query DB)
  TC2 EP-10: Call 1 X-Cache: MISS  → Call 2 X-Cache: HIT
  TC3 Insert 1 ScamPattern active mới via ORM → cache auto invalidate (invalida-
      tion event listener chạy): call EP-05 q=T028-NEW thấy bản mới, X-Cache: MISS
  TC4 Update title ScamPattern đang active via ORM (session.commit) → cache auto
      invalidate: call EP-10 id đó thấy title MỚI, X-Cache: MISS (không còn cũ)

Chạy:
  cd e:\lachanchongluadao\backend
  docker compose exec -e ENV=dev web python /app/test_t028_cache.py
"""
import sys
import uuid as uuid_lib

from app.core.cache import (
    cache_invalidate_all_pattern,
)
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
    _HEAD = {"X-Device-Uid": "t028-test-device-001"}
except Exception as e:
    print(f"[FATAL] Không thể tạo TestClient app.main: {e}")
    sys.exit(1)


def _ep05(params):
    return _CLIENT.get("/api/v1/scam-patterns", params=params, headers=_HEAD)


def _ep10(pid):
    return _CLIENT.get(f"/api/v1/scam-patterns/{pid}", headers=_HEAD)


def _cleanup(db):
    try:
        db.query(ScamPattern).filter(ScamPattern.title.like("[T028-%")).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")


# ================================================================
# TC1 — EP-05 cache hoạt động: Lần 1 MISS → Lần 2 HIT
# ================================================================
print("\n=== TC1 — [T-028.1] EP-05 Cache: Lần 1 MISS → Lần 2 HIT (header X-Cache) ===")
# Bắt đầu: invalidate cache để test từ trạng thái sạch
cache_invalidate_all_pattern()

r1 = _ep05({"q": "T028-BOOTSTRAP-NOTFOUND-123456789", "limit": 5})
case("call #1 status = 200", r1.status_code == 200,
     f"actual={r1.status_code} text={r1.text[:120]}")
xc1 = r1.headers.get("X-Cache", "")
case("call #1 header X-Cache = MISS (cache rỗng hoặc vừa invalidated)",
     xc1.upper() == "MISS", f"actual X-Cache={xc1!r}")

r2 = _ep05({"q": "T028-BOOTSTRAP-NOTFOUND-123456789", "limit": 5})
case("call #2 status = 200", r2.status_code == 200,
     f"actual={r2.status_code} text={r2.text[:120]}")
xc2 = r2.headers.get("X-Cache", "")
case("call #2 header X-Cache = HIT (đã được cache từ call #1)",
     xc2.upper() == "HIT", f"actual X-Cache={xc2!r}")


# ================================================================
# TC2 — EP-10 detail cache: insert 1 active → call 1 MISS → call 2 HIT
# ================================================================
print("\n=== TC2 — [T-028.2] EP-10 Cache: Insert active → Call #1 MISS → Call #2 HIT ===")
db2 = SessionLocal()
DETAIL_ID = None
try:
    _cleanup(db2)
    obj = ScamPattern(
        title="[T028-A1] Test cache EP-10 đủ 3 khối",
        category="Mạo danh",
        description="Mẫu T028 TC2: test cache detail EP-10",
        signs="S1. Dấu hiệu mẫu test cache\nS2. Gọi điện đe doạ",
        example_content="VD mẫu cache: 'Chào anh, em là A1 kiểm tra tài khoản anh...'",
        recommended_action="RA1. Không cung cấp OTP\nRA2. CÚNG máy\nRA3. Gửi tin về 5657",
        is_active=True,
    )
    db2.add(obj)
    db2.flush()
    DETAIL_ID = str(obj.id)
    db2.commit()
except Exception as e:
    db2.rollback()
    case("insert ScamPattern active đủ 3 khối thành công", False, f"exception={e}")
finally:
    db2.close()

case(f"insert T028-A1 active OK — id={DETAIL_ID}",
     DETAIL_ID is not None, f"actual={DETAIL_ID}")

if DETAIL_ID:
    # Invalidate cache sau khi insert (để event listener tự chạy thì insert
    # ở trên có gọi; nhưng ở đây test riêng TC2 nên invalidate explicit cho chắc)
    cache_invalidate_all_pattern(DETAIL_ID)

    rd1 = _ep10(DETAIL_ID)
    case("EP-10 call #1 status = 200", rd1.status_code == 200,
         f"actual={rd1.status_code} text={rd1.text[:120]}")
    xcd1 = rd1.headers.get("X-Cache", "")
    case("EP-10 call #1 X-Cache = MISS (detail cache chưa có)",
         xcd1.upper() == "MISS", f"actual X-Cache={xcd1!r}")
    if rd1.status_code == 200:
        try:
            bd1 = rd1.json()
            case("EP-10 call #1 title chứa [T028-A1]",
                 isinstance(bd1.get("title"), str) and "[T028-A1]" in bd1["title"],
                 f"actual title={bd1.get('title')!r}")
        except Exception:
            pass

    rd2 = _ep10(DETAIL_ID)
    case("EP-10 call #2 status = 200", rd2.status_code == 200,
         f"actual={rd2.status_code} text={rd2.text[:120]}")
    xcd2 = rd2.headers.get("X-Cache", "")
    case("EP-10 call #2 X-Cache = HIT (lấy từ cache detail id)",
         xcd2.upper() == "HIT", f"actual X-Cache={xcd2!r}")


# ================================================================
# TC3 — Insert NEW active via ORM → Event listener auto invalidate cache
#         => EP-05 tiếp theo thấy bản MỚI, X-Cache = MISS (cache đã clear)
# ================================================================
print("\n=== TC3 — [T-028.3] Invalidation after INSERT: event listener auto clear cache ===")
NEW_ID = None
db3 = SessionLocal()
try:
    obj3 = ScamPattern(
        title="[T028-NEW] Vừa mới insert CMS — cache phải thấy ngay",
        category="Đòi nợ",
        description="Mẫu T028 TC3: test cache invalidation sau khi insert mới",
        signs="S1. Gọi điện tự xưng đồng đội đòi nợ 50tr trong 24h\nS2. Đe doạ đến nhà",
        example_content="VD: 'Anh Tèo đây, em nợ 50tr, 24h chưa trả đến nhà lấy giấy'",
        recommended_action="RA1. Không chuyển tiền\nRA2. Gọi 113 nếu có đe doạ\nRA3. Chụp màn hình gửi về 5657",
        is_active=True,
    )
    db3.add(obj3)
    db3.flush()
    NEW_ID = str(obj3.id)
    # Event listener after_insert sẽ gọi cache_invalidate_all_pattern() tự động ở commit
    db3.commit()
except Exception as e:
    db3.rollback()
    case("insert [T028-NEW] active via ORM thành công", False, f"exception={e}")
finally:
    db3.close()

case("insert [T028-NEW] OK (event listener after_insert được trigger khi commit)",
     NEW_ID is not None, f"NEW_ID={NEW_ID}")

if NEW_ID is not None:
    # Sau khi insert xong, EP-05 phải THẤY luôn bản mới (nếu cache bị invalidated đúng)
    r3 = _ep05({"q": "T028-NEW CMS đòi nợ"})
    case("EP-05 sau insert status = 200", r3.status_code == 200,
         f"actual={r3.status_code}")
    try:
        b3 = r3.json()
        titles3 = [i.get("title", "") for i in (b3.get("items") or [])]
        case("EP-05 sau insert THẤY luôn [T028-NEW] trong kết quả (cache invalidated, không đọc cache cũ)",
             any("[T028-NEW]" in t for t in titles3),
             f"actual titles={titles3}")
    except Exception as e:
        case("EP-05 parse JSON OK", False, f"err={e} text={r3.text[:200]}")
    # Sau khi cache bị xóa ở TC3, lần gọi này sẽ SET cache mới -> X-Cache phải là MISS
    xc3 = r3.headers.get("X-Cache", "")
    case("EP-05 sau insert X-Cache = MISS (active_rows cache đã bị clear bởi event listener)",
         xc3.upper() == "MISS", f"actual X-Cache={xc3!r}")


# ================================================================
# TC4 — UPDATE title của bản đang active via ORM → event listener auto invalidate
#         => EP-10 gọi tiếp thấy title MỚI, X-Cache = MISS
# ================================================================
print("\n=== TC4 — [T-028.4] Invalidation after UPDATE: event listener auto clear cache ===")
UPDATED_ID = DETAIL_ID  # dùng TC2-A1 (đã exists) làm mẫu update
UPDATE_OK = False
if UPDATED_ID is not None:
    db4 = SessionLocal()
    try:
        obj4 = db4.query(ScamPattern).filter(ScamPattern.id == uuid_lib.UUID(DETAIL_ID)).first()
        obj4_title = obj4.title if obj4 else None
        case("load [T028-A1] từ DB để update",
             obj4 is not None and obj4_title and "[T028-A1]" in str(obj4_title),
             f"obj4 is None={obj4 is None}")
        if obj4:
            NEW_TITLE = "[T028-A1-UPDATED] Đã sửa title CMS — cache phải thấy thay đổi"
            obj4.title = NEW_TITLE
            # T-025 BR-03-2: is_active=true, đủ 3 khối rồi nên không cần set lại
            db4.add(obj4)
            db4.flush()
            # event listener after_update sẽ gọi cache_invalidate_all_pattern(id) tự động
            db4.commit()
            UPDATE_OK = True
    except Exception as e:
        db4.rollback()
        UPDATE_OK = False
        print(f"  [WARN] update T028-A1 lỗi exception: {e}")
    finally:
        db4.close()

case("update [T028-A1] title via ORM → commit triggered after_update event",
     UPDATE_OK, f"actual UPDATE_OK={UPDATE_OK}")

if UPDATE_OK and UPDATED_ID is not None:
    # Sau update, gọi EP-10 → phải thấy title MỚI, và X-Cache = MISS (detail cache đã bị xóa)
    rd4 = _ep10(UPDATED_ID)
    case("EP-10 sau update status = 200", rd4.status_code == 200,
         f"actual={rd4.status_code}")
    xcd4 = rd4.headers.get("X-Cache", "")
    case("EP-10 sau update X-Cache = MISS (detail cache cũ đã bị xóa bởi after_update)",
         xcd4.upper() == "MISS", f"actual X-Cache={xcd4!r}")
    if rd4.status_code == 200:
        try:
            bd4 = rd4.json()
            case("EP-10 sau update title = [T028-A1-UPDATED] (thấy luôn thay đổi CMS, không cache cũ)",
                 isinstance(bd4.get("title"), str) and "[T028-A1-UPDATED]" in bd4["title"],
                 f"actual title={bd4.get('title')!r}")
        except Exception as e:
            case("EP-10 parse JSON OK", False, f"err={e}")


# ================================================================
# Cleanup + Tổng kết
# ================================================================
db5 = SessionLocal()
try:
    _cleanup(db5)
    print("\n[CLEANUP] Đã xóa toàn bộ rows title LIKE '[T028-%' khỏi scam_pattern.")
    cache_invalidate_all_pattern()
    print("[CLEANUP] Đã flush cache scam_pattern Redis.")
except Exception as e:
    print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")
finally:
    db5.close()

print("\n" + "=" * 80)
print(f"KET QUA:  PASS = {PASS_CNT}   |   FAIL = {FAIL_CNT}")
if FAIL_LOG:
    print("\n[DANH SACH TEST FAIL]:")
    for m in FAIL_LOG:
        print("   ", m)
    print("\n=> CHƯA PASS T-028, sửa các mục trên rồi chạy lại.")
    sys.exit(1)
else:
    print("✅ T-028: Tat ca test case PASSED! (Cache HIT/MISS + Auto invalidation insert/update)")
    sys.exit(0)
