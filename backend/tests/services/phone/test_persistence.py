"""
Test T-022 — persist_phone_lookup() (FR-02.8, BR-02-5)

Ghi vào scan_request (input_type=PHONE) + scan_result — dùng lại đúng 2
bảng của FR-01, KHÔNG tạo bảng phone_lookup riêng, để lượt tra số hiện
chung màn lịch sử FR-06 (Chốt mục treo #5 trong spec).

1) CÁCH CHẠY

Đây là test TÍCH HỢP thật — ghi (INSERT) thật vào scan_request +
scan_result trên DB thật (không dùng _FakeSession), vì hàm có ràng
buộc FK (ScanResult.scan_request_id -> ScanRequest.id) cần DB thật
để kiểm tra đúng. Mỗi test tự rollback() ở cuối, KHÔNG để lại rác
trong DB sau khi chạy xong.

Chạy trong Docker:
    docker compose up -d
    docker compose exec web pytest tests/services/phone/test_persistence.py -v -s

Chạy toàn bộ test suite trước khi push (đảm bảo không vỡ test khác):
    docker compose exec web pytest -v

2) LƯU Ý

Nếu test bị ngắt đột ngột giữa chừng (crash/mất kết nối) TRƯỚC khi
rollback() kịp chạy, có thể sót vài dòng rác dạng device_uid bắt đầu
bằng "test-device-...". Có thể dọn tay bằng cách:
    DELETE FROM device WHERE device_uid LIKE 'test-device-%';
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.db_models import Device, InputType, RiskLevel, ScanRequest, ScanResult, ScanStatus
from app.services.phone.lookup_service import PhoneLookupResult
from app.services.phone.persistence import _REPRESENTATIVE_SCORE, persist_phone_lookup


@pytest.fixture()
def test_device(db_session: Session) -> Device:
    """Tạo 1 Device mới cho mỗi test, ẩn danh (user_id=None), rollback sau khi xong."""
    device = Device(
        device_uid=f"test-device-{uuid.uuid4()}",
        platform="test",
        user_id=None,
    )
    db_session.add(device)
    db_session.flush()
    yield device
    db_session.rollback()  # dọn sạch, không để lại rác trong DB thật sau khi test


def _make_result(risk_level: RiskLevel, **overrides) -> PhoneLookupResult:
    defaults = dict(
        phone="+84987654321",
        carrier="Viettel",
        risk_level=risk_level,
        reasons=[{"source": "CARRIER", "text": "Nhà mạng: Viettel"}],
        recommended_action="Test action",
        rule_score=0,
        ai_score=None,
        ai_available=True,
        has_hard_override=(risk_level == RiskLevel.NGUY_HIEM),
    )
    defaults.update(overrides)
    return PhoneLookupResult(**defaults)


class TestPersistPhoneLookup:
    def test_creates_scan_request_with_correct_fields(self, db_session: Session, test_device: Device):
        result = _make_result(RiskLevel.AN_TOAN)
        raw_phone = "0987654321"

        scan_request = persist_phone_lookup(db_session, test_device, raw_phone, result)

        assert scan_request.id is not None
        assert scan_request.device_id == test_device.id
        assert scan_request.user_id == test_device.user_id  # None vì ẩn danh
        assert scan_request.input_type == InputType.PHONE
        assert scan_request.raw_content == raw_phone
        assert scan_request.normalized_text == result.phone  # E.164, không phải raw
        assert scan_request.status == ScanStatus.COMPLETED
        assert scan_request.completed_at is not None

    def test_creates_scan_result_linked_to_scan_request(self, db_session: Session, test_device: Device):
        result = _make_result(RiskLevel.NGUY_HIEM, rule_score=0, ai_score=None)

        scan_request = persist_phone_lookup(db_session, test_device, "0912345678", result)

        scan_result = (
            db_session.query(ScanResult)
            .filter(ScanResult.scan_request_id == scan_request.id)
            .first()
        )
        assert scan_result is not None
        assert scan_result.risk_level == RiskLevel.NGUY_HIEM
        assert scan_result.rule_score == 0
        assert scan_result.ai_score is None
        assert scan_result.has_hard_override is True
        assert scan_result.recommended_action == "Test action"

    @pytest.mark.parametrize(
        "risk_level,expected_score",
        [
            (RiskLevel.AN_TOAN, 0),
            (RiskLevel.NGHI_NGO, 50),
            (RiskLevel.NGUY_HIEM, 100),
        ],
    )
    def test_final_score_uses_representative_mapping(
        self, db_session: Session, test_device: Device, risk_level, expected_score
    ):
        # Khóa lại giá trị đại diện hiện tại (0/50/100) — nếu ai đổi
        # _REPRESENTATIVE_SCORE mà quên cập nhật test, test này sẽ báo động
        # ngay, nhắc nhở kiểm tra lại quyết định [CẦN LÀM RÕ] đã note trong code.
        assert _REPRESENTATIVE_SCORE[risk_level] == expected_score

        result = _make_result(risk_level)
        scan_request = persist_phone_lookup(db_session, test_device, "0987654321", result)

        scan_result = (
            db_session.query(ScanResult)
            .filter(ScanResult.scan_request_id == scan_request.id)
            .first()
        )
        assert scan_result.final_score == expected_score

    def test_does_not_commit_only_flushes(self, db_session: Session, test_device: Device):
        """
        T-022 không tự commit — trách nhiệm của router (T-023). Kiểm tra
        bằng cách rollback thủ công sau flush: nếu persist_phone_lookup lỡ
        tự commit, dữ liệu sẽ VẪN còn sau rollback (sai). Nếu chỉ flush
        đúng như thiết kế, rollback sẽ xóa sạch.
        """
        result = _make_result(RiskLevel.AN_TOAN)
        scan_request = persist_phone_lookup(db_session, test_device, "0987654321", result)
        scan_id = scan_request.id

        db_session.rollback()

        still_exists = db_session.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
        assert still_exists is None, (
            "persist_phone_lookup() không được tự commit — nếu bản ghi vẫn "
            "còn sau rollback() nghĩa là hàm đã commit ngầm, sai thiết kế."
        )