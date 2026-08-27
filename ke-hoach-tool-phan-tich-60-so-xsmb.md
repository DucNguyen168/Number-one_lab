
# KẾ HOẠCH THIẾT KẾ TOOL PHÂN TÍCH 60 SỐ CUỐI GIẢI ĐẶC BIỆT XSMB

**Phiên bản:** 0.1.0-draft  
**Trạng thái:** Chờ duyệt  
**Mục tiêu:** Phân tích dữ liệu lịch sử và xếp hạng 100 số `00–99`, sau đó chọn đúng 60 số có điểm cao nhất trước mỗi kỳ quay.

> Tool chỉ phục vụ phân tích, kiểm định mô hình và mô phỏng. Không cam kết dự đoán trúng, không tự động đặt cược và không được dùng kết quả kiểm thử trên dữ liệu tương lai để quảng cáo hiệu quả.

## 1. Bài toán và điều kiện hòa vốn

Giả định theo mô tả:

- Chọn 60 số, mỗi số 10.000 đồng: tổng vốn mỗi kỳ là **600.000 đồng**.
- Nếu trúng một số: nhận **950.000 đồng**, lãi ròng **350.000 đồng**.
- Nếu không trúng: lỗ **600.000 đồng**.

Nếu kết quả công bằng và độc lập, một tập 60 số bất kỳ có xác suất trúng cơ sở:

`P(trúng) = 60 / 100 = 60%`

Giá trị kỳ vọng tại xác suất 60%:

`EV = 0,60 × 350.000 + 0,40 × (-600.000) = -30.000 đồng/kỳ`

Điểm hòa vốn:

`p × 350.000 + (1-p) × (-600.000) = 0`

`p hòa vốn = 600 / 950 ≈ 63,1579%`

Do đó, tool chỉ có lợi thế kinh tế nếu tỷ lệ trúng thật trên dữ liệu chưa từng nhìn thấy **cao hơn 63,16%**, sau khi tính mọi chi phí và sai lệch thực tế. Mục tiêu 60% là chưa đủ.

## 2. Phạm vi sản phẩm

### Trong phạm vi

- Thu thập và chuẩn hóa kết quả giải đặc biệt theo ngày.
- Lấy hai chữ số cuối và lưu dưới dạng `00–99`.
- Phát hiện dữ liệu thiếu, trùng ngày, sai định dạng hoặc bị sửa.
- Tính điểm/xác suất cho toàn bộ 100 số.
- Chọn 60 số có điểm cao nhất trước giờ quay.
- Khóa và lưu dấu thời gian dự đoán để chống sửa sau khi biết kết quả.
- Cập nhật kết quả sau kỳ quay và tính hiệu suất.
- Backtest tuần tự theo thời gian, Monte Carlo và kiểm định thống kê.
- Dashboard real-time: dữ liệu mới, tập 60 số, độ tin cậy và lịch sử lãi/lỗ mô phỏng.
- Xuất báo cáo CSV/JSON/PDF ở giai đoạn sau.

### Ngoài phạm vi

- Không tự động đặt cược, nạp/rút tiền hoặc kết nối tài khoản cá cược.
- Không tăng tiền cược theo chuỗi thua, gấp thếp hoặc martingale.
- Không tuyên bố “chắc thắng”, “bao trúng” hoặc che giấu kỳ thua.
- Không dùng dữ liệu kết quả đã công bố để tạo lại dự đoán cho chính ngày đó.

## 3. Dữ liệu và quy trình real-time

### Dữ liệu tối thiểu

| Trường | Ví dụ | Ghi chú |
|---|---:|---|
| `draw_date` | `2026-08-17` | Một bản ghi hợp lệ mỗi ngày |
| `special_prize` | `12345` | Kết quả giải đặc biệt đầy đủ |
| `last_two` | `45` | Luôn giữ 2 ký tự, gồm cả `00` |
| `published_at` | ISO-8601 | Thời điểm nguồn công bố |
| `source` | URL/mã nguồn | Truy vết nguồn |
| `checksum` | SHA-256 | Phát hiện nội dung bị thay đổi |
| `status` | verified/pending | Chỉ dữ liệu verified được chấm điểm |

### Luồng xử lý

1. Bộ lập lịch lấy dữ liệu từ ít nhất hai nguồn được phép sử dụng.
2. Chuẩn hóa ngày, múi giờ `Asia/Bangkok`/giờ Việt Nam và định dạng giải.
3. So sánh chéo; nếu hai nguồn khác nhau thì đánh dấu `pending` và không tự chấm.
4. Trước giờ quay, hệ thống tạo danh sách 60 số và ghi bản snapshot bất biến.
5. Sau khi kết quả được xác minh, hệ thống chấm `hit/miss`, ROI và cập nhật dashboard.
6. Mọi lần sửa dữ liệu đều có audit log; không ghi đè âm thầm.

## 4. Phương pháp phân tích

### Baseline bắt buộc

- 60 số cố định.
- 60 số chọn ngẫu nhiên bằng seed được lưu lại.
- 60 số có tần suất cao nhất trong cửa sổ lịch sử.

Mọi mô hình phải thắng baseline trên tập kiểm thử ngoài mẫu, không chỉ trên dữ liệu huấn luyện.

### Mô hình ứng viên

- Tần suất có làm trơn Bayesian để tránh thổi phồng số ít xuất hiện.
- Tần suất theo nhiều cửa sổ: 30, 90, 180, 365 và toàn bộ lịch sử.
- Trọng số giảm dần theo thời gian, nhưng hệ số phải được chọn chỉ trên tập huấn luyện.
- Đặc trưng đầu/đuôi, chẵn/lẻ, số kép và khoảng cách lần xuất hiện gần nhất.
- Mô hình đa lớp dự đoán phân phối xác suất cho 100 số.
- Ensemble chỉ được giữ nếu cải thiện ổn định trong walk-forward test.

Các đặc trưng “gan”, “chu kỳ” hoặc “vừa ra nên chưa ra lại” không được mặc định là quy luật. Chúng chỉ được dùng nếu qua kiểm định ngoài mẫu.

### Cách chọn 60 số

1. Mô hình xuất xác suất/điểm cho 100 số.
2. Hiệu chỉnh xác suất nếu mô hình cho phép.
3. Sắp xếp giảm dần và lấy top 60.
4. Khi bằng điểm, dùng quy tắc cố định đã công bố trước, không chọn thủ công sau khi xem kết quả.

## 5. Kiểm thử và chống tự đánh lừa

### Chia dữ liệu

- Chỉ dùng chia theo thời gian; không random train/test.
- Ví dụ: huấn luyện 5 năm đầu, dự đoán kỳ kế tiếp, sau đó cuộn cửa sổ từng ngày.
- Mỗi kỳ kiểm thử phải được mô phỏng như real-time: chỉ dùng dữ liệu đã có trước thời điểm khóa dự đoán.
- Tách riêng một giai đoạn final holdout và chỉ mở một lần khi mô hình đã chốt.

### Chỉ số đánh giá

| Chỉ số | Ý nghĩa | Ngưỡng tham khảo |
|---|---|---:|
| `Hit@60` | Kết quả có nằm trong 60 số không | Phải vượt 63,16% để hòa vốn theo giả định |
| ROI | Lãi/lỗ chia tổng vốn | Phải dương ngoài mẫu |
| Brier score | Độ chính xác phân phối xác suất | Thấp hơn baseline |
| Log loss | Phạt dự đoán quá tự tin | Thấp hơn baseline |
| Max drawdown | Chuỗi suy giảm vốn lớn nhất | Hiển thị bắt buộc |
| Longest miss streak | Chuỗi kỳ không trúng dài nhất | Hiển thị bắt buộc |

### Kiểm định thống kê

- Kiểm định nhị thức với giả thuyết gốc `p = 0,60`.
- Báo cáo khoảng tin cậy 95% cho `Hit@60`.
- Bootstrap theo thời gian để ước lượng độ bất định của ROI.
- Permutation test để kiểm tra mô hình có thật sự hơn chọn ngẫu nhiên hay không.
- Điều chỉnh multiple testing khi thử nhiều mô hình/cửa sổ để giảm data snooping.

Không duyệt triển khai thử tiền thật chỉ vì tỷ lệ quan sát vượt 63,16% trong vài chục hoặc vài trăm kỳ. Cần cỡ mẫu đủ lớn và cận dưới khoảng tin cậy vẫn phải vượt điểm hòa vốn. Nếu tỷ lệ quan sát khoảng 65%, có thể cần xấp xỉ vài nghìn kỳ mới có bằng chứng đủ mạnh rằng tỷ lệ thật vượt 63,16%.

## 6. Kiến trúc kỹ thuật đề xuất

### Stack

- **Backend:** Python + FastAPI.
- **Phân tích:** pandas, NumPy, SciPy, scikit-learn.
- **Database:** PostgreSQL.
- **Hàng đợi/lịch chạy:** Celery hoặc APScheduler; Redis nếu cần queue/cache.
- **Frontend:** Next.js + TypeScript.
- **Real-time:** WebSocket hoặc Server-Sent Events cho cập nhật dashboard.
- **Đóng gói:** Docker Compose cho bản thử nghiệm.

### Thành phần

- `collector`: lấy và đối chiếu kết quả.
- `validator`: kiểm tra schema, ngày, nguồn và checksum.
- `feature_pipeline`: tạo đặc trưng chỉ từ quá khứ.
- `model_service`: huấn luyện, chấm điểm và version mô hình.
- `prediction_lock`: khóa danh sách 60 số trước giờ quay.
- `evaluator`: chấm hit/miss, ROI và kiểm định.
- `dashboard`: hiển thị danh sách, lịch sử và cảnh báo.
- `audit_log`: lưu thay đổi dữ liệu, mô hình và dự đoán.

### API dự kiến

- `GET /api/results/latest`
- `GET /api/predictions/latest`
- `POST /api/predictions/generate`
- `POST /api/predictions/{id}/lock`
- `GET /api/backtests/{run_id}`
- `GET /api/metrics/rolling`
- `GET /api/audit-log`

## 7. Giao diện MVP

Dashboard gồm:

- 100 ô số từ `00–99`, tô nổi 60 số được chọn.
- Điểm/xác suất của từng số và phiên bản mô hình.
- Thời điểm tạo, thời điểm khóa và trạng thái `locked`.
- Kết quả mới nhất và trạng thái xác minh nguồn.
- `Hit@60`, ROI, khoảng tin cậy, drawdown theo 30/90/365 kỳ và toàn bộ holdout.
- So sánh với chọn ngẫu nhiên và tập 60 số cố định.
- Nhật ký mọi dự đoán, kể cả dự đoán sai; không cho xóa khỏi báo cáo hiệu suất.
- Cảnh báo rõ khi mẫu nhỏ, dữ liệu lỗi hoặc mô hình không vượt baseline.

## 8. An toàn, bảo mật và tính minh bạch

- Bí mật nguồn/API chỉ đặt trong biến môi trường; không commit vào Git.
- Phân quyền: người xem, người chạy backtest và quản trị dữ liệu.
- Snapshot dự đoán dùng hash và timestamp; khóa rồi không được sửa.
- Rate limit, kiểm tra input, backup PostgreSQL và audit log.
- Tuân thủ điều khoản sử dụng của nguồn dữ liệu và quy định pháp luật áp dụng.
- Chỉ hiển thị mô phỏng tài chính; không tích hợp nút đặt cược.
- Cho phép đặt giới hạn vốn mô phỏng và cảnh báo chuỗi thua/drawdown.

## 9. Lộ trình triển khai

### Giai đoạn 0 — Xác minh giả định (2–3 ngày)

- Chốt cách hiểu “1 ăn 95”, thời điểm chốt cược và phí thực tế.
- Chọn nguồn dữ liệu hợp lệ và kiểm tra lịch sử có đủ dài không.
- Chốt thời điểm khóa dự đoán để ngăn rò rỉ dữ liệu.

### Giai đoạn 1 — Data pipeline và baseline (4–7 ngày)

- Thiết kế database, nhập dữ liệu lịch sử và kiểm tra chất lượng.
- Xây ba baseline và báo cáo `Hit@60`, ROI, khoảng tin cậy.
- Hoàn thành walk-forward engine.

### Giai đoạn 2 — Mô hình và kiểm định (7–14 ngày)

- Xây đặc trưng, mô hình ứng viên và versioning.
- Chạy kiểm định ngoài mẫu, bootstrap, permutation test.
- Loại mô hình không cải thiện ổn định.

### Giai đoạn 3 — MVP real-time (7–10 ngày)

- Collector theo lịch, prediction lock, evaluator và dashboard.
- WebSocket/SSE, cảnh báo dữ liệu và audit log.
- Chạy paper-trading liên tục, không dùng tiền thật.

### Giai đoạn 4 — Đánh giá go/no-go

- So sánh kết quả live với baseline và điểm hòa vốn.
- Kiểm tra cận dưới khoảng tin cậy, drawdown và lỗi dữ liệu.
- Nếu không có bằng chứng lợi thế: dừng ở công cụ thống kê, không mở rộng.

## 10. Tiêu chí nghiệm thu và quyết định duyệt

### Nghiệm thu kỹ thuật

- 100% dự đoán live được lưu và khóa trước khi có kết quả.
- Không có leakage trong unit test và walk-forward test.
- Kết quả từ hai nguồn được đối chiếu; xung đột không tự động chấm.
- Backtest có thể tái lập bằng seed, phiên bản dữ liệu và phiên bản mô hình.
- Dashboard luôn hiển thị cả kỳ thắng lẫn kỳ thua.

### Go/No-Go về lợi thế

- **Go nghiên cứu tiếp:** mô hình hơn baseline ổn định trên nhiều giai đoạn ngoài mẫu.
- **Chưa đủ bằng chứng:** tỷ lệ quan sát trên 63,16% nhưng cận dưới khoảng tin cậy chưa vượt 63,16%.
- **No-Go:** ROI ngoài mẫu không dương, không hơn random hoặc chỉ tốt ở một cửa sổ đã tối ưu quá mức.

## 11. Các quyết định cần người duyệt xác nhận

- [ ] `950.000 đồng` là tổng tiền nhận về hay tiền lãi chưa gồm 10.000 đồng tiền cược?
- [ ] Nguồn dữ liệu lịch sử và nguồn real-time nào được phép sử dụng?
- [ ] Giờ khóa danh sách 60 số trước kỳ quay là bao nhiêu?
- [ ] Dùng cửa sổ huấn luyện mở rộng hay cố định?
- [ ] Khoảng thời gian paper-trading tối thiểu trước khi đánh giá lại?
- [ ] Ngân sách hạ tầng và yêu cầu triển khai local/cloud?
- [ ] Có cần đăng nhập nhiều người dùng hay chỉ dashboard cá nhân?

## 12. Kết luận

Tool có thể được xây dựng để thu thập real-time, xếp hạng và khóa 60 số, đồng thời đo chính xác mô hình có vượt ngẫu nhiên hay không. Tuy nhiên, nếu xổ số thực sự độc lập và công bằng, mọi tập 60 số vẫn có xác suất 60%; dữ liệu lịch sử không tự tạo ra lợi thế. Quyết định quan trọng nhất của dự án là không dựa vào tỷ lệ trúng thô, mà dựa vào kiểm thử ngoài mẫu, khoảng tin cậy và ROI sau mọi chi phí.
