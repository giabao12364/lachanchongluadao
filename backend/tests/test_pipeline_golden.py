"""
T-019 — Test FR-01 với bộ mẫu vàng (AT-01-1, AT-01-2)

AT-01-1 (spec trang 14): Bộ mẫu vàng 50 tin lừa đảo -> >= 48/50 ra
NGHI_NGO/NGUY_HIEM.
AT-01-2 (spec trang 14): Bộ 30 tin an toàn thật -> <= 3/30 bị gắn cờ sai.

Đây là test TÍCH HỢP thật (gọi execute_scan_pipeline với DB thật, cần
scoring_rule đã seed qua T-001/alembic upgrade head), khác với các unit
test dùng _FakeSession ở tests/services/phone/.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.db_models import ScoringRule
from app.services.pipeline import execute_scan_pipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_MATCHED_RISK_LEVELS = ("NGHI_NGO", "NGUY_HIEM")


def _load_fixture(filename: str) -> list[dict]:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _run_pipeline_risk(db: Session, text: str) -> str:
    result = execute_scan_pipeline(text, db)
    return result["risk_level"]


@pytest.fixture()
def _require_seeded_rules(db_session: Session):
    """
    Golden test phụ thuộc scoring_rule đã seed (T-001). Nếu bảng rỗng,
    mọi mẫu lừa đảo sẽ ra AN_TOAN sai lệch -> báo lỗi rõ ràng thay vì
    để 2 test dưới fail mù mờ, khó chẩn đoán nguyên nhân.
    """
    count = (
        db_session.query(ScoringRule)
        .filter(ScoringRule.is_active == True)  # noqa: E712
        .count()
    )
    if count == 0:
        pytest.fail(
            "Bảng scoring_rule không có bản ghi active nào. "
            "Chạy `alembic upgrade head` để nạp seed T-001 trước khi "
            "chạy golden test."
        )
    return count


class TestGoldenScamSet:
    """AT-01-1: Bộ mẫu vàng 50 tin lừa đảo -> >= 48/50 ra NGHI_NGO/NGUY_HIEM."""

    def test_at_01_1_scam_detection_rate(self, db_session: Session, _require_seeded_rules):
        samples = _load_fixture("golden_scam_50.json")
        assert len(samples) == 50, "Bộ mẫu vàng phải có đúng 50 mẫu theo AT-01-1"

        missed: list[dict] = []
        for item in samples:
            risk = _run_pipeline_risk(db_session, item["text"])
            if risk not in _MATCHED_RISK_LEVELS:
                missed.append({"id": item["id"], "risk": risk, "text": item["text"][:60]})

        detected = len(samples) - len(missed)
        print(f"\n[AT-01-1] Phát hiện đúng {detected}/{len(samples)} mẫu lừa đảo.")
        if missed:
            print("Các mẫu bị bỏ sót (risk_level không đạt NGHI_NGO/NGUY_HIEM):")
            for m in missed:
                print(f"  - {m['id']} -> {m['risk']}: {m['text']}...")

        assert detected >= 48, (
            f"AT-01-1: chỉ phát hiện {detected}/50 (yêu cầu >= 48/50). "
            f"Bỏ sót: {[m['id'] for m in missed]}"
        )


class TestGoldenSafeSet:
    """AT-01-2: Bộ 30 tin an toàn thật -> <= 3/30 bị gắn cờ sai."""

    def test_at_01_2_false_positive_rate(self, db_session: Session, _require_seeded_rules):
        samples = _load_fixture("golden_safe_30.json")
        assert len(samples) == 30, "Bộ mẫu an toàn phải có đúng 30 mẫu theo AT-01-2"

        false_positives: list[dict] = []
        for item in samples:
            risk = _run_pipeline_risk(db_session, item["text"])
            if risk != "AN_TOAN":
                false_positives.append({"id": item["id"], "risk": risk, "text": item["text"][:60]})

        fp_count = len(false_positives)
        print(f"\n[AT-01-2] Báo nhầm {fp_count}/{len(samples)} mẫu an toàn.")
        if false_positives:
            print("Các mẫu bị báo nhầm (risk_level khác AN_TOAN):")
            for fp in false_positives:
                print(f"  - {fp['id']} -> {fp['risk']}: {fp['text']}...")

        assert fp_count <= 3, (
            f"AT-01-2: báo nhầm {fp_count}/30 (yêu cầu <= 3/30). "
            f"Báo nhầm: {[fp['id'] for fp in false_positives]}"
        )