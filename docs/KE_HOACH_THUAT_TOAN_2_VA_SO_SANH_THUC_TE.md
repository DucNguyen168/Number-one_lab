# Kế hoạch thuật toán thứ hai và so sánh bằng kết quả thực

Ngày lập: 22/09/2026. Trạng thái: **đã triển khai lõi v1; đang chờ dữ liệu tương lai để xác nhận**.

### Cập nhật triển khai ngày 22/09/2026

- Đã thêm `factorized_logistic_v1`, dùng Logistic Regression L2 cho hàng chục và hàng đơn vị, tạo đủ 100 xác suất và snapshot bất biến trong collection `predictions`.
- Đã thêm API tạo/list/latest, so sánh A/B cùng kỳ, tích hợp scheduler và Vercel Cron để tự tạo mô hình B sau khi có kết quả mới.
- Đã thêm trang `/du-doan-than-tai` với lựa chọn 60/65/70/75/80, bảng số, bộ lọc, sao chép, lịch sử và so sánh live; theme đỏ–vàng theo phong cách Thần Tài Trung Hoa.
- Đã thêm script `scripts/compare_factorized_logistic.py`, manifest kết quả và 365 dòng đối chiếu tại `reports/logistic_comparison/`.
- Backtest cố định 365 kỳ quan sát từ 02/09/2025 đến 05/09/2026: Top 65 A đạt 213/365 = 58,36%; B đạt 243/365 = 66,58%; chênh lệch B−A = 8,22 điểm %, McNemar exact p=0,01995, paired block-bootstrap CI 95% = 1,92–14,52 điểm %. So với baseline 65%, Wilson CI của B là 61,59–71,22%, vẫn chứa 65%.
- Log loss/Brier của B (4,69048 / 0,99174) kém nhẹ A (4,68354 / 0,99161). B xếp hạng Top 65 tốt hơn trên giai đoạn này nhưng toàn phân phối chưa tốt hơn.
- Đây là kết quả lịch sử trên cấu hình đã chọn, chưa phải xác nhận tương lai độc lập. Giai đoạn theo dõi khóa trước tối thiểu 365 kỳ bắt đầu khi bản triển khai được đưa vào vận hành; chưa thể hoàn thành bằng code ngay trong ngày.

Mục tiêu: bổ sung một phương pháp dự đoán hai số cuối giải đặc biệt khác về cơ chế học so với `frequency_ensemble_v1`, giữ các lựa chọn Top 60/65/70/75/80 và theo dõi hai mô hình trên cùng các kỳ quay. Nghiên cứu và chốt kế hoạch trước; giao diện, màu sắc riêng cho từng trang được thực hiện sau.

## 1. Đề xuất chính

Chọn **Logistic Regression đa lớp có regularization L2, học riêng hàng chục và hàng đơn vị**, mã đề xuất `factorized_logistic_v1`, làm mô hình B. Mô hình A là `frequency_ensemble_v1` hiện tại.

A xếp hạng bằng tần suất có làm trơn trên nhiều cửa sổ. B học các hệ số liên hệ giữa thông tin biết trước kỳ quay và chữ số kết quả, bằng tối ưu hàm mất mát. B không nhận bảng xếp hạng, điểm số hoặc danh sách chọn của A làm đầu vào. Hai mô hình dùng cùng dữ liệu kết quả chuẩn nhưng tạo dự đoán độc lập.

Đây là ứng dụng một thuật toán học máy đã có, không phải phát minh toán học mới, cũng chưa phải phương pháp đã được chứng minh dự đoán XSMB chính xác hơn. Các nguồn nghiên cứu bên dưới hỗ trợ thuật toán và cách kiểm chứng, không chứng minh lợi thế trên xổ số.

Nếu các kết quả độc lập và đều trên 00–99, một danh sách N số khác nhau được chọn trước kỳ quay có xác suất trúng N/100, dù được chọn bằng phương pháp nào. Do đó phải kiểm tra riêng:

1. B có tốt hơn A trên cùng ngày, cùng N không?
2. B có vượt mốc N/100 không?
3. Phần trăm do B xuất ra có phù hợp với tỷ lệ quan sát không?

Không cần API key AI. Giai đoạn này sử dụng Python và mô hình thống kê chạy bằng CPU.

## 2. Những gì đã xác minh trong dự án

Code được đọc tại commit `59fe67344552801aa2a1fc4b8fbd4c6e5b5cf173`. Không thay đổi code ứng dụng trong bước lập kế hoạch.

| Thành phần | Hiện trạng đã kiểm tra | Ý nghĩa khi thêm B |
|---|---|---|
| `app/services/prediction.py` | Tần suất 30/90/180/365/toàn bộ kỳ, trọng số 35/25/20/15/5%, alpha=1 | Giữ nguyên A để làm đối chứng |
| `app/models.py` | Số lượng backend cho phép 60–80; mặc định 65 | Giữ tương thích API; giao diện tiếp tục 5 lựa chọn |
| `app/database.py` | Unique prediction theo ngày + model_version + selected_count | Đã hỗ trợ hai model khác version cùng ngày |
| `app/main.py` | Danh sách/latest predictions chưa lọc model; tạo dự đoán gọi trực tiếp A | Cần registry và lọc model trước khi mở B |
| `app/services/evaluation.py` | Đối chiếu từng prediction được; summary đang gộp theo N, chưa theo model | Bổ sung thống kê riêng và so sánh ghép cặp |
| `app/services/backtest.py` | Walk-forward đang gọi trực tiếp A | Tách engine dùng chung; nhận model/cấu hình |
| `app/services/scheduler.py`, `/api/auto-daily` | Đã có đồng bộ, đối chiếu, tạo snapshot tiếp theo | Mở rộng orchestration cho A và B |
| `app/static/app.js` | Toggle loại số gần nhất lọc hiển thị/export, không khóa chiến lược mới trên backend | Không coi danh sách đã lọc là kết quả chính thức của snapshot gốc |
| `app/services/backtest.py` | Drawdown dùng cố định thắng +350.000, thua −600.000 cho mọi N | Không dùng cột tiền này để kết luận mô hình tốt hơn |

Đã chạy `.\.venv\Scripts\python.exe -m pytest -q`: **41 test đạt**. Đây là kiểm thử hệ thống hiện có, không phải kiểm thử độ chính xác của B.

Môi trường local đang là Python `3.13.0rc2`. Khi triển khai phải xác nhận wheel/dependency phù hợp với cả local và Python trên Vercel; ưu tiên phiên bản Python ổn định được hai môi trường hỗ trợ. Chưa cài scikit-learn hoặc đổi môi trường trong bước này.

### 2.1. Dữ liệu dùng để kiểm tra sơ bộ

Đọc file có sẵn `reports/recent5_pause/input_snapshot.json`, không gọi tác vụ ghi MongoDB:

- 2.752 kỳ quan sát, từ 01/01/2019 đến 05/09/2026.
- 0 ngày trùng, 0 `last_two` sai định dạng hai chữ số, 0 bản ghi có trạng thái conflict.
- Có 53 ngày lịch không có bản ghi trong khoảng trên. Chưa xác định từng ngày là nghỉ quay hay thiếu thu thập; không tự điền kết quả.
- SHA-256 file: `8078474323e36520602e02a86692db7d73ff7bbd434f28e09ec8ca084c13ef37`.
- File chỉ chứa ngày, hai số cuối và trạng thái; chưa đủ chứng cứ nguồn/giờ thu thập cho một phép tái dựng dữ liệu thực sự có sẵn tại từng thời điểm lịch sử.

Đây là snapshot cũ đến 05/09, không phải xác nhận MongoDB/production đã có dữ liệu đến 22/09. Trước thử nghiệm B sẽ tạo một snapshot mới, có thông tin nguồn và checksum; kết quả hai snapshot phải ghi riêng.

### 2.2. Chạy lại A trên snapshot này

Mỗi ngày gọi hàm `rank_numbers` hiện tại chỉ với các kỳ trước ngày đó; bỏ 365 kỳ đầu để warm-up. Xếp hạng đủ 100 số một lần, đánh giá tất cả N từ cùng thứ hạng. Không sử dụng loại số gần nhất hoặc quy tắc nghỉ sau khi sai.

| N | Trúng / 2.387 kỳ | Hit rate A | Baseline | Chênh lệch, điểm % |
|---|---:|---:|---:|---:|
| 60 | 1.384 | 57,98% | 60% | −2,02 |
| 65 | 1.509 | 63,22% | 65% | −1,78 |
| 70 | 1.637 | 68,58% | 70% | −1,42 |
| 75 | 1.763 | 73,86% | 75% | −1,14 |
| 80 | 1.890 | 79,18% | 80% | −0,82 |

Khoảng kiểm tra: 05/01/2020–05/09/2026. Với Top 65, Wilson CI 95% là 61,26%–65,13%. Log loss trung bình 4,66805016; multiclass Brier dạng tổng 0,99134974. Phân phối đều có log loss ln(100) ≈ 4,60517019 và Brier 0,99; hai chỉ số này càng thấp càng tốt.

Trong **365 kỳ quan sát cuối**, 02/09/2025–05/09/2026, A Top 65 đạt 213/365 = 58,36%. Đây không phải đúng 365 ngày lịch. Kết quả giúp xác định mốc hiện trạng, chưa phải bảng A/B: phải chạy lại A trên chính các ngày đủ điều kiện kiểm tra của B trước khi so sánh.

Các con số trên được tính lại trong phiên lập kế hoạch, không sao chép tỷ lệ của các nghiên cứu loại trừ trước đây. B chưa có hit rate, runtime hoặc kết quả backtest để công bố.

## 3. Các phương pháp đã tìm hiểu

| Phương pháp | Cơ chế khác A | Đánh giá cho dữ liệu hiện có | Quyết định |
|---|---|---|---|
| Logistic Regression đa lớp, tách hai chữ số | Học phân phối có điều kiện từ đặc trưng quá khứ | Ít lớp hơn softmax trực tiếp 100 lớp, kiểm soát độ phức tạp bằng L2 | B ưu tiên |
| Markov bậc 1 có làm trơn | Học xác suất chuyển từ kết quả trước sang kết quả sau | Bảng 100×100 có 10.000 ô, trong khi chỉ khoảng 2.751 chuyển tiếp; rất thưa | Đối chứng nghiên cứu đơn giản, chưa mở trang riêng |
| CatBoost nhỏ | Cây boosting học tương tác phi tuyến và biến phân loại | Có thể kiểm tra tín hiệu B tuyến tính bỏ sót; tăng số lần thử và chi phí triển khai | Thử giai đoạn sau, với protocol riêng |
| Thay trọng số tần suất/loại 5–10 số gần nhất | Vẫn dựa vào tần suất hoặc luật hậu xử lý | Không đáp ứng đầy đủ mục tiêu một cơ chế học khác | Giữ là chiến lược phụ, không gọi là B mới |

Theo tài liệu scikit-learn, Logistic Regression đa lớp hỗ trợ regularization và xác suất cho các lớp [S1]. Markov biểu diễn phụ thuộc qua ma trận chuyển tiếp; giả định Markov cần được kiểm chứng trên bài toán cụ thể [S2]. CatBoost của Prokhorenkova và cộng sự đề xuất ordered boosting và xử lý biến phân loại để giảm một dạng rò rỉ nhãn [S3]. Những mô tả này không phải bằng chứng chúng dự đoán được XSMB.

LSTM/Transformer không nằm trong phạm vi v1: hiện chỉ có một kết quả mỗi kỳ, ít mẫu và chưa có bằng chứng tín hiệu thời gian. Đây là lựa chọn kỹ thuật của dự án, không phải khẳng định mạng sâu luôn kém hơn. Không hồi quy trực tiếp giá trị 00–99 như số liên tục vì khoảng cách số học không phải mục tiêu cần dự đoán.

## 4. Đặc tả thuật toán B

### 4.1. Đầu vào và đầu ra

Tại kỳ t, dùng `last_two` của ba kỳ hợp lệ trước đó; tách thành hàng chục/hàng đơn vị. Các chữ số được mã hóa one-hot, không hiểu chữ số 9 là có tác động gấp 9 lần chữ số 1.

Đặc trưng v1 cố định:

- Hàng chục và hàng đơn vị tại lag 1, 2, 3: 6 biến phân loại × 10 giá trị = 60 chiều.
- Thứ trong tuần của ngày dự đoán: 7 chiều, là thông tin đã biết trước.
- Khoảng cách ngày lịch từ kỳ trước đến ngày dự đoán: chặn tại 31 và chia 31, thêm 1 chiều.
- Tổng 68 chiều; intercept do mô hình học. Thứ trong tuần chỉ là giả thuyết thử nghiệm, chưa coi là quy luật.

Lag là **kỳ quan sát trước**, không phải tự động ngày t−1 trên lịch. Chỉ nhãn của các kỳ trước t được dùng để fit. Ba kỳ đầu chưa đủ lag được bỏ khỏi tập mẫu có nhãn; không điền số 00 thay cho dữ liệu thiếu.

Hai bộ phân loại 10 lớp dùng cùng X:

`p_chuc(a | X_t) = softmax(W_chuc X_t + b_chuc)[a]`

`p_don_vi(b | X_t) = softmax(W_don_vi X_t + b_don_vi)[b]`

Ghép thành 100 xác suất:

`p(10a+b | X_t) = p_chuc(a | X_t) * p_don_vi(b | X_t)`.

Đây là giả định độc lập có điều kiện giữa hai chữ số trong cùng kỳ. Nó giúp giảm độ phức tạp nhưng có thể bỏ sót tương tác. Nếu cần kiểm tra mô hình `P(chục|X) × P(đơn vị|chục,X)`, đó là một phiên bản/thử nghiệm mới, không âm thầm đổi B sau khi thấy kết quả.

Chuẩn hóa để tổng xác suất bằng 1; dùng epsilon cố định 1e−12 trước khi tính log loss. Bảng điểm hiển thị là xác suất **ước lượng của mô hình**, chưa được chứng minh là xác suất thực đã hiệu chỉnh.

Sắp xếp điểm giảm dần, hòa điểm theo chuỗi `00` đến `99`; lấy Top N. Một lần tính 100 điểm phục vụ cả năm lựa chọn N, không fit lại chỉ vì đổi N.

### 4.2. Huấn luyện và phạm vi dò tham số

- Multinomial logistic, L2, solver `lbfgs`, tối đa 1.000 vòng lặp, tolerance 1e−6; không `class_weight=balanced` để tránh chủ động đổi phân phối mục tiêu.
- C ∈ {0,01; 0,1; 1}. C nhỏ tương ứng co hệ số mạnh hơn [S1].
- Cửa sổ fit ∈ {730 mẫu có nhãn gần nhất; toàn bộ quá khứ đủ điều kiện}.
- Tổng **6 cấu hình B**; cố định đặc trưng, không đồng thời dò thêm hàng chục luật loại trừ.
- Chọn cấu hình bằng log loss 100 lớp trung bình ở validation nội bộ; không chọn theo ngày cuối hoặc N đang có hit rate đẹp nhất.
- Nếu log loss lệch dưới 1e−6: ưu tiên C nhỏ, sau đó cửa sổ 730 mẫu để quyết định có thể tái lập.
- Tối thiểu 730 mẫu có nhãn sau khi tạo lag, đủ cả 10 nhãn cho mỗi đầu. Nếu thiếu điều kiện, trả `insufficient_training_data` thay vì giả mạo dự đoán B bằng A.
- Không hội tụ, NaN, xác suất sai hoặc thiếu lớp: ghi `model_error`, lưu lỗi và không đưa ngày đó vào cặp A/B hợp lệ. Đồng thời tính vào tỷ lệ thiếu dự đoán để không che giấu vấn đề vận hành.

Các giá trị trên là cấu hình đề xuất phải khóa vào manifest trước khi chạy, chưa phải kết quả đã tối ưu. Phiên bản thư viện cụ thể được chốt khi xác minh compatibility, không tự dựa vào phiên bản mới nhất.

## 5. Quy trình kiểm chứng

### 5.1. Ba đối chứng bắt buộc

1. A nguyên trạng `frequency_ensemble_v1`.
2. B `factorized_logistic_v1`.
3. Phân phối đều: p=0,01 cho mỗi số; baseline hit=N/100.

Có thể thêm danh sách ngẫu nhiên có seed cố định để minh họa biến động, nhưng kết luận không phụ thuộc một seed may mắn. Mô hình một chữ số cuối không nằm trong bảng so sánh hai số cuối vì khác bài toán.

### 5.2. Walk-forward có lựa chọn tham số lồng bên trong

Theo nguyên tắc rolling origin, một dự đoán chỉ được dùng các quan sát trước kỳ kiểm tra [S4]. Lựa chọn tham số và đánh giá cuối phải tách ra để hạn chế điểm số lạc quan do chọn mô hình trên chính tập test [S5].

Quy trình đề xuất:

1. Đóng băng snapshot, checksum, code revision, feature specification, grid 6 cấu hình và danh sách kỳ.
2. Khi có ít nhất 1.003 kỳ lịch sử hợp lệ: tạo được 1.000 mẫu có nhãn sau khi bỏ 3 lag đầu.
3. Lấy 270 mẫu có nhãn cuối của phần quá khứ làm ba block validation 90 kỳ. Trước dự đoán validation đầu tiên còn tối thiểu 730 mẫu fit.
4. Trong mỗi cấu hình, dự đoán từng kỳ validation và refit theo đúng dữ liệu đã có trước kỳ đó. Chọn C/cửa sổ theo log loss gộp 270 kỳ.
5. Khóa C/cửa sổ cho block test ngoài tiếp theo gồm 90 kỳ. Vẫn cập nhật hệ số từng ngày bằng dữ liệu quá khứ; không chọn lại C bằng kết quả trong block đang chạy.
6. Đến biên block mới, lặp lại việc chọn cấu hình chỉ với phần quá khứ lúc đó. Kết quả block đã qua được phép trở thành lịch sử cho quyết định tương lai.
7. A cũng dự đoán chính các ngày test ngoài này. Chạy cả Top 60/65/70/75/80 từ cùng ranking mỗi ngày.
8. Giữ block cuối ngắn hơn 90 kỳ nếu có; ghi rõ số kỳ thay vì bỏ để làm đẹp kết quả.

Như vậy bảng A/B có warm-up dài hơn bảng kiểm tra A ở mục 2.2. Không lấy tỷ lệ của hai bảng khác thời gian để tuyên bố B thắng A. Nested backtest đánh giá một **quy trình chọn cấu hình**, không chứng minh rằng một bộ C cố định sẽ đạt y hệt.

Lịch sử từng được xem trong các nghiên cứu trước không được gọi là “holdout hoàn toàn chưa đụng đến”. Toàn bộ backtest đó là nghiên cứu lịch sử; cần dữ liệu tương lai để xác nhận độc lập.

### 5.3. Đánh giá tương lai được khóa trước

- Chốt một cấu hình B bằng validation trước ngày bắt đầu, giữ nguyên đặc trưng, C, cửa sổ, quy tắc refit hằng ngày và tiêu chí kết luận.
- Ngày bắt đầu là ngày cả hai snapshot đầu tiên được khóa hợp lệ trước hạn dự đoán; không mặc định lấy 22/09 nếu chưa triển khai.
- Chỉ tiêu chính: Top 65 vì đây là lựa chọn mặc định hiện tại. Top 60/70/75/80 là chỉ tiêu phụ; không đổi chỉ tiêu chính sau khi thấy kết quả.
- Theo dõi tối thiểu 365 **kỳ ghép cặp hợp lệ**; đặt thêm mốc kiểm tra vận hành tại 365 kỳ thực tế và thời hạn 450 ngày lịch. Nếu đến hạn chưa đủ cặp, ghi chưa đủ dữ liệu; không kéo dài vô hạn đến khi thắng.
- Dashboard được cập nhật mô tả hằng ngày. Kết luận xác nhận chỉ tại mốc đã khóa, không dừng khi p-value vừa xuống dưới 0,05.
- 365 kỳ không bảo đảm phân biệt được lợi thế nhỏ. Với p≈65%, sai số chuẩn xấp xỉ cho CI 95% là ±4,9 điểm % ở 365 kỳ; cần tính power theo chênh lệch mục tiêu và mức bất đồng A/B trước khi yêu cầu phát hiện lợi thế 1–2 điểm %.
- Chỉ thay đổi phiên bản bằng experiment mới. Việc fit lại hệ số theo protocol đã khóa là bình thường; thay feature/hyperparameter/quy tắc chọn số là thay phương pháp.

### 5.4. Ghép cặp và thống kê

Mỗi cặp phải cùng ngày dự đoán, cùng N, cùng chiến lược chọn, cùng snapshot lịch sử đầu vào và đều được khóa trước hạn. Với A dùng toàn lịch sử, B có thể chỉ fit 730 mẫu theo cấu hình, nhưng phải nhận cùng tập thông tin sẵn có ban đầu; lưu riêng hash tập đầu vào và hash tập thực sự fit.

| Chỉ số | Mục đích |
|---|---|
| Số kỳ đủ điều kiện, số cặp, thiếu A, thiếu B, khóa muộn | Tránh ẩn các ngày vận hành thất bại |
| Hit rate A/B, baseline N/100 | Kết quả cơ bản của cùng kỳ, cùng N |
| Delta B−A, tính bằng điểm phần trăm | Không nhầm cải thiện tương đối với chênh lệch tuyệt đối |
| A đúng/B sai; A sai/B đúng; cả hai đúng; cả hai sai | Kiểm tra lợi thế ghép cặp |
| Wilson CI cho hit rate; CI cho delta ghép cặp | Thể hiện bất định, không kết luận qua số % đơn lẻ |
| Log loss và Brier dạng tổng trên 100 lớp | Đánh giá toàn phân phối, không chỉ danh sách Top N [S6] |
| Trung bình tổng điểm Top N so với hit rate thực | Kiểm tra mức tự tin, không gọi tổng điểm là độ chính xác đã được chứng minh |
| Chuỗi sai dài nhất, báo cáo theo năm/tháng | Mô tả sự ổn định; không chọn riêng tháng tốt |
| Độ trùng danh sách A/B | Xem mô hình có thực sự tạo lựa chọn khác; không phải bằng chứng chính xác |

McNemar exact dùng các kỳ A/B bất đồng để kiểm tra khác biệt tỷ lệ trên dữ liệu ghép cặp [S7]. Wilson, binomial và McNemar thông thường có giả định về sự độc lập giữa các kỳ; không dùng máy móc nếu chuỗi còn phụ thuộc thời gian.

Đề xuất bổ sung paired moving-block bootstrap: 10.000 lần, block chính 7 kỳ, sensitivity 30 kỳ, seed cố định; resample cả vector kết quả A/B cùng nhau. Báo CI 95% của delta và của lift so baseline. Kết quả nhạy với block length hoặc không phù hợp giả định phải ghi “chưa đủ bằng chứng”, không chọn cấu hình CI thuận lợi hơn.

Gia đình kiểm định chính có hai so sánh Top 65: B−A và B−baseline. Dùng điều chỉnh Holm cho các p-value chính phù hợp giả định; tám kiểm định phụ ở bốn N khác thành nhóm riêng [S8]. Không coi các N từ cùng ranking là các thí nghiệm độc lập. Các CI trình bày riêng là CI từng chỉ số, không tự gọi chúng là CI đồng thời.

Mức kết luận phải tách bạch:

- **B có hit rate quan sát cao hơn A:** chỉ là mô tả số liệu.
- **Có bằng chứng B tốt hơn A:** cần chênh lệch dương, kiểm định/CI phù hợp protocol và dữ liệu xác nhận đủ điều kiện.
- **Có bằng chứng vượt baseline:** cần kiểm tra riêng B−N/100, không suy ra từ việc thắng A.
- **Chưa đủ bằng chứng:** kết luận hợp lệ nếu CI còn chứa 0 hoặc dữ liệu chưa đủ. Không tiếp tục dò tham số trên cùng tập xác nhận để ép thành kết quả thắng.

Không dùng giả thuyết “hai mô hình cùng chọn thì chắc hơn”. Giao/hợp hai danh sách làm đổi N và baseline; nếu nghiên cứu phải là chiến lược thứ ba được khóa riêng.

## 6. Kiến trúc tích hợp dự kiến

### 6.1. Chia trách nhiệm

| File/module dự kiến | Trách nhiệm |
|---|---|
| `app/services/predictors/base.py` | Hợp đồng fit/predict 100 xác suất, thông tin phiên bản |
| `app/services/predictors/registry.py` | Danh sách model hợp lệ, bật/tắt B, default A |
| `app/services/predictors/frequency.py` | Adapter cho A, bảo toàn thứ hạng/đầu ra |
| `app/services/predictors/factorized_logistic.py` | B với feature builder và fitting |
| `app/services/prediction.py` | Điều phối ngày đích, lấy dữ liệu, khóa snapshot và idempotency |
| `app/services/comparison.py` | Ghép cặp và chỉ số A/B theo model/N/experiment |
| `app/services/backtest.py` | Engine walk-forward nhận predictor; tách tính toán khỏi ghi DB |
| `scripts/compare_two_digit_models.py` | Backtest offline, resume, xuất manifest và kết quả từng kỳ |
| `app/main.py`, `app/models.py`, `app/services/evaluation.py` | API lọc model, validation và summary |
| `app/services/scheduler.py`, `/api/auto-daily` | Tạo cả A/B từ một batch dữ liệu, log kết quả riêng |

Các đường dẫn mới là đề xuất, chưa được tạo. Phần CLI research chạy offline để tránh chạy toàn bộ nested backtest trong một request Vercel.

### 6.2. MongoDB và snapshot

Tận dụng collection `predictions` và unique index đang có: `(prediction_date, model_version, selected_count)`. Trong v1 chỉ lưu dự đoán chính thức theo chiến lược raw Top N, nên chưa cần thay unique index hay viết lại snapshot cũ.

Các trường bổ sung cho snapshot mới:

- `model_id`, `model_version`, `experiment_id`, `config_hash`, `feature_version`.
- `input_dataset_hash`, `training_dataset_hash`, `trained_through`, `training_draw_count`.
- `batch_id`, `information_cutoff_at`, `prediction_deadline_at`, `locked_at`.
- `fit_artifact_id`, `fit_duration_ms`, `strategy_id="raw_top_n_v1"`.
- `scores`, `numbers`, `selected_count`, `coverage_probability`, `evaluation` như hợp đồng hiện tại.

`model_version` bất biến cho một feature/config/protocol đã khóa; đổi C hoặc cửa sổ chính thức phải tạo version khác. `fit_artifact_id` thay đổi theo lần fit dữ liệu mới, không cần đổi version mỗi ngày. API dùng `model_id` ổn định; registry chỉ ra version đang được dùng.

Thêm `model_artifacts` để lưu hệ số, intercept, thứ tự lớp/feature, config, hash dữ liệu và phiên bản thư viện dưới dạng JSON/BSON có schema. Không lưu một file pickle tùy ý rồi nạp không kiểm chứng. Với logistic nhỏ, artifact đủ gọn để giữ cùng MongoDB; phải kiểm tra tính tương đương nếu dùng bộ suy luận thuần Python.

Thêm `model_comparison_runs` cho manifest/tóm tắt và `model_comparison_outcomes` cho từng kỳ, với khóa duy nhất `(run_id, prediction_date, selected_count)`. Không nhét toàn bộ ranking của hàng nghìn kỳ vào một document lớn. Index lịch sử và truy vấn phải có model/version/N trước khi paginate.

Snapshot legacy không đủ cutoff/batch vẫn xem được ở lịch sử, nhưng không tự gắn mác “cặp xác nhận triển vọng hợp lệ”. Nếu một snapshot đã tồn tại từ batch khác, giữ nguyên và ghi không ghép cặp được; không viết lại để tạo vẻ công bằng.

Nếu sau này biến “loại số gần nhất” thành dự đoán chính thức, phải thêm strategy identity vào khóa unique, kiểm tra dữ liệu trùng và có migration riêng. Không đổi index trong bước nghiên cứu này.

### 6.3. API và trải nghiệm tương thích

- `GET /api/models`: model, version, trạng thái, mô tả phương pháp, N hỗ trợ.
- `POST /api/predictions/generate`: thêm `model_id` tùy chọn; thiếu thì vẫn là A. Ngày tiếp tục tự chọn hôm nay/ngày mai theo kết quả và hạn khóa.
- `GET /api/predictions`, `/latest`: lọc model/version/N; default A để trang cũ không nhận nhầm B.
- `GET /api/comparisons/summary` và `/daily`: lọc experiment/N/date range, phân biệt `historical_backtest` và `prospective_locked`.
- Snapshot detail tra ID vẫn giữ model/version rõ ràng. Backtest run/list và metrics overview cũng phải lọc model; không chỉ sửa trang dự đoán.
- Model không hợp lệ trả 422; thiếu training trả trạng thái có cấu trúc; lỗi B không làm bảng A biến mất.

Giao diện sau này có trang A, trang B và trang so sánh. Cả A/B giữ lựa chọn 60/65/70/75/80, tự chọn ngày, bảng đủ 100 số, tab được chọn/bị loại, sao chép, xem lịch sử và HIT/MISS. Tiêu đề và model badge phân biệt hai trang trước; bảng màu/light/dark sẽ thiết kế ở giai đoạn giao diện theo yêu cầu.

Toggle loại số gần nhất hiện là bộ lọc xem/sao chép; khi mang sang B phải ghi rõ nó không thay snapshot được chấm điểm. Nếu yêu cầu chấm cả biến thể này, backend phải khóa danh sách sau loại trừ, xác định loại theo ngày hay kỳ, số distinct và quy tắc bù đủ N. Không hiển thị hit rate Top 65 cho một danh sách export thực tế còn 61 số.

### 6.4. Đồng bộ tự động và Vercel

Một batch chạy: đồng bộ → xác nhận kết quả → đánh giá pending của từng model → chọn ngày đích → lấy một snapshot lịch sử → tạo ranking A/B → lưu từng N → xuất trạng thái batch.

- Đề xuất tự tạo cả 5 N cho A và B, chỉ cần fit/tính ranking một lần mỗi model cho cùng batch. UI mặc định 65; mô hình một chữ số cuối giữ luồng riêng.
- Nếu hôm nay có kết quả hợp lệ, tạo ngày mai. Nếu chưa có, chỉ tạo hôm nay trước hạn khóa đã khai báo. Không lấy “DB chưa có kết quả” làm bằng chứng rằng còn trước giờ quay.
- Hạn khóa đề xuất 17:30 giờ Việt Nam, là quy tắc của thí nghiệm, không phải khẳng định giờ quay. Cron đến trễ không được điền ngược một snapshot cho hôm nay.
- Dùng lease MongoDB đang có. Batch có trạng thái từng model/N; retry chỉ hoàn thiện phần thiếu từ snapshot batch đã khóa, không đổi dữ liệu input giữa A và B.
- A thành công/B thất bại phải trả `partial_failure` và log lỗi B, không `completed` chỉ vì collector thành công. Pending của cả hai vẫn được đối chiếu khi kết quả về.
- Kết quả conflict thì chưa chấm; kết quả được sửa sau khi chấm cần revision và bản ghi đánh giá thay thế có dấu vết, không sửa predictions/numbers đã khóa.
- Mặc định nghiên cứu phương án fit logistic nhẹ ngay trong invocation với cấu hình đã khóa; không grid search tại production.
- Đo fit, cold start, sync, MongoDB và tổng invocation trên deployment thử nghiệm trước khi bật tự động. Giới hạn thời gian/gói Vercel phải đọc theo cấu hình thực tế [S9].
- Mục tiêu kỹ thuật ban đầu: fit+predict B p95 ≤10 giây, tổng cron còn ít nhất 30% dự phòng so với timeout cấu hình. Đây là tiêu chí cần đo, chưa phải hiệu năng đã đạt.
- Nếu không đạt, phương án kế tiếp là worker có lịch chạy để train/ghi artifact, Vercel chỉ đọc và suy luận. Phải chốt hạ tầng worker trước khi triển khai phương án đó; không âm thầm yêu cầu người dùng train thủ công mỗi ngày.

## 7. Kế hoạch test khi triển khai

| Nhóm | Kiểm chứng bắt buộc |
|---|---|
| Dữ liệu | Giữ `00`, không trùng ngày, loại conflict, gap không được tự điền, kiểm tra dữ liệu stale |
| Chống rò rỉ | Thêm/sửa kết quả kỳ t hoặc tương lai không làm thay dự đoán t; thêm đặc trưng/scale chỉ fit trên train |
| Categorical lag | Lag 1/2/3 đúng theo kỳ quan sát; feature schema ổn định khi một category không có trong cửa sổ |
| Xác suất | Đủ 100 số, không NaN/âm, tổng≈1, đúng ánh xạ chục/đơn vị, log loss không vô hạn |
| Chọn số | Mỗi N đủ N số khác nhau; Top 60 là tập con Top 65,... khi cùng ranking; tie-break tái lập |
| Mô hình A | Adapter mới cho kết quả giống A hiện có trên fixture cố định; không đổi version nếu không đổi thuật toán |
| Mô hình B | Synthetic có quan hệ lag rõ để xác minh pipeline học được; IID đều để phát hiện sự tự tin giả/rò rỉ, không bắt buộc mỗi seed đúng baseline tuyệt đối |
| Nested validation | Mọi train_end < target; inner không chạm outer chưa quan sát; cấu hình khóa trong block; lưu tất cả 6 cấu hình |
| Ghép cặp | Không gộp khác ngày/N/version/strategy/hash; thiếu model được đếm; kiểm tra delta và bảng bất đồng bằng fixture tính tay |
| Snapshot | Hai request đồng thời không trùng; đã khóa không đổi; retry batch giữ input; snapshot legacy không bị sửa |
| Thời gian | Trước/sau deadline, qua nửa đêm Việt Nam, DB chưa có kết quả nhưng đã qua hạn, ngày không có kỳ quay |
| Tự động hóa | Kết quả mới tạo A/B tiếp theo; lỗi B vẫn hoàn thành A và trả partial; xác thực cron và lease còn hoạt động |
| API/UI sau này | Mỗi trang đúng model; refresh/direct URL; đổi N không trộn cache; bộ lọc export không thay HIT/MISS |
| Hiệu năng | Backtest resume cùng checksum cho cùng kết quả; memory, fit runtime, Mongo reads/writes và cold start |

Mô phỏng IID phải chạy cả quy trình lựa chọn tham số, không chỉ một mô hình đã chọn. Đề xuất bắt đầu 100 chuỗi với seed đã khóa để đo chi phí và phát hiện lỗi rõ; 100 lần không đủ ước lượng chính xác sai số loại I gần 5%. Có thể mở rộng 1.000 lần offline theo ngân sách đã định trước, ghi cả số lần lẫn bất định.

Không ép test ngẫu nhiên phải cho B “không bao giờ vượt baseline”: vượt do may mắn là điều có thể xảy ra. Test phải phát hiện rò rỉ và đo mức báo thắng nhầm, không phủ nhận biến động lấy mẫu.

## 8. Trình tự thực hiện và đầu ra

| Giai đoạn | Việc làm | Điều kiện hoàn thành |
|---|---|---|
| 0 — Kế hoạch hiện tại | Audit code, nghiên cứu nguồn, chạy A làm mốc, đặc tả B/protocol | Tài liệu này; chưa có code B/UI |
| 1 — Bộ nghiên cứu offline | Dataset validator, manifest, feature builder, B, engine nested dùng chung | Test leakage/synthetic đạt; lệnh CLI tái lập, chưa ghi predictions production |
| 2 — Chạy và báo cáo | Chạy A/B/uniform cùng kỳ, 5 N, log loss/Brier, paired stats, runtime | Lưu cả kết quả tốt/xấu; kết luận có/không/chưa đủ bằng chứng |
| 3 — Tích hợp thử nghiệm | Registry, snapshot metadata, API/model filter, artifact, cron A/B, metrics | Idempotency/deadline/partial failure được test; runtime đạt trên preview |
| 4 — Trang riêng và so sánh | Dùng cùng chức năng, theme theo model, bộ lọc N/lịch sử | Kiểm tra giao diện và truy vấn đúng model; màu sắc quyết định ở bước này |
| 5 — Theo dõi kết quả mới | Khóa experiment, triển khai được xác minh, thu thập A/B tự động | Báo coverage hằng ngày; đánh giá tại mốc protocol |

Ước lượng kỹ thuật sơ bộ: 1–2 ngày cho research harness, 1–2 ngày chạy/đọc kết quả tùy runtime, 2–3 ngày tích hợp backend và kiểm thử vận hành; UI tính riêng sau khi thống nhất. Đây không bao gồm thời gian chờ 365 kỳ thực tế và không phải cam kết hiệu năng trước benchmark.

Các artifact dự kiến của một lần chạy:

- `manifest.json`: dữ liệu/hash, git revision, phiên bản thư viện, grid, feature/validation protocol, seed.
- `candidate_validation.jsonl`: cả 6 ứng viên và kết quả từng block.
- `daily_predictions.jsonl`: 100 xác suất, ngày, model, cutoff, hash và training metadata.
- `daily_comparison.csv`: cùng kỳ, cùng N, actual, HIT/MISS A/B, trạng thái thiếu/lỗi.
- `summary.json`, `report.md`: hit rate, baseline, CI, paired delta, log loss/Brier và thời gian chạy.
- `data_quality.json`: gap, trùng, conflict, dữ liệu không hợp lệ và thời điểm có dữ liệu.

Sau giai đoạn 2, nếu B kém hơn hoặc chưa rõ, vẫn có thể giữ trang B mang nhãn “thử nghiệm” để theo dõi tương lai. Không tự thay A bằng B và không bỏ kết quả âm. Mục tiêu hoàn thành là có hệ thống kiểm chứng đáng tin, không bắt buộc tìm được thuật toán thắng.

## 9. Nguồn tham khảo đã tra cứu

Ngày truy cập: 22/09/2026. Nguồn hỗ trợ phương pháp, không phải chứng nhận tỷ lệ thắng XSMB.

- **[S1] scikit-learn — LogisticRegression.** Tài liệu thuật toán, regularization, solver và xác suất đa lớp: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
- **[S2] Cosma Shalizi, Carnegie Mellon — Markov Chains I (2020).** Giả định Markov và ma trận chuyển tiếp: https://stat.cmu.edu/~cshalizi/dst/20/lectures/18/lecture-18.html
- **[S3] Liudmila Prokhorenkova, Gleb Gusev, Aleksandr Vorobev, Anna Veronika Dorogush, Andrey Gulin — CatBoost: unbiased boosting with categorical features, NeurIPS 2018.** https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html
- **[S4] Rob J. Hyndman và George Athanasopoulos — Forecasting: Principles and Practice, mục 5.10.** Kiểm tra theo rolling origin: https://otexts.com/fpp3/tscv.html
- **[S5] scikit-learn — Nested versus non-nested cross-validation.** Tách chọn tham số và đánh giá; dự án áp dụng nguyên tắc này với split theo thời gian, không sao chép random K-fold của ví dụ: https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html
- **[S6] Tilmann Gneiting và Adrian E. Raftery — Strictly Proper Scoring Rules, Prediction, and Estimation, JASA 2007.** Nền tảng đánh giá dự báo xác suất: https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf
- **[S7] statsmodels — McNemar test.** Kiểm định ghép cặp, phiên bản exact dựa trên binomial: https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
- **[S8] statsmodels — Multiple testing corrections.** API điều chỉnh Holm và các phương pháp khác: https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
- **[S9] Vercel — Functions Limits.** Đối chiếu giới hạn deployment trước khi quyết định fit trong request: https://vercel.com/docs/functions/limitations

Các lựa chọn đặc trưng 68 chiều, grid 6 cấu hình, block 90 kỳ, Top 65 chính, mốc 365 kỳ, benchmark 10 giây và schema MongoDB là thiết kế đề xuất riêng cho dự án. Không gán các lựa chọn đó thành khuyến nghị nguyên văn hoặc kết quả thực nghiệm của các tác giả nguồn.
