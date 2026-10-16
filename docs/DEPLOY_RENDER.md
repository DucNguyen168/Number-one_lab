# Chạy thử miễn phí trên Render

Cấu hình đã chuẩn bị tại [`render.yaml`](../render.yaml): một **Python Web Service Free** tại Singapore, dùng MongoDB Atlas hiện tại. Không khai báo worker, cron, đĩa hay database trả phí. Chưa tạo/deploy dịch vụ trên tài khoản Render.

## Sửa lỗi trong ảnh: render.yaml not found on main branch

Render đang đọc file trong GitHub, không đọc workspace máy tính này. Cần commit và push `render.yaml`, `.python-version`, `scripts/run_host.py` cùng toàn bộ bản sửa ứng dụng lên nhánh `main` của repo `DucNguyen5668/number_two`. Chỉ tạo file local chưa làm màn hình Render hết lỗi.

Sau khi GitHub hiển thị `render.yaml` ở thư mục gốc, tải lại màn hình Blueprint và điền:

| Ô trên màn hình | Giá trị |
|---|---|
| Blueprint Name | `xsmb-lab-free` |
| Branch | `main` |
| Blueprint Path | `render.yaml` |

Bản xem trước phải hiện đúng một web service `xsmb-lab`, plan **Free**. Khi được yêu cầu nhập `MONGODB_URI`, sao chép URI từ cấu hình Vercel hiện tại vào ô secret; không gửi URI vào chat hoặc commit vào repo. Database mặc định là `xsmb_research`; nếu project cũ dùng tên khác, sửa lại đúng tên trước khi deploy.

`sync: false` yêu cầu nhập secret ở lần tạo Blueprint đầu tiên. [Tài liệu Blueprint của Render](https://render.com/docs/blueprint-spec).

## Nếu muốn tạo Web Service trực tiếp

Dùng New → Web Service → chọn repo và điền:

| Trường | Giá trị |
|---|---|
| Name | `xsmb-lab` |
| Language | Python |
| Branch | `main` |
| Region | Singapore nếu còn khả dụng |
| Root Directory | Để trống, dùng gốc repo |
| Build Command | `python -m pip install --no-cache-dir -r requirements.txt` |
| Start Command | `python scripts/run_host.py web` |
| Instance Type | Free |
| Health Check Path | `/api/health` |

Nhập Environment theo `envVars` trong `render.yaml`; cách tạo thủ công không tự áp dụng Blueprint. `.python-version` chọn nhánh Python 3.13, tránh tự dùng Python mặc định mới hơn chưa kiểm tra với mô hình. Render hỗ trợ bỏ patch trong file này và chọn patch mới nhất của nhánh. [Python version](https://render.com/docs/python-version).

Runner đọc `PORT` do Render cấp và bind `0.0.0.0`; không cần tự thêm PORT hoặc Start Command Uvicorn khác. Chỉ chạy một instance/một worker.

## Giới hạn của bản Free

Render Free có 512 MB RAM, 0,1 CPU theo bảng cấu hình hiện tại. Service ngủ sau 15 phút không có truy cập; khi có truy cập mới sẽ thức lại, thường mất khoảng một phút. Không có background worker Free. [Tài nguyên](https://render.com/docs/blueprint-spec), [giới hạn Free](https://render.com/docs/free).

Do đó:

- Scheduler hoạt động khi tiến trình đang thức. Không bảo đảm tự chạy lúc 17:00 hoặc cập nhật sau 18:30 khi không có người truy cập.
- Khi thử theo dõi kỳ quay, mở trang trước 18:30 và để tab hoạt động; vẫn phụ thuộc nguồn dữ liệu, tab nền và khả năng service chạy.
- `SYNC_ON_STARTUP=false` tránh tải/đối chiếu toàn năm mỗi lần service thức. Khi dữ liệu cần đồng bộ ngay, dùng nút Đồng bộ hoặc Tự động. Scheduler vẫn xử lý các mốc đến hạn khi service đang chạy.
- Nếu không có snapshot khóa trước 17:30, bản tạo sau kết quả chỉ là hồi kiểm, không phải dự đoán LIVE.
- Chưa đo peak RAM trên Render thật. CatBoost hoặc nhiều tác vụ đồng thời có thể bị hết RAM; nếu Logs có Out of memory/OOM/exit 137, không bấm huấn luyện liên tục. Có thể tạo snapshot trên máy local dùng cùng Atlas rồi dùng Render xem dữ liệu; muốn huấn luyện ổn định trên host cần đo và chọn thêm RAM.
- Không chạy báo cáo rolling 365 kỳ hoặc backfill toàn bộ lịch sử trên Free chỉ để thử giao diện. Các báo cáo này vẫn có thể chạy riêng trên local.

## Kiểm tra sau deploy

1. Logs phải có startup hoàn tất và service chuyển Live.
2. Mở URL `onrender.com` được cấp + `/api/health`. Mong đợi `mongodb: true`, `scheduler_enabled: true`, `automation_mode: "scheduler"`. Nhãn scheduler bật không có nghĩa Render sẽ luôn thức.
3. Nếu lỗi Mongo timeout, kiểm tra URI, user/password và Atlas Network Access. Lấy outbound IP/ranges từ Render service để cấu hình Atlas. Không tự tạo database rỗng thay database đang dùng.
4. Không sao chép `VERCEL`, `VERCEL_ENV`, `VERCEL_URL` vào Render. Các biến này làm ứng dụng nhận nhầm môi trường và tắt scheduler.
5. Mở ba trang mô hình, lịch sử và LIVE A/B/C; thử tác vụ thủ công từng lần và quan sát Memory/Logs.
6. Sau khi xác nhận Render hoạt động, tắt cron Vercel cũ và scheduler local nếu muốn Render là máy duy nhất tự động. Không bật hai máy cùng lịch trên một Atlas khi không cần.

Blueprint tự deploy khi push commit theo cấu hình hiện tại. Luôn xem lại plan trong phần Review trước khi áp dụng sửa Blueprint; file này chỉ chọn Free. Không cần ADMIN_API_KEY hoặc CRON_SECRET.
