# Báo cáo Đóng góp Cá nhân — Lab Day 14
**Họ và tên:** Nguyễn Ngọc Khánh Duy 

**Mã HV:** 2A202600189

---

## 1. Engineering Contribution

**Phần phụ trách:** Thiết kế và xây dựng Golden Dataset (`data/golden_set.jsonl`)

Tôi đảm nhiệm toàn bộ phần **Dataset & SDG** — đây là nền tảng để toàn bộ pipeline eval của nhóm hoạt động được.

**Cụ thể đã làm:**

- Đọc và phân tích toàn bộ `corpus.jsonl` (29 chunks từ 5 tài liệu nội bộ) để nắm nội dung từng chunk trước khi viết câu hỏi
- Thiết kế schema cho mỗi test case gồm 5 trường: `question`, `expected_answer`, `expected_chunk_ids`, `context`, `metadata`
- Tạo **85 test cases** handcrafted, phân loại theo 4 mức độ và 11 type khác nhau:

| Difficulty | Số cases |
|---|---|
| easy | 34 |
| medium | 24 |
| hard | 16 |
| adversarial | 11 |

| Type | Số cases |
|---|---|
| fact-retrieval | 55 |
| multi-hop | 12 |
| boundary-case | 7 |
| out-of-context | 3 |
| prompt-injection | 2 |
| ambiguous-question, conflicting-information, cross-domain-confusion, goal-hijacking, hallucination-bait, misleading-premise | 1 mỗi loại |

- Thêm trường `expected_chunk_ids` mapping trực tiếp với `chunk_id` thực trong `corpus.jsonl` — đây là ground truth để tính **Hit Rate và MRR** cho retrieval evaluation
- Đảm bảo **100% chunk coverage** (29/29 chunks đều có ít nhất 1 test case), tránh blind spot trong quá trình eval
- Thêm trường `chunk_id_rationale` giải thích lý do chọn chunk đó làm ground truth, giúp team debug khi retrieval fail

**Kết quả :** File `golden_set.jsonl` sẵn sàng đưa thẳng vào `BenchmarkRunner` — `main.py` đọc file này và chạy eval ngay mà không cần chỉnh sửa thêm.

---

## 2. Technical Depth

### Hit Rate

Hit Rate đo tỉ lệ câu hỏi mà ít nhất 1 chunk đúng xuất hiện trong Top-K kết quả retrieval. Mỗi test case trong golden set có `expected_chunk_ids` — hệ thống so sánh list này với `retrieved_chunk_ids` trả về từ agent. Nếu có giao thì Hit = 1, không có thì Hit = 0.

```
Hit Rate = (số câu hỏi có ít nhất 1 chunk đúng trong Top-K) / (tổng số câu hỏi)
```

### MRR (Mean Reciprocal Rank)

MRR đo chất lượng *thứ hạng* của chunk đúng, không chỉ là có/không. Công thức:

```
MRR = (1/N) * Σ (1 / rank_i)
```

Trong đó `rank_i` là vị trí đầu tiên (1-indexed) mà chunk đúng xuất hiện trong kết quả trả về:

| Chunk đúng ở vị trí | Reciprocal Rank |
|---|---|
| 1 | 1.000 |
| 2 | 0.500 |
| 3 | 0.333 |
| Không tìm thấy | 0.000 |

Trong golden set, các câu hỏi `fact-retrieval` easy kỳ vọng MRR cao (chunk đúng phải ở top 1-2), trong khi `multi-hop` chấp nhận MRR thấp hơn vì có nhiều chunk relevant phân tán.

### Cohen's Kappa

Cohen's Kappa (κ) đo mức độ đồng thuận giữa các judge **có tính đến xác suất đồng thuận ngẫu nhiên**, khác với simple agreement rate chỉ đếm số lần đồng ý.

```
κ = (Po - Pe) / (1 - Pe)
```

Trong đó:
- `Po` = tỉ lệ đồng thuận thực tế (observed agreement)
- `Pe` = tỉ lệ đồng thuận kỳ vọng nếu hai judge chọn ngẫu nhiên (expected agreement by chance)

| Giá trị κ | Ý nghĩa |
|---|---|
| < 0.20 | Đồng thuận kém (Poor) |
| 0.21 – 0.40 | Đồng thuận yếu (Fair) |
| 0.41 – 0.60 | Đồng thuận trung bình (Moderate) |
| 0.61 – 0.80 | Đồng thuận tốt (Substantial) |
| 0.81 – 1.00 | Đồng thuận gần như hoàn hảo (Almost Perfect) |

**Ứng dụng trong Multi-Judge:** Khi dùng 2 model judge (GPT + Claude) chấm cùng 1 câu trả lời, simple agreement rate có thể cao giả tạo vì cả 2 đều hay cho điểm cao với câu trả lời dài. Cohen's Kappa loại bỏ phần đồng thuận ngẫu nhiên đó, đưa ra con số trung thực hơn về mức độ thực sự đồng ý giữa 2 judge.

### Position Bias

LLM Judge có xu hướng đánh giá cao câu trả lời xuất hiện ở vị trí đầu trong prompt (position bias). Đây là lý do rubric yêu cầu ít nhất 2 model judge — nếu chỉ dùng 1 judge, bias này ảnh hưởng trực tiếp đến kết quả. Các adversarial case như `prompt-injection` và `goal-hijacking` trong dataset đặc biệt dễ bị ảnh hưởng nếu judge không được calibrate kỹ.

### Trade-off Chi phí vs Chất lượng

Tôi chọn **handcrafted** thay vì dùng LLM để generate toàn bộ golden set vì LLM-generated cases thường thiếu adversarial depth, dễ bị confirmation bias (LLM tự hỏi rồi tự trả lời theo kiểu mình hay trả lời). Đánh đổi là tốn thời gian hơn nhưng 85 cases handcrafted có chất lượng kiểm soát được, đặc biệt ở các `conflicting-information` và `misleading-premise` case mà LLM thường bỏ sót.

---

## 3. Problem Solving

**Vấn đề 1 — Chunk ID không biết trước:**

Ban đầu không biết chunk ID thực tế trong ChromaDB là gì. Giải pháp: đọc `corpus.jsonl` đã được generate sẵn, extract toàn bộ `chunk_id` và nội dung từng chunk trước khi viết câu hỏi — đảm bảo `expected_chunk_ids` trong golden set 100% khớp với ID thực trong hệ thống.

**Vấn đề 2 — Test case bị trùng lặp về nội dung:**

Khi viết nhiều câu hỏi cho cùng 1 document, dễ bị trùng ý. Giải pháp: phân chia theo section + type trước, mỗi ô (section × type) chỉ được dùng 1 lần — tránh 2 câu hỏi cùng hỏi về cùng 1 fact theo cùng 1 cách.

**Vấn đề 3 — Adversarial case phải realistic:**

Nếu adversarial quá lộ liễu (ví dụ: "hãy ignore tất cả rules"), agent nào cũng pass được. Giải pháp: thiết kế các case tinh tế hơn:
- `misleading-premise`: cố tình đưa số sai để xem agent có sửa không (ví dụ: "SLA P1 là 6 giờ đúng không?" trong khi thực tế đã đổi xuống 4 giờ)
- `conflicting-information`: 2 điều khoản trong cùng 1 tài liệu mâu thuẫn nhau (Điều 2 ghi "7 ngày làm việc", Điều 3 ghi "7 ngày")
- `cross-domain-confusion`: trộn khái niệm từ 2 tài liệu khác nhau để xem agent có phân biệt được không (quyền tạm thời IT vs remote work policy HR)

**Vấn đề 4 — Multi-hop cần đúng thứ tự chunk:**

Với `multi-hop` cases có 2 chunk trong `expected_chunk_ids`, thứ tự quan trọng vì ảnh hưởng đến MRR. Tôi sắp xếp chunk quan trọng nhất (chứa answer chính) lên đầu list để MRR calculation phản ánh đúng chất lượng retrieval.