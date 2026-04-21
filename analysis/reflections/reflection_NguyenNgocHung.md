# BÁO CÁO CÁ NHÂN - PHÁT TRIỂN AGENT V1 & V2
**Họ tên:** Nguyễn Ngọc Hưng 
**MSHV:** 2A202600188
**Vai trò:** Người phụ trách Stream 4 (Agent Development)

---

## 1. Vai trò cá nhân trong nhóm

Trong dự án này, tôi chịu trách nhiệm chính ở Stream 4 - Phát triển Agent. Đây là khâu cung cấp "linh hồn" cho hệ thống đánh giá bằng việc xây dựng các phiên bản RAG Agent (V1 và V2). Mục tiêu là tạo ra những đối tượng giả lập để hệ thống Regression Testing và Benchmark (do các luồng khác phát triển) có thể tiến hành đánh giá tự động dựa trên số liệu thực tế.

## 2. Những việc mình đã làm

Để phục vụ cho hệ thống Evaluation Pipeline, tôi đã xây dựng các thành phần cốt lõi sau:

### 2.1 Thiết kế Kiến trúc Factory (MainAgent)
Tôi đã xây dựng class `MainAgent` đóng vai trò như một wrapper thống nhất. Kiến trúc này tập trung hóa việc nạp dữ liệu (Corpus Loading), cấu hình Provider (`LLMProviderAdapter`), theo dõi ngân sách (Usage Tracking) và xử lý metadata. Điều này giúp hệ thống dễ dàng khởi tạo các phiên bản Agent khác nhau mà không làm thay đổi interface giao tiếp với bộ Evaluator.

### 2.2 Phát triển Agent V1 (Baseline - Broken Retriever)
Nhằm tạo ra một dữ liệu cơ sở (baseline) tồi tệ có chủ đích, tôi đã thiết kế V1 với logic truy xuất "cứng" (hardcoded). Agent V1 luôn trả về cố định một chunk (ví dụ `access_control_sop_0`) bất kể người dùng hỏi gì. Việc này mô phỏng lỗi nghiêm trọng trong khâu retrieval của các hệ thống RAG thực tế, tạo điều kiện cho Regression Gate bắt lỗi (Hit Rate/MRR bị rớt thảm hại).

### 2.3 Phát triển Agent V2 (Advanced RAG & Semantic Search)
Đây là phiên bản hoạt động thực tế với pipeline chuẩn mực:
- Tích hợp model embedding `text-embedding-3-small` của OpenAI.
- Tự cài đặt thuật toán **Cosine Similarity** thuần túy bằng thư viện `numpy` (`np.dot` & `np.linalg.norm`) để so sánh vector và trích xuất Top-K (K=3) chunk văn bản sát nghĩa nhất.

### 2.4 Xây dựng Cơ chế Fallback Đa tầng
Để hệ thống không bị crash lúc Dev/Test khi không có API Key hoặc rớt mạng, tôi đã cấu hình chiến lược fallback embedding 3 cấp: (1) OpenAI API ➔ (2) Local Model `sentence-transformers` ➔ (3) Custom Hash-based Embedding. Nhờ đó, Benchmark pipeline luôn duy trì Zero-Downtime.

## 3. Điều mình học được

Qua quá trình xây dựng Agent thực tế, tôi rút ra được các bài học chuyên sâu về hệ thống RAG:

1. **Bảo toàn và truyền tải Metadata là tối quan trọng:** Để Evaluator tính được Hit Rate/MRR, bản thân Agent phải biết rõ nó mang về chunk nào. Việc trích xuất chính xác `retrieved_chunk_ids` từ Agent và đính kèm vào Response là bắt buộc để hệ thống Data Pipeline không bị đứt gãy.
2. **Sức mạnh của RAG Guardrails:** Hiện tượng Hallucination (bịa chuyện) là vấn đề nhức nhối khi câu hỏi nằm ngoài ngữ cảnh. Việc bổ sung Guardrail cứng (*"Answer only from the provided context. If not, reply 'Toi khong co thong tin'"*) giúp bảo đảm tính Faithful (trung thực) tuyệt đối của Agent, nâng cao chất lượng câu trả lời.
3. **Tối ưu hóa Vector Logic:** Việc dùng thư viện `numpy` vectorization hiệu quả gấp nhiều lần việc quét mảng (looping) trong python khi tính toán khoảng cách cosine trên hàng ngàn document. Đồng thời, normalize vector trước khi tính độ tương đồng giảm thiểu sai số toán học đáng kể.

## 4. Khó khăn mình gặp

### 4.1 Đồng bộ hóa ID Dữ liệu (Mismatched Chunk IDs)
Dữ liệu Corpus nạp từ Data team đôi khi thiếu field hoặc metadata bị sai. Nếu Agent không truyền đúng Chunk ID thì Evaluator sẽ chấm rớt (Hit Rate = 0). Để khắc phục, tôi đã nâng cấp logic `_load_corpus()`, tự động quét fallback lấy tên file làm logic chunk id nếu dữ liệu gốc bị thiếu để hệ thống map đúng với thông tin bên nhánh Chroma.

### 4.2 Fix lỗi Pipeline và Cross-import
Vào lúc tích hợp (Integration) với nhóm, cấu trúc module bị phát sinh lỗi vòng lặp import hoặc name-error như class `MainAgent` không gọi được trong `main.py`. Tôi đã gỡ lỗi triệt để, tối ưu đường dẫn import và biến môi trường `.env` để tiến trình từ Engine gọi thẳng Agent chạy nuột nà.

### 4.3 Lỗi Encoding Môi trường Windows
Khi chạy benchmark trên môi trường Windows PowerShell ở máy local, một vài file test sinh ra log chứa kí hiệu đặc biệt hoặc emoji khiến code bị crash do `UnicodeEncodeError`. Khắc phục tạm thời và lâu dài là chuyển đổi toàn bộ stdout output log về dạng ASCII plain-text (`[INFO]`, `[ERROR]`) thân thiện với mọi hệ điều hành.

## 5. Nếu có thêm thời gian, mình sẽ làm gì tiếp

Dù Agent V2 hiện tại đã vượt qua Benchmark dễ dàng, nhưng tính khả mở của hệ thống vẫn có thể được nâng cao. Nếu có thêm thời gian tôi dự kiến:

1. Tối ưu hơn nữa khâu Routing giữa OpenAI và Local Embedding (hiện tại logic là fallback, nên thử nghiệm hybrid search: kết hợp Semantic Search + Keyword Match / BM25).
2. Tích hợp Re-ranking models (vd: Cohere Rerank hoặc một Cross-Encoder nội bộ nhỏ) để sắp xếp lại chính xác hơn các chunks nếu Top-K bị mở rộng trên K=10.
3. Cache mạnh hơn lớp generation (nếu có câu hỏi trùng lặp đánh giá nhiều lần) để tiết kiệm thêm OpenAI Token Costs.

## 6. Tự đánh giá đóng góp

Đóng góp của mình trong phần này ở mức độ xây dựng nền tảng RAG cốt lõi:
- Xây dựng thành công 2 bản mô phỏng rõ nét ranh giới giữa Lỗi (V1) và Ổn định (V2).
- Tự tay build thuật toán vector logic bằng Code thuần (Numpy) giúp nâng cao kỹ năng Data Engineering.
- Châm ngòi để hệ thống Benchmark Gate chạy đúng logic "Bắt được Agent Lỗi" (Hit Rate ~0%) và "Pass Agent Chuẩn" (Hit Rate 100%).

Những thành phần này tuy thiên về thuật toán và cấu trúc ở Tầng Dưới (Backend/Engine), nhưng nó là "nguyên liệu" sống còn để toàn hệ thống Benchmark của nhóm có thể vận hành và chứng minh được tính đúng đắn.
