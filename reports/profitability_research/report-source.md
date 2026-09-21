# Kế hoạch nghiên cứu tối ưu lợi nhuận dàn 60 và 80 số

**Ngày:** 05/09/2026  
**Phạm vi dữ liệu:** XSMB hai số cuối, 01/01/2019–05/09/2026  
**Mức tiền mô phỏng:** 10.000 đồng mỗi số; trúng nhận tổng cộng 999.000 đồng  
**Trạng thái:** Kế hoạch nghiên cứu; chưa chứng minh có lợi thế sinh lời tương lai

## Kết luận điều hành

Trong lưới chiến lược đã chạy, ứng viên tốt nhất về lợi nhuận tuyệt đối ở 361 kỳ quan sát gần nhất là **dàn 60, loại 40 số khác nhau vừa xuất hiện, tham gia mỗi kỳ**: đúng 234/361 (64,82%), lãi mô phỏng 17.166.000 đồng, ROI 7,93%, drawdown tối đa 4.824.000 đồng. Ứng viên tốt nhất về ROI là **dàn 60, loại 38 số khác nhau vừa xuất hiện, nghỉ sau một kỳ sai và chỉ tham gia lại sau một kỳ theo dõi đúng**: 154/232 lần tham gia đúng (66,38%), lãi 14.646.000 đồng, ROI 10,52%, drawdown 4.410.000 đồng.

Dàn 80 tốt nhất trong cùng cửa sổ là **loại 20 số vừa xuất hiện và tham gia mỗi kỳ**: đúng 300/361 (83,10%), lãi 10.900.000 đồng, ROI 3,77%, drawdown 3.455.000 đồng. Vì vậy, dữ liệu gần nhất ưu tiên dàn 60 nếu mục tiêu là lợi nhuận tuyệt đối hoặc ROI, còn dàn 80 dùng nhiều vốn hơn để đổi lấy biến động thấp hơn.

Các kết quả này là **thăm dò**. Lưới loại trừ và dữ liệu đã được xem nhiều lần; p-value hoặc khoảng tin cậy thông thường của phương án thắng cuộc không sửa được thiên lệch chọn mô hình. White chỉ ra rằng dùng lại cùng dữ liệu cho lựa chọn mô hình và suy luận có thể tạo kết quả đẹp do may mắn; phương pháp Reality Check kiểm định mô hình tốt nhất trong cả tập ứng viên so với chuẩn [1]. Do đó chưa có cơ sở chuyển kết quả trên thành lời hứa “không lỗ”.

## 1. Bài toán kinh tế phải tối ưu

Với dàn N số, lợi nhuận một kỳ tham gia là:

`Lợi nhuận = 999.000 × H − 10.000 × N`, với `H = 1` nếu trúng và `0` nếu sai.

Điểm hòa vốn là 60,0601% cho dàn 60 và 80,0801% cho dàn 80. Nếu hai dàn dùng cùng thứ hạng và dàn 80 chứa dàn 60, chỉ nên mua thêm 20 số khi xác suất thật cộng thêm của chúng vượt 200.000 / 999.000 = 20,0200%.

Mục tiêu chọn mô hình là **lợi nhuận trung bình trên mỗi kỳ quan sát**, trong đó ngày nghỉ ghi 0 đồng. ROI, hit rate, số kỳ tham gia, drawdown tối đa và chuỗi thua là chỉ số phụ. Cách này ngăn một quy tắc nghỉ rất nhiều ngày trông tốt chỉ vì mẫu số nhỏ.

## 2. Dữ liệu và phép thử đã thực hiện

- Snapshot có 2.752 kết quả hợp lệ từ 01/01/2019 đến 05/09/2026; 53 ngày lịch không có kết quả trong nguồn và không được tự điền.
- SHA-256 của snapshot: `8078474323e36520602e02a86692db7d73ff7bbd434f28e09ec8ca084c13ef37`.
- Mỗi dự đoán chỉ dùng dữ liệu đứng trước ngày cần dự đoán. 365 kết quả đầu làm lịch sử tối thiểu; còn 2.387 kỳ walk-forward từ 05/01/2020.
- Lưới cố định trong lần chạy này: dàn 60 với K = 0, 5, 10, 20, 30, 38, 40; dàn 80 với K = 0, 5, 10, 20; mỗi cấu hình chạy hằng ngày và chạy với quy tắc nghỉ sau sai.
- “Loại K” là bỏ K số **khác nhau** xuất hiện gần nhất, rồi lấy các số có thứ hạng tiếp theo cho đủ N số. K = 40, N = 60 nghĩa là lấy toàn bộ 60 số chưa nằm trong nhóm 40 số gần nhất.

## 3. Kết quả thăm dò

### 3.1 Cửa sổ 361 kỳ quan sát gần nhất

| Chiến lược | Đúng / cược | Tỷ lệ | Lãi ròng | ROI | Drawdown tối đa |
|---|---:|---:|---:|---:|---:|
| 60 số, loại 40, mỗi kỳ | 234 / 361 | 64,82% | +17.166.000 | 7,93% | 4.824.000 |
| 60 số, loại 38, nghỉ sau sai | 154 / 232 | 66,38% | +14.646.000 | 10,52% | 4.410.000 |
| 60 số, loại 38, mỗi kỳ | 231 / 361 | 63,99% | +14.169.000 | 6,54% | 6.228.000 |
| 80 số, loại 20, mỗi kỳ | 300 / 361 | 83,10% | +10.900.000 | 3,77% | 3.455.000 |
| 80 số, loại 20, nghỉ sau sai | 251 / 301 | 83,39% | +9.949.000 | 4,13% | 5.015.000 |
| Top 60 hiện tại, mỗi kỳ | 191 / 361 | 52,91% | −25.791.000 | −11,91% | 28.173.000 |
| Top 80 hiện tại, mỗi kỳ | 277 / 361 | 76,73% | −12.077.000 | −4,18% | 16.924.000 |

Nếu giả sử đây là **một** chiến lược đã được khóa trước và các lần trúng phù hợp giả định Bernoulli, dàn 60 loại 40 có p-value nhị thức một phía khoảng 0,0358. Nhưng phương án này được chọn sau khi so sánh nhiều K, N và quy tắc tham gia, nên con số đó không phải p-value xác nhận.

### 3.2 Toàn bộ 2.387 kỳ walk-forward

| Chiến lược | Đúng / cược | Tỷ lệ | Lãi ròng | ROI | Drawdown tối đa |
|---|---:|---:|---:|---:|---:|
| 60 số, loại 38, nghỉ sau sai | 883 / 1.446 | 61,07% | +14.517.000 | 1,67% | 29.967.000 |
| 60 số, loại 38, mỗi kỳ | 1.445 / 2.387 | 60,54% | +11.355.000 | 0,79% | 35.037.000 |
| 60 số, loại 40, mỗi kỳ | 1.443 / 2.387 | 60,45% | +9.357.000 | 0,65% | 34.647.000 |
| 80 số, loại 20, mỗi kỳ | 1.905 / 2.387 | 79,81% | −6.505.000 | −0,34% | 33.588.000 |
| Top 60 hiện tại, mỗi kỳ | 1.384 / 2.387 | 57,98% | −49.584.000 | −3,46% | 64.674.000 |
| Top 80 hiện tại, mỗi kỳ | 1.890 / 2.387 | 79,18% | −21.490.000 | −1,13% | 33.121.000 |

Kết quả 60/38/nghỉ không ổn định: lỗ trong 2020–2023 và có lãi trong 2024–2026. Khoảng Wilson 95% toàn kỳ cho hit rate của nó là 58,53–63,55%, vẫn chứa mốc hòa vốn 60,0601%; kiểm định nhị thức một phía chưa hiệu chỉnh có p ≈ 0,226. Mẫu gần đây có thể là thay đổi chế độ hoặc dao động ngẫu nhiên; dữ liệu hiện tại chưa phân biệt được hai khả năng.

Một mô phỏng chọn chiến lược bằng dữ liệu các năm trước rồi áp dụng cho năm kế tiếp chọn “không tham gia” cho 2024 và 2025; đến 2026 mới chọn 60/38/nghỉ và tạo lãi mô phỏng 9.894.000 đồng trên 160 lần tham gia. Đây vẫn là tái dựng sau khi lịch sử đã được nghiên cứu, không phải holdout sạch.

## 4. Cách hiểu phương pháp loại trừ

Nghiên cứu về hành vi người chơi xổ số cho thấy người chơi có xu hướng tránh số vừa ra; điều đó không biến lượt quay độc lập thành quy luật “số vừa ra ít có khả năng ra lại” [2]. Vì thế, loại số gần đây phải được xem như một giả thuyết dữ liệu, không phải nguyên lý xác suất.

Với một phân phối xác suất đã ước lượng đúng, chọn N số có xác suất cao nhất tối đa hóa lợi nhuận kỳ vọng. Cách loại trừ tốt nhất khi đó chính là loại các số có xác suất thấp nhất. Kế hoạch mới sẽ biến “độ gần đây” thành đặc trưng hoặc mức phạt được học có regularization; K = 38 và 40 vẫn được giữ làm hai đối chứng cố định vì chúng dẫn đầu trong lần thăm dò.

## 5. Danh mục thuật toán nghiên cứu

### 5.1 Đối chứng bắt buộc

1. Phân phối đều 1% cho mỗi số và không tham gia, lợi nhuận 0.
2. `frequency_ensemble_v1` hiện tại.
3. 60/38/nghỉ, 60/40/mỗi kỳ và 80/20/mỗi kỳ, đóng băng đúng định nghĩa đã chạy.

### 5.2 Mô hình ưu tiên

1. **Bayesian frequency có co về đều.** Với mỗi số j: `p(j) = (count(j) + A/100) / (n + A)`. Dirichlet là prior liên hợp của multinomial, và posterior được cập nhật bằng cách cộng số quan sát [3]. Chỉ thử một lưới nhỏ A và một số half-life đã đăng ký trước.
2. **Mô hình tách hàng chục và hàng đơn vị.** Trộn xác suất 100 lớp trực tiếp với tích hai phân phối 10 lớp: `p(a,b) = λ p_direct(a,b) + (1−λ) p_tens(a)p_units(b)`. Cách này giảm độ thưa nhưng không ép hai chữ số độc lập hoàn toàn.
3. **Markov bậc một có co mạnh.** Ma trận 100×100 có 10.000 ô trong khi chỉ có khoảng 2.751 chuyển tiếp; trung bình khoảng 27 quan sát cho mỗi trạng thái trước. Mỗi hàng phải co về phân phối nền. Không thử Markov bậc cao ở giai đoạn đầu.
4. **Gradient boosting nhỏ.** Dùng một thư viện, độ sâu thấp và ngân sách tham số cố định. Nghiên cứu benchmark trên dữ liệu bảng cho thấy mô hình cây là đối chứng mạnh trên các bộ dữ liệu cỡ trung bình, nhưng kết quả đó không chứng minh hiệu quả trên xổ số [4].
5. **TabPFN-3 như một challenger duy nhất.** Báo cáo kỹ thuật 2026 công bố kết quả mạnh trên benchmark dữ liệu bảng nhiều lớp [5], và tài liệu nhà cung cấp nêu giới hạn 160 lớp, đủ cho 100 nhãn [6]. Đây là ứng viên kiểm tra sau, không phải bằng chứng xổ số có tín hiệu.

Không ưu tiên LSTM hoặc Transformer tự huấn luyện: 2.752 nhãn quá ít so với độ linh hoạt của mô hình và chi phí thử tham số. Chúng chỉ được đưa vào khi các kiểm định phụ thuộc thời gian cho thấy tín hiệu ổn định và có ngân sách dữ liệu lớn hơn.

### 5.3 Đặc trưng đã khóa

- Tần suất ở cửa sổ 30, 90, 180, 365 và toàn lịch sử.
- Tần suất suy giảm mũ với tối đa ba half-life định trước.
- Số kỳ kể từ lần xuất hiện; cờ xuất hiện trong 1, 3, 5, 10, 20, 38 và 40 số khác nhau gần nhất.
- Tần suất hàng chục, hàng đơn vị và cặp chữ số.
- Chuyển tiếp từ kết quả trước, có prior co về nền.
- Thứ/ngày chỉ làm một nhóm kiểm tra riêng; loại bỏ nếu không cải thiện outer walk-forward.

Mọi mô hình phải xuất đủ 100 xác suất có tổng bằng 1. Log score và Brier score là proper scoring rules dùng để đánh giá dự báo xác suất [7]. Hiệu chỉnh nhiệt độ dùng validation riêng có thể cải thiện xác suất báo cáo [8], nhưng vì giữ nguyên thứ hạng nên không tự tăng hit rate top 60/80; giá trị chính là hỗ trợ quyết định nghỉ.

## 6. Thiết kế kiểm định tránh tự lừa mình

1. **Sổ đăng ký thử nghiệm.** Mỗi N, K, cửa sổ, half-life, feature set, thuật toán, seed, quy tắc nghỉ và ngưỡng tham gia là một trial. Không xóa trial thua.
2. **Nested walk-forward.** Tầng trong chọn tham số chỉ bằng quá khứ; tầng ngoài tiếp theo ghi dự đoán và lợi nhuận. Tài liệu scikit-learn cảnh báo chọn tham số và đánh giá trên cùng dữ liệu tạo ước lượng quá lạc quan và hướng dẫn tách đánh giá lồng nhau; dữ liệu thời gian phải giữ thứ tự [9].
3. **Chuẩn kinh tế.** So với không tham gia = 0 đồng. So với phân phối đều để kiểm tra năng lực dự báo. Đánh bại mô hình hiện tại đang lỗ chưa đủ chứng minh có lãi.
4. **Sửa nhiều phép thử.** Chạy Reality Check của White và SPA của Hansen trên ma trận lợi nhuận cùng ngày của toàn bộ trial [1,10]. Bootstrap phải lấy cùng chỉ số ngày cho mọi chiến lược và kiểm tra độ nhạy theo độ dài khối.
5. **Mô phỏng giả thuyết không có tín hiệu.** Tạo tối thiểu 10.000 chuỗi IID đều 00–99, giữ độ dài và cấu trúc ngày thiếu, rồi chạy lại toàn bộ pipeline xây đặc trưng, chọn mô hình và đánh giá. So sánh lợi nhuận tốt nhất thật với phân phối lợi nhuận tốt nhất do tìm kiếm trên dữ liệu giả.
6. **Theo dõi tương lai.** Khóa một champion, hash cấu hình và prediction trước giờ quay. Confidence sequence có độ phủ đồng thời theo thời gian phù hợp hơn interval cố định khi theo dõi liên tục [11]. Nó không sửa được thiên lệch do chọn champion bằng dữ liệu kiểm định.

## 7. Quy tắc chọn 60 hay 80 và quyết định tham gia

Mỗi ngày, mô hình tạo p(00)…p(99), hiệu chỉnh bằng dữ liệu validation quá khứ và xếp giảm dần. Tính `q60` là tổng xác suất top 60 và `q80` là tổng xác suất top 80.

- Dàn 60 đủ điều kiện nếu cận dưới đã hiệu chỉnh của q60 vượt 0,600601 cộng biên an toàn đã khóa.
- Dàn 80 chỉ thay thế dàn 60 nếu cận dưới của `q80 − q60` vượt 0,200200 và lợi nhuận kỳ vọng trên mỗi kỳ quan sát cao hơn sau chi phí.
- Nếu không điều kiện nào đạt, hệ thống chỉ ghi prediction và không tham gia.
- Không dùng chuỗi thắng/thua riêng lẻ để đổi tiền cược. Quy tắc nghỉ chỉ tồn tại nếu vượt qua nested walk-forward và kiểm định nhiều mô hình.

Trong nghiên cứu tương lai một chiến lược cố định, 365 lần tham gia cần ít nhất 236 lần đúng cho dàn 60 hoặc 306 lần đúng cho dàn 80 để vượt hòa vốn trong kiểm định nhị thức một phía 5%, nếu các giả định Bernoulli phù hợp. Đây không phải ngưỡng hợp lệ cho chiến lược được chọn sau hàng trăm phép thử. Phát hiện lợi thế thật chỉ +1 điểm phần trăm với power 80% cần xấp xỉ 14.787 lần tham gia cho dàn 60 hoặc 9.734 cho dàn 80; một năm có rất ít lực kiểm định cho lợi thế nhỏ.

## 8. Kế hoạch triển khai cụ thể

### Giai đoạn 0 — đóng băng nghiên cứu hiện tại, 1–2 ngày

- Lưu snapshot, checksum, danh sách ngày thiếu và công thức payout.
- Sửa báo cáo dashboard để luôn hiển thị lợi nhuận trên kỳ quan sát, ROI, số lần cược, drawdown và trạng thái thăm dò/xác nhận.
- Hoàn thành khi một lệnh tạo lại đúng `comparison.csv` và `results.json` từ snapshot.

### Giai đoạn 1 — pipeline xác suất và registry, 3–5 ngày

- Chuẩn hóa interface `fit(history) → p[100]`, cấm đọc kết quả cùng ngày/tương lai.
- Tạo bảng `experiment_registry`: trial_id, model, feature hash, hyperparameters, training cutoff, code commit, seed, trạng thái.
- Tạo benchmark đều, frequency hiện tại và ba chính sách loại trừ đóng băng.
- Hoàn thành khi tất cả mô hình trả 100 xác suất hợp lệ và test leakage đạt.

### Giai đoạn 2 — mô hình thống kê gọn, 1 tuần

- Cài Bayesian shrinkage, exponential decay, digit mixture và Markov co mạnh.
- Chọn tối đa 12 cấu hình trong tầng trong; không mở rộng lưới giữa chừng.
- Báo cáo log loss, Brier, top-60/top-80 hit, lãi và drawdown trên cùng outer folds.

### Giai đoạn 3 — challenger học máy, 1 tuần

- Thử một boosting cấu hình nhỏ và một TabPFN-3 nếu môi trường, giấy phép và dữ liệu cho phép.
- Fit preprocessing và calibration chỉ trong dữ liệu quá khứ của từng fold.
- Loại challenger nếu không cải thiện ổn định so với Bayesian/frequency hoặc tăng mạnh variance.

### Giai đoạn 4 — kiểm định toàn pipeline, 1–2 tuần

- Chạy nested walk-forward, Reality Check/SPA và 10.000 mô phỏng IID toàn pipeline.
- Chọn champion theo lợi nhuận trung bình trên mỗi kỳ quan sát; dùng drawdown và độ ổn định làm điều kiện phụ đã khóa.
- Xuất một model card với toàn bộ trial thắng/thua, giới hạn và phiên bản dữ liệu.

### Giai đoạn 5 — paper trading tương lai, tối thiểu 365 kỳ quan sát

- Không sửa champion, feature, K, N, ngưỡng hoặc quy tắc nghỉ trong cửa sổ xác nhận.
- Khóa prediction trước kết quả; tự động đối chiếu sau kỳ quay.
- Nếu cần thay đổi, đóng cửa sổ cũ, đăng ký phiên bản mới và bắt đầu một cửa sổ mới.

## 9. Điều kiện vượt vòng và điều kiện dừng

Champion chỉ được gắn nhãn “có bằng chứng lợi thế” khi đồng thời:

1. Lợi nhuận outer walk-forward dương so với không tham gia.
2. Kiểm định đã đăng ký trước có cận dưới một phía của lợi nhuận kỳ vọng trên 0 sau điều chỉnh tìm kiếm.
3. Reality Check/SPA hoặc mô phỏng toàn pipeline bác bỏ hợp lý việc kết quả tốt nhất chỉ do thử nhiều phương án.
4. Paper trading khóa trước đạt tiêu chí mẫu và rủi ro đã định.
5. Không có lỗi leakage, sửa dữ liệu hồi tố hoặc thay đổi payout.

Dừng hoặc quay về “chỉ theo dõi” nếu cận dưới không vượt 0, pipeline không thắng phân phối tốt nhất trên dữ liệu IID giả, drawdown vượt giới hạn đã đăng ký, hoặc lợi thế biến mất ở hai outer window liên tiếp. Kelly chỉ tối ưu mức vốn khi đã có thông tin dự đoán và odds; nó không tạo lợi thế từ một mô hình kỳ vọng âm [12]. Trong giai đoạn nghiên cứu, giữ mức mô phỏng cố định 10.000 đồng mỗi số và không gấp thếp.

## 10. Khuyến nghị hiện tại

Giữ ba ứng viên đóng băng: 60/38/nghỉ, 60/40/mỗi kỳ và 80/20/mỗi kỳ. Ưu tiên nghiên cứu **60/38/nghỉ** vì ROI toàn kỳ dương và vốn tham gia thấp hơn; dùng **60/40/mỗi kỳ** làm challenger lợi nhuận tuyệt đối gần đây; dùng **80/20/mỗi kỳ** làm đối chứng biến động thấp. Không chọn ứng viên chỉ dựa trên 361 kỳ gần nhất.

Bước triển khai có giá trị cao nhất là xây registry + nested walk-forward + mô phỏng toàn pipeline trước khi thêm mô hình phức tạp. Nếu chuỗi không chứa tín hiệu dự đoán bền vững, thuật toán mạnh hơn chỉ học nhiễu nhanh hơn.

## Nguồn

[1] Halbert White, “A Reality Check for Data Snooping,” Econometrica 68(5), 2000. https://users.ssc.wisc.edu/~behansen/718/White2000.pdf  
[2] Charles Clotfelter and Philip Cook, “The Gambler’s Fallacy in Lottery Play,” NBER Working Paper 3769, 1991; Management Science, 1993. https://www.nber.org/papers/w3769  
[3] Stan User’s Guide 2.35, “Dirichlet-multinomial HMM — Analytic posterior.” https://mc-stan.org/docs/2_35/stan-users-guide/time-series.html#analytic-posterior  
[4] Léo Grinsztajn, Edouard Oyallon and Gaël Varoquaux, “Why do tree-based models still outperform deep learning on typical tabular data?” NeurIPS 2022. https://arxiv.org/abs/2207.08815  
[5] Grinsztajn et al., “TabPFN-3: Technical Report,” arXiv:2605.13986, revised 28/05/2026. https://arxiv.org/abs/2605.13986  
[6] Prior Labs, “REST API quickstart — model limits,” accessed 05/09/2026. https://docs.priorlabs.ai/api-reference/getting-started  
[7] Tilmann Gneiting and Adrian Raftery, “Strictly Proper Scoring Rules, Prediction, and Estimation,” JASA 102(477), 2007. https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf  
[8] Chuan Guo et al., “On Calibration of Modern Neural Networks,” ICML 2017. https://proceedings.mlr.press/v70/guo17a.html  
[9] scikit-learn, “Cross-validation: evaluating estimator performance” and nested cross-validation example, accessed 05/09/2026. https://scikit-learn.org/stable/modules/cross_validation.html  
[10] Peter R. Hansen, “A Test for Superior Predictive Ability,” Journal of Business & Economic Statistics 23(4), 2005. https://bashtage.github.io/kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Hansen.pdf  
[11] Steven Howard et al., “Time-uniform, nonparametric, nonasymptotic confidence sequences,” Annals of Statistics 49(2), 2021; revised 06/08/2022. https://arxiv.org/abs/1810.08240  
[12] John L. Kelly Jr., “A New Interpretation of Information Rate,” Bell System Technical Journal 35(4), 1956. https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x
