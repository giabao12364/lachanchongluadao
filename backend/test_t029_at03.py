"""
T-029 FR-03 — Nghiệm thu AT-03-1 .. AT-03-5
==============================================
Mã  Kịch bản                                  Kỳ vọng
---- ----------------------------------------- ---------------------------------------
AT03-1 Thêm mẫu mới scam_pattern S-07 hiển thị Ngay khi refresh EP-05 thấy mẫu mới,
       ngay (không rebuild app, KT-02)          không cần khởi động lại app.
AT03-2 EP-10 field order theo trình đọc màn    Thứ tự: Tiêu đề -> Dấu hiệu -> Ví dụ ->
       hình S-07.1                              Khuyến nghị (JSON insertion order).
AT03-3 Search "ngan hang" (không dấu)          Trả về bài chủ đề mạo danh NGÂN HÀNG
                                                 (không dấu match có dấu, token-based).
AT03-4 1 mẫu is_active=false, gọi EP-10 id đó HTTP 404, cấm hiển thị dữ liệu ẩn.
AT03-5 XÓA SẠCH scam_pattern → gọi EP-05       HTTP 200 + items=[], giao diện "Hiện
       (không filter q/cat)                     chưa có cảnh báo mới" → backend không
                                                 crash, không 500. SAU KHI TEST xong
                                                 restore toàn bộ data seed cũ về DB.

Chạy:
  cd e:\lachanchongluadao\backend
  docker compose exec -e ENV=dev web python /app/test_t029_at03.py
"""
import copy
import sys
import uuid as uuid_lib
from typing import Any, Dict, List

from app.core.cache import cache_invalidate_all_pattern
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
    _HEAD = {"X-Device-Uid": "t029-at03-device-001"}
except Exception as e:
    print(f"[FATAL] Không thể tạo TestClient app.main: {e}")
    sys.exit(1)


def _ep05(params):
    return _CLIENT.get("/api/v1/scam-patterns", params=params, headers=_HEAD)


def _ep10(pid):
    return _CLIENT.get(f"/api/v1/scam-patterns/{pid}", headers=_HEAD)


def _cleanup_tagged(db, tag="T029"):
    """Xóa các hàng insert bởi test này, giữ lại seed cũ."""
    try:
        db.query(ScamPattern).filter(ScamPattern.title.like(f"[{tag}-%")).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[CLEANUP][WARNING] Xóa test rows tag={tag} lỗi: {e}")


# ================================================================
# AT-03-1: Insert mẫu mới → EP-05 refresh thấy ngay (KT-02: không rebuild)
# ================================================================
print("\n=== AT-03-1 [T-029.1] Insert mẫu mới active → EP-05 thấy ngay không rebuild ===")
_db1 = SessionLocal()
NEW_PATTERN_ID = None
try:
    _cleanup_tagged(_db1, "T029A1")
    new_p = ScamPattern(
        title="[T029A1-NEW] Mẫu mới thêm vào AT-03-1 (không rebuild app)",
        category="Lừa đảo đầu tư",
        description="Mẫu test AT03-1: kiểm tra KT-02 CMS thêm mẫu mới → app hiển thị ngay, không cần build lại container.",
        signs="S1. Tin nhắn 'lãi suất cao 18%/năm'\nS2. Đòi chuyển khoản trước để 'mở tài khoản VIP'",
        example_content="VD: 'Chị Lan nhé, quỹ Aura đầu tư BĐS cho chị 18%/năm, chuyển 20tr trước vào STK 00999 của em nha, sau 3 tháng nhận lãi 9tr.'",
        recommended_action="RA1. KHÔNG chuyển khoản\nRA2. Block số điện thoại / tài khoản mạng xã hội\nRA3. Báo cho người thân và gửi tin về 5657",
        is_active=True,
    )
    _db1.add(new_p)
    _db1.flush()
    NEW_PATTERN_ID = str(new_p.id)
    _db1.commit()  # commit → SQLAlchemy event listener after_insert auto invalidate cache T-028
except Exception as e:
    _db1.rollback()
    case("Insert mẫu mới [T029A1-NEW] via ORM + commit thành công",
         False, f"exception={e}")
finally:
    _db1.close()

case("Insert mẫu mới AT-03-1 OK → event listener đã trigger (cache invalidated)",
     NEW_PATTERN_ID is not None, f"id={NEW_PATTERN_ID}")

if NEW_PATTERN_ID is not None:
    r = _ep05({"q": "T029A1 NEW lừa đảo"})
    case("EP-05 status = 200", r.status_code == 200, f"actual={r.status_code} text={r.text[:120]}")
    if r.status_code == 200:
        try:
            b = r.json()
            titles = [i.get("title", "") for i in (b.get("items") or [])]
            found = any("T029A1-NEW" in t for t in titles)
            case("EP-05 thấy ngay mẫu [T029A1-NEW] vừa insert (KHÔNG rebuild app, KT-02)",
                 found, f"actual titles={titles[:8]} ...(total={len(titles)})")
        except Exception as e:
            case("EP-05 parse JSON OK", False, f"err={e}")


# ================================================================
# AT-03-2: EP-10 trình đọc màn hình đúng thứ tự
#          Title → Signs → Example_content → Recommended_action
# ================================================================
print("\n=== AT-03-2 [T-029.2] EP-10 field order Trình đọc màn hình (Title→Signs→VD→Khuyến nghị) ===")
ACTIVE_DETAIL_ID = None
_db2 = SessionLocal()
try:
    _cleanup_tagged(_db2, "T029A2")
    a2 = ScamPattern(
        title="[T029A2] Mẫu test thứ tự field AT-03-2",
        category="Đòi nợ",
        description="Mẫu test AT03-2: EP-10 JSON keys theo đúng trình đọc màn hình.",
        image_url="https://example.com/t029a2.png",
        signs="S1. Đe doạ đập nhà\nS2. Gọi 'đồng đội' đến địa chỉ nhà bạn trong 24h",
        example_content="VD: 'Anh Hải đây, nợ 50tr chưa trả, 24h tới mang đồng đội 11 người đến nhà chơi đấy.'",
        recommended_action="RA1. Gọi 113 nếu có đe doạ\nRA2. Chụp màn hình tin nhắn / cuộc gọi\nRA3. Không trả lời đe doạ",
        is_active=True,
    )
    _db2.add(a2)
    _db2.flush()
    ACTIVE_DETAIL_ID = str(a2.id)
    _db2.commit()
except Exception as e:
    _db2.rollback()
    case("Insert mẫu test AT-03-2 thành công", False, f"exception={e}")
finally:
    _db2.close()

case("Insert mẫu T029A2 OK", ACTIVE_DETAIL_ID is not None, f"id={ACTIVE_DETAIL_ID}")

if ACTIVE_DETAIL_ID is not None:
    rd = _ep10(ACTIVE_DETAIL_ID)
    case("EP-10 AT-03-2 status = 200", rd.status_code == 200,
         f"actual={rd.status_code} text={rd.text[:120]}")
    if rd.status_code == 200:
        try:
            bd = rd.json()
            keys_order = list(bd.keys())
            # Kiểm tra idx của 4 khóa then chốt theo trình đọc màn hình:
            #   title (Tiêu đề) → signs (Dấu hiệu) → example_content (Ví dụ) →
            #   recommended_action (Khuyến nghị)
            def _idx(k):
                return keys_order.index(k) if k in keys_order else -1

            i_title = _idx("title")
            i_signs = _idx("signs")
            i_ex = _idx("example_content")
            i_rec = _idx("recommended_action")

            case("EP-10 có đủ 4 field: title / signs / example_content / recommended_action",
                 all(i >= 0 for i in (i_title, i_signs, i_ex, i_rec)),
                 f"actual keys={keys_order}")

            order_ok = (i_title >= 0 and i_signs >= 0 and i_ex >= 0 and i_rec >= 0
                        and i_title < i_signs < i_ex < i_rec)
            case("Thứ tự đúng theo trình đọc màn hình: Tiêu đề → Dấu hiệu → Ví dụ → Khuyến nghị",
                 order_ok,
                 f"idx: title={i_title}, signs={i_signs}, example_content={i_ex}, recommended_action={i_rec} | keys={keys_order}")
        except Exception as e:
            case("EP-10 parse JSON OK", False, f"err={e}")


# ================================================================
# AT-03-3: Search "ngan hang" không dấu → bài chủ đề mạo danh ngân hàng
# ================================================================
print("\n=== AT-03-3 [T-029.3] Search 'ngan hang' (không dấu) → Mạo danh ngân hàng (có dấu) ===")
BANK_PATTERN_ID = None
NOTBANK_PATTERN_ID = None
_db3 = SessionLocal()
try:
    _cleanup_tagged(_db3, "T029A3")
    # A = mạo danh NGÂN HÀNG — 4 token độc nhất T029A3 / xyz9 / ngan / hang
    bp = ScamPattern(
        title="[T029A3-BANK] XYZ9 Mạo danh Ngân hàng TCB (T029A3) thu hồi nợ giả",
        category="Mạo danh",
        description="Mẫu test AT03-3: chủ đề NGÂN HÀNG.",
        signs="S1. Gọi tự giới thiệu là cán bộ Ngân hàng TCB\nS2. Nói nợ thẻ tín dụng 3 tháng chưa trả, đe doạ khóa tài khoản",
        example_content="VD: 'Chị Hải đây là cán bộ TCB, thẻ tín dụng Visa của chị nợ 3 tháng.'",
        recommended_action="RA1. Gọi hotline chính thức của ngân hàng để xác nhận\nRA2. Không nhấn link / call số của người gọi\nRA3. Gửi tin về 5657",
        is_active=True,
    )
    # B = lừa đảo HÀNG (chỉ "hàng" đơn lẻ, KO có "ngân" KO có "T029A3" trong toàn bộ 3 field)
    nb = ScamPattern(
        title="[T029A3-NOTBANK] XYZ8 Lừa đảo HÀNG giảm giá Shopee (T029B3) đơn hàng mất cước",
        category="Lừa đảo mua bán",
        description="Mẫu test AT03-3 neg-case: chủ đề HÀNG, không liên quan ngân hàng.",
        signs="S1. SMS 'Đơn hàng Shopee của chị bị mất cước'\nS2. Link giả mạo Shopee",
        example_content="VD: 'Shopee thông báo đơn #789 của chị bị mất cước 20k.'",
        recommended_action="RA1. Không click link lạ\nRA2. Mở app Shopee chính thức để kiểm tra\nRA3. Block số gửi SMS",
        is_active=True,
    )
    _db3.add_all([bp, nb])
    _db3.flush()
    BANK_PATTERN_ID = str(bp.id)
    NOTBANK_PATTERN_ID = str(nb.id)
    _db3.commit()
except Exception as e:
    _db3.rollback()
    case("Insert 2 mẫu AT-03-3 (BANK + NOTBANK) thành công", False, f"exception={e}")
finally:
    _db3.close()

case("Insert 2 mẫu AT-03-3 OK", BANK_PATTERN_ID is not None and NOTBANK_PATTERN_ID is not None,
     f"BANK_ID={BANK_PATTERN_ID}  NOTBANK_ID={NOTBANK_PATTERN_ID}")

if BANK_PATTERN_ID is not None:
    # Bảo đảm không đọc cache cũ thiếu row vừa insert (dù event listener đã trigger
    # khi commit, làm explicit cho chắc)
    cache_invalidate_all_pattern()
    # 4 token AND: T029A3 / XYZ9 / ngan / hang
    # BANK title có T029A3 + XYZ9 + ngan (Ngân) + hang (hàng) → MATCH 4/4
    # NOTBANK title có T029B3 + XYZ8 + hang → thiếu T029A3, thiếu XYZ9, thiếu ngan → FAIL
    # Seed cũ không có T029A3 → FAIL
    rb = _ep05({"q": "T029A3 XYZ9 ngan hang"})
    case("Search T029A3 XYZ9 ngan hang (4 token AND) EP-05 status = 200",
         rb.status_code == 200, f"actual={rb.status_code} text={rb.text[:120]}")
    if rb.status_code == 200:
        try:
            bb = rb.json()
            items_b = list(bb.get("items") or [])
            ids_b = [str(i.get("id", "")) for i in items_b]
            has_bank_id = BANK_PATTERN_ID in ids_b
            has_notbank_id = NOTBANK_PATTERN_ID in ids_b
            case("Match đúng 1 mẫu Mạo danh Ngân hàng (id trùng BANK_PATTERN_ID)",
                 has_bank_id,
                 f"expected id={BANK_PATTERN_ID} present={has_bank_id} actual ids={ids_b}")
            case("KHÔNG lẫn mẫu Lừa đảo HÀNG Shopee (thiếu T029A3 + XYZ9 + ngan)",
                 not has_notbank_id,
                 f"expected notbank id={NOTBANK_PATTERN_ID} present={has_notbank_id} actual ids={ids_b}")
        except Exception as e:
            case("EP-05 parse JSON OK", False, f"err={e}")


# ================================================================
# AT-03-4: Đặt 1 bài is_active=false → EP-10 gọi id đó = 404 (ẩn dữ liệu)
# ================================================================
print("\n=== AT-03-4 [T-029.4] Nháp is_active=false → EP-10 = 404 cấm hiển thị ===")
DRAFT4_ID = None
_db4 = SessionLocal()
try:
    _cleanup_tagged(_db4, "T029A4")
    d = ScamPattern(
        title="[T029A4-DRAFT] Mẫu nháp test AT-03-4 (thiếu khối, không được public)",
        category="Mạo danh",
        description="AT-03-4: is_active=false thiếu 3 khối → EP-10 phải trả 404, ẩn hoàn toàn.",
        signs=None,
        example_content=None,
        recommended_action=None,
        is_active=False,
    )
    _db4.add(d)
    _db4.flush()
    DRAFT4_ID = str(d.id)
    _db4.commit()
except Exception as e:
    _db4.rollback()
    case("Insert nháp AT-03-4 (is_active=false) thành công", False, f"exception={e}")
finally:
    _db4.close()

case("Insert nháp T029A4-DRAFT id OK", DRAFT4_ID is not None, f"id={DRAFT4_ID}")
if DRAFT4_ID is not None:
    rd4 = _ep10(DRAFT4_ID)
    case("EP-10 call draft ID → HTTP 404 (cấm hiển thị dữ liệu ẩn)",
         rd4.status_code == 404, f"actual={rd4.status_code} text={rd4.text[:150]}")
    if rd4.status_code == 404:
        try:
            bd4 = rd4.json()
            code4 = ""
            if isinstance(bd4, dict) and isinstance(bd4.get("code"), str):
                code4 = bd4["code"]
            case("code = SCAM_PATTERN_NOT_FOUND (L3.4 root {code,message,extra})",
                 code4 == "SCAM_PATTERN_NOT_FOUND",
                 f"actual code={code4!r} body={bd4}")
        except Exception as e:
            case("EP-10 parse JSON 404 OK", False, f"err={e}")


# ================================================================
# AT-03-5: XÓA SẠCH toàn bộ scam_pattern → gọi EP-05 = 200 + items=[]
#          SAU KHI TEST xong, restore toàn bộ data seed cũ về DB (transactional-safe)
# ================================================================
print("\n=== AT-03-5 [T-029.5] XÓA SẠCH scam_pattern → EP-05 200 items=[] → restore lại seed ===")

# STEP 1: Backup toàn bộ ScamPattern vào list
_db5_backup = SessionLocal()
BACKUP_ROWS: List[Dict[str, Any]] = []
try:
    all_rows = _db5_backup.query(ScamPattern).order_by(ScamPattern.created_at.asc()).all()
    for r in all_rows:
        BACKUP_ROWS.append({
            "id": r.id,
            "title": r.title,
            "category": r.category,
            "image_url": r.image_url,
            "description": r.description,
            "signs": r.signs,
            "example_content": r.example_content,
            "recommended_action": r.recommended_action,
            "is_active": bool(r.is_active),
            "created_at": copy.deepcopy(r.created_at),
            "updated_at": copy.deepcopy(r.updated_at),
        })
    case(f"[PREP] Backed up {len(BACKUP_ROWS)} rows khỏi scam_pattern trước khi xóa",
         len(BACKUP_ROWS) >= 0, f"backup_count={len(BACKUP_ROWS)}")
finally:
    _db5_backup.close()

# STEP 2: DELETE sạch scam_pattern (raw SQL → tránh ORM cascading issue)
_db5_del = SessionLocal()
ROWS_BEFORE_DEL = -1
ROWS_AFTER_DEL = -1
try:
    ROWS_BEFORE_DEL = _db5_del.query(ScamPattern).count()
    _db5_del.execute(__import__("sqlalchemy").text("DELETE FROM scam_pattern"))
    _db5_del.commit()
    ROWS_AFTER_DEL = _db5_del.query(ScamPattern).count()
    case(f"DELETE sạch scam_pattern: trước={ROWS_BEFORE_DEL} → sau={ROWS_AFTER_DEL}",
         ROWS_AFTER_DEL == 0,
         f"rows_after={ROWS_AFTER_DEL} (expected 0)")
except Exception as e:
    _db5_del.rollback()
    ROWS_AFTER_DEL = -1
    case(f"[FATAL] DELETE scam_pattern lỗi: {e}", False, f"exception={type(e).__name__}: {e}")
finally:
    _db5_del.close()

# STEP 3: Call EP-05 với DB RỖNG = kiểm tra empty-safe
if ROWS_AFTER_DEL == 0:
    cache_invalidate_all_pattern()  # flush cache cũ có dữ liệu
    re = _ep05({})  # không filter q / category / limit (lấy default limit=20)
    case("AT-03-5a EP-05 DB rỗng → HTTP 200 (không 500, không crash)",
         re.status_code == 200, f"actual={re.status_code} text={re.text[:200]}")
    if re.status_code == 200:
        try:
            be = re.json()
            items_e = be.get("items")
            next_cursor_e = be.get("next_cursor")
            case("AT-03-5b items = [] (rỗng, để giao diện hiện 'Hiện chưa có cảnh báo mới')",
                 isinstance(items_e, list) and len(items_e) == 0,
                 f"actual items type={type(items_e).__name__} len={len(items_e) if hasattr(items_e, '__len__') else 'N/A'} val={items_e!r}")
            case("AT-03-5c next_cursor = None (hết trang)",
                 next_cursor_e is None, f"actual next_cursor={next_cursor_e!r}")
        except Exception as e:
            case("AT-03-5 parse JSON OK", False, f"err={e}")

# STEP 4: RESTORE toàn bộ rows backup về scam_pattern (critical!)
RESTORE_OK = False
_db5_restore = SessionLocal()
try:
    # Nếu có rows còn sót lại do lỗi delete trước đó → xóa sạch lại để insert không duplicate
    _db5_restore.execute(__import__("sqlalchemy").text("DELETE FROM scam_pattern"))
    restored = 0
    for row_dict in BACKUP_ROWS:
        obj = ScamPattern(
            id=row_dict["id"],
            title=row_dict["title"],
            category=row_dict["category"],
            image_url=row_dict.get("image_url"),
            description=row_dict["description"],
            signs=row_dict.get("signs"),
            example_content=row_dict.get("example_content"),
            recommended_action=row_dict.get("recommended_action"),
            is_active=row_dict.get("is_active", False),
            created_at=row_dict.get("created_at"),
            updated_at=row_dict.get("updated_at"),
        )
        _db5_restore.add(obj)
        restored += 1
    _db5_restore.commit()
    cache_invalidate_all_pattern()
    RESTORE_OK = True
    case(f"[CRITICAL] RESTORED {restored}/{len(BACKUP_ROWS)} rows scam_pattern về DB (seed cũ an toàn)",
         restored == len(BACKUP_ROWS),
         f"restored={restored} expected={len(BACKUP_ROWS)}")
except Exception as e:
    _db5_restore.rollback()
    RESTORE_OK = False
    case(f"[CRITICAL] RESTORE scam_pattern FAILED: {e}",
         False, f"exception={type(e).__name__}: {e}")
finally:
    _db5_restore.close()

# STEP 5: Verify restore thành công (sanity check)
_db5_verify = SessionLocal()
try:
    after_count = _db5_verify.query(ScamPattern).count()
    case(f"[VERIFY] Sau restore DB có {after_count} rows (expected {len(BACKUP_ROWS)})",
         after_count == len(BACKUP_ROWS),
         f"after_count={after_count} backup_count={len(BACKUP_ROWS)}")
    # Gọi 1 lần EP-05 nữa để confirm service hoạt động bình thường sau restore
    if RESTORE_OK and after_count > 0:
        rv = _ep05({"limit": 5})
        case("[VERIFY] Sau restore EP-05 status=200 items>0 (service hoạt động)",
             rv.status_code == 200 and len((rv.json().get("items") or [])) >= 1,
             f"actual status={rv.status_code} items_len={len((rv.json().get('items') or []))}")
finally:
    _db5_verify.close()


# ================================================================
# Cleanup các hàng test insert trong TC1..TC4 (backup/restore trong TC5
# giữ nguyên seed cũ nên không cần cleanup đặc biệt)
# ================================================================
_db9 = SessionLocal()
try:
    for tag in ("T029A1", "T029A2", "T029A3", "T029A4"):
        _cleanup_tagged(_db9, tag)
    cache_invalidate_all_pattern()
    print("\n[CLEANUP] Đã xóa toàn bộ test rows AT-03 tags [T029A1..A4] và flush cache.")
except Exception as e:
    print(f"[CLEANUP][WARNING] Xóa test rows lỗi: {e}")
finally:
    _db9.close()


# ================================================================
# Tổng kết
# ================================================================
print("\n" + "=" * 80)
print(f"KET QUA:  PASS = {PASS_CNT}   |   FAIL = {FAIL_CNT}")
if FAIL_LOG:
    print("\n[DANH SACH TEST FAIL]:")
    for m in FAIL_LOG:
        print("   ", m)
    if not RESTORE_OK:
        print("\n!!!! [CRITICAL] AT-03-5 RESTORE FAILED — kiểm tra DB scam_pattern có đầy đủ seed cũ không !!!!")
    print("\n=> CHƯA PASS T-029, sửa các mục trên rồi chạy lại.")
    sys.exit(1)
else:
    print("✅ T-029 AT-03: Nghiệm thu 5/5 kịch bản PASSED! (AT03-1..5)")
    if RESTORE_OK:
        print("   → Data scam_pattern seed cũ đã RESTORED an toàn (AT-03-5 backup → delete-test → restore.)")
    sys.exit(0)
