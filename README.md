# XSMB Research Lab

Công cụ nghiên cứu cá nhân để:

- Thu thập giải đặc biệt XSMB từ `kqxs.vn` và lưu vào MongoDB.
- Giữ nguyên kết quả 5 chữ số và hai số cuối `00–99`.
- Tạo prediction snapshot cho 60–80 số và khóa ngay khi tạo.
- Tạo một snapshot độc lập chọn Top‑1 chữ số cuối từ `0–9`.
- Không cho tạo prediction hồi tố nếu ngày đó đã có kết quả.
- Tự động đối chiếu `hit/miss` khi collector nhận kết quả mới.
- Mở lại chi tiết từng prediction đã khóa: Top N, đủ 100 điểm số, dữ liệu huấn luyện và kết quả thực tế.
- Chạy backtest walk-forward chỉ bằng dữ liệu có trước từng kỳ.
- Backtest Top‑1 chữ số cuối và đối chiếu với baseline ngẫu nhiên `10%`.
- Theo dõi toàn bộ dữ liệu bằng dashboard và MongoDB Compass.

Đây là công cụ kiểm định khả năng dự đoán, không phải hệ thống đảm bảo dự đoán đúng.

## Luồng dữ liệu

```text
KQXS yearly ───────┐
Xổ Số Đại Phát ────┼──► hợp nhất theo ngày
KQXS recent ───────┘        │
                            ▼
validate 5 digits + rebuild date + checksum
        │
        ▼
MongoDB.draw_results ─────► frequency_ensemble_v1
        │                            │
        │                            ▼
        │                  MongoDB.predictions (locked)
        │                            │
        └──────── result by date ────┤
                                     ▼
                            evaluation hit / miss
                                     │
                                     ▼
                               dashboard metrics
```

Collector dùng nhiều nguồn độc lập để tránh một website timeout làm hỏng toàn bộ lần
đồng bộ:

- `KQXS yearly`: dữ liệu lịch sử theo năm.
- `Xổ Số Đại Phát yearly`: nguồn lịch sử dự phòng và đối chiếu chéo.
- `KQXS recent`: bổ sung các kỳ mới nhất của năm hiện tại.

Mỗi nguồn được gọi riêng. Nếu một nguồn lỗi SSL/timeout nhưng nguồn khác còn hoạt động,
lần đồng bộ vẫn hoàn tất ở trạng thái `partial`; API chỉ trả `502` khi tất cả nguồn đều
không dùng được. Kết quả của từng nguồn được lưu trong `draw_results.sources`, còn tóm
tắt thành công/thất bại được lưu trong `collector_runs.sources`.

Các nguồn của cùng một năm được tải song song. MongoDB được đọc một lần và ghi bằng
`bulk_write`; những bản ghi có checksum không đổi sẽ không bị ghi lại. Backfill mặc
định bỏ qua các năm lịch sử đã có lần đồng bộ hoàn tất và chỉ cập nhật năm hiện tại.

## Yêu cầu

- Python 3.12 trở lên.
- MongoDB chạy tại máy local.
- MongoDB Compass để xem/chỉnh dữ liệu khi cần.
- Kết nối Internet khi đồng bộ từ nguồn.

MongoDB đang cài local có thể dùng URI mặc định:

```text
mongodb://127.0.0.1:27017
```

## Cài đặt trên Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Nếu MongoDB dùng URI hoặc database khác, sửa `.env` trước khi chạy.

## Nhập dữ liệu và khởi động

Nhập toàn bộ lịch sử hiện có từ 2019 đến năm hiện tại:

```powershell
.\.venv\Scripts\python.exe -m app.cli backfill --start-year 2019
```

Các lần chạy sau dùng chế độ gia tăng nên thường chỉ tải năm hiện tại. Chỉ dùng
`--force` khi cần kiểm tra lại toàn bộ nguồn lịch sử:

```powershell
.\.venv\Scripts\python.exe -m app.cli backfill --start-year 2019 --force
```

Khởi động API và dashboard:

```powershell
.\.venv\Scripts\python.exe -m app.cli serve --reload
```

Mở:

- Tổng quan: <http://127.0.0.1:8000/>
- Kết quả và đồng bộ dữ liệu: <http://127.0.0.1:8000/ket-qua>
- Dự đoán hai số cuối: <http://127.0.0.1:8000/du-doan-2-so>
- Dự đoán một số cuối: <http://127.0.0.1:8000/du-doan-1-so>
- Backtest hai mô hình: <http://127.0.0.1:8000/backtest>
- API docs: <http://127.0.0.1:8000/docs>

Thanh nút điều hướng kiểu ứng dụng ở đầu trang chuyển giữa các chức năng mà không tải
lại toàn bộ giao diện; trên điện thoại thanh này nằm cố định ở cuối màn hình. Mỗi URL
vẫn có thể mở trực tiếp hoặc lưu bookmark; backend trả cùng shell giao diện rồi
JavaScript chỉ hiển thị các khối thuộc đúng trang.

## MongoDB Compass

1. Mở MongoDB Compass.
2. Kết nối `mongodb://127.0.0.1:27017`.
3. Sau lần backfill đầu tiên, mở database `xsmb_research`.
4. Các collection chính:

| Collection | Nội dung |
|---|---|
| `draw_results` | Kết quả kỳ quay, nguồn, checksum và xung đột |
| `predictions` | Snapshot dự đoán bất biến, scores và đánh giá hit/miss |
| `backtest_runs` | Kết quả walk-forward và lịch sử từng kỳ |
| `digit_predictions` | Snapshot Top‑1 chữ số cuối 0–9 và đánh giá hit/miss |
| `digit_backtest_runs` | Backtest riêng cho mô hình một chữ số cuối |
| `collector_runs` | Nhật ký đồng bộ thành công/thất bại |

Các index duy nhất được tạo tự động khi ứng dụng khởi động. `draw_results.draw_date`
không thể bị trùng; prediction không thể trùng theo ngày, model và số lượng đã chọn.
Trong `draw_results`, trường `sources` giữ snapshot theo từng website để kiểm tra chéo;
trường kết quả chuẩn chỉ được cập nhật khi dữ liệu hợp lệ và không âm thầm ghi đè khi
hai nguồn mâu thuẫn.

## Lệnh vận hành

```powershell
# Đồng bộ lại năm hiện tại và tự đối chiếu prediction pending
.\.venv\Scripts\python.exe -m app.cli sync

# Tạo prediction 65 số cho một ngày chưa có kết quả
.\.venv\Scripts\python.exe -m app.cli predict --date 2026-08-18 --count 65

# Tạo prediction một chữ số cuối 0-9
.\.venv\Scripts\python.exe -m app.cli digit-predict --date 2026-08-18

# Đối chiếu tất cả prediction đang chờ
.\.venv\Scripts\python.exe -m app.cli evaluate

# Backtest walk-forward
.\.venv\Scripts\python.exe -m app.cli backtest --count 65 --minimum-training-draws 365

# Backtest Top-1 chữ số cuối (baseline ngẫu nhiên 10%)
.\.venv\Scripts\python.exe -m app.cli digit-backtest --minimum-training-draws 365
```

Có thể đổi URL nguồn và timeout trong `.env`:

```dotenv
KQXS_BASE_URL=https://www.kqxs.vn
XOSODAIPHAT_BASE_URL=https://xosodaiphat.com
HTTP_TIMEOUT_SECONDS=12
HTTP_CONNECT_TIMEOUT_SECONDS=5
HTTP_RETRIES=1
BACKFILL_WORKERS=4
SKIP_COMPLETED_HISTORY=true
```

## Scheduler hằng ngày

Mặc định scheduler:

- Tạo đồng thời prediction 65 số và prediction Top‑1 chữ số cuối lúc `17:30` theo giờ `Asia/Ho_Chi_Minh`.
- Đồng bộ kết quả lúc `18:35`, `18:50` và `19:10`.
- Sau mỗi lần đồng bộ, tự đánh giá prediction cùng ngày.
- Ngay khi xác nhận đã có kết quả hợp lệ của hôm nay, tự khóa prediction 65 số và
  prediction Top‑1 cho ngày mai. Nếu snapshot ngày mai đã tồn tại thì giữ nguyên,
  không tạo trùng và không ghi đè.

Có thể thay đổi trong `.env`:

```dotenv
AUTO_PREDICTION_COUNT=65
PREDICTION_TIME=17:30
RESULT_SYNC_TIMES=18:35,18:50,19:10
SYNC_ON_STARTUP=true
SCHEDULER_RETRY_ATTEMPTS=3
SCHEDULER_RETRY_DELAY_SECONDS=5
```

Scheduler chỉ hoạt động trong thời gian ứng dụng đang chạy. Nếu cần chạy bền vững,
dùng Windows Task Scheduler, NSSM hoặc container/service manager để giữ API hoạt động.
Khi `SYNC_ON_STARTUP=true`, scheduler tự đồng bộ năm hiện tại ngay sau khi server chạy.
Nếu kết quả hôm nay đã tồn tại, lượt khởi động này cũng tự kiểm tra và tạo prediction
cho ngày mai; lịch `17:30` vẫn là phương án dự phòng nếu ứng dụng được bật trước giờ quay.
Mỗi mốc lỗi được thử lại theo `SCHEDULER_RETRY_ATTEMPTS` thay vì bị đánh dấu hoàn tất
ngay ở lần lỗi đầu tiên.

## Mô hình hiện tại

`frequency_ensemble_v1` kết hợp phân phối tần suất có làm trơn của các cửa sổ:

- 30 kỳ: trọng số 35%.
- 90 kỳ: 25%.
- 180 kỳ: 20%.
- 365 kỳ: 15%.
- Toàn bộ lịch sử: 5%.

Model xuất phân phối cho đủ 100 số, sau đó xếp hạng và lấy Top N. Đây là baseline
thống kê để kiểm định; các đặc trưng chu kỳ hoặc “gan” không được coi là quy luật nếu
không thắng baseline trên dữ liệu ngoài mẫu.

Mô hình `last_digit_frequency_ensemble_v1` dùng cùng các cửa sổ và trọng số nhưng
gom kết quả theo đúng chữ số cuối `0–9`, làm trơn trên 10 nhóm rồi chọn duy nhất Top‑1.
Phần trăm hiển thị là **điểm phân phối thô của mô hình**, không phải xác suất trúng đã
hiệu chỉnh hay bảo đảm. Chỉ hit rate walk-forward và khoảng tin cậy so với baseline
`10%` mới dùng để đánh giá mô hình có tạo ra tín hiệu đáng kể hay không.

## Có cần API key AI không?

Không. Collector, prediction, backtest, MongoDB và dashboard đều chạy local mà không
cần API key. Mô hình ngôn ngữ không có thông tin về kết quả tương lai và tự nó không
tạo ra lợi thế thống kê.

Chỉ nên thêm AI dưới dạng một mô hình thử nghiệm riêng nếu có giả thuyết rõ ràng. Khi
đó phải khóa đầu ra AI trước kỳ quay, lưu prompt/model/version và so sánh walk-forward
với `frequency_ensemble_v1`. Biến `AI_API_KEY` trong `.env.example` chỉ là chỗ dự phòng;
phiên bản hiện tại không gửi dữ liệu tới dịch vụ AI.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Test hiện có kiểm tra parser giữ số `00`, loại dữ liệu sai, phát hiện ngày trùng,
đảm bảo Top N không trùng và ngăn dữ liệu cùng ngày/tương lai lọt vào prediction.
