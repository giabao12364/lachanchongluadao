# tests/api/v1/test_reports_fr04_acceptance.py
"""
T-036 — Nghiệm thu FR-04 (AT-04-1 đến AT-04-8, spec mục 04.9)

Test qua HTTP endpoint thật (TestClient), khớp convention test_phones_at02.py
(T-024): đi qua middleware -> router -> service -> DB thật.

NGOẠI LỆ: get_current_user_id() vẫn là stub (FR-05/T-040 chưa xong) -> mọi
"đăng nhập" trong file này được giả lập bằng monkeypatch riêng
app.api.v1.reports.get_current_user_id (chỉ 1 điểm chưa có thật, còn lại
chạy thật qua HTTP). KHI T-040 XONG: xóa monkeypatch, dùng access_token
thật từ luồng OTP.

────────────────────────────────────────────────────────────────────
CÁCH CHẠY
────────────────────────────────────────────────────────────────────
    docker compose up -d
    docker compose exec web pytest tests/api/v1/test_reports_fr04_acceptance.py -v -s

────────────────────────────────────────────────────────────────────
LƯU Ý VỀ DỌN DỮ LIỆU
────────────────────────────────────────────────────────────────────
EP-06/EP-01 tự commit() thật -> mỗi test dùng entity/user riêng (uuid4),
fixture tự xóa report + blacklist_entity + user (và scan_request/result
nếu có, ở AT-04-8) sau khi test xong, dù pass hay fail.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.db_models import (
    AppUser,
    BlacklistEntity,
    EntityType,
    ScamReport,
    ScanRequest,
)

client = TestClient(app)


@pytest.fixture()
def make_user(db_session: Session):
    """Factory tạo AppUser thật (commit ngay). Tự dọn user + ScamReport
    liên quan sau khi test xong."""
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


@pytest.fixture()
def cleanup_blacklist(db_session: Session):
    """Dọn blacklist_entity tạo trong test theo (entity_type, normalized_value)
    đã đăng ký qua fixture này."""
    keys: list[tuple[EntityType, str]] = []

    def _register(entity_type: EntityType, normalized_value: str) -> None:
        keys.append((entity_type, normalized_value))

    yield _register

    for entity_type, value in keys:
        db_session.query(BlacklistEntity).filter(
            BlacklistEntity.entity_type == entity_type,
            BlacklistEntity.normalized_value == value,
        ).delete()
    db_session.commit()


@pytest.fixture()
def cleanup_device_scans(db_session: Session):
    """Dọn scan_request tạo trong test theo device_uid đã đăng ký."""
    from app.models.db_models import Device

    device_uids: list[str] = []

    def _register(device_uid: str) -> None:
        device_uids.append(device_uid)

    yield _register

    for uid in device_uids:
        device = db_session.query(Device).filter(Device.device_uid == uid).first()
        if device:
            db_session.query(ScanRequest).filter(ScanRequest.device_id == device.id).delete()
            db_session.delete(device)
    db_session.commit()


def _login_as(monkeypatch, user: AppUser) -> None:
    monkeypatch.setattr(
        "app.api.v1.reports.get_current_user_id",
        lambda request: str(user.id),
    )


def _report(monkeypatch, user, entity_type: str, value: str, device_uid: str = "test-device"):
    _login_as(monkeypatch, user)
    return client.post(
        "/api/v1/reports",
        json={"entity_type": entity_type, "normalized_value": value},
        headers={"X-Device-Uid": device_uid},
    )


def _get_blacklist_entity(db_session: Session, entity_type: EntityType, value: str):
    return (
        db_session.query(BlacklistEntity)
        .filter(
            BlacklistEntity.entity_type == entity_type,
            BlacklistEntity.normalized_value == value,
        )
        .first()
    )


class TestAT04_1_FirstReport:
    def test_new_phone_report_creates_pending_and_inactive_entity(
        self, make_user, monkeypatch, db_session, cleanup_blacklist
    ):
        user = make_user()
        phone = f"+8490{uuid.uuid4().hex[:7]}"
        cleanup_blacklist(EntityType.PHONE, phone)

        resp = _report(monkeypatch, user, "PHONE", phone)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "PENDING"

        entity = _get_blacklist_entity(db_session, EntityType.PHONE, phone)
        assert entity is not None
        assert entity.report_count == 1
        assert entity.is_active is False


class TestAT04_2_ThreeIndependentReportsAutoActive:
    def test_third_independent_report_activates_entity(
        self, make_user, monkeypatch, db_session, cleanup_blacklist
    ):
        domain = f"scam-{uuid.uuid4().hex[:8]}.top"
        cleanup_blacklist(EntityType.DOMAIN, domain)

        for _ in range(3):
            user = make_user()
            resp = _report(monkeypatch, user, "DOMAIN", domain)
            assert resp.status_code == 200, resp.text

        entity = _get_blacklist_entity(db_session, EntityType.DOMAIN, domain)
        assert entity.report_count == 3
        assert entity.is_active is True
        assert entity.confidence == 70


class TestAT04_3_DuplicateBySameUser:
    def test_second_report_same_entity_does_not_increment(
        self, make_user, monkeypatch, db_session, cleanup_blacklist
    ):
        user = make_user()
        phone = f"+8491{uuid.uuid4().hex[:7]}"
        cleanup_blacklist(EntityType.PHONE, phone)

        first = _report(monkeypatch, user, "PHONE", phone)
        assert first.status_code == 200

        second = _report(monkeypatch, user, "PHONE", phone)
        assert second.status_code == 200
        assert "trước đó" in second.json()["message"]

        entity = _get_blacklist_entity(db_session, EntityType.PHONE, phone)
        assert entity.report_count == 1  # không tăng lần 2


class TestAT04_4_RequiresLogin:
    def test_no_auth_returns_401(self):
        resp = client.post(
            "/api/v1/reports",
            json={"entity_type": "PHONE", "normalized_value": "0900000000"},
            headers={"X-Device-Uid": "test-device"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"


class TestAT04_5_RateLimit:
    def test_sixth_report_in_hour_returns_429(
        self, make_user, monkeypatch, db_session, cleanup_blacklist
    ):
        user = make_user()
        phones = [f"+8492{uuid.uuid4().hex[:7]}" for _ in range(6)]
        for p in phones:
            cleanup_blacklist(EntityType.PHONE, p)

        statuses = []
        for p in phones:
            resp = _report(monkeypatch, user, "PHONE", p)
            statuses.append(resp.status_code)

        assert statuses[:5] == [200] * 5
        assert statuses[5] == 429


class TestAT04_6_PhoneFormatsNormalize:
    def test_three_formats_same_phone_by_three_users_merge_to_one_e164(
        self, make_user, monkeypatch, db_session, cleanup_blacklist
    ):
        raw_digits = f"90{uuid.uuid4().hex[:7]}"[:9]  # 9 chữ số sau đầu số
        formats = [f"0{raw_digits}", f"+84{raw_digits}", f"84{raw_digits}"]
        e164 = f"+84{raw_digits}"
        cleanup_blacklist(EntityType.PHONE, e164)

        for fmt in formats:
            user = make_user()
            resp = _report(monkeypatch, user, "PHONE", fmt)
            assert resp.status_code == 200, resp.text

        entity = _get_blacklist_entity(db_session, EntityType.PHONE, e164)
        assert entity is not None, "3 định dạng phải gộp về đúng 1 dòng E.164"
        assert entity.report_count == 3


class TestAT04_7_MyReports:
    def test_my_reports_only_shows_own(self, make_user, monkeypatch):
        user_a = make_user("A")
        user_b = make_user("B")

        _report(monkeypatch, user_a, "PHONE", f"+8493{uuid.uuid4().hex[:7]}")
        _report(monkeypatch, user_b, "PHONE", f"+8493{uuid.uuid4().hex[:7]}")

        _login_as(monkeypatch, user_a)
        resp = client.get("/api/v1/reports", headers={"X-Device-Uid": "test-device"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


class TestAT04_8_AutoActiveCappedAtNghiNgoInFR01:
    """
    Kịch bản nối FR-04 -> FR-01: sau auto-active (community, confidence=70),
    quét lại số đó ở FR-01 (EP-01) phải ra tối đa NGHI_NGO, KHÔNG được
    NGUY_HIEM (BR-01-1b).
    """

    def test_scan_after_auto_active_caps_at_nghi_ngo(
        self, make_user, monkeypatch, db_session, cleanup_blacklist, cleanup_device_scans
    ):
        phone = f"+8494{uuid.uuid4().hex[:7]}"
        cleanup_blacklist(EntityType.PHONE, phone)

        for _ in range(3):
            user = make_user()
            resp = _report(monkeypatch, user, "PHONE", phone)
            assert resp.status_code == 200, resp.text

        entity = _get_blacklist_entity(db_session, EntityType.PHONE, phone)
        assert entity.is_active is True  # xác nhận auto-active đã xảy ra trước khi quét

        device_uid = f"test-at04-8-{uuid.uuid4()}"
        cleanup_device_scans(device_uid)

        scan_resp = client.post(
            "/api/v1/scans",
            json={"input_type": "PHONE", "content": phone},
            headers={"X-Device-Uid": device_uid},
        )
        assert scan_resp.status_code == 200, scan_resp.text
        assert scan_resp.json()["risk_level"] == "NGHI_NGO"
        assert scan_resp.json()["risk_level"] != "NGUY_HIEM", (
            "Entry COMMUNITY confidence=70 (chưa đạt ngưỡng hard-override 90) "
            "KHÔNG được phép hard-override thành NGUY_HIEM (BR-01-1b)"
        )