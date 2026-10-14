# Hồi kiểm ngày 14/10/2026

Kết quả đã lưu: **28259**, hai số cuối **59**. Tại lúc kiểm tra, cả ba mô hình
không có snapshot trực tiếp cho ngày 14/10. Nút tạo bình thường chuyển sang 15/10
do ngày 14/10 đã có kết quả.

Đã bổ sung ba bản **hồi kiểm Top 65** vào collection `prediction_replays` của
MongoDB đang dùng cho website. Đã đối chiếu ID bản ghi kết quả với API Production
trước khi ghi. Snapshot trực tiếp trong `predictions` không bị thêm hoặc sửa.

| Mô hình | Dữ liệu huấn luyện | Hạng của 59 | Đối chiếu Top 65 |
|---|---|---:|---|
| Tần suất | 2.790 kỳ, đến 13/10/2026 | 71 | MISS |
| Logistic | 2.790 kỳ, đến 13/10/2026 | 51 | HIT |
| CatBoost | 2.790 kỳ, đến 13/10/2026 | 43 | HIT |

Đây là tính toán **sau khi biết kết quả**, với thuật toán hiện tại và dữ liệu lịch
sử hiện có. Dữ liệu ngày 14/10 và các ngày sau không được đưa vào huấn luyện.
Các bản này không chứng minh mô hình đã dự đoán trước kỳ quay và không được cộng
vào tỷ lệ chính xác trực tiếp hoặc so sánh trực tiếp giữa mô hình.

Chi tiết 100 điểm số, thời điểm tạo thực tế, phiên bản thuật toán, hash dữ liệu và
snapshot huấn luyện nằm trong [replays.json](replays.json). Giao diện mới ghép các
bản này vào lịch sử từng mô hình với nhãn **HỒI KIỂM** sau khi deploy mã mới.
