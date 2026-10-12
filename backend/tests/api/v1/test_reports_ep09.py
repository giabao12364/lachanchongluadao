# tests/api/v1/test_reports_ep09.py
"""
T-035 — Nghiệm thu EP-09 GET /api/v1/reports (Báo cáo của tôi)

Test qua HTTP endpoint thật (TestClient), giống test_phones_at02.py (T-024):
đi qua middleware -> router -> service -> DB thật, không gọi thẳng hàm
Python.

NGOẠI LỆ so với T-024: get_current_user_id() vẫn là stub (FR-05/T-040
chưa xong) -> không có cách nào lấy Bearer token thật để đăng nhập qua
HTTP. Test này monkeypatch riêng app.api.v1.reports.get_current_user_id
để giả lập "đã đăng nhập", còn middleware/router/DB vẫn chạy thật qua
TestClient. KHI T-040 XONG: xóa toàn bộ monkeypatch trong file này, thay
bằng đăng ký + verify OTP thật lấy access_token, gọi qua header
Authorization như luồng auth thật.

────────────────────────────────────────────────────────────────────
CÁCH CHẠY
────────────────────────────────────────────────────────────────────
    docker compose up -d
    docker compose exec web pytest tests/api/v1/test_reports_ep09.py -v -s

────────────────────────────────────────────────────────────────────
LƯU Ý VỀ DỌN DỮ LIỆU
────────────────────────────────────────────────────────────────────
EP-06 (POST /reports, dùng để tạo dữ liệu test) tự gọi db.commit() bên
trong request, giống EP-04 -> mỗi test tạo AppUser + ScamReport riêng
bằng uuid4, fixture make_user tự xóa report + user liên quan sau khi
test xong (dù pass hay fail), không để lại rác trong DB dev.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.db_models import AppUser, ScamReport

client = TestClient(app)


@pytest.fixture()
def make_user(db_session: Session):
    """
    Factory tạo AppUser thật (commit ngay để session của TestClient thấy
    được). Tự dọn user + mọi ScamReport liên quan sau khi test xong.
    """
    created_ids = []

    def _make(display_name: str = "Test User") -> AppUser:
        user = AppUser(
            phone_number=f"+849{uuid.uuid4().hex[:8]}",
            display_name=display_name,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        created_ids.append(user.id)
        return user

    yield _make

    for uid in created_ids:
        db_session.query(ScamReport).filter(ScamReport.user_id == uid).delete()
    if created_ids:
        db_session.query(AppUser).filter(AppUser.id.in_(created_ids)).delete(
            synchronize_session=False
        )
    db_session.commit()


def _login_as(monkeypatch, user: AppUser) -> None:
    """Monkeypatch điểm DUY NHẤT chưa có thật (JWT decode) -> phần còn lại
    (middleware, router, DB) vẫn chạy thật qua TestClient."""
    monkeypatch.setattr(
        "app.api.v1.reports.get_current_user_id",
        lambda request: str(user.id),
    )


class TestAT035_1_RequiresLogin:
    """Chưa đăng nhập gọi EP-09 -> 401 UNAUTHORIZED (không cần monkeypatch,
    hành vi thật của get_current_user_id() stub hiện tại)."""

    def test_no_auth_header_returns_401(self):
        resp = client.get("/api/v1/reports", headers={"X-Device-Uid": "test-device"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"


class TestAT035_2_Isolation:
    """AT-04-7: chỉ thấy report của chính mình, không thấy của người khác."""

    def test_user_sees_only_own_reports(self, make_user, monkeypatch):
        user_a = make_user("User A")
        user_b = make_user("User B")

        _login_as(monkeypatch, user_a)
        resp = client.post(
            "/api/v1/reports",
            json={"entity_type": "PHONE", "normalized_value": "0900000101"},
            headers={"X-Device-Uid": "test-device"},
        )
        assert resp.status_code == 200, resp.text

        _login_as(monkeypatch, user_b)
        resp = client.post(
            "/api/v1/reports",
            json={"entity_type": "PHONE", "normalized_value": "0900000102"},
            headers={"X-Device-Uid": "test-device"},
        )
        assert resp.status_code == 200, resp.text

        _login_as(monkeypatch, user_a)
        resp = client.get("/api/v1/reports", headers={"X-Device-Uid": "test-device"})
        assert resp.status_code == 200

        values = [item["normalized_value"] for item in resp.json()["items"]]
        assert values == ["+84900000101"]  # KHÔNG thấy report của user_b


class TestAT035_3_NoUserIdLeak:
    """FR-04.8: response không lộ user_id, kể cả của chính người gọi."""

    def test_response_does_not_contain_user_id(self, make_user, monkeypatch):
        user = make_user()
        _login_as(monkeypatch, user)

        client.post(
            "/api/v1/reports",
            json={"entity_type": "PHONE", "normalized_value": "0900000201"},
            headers={"X-Device-Uid": "test-device"},
        )
        resp = client.get("/api/v1/reports", headers={"X-Device-Uid": "test-device"})

        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "user_id" not in item


class TestAT035_4_Pagination:
    """Phân trang cursor: limit=2 với 3 report -> next_cursor khác None,
    trang 2 còn đúng 1 bản ghi, không trùng lặp giữa 2 trang."""

    def test_next_cursor_and_no_duplicate_across_pages(self, make_user, monkeypatch):
        user = make_user()
        _login_as(monkeypatch, user)

        for i in range(3):
            resp = client.post(
                "/api/v1/reports",
                json={"entity_type": "PHONE", "normalized_value": f"090000030{i}"},
                headers={"X-Device-Uid": "test-device"},
            )
            assert resp.status_code == 200, resp.text

        page1 = client.get(
            "/api/v1/reports", params={"limit": 2}, headers={"X-Device-Uid": "test-device"}
        ).json()
        assert len(page1["items"]) == 2
        assert page1["next_cursor"] is not None

        page2 = client.get(
            "/api/v1/reports",
            params={"limit": 2, "cursor": page1["next_cursor"]},
            headers={"X-Device-Uid": "test-device"},
        ).json()
        assert len(page2["items"]) == 1
        assert page2["next_cursor"] is None

        ids_page1 = {item["report_id"] for item in page1["items"]}
        ids_page2 = {item["report_id"] for item in page2["items"]}
        assert ids_page1.isdisjoint(ids_page2)


class TestAT035_5_InvalidCursor:
    """EX-06-4: cursor sai định dạng -> tự tải lại từ trang đầu, KHÔNG lỗi 500."""

    def test_garbage_cursor_falls_back_to_first_page(self, make_user, monkeypatch):
        user = make_user()
        _login_as(monkeypatch, user)

        client.post(
            "/api/v1/reports",
            json={"entity_type": "PHONE", "normalized_value": "0900000401"},
            headers={"X-Device-Uid": "test-device"},
        )

        resp = client.get(
            "/api/v1/reports",
            params={"cursor": "___khong-phai-base64-hop-le___"},
            headers={"X-Device-Uid": "test-device"},
        )

        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1