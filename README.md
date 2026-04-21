# 🚀 Lab Day 14: AI Evaluation Factory (Team Edition)

## 🎯 Tổng quan
"Nếu bạn không thể đo lường nó, bạn không thể cải thiện nó." — Nhiệm vụ của nhóm bạn là xây dựng một **Hệ thống đánh giá tự động** chuyên nghiệp để benchmark AI Agent. Hệ thống này phải chứng minh được bằng con số cụ thể: Agent đang tốt ở đâu và tệ ở đâu.

---

## 🕒 Lịch trình thực hiện (4 Tiếng)
- **Giai đoạn 1 (45'):** Thiết kế Golden Dataset & Script SDG. Tạo ra ít nhất 50 test cases chất lượng.
- **Giai đoạn 2 (90'):** Phát triển Eval Engine (RAGAS, Custom Judge) & Async Runner.
- **Giai đoạn 3 (60'):** Chạy Benchmark, Phân cụm lỗi (Failure Clustering) & Phân tích "5 Whys".
- **Giai đoạn 4 (45'):** Tối ưu Agent dựa trên kết quả & Hoàn thiện báo cáo nộp bài.

---

## 🛠️ Các nhiệm vụ chính (Expert Mission)

### 1. Retrieval & SDG (Nhóm Data)
- **Retrieval Eval:** Tính toán Hit Rate và MRR cho Vector DB. Bạn phải chứng minh được Retrieval stage hoạt động tốt trước khi đánh giá Generation.
- **SDG:** Tạo 50+ cases, bao gồm cả Ground Truth IDs của tài liệu để tính Hit Rate.

### 2. Multi-Judge Consensus Engine (Nhóm AI/Backend)
- **Consensus logic:** Sử dụng ít nhất 2 model Judge khác nhau. 
- **Calibration:** Tính toán hệ số đồng thuận (Agreement Rate) và xử lý xung đột điểm số tự động.

### 3. Regression Release Gate (Nhóm DevOps/Analyst)
- **Delta Analysis:** So sánh kết quả của Agent phiên bản mới với phiên bản cũ.
- **Auto-Gate:** Viết logic tự động quyết định "Release" hoặc "Rollback" dựa trên các chỉ số Chất lượng/Chi phí/Hiệu năng.

---

## 📤 Danh mục nộp bài (Submission Checklist)
Nhóm nộp 1 đường dẫn Repository (GitHub/GitLab) chứa:
1. [ ] **Source Code**: Toàn bộ mã nguồn hoàn chỉnh.
2. [ ] **Reports**: File `reports/summary.json` và `reports/benchmark_results.json` (được tạo ra sau khi chạy `main.py`).
3. [ ] **Group Report**: File `analysis/failure_analysis.md` (đã điền đầy đủ).
4. [ ] **Individual Reports**: Các file `analysis/reflections/reflection_[Tên_SV].md`.
5. [ ] **Supplementary Benchmark Report**: File `GROUP_REPORT.md` tóm tắt kết quả benchmark hiện tại, giải thích các metric nâng cao, và phân tích regression V1/V2.

---

## 🏆 Bí kíp đạt điểm tuyệt đối (Expert Tips)

### ✅ Đánh giá Retrieval (15%)
Nhóm nào chỉ đánh giá câu trả lời mà bỏ qua bước Retrieval sẽ không thể đạt điểm tối đa. Bạn cần biết chính xác chunk nào đang gây ra lỗi Hallucination.

### ✅ Multi-Judge Reliability (20%)
Việc chỉ tin vào một Judge (ví dụ GPT-4o) là một sai lầm trong sản phẩm thực tế. Hãy chứng minh hệ thống của bạn khách quan bằng cách so sánh nhiều Judge model và tính toán độ tin cậy của chúng.

### ✅ Tối ưu hiệu năng & Chi phí (15%)
Hệ thống Expert phải chạy cực nhanh (Async) và phải có báo cáo chi tiết về "Giá tiền cho mỗi lần Eval". Hãy đề xuất cách giảm 30% chi phí eval mà không giảm độ chính xác.

### ✅ Phân tích nguyên nhân gốc rễ (Root Cause) (20%)
Báo cáo 5 Whys phải chỉ ra được lỗi nằm ở đâu: Ingestion pipeline, Chunking strategy, Retrieval, hay Prompting.

---

## 🔧 Hướng dẫn chạy

```bash
# 1. Cài đặt dependencies
pip install -r requirements.txt

# 2. Tạo Golden Dataset (chạy trước khi benchmark)
python data/synthetic_gen.py

# 3. Chạy Benchmark & tạo reports
python main.py

# 4. Kiểm tra định dạng trước khi nộp
python check_lab.py
```

## 🧭 Ghi chú chỉnh `main.py`
- `main.py` hiện giữ output `reports/summary.json` và `reports/benchmark_results.json` theo đúng format mẫu để script chấm tự động đọc được.
Vì sao: autograder thường check shape JSON rất cứng; các metric nâng cao sẽ chạy riêng hoặc được mô tả trong README thay vì nhét trực tiếp vào 2 file chuẩn này.

- `run_benchmark_with_results(...)`: sửa để map đúng label benchmark sang runtime agent thực (`Agent_V1_Base -> version="v1"`, `Agent_V2_Optimized -> version="v2"`).
Vì sao: trước đó chỉ đổi tên version trong metadata nhưng vẫn khởi tạo cùng một agent runtime, nên regression không phản ánh đúng V1 và V2.

- `BenchmarkRunner(...)`: thay evaluator stub bằng `AdvancedEvaluator()` và giữ `LLMJudge()` thật.
Vì sao: benchmark cũ trả `faithfulness`, `relevancy`, `hit_rate`, `mrr` theo giá trị placeholder; bản sửa dùng retrieval thật, semantic similarity thật và judge thật/fallback có kiểm soát.

- Phần ghi file `reports/summary.json`: chỉ giữ `metadata`, `metrics.avg_score`, `metrics.hit_rate`, `metrics.agreement_rate`, và `regression`.
Vì sao: đây là đúng shape của file mẫu; metric nâng cao không được ghi trực tiếp ở đây để tránh lệch format chấm.

- Phần ghi file `reports/benchmark_results.json`: chuẩn hóa mỗi case về các key `test_case`, `agent_response`, `latency`, `ragas`, `judge`, `status`, và bọc ngoài thành object có 2 key `v1` và `v2`.
Vì sao: file benchmark mẫu ngoài root đang lưu kết quả theo hai nhánh agent song song với schema gọn hơn output nội bộ của runner.

- Các metric nâng cao như `context_precision`, `context_recall`, `semantic_similarity`, `position_bias`, `cost`, `latency breakdown` vẫn được tính ở engine nhưng không được ghi vào 2 file report chuẩn của `main.py`.
Vì sao: giữ tách biệt giữa “output để chấm tự động” và “output để phân tích nội bộ”.

---

## ⚠️ Lưu ý quan trọng
- **Bắt buộc** chạy `python data/synthetic_gen.py` trước để tạo file `data/golden_set.jsonl`. File này không được commit sẵn trong repo.
- Trước khi nộp bài, hãy chạy `python check_lab.py` để đảm bảo định dạng dữ liệu đã chuẩn. Bất kỳ lỗi định dạng nào dẫn đến việc script chấm điểm tự động không chạy được sẽ bị trừ 5 điểm thủ tục.
- File `.env` chứa API Key **KHÔNG** được push lên GitHub.

---
*Chúc nhóm bạn xây dựng được một Evaluation Factory thực sự mạnh mẽ!*
