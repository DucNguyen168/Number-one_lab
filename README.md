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
Nếu cài bằng `pyproject.toml` và cần lệnh `xsmb-lab serve`, cài thêm
`.[server]` (hoặc dùng `requirements.txt`, vốn đã có Uvicorn).

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
- Dự đoán một số cuối: <http://127.0.0.1:8000/du-doan-catboost-2-so>
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

- Tạo dự đoán Top 65 cho Tần suất, Logistic và CatBoost lúc `17:00` theo giờ `Asia/Ho_Chi_Minh`; khóa trước deadline `17:30`.
- Bắt đầu kiểm tra kết quả lúc `18:30` giờ Việt Nam, thử lại mỗi `10` giây
  sau khi lượt trước kết thúc cho đến khi có kết quả hợp lệ trong ngày.
  Nếu chưa có kết quả, tiếp tục đến hết ngày; nguồn lỗi cũng được thử lại.
- Đồng bộ/đối chiếu bổ sung lúc `18:30`, `18:50` và `19:10`.
- Sau mỗi lần đồng bộ, tự đánh giá prediction cùng ngày.
- Ngay khi xác nhận đã có kết quả hợp lệ của hôm nay, tự khóa ba mô hình Top 65 cho ngày mai. Nếu snapshot ngày mai đã tồn tại thì giữ nguyên,
  không tạo trùng và không ghi đè.

Có thể thay đổi trong `.env`:

```dotenv
AUTO_PREDICTION_COUNT=65
PREDICTION_TIME=17:00
RESULT_POLL_START_TIME=18:30
RESULT_POLL_INTERVAL_SECONDS=10
RESULT_SYNC_TIMES=18:30,18:50,19:10
SYNC_ON_STARTUP=true
SCHEDULER_RETRY_ATTEMPTS=3
SCHEDULER_RETRY_DELAY_SECONDS=5
```

Scheduler chỉ hoạt động trong thời gian ứng dụng đang chạy. Nếu cần chạy bền vững,
dùng Windows Task Scheduler, NSSM hoặc container/service manager để giữ API hoạt động.
Khi `SYNC_ON_STARTUP=true`, scheduler tự đồng bộ năm hiện tại ngay sau khi server chạy.
Nếu kết quả hôm nay đã tồn tại, lượt khởi động này cũng tự kiểm tra và tạo prediction
cho ngày mai; lịch `17:00` vẫn là phương án dự phòng nếu ứng dụng được bật trước giờ quay.
Mỗi mốc lỗi được thử lại theo `SCHEDULER_RETRY_ATTEMPTS` thay vì bị đánh dấu hoàn tất
ngay ở lần lỗi đầu tiên.

### Tự động hóa khi deploy Vercel

Vercel chạy FastAPI dưới dạng serverless Function, vì vậy scheduler trong RAM không
được dùng trên Vercel. Biến hệ thống `VERCEL=1` được nhận diện tự động và ứng dụng dùng
Vercel Cron gọi `GET /api/auto-daily` thay thế. Các mốc trong `vercel.json` là UTC:

- `0 9 * * *`: chuẩn bị dự đoán từ 16:00 giờ Việt Nam, chừa thời gian cho độ trễ cron Hobby và deadline 17:30.
- `30 11 * * *`, `50 11 * * *`, `10 12 * * *`: đồng bộ/đối chiếu sau kỳ quay và
  tạo prediction ngày mai ngay khi kết quả hôm nay xuất hiện.

Endpoint cron và thao tác thủ công không yêu cầu đăng nhập hoặc khóa API theo cấu hình
hiện tại. `ADMIN_API_KEY`, `CRON_SECRET` và `REQUIRE_ADMIN_AUTH` không còn được đọc,
kể cả khi biến cũ vẫn tồn tại trên Vercel. Các endpoint thao tác có thể được gọi bởi
người truy cập website. MongoDB lease vẫn chống các lượt Cron chạy chồng nhau.

Deploy mã nguồn mới lên Production, giữ `AUTO_PREDICTION=true`, rồi mở **Tự động →
Chạy tự động ngay** để đồng bộ và bổ sung dự đoán ngày hợp lệ. `ENABLE_SCHEDULER`
không điều khiển Vercel Cron. Lịch Cron cần được bật trong **Settings → Cron Jobs**.
Giao diện hiển thị lượt chạy gần nhất; nhãn Vercel Cron mô tả chế độ hoạt động, không
khẳng định Vercel đã thực thi lịch. Lỗi mô hình trả HTTP 500, lỗi nguồn trả 502.
Function dùng Fluid Compute với giới hạn 300 giây và lease 330 giây.

**Ngày lịch sử bị thiếu:** nút tạo thông thường chuyển sang ngày mai khi hôm nay đã
có kết quả, nên không khôi phục được ngày bị bỏ lỡ. Mở **Tự động → Bổ sung ngày thiếu
bằng hồi kiểm**, chọn ngày và Top N để chạy cả ba mô hình. Mỗi mô hình chỉ nhận dữ liệu
trước ngày chọn. Các bản này lưu riêng trong `prediction_replays`, hiển thị nhãn
**HỒI KIỂM** trong lịch sử, có giờ tạo thực tế và không có giờ khóa giả. Chúng không
tham gia thống kê/so sánh dự đoán trực tiếp; snapshot trực tiếp đã có được giữ nguyên.
Gọi lại cùng ngày/model/Top N không tạo trùng. Kết quả dùng để đánh giá hồi kiểm được
đọc lại khi xem, nên dữ liệu nguồn sửa hoặc xung đột không giữ HIT/MISS cũ.


Trên gói Hobby, cron chỉ đảm bảo chạy trong giờ đã cấu hình, có thể lệch tối đa 59 phút.
Lịch trên vẫn dùng các cron hằng ngày tương thích Hobby; không dùng cron mỗi phút
vì Vercel sẽ từ chối deploy trên gói này.
[Giới hạn chính thức của Vercel](https://vercel.com/docs/cron-jobs/usage-and-pricing).
Sau mỗi lần sửa `vercel.json` phải tạo production deployment mới thì lịch cron mới
được cập nhật.

**Cập nhật nhanh trên Hobby khi trang đang mở:** từ `18:30`, trình duyệt kiểm tra
mỗi 10 giây và gọi `POST /api/results/refresh` nếu hôm nay chưa có kết quả hợp lệ.
Endpoint chỉ thu thập kết quả của ngày hiện tại, không tạo/huấn luyện dự đoán.
Các nguồn được tải song song và lưu ngay khi từng nguồn trả về; vẫn giữ kiểm tra
xung đột. MongoDB lease dùng chung với cron và nhật ký lần thử giới hạn số lượt
gọi nguồn trên toàn bộ người xem, kể cả khi nguồn lỗi. Kết quả hợp lệ đã có thì
không tải lại nguồn. Giao diện tiếp tục kiểm tra mỗi phút để cập nhật đánh giá và
các thay đổi đối chiếu, hiển thị thời điểm lưu kết quả và bỏ cache khi đọc kết quả.
Khi quay lại tab hoặc có mạng trở lại, trang kiểm tra ngay. Trình duyệt có thể làm
chậm timer ở tab nền; thời gian nhận dữ liệu còn phụ thuộc lúc nguồn công bố và
tốc độ mạng, không bảo đảm kết quả xuất hiện đúng 18:30.

**Cập nhật nhanh ngay cả khi không mở trang:** cần dịch vụ lịch bên ngoài gọi
`POST https://<ten-mien>/api/results/refresh` từ 18:30 đến hết ngày giờ Việt Nam
(11:30–16:59 UTC), mỗi 10–60 giây tùy dịch vụ. Endpoint tự bỏ qua trước khung giờ
và giới hạn lượt gọi nguồn, không yêu cầu gửi khóa admin ra trình duyệt.
Các lịch cron hằng ngày vẫn tạo dự đoán ngày tiếp theo. Dự án chưa tự đăng ký hay
cấu hình dịch vụ lịch bên ngoài; chỉ deploy mã nguồn không tạo ra dịch vụ này.
Nếu chạy API trên máy tính/VPS liên tục với `ENABLE_SCHEDULER=true`, scheduler
tích hợp đã tự kiểm tra mỗi 10 giây và không cần mở trang.

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

### Mô hình Logistic kiểm chứng chéo

Trang `/du-doan-than-tai` dùng `factorized_logistic_v1`: hai Logistic Regression L2
học riêng hàng chục và hàng đơn vị từ ba kỳ trước, thứ trong tuần và khoảng cách ngày.
Hai phân phối 0–9 được ghép thành 100 điểm cho `00–99`, sau đó chọn Top 60/65/70/75/80.
Snapshot được lưu trong collection `predictions` với `model_version` riêng nên có thể
đối chiếu cùng ngày với `frequency_ensemble_v1` mà không trộn lịch sử.

Chạy lại báo cáo lịch sử cố định:

```powershell
.\.venv\Scripts\python.exe scripts\compare_factorized_logistic.py
```

Kết quả được ghi vào `reports/logistic_comparison/summary.json` và `daily.csv`.
Trang Thần Tài hiển thị riêng backtest lịch sử và kết quả live đã khóa; backtest không
được coi là bằng chứng chắc chắn cho dữ liệu tương lai.

### Mô hình CatBoost trực tiếp 00–99

Trang `/du-doan-catboost-2-so` hiện là trang **CatBoost** và thay thế luồng tạo dự đoán một
chữ số mới. Mô hình `direct_catboost_multiclass_v2_context2000` học trực tiếp 100 lớp
`00–99` từ ngữ cảnh 2.000 kỳ trước. Để thời gian huấn luyện khả thi, mô hình giữ 14 kỳ
gần nhất theo đúng thứ tự và nén toàn bộ 2.000 kỳ thành tần suất 00–99 ở cửa sổ
365/2.000 kỳ cùng các thống kê nhiều cửa sổ. `has_time=True` giữ thứ tự thời gian; không có kết quả của kỳ dự đoán hoặc
tương lai trong dữ liệu train. Phân phối đầu ra được co 15% về phân phối đều để hạn
chế điểm quá tự tin khi dữ liệu lịch sử còn thưa.

Phiên bản này cần tối thiểu **2.730 kết quả lịch sử**: 2.000 kỳ làm cửa sổ đặc
trưng và 730 mẫu để huấn luyện. Nếu dữ liệu chưa đủ, API từ chối tạo snapshot thay
vì âm thầm rút ngắn cửa sổ hoặc trộn với mô hình 14 kỳ cũ.

CatBoost tạo cùng một loại snapshot Top 60/65/70/75/80 trong collection `predictions`,
nên cơ chế khóa, đối chiếu HIT/MISS và lịch sử dùng chung với hai mô hình hiện có.
`/api/model-comparison/three-way` chỉ ghép những ngày mà Tần suất A, Logistic B và
CatBoost C đều đã khóa trước kỳ quay và đã được đánh giá; không đủ kỳ ghép thì không
được suy ra mô hình nào tốt hơn.

`catboost>=1.2.10` là dependency native khá lớn. Bản deploy Vercel bỏ Uvicorn
(chỉ cần khi chạy server local), loại Plotly/Matplotlib khỏi đồ thị dependency
do mô hình chỉ dự đoán bằng mảng số, và không đóng gói test/tài liệu/báo cáo vào
Function. CatBoost, NumPy, SciPy, pandas và scikit-learn vẫn được giữ nguyên.
Vì tổng gói vẫn có thể vượt 500 MB, `vercel.json` bật Fluid Compute cùng cờ
Large Functions `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` ở build. Sau khi push, kiểm tra
Production build và Function trên dashboard; nếu dự án chưa được bật beta, đặt thêm
biến này trong **Project Settings → Environment Variables** rồi redeploy. Tính năng
Large Functions phụ thuộc Vercel và không thay thế bước kiểm tra build thực tế.

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
