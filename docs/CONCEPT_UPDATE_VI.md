# Cập nhật khái niệm KG — 13/10/2026

## Kết quả và giới hạn

Đã rà soát corpus 93 tài liệu. Bản chuyển đổi hợp nhất **78 nhóm tên trùng khác loại**, ánh xạ **89 ID cũ** về ID chuẩn đã tồn tại; có **158 lượt khai báo** được đổi ID trong các tài liệu. Sau chuyển đổi còn **86 nhóm khác loại cần duyệt**. Đây là bản chuẩn hóa có kiểm soát, không phải tuyên bố toàn bộ corpus đã được chuyên gia xác nhận đúng nội dung.

Những nhóm được xử lý gồm hen phế quản, đợt cấp COPD, lao phổi, bệnh tim mạch, tiêu chảy, buồn nôn, đau bụng, đau đầu và thông khí không xâm lấn. Một khái niệm có thể tham gia nhiều quan hệ: bệnh hen có thể là yếu tố nguy cơ; triệu chứng có thể là tác dụng bất lợi của thuốc. Vai trò này được giữ trong quan hệ, không cần tạo node riêng chỉ vì vai trò khác nhau.

Các trường hợp như can thiệp nội soi so với thủ thuật chẩn đoán, các loại chung/chuyên biệt hoặc tên trích xuất chưa rõ không tự gộp. “Do trào ngược dạ dày - thực quản” loại PreventiveMeasure trong DOC_000038_STT_09 vẫn cần đối chiếu câu nguồn và quan hệ; không tự sửa thành bệnh trào ngược.

## Các phần đã thay đổi

- Bảng quyết định `backend/examples/kg/concept_identity_policy.json` xác định từng ID + tên + loại cũ và ID chuẩn. Không áp dụng quy tắc ưu tiên loại tùy tiện cho dữ liệu mới; không tự gộp theo điểm embedding.
- Bổ sung công cụ `python -m scripts.kg.normalize_corpus` chuyển đổi ngoại tuyến, kiểm tra ontology và xuất báo cáo. File gốc không bị ghi đè bởi lệnh này.
- Import chặn các ID cũ đã có quyết định chuẩn hóa bằng lỗi `CONCEPT_NORMALIZATION_REQUIRED`. Dùng corpus mới để nạp. Việc chặn giúp không tái tạo node đã chuẩn hóa nếu vô tình tải lại bộ cũ. ID không khớp tên/loại bị chặn để kiểm tra.
- Ontology mở rộng có giới hạn: bệnh có thể tham gia quan hệ yếu tố nguy cơ, bệnh/triệu chứng có thể là kết quả bất lợi; tác nhân vi khuẩn/virus/ký sinh trùng giữ loại cụ thể; đợt cấp có thể có quan hệ chẩn đoán. Không bỏ kiểm tra domain/range.
- Truy vấn chuỗi tác dụng phụ giữ cả Symptom, Disease, ClinicalSign, LaboratoryFinding và AdverseDrugReaction, tránh mất kết quả sau chuẩn hóa.
- Gộp các ứng viên duyệt trùng ID/loại từ tra cứu tên và embedding thành một dòng; giao diện hiển thị loại đầu vào, loại và ID ứng viên.
- Giữ ánh xạ ID cũ trong metadata tài liệu và `entity_id_map` khi import. Không thay đổi câu nguồn, văn bản mệnh đề, bằng chứng, ID quan hệ hay thuộc tính quan hệ. Các quyết định duyệt cũ của file bị chuyển đổi phải thực hiện lại.

## Cách áp dụng trên dự án đang chạy

1. Dừng backend, sao lưu mã nguồn và CSDL. Không xóa dữ liệu hiện có.
2. Bản vá `medical-ai-integrated-concept-patch.zip` áp dụng cho bản verified-full có cập nhật KG identity/fallback vừa bàn giao trước đó. Giải nén và chép nội dung thư mục `medical-ai-integrated` vào thư mục dự án cùng tên.
3. Giữ nguyên `.env`, venv, mô hình và dữ liệu riêng. Không cần cài lại dependencies. Nếu có `KG_ONTOLOGY_PATH` trỏ đến ontology riêng, phải đối chiếu các bổ sung trong `backend/examples/kg/kg_ontology.example.json` với file đang dùng; không ghi đè ontology tùy biến một cách máy móc.
4. Khởi động lại backend:

```bat
cd /d D:\medical_wed\banzip\medical-ai-integrated\backend
call venv\Scripts\activate.bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
```

5. Làm mới trang quản trị để tải JavaScript mới. Bản này sửa giao diện quản trị do backend phục vụ; không đổi React frontend hay dependencies.
6. Giải nén `CORPUS_v687_CONCEPT_NORMALIZED.zip`. Chỉ chọn file trong **documents/** để nạp. Không nạp reports/ hoặc file báo cáo thành tài liệu. Đọc báo cáo trước khi bấm duyệt các mục còn lại.

**Nếu KG hiện tại đã chứa node cũ:** nạp corpus mới không tự xóa/gộp các node đó, nên vẫn có thể gặp cảnh báo khác loại. Cần xuất báo cáo KG hiện hữu và lập bước chuyển dữ liệu riêng, hoặc thử corpus trong CSDL KG biệt lập trước. Không dùng “Giữ riêng tất cả” để bỏ qua và không xóa toàn bộ Neo4j đang có Patient Graph. Chỉ tạo lại chỉ mục embedding sau khi dữ liệu graph thực tế đã chuyển đổi; bản vá không tự thực hiện chuyển đổi CSDL.

## Chạy lại chuyển đổi khi cần

Trong thư mục backend, với venv của dự án:

```bat
python -m scripts.kg.normalize_corpus D:\du_lieu\CORPUS_v687_CLEAN_UNIQUE_DOCIDS.zip D:\du_lieu\CORPUS_v687_CONCEPT_NORMALIZED.zip
```

Nếu dùng ontology riêng, thêm `--ontology D:\du_lieu\ontology.json`. Công cụ không kết nối CSDL. Khi có tài liệu không hợp lệ, đưa vào invalid/ và báo lỗi, không âm thầm bỏ tài liệu. Những tên/ID ngoài bảng quyết định được giữ nguyên để đi qua quy trình duyệt thông thường.

## Báo cáo và kiểm chứng

Trong ZIP corpus:
- `reports/normalization-report.json`: ánh xạ theo từng tài liệu, thống kê, lỗi validation và nhóm chưa giải quyết.
- `reports/review-pending.json`: 86 nhóm cần duyệt, kèm ví dụ quan hệ/mệnh đề/câu nguồn.
- `reports/review-pending.md`: bảng đọc nhanh.

Kết quả kiểm tra bản này:
- 93/93 tài liệu hợp lệ về schema, tham chiếu và ontology đi kèm.
- Kiểm tra toàn bộ corpus: giữ văn bản tài liệu, mệnh đề, bằng chứng, ID và thuộc tính quan hệ; chạy chuyển đổi lần hai không thay đổi kết quả.
- 64 kiểm thử mục tiêu đạt; 19 kiểm thử cần bộ ví dụ KG mở rộng bị bỏ qua. Có kiểm thử import, ánh xạ ID, thuộc tính xung đột, chặn ID cũ và cấu hình truy vấn.
- DOC_000001 nạp thành công vào graph giả lập rỗng, không bật đề xuất vector: 112 thực thể. Kết quả này không bảo đảm graph hiện tại của bạn không có xung đột.
- Kiểm tra cú pháp JavaScript hai màn hình quản trị thành công. Chưa chạy trình duyệt thật, CSDL thực hay toàn bộ bộ kiểm thử tích hợp của dự án trong lượt này.

Bản đầy đủ vẫn không chứa `.env` riêng, CSDL, môi trường Python, node_modules hoặc trọng số chưa được cung cấp. Hai trọng số Clinical NLP joint/simplifier đã nêu trong VERIFIED_UPDATE_VI.md vẫn cần có trên máy để chạy suy luận tương ứng.
