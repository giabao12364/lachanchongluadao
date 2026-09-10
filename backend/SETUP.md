# Setup Backend — Lá Chắn Chống Lừa Đảo
Hướng dẫn này dành cho member clone repo về máy lần đầu. Toàn bộ code
(models, migration, docker-compose...) đã có sẵn trong repo — bạn KHÔNG cần
tự viết lại gì, chỉ cần dựng môi trường trên máy mình.

## Yêu cầu trước khi bắt đầu
- Python 3.12
- Docker Desktop (đã cài và đang chạy)
- Đã clone repo, đang đứng trong thư mục `backend/`

## Bước 1 — Tạo file `.env`
Tạo file `.env` (cùng thư mục `backend/`), giữ nguyên
nội dung mặc định dưới đây: 
"""
AI_PROVIDER=openai
AI_API_KEY=your-secret-key-here
AI_MODEL=gpt-4o-mini

ENV=dev
LOG_LEVEL=INFO
CONTENT_RETENTION_DAYS=30
"""

> `.env` đã nằm trong `.gitignore`, sẽ không bao giờ lên GitHub — mỗi máy tự
> tạo riêng.

## Bước 2 — Tạo môi trường ảo & cài thư viện
```bash
python -m venv venv
venv\Scripts\activate        # Windows PowerShell/cmd
# hoặc: source venv/bin/activate    # Mac/Linux

pip install -r requirements.txt
```

## Bước 3 — Tạo DB rỗng bằng Docker
```bash
docker compose up -d
docker ps
```
Phải thấy `lachan_postgres` và `lachan_redis` đang chạy (status "Up").

## Bước 4 — Chạy migration có sẵn vào DB rỗng của bạn
Migration đã được viết sẵn trong `alembic/versions/`, bạn KHÔNG cần
`alembic init` hay `alembic revision --autogenerate` lại — chỉ cần áp dụng nó bằng cách:

```bash
alembic upgrade head
```

## Bước 5 — Kiểm tra
```bash
docker exec -it lachan_postgres psql -U lachan_user -d lachan_db -c "\dt"
```
Phải thấy đủ 10 bảng nghiệp vụ + bảng `alembic_version`:
```
app_config, app_user, blacklist_entity, device, scam_report,
scan_entity, scan_request, scan_result, scan_signal, scoring_rule
```

Nếu đủ 11 dòng → xong, môi trường đã sẵn sàng để code.

---

## Xử lý lỗi — "password authentication failed for user lachan_user"

Lỗi này nghĩa là máy bạn có sẵn 1 Postgres khác (cài từ trước, không phải
Docker) đang chiếm cổng 5432, khiến kết nối bị lạc vào nhầm chỗ.

Cách kiểm tra:
```bash
netstat -ano | findstr :5432      # Windows
```
Nếu thấy nhiều hơn 1 dòng LISTENING → đúng là bị đụng cổng.

Cách sửa — đổi cổng riêng cho project này (không đụng gì tới máy):

1. Mở `docker-compose.yml`, đổi:
   ```yaml
   ports:
     - "5433:5432"
   ```
2. Mở `.env`, đổi `5432` thành `5433` ở 2 dòng `DATABASE_URL` và `DATABASE_URL_SYNC`.
3. Chạy lại:
   ```bash
   docker compose down
   docker compose up -d
   alembic upgrade head
   ```


---
TRƯỚC KHI COMMIT/PUSH YÊU CẦU:
1. Chạy lại toàn bộ test suite (thói quen đã thống nhất trước mỗi lần push):

docker compose exec web pytest -v

2. Test thử qua Swagger/docs 



