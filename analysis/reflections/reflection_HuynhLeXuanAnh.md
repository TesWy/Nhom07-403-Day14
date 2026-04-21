# Individual Reflection Report — Huỳnh Lê Xuân Ánh

## 1) Thông tin & phạm vi đóng góp
- **Họ tên:** Huỳnh Lê Xuân Ánh
- **MSHV:** 2A202600083

## 2) Engineering Contribution
### 2.1. Những thay đổi đã thực hiện
Trong `analysis/failure_analysis.md`, báo cáo đã được mở rộng theo hướng **regression + metrics**:
- **Tổng quan regression (85 cases):** so sánh `Agent_V1_Base` vs `Agent_V2_Optimized`, V1 pass `40/85` → V2 pass `68/85`, delta điểm trung bình `+1.2176`, quyết định `APPROVE`.
- **Các chỉ số chính của V2** để “đo đúng chỗ cần tối ưu”:
  - Retrieval: `hit_rate = 0.8824`, `mrr = 0.8412`, `context_precision = 0.3294`, `context_recall = 0.8647`
  - Answer quality: `faithfulness = 0.7469`, `relevancy = 0.8320`, `semantic_similarity = 0.8613`
  - Multi-judge: `agreement_rate = 0.8471`, `position_bias_rate = 0.0118`
- **Phân nhóm lỗi theo nguyên nhân gốc (V2):** `retrieval_miss` (10), `retrieved_but_weak_grounding` (6), `judge_quality_failure` (1); kèm thêm phân bố theo loại câu hỏi/độ khó (fail tập trung ở `hard`/`adversarial`).
- **3 case 5 Whys tệ nhất** bám sát dữ liệu benchmark: (1) out-of-context/coverage gap (nghỉ phép part-time), (2) multi-hop (điều phối email IT 2 mục tiêu), (3) prompt injection (liệt kê quyền admin).
- **Kế hoạch cải tiến** được ưu tiên hoá rõ ràng: tăng precision retrieval, cải thiện multi-hop, siết safety, và tối ưu latency/cost.

### 2.2. Giá trị kỹ thuật mang lại
- Biến benchmark thành **chẩn đoán có thể hành động**: tách `retrieval_miss` vs `weak_grounding` vs `judge/safety`, tránh sửa “mò”.
- Làm rõ trade-off chất lượng/chi phí: precision thấp (`0.3294`) nghĩa là retrieval còn nhiễu → cần reranking/filter để giảm token/cost mà vẫn giữ recall.

## 3) Technical Depth
### 3.1. MRR/Hit Rate và insight từ Context Precision/Recall
- **Hit Rate@K** trả lời “có retrieve được evidence đúng không”; **MRR** đo “evidence đúng xuất hiện sớm hay muộn” trong danh sách.
- Với V2: `hit_rate = 0.8824`, `mrr = 0.8412` cho thấy retrieval tốt, nhưng `context_precision = 0.3294` chỉ ra **nhiễu cao** (dễ làm câu trả lời kém grounded dù `context_recall = 0.8647`).
- Hướng tối ưu hợp lý: reranking/filter + top-k động theo loại câu hỏi, thay vì chỉ tăng top-k.

### 3.2. Cohen’s Kappa trong Multi-Judge consensus
- `agreement_rate = 0.8471` là tín hiệu tốt, nhưng để release gate đáng tin hơn nên bổ sung **Cohen’s Kappa** nhằm hiệu chỉnh đồng thuận vượt ngẫu nhiên (đặc biệt khi phân phối nhãn lệch).

### 3.3. Position Bias (thiên lệch vị trí)
- `position_bias_rate = 0.0118` (~1.18%) cho thấy position bias hiện thấp; vẫn cần duy trì kiểm tra swap A/B để giám sát drift.

## 4) Problem Solving (theo rubric — tối đa 10đ)
Từ các case thất bại nổi bật và action plan của failure analysis mới, em rút ra 4 hướng giải quyết cốt lõi:
1. **Tăng precision retrieval:** thêm reranking và metadata filter; cân nhắc top-k động để giảm nhiễu (cải thiện `context_precision`).
2. **Multi-hop:** decomposition/retrieval nhiều bước để assemble đủ evidence cho câu hỏi nhiều nhánh (case “điều phối email IT”).
3. **Safety:** refusal policy rõ ràng cho prompt injection/goal hijacking (case “liệt kê quyền admin”), và tách benchmark slice nhạy cảm để kiểm soát release gate.
4. **Out-of-context/coverage gap:** trả lời an toàn nhưng hữu ích (nêu phạm vi tài liệu + hướng dẫn kênh hỗ trợ), đồng thời gắn nhãn “no-evidence” để phân biệt với retrieval miss.

## 5) Kế hoạch cải thiện tiếp theo (cá nhân)
- Ưu tiên thử **reranking/filter** để nâng `context_precision` trong khi giữ `hit_rate/mrr` ổn định.
- Thêm **decomposition** cho nhóm `multi-hop` và đánh giá theo slice `hard/adversarial`.
- Hoàn thiện **refusal policy** cho prompt injection và theo dõi safety slice trong regression.
- Theo dõi trade-off **latency/cost**: tăng song song khi chạy benchmark và dùng evaluator nhẹ để screening trước khi gọi full multi-judge.
