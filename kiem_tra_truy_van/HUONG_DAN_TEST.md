# Kiểm tra truy vấn medical-ai-integrated và thu log

## Cách chạy đề nghị

1. Giải nén và chép **toàn bộ các file** trong ZIP vào `D:\medical_wed\banmoi\medical-ai-integrated\`, cùng cấp với `backend`. Đặc biệt giữ `test_queries.py` cạnh các BAT. Không chạy trong cửa sổ xem ZIP.
2. Dừng backend/ứng dụng đang chạy để tránh hai tiến trình nạp model cùng lúc. Giữ Neo4j, MongoDB, Qdrant, Ollama và Clinical IE (nếu sử dụng) chạy như bình thường.
3. Nhấp đúp **`TEST_TAT_CA_TRUY_VAN.bat`**. BAT tự nhận thư mục `backend` bên cạnh và ưu tiên Python trong `backend/.venv` hoặc `backend/venv`.
4. Bộ test kiểm tra classifier riêng, sau đó tự mở backend chẩn đoán tại `127.0.0.1:8111`, lần lượt gửi các truy vấn và ghi log. Không cần mở giao diện frontend, không cần sửa `main.py` để có traceback.
5. Khi xong, tìm dòng **`SEND THIS ZIP:`**. Gửi ZIP được chỉ ra cho trợ lý. ZIP nằm trong `query_test_logs/<thời điểm>/<mã>-query-logs.zip`, cạnh BAT. Mỗi lần chạy có thư mục riêng.

Đây là công cụ kiểm tra, không phải bản cập nhật code. Nó không sửa code ứng dụng, không nhập/xóa KG và không dọn dữ liệu.

## Chọn BAT

| File | Khi dùng |
| --- | --- |
| **`TEST_TAT_CA_TRUY_VAN.bat`** | Đề nghị dùng: toàn bộ catalogue truy vấn hiện có + chat, có backend.log và traceback |
| `TEST_NHANH.bat` | Một tập nhỏ để chẩn đoán nhanh, không quét từng quan hệ ontology |
| `TEST_CLASSIFIER_CPU.bat` | Chạy nhanh với classifier dùng CPU để so sánh khi nghi lỗi CUDA; không đổi cấu hình `.env` |
| `TEST_BACKEND_DANG_CHAY.bat` | Test HTTP backend đã chạy ở cổng 8100; **không lấy được traceback của tiến trình đó**, bỏ qua probe nặng để tránh nạp thêm model |

Không chạy nhiều BAT cùng lúc. BAT chính tự dừng backend chẩn đoán khi hoàn thành. Trình duyệt không cần mở. Sau đó bạn có thể mở lại ứng dụng bằng bộ chạy thông thường.

## Phạm vi kiểm tra

- Phiên bản Python, package liên quan, Torch/CUDA và thử chạy trực tiếp bộ phân loại E5+SVM trên câu hỏi mẫu; giữ nguyên cách cấu hình classifier của ứng dụng.
- Các nhóm classifier: đánh giá chẩn đoán, ngoài phạm vi, y khoa tổng quát, quan hệ KG và giải thích/quản lý lâm sàng. Lưu nhãn thực tế để đối chiếu, không coi nhãn tham khảo là gold label đã duyệt y khoa.
- KG: `auto`, `one_hop`, `multi_hop`, `path`, `compare`, `common`, `difference`, `inference`; các hướng `auto/out/in/any`; chuỗi tùy chọn; có/không kèm evidence.
- Từng intent, preset và quan hệ được API catalogue/ontology công bố. Danh sách được lấy lúc chạy; nếu API meta lỗi, thử dùng catalogue từ code cục bộ. Không giả định số lượng preset hay quan hệ cố định.
- Hai luật suy luận `is_a_transitive`, `part_of_transitive`, với evidence cùng tài liệu và chéo tài liệu.
- Tên chuẩn, alias, từ viết tắt mơ hồ và tên không tồn tại.
- RAG: tìm trên `all`, `chunk`, `proposition`.
- Công cụ KG hỗ trợ đánh giá: coverage, mapping; followups với fixture hư cấu nếu có entity Symptom trong snapshot. Fixture đánh dấu rõ `SYNTHETIC_TEST_NOT_A_REAL_PATIENT`; không phải dữ kiện bệnh nhân thật.
- Chat tổng hợp và ba lượt ngữ cảnh liên tiếp; ghi cả kết quả yêu cầu làm rõ, route, nhãn classifier, lỗi và thời gian.
- Bảy đầu vào không hợp lệ: trắng, mode sai, giới hạn sai, số bước sai, trộn ID và tên, thiếu chuỗi và preset không tồn tại. Chúng cần trả HTTP 422; đây là kiểm tra thành công khi hệ thống từ chối đúng.

Không kiểm tra âm thanh, upload ảnh/hồ sơ, import KG hoặc toàn bộ thao tác tương tác của phiên đánh giá. Không có bộ test hữu hạn nào bảo đảm mọi câu hỏi tự nhiên; gói này kiểm tra các chế độ được code/API hiện tại cung cấp.

## Cách đọc kết quả

- `HTTP_ERROR` / `CONNECTION_ERROR`: lỗi HTTP hoặc lỗi kết nối; xem requests.jsonl và backend.log.
- `HTTP_OK`: API đáp ứng mã HTTP mong đợi; **không chứng minh nội dung trả lời đúng y khoa hoặc route đúng**.
- `NO_FACTS`, `NO_ENTITY`, `NEEDS_CLARIFICATION`: không coi là lỗi máy chủ, nhưng nhánh truy vấn sâu có thể chưa được thực thi. Log giữ trạng thái riêng, không đánh dấu tất cả thành công chỉ vì HTTP 200.
- Nếu có nhiều entity trùng tên, bộ test dùng ID mẫu từ snapshot active để kiểm tra các nhánh sâu. Các lượt test alias vẫn giữ tên để kiểm tra xử lý mơ hồ. Nếu kho không có snapshot active hoặc không có mẫu phù hợp, kết quả có thể dừng ở làm rõ thực thể.
- `summary.json` ghi catalogue đã phát hiện, số lượt, các lỗi, trạng thái probe và việc chạy bị gián đoạn hay không.
- Mã thoát 2 nghĩa là có lỗi được ghi nhận hoặc test chưa hoàn thành; không cần xóa log hay chạy lại trước khi gửi ZIP.

## Các file gửi lại

ZIP kết quả tự gom:

- `backend.log`: startup module, các bước chat và traceback (chế độ backend chẩn đoán).
- `classifier-probe.log`: lỗi model/encoder/Torch riêng, kể cả AssertionError không có thông báo.
- `environment.json`: phiên bản runtime/package và device được chọn.
- `requests.jsonl`: câu hỏi/payload mẫu, HTTP response, mã lỗi, request_id, thời gian và kết quả từng lượt.
- `catalog.json`, `live-catalog.json`: các loại truy vấn/ontology và ID mẫu KG cần đối chiếu.
- `summary.json`, `summary.txt`, `runner-error.log` nếu có lỗi runner.

Không đóng gói `.env`, trọng số model, thư mục upload hoặc file SQLite. Dạng mật khẩu/token phổ biến trong log được che tự động; vẫn nên xem qua ZIP nếu dịch vụ bên ngoài tự ghi thông tin nhạy cảm vào log.

Backend chẩn đoán dùng SQLite hội thoại riêng trong thư mục log và ID hội thoại/patient mẫu có tiền tố `diag-`; không đọc các cuộc trò chuyện cũ để dựng ca test. Các dịch vụ bộ nhớ ngoài có thể lưu các lượt hội thoại mẫu này như một phiên sử dụng thông thường. Chế độ test backend đang chạy cũng tạo hội thoại mẫu trong kho của tiến trình đang chạy, nhưng không tự xóa chúng.

## Lưu ý vận hành

- Chạy đủ có thể mất nhiều phút hoặc lâu hơn nếu model/dịch vụ chậm. Mặc định mỗi request, startup và probe có timeout 180 giây. Các ca lỗi độc lập vẫn được chạy tiếp.
- Cần môi trường Python của backend đã cài thư viện. Bộ test không cài lại thư viện hoặc thay model. Nếu model chưa cache, thư viện có thể tải model theo cấu hình ứng dụng như khi chat bình thường.
- BAT CPU chỉ ép `CLASSIFIER_DEVICE=cpu` trong tiến trình test; không ép mọi model khác về CPU. Vì vậy phải so sánh riêng classifier-probe.log khi chẩn đoán CUDA.
- Có thể bấm Ctrl+C để kết thúc và lưu phần log đã có. Không đóng cửa sổ bằng nút X nếu muốn runner kịp đóng gói.
- Cổng 8111 cần trống. Nếu không, runner ghi lỗi và đóng gói log, không dừng tiến trình đang chiếm cổng.
- Chưa chạy trên Windows, CSDL hoặc model thực tế của bạn. Self-test đi kèm sử dụng máy chủ HTTP mô phỏng và mô phỏng backend startup thất bại; các dòng HTTP 502 trong SELF_TEST_RESULTS.txt là lỗi chủ ý để kiểm tra việc thu log.

## Chạy bằng dòng lệnh (tùy chọn)

```bat
backend\.venv\Scripts\python.exe test_queries.py --project .
backend\.venv\Scripts\python.exe test_queries.py --project . --quick --timeout 60
backend\.venv\Scripts\python.exe test_queries.py --project . --device cpu --quick
backend\.venv\Scripts\python.exe test_queries.py --project . --existing http://127.0.0.1:8100
```

Tự kiểm tra công cụ: đặt `MEDICAL_TEST_PROJECT` là thư mục dự án có backend, rồi chạy `python test_harness.py` bằng Python đã cài dependency của backend. Việc này không dùng model hoặc database thật.

## Sửa lỗi Windows charmap

Bản này đọc catalog JSON bằng UTF-8 (kể cả BOM), đồng thời đặt chế độ UTF-8 cho tiến trình Python con. Ghi đè các file của bộ test trong `kiem_tra_truy_van`, giữ nguyên thư mục `query_test_logs`, rồi chạy lại BAT. `Classifier probe exit: 1` là trạng thái lỗi model/encoder riêng; xem classifier-probe.log trong ZIP kết quả, không quy lỗi đó cho charmap.
