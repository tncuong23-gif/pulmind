# Sửa luồng duyệt bổ sung khi nạp KG

## Những gì đã sửa

- Gộp hoặc chuyển ID cũ về ID chuẩn chỉ loại bỏ quyết định của thành viên bị gộp; giữ quyết định của thực thể không liên quan.
- Đích liên kết là ID đã gộp được chuyển về ID chuẩn. Bước kiểm tra loại/ontology vẫn áp dụng; không tự bỏ qua xung đột.
- Khi nạp gặp ENTITY_LINK_REVIEW_REQUIRED, báo Cần duyệt bổ sung thay vì Lỗi / Đã duyệt. Hiện tên thực thể và ứng viên cùng loại của ứng viên.
- Có nút Duyệt bổ sung file này ở lượt nạp đã kết thúc. Nút tạo lượt xem trước riêng cho file đó, không tự ghi graph.
- Xem trước lại từ lượt nạp chỉ chọn file lỗi, ghi một phần hoặc cần duyệt. Không đưa các file hoàn tất vào lượt này.
- Báo cáo cũ chứa ENTITY_LINK_REVIEW_REQUIRED không còn hiển thị nhãn Đã duyệt khi mở lại. Kết quả Lỗi lịch sử được giữ; lượt xem trước mới sẽ cập nhật ứng viên theo graph hiện tại.

## Ghi đè

1. Dừng backend (Ctrl+C).
2. Giải nén medical-ai-integrated-review-recovery-patch.zip, chép nội dung thư mục medical-ai-integrated vào dự án đang chạy. Bản vá dựa trên bản gộp khái niệm đã gửi trước đó; danh sách file ở REVIEW_RECOVERY_PATCH_FILES.txt.
3. Giữ nguyên .env, venv, model, dữ liệu và Docker volume. Không cần cài lại dependencies hay xóa CSDL.
4. Chạy lại:

```bat
cd /d D:\medical_wed\banzip\medical-ai-integrated\backend
venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
```

5. Ctrl+F5 trên màn hình quản lý dữ liệu. Không cần build lại React vì màn hình này được backend phục vụ.

## Tiếp tục xử lý báo cáo 93 tài liệu

24 tài liệu đã hoàn tất không cần nạp lại chỉ vì lỗi duyệt của tài liệu khác.

- Mở lượt nạp cũ. Bấm Duyệt bổ sung file này ở file bị chặn, hoặc Xem trước lại để xử lý nhóm chưa hoàn tất.
- Mở Xem / duyệt, xử lý các ứng viên còn xuất hiện. Quyết định hợp lệ đã lưu không cần chọn lại.
- Lưu duyệt tài liệu, chọn file đủ điều kiện và xác nhận nạp.
- Nếu ứng viên mới xuất hiện do tài liệu khác vừa bổ sung graph, hệ thống vẫn yêu cầu duyệt phần phát sinh. Bản sửa không tự gộp theo độ tương đồng và không bảo đảm cả 69 file tự nạp được mà không duyệt.
- Quyết định từng bị xóa trong file bởi bản cũ không thể tự khôi phục từ dấu Đã duyệt: dấu này chỉ lưu hash/thời điểm/số quyết định. Cần duyệt lại phần bị mất hoặc dùng bản JSON đã duyệt còn lưu.

Bản này không thay đổi ontology. Xung đột như PatientGroup với RISK_FACTOR_FOR vẫn cần được xử lý riêng.

## Kiểm thử

86 ca đạt, 19 ca bỏ qua do fixture mở rộng không có trong mã nguồn. Có ca tái hiện duyệt tài liệu → graph được bổ sung → nạp bị chặn → trạng thái cần duyệt bổ sung → duyệt phần mới → nạp thành công; kiểm tra giữ quyết định sau gộp và chuyển đích ID cũ. JavaScript đã kiểm tra cú pháp.

Chưa kiểm thử trực tiếp trên Neo4j/Qdrant Windows của bạn; kiểm thử luồng dùng bộ lưu trữ trong bộ nhớ. Bản vá không thực hiện thao tác nào lên CSDL đang chạy của bạn.
