# Cập nhật gộp khái niệm KG

## Thay đổi

- Trong màn hình nạp KG hàng loạt và duyệt một file, danh sách ứng viên có lựa chọn **Gộp với…** cho cả thực thể cùng loại và khác loại.
- Nút **Gộp cùng khái niệm…** cho phép chọn 2–20 thực thể, ID chuẩn, tên chuẩn và loại cuối cùng từ ontology.
- Màn hình rà soát các node đã lưu cũng có chức năng gộp thật. Các nút đánh giá “Cùng khái niệm” / “Khác khái niệm” cũ vẫn chỉ ghi nhận nhận xét.
- Xem trước liệt kê các quan hệ bị ảnh hưởng. Chặn lưu khi loại mới không phù hợp với quan hệ, thuộc tính mâu thuẫn hoặc tạo quan hệ tự nối.
- Khi xác nhận, các node được gộp về một node hoạt động. ID cũ được lưu thành EntityAlias; quan hệ giữ ID, nguồn và bằng chứng. Có KGMergeAudit lưu trạng thái trước khi gộp.
- Lần nhập tiếp theo bằng ID cũ được chuyển về ID chuẩn. Chỉ mục vector được đồng bộ; nếu thất bại, giao diện báo rõ graph đã lưu nhưng vector chưa đồng bộ.

**Chỉ gộp khi người duyệt xác định cùng khái niệm.** Không tự gộp tất cả tên gần giống nhau. Các quan hệ có cùng nội dung nhưng khác nguồn vẫn được giữ để bảo toàn bằng chứng.

## Cập nhật dự án đang chạy

Bản `medical-ai-integrated-merge-patch.zip` là phần thay đổi so với bản đầy đủ có cập nhật concept trước đó. Nếu dự án của bạn cũ hơn, dùng bản đầy đủ và giữ lại cấu hình riêng.

1. Dừng backend bằng Ctrl+C. Sao lưu thư mục dự án và CSDL Neo4j trước khi thực hiện gộp dữ liệu thật.
2. Giải nén ZIP. Chép nội dung thư mục `medical-ai-integrated` vào thư mục dự án hiện tại, chọn ghi đè các file trùng tên. Danh sách file thay đổi có trong `MERGE_PATCH_FILES.txt`.
3. Không xóa `.env`, `venv`, dữ liệu nạp, model hoặc Docker volume. Bản vá này không yêu cầu thay đổi `.env` hay cài lại thư viện.
4. Khởi động lại backend từ CMD:

```bat
cd /d D:\medical_wed\banzip\medical-ai-integrated\backend
venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
```

5. Mở lại màn hình quản lý dữ liệu, nhấn Ctrl+F5 để tải JavaScript mới. Các màn hình thay đổi được backend phục vụ; không cần build lại frontend React cho bản vá này.

## Thao tác

1. Chạy xem trước file KG và mở tài liệu cần duyệt.
2. Chọn **Gộp với…** ở ứng viên, hoặc **Gộp cùng khái niệm…** để chọn nhiều thành viên.
3. Chọn ID giữ lại, tên và loại cuối cùng. Ví dụ hai node “Nhồi máu cơ tim” thuộc Disease / Complication có thể được gộp, với loại cuối cùng do người duyệt chọn.
4. Nhấn **Xem trước gộp**. Nếu có lỗi ontology hoặc thuộc tính, xử lý lỗi trước rồi xem trước lại. Hệ thống không tự bỏ quan hệ để ép gộp.
5. Nhấn **Xác nhận gộp và lưu node chuẩn**. Đây là thao tác ghi Neo4j ngay, kể cả node chưa được nhập trước đó. Việc nhập toàn bộ tài liệu và các quan hệ trong file vẫn là bước riêng.
6. Mở lại tài liệu, xem trước, **Lưu duyệt tài liệu**, sau đó xác nhận nạp như bình thường. File tải từ máy ở màn hình duyệt riêng chỉ được cập nhật trong trình duyệt; tải JSON đã duyệt về nếu cần giữ bản đó. Với nạp hàng loạt, file trên backend được cập nhật.

Bản xem trước hết hạn sau 10 phút hoặc khi dữ liệu thay đổi. Khi khởi động lại backend, cần xem trước lại. Dùng một worker như lệnh trên để các token nằm cùng tiến trình.

## Đồng bộ lại vector khi có cảnh báo

Trong môi trường backend đã kích hoạt và có cấu hình Qdrant/embedding đang dùng:

```bat
python -m scripts.kg.reindex_merged
```

Lệnh xóa vector theo các ID thành viên cũ và lập lại vector node chuẩn của những nhóm đã gộp. Không chỉnh sửa Neo4j hay MongoDB.

## Giới hạn và kiểm tra

- Kiểm thử backend liên quan: **83 đạt, 19 bỏ qua**; các ca bỏ qua phụ thuộc fixture mở rộng không có trong bộ mã nguồn. Đã kiểm tra API, luồng nạp hàng loạt, nhập lại ID cũ, bảo toàn nguồn, xung đột và token hết hiệu lực.
- Kiểm thử DOM cho hộp gộp: chọn khác loại, xem trước không ghi, sửa lựa chọn làm mất hiệu lực token và xác nhận riêng. JavaScript đã kiểm tra cú pháp.
- Chưa kiểm thử tích hợp trực tiếp với Neo4j/Qdrant trên máy người dùng. Nên thử một nhóm nhỏ trên bản sao CSDL trước khi gộp nhiều dữ liệu.
- Mỗi lần tối đa 20 thực thể và 2.000 quan hệ đã lưu. Nhóm lớn hơn cần xử lý riêng.
- Ghi graph là một transaction; ghi file của lượt nạp hàng loạt và đồng bộ vector là bước sau. Nếu ghi file thất bại sau khi graph đã gộp, graph không tự hoàn tác: mở lại lượt xem trước, các ID cũ được chuyển về node chuẩn. Nếu cần khôi phục hoàn toàn, dùng bản sao lưu; bản này chưa có nút hoàn tác.
- Tài liệu/đoạn bằng chứng nguồn không bị sửa nội dung; ID cũ vẫn có thể xuất hiện trong dữ liệu nguồn lịch sử và được giữ để truy vết.
