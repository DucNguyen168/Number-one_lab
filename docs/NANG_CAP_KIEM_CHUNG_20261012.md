# Nâng cấp kiểm chứng ưu tiên cao và vừa — 12/10/2026

Đã triển khai trong mã nguồn local sáu hạng mục của báo cáo rà soát. Bản này nâng cấp khóa dự đoán, lưu bằng chứng và đánh giá; thuật toán xếp hạng và trọng số hiện tại được giữ nguyên. Chưa deploy hoặc chạy tác vụ ghi MongoDB production trong lần thực hiện này.

## Các thay đổi

| Mức | Hạng mục | Hành vi mới |
|---|---|---|
| Cao | Deadline thực tế | Cả Tần suất, Logistic, CatBoost và chữ số đều chặn tạo mới từ 17:30 giờ Việt Nam. Kiểm tra trước đọc/fit và sau fit/lưu tập huấn luyện. Huấn luyện vượt deadline không tạo snapshot dự đoán. Đọc lại snapshot đã tồn tại không khóa lại hoặc đổi thời gian cũ. |
| Cao | So sánh đủ điều kiện | Kiểm tra protocol, deadline/timezone, thời điểm thông tin, cutoff huấn luyện, danh sách số, dấu vết dữ liệu, cấu hình/code/thư viện, chiến lược, batch và actual revision. Chỉ ghép cùng ngày/N/dữ liệu. Tính hit từ actual hiện tại; bỏ evaluation cũ chưa chấm lại. Mỗi version chỉ dùng một nhóm cấu hình/thư viện hợp lệ mới nhất. |
| Cao | Dữ liệu huấn luyện bất biến | Lưu `training_datasets` bằng hash nội dung, dùng `$setOnInsert`; ba mô hình dùng cùng dữ liệu chia sẻ cùng bản lưu. Mỗi record có ngày, hai số, giải đặc biệt, status, ID và revision hash. Snapshot dự đoán giữ reference, config hash, code hash và phiên bản thư viện. |
| Vừa | Cache rolling | Khóa cache gồm hash cấu hình, code mô hình/code báo cáo, Python/thư viện và protocol kiểm chứng. Đổi dữ liệu hoặc một thành phần này sẽ dựng lại báo cáo; không dùng cache cũ chỉ vì dataset hash chưa đổi. |
| Vừa | Chấm lại và nhật ký | Mỗi lượt đối chiếu kiểm tra các snapshot pending/evaluated/invalidated. Kết quả thay đổi thì chấm lại; mất actual, sai định dạng hoặc conflict thì đánh dấu invalidated; giải quyết xung đột thì khôi phục đánh giá. Lưu lần chấm trước trong `evaluation_history`; compare-and-set tránh hai lượt ghi cùng một chỉnh sửa. |
| Vừa | Thống kê trên giao diện | Bảng A/B, A/B/C và rolling hiện số kỳ, Wilson CI 95% và mốc N/100. Live có McNemar ghép cặp, Holm cho ba phép so sánh; bootstrap không trả khoảng ở mẫu quá ngắn. Hiển thị số bộ dự đoán bị loại và thông báo chưa đủ bằng chứng. Các bảng live được tải lại cùng kết quả; không chạy fit rolling trong vòng cập nhật kết quả. |

Các query đối chiếu bỏ scores, window details và nhật ký không cần dùng; đọc actual theo nhóm ngày với các trường tối thiểu để giảm tải mỗi lượt cập nhật.

## Lịch tạo dự đoán và cập nhật kết quả

- Scheduler local mặc định tạo lúc **17:00**. Cấu hình cũ từ 17:30 trở đi được scheduler đưa về 17:00; backend vẫn từ chối mọi lần khóa mới từ deadline.
- Cron tạo dự đoán dự phòng trong `vercel.json` đổi thành `0 9 * * *`, tức **16:00 giờ Việt Nam**. Hobby có thể chạy trong giờ được cấu hình, ví dụ 16:00–16:59, nên lịch này chừa thời gian trước deadline. [Tài liệu Vercel](https://vercel.com/docs/cron-jobs/usage-and-pricing).
- Các lượt đồng bộ sau 18:30 và cơ chế trình duyệt kiểm tra mỗi 10 giây giữ lịch hiện có. Khi có kết quả hôm nay, vẫn tạo dự đoán ngày mai.
- Auto-daily không tạo dự đoán hôm nay sau 17:30 nếu kết quả chưa có; chờ kết quả để tạo kỳ tiếp theo. API tạo cho ngày đã qua deadline trả lỗi rõ ràng.

## Dữ liệu cũ và áp dụng

Snapshot cũ giữ nguyên danh sách dự đoán và giờ khóa. Bộ đối chiếu mới có thể thêm revision hash/nhật ký khi cập nhật đánh giá, nhưng không tự điền dấu vết huấn luyện hay tuyên bố chúng tuân thủ protocol mới. Vì vậy bảng so sánh chính thức có thể bắt đầu với 0 kỳ đủ điều kiện sau deploy; lịch sử và báo cáo audit cũ vẫn xem được. Chỉ snapshot mới có đủ metadata tham gia protocol `locked_before1730_v2`.

MongoDB tự tạo collection `training_datasets` khi lưu bản đầu tiên; dùng unique `_id` mặc định, không cần di chuyển hoặc xóa dữ liệu cũ. Nên theo dõi dung lượng vì lưu thêm lịch sử huấn luyện cho từng nội dung dữ liệu mới. Các bản giống nhau được dùng chung giữa mô hình và Top N.

Để áp dụng lên website, cần redeploy bản mã nguồn này lên Vercel; lịch cron mới chỉ có hiệu lực với deployment mới. Nếu cấu hình `PREDICTION_TIME` riêng, đặt trước 17:30; giá trị mẫu là 17:00. Không cần API key hoặc cài thêm thư viện mô hình.

## Kiểm tra

Đã chạy toàn bộ: **110 test Python và 9 test JavaScript đạt**; kiểm tra cú pháp `app.js` đạt. Test mới bao gồm khóa muộn khi chưa có actual, fit đi qua deadline cho bốn mô hình, dữ liệu dùng chung/bất biến, giữ nguyên ranking thực của Tần suất/chữ số, đổi cấu hình hoặc dữ liệu giữa mô hình, stale evaluation, sửa actual/conflict/khôi phục, cache đổi cấu hình/thư viện/dữ liệu, scheduler cũ và hiển thị CI/trạng thái invalidated. Các test dùng dữ liệu giả, không ghi production.

Nguồn chính: `app/services/prediction_protocol.py`, `model_comparison.py`, `evaluation.py`, `rolling_comparison.py`; tích hợp vào bốn hàm tạo dự đoán, scheduler, API và giao diện. Test bổ sung: `tests/test_prediction_integrity.py`, `tests/test_comparison_ui.cjs`.
