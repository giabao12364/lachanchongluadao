"""
T-024 — Nghiệm thu FR-02 (AT-02-1 đến AT-02-6, spec mục 02.8)

Test qua HTTP endpoint thật (TestClient), không gọi thẳng hàm Python,
để kiểm tra toàn bộ luồng: middleware -> router -> service -> DB.

────────────────────────────────────────────────────────────────────
CÁCH CHẠY
────────────────────────────────────────────────────────────────────
    docker compose up -d
    docker compose exec web pytest tests/api/v1/test_phones_at02.py -v -s

────────────────────────────────────────────────────────────────────
LƯU Ý VỀ DỌN DỮ LIỆU
────────────────────────────────────────────────────────────────────
Endpoint EP-04 tự gọi db.commit() bên trong request (khác test_persistence.py
dùng rollback được) -> mỗi test dùng 1 device_uid duy nhất (uuid4), fixture
tự xóa scan_request/scan_result/device liên quan sau khi test xong (dù pass
hay fail), không để lại rác trong DB dev.

────────────────────────────────────────────────────────────────────
YÊU CẦU DỮ LIỆU
────────────────────────────────────────────────────────────────────
Cần đã seed T-003 (blacklist_entity), đặc biệt số +84900000004
(PUBLIC_FEED, confidence=90) dùng cho AT-02-3. Nếu số này không còn
tồn tại trong DB (bị xóa/đổi), test AT-02-3 cần cập nhật lại số khác.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.db_models import Device, ScanRequest

client = TestClient(app)

# Số đã seed ở T-003, source=PUBLIC_FEED -> luôn NGUY_HIEM bất kể confidence (BR-01-1)
BLACKLISTED_PUBLIC_FEED_PHONE = "0900000004"
# Số Viettel hợp lệ, KHÔNG nằm trong 40 bản ghi seed T-003
CLEAN_VIETTEL_PHONE = "0987654321"
# Đầu số không tồn tại trong bảng PhoneCarrierService (T-020)
UNKNOWN_PREFIX_PHONE = "0199999999"


@pytest.fixture()
def device_uid(db_session: Session):
    """
    Mỗi test dùng 1 X-Device-Uid riêng biệt, để cô lập dữ liệu và dọn sạch
    sau khi test xong -- vì EP-04 tự commit(), không rollback được.
    """
    uid = f"test-at02-{uuid.uuid4()}"
    yield uid

    # Dọn dẹp: xóa scan_request (kéo theo scan_result nhờ ON DELETE CASCADE)
    # rồi xóa device, tránh để lại rác sau mỗi lần chạy test.
    device = db_session.query(Device).filter(Device.device_uid == uid).first()
    if device:
        db_session.query(ScanRequest).filter(ScanRequest.device_id == device.id).delete()
        db_session.delete(device)
        db_session.commit()


class TestAT02_1_CarrierKnown:
    """AT-02-1: Tra số đầu 098 -> reasons có 'Nhà mạng: Viettel'."""

    def test_viettel_carrier_in_reasons(self, device_uid):
        resp = client.get(
            f"/api/v1/phones/{CLEAN_VIETTEL_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["carrier"] == "Viettel"
        assert any(r["text"] == "Nhà mạng: Viettel" for r in body["reasons"])


class TestAT02_2_CarrierUnknown:
    """AT-02-2: Tra số đầu số lạ -> reasons có 'Không xác định được nhà mạng'."""

    def test_unknown_prefix_carrier(self, device_uid):
        resp = client.get(
            f"/api/v1/phones/{UNKNOWN_PREFIX_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["carrier"] == "Không xác định"
        assert any(r["text"] == "Không xác định được nhà mạng" for r in body["reasons"])


class TestAT02_3_BlacklistPublicFeed:
    """AT-02-3: Số trong blacklist (PUBLIC_FEED) -> NGUY_HIEM, rule_score=0, ai_score=null."""

    def test_public_feed_number_is_nguy_hiem(self, device_uid, db_session: Session):
        resp = client.get(
            f"/api/v1/phones/{BLACKLISTED_PUBLIC_FEED_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "NGUY_HIEM"

        # BR-02-5: rule_score=0, ai_score=null -- kiểm tra trực tiếp trong DB
        # vì response JSON của EP-04 không expose 2 field này (chỉ có trong scan_result)
        from app.models.db_models import ScanResult
        scan_result = (
            db_session.query(ScanResult)
            .filter(ScanResult.scan_request_id == uuid.UUID(body["scan_id"]))
            .first()
        )
        assert scan_result.rule_score == 0
        assert scan_result.ai_score is None
        assert scan_result.has_hard_override is True


class TestAT02_4_NotInBlacklist:
    """AT-02-4: Số không có trong blacklist -> AN_TOAN, KHÔNG BAO GIỜ ra NGHI_NGO."""

    def test_clean_number_is_an_toan_never_nghi_ngo(self, device_uid):
        resp = client.get(
            f"/api/v1/phones/{CLEAN_VIETTEL_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "AN_TOAN"
        assert body["risk_level"] != "NGHI_NGO", (
            "Số sạch (không trong blacklist) không bao giờ được phép ra "
            "NGHI_NGO -- đây là quy tắc riêng bảo vệ FR-02 khỏi false positive."
        )


class TestAT02_5_AnonymousLookup:
    """AT-02-5: Tra ẩn danh -> lưu scan_request (input_type=PHONE), user_id=null."""

    def test_anonymous_lookup_persists_with_null_user_id(self, device_uid, db_session: Session):
        resp = client.get(
            f"/api/v1/phones/{CLEAN_VIETTEL_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert resp.status_code == 200
        scan_id = resp.json()["scan_id"]

        scan_request = (
            db_session.query(ScanRequest)
            .filter(ScanRequest.id == uuid.UUID(scan_id))
            .first()
        )
        assert scan_request is not None
        assert scan_request.input_type.value == "PHONE"
        assert scan_request.user_id is None  # ẩn danh, không đăng nhập


class TestAT02_6_AppearsInHistory:
    """AT-02-6: Xem lịch sử ở FR-06 -> lượt tra PHONE hiện chung màn lịch sử với FR-01."""

    def test_phone_lookup_appears_in_scan_history(self, device_uid):
        lookup_resp = client.get(
            f"/api/v1/phones/{CLEAN_VIETTEL_PHONE}",
            headers={"X-Device-Uid": device_uid},
        )
        assert lookup_resp.status_code == 200
        scan_id = lookup_resp.json()["scan_id"]

        history_resp = client.get(
            "/api/v1/scans",
            headers={"X-Device-Uid": device_uid},
        )
        assert history_resp.status_code == 200
        items = history_resp.json()["items"]

        matching = [item for item in items if item["scan_id"] == scan_id]
        assert len(matching) == 1, (
            f"Lượt tra số {scan_id} phải xuất hiện đúng 1 lần trong lịch sử "
            f"chung (FR-06), items hiện có: {[i['scan_id'] for i in items]}"
        )
        assert matching[0]["input_type"] == "PHONE"