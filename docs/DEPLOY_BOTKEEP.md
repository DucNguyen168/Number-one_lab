# Triển khai tiết kiệm CPU trên Botkeep

Kiểm tra ngày 16/10/2026. Đề xuất: **một Python server chạy web + scheduler trên Botkeep, giữ MongoDB Atlas hiện tại**. Không cần mua Vercel Pro chỉ để chạy lịch 10 giây.

## Vì sao Vercel bị dừng

Ảnh tài khoản ghi Active CPU **4 giờ 33 phút / 4 giờ**, dự án Number One chiếm **99,9%**; thời hạn pause hiển thị đến **15/11/2026**. Đây là hạn mức CPU, không phải hết dung lượng hay số request. Sửa code hoặc deploy lại không xóa CPU đã dùng. [Hạn mức Fluid compute](https://vercel.com/docs/functions/usage-and-pricing).

Qua đọc code, mỗi lượt tải dashboard từng có thể gọi API báo cáo rolling, rồi chạy lại 365 kỳ huấn luyện khi cache hết hiệu lực. Nhiều lượt xem đồng thời có thể cùng dựng báo cáo. Đây là đường xử lý tốn CPU đã xác định; chưa có log theo endpoint để kết luận nó chiếm bao nhiêu trong 4 giờ 33 phút.

Bản sửa này:

- Các GET `model-comparison/rolling`, `historical`, `historical-daily` chỉ đọc báo cáo đã lưu; không huấn luyện khi mở trang.
- Thiếu cache đúng dữ liệu/protocol: giao diện thông báo chưa có báo cáo cập nhật. Không đưa báo cáo cũ thành kết quả hiện tại, không ảnh hưởng đối chiếu LIVE A/B/C.
- Báo cáo 365 kỳ được tính bằng lệnh riêng, có Mongo lease chống chạy trùng tối đa 6 giờ. Không đặt lịch tự dựng báo cáo mỗi ngày trên máy nhỏ.
- Lệnh chạy host dùng một Uvicorn worker, không reload; mặc định giới hạn BLAS/OpenMP một thread và tắt access log thường xuyên. CatBoost vẫn dùng cấu hình mô hình hiện tại.

## Cấu hình dành cho tài khoản trong ảnh

| Mục | Giá trị đề xuất |
|---|---|
| Loại ứng dụng | Python/FastAPI, Python 3.12 hoặc 3.13 |
| Server | 1 server cho dự án này |
| RAM | 2 GB nếu chưa cấp cho dự án khác |
| CPU | 1,5 vCore; nếu panel dùng %, tương ứng 150% |
| Storage | 2 GB |
| Nguồn | Repo `DucNguyen5668/number_two`, nhánh chứa bản sửa, thư mục gốc repo |
| Install | `python -m pip install --no-cache-dir -r requirements.txt` |
| Start | `python scripts/run_host.py web` |
| Health URL | `/api/health` |

5 slot dùng **chung** ngân sách 2 GB RAM / 1,5 vCore / 2 GB storage; không tạo 5 bản ứng dụng. Đây là cấu hình khởi đầu, chưa đo peak RAM/CPU trên máy Botkeep thật. Botkeep hỗ trợ tiến trình không ngủ theo lịch nhưng không cam kết uptime 100%; CPU vẫn chia sẻ và chịu fair use. MongoDB chưa được cung cấp trong danh mục của họ nên tiếp tục dùng Atlas. [Tài nguyên và vận hành Botkeep](https://botkeep.cloud/faq).

## Các bước triển khai

1. Đưa bản sửa trong workspace lên GitHub. Trong Botkeep thật, tạo project/server Python; kết nối GitHub, chọn repo, branch và project root. Import hoặc update source qua tab GitHub; chỉ bấm Redeploy không tự kéo commit mới. [Hướng dẫn GitHub](https://botkeep.cloud/docs/github).
2. Cấp tài nguyên như bảng trên. Không upload `.venv`, `.env`, `.git`, cache hay thư mục reports lớn. Với 2 GB đĩa, theo dõi phần trống sau cài thư viện; nếu hết đĩa phải tăng allocation/gói hoặc chọn host khác, không xóa dữ liệu MongoDB.
3. Dùng Python 3.12/3.13 và chạy lệnh Install. Không cài lại dependency trong lệnh Start ở mỗi lần khởi động. Nếu profile có trường tự cài requirements, dùng trường đó thay cho chạy cài hai lần. [Starter FastAPI chính thức](https://botkeep.cloud/templates/fastapi-api).
4. Mở Environment. Điền các giá trị từ [`deploy/botkeep.env.example`](../deploy/botkeep.env.example). `MONGODB_URI` phải là secret lấy từ cấu hình đang hoạt động, `MONGODB_DATABASE` phải giữ đúng database hiện tại. Cho phép địa chỉ egress của Botkeep trong Atlas Network Access nếu Atlas đang giới hạn IP; lấy địa chỉ từ panel/hỗ trợ nhà cung cấp.
5. Không đưa `VERCEL`, `VERCEL_ENV`, `VERCEL_URL` sang Botkeep vì chúng tắt scheduler nội bộ. Không cần `ADMIN_API_KEY` hay `CRON_SECRET`.
6. Điền Start command. Runner bind `0.0.0.0`, đọc `PORT`, sau đó `SERVER_PORT`, cuối cùng mới mặc định 8000. Đặt `PORT` đúng cổng được cấp ở panel. Không dùng `--reload`, nhiều worker hoặc nhiều replica.
7. Trong Domains/Networking của panel thật, nối alias/tên miền HTTPS vào đúng cổng ứng dụng. FAQ chính thức mô tả hỗ trợ alias và custom domain HTTPS, nhưng profile/quyền trong tài khoản phải có tính năng đó. Bản configurator preview trên website không thực sự chạy mạng. Nếu không thấy cổng/HTTP routing, dùng phương án worker phía dưới và hỏi hỗ trợ Botkeep về web exposure.
8. Start và kiểm tra Console: ứng dụng khởi động thành công, Mongo kết nối, không lặp restart hoặc lỗi thiếu RAM. Mở URL HTTPS mới + `/api/health`, kiểm tra `mongodb: true`, `scheduler_enabled: true`, `automation_mode: "scheduler"`.
9. Mở các trang kết quả, Tần suất, Logistic, CatBoost và LIVE A/B/C. Dữ liệu cũ vẫn ở cùng Atlas; không backfill toàn bộ lại chỉ vì đổi host. Báo cáo rolling có thể báo chưa cập nhật cho đến khi chạy lệnh riêng bên dưới.
10. Khi Botkeep đã xác minh hoạt động, tắt scheduler local và cron Vercel để chỉ còn **một** máy phụ trách tự động. Nếu giữ project Vercel dự phòng, bỏ các mục `crons` trong cấu hình của bản dự phòng hoặc disable cron từ panel. Không chạy đồng thời bản web Botkeep có scheduler và một worker Botkeep khác.

Tên miền `number-onesxmb.vercel.app` thuộc Vercel, không chuyển DNS của tên đó sang Botkeep được. Dùng alias Botkeep cấp hoặc tên miền riêng của bạn. Chuyển hướng qua Vercel đang pause không khôi phục được website.

## Lịch cập nhật và dự đoán

- Múi giờ: `Asia/Ho_Chi_Minh`.
- 17:00: tạo bộ dự đoán nếu chưa có; vẫn giữ hạn khóa LIVE trước 17:30.
- Sau 18:30: kiểm tra kết quả khoảng mỗi 10 giây đến khi nhận được kết quả hợp lệ. Đây là khoảng chờ giữa các lượt; thời gian nguồn phản hồi, retry và xử lý có thể làm chu kỳ dài hơn. Không thể có kết quả trước khi nguồn công bố.
- Có kết quả: đối chiếu snapshot, tạo dự đoán A/B/C cho ngày kế tiếp. Các mốc 18:50 và 19:10 tiếp tục kiểm tra nguồn.
- Không cần mở trình duyệt hoặc dùng dịch vụ ping giữ sống. Xem Console sau kỳ quay đầu tiên, kiểm tra có đủ ba snapshot và ngày `trained_through` đúng.

## Tính báo cáo rolling khi cần nghiên cứu

Chạy trong terminal của **cùng server, cùng source và dependency**:

```sh
python scripts/run_host.py rolling-report
```

Lệnh thoát sau khi lưu báo cáo vào Atlas; không dùng nó làm Start command lâu dài. Nên chạy ngoài khung 17:00–19:15 và theo dõi RAM; chỉ chạy một lần, không mở nhiều terminal huấn luyện. Nếu panel không có terminal/one-off command, không giả định Console nhập lệnh được: cần dùng khả năng thực thi được host hỗ trợ. Không khởi chạy một server thứ hai trên cùng ngân sách 2 GB chỉ để tạo báo cáo.

Báo cáo khớp được dùng lại khi đổi Top N. Kết quả xổ số, phiên bản Python/thư viện hoặc protocol/code thay đổi sẽ làm cache hết hiệu lực. Lượt xem không tự dựng lại. Khác môi trường Windows/Linux có thể không dùng chung cache rolling vì provenance cố ý nghiêm ngặt; LIVE A/B/C dùng cơ chế tương thích riêng đã có. Sau khi triển khai ổn định, lưu `python -m pip freeze` để tái lập dependency; không nâng thư viện giữa các lần restart tùy tiện.

## Nếu chỉ chạy nền trên Botkeep

Dùng Start command:

```sh
python scripts/run_host.py worker
```

Chế độ này dùng cùng Environment, chỉ chạy đồng bộ/đánh giá/dự đoán, không mở HTTP. Website vẫn cần host khác đang hoạt động; **không sửa được trang Vercel đang pause**. Khi Vercel được mở lại, bản web đã tối ưu có thể đọc Atlas; bỏ cron Vercel và không bật scheduler ở một máy khác. Thao tác tạo thủ công từ website Vercel vẫn dùng CPU Vercel, vì vậy phương án toàn bộ web + scheduler trên Botkeep được ưu tiên.

## Kiểm tra sau chuyển host

Theo dõi CPU, peak RAM, dung lượng đĩa và số lần restart trong 24–48 giờ. Kiểm tra một lần sync và tạo dự đoán A/B/C; xác nhận mở lại dashboard không tạo log huấn luyện 365 kỳ. Nếu bị OOM, không tăng số worker; giảm công việc đồng thời và đo lại trước khi quyết định tăng tài nguyên. Không có cam kết tài khoản miễn phí chịu được mọi lượng truy cập.

Các thay đổi này tối ưu vận hành, không nâng hay cam kết độ chính xác thuật toán.
