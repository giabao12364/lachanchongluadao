import pytest

from app.core.database import SessionLocal


@pytest.fixture()
def db_session():
    """
    Session SQLAlchemy thật, kết nối theo DATABASE_URL_SYNC (.env).
    Dùng cho test tích hợp cần dữ liệu seed thật (scoring_rule, app_config,
    blacklist_entity) — execute_scan_pipeline() chỉ ĐỌC, không ghi, nên
    không cần rollback bảo vệ ở đây.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()