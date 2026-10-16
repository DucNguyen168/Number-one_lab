# Deploy Vercel Hobby sau tối ưu CPU

Bản cấu hình ngày 16/10/2026. Các sửa đổi nằm trong workspace; cần commit/push rồi deploy. Chưa chạy production build trên tài khoản Vercel mới, chưa đo mức giảm CPU thực tế.

## Những gì đã tối ưu

- GET báo cáo rolling chỉ đọc cache, không chạy huấn luyện 365 kỳ. Tính báo cáo riêng trên máy local bằng `python scripts/run_host.py rolling-report` khi cần. Cache phải khớp môi trường/protocol/dữ liệu nên không bảo đảm báo cáo local dùng được trên Vercel.
- Trang tổng quan chỉ tải 2 API dữ liệu thay cho 15; CatBoost chỉ tải 4. Chuyển trang sẽ tải dữ liệu của trang đó. Health/settings và vòng theo dõi kết quả là các request riêng.
- Khi kết quả không đổi, các bảng chỉ tự tải lại sau 5 phút; thay đổi kết quả/trạng thái xung đột sẽ cập nhật ngay ở lượt poll kế tiếp. Bấm làm mới/chuyển trang vẫn tải lại dữ liệu.
- Bootstrap LIVE lưu cache trong bộ nhớ theo đầy đủ chuỗi HIT/MISS có thứ tự và Top N, tối đa 128 đầu vào. Dữ liệu thay đổi sẽ tính lại; không thay đổi thuật toán dự đoán hay điều kiện ghép cặp LIVE.
- HTML công khai có CDN cache 1 giờ; ảnh/CSS/JS có CDN cache 24 giờ, cache trình duyệt 5 phút. Asset vẫn đi qua Python khi CDN miss. JS mới đã đổi query version. API kết quả/automation vẫn `no-store`.
- Cron dùng đồng bộ ngày gần nhất; từ 19:00 đối chiếu toàn năm một lần thành công/partial mỗi ngày để phát hiện sửa nguồn. Nút đồng bộ năm thủ công vẫn dùng được. Sau lỗi hoàn toàn có thể thử lại. Giữ kiểm tra snapshot đã tồn tại trước khi tạo mới.
- Mongo lease tránh chạy auto-daily đồng thời; lượt vừa completed/waiting_result được giới hạn gọi lại trong 30 giây. Không thêm ADMIN_API_KEY/CRON_SECRET.
- Giới hạn BLAS/OpenMP 1 thread trước khi import mô hình ở entrypoint Vercel. Loại thư mục dev/report/env khỏi bundle; giữ Fluid và maxDuration 300 giây.

## Tạo project

1. Commit/push bản sửa lên nhánh `main` của `DucNguyen5668/number_two`.
2. Vercel → Add New → Project → Import repo đó.
3. Với cấu trúc `/api/index.py` và `vercel.json` hiện tại, dùng **Framework Preset: Other**, Root Directory là gốc repo. Không dùng lệnh khởi động Botkeep `run_host.py`, không khai báo Output Directory thành `app/static`.
4. Không nhập một Build Command tùy ý; để runtime Python cài dependency theo cấu hình repo. Giữ các thiết lập Fluid Compute/Large Functions trong `vercel.json`.
5. Nhập Environment từ [`deploy/vercel.env.example`](../deploy/vercel.env.example). URI lấy từ project đang dùng; database giữ nguyên để có lịch sử và snapshot cũ. Không đưa URI vào GitHub. Không cần PORT; Vercel quản lý cổng.
6. Deploy Production. Nếu lỗi bundle lớn, xem log và kiểm tra dự án được bật Large Functions theo [tài liệu Python](https://vercel.com/docs/functions/runtimes/python); cấu hình beta không đảm bảo mọi tài khoản được cấp tính năng. Không bỏ CatBoost chỉ để build qua mà không đánh giá ảnh hưởng.
7. Mở `/api/health`: `mongodb: true`, `scheduler_enabled: false`, chế độ `vercel_cron`. Đây là đúng trên serverless. Kiểm tra đủ ba trang mô hình và LIVE A/B/C; mở trang không được chạy huấn luyện rolling.
8. Kiểm tra Cron Jobs có bốn lịch trong `vercel.json`. Khi project mới chạy ổn, tắt cron của project cũ và scheduler local nếu dùng chung MongoDB, để không có hai deployment tự động cùng hoạt động.
9. Trong ngày đầu, kiểm tra Logs cho `/api/auto-daily`, thời gian chạy và trạng thái hoàn tất; Usage → Active CPU để theo dõi. HTTP 500/502 cần xem lỗi; không mở vòng retry liên tục. CPU vẫn có thể vượt hạn mức nếu chạy nhiều backtest, hồi kiểm hoặc traffic lớn.

## Lịch và tốc độ cập nhật

| Cron UTC | Giờ Việt Nam cấu hình | Mục đích |
|---|---|---|
| `0 9 * * *` | 16:00 | Bù dự đoán hôm nay trước hạn khóa 17:30 |
| `30 11 * * *` | 18:30 | Đồng bộ kết quả và tạo dự đoán ngày mai |
| `50 11 * * *` | 18:50 | Thử lại nếu nguồn hoặc mô hình lỗi |
| `10 12 * * *` | 19:10 | Đối chiếu nguồn và bổ sung snapshot còn thiếu |

Mỗi cron chỉ chạy một lần/ngày, tương thích Hobby; Vercel cho phép nhiều job hằng ngày. Tuy nhiên Hobby có thể gọi trễ tới 59 phút. Không có cam kết chạy chính xác 18:30 hay liên tục mỗi 10 giây khi không ai mở trang. [Giới hạn cron chính thức](https://vercel.com/docs/cron-jobs/usage-and-pricing).

Khi trang đang mở, trình duyệt kiểm tra mỗi khoảng 10 giây sau 18:30 đến khi có kết quả. API refresh có throttle chung giữa người xem; chỉ lấy kết quả/đánh giá, không huấn luyện. Cron hoặc nút Tự động sẽ bổ sung dự đoán ngày tiếp theo. Khi đã có kết quả, trình duyệt kiểm tra sửa đổi mỗi phút và chỉ tải các bảng khi cần. Nguồn chậm/retry và tab nền có thể kéo dài thời gian cập nhật.

## Hạn mức và dữ liệu

Hobby có 4 giờ Active CPU/tháng. Ảnh tài khoản cũ cho thấy team đã bị pause vì vượt CPU; tạo project mới trong **cùng team đang pause** không cấp một ngân sách mới và không gỡ pause. Cần dùng môi trường Vercel đủ điều kiện hoạt động hoặc giải quyết hạn mức với Vercel. Việc tối ưu không xóa usage đã dùng. [Fluid compute](https://vercel.com/docs/functions/usage-and-pricing).

Không chạy lại backfill 2019–nay khi dùng cùng database có đủ dữ liệu. Đối chiếu LIVE vẫn loại snapshot hồi kiểm/khóa muộn/khác cấu hình như trước; tối ưu CPU không biến chúng thành dự đoán LIVE. Sau chuyển host, chưa thể hứa tỷ lệ CPU giảm cụ thể trước khi quan sát production.
