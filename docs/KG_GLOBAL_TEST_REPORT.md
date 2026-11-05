# Kiểm chứng bản KG global

Ngày: 13/10/2026. Phạm vi: mã nguồn bản tích hợp, chạy trong môi trường kiểm thử cục bộ, không truy cập CSDL Windows của người dùng.

## Kết quả cuối

| Kiểm tra | Kết quả |
|---|---|
| `cd backend` rồi `python -m pytest -q` | 520 passed, 35 skipped, 23 warnings; 8.14 giây |
| Kiểm tra DOM của giao diện global với Node.js/JSDOM | Đạt: một quyết định chứa cả hai thành viên xuyên tài liệu; không tự đồng bộ/kích hoạt |
| Python compileall cho phần thay đổi | Đạt |
| `node --check app/kg_global/web/app.js` | Đạt |
| Nạp thử bộ 93 JSON chuẩn hóa v687 | Không lỗi cấu trúc; 4.953 thực thể trước gộp, 4.812 bộ ba/phát biểu nguồn, 10.251 bằng chứng; 8.567 cặp gợi ý tên/bí danh |

Bước nạp và đối chiếu tên của bộ 93 JSON mất khoảng 1,61 giây trong lần thử cục bộ. Đây không phải đo tốc độ embedding, GPU hoặc đồng bộ các dịch vụ, và không phải cam kết tốc độ trên máy khác.

## Những hành vi đã kiểm tra

- ID cục bộ giống nhau giữa hai tài liệu không bị coi là cùng khái niệm.
- Nạp lại nội dung không đổi không tạo phiên bản thừa.
- Gộp giữ một bộ ba chuẩn nhưng bảo toàn các phát biểu và bằng chứng của nhiều tài liệu.
- Giữ riêng khái niệm; không tự suy ra gộp từ quan hệ bắc cầu.
- Chọn loại sau gộp không hợp lệ bị từ chối mà không thay dữ liệu.
- Chặn quyết định trên revision cũ; buộc quét lại khi bản nháp thay đổi.
- Snapshot bất biến; nguồn rút khỏi bản nháp không xóa nguồn còn lại hoặc lịch sử.
- Xuất/phục hồi global; phục hồi dữ liệu không nhất quán được rollback.
- API yêu cầu xác nhận chốt và kích hoạt; chưa đồng bộ xong không được kích hoạt.
- Đồng bộ lỗi, thử lại và trạng thái ready được kiểm tra bằng driver giả lập; không ghi vào nhãn graph cũ.
- Truy vấn chọn nhãn snapshot, giữ thuộc tính từng phát biểu nguồn.
- Kiểm thử hồi quy các phần backend hiện có.

## Điều chỉnh môi trường và fixture

Lần chạy mở rộng đầu phát hiện fixture importer cũ chưa có thuộc tính `graph` theo hợp đồng hiện tại; đã bổ sung graph giả lập vào fixture, không bỏ kiểm tra chức năng.

Môi trường có scikit-learn 1.8.0, trong khi model đóng gói và `requirements.txt` dùng 1.6.1. Chạy lại bằng đúng 1.6.1 đã giải quyết lỗi tương thích model; không thay file model và không nới điều kiện kiểm thử.

35 ca được bộ kiểm thử đánh dấu bỏ qua theo điều kiện môi trường/fixture; chúng không được tính là đã đạt. 23 cảnh báo thuộc API FastAPI/Starlette cũ, không phải kết quả xác nhận an toàn của dịch vụ thực tế.

## Chưa xác minh và giới hạn

- Chưa kiểm thử đầu-cuối với Neo4j, MongoDB, Qdrant và model embedding thật của người dùng; driver giả lập không thay thế kiểm thử tích hợp đó.
- Chưa đo hiệu năng trên RTX 4060 của người dùng; chưa thử lỗi mất mạng giữa các dịch vụ thật.
- UI được kiểm tra DOM, chưa xác minh hình ảnh trên mọi trình duyệt và kích thước màn hình.
- Đồng bộ ghi toàn bộ snapshot riêng theo phiên bản, chưa tối ưu delta. Không tự dọn bản cũ.
- Nhận diện mâu thuẫn chỉ bao phủ khẳng định/phủ định có cùng các thuộc tính còn lại; vẫn cần duyệt nội dung nguồn.
- JSON global là bản xuất từ kho SQLite có giao dịch, không phải file duy nhất để nhiều tiến trình ghi trực tiếp. Cần chạy backend một worker.

Các file kiểm thử mới: `backend/tests/test_kg_global.py`, `backend/tests/kg_global_ui.cjs`. Với JSDOM có sẵn trong môi trường Node, chạy `node tests/kg_global_ui.cjs` từ backend. Quy trình cập nhật, thử nghiệm nhỏ và quay lui nằm trong `KG_GLOBAL_GUIDE_VI.md`.
