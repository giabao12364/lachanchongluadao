from typing import Optional
from fastapi import Request


def get_current_user_id(request: Request) -> Optional[str]:
    """
    Trả về user_id (string UUID) nếu request đã đăng nhập hợp lệ, None nếu ẩn danh.

    THỰC TẾ: khi FR-05 hoàn thành, hàm này sẽ:
      1. Lấy Bearer token từ header Authorization
      2. Giải mã JWT (verify chữ ký, hạn dùng)
      3. Lấy user_id từ payload["sub"]
      4. Trả về user_id đó

    HIỆN TẠI (FR-05 chưa có): luôn trả về None -> mọi request coi là ẩn danh.
    """
    # TODO(FR-05): thay thân hàm này bằng giải mã JWT thật khi FR-05 xong.
    return None