# Nâng cấp giao diện web và mobile — 16/10/2026

Giao diện dùng khung workspace thống nhất, giữ các trang và API hiện có. Không cần cài thêm thư viện frontend hoặc chạy bước build.

- Desktop: điều hướng đúng 5 mục, bố cục có giới hạn chiều rộng, phân cấp tiêu đề và thẻ số liệu, truy cập nhanh ba mô hình ở tổng quan.
- Tablet: điều hướng chuyển xuống hàng riêng để tránh chen chúc với thương hiệu và nút công cụ.
- Mobile: thanh điều hướng dưới cùng, khoảng trống safe area, thẻ số liệu hai cột, vùng chạm tối thiểu 44px cho các nút chính, bảng cuộn ngang và popup dạng sheet.
- Popup: dùng native `dialog` để quản lý focus và nền inert; khóa cuộn nền, khôi phục focus, đóng bằng Escape/chạm ngoài với popup thường. Thông báo quy định vẫn yêu cầu đồng ý mỗi lần truy cập. Nội dung dài có vùng cuộn riêng.
- Điều hướng: không tải lại shell, hiệu ứng vào trang 200ms, giữ hành vi mở tab bằng Ctrl/Cmd, khôi phục vị trí cuộn khi Back/Forward, thông báo tiêu đề cho trình đọc màn hình.
- Tải dữ liệu: hiển thị tiến trình, giờ cập nhật, lỗi toàn phần/một phần và nút thử lại. Gộp các GET giống nhau đang chạy; giới hạn đọc 25 giây. POST giữ hành vi riêng, không tự thử lại.
- Chi tiết dự đoán: bỏ qua phản hồi cũ nếu đã đóng hoặc mở một dự đoán khác; lỗi hiển thị ngay trong popup kèm nút thử lại.
- Hiệu năng: bỏ các hạt trang trí và chuyển động lặp gây phân tán, giảm lớp blur trên thẻ, gộp tải font. Theme được áp dụng sớm và hoạt động khi localStorage bị chặn. Tôn trọng `prefers-reduced-motion`.

Các file chính: `app/static/workspace.css` (khung responsive), `ui.js` (popup và chuyển động), `theme.js` (theme trước khi hiển thị), `app.js` (điều hướng và dữ liệu).

Kiểm tra đã thực hiện:

```powershell
node --test tests/test_workspace_ui.cjs tests/test_automation_ui.cjs tests/test_comparison_ui.cjs tests/test_result_refresh.cjs
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_contract.py tests/test_automation_access.py tests/test_result_refresh.py tests/test_comparison_cache.py
```

29 kiểm tra JavaScript và 41 kiểm tra Python đạt. HTML đã kiểm tra thẻ đóng/mở, ID trùng, đường dẫn tài nguyên và các ID được JavaScript sử dụng. Local preview trả HTTP 200 cho shell và CSS mới.

Giới hạn: phiên làm việc không có trình duyệt khả dụng cho kiểm thử trực quan. Chưa xác nhận ảnh chụp, kích thước thực tế hay thao tác cảm ứng trên thiết bị. Cần kiểm tra trực quan ở 320/390/768/1280px, hai theme, popup dài và bàn phím trước khi phát hành. Chưa triển khai lên hosting; các kiểm tra trên không chạy tác vụ ghi dữ liệu thật.

Xem riêng giao diện bằng `python scripts/preview_static.py --port 8765` (API không được cung cấp trong chế độ này). Chạy đầy đủ bằng `python -m app.cli serve --reload` với cấu hình MongoDB hiện có.

## Cập nhật trang kết quả — 17/10/2026

Bảng kết quả có khung phong cách bảo tàng, nằm trên khu vực đồng bộ và tranh. Hiển thị 6 ngày đầu; mỗi lần bấm “Xem thêm” tải 6 ngày cũ hơn bằng con trỏ ngày, giữ số ngày đã mở khi làm mới. Tranh giữ nguyên toàn bộ ảnh `img/backgroud.jpg`, chỉ hiển thị từ 1024px. Thanh điều hướng desktop dùng hai cột bên cân nhau để giữ menu ở giữa.

Cột nguồn được thay bằng A (Dự đoán), B (Thần Tài), C (CatBoost), có chú thích nhỏ. Đúng dùng xanh lá và ✓; sai dùng đỏ và ×. Thiếu dự đoán, chưa đánh giá hoặc đánh giá không còn khớp kết quả dùng màu trung tính và —. Bản hồi kiểm có nhãn HK riêng. Chữ và trạng thái sáng hơn trong dark mode, giữ bảng màu than ấm và đồng.

`GET /api/results?include_models=true` bổ sung đánh giá theo ngày, phiên bản mô hình và `auto_prediction_count`; giao diện ghi rõ Top đang đối chiếu. Hai truy vấn theo lô đọc dự đoán trực tiếp và hồi kiểm cho trang dữ liệu hiện tại, không huấn luyện hay ghi dữ liệu. Ưu tiên dự đoán trực tiếp; dữ liệu xung đột hoặc đánh giá trực tiếp cũ không được tô đúng/sai. API mặc định không thêm truy vấn mô hình.

Kiểm tra cập nhật: 37 kiểm thử JavaScript và 35 kiểm thử Python đạt (workspace/automation/comparison/result-refresh UI; results-pagination/model-outcomes/dashboard-contract/result-refresh backend). HTML hợp lệ về cấu trúc, ID và tham chiếu JS; 14 cặp màu chữ/trạng thái/mô hình đạt độ tương phản tối thiểu 4.5:1. Chưa kiểm tra trực quan bằng trình duyệt trong phiên này. Nếu server không dùng tự reload, cần khởi động lại backend để nhận phần API mới.
