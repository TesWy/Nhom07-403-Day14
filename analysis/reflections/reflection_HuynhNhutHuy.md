# Reflection Cá Nhân: 
# Huỳnh Nhựt Huy
# Mã học viên: 2A202600084

## 1. Vai trò cá nhân trong nhóm

Phần việc chính mình phụ trách nằm ở giai đoạn chuẩn bị dữ liệu và ổn định hóa benchmark input cho cả nhóm. Cụ thể, mình tập trung vào:

- xử lý lại dữ liệu từ các ngày trước
- kiểm tra chunking và metadata
- đưa bộ tài liệu về đúng cấu trúc của Day 14
- xác minh pipeline đang dùng embedding thật và retrieval thật
- mở rộng thêm benchmark layer dựa trên phần teammate đã làm

## 2. Những việc mình đã làm

### 2.1 Chuẩn hóa dữ liệu và chunk

Mình lấy lại dữ liệu từ các ngày trước, sau đó kiểm tra xem dữ liệu nào thực sự cần giữ lại để tránh duplicate không cần thiết. Vì các bộ tài liệu giữa các ngày gần như giống nhau, mình quyết định chỉ giữ một bộ docs sạch làm nguồn chính để benchmark không bị lặp.

Các việc cụ thể mình đã làm:

- copy bộ docs vào Day 14 và tạo thư mục `documents/`
- kiểm tra lại corpus và raw chunk export
- tách embedding ra khỏi file JSON export để dữ liệu gọn hơn và dễ đọc hơn
- giữ tham chiếu sang ChromaDB thay vì nhét toàn bộ vector vào mỗi row
- xác minh lại mapping giữa `chunk_id` trong corpus và id thực trong ChromaDB
- kiểm tra ngược bằng query theo `chunk_id` để đảm bảo chunk map đúng

Điểm mình thấy quan trọng nhất ở phần này là: benchmark chỉ đáng tin khi chunk id, metadata, và vector store khớp thật với nhau. Nếu phần chuẩn bị dữ liệu sai, toàn bộ hit-rate hay MRR phía sau đều không còn nhiều ý nghĩa.

### 2.2 Kiểm tra lại chất lượng chunking

Sau khi export dữ liệu, mình audit lại kích thước chunk cũ để xem liệu chunk có bị quá to hay không. Kết quả cho thấy chunk text cũ không phình bất thường; phần gây cảm giác file rất to trước đó thực chất là do embedding vector.

Việc kiểm tra này giúp nhóm đưa ra quyết định đúng:

- không re-chunk vội nếu chưa thật sự cần
- giữ chunk gốc để tránh làm mất liên kết với Chroma cũ
- ưu tiên đảm bảo tính nhất quán của benchmark trước khi tối ưu thêm

### 2.3 Mở rộng benchmark từ phần teammate

Sau khi phần benchmark cơ bản đã có sẵn, mình tiếp tục mở rộng thêm các metric để benchmark không chỉ dừng ở score bề mặt. Phần mình bổ sung và tích hợp thêm gồm:

- `context_precision`
- `context_recall`
- `semantic_similarity`
- `position_bias_detection`
- `latency`
- `token usage`
- `cost per eval`

Mình cũng rà lại để các benchmark cũ gọi metric thật thay vì placeholder, đặc biệt là retrieval metrics như `hit_rate` và `mrr`.

Điểm mình quan tâm ở đây là: benchmark phải trả lời được agent sai ở đâu, không chỉ trả lời agent có score cao hay thấp.

### 2.4 Xác minh hệ thống đang chạy với embedding thật

Một điểm mình thấy cần làm rõ trong nhóm là benchmark phải chạy trên embeddings thật và retrieval thật, không phải dữ liệu mock. Vì vậy mình kiểm tra lại:

- corpus có tham chiếu đúng về ChromaDB
- agent đang dùng chunk id thật như `access_control_sop_0`
- retrieval của V2 đang chạy theo vector thật
- benchmark output phản ánh retrieval thực thay vì trả số giả lập

Việc này rất quan trọng vì nếu nhóm demo bằng dữ liệu placeholder thì nhìn ngoài có thể ổn, nhưng benchmark sẽ không có giá trị kỹ thuật.

## 3. Điều mình học được

Điều mình học rõ nhất là phần data prep và benchmark prep thường bị xem là việc phụ, nhưng thực tế lại quyết định độ tin cậy của toàn bộ hệ thống.

Có ba bài học lớn với mình:

1. Nếu corpus và chunk id không sạch, mọi metric phía sau đều dễ trở thành số đẹp nhưng không đáng tin.
2. Hit-rate cao chưa chắc retrieval tốt; cần thêm precision và recall để thấy hệ thống đang thiếu evidence hay chỉ đang mang quá nhiều nhiễu.
3. Một benchmark tốt phải giúp nhóm ra quyết định kỹ thuật tiếp theo, chứ không chỉ để báo cáo điểm số.

## 4. Khó khăn mình gặp

### 4.1 Dữ liệu giữa các ngày bị trùng nhiều

Khó khăn đầu tiên là bộ tài liệu giữa các ngày gần như giống nhau, nên nếu bê nguyên tất cả vào sẽ làm benchmark bị duplicate và khó đọc. Mình phải chọn cách giữ lại một nguồn chính, đồng thời vẫn đảm bảo chunk mapping không bị gãy.

### 4.2 Đường dẫn và placeholder cũ chưa khớp với corpus thật

Một số phần code ban đầu vẫn còn đường dẫn hoặc chunk placeholder kiểu `intro.txt`, `chunk_000`. Mình phải rà lại để agent và benchmark dùng đúng chunk id thật từ corpus Day 14.

### 4.3 Cân bằng giữa format chấm và format phân tích

Một khó khăn khác là `main.py` vừa phải tạo output đúng format để check và chấm tự động, vừa phải giữ đủ thông tin để nhóm phân tích sâu hơn. Phần này đòi hỏi phải tách rõ đâu là output chuẩn để chấm, đâu là metric mở rộng phục vụ nội bộ.

## 5. Nếu có thêm thời gian, mình sẽ làm gì tiếp

Nếu có thêm thời gian, mình muốn tiếp tục theo ba hướng:

1. Re-rank retrieval để tăng `context_precision`.
2. Tách riêng benchmark adversarial và safety để team theo dõi regression dễ hơn.
3. Dọn lại pipeline benchmark để giảm runtime và cost, vì hiện chất lượng đã lên nhưng độ trễ còn khá cao.

## 6. Tự đánh giá đóng góp

Mình đánh giá phần đóng góp của mình nằm ở lớp nền tảng:

- làm sạch và cố định dữ liệu benchmark
- đảm bảo benchmark chạy trên embeddings thật
- làm cho chunk id và tài liệu có thể truy vết được
- mở rộng benchmark để nhóm có thêm góc nhìn kỹ thuật thực sự hữu ích

Phần này không phải phần “hào nhoáng” nhất khi demo, nhưng mình nghĩ nó là phần giúp toàn bộ kết quả benchmark có độ tin cậy cao hơn.
