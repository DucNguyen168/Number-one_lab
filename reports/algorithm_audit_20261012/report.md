# Rà soát thuật toán và đối chiếu thực tế — 12/10/2026

**Kết luận: cần nâng cấp cách kiểm chứng; chưa đủ bằng chứng để thay mô hình đang chạy bằng một phiên bản được gọi là chính xác hơn.** Tần suất, Logistic và CatBoost đổi thứ tự khi đổi khoảng đánh giá. Ứng viên Logistic + Bayesian đạt 66,58% trên 365 kỳ, nhưng chỉ hơn Logistic 3 kỳ đúng, chưa xác nhận lợi thế. Đề xuất tiếp tục thử nghiệm có khóa cấu hình và dự đoán trước kỳ quay.

Đã đọc code dự đoán, đối chiếu, backtest, so sánh rolling và các báo cáo nghiên cứu cũ; lấy dữ liệu MongoDB chỉ đọc; chạy lại lịch sử và kiểm tra snapshot đã lưu. Bộ nghiên cứu mới nằm trong thư mục này. Không thay mô hình vận hành hoặc ghi lại kết quả trong MongoDB trong lần rà soát này.

## 1. Dữ liệu và phương pháp

- 2.789 kỳ quan sát, từ 01/01/2019 đến 12/10/2026; kết quả cuối: giải đặc biệt `38287`, hai số cuối `87`.
- 91 snapshot hai số, gồm 88 đã đối chiếu và 3 đang chờ; 20 snapshot một chữ số đã đối chiếu.
- Không có ngày trùng, `last_two` sai định dạng, trạng thái conflict hoặc hai số cuối mâu thuẫn với giải đặc biệt trong bản xuất.
- Có 53 ngày lịch không có bản ghi. Chưa xác minh từng ngày là nghỉ quay hay thiếu thu thập; không tự điền kết quả. “365 kỳ” là 365 quan sát, không phải 365 ngày lịch.
- Bản dữ liệu mới thêm 37 kỳ so với bản đến 05/09/2026; 2.752 kết quả trước đó không đổi.

SHA-256 dữ liệu chuẩn: `586c32ad7a0dc633fae837286f5d81b65e3162ec1698f5e168f0dc5750c50074`. SHA-256 file, thư viện, code và cấu hình nghiên cứu được lưu trong `manifest.json`.

Backtest huấn luyện lại từng kỳ, chỉ dùng kết quả có ngày trước ngày mục tiêu. Đây là cách kiểm chứng theo thời gian với cửa sổ huấn luyện mở rộng; tài liệu [Forecasting: Principles and Practice](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation) trình bày nguyên tắc chỉ dùng quá khứ cho mỗi dự báo. Tuy nhiên, dữ liệu hiện tại không tái dựng đầy đủ thời điểm từng bản ghi lịch sử được thu thập. Các thử nghiệm này là nghiên cứu trên dữ liệu đã quan sát, chưa phải tập tương lai độc lập chưa từng được xem.

Mục tiêu chính là **Top 65**, nghĩa là kết quả thực nằm trong 65 số được chọn. Nếu kết quả độc lập và đều trên 00–99, mốc tham chiếu là **65%**. Top 60/70/75/80 có mốc tương ứng 60/70/75/80%; tăng số lượng chọn tự nó tăng tỷ lệ đúng. Dự đoán một chữ số có mốc 10%.

Đã tính Wilson 95%, kiểm định nhị thức một phía so với mốc tham chiếu, McNemar ghép cặp, bootstrap theo khối 7/30 kỳ và hiệu chỉnh Holm khi thử nhiều mô hình. Những phép suy luận có giả định về tính độc lập/phụ thuộc; kết quả mẫu ngắn cần thận trọng. Không tính khoảng bootstrap 30 kỳ khi chỉ có 19 hoặc 59 quan sát. Kiểm định phân phối biên đều có p=0,741, không phát hiện mất cân bằng rõ; điều này không chứng minh các kỳ độc lập.

## 2. Toàn bộ mô hình hiện có

| Mô hình | Cơ chế đang chạy | Đánh giá và hướng xử lý |
|---|---|---|
| `frequency_ensemble_v1` | Tần suất 30/90/180/365/toàn bộ; trọng số 35/25/20/15/5%; Laplace alpha=1 | Giữ làm đối chứng đơn giản. Tỷ lệ đúng phụ thuộc giai đoạn; xác suất có dấu hiệu quá tự tin. |
| `factorized_logistic_v1` | Hai Logistic L2 cho chục/đơn vị; 3 lag one-hot, thứ trong tuần, khoảng cách ngày; 730 mẫu huấn luyện | Giữ theo dõi. Giả định tích hai phân phối chữ số cần kiểm chứng; log loss hiện kém phân phối đều trên 365 kỳ. |
| `direct_catboost_multiclass_v2_context2000` | Dự đoán trực tiếp 100 lớp; 287 đặc trưng, ngữ cảnh 2.000 kỳ; tối thiểu 730 mẫu huấn luyện; 48 cây sâu 4; trộn 15% đều | Cần 2.730 kỳ quá khứ, nên chỉ chạy được 59 kỳ kiểm chứng. Với 2.789 kỳ hiện tại, dự đoán kỳ tiếp theo chỉ có 789 mẫu huấn luyện cho 100 lớp. Chưa đủ cơ sở nâng tiếp chỉ vì mô hình phức tạp. |
| `direct_catboost_multiclass_v1` cũ | Hai snapshot Top 65 đã đối chiếu, hai `config_hash` khác nhau | Đúng 1/2 tổng cộng; mỗi cấu hình chỉ có một kỳ. Không gộp để kết luận hiệu năng một cấu hình. |
| `last_digit_frequency_ensemble_v1` | Tần suất có làm trơn trên 10 chữ số | Thực tế 0/20; loại khóa muộn còn 0/17. Mẫu quá nhỏ để khẳng định kém mốc 10%. Backtest 32/365 = 8,77%; chưa có tín hiệu để mở lại tự động. |
| Loại số mới ra, nghỉ sau khi sai và các luật nghiên cứu cũ | Hậu xử lý danh sách hoặc bỏ kỳ | Chưa có xác nhận tương lai. Nghiên cứu thử nhiều luật có nguy cơ chọn phương án tốt tình cờ; không đưa phương án thắng lịch sử vào vận hành ngay. |

Code xếp hạng đã lọc ngày mục tiêu/tương lai và loại conflict. CatBoost tạo đặc trưng từ các kỳ trước mẫu huấn luyện. Snapshot có khóa duy nhất và metadata giúp kiểm tra lại. `has_time=True` giữ thứ tự đầu vào theo [tài liệu CatBoost](https://catboost.ai/docs/en/references/training-parameters/common#has_time); tham số này không tự chứng minh có tín hiệu dự báo.

## 3. Kết quả đã lưu thực tế

Sau khi yêu cầu cùng ngày, cùng Top 65, cùng `dataset_hash`, có kết quả hợp lệ và khóa trước 17:30 theo protocol dự án, ba mô hình có **19 ngày chung: 24/09–12/10/2026**.

| Mô hình | Đúng / kỳ | Tỷ lệ đúng | Wilson 95% |
|---|---:|---:|---:|
| Tần suất | 15/19 | 78,95% | 56,67–91,49% |
| Logistic | 12/19 | 63,16% | 41,04–80,85% |
| CatBoost v2 | 15/19 | 78,95% | 56,67–91,49% |

Tần suất và CatBoost bằng số kỳ đúng; hai mô hình sai khác kết quả ở hai ngày, mỗi bên thắng một ngày, McNemar p=1. Logistic và mỗi mô hình còn lại có p=0,508. Khoảng tin cậy của cả ba đều chứa 65%. Tỷ lệ 78,95% trong mẫu này chưa xác nhận độ chính xác dài hạn.

Nếu xem từng mô hình riêng, số ngày quan sát khác nhau: Tần suất Top 65 đạt 32/43 trước lọc, còn 31/42 sau lọc; Logistic 13/21; CatBoost v2 15/19. Không dùng các tỷ lệ khác khoảng thời gian này để chọn mô hình thắng. Snapshot Top 60 hoặc Top 80 chỉ có một kỳ cũng được giữ riêng.

**Phát hiện cần xử lý:** dự đoán Tần suất cho 05/09 đã khóa lúc 18:44:31 giờ Việt Nam. Dù nhãn huấn luyện kết thúc trước ngày mục tiêu và không phát hiện lấy kết quả mục tiêu làm đầu vào, dự đoán này vẫn không đáp ứng deadline đã chọn và bị loại khỏi đánh giá đủ điều kiện. Ba snapshot chữ số cũng khóa muộn. Deadline dự đoán 17:30 khác với giờ bắt đầu cập nhật kết quả 18:30.

Đã kiểm lại kết quả thực và cờ đúng/sai của tất cả snapshot đã đối chiếu: không phát hiện mâu thuẫn. Đã chạy lại 83 snapshot Top 65 bằng dữ liệu lịch sử hiện tại: Logistic khớp 21/21 danh sách, CatBoost v2 khớp 19/19, Tần suất khớp 37/43. Sáu danh sách Tần suất cũ khác có lịch sử huấn luyện ngắn hơn, ví dụ 235 hoặc 700 kỳ; không coi chạy lại với toàn bộ dữ liệu hiện tại là tái hiện chính xác dữ liệu có sẵn lúc đó. Chi tiết nằm trong `replay_checks.json`.

## 4. Chạy lại 365 kỳ và các ứng viên mới

Khoảng chung: **09/10/2025–12/10/2026**. Cấu hình ứng viên cố định, không tìm lưới tham số; lưu cả kết quả tốt và kém. Log loss/Brier càng thấp càng tốt.

| Mô hình / ứng viên | Đúng Top 65 | Tỷ lệ | Log loss | Brier |
|---|---:|---:|---:|---:|
| Tần suất hiện tại | 220/365 | 60,27% | 4,67286 | 0,991395 |
| Logistic hiện tại | 240/365 | 65,75% | 4,69775 | 0,991835 |
| Bayesian trực tiếp, 365 kỳ | 236/365 | 64,66% | 4,61096 | 0,990107 |
| Bayesian phối hợp trực tiếp và tách chữ số | 234/365 | 64,11% | 4,61007 | 0,990090 |
| Markov bậc 1 có làm trơn mạnh | 239/365 | 65,48% | 4,63278 | 0,990661 |
| Logistic + Bayesian, mỗi bên 50% | 243/365 | **66,58%** | 4,62249 | 0,990356 |
| Logistic trộn 50% phân phối đều | 240/365 | 65,75% | 4,62087 | 0,990334 |
| Phân phối đều — mốc kỳ vọng | — | 65% | **4,60517** | **0,990000** |

Bayesian trực tiếp dùng prior đều tổng khối lượng 1.000, tương đương 10 mỗi số. Nhánh chữ số dùng prior tổng 100 trên mỗi hàng. Markov làm trơn hàng chuyển tiếp bằng 100 lần phân phối Bayesian trực tiếp. Chi tiết công thức trong script và manifest.

Logistic + Bayesian hơn Logistic **3/365 kỳ = 0,82 điểm phần trăm**; McNemar p=0,743; khoảng bootstrap 7 kỳ của chênh lệch là −2,47 đến +4,38 điểm phần trăm. Wilson của ứng viên là 61,59–71,22%; kiểm định vượt 65% có p=0,284. Tất cả bảy kiểm định Top 65 sau Holm đều có p hiệu chỉnh bằng 1. Chưa có ứng viên đạt điều kiện xác nhận vượt mốc.

Mọi mô hình xác suất trong bảng 365 kỳ đều có log loss và Brier kém phân phối đều. Trộn đều làm xác suất Logistic bớt cực đoan và cải thiện hai chỉ số, nhưng giữ nguyên thứ hạng nên **không tăng tỷ lệ đúng**. Theo [scikit-learn về calibration](https://scikit-learn.org/stable/modules/calibration.html), bộ hiệu chỉnh cần được fit trên dữ liệu độc lập với dữ liệu huấn luyện mô hình; log loss/Brier còn phản ánh nhiều khía cạnh ngoài calibration. Chưa fit calibrator từ chính tập kiểm tra này.

Báo cáo cũ đến 05/09 có Logistic 243/365 và Tần suất 213/365, McNemar p=0,01995. Khi cập nhật cửa sổ, Logistic còn 240/365, Tần suất 220/365, p=0,133. Các cửa sổ chồng lặp phần lớn nên không phải hai thử nghiệm độc lập; sự thay đổi cho thấy chưa nên suy rộng kết quả tốt của một giai đoạn.

### CatBoost: so trên đúng 59 kỳ đủ điều kiện

Không rút ngắn ngữ cảnh v2 để tạo ra một backtest 365 kỳ không đúng cấu hình đang chạy. Trên **15/08–12/10/2026**:

| Mô hình | Đúng Top 65 | Tỷ lệ | Log loss |
|---|---:|---:|---:|
| Tần suất | 43/59 | 72,88% | 4,59432 |
| Logistic | 42/59 | 71,19% | 4,61694 |
| CatBoost v2 | 41/59 | 69,49% | 4,58410 |

CatBoost có log loss tốt nhất trong khoảng này, nhưng thấp hơn Tần suất hai kỳ đúng, McNemar p=0,727. Wilson CatBoost là 56,85–79,75%; p vượt 65% là 0,282. Đây là tín hiệu để theo dõi chất lượng xác suất, chưa đủ chọn phiên bản thắng.

## 5. Các nâng cấp cần ưu tiên

| Ưu tiên | Phát hiện trong code | Thay đổi đề xuất |
|---|---|---|
| Cao | Các hàm `create_prediction` chặn khi kết quả đã vào DB, chưa chặn theo đồng hồ thực tế | Enforce deadline dự đoán ở backend. Dự đoán muộn chỉ dùng nghiên cứu, không đưa vào tỷ lệ khóa trước. Lưu timezone và deadline của protocol. |
| Cao | `model_comparison.py` ghép theo ngày/N/version/trạng thái nhưng không kiểm tra deadline, hash dữ liệu, cấu hình, actual đồng nhất | Ghép theo protocol/batch; kiểm tra eligibility, hash và kết quả thực trước khi tính tỷ lệ. Không gộp cấu hình khác nhau dưới một version. |
| Cao | Lịch sử dữ liệu có thể được bổ sung sau khi đã khóa dự đoán | Giữ snapshot dữ liệu hoặc danh sách ID/revision của tập huấn luyện; lưu code hash và cấu hình cho tất cả mô hình, kể cả Tần suất. |
| Vừa | Cache rolling dựa vào ID cố định và `dataset_hash` | Thêm model/config/code/library/protocol hash để tránh trả báo cáo của thuật toán cũ sau cập nhật code. |
| Vừa | Evaluation chỉ xử lý pending; chưa tính lại snapshot đã chấm khi kết quả được sửa | Lưu revision/hash của actual; khi nguồn sửa, chấm lại có nhật ký. Lần này chưa thấy mâu thuẫn actual. |
| Vừa | Bảng live chưa kèm bất định và kiểm định ghép cặp | Hiển thị số kỳ, Wilson, mốc N/100, chênh lệch cùng ngày và trạng thái “chưa đủ bằng chứng”. |
| Thấp | `_history_before` của Tần suất/Logistic chỉ kiểm tra `last_two` là chuỗi | Dùng validator chung kiểm tra đủ hai chữ số ASCII và giải đặc biệt đồng nhất; dữ liệu hiện tại hợp lệ. |

CatBoost đang dùng giá trị 00–99, trung bình/độ lệch chuẩn như đại lượng có thứ tự. Đây là lựa chọn đặc trưng cần thử bỏ/thay bằng categorical hoặc one-hot, chưa phải lỗi được chứng minh. Cột drawdown cũ dùng cùng mức thắng/thua cho mọi N cũng không phù hợp để so các lựa chọn; không dùng cột này cho kết luận về độ chính xác.

## 6. Đề xuất phiên bản thử nghiệm và thuật toán tham chiếu

1. **Ưu tiên thử `factorized_logistic_bayes_v2_shadow`.** Cơ chế phối hợp hiện đạt 243/365, chạy CPU nhẹ, tận dụng các thư viện sẵn có. Giữ trọng số 50/50 và prior đã ghi để chạy song song, chưa thay mô hình hiện tại. Nếu cần đổi trọng số, chọn bằng vòng validation quá khứ bên trong; đánh giá bằng một khoảng tương lai khác.

2. **Thử `factorized_catboost_v3_shadow`.** Hai mô hình 10 lớp cho chục và đơn vị; ngữ cảnh 90/365 để có nhiều mẫu huấn luyện hơn; lag categorical hoặc one-hot. So sánh lần lượt việc tách chữ số, rút ngắn ngữ cảnh và bỏ đặc trưng số học; tránh đổi tất cả rồi không biết thay đổi nào giúp ích. Mục đích là kiểm tra giả thuyết dữ liệu ít/100 lớp; phiên bản này chưa được chạy, chưa có tỷ lệ chính xác công bố. [Bài báo CatBoost gốc](https://proceedings.neurips.cc/paper_files/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html) hỗ trợ cơ chế học, không chứng minh lợi thế trên XSMB.

3. **Tham chiếu ngoài: TabPFN-3.5 / 3.5-Fast.** Báo cáo phát hành 15/09/2026 của tác giả cho biết đạt vị trí đầu trên TabArena và BeyondArena; đây là benchmark dữ liệu bảng tổng quát, không phải dữ liệu xổ số. Đáng thử làm đối chứng ngoại tuyến với cùng đặc trưng và protocol thời gian, trước hết dùng hai bài toán 10 lớp. Nguồn: [báo cáo TabPFN-3.5](https://priorlabs.ai/technical-reports/tabpfn-3-5). Tác giả khuyến nghị GPU; CPU cho phép tối đa 5.000 mẫu ở bản này. Trọng số model có giấy phép phi thương mại riêng. Với Vercel Hobby, đề xuất chạy nghiên cứu trên máy/worker riêng rồi lưu snapshot để web đọc; khả năng triển khai phải được đo trước. Nguồn: [repository chính thức](https://github.com/PriorLabs/TabPFN). Chưa cài, chạy hoặc gửi dữ liệu tới API TabPFN trong lần này.

Bayesian và Markov đã chạy như đối chứng, chưa cho thấy lợi thế đủ rõ. Không có cơ sở từ lần rà soát này để gắn nhãn “độ chính xác cao” cho bất kỳ thuật toán dự đoán XSMB mới nào.

Điều kiện nâng phiên bản chính thức: khóa version/config/dataset/protocol, chọn Top 65 làm chỉ tiêu chính, dự đoán trước deadline, có mẫu tương lai đủ lớn theo kế hoạch cỡ mẫu, vượt mô hình đối chứng trên cùng ngày và vượt mốc 65% với mức bất định chấp nhận được. Mức cải thiện tối thiểu cần chốt trước khi xem kết quả. Theo dõi thêm log loss/Brier; hiệu chỉnh thử nhiều mô hình/N bằng Holm. Mốc 365 kỳ theo kế hoạch cũ là thời gian theo dõi ban đầu, không bảo đảm đủ lực kiểm định cho một cải thiện rất nhỏ. McNemar dùng số cặp bất đồng theo [tài liệu statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html); Holm được mô tả trong [multipletests](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).

## 7. Tái chạy và kiểm tra

Từ thư mục dự án, với môi trường chứa dependencies hiện tại:

```powershell
python -m scripts.audit_algorithms --backtest
python -m scripts.audit_algorithms --catboost-only --workers 4
python -m scripts.audit_algorithms --summarize
```

Script chỉ đọc file xuất, không kết nối hay ghi MongoDB. Chạy CatBoost bốn fit độc lập đồng thời; mỗi fit giữ nguyên hai thread và seed của mô hình vận hành. Không dùng nhãn mục tiêu hoặc tương lai trong fit.

**36 kiểm thử đạt**, gồm audit mới và các test Tần suất, chữ số, Logistic, CatBoost, rolling. Test audit kiểm tra loại khóa muộn, tính lại hit từ actual, phân phối xác suất, hiệu chỉnh Holm, không báo bootstrap quá chính xác ở mẫu ngắn, và prefix huấn luyện CatBoost không lấy mục tiêu/tương lai. Kiểm thử phần mềm không xác nhận khả năng dự đoán.

Các file bằng chứng: `live_audit.json`, `backtest_daily.json`, `backtest_summary.json`, `backtest_comparisons.json`, `catboost_backtest_daily.json`, `catboost_backtest_summary.json`, `catboost_matched_comparison.json`, `replay_checks.json`, `manifest.json`, `database_snapshot.json`. Mã nghiên cứu: `scripts/audit_algorithms.py`; kiểm thử: `tests/test_algorithm_audit.py`.
