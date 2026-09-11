"""
T-025 — FR-03 BR-03-2 Test: ScamPattern is_active=true BAT BUOC
phai co day du 3 khoi signs, example_content, recommended_action.
Khong duoc active neu thieu 1 khoi nao (null, empty, hoac chi khoang trang).

Chay:
  python test_t025_br032_scam_pattern_validate.py
  Hoac trong Docker:
  docker compose exec web python /app/test_t025_br032_scam_pattern_validate.py
"""
import sys
import os
import uuid
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.db_models import ScamPattern


# ---------- Helpers ----------
def _cleanup(db, *patterns_to_delete):
    for p in patterns_to_delete:
        if p and getattr(p, "id", None):
            try:
                db.query(ScamPattern).filter(ScamPattern.id == p.id).delete()
                db.commit()
            except Exception:
                db.rollback()


def make_pattern_base():
    """Tao pattern co day du 3 khối (template cho cac test pass)."""
    return {
        "title": f"T-025 Sample {uuid.uuid4().hex[:6]}",
        "category": "LUADAO_TEST",
        "description": "Mẫu test kiểm thử T-025 BR-03-2",
        "signs": "Dấu hiệu 1: Yêu cầu cấp tiền ngay lập tức\nDấu hiệu 2: Link rút gọn không rõ nguồn gốc",
        "example_content": "Nhanh gui 10tr vao STK 0912... de chung toi xac minh tai khoan! Link: bit.ly/abc123",
        "recommended_action": "Hãy xóa tin nhắn, chặn số và không bấm vào bất kỳ link nào. Chuyển tin nhắn scam về 5657.",
    }


# ---------- Test Cases ----------
passed = 0
failed = 0
errors = []


def run_case(name: str, fn: Callable[[], None]):
    global passed, failed
    db = SessionLocal()
    created_objects = []
    try:
        fn(db, created_objects)
        print(f"  [PASS] {name}")
        passed += 1
    except AssertionError as ae:
        print(f"  [FAIL] {name}: {ae}")
        failed += 1
        errors.append((name, str(ae)))
    except Exception as ex:
        print(f"  [FAIL] {name}: unhandled {type(ex).__name__}: {ex}")
        failed += 1
        errors.append((name, f"{type(ex).__name__}: {ex}"))
    finally:
        _cleanup(db, *created_objects)
        db.close()


# TC0 — Du 3 khoi → set is_active=true OK
def tc0_ok_full_blocks(db, created):
    data = make_pattern_base()
    p = ScamPattern(**data, is_active=True)
    db.add(p)
    db.flush()
    created.append(p)
    assert p.is_active is True, "Tao active pattern voi du 3 khoi phai thanh cong"
    db.commit()
    fetched = db.query(ScamPattern).filter(ScamPattern.id == p.id).first()
    assert fetched is not None and fetched.is_active is True, "Sau commit van phai active=true"


# TC1 — signs rỗng → không thể active=true
def tc1_missing_signs(db, created):
    data = make_pattern_base()
    data["signs"] = ""
    raised = False
    try:
        p = ScamPattern(**data, is_active=True)
        db.add(p)
        db.commit()
        created.append(p)
    except (ValueError, IntegrityError):
        raised = True
        db.rollback()
    if not raised:
        # Thu flush/commit khac cach
        try:
            db.rollback()
            data2 = make_pattern_base()
            data2["signs"] = ""
            p2 = ScamPattern(**data2, is_active=False)
            db.add(p2)
            db.flush()
            created.append(p2)
            p2.is_active = True
            try:
                db.commit()
            except (ValueError, IntegrityError):
                raised = True
                db.rollback()
        except (ValueError, IntegrityError):
            raised = True
            db.rollback()
    assert raised is True, "Phai bao loi khi set active=true ma signs rong"


# TC2 — example_content rỗng → không thể active=true
def tc2_missing_example(db, created):
    data = make_pattern_base()
    data["example_content"] = ""
    raised = False
    try:
        p = ScamPattern(**data, is_active=True)
        db.add(p)
        db.commit()
        created.append(p)
    except (ValueError, IntegrityError):
        raised = True
        db.rollback()
    if not raised:
        db.rollback()
        try:
            data2 = make_pattern_base()
            data2["example_content"] = ""
            p2 = ScamPattern(**data2, is_active=False)
            db.add(p2)
            db.flush()
            created.append(p2)
            p2.is_active = True
            db.commit()
        except (ValueError, IntegrityError):
            raised = True
            db.rollback()
    assert raised is True, "Phai bao loi khi set active=true ma example_content rong"


# TC3 — recommended_action rỗng → không thể active=true
def tc3_missing_action(db, created):
    data = make_pattern_base()
    data["recommended_action"] = ""
    raised = False
    try:
        p = ScamPattern(**data, is_active=True)
        db.add(p)
        db.commit()
        created.append(p)
    except (ValueError, IntegrityError):
        raised = True
        db.rollback()
    if not raised:
        db.rollback()
        try:
            data2 = make_pattern_base()
            data2["recommended_action"] = ""
            p2 = ScamPattern(**data2, is_active=False)
            db.add(p2)
            db.flush()
            created.append(p2)
            p2.is_active = True
            db.commit()
        except (ValueError, IntegrityError):
            raised = True
            db.rollback()
    assert raised is True, "Phai bao loi khi set active=true ma recommended_action rong"


# TC4 — 3 field chỉ khoảng trắng → không thể active=true
def tc4_whitespace_only(db, created):
    data = make_pattern_base()
    data["signs"] = "   \n\t   "
    data["example_content"] = "   "
    data["recommended_action"] = "      \r\n   "
    raised = False
    try:
        p = ScamPattern(**data, is_active=True)
        db.add(p)
        db.commit()
        created.append(p)
    except (ValueError, IntegrityError):
        raised = True
        db.rollback()
    if not raised:
        db.rollback()
        try:
            data2 = make_pattern_base()
            data2["signs"] = "  "
            data2["example_content"] = " "
            data2["recommended_action"] = "  \t"
            p2 = ScamPattern(**data2, is_active=False)
            db.add(p2)
            db.flush()
            created.append(p2)
            p2.is_active = True
            db.commit()
        except (ValueError, IntegrityError):
            raised = True
            db.rollback()
    assert raised is True, "Phai bao loi khi 3 khoi chi co khoang trang ma set active=true"


# TC5 — thiếu 3 khối nhưng is_active=false → vẫn OK (lưu nháp được)
def tc5_inactive_is_allowed_even_empty(db, created):
    data = make_pattern_base()
    data["signs"] = ""
    data["example_content"] = ""
    data["recommended_action"] = ""
    p = ScamPattern(**data, is_active=False)
    db.add(p)
    db.flush()
    created.append(p)
    assert p.is_active is False, "Pattern nháp phai duoc luu (is_active=false)"
    db.commit()
    fetched = db.query(ScamPattern).filter(ScamPattern.id == p.id).first()
    assert fetched is not None, "Pattern nháp phai ton tai sau commit"
    assert fetched.is_active is False, "Pattern nháp van phai active=false"


# TC6 — Update pattern đang active=true: set example_content='' sẽ bị lỗi
def tc6_update_active_to_empty_block(db, created):
    data = make_pattern_base()
    p = ScamPattern(**data, is_active=True)
    db.add(p)
    db.flush()
    created.append(p)
    db.commit()
    raised = False
    try:
        p.example_content = ""
        db.flush()
        db.commit()
    except (ValueError, IntegrityError):
        raised = True
        db.rollback()
    assert raised is True, "Khong duoc cho phep update example_content='' tren pattern dang active=true"
    fetched = db.query(ScamPattern).filter(ScamPattern.id == p.id).first()
    assert fetched.example_content == make_pattern_base()["example_content"], \
        "Sau khi rollback, example_content phai van giu gia tri ban dau (khong bi update rong)"


# TC7 — static method ScamPattern.validate_active_requirements goi truc tiep
def tc7_static_validate_method(db, created):
    # Du 3 khoi → khong raise gi
    ScamPattern.validate_active_requirements(
        is_active=True,
        signs="a",
        example_content="b",
        recommended_action="c",
    )
    # Thiếu signs → ValueError
    v_raised = False
    try:
        ScamPattern.validate_active_requirements(
            is_active=True,
            signs="   \t",
            example_content="b",
            recommended_action="c",
        )
    except ValueError as ve:
        v_raised = True
        msg = str(ve)
        assert "signs (dấu hiệu)" in msg, "Thông báo lỗi phai chi rõ là thiếu signs"
    assert v_raised, "Static validate phai raise ValueError khi signs chi khoang trang va is_active=true"
    # active=false, moi thu rong → OK khong raise
    ScamPattern.validate_active_requirements(
        is_active=False,
        signs="",
        example_content="",
        recommended_action="",
    )


# ---------- Runner ----------
if __name__ == "__main__":
    print("=" * 78)
    print("T-025  FR-03 BR-03-2 TEST  |  ScamPattern is_active requires 3 blocks")
    print("=" * 78)
    print()

    run_case("TC0 — Đủ 3 khối → set is_active=true OK", tc0_ok_full_blocks)
    run_case("TC1 — signs rỗng → cấm active=true", tc1_missing_signs)
    run_case("TC2 — example_content rỗng → cấm active=true", tc2_missing_example)
    run_case("TC3 — recommended_action rỗng → cấm active=true", tc3_missing_action)
    run_case("TC4 — 3 khối chỉ khoảng trắng → cấm active=true", tc4_whitespace_only)
    run_case("TC5 — Thiếu 3 khối nhưng is_active=false (nháp) → vẫn OK", tc5_inactive_is_allowed_even_empty)
    run_case("TC6 — Pattern active=true, set example_content='' → rollback OK", tc6_update_active_to_empty_block)
    run_case("TC7 — Static method validate_active_requirements trả đúng message", tc7_static_validate_method)

    print()
    print("=" * 78)
    print(f"KET QUA:  PASS = {passed}   |   FAIL = {failed}")
    print("=" * 78)
    if failed == 0:
        print("✅ T-025: Tat ca test case PASSED!")
        sys.exit(0)
    else:
        print("❌ Co test FAIL:")
        for (n, m) in errors:
            print(f"  - {n}: {m}")
        sys.exit(1)
