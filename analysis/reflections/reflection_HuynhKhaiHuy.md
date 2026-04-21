# Reflection Cá Nhân:
**Họ và tên:** Huỳnh Khải Huy
**Mã HV:** 2A202600082

## 1. Vai trò cá nhân trong nhóm

Phần mình phụ trách nằm ở lớp benchmark core của bài lab. Mình tập trung vào xây dựng pipeline chấm điểm tự động, tích hợp nhiều judge model, bổ sung retrieval metrics, và sửa benchmark để phần so sánh V1/V2 phản ánh đúng runtime thực tế.

Các commit chính của mình tập trung vào 3 việc:

- triển khai benchmark ban đầu
- cập nhật output report
- sửa benchmark để score phản ánh đúng chất lượng thật

## 2. Những việc mình đã làm

### 2.1 Xây dựng benchmark engine

Phần việc chính mình làm là triển khai bộ khung benchmark cho nhóm. Cụ thể, mình tham gia vào các module:

- `engine/llm_judge.py`: mở rộng judge từ stub thành multi-judge có `agreement_rate`
- `engine/llm_provider.py`: chuẩn hóa cách gọi nhiều provider
- `engine/retrieval_eval.py`: tính `hit_rate`, `mrr`, `context_precision`, `context_recall`
- `engine/runner.py`: chạy benchmark theo batch bất đồng bộ và gom latency, usage
- `main.py`: chạy benchmark và xuất report

Điểm mình quan tâm nhất là benchmark không chỉ chấm điểm bề mặt, mà phải cho thấy retrieval có đúng không, judge có đồng thuận không, và pipeline có chạy ổn định không.

### 2.2 Sửa benchmark để phản ánh đúng chất lượng thực tế

Phần quan trọng nhất mình xử lý là sửa benchmark để V1 và V2 thực sự khác nhau về runtime, thay vì chỉ khác tên trong report. Mình cũng sửa lại phần load corpus để hệ thống dùng `chunk_id` thật từ `data/corpus.jsonl` thay vì dữ liệu placeholder.

Nhờ đó, các metric như `hit_rate` và `mrr` mới phản ánh retrieval thật, còn regression mới có ý nghĩa kỹ thuật thay vì chỉ là so sánh hình thức.

### 2.3 Hoàn thiện output benchmark

Ngoài phần code, mình cũng cập nhật lại `reports/summary.json` và `reports/benchmark_results.json` để nhóm có artifact rõ ràng cho việc nộp bài và phân tích regression.

## 3. Technical Depth

Phần mình hiểu rõ hơn sau khi làm benchmark là:

- **MRR** không chỉ đo có tìm thấy chunk đúng hay không, mà còn đo chunk đúng đứng ở vị trí nào trong danh sách retrieval
- **agreement rate** giúp nhìn nhanh mức đồng thuận giữa hai judge, nhưng nếu muốn chặt hơn thì có thể dùng thêm **Cohen's Kappa** để loại bớt đồng thuận ngẫu nhiên
- **position bias** là nguy cơ judge bị ảnh hưởng bởi thứ tự đáp án, nên việc kiểm tra đảo vị trí là cần thiết
- benchmark tốt luôn phải cân bằng giữa **chất lượng**, **chi phí**, và **độ trễ**, vì càng thêm nhiều lớp đánh giá thì càng tốn token và thời gian

## 4. Khó khăn mình gặp

### 4.1 Benchmark có số nhưng chưa chắc đo đúng

Khó khăn lớn nhất là benchmark ban đầu có thể tạo ra score nhưng chưa chắc đo đúng chất lượng agent. Mình phải sửa phần map version và load corpus để V1/V2 chạy đúng runtime, đồng thời dùng `chunk_id` thật thay vì placeholder.

### 4.2 Hệ thống dễ gãy khi dùng nhiều provider

Khi thêm multi-judge, benchmark dễ lỗi vì thiếu API key, thiếu package hoặc response JSON không sạch. Mình xử lý bằng cách bọc provider qua adapter chung và thêm fallback heuristic để pipeline không sập toàn bộ.

### 4.3 Cần retrieval metrics sâu hơn

Nếu chỉ nhìn Hit Rate thì chưa đủ biết retriever đang thiếu evidence hay kéo quá nhiều nhiễu. Vì vậy mình thêm `context_precision` và `context_recall` để benchmark chỉ ra lỗi rõ hơn.

## 5. Điều mình học được

Qua phần việc này, mình rút ra một số bài học chính:

1. Benchmark chỉ có giá trị khi dữ liệu, runtime và metric cùng đo đúng một thứ thật.
2. Multi-judge không chỉ là gọi thêm model, mà còn phải xử lý disagreement và fallback.
3. Retrieval metrics cần đủ sâu để chỉ ra hệ thống đang thiếu bằng chứng hay mang quá nhiều nhiễu.
4. Một hệ eval tốt phải nhìn đồng thời chất lượng, độ ổn định và chi phí.

## 6. Nếu có thêm thời gian, mình sẽ làm gì tiếp

Nếu có thêm thời gian, mình muốn tiếp tục theo các hướng sau:

1. Bổ sung `Cohen's Kappa` để đo độ đồng thuận giữa các judge chặt hơn.
2. Hoàn thiện release gate theo cả chất lượng, latency và chi phí.
3. Thêm reranking hoặc query decomposition để cải thiện retrieval.

## 7. Tự đánh giá đóng góp

Mình đánh giá phần đóng góp của mình nằm ở lớp benchmark nền tảng:

- xây dựng benchmark core và multi-judge
- bổ sung retrieval metrics và output report
- sửa benchmark để regression phản ánh đúng runtime và dữ liệu thật

Phần này không phải phần hoàn hảo nhất cho kết quả cuối cùng, nhưng mình nghĩ mình đã góp phần đáng kể vào kết quả benchmark cuối của nhóm để nó trở nên đáng tin hơn và có giá trị kỹ thuật hơn.
