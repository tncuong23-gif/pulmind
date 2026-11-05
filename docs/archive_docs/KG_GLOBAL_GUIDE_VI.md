# Kho KG toàn cục — hướng dẫn cập nhật và vận hành

## Phạm vi bản này

Nạp nhiều JSON vào một kho nháp chung; đối chiếu và duyệt theo nhóm khái niệm xuyên tài liệu; chốt thành một JSON global có phiên bản; đồng bộ bản đã chốt vào CSDL rồi kích hoạt phục vụ truy vấn.

SQLite là kho làm việc có giao dịch, không ghi đè một JSON khổng lồ sau từng thao tác. JSON global là bản xuất đầy đủ của phiên bản đã chốt. Thực thể dùng ID toàn cục `GE_...`; ánh xạ giữ ID gốc theo tài liệu và phiên bản. Một bộ ba chuẩn chỉ có một bản ghi, nhưng có thể có nhiều phát biểu nguồn, bằng chứng và điều kiện khác nhau. Không xóa bằng chứng chỉ vì trùng bộ ba.

## 1. Cập nhật dự án hiện tại

1. Dừng backend bằng Ctrl+C. Sao lưu thư mục dự án, cấu hình `.env` và các CSDL trước khi cập nhật.
2. Giải nén `medical-ai-integrated-kg-global-patch.zip`. Chép nội dung bên trong thư mục `medical-ai-integrated` vào đúng thư mục dự án hiện tại, chấp nhận ghi đè các file mã nguồn tương ứng.
3. Giữ nguyên `.env`, `venv`, thư mục model và Docker volumes. Bản vá không yêu cầu xóa hay tạo lại CSDL.
4. Bản vá dựa trên bản đầy đủ đã có tính năng khôi phục duyệt KG. Nếu dự án quá cũ hoặc không rõ phiên bản, dùng ZIP đầy đủ trong một thư mục mới, chuyển cấu hình của bạn sang, rồi kiểm tra trước khi thay bản đang chạy.
5. Phần mới dùng SQLite có sẵn trong Python và các thư viện KG hiện hữu. Không cần cài lại môi trường nếu các dependencies hiện tại đã đủ. Khi cài từ đầu, vẫn phải thực hiện hướng dẫn cài dự án và chuẩn bị model riêng; ZIP không thay thế các dịch vụ hay model cần tải.

Chạy backend từ CMD:

```bat
cd /d D:\medical_wed\banzip\medical-ai-integrated\backend
venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
```

Dùng **một worker**: hàng đợi công việc và khóa điều phối của bản này nằm trong tiến trình. Mở:

- `http://127.0.0.1:8100/kg-global`
- Hoặc `http://127.0.0.1:8100/data#kg/global`

Giao diện mới được backend phục vụ trực tiếp, không cần build lại frontend cho phần này.

## 2. Cấu hình và dữ liệu đầu vào

Giữ các biến `KG_NEO4J_*`, `KG_MONGODB_*`, `KG_QDRANT_URL` đúng với dịch vụ đang chạy. Các biến nhận diện thực thể dùng lại cấu hình hiện có:

```dotenv
KG_ENTITY_EMBEDDING_ENABLED=1
KG_ENTITY_MODEL=Dqdung205/medical_vietnamese_embedding
KG_ENTITY_DEVICE=auto
KG_ENTITY_BATCH_SIZE=16
KG_GLOBAL_SIMILARITY_THRESHOLD=0.88
```

`auto` chỉ dùng GPU nếu môi trường model nhận được GPU; biến này không chuyển bản PyTorch CPU thành CUDA. Nếu embedding bị tắt, bước quét chỉ đối chiếu tên và bí danh, không đối chiếu ngữ nghĩa. Nếu embedding bật nhưng model tải/chạy lỗi, bước quét báo lỗi để bạn xử lý, không âm thầm coi là đã quét ngữ nghĩa.

Ngưỡng global chấp nhận 0.5–1, mặc định 0.88. Tương đồng chỉ tạo gợi ý, không tự gộp. Các tên giống nhau khác loại cũng cần quyết định ngữ nghĩa.

Có hai cách nạp:

- Chọn nhiều file JSON trên giao diện, nạp cùng một lượt. File lỗi được ghi vào báo cáo; các file còn lại tiếp tục.
- Đặt JSON trong `backend/data/import/kg/` (có thể có thư mục con), chọn nạp thư mục. Nếu có `BATCH_DATA_ROOT`, đường dẫn là `<BATCH_DATA_ROOT>/import/kg/`.

Giới hạn mỗi JSON đầu vào: 20 MB. Dữ liệu vẫn theo schema KG hiện tại, gồm tài liệu, thực thể, quan hệ và bằng chứng. Tài liệu cùng ID và cùng nội dung không bị nạp lại. Nội dung thay đổi tạo phiên bản mới; phiên bản trước còn trong lịch sử. Sửa file lỗi rồi chỉ tải lại file đó.

## 3. Duyệt nhiều tài liệu cùng lúc

1. Nạp tất cả tài liệu cần đưa vào phiên bản global, kể cả tài liệu đã có ở KG cũ nếu muốn chúng có mặt trong phiên bản mới.
2. Chạy đối chiếu. Danh sách nhóm tập hợp các cặp có khả năng cùng khái niệm, xuyên nhiều tài liệu.
3. Xem thực thể nguồn, quan hệ và bằng chứng. Chọn đúng các thành viên cùng khái niệm, ID chuẩn, tên chuẩn và loại sau gộp rồi xác nhận.
4. Nếu khác khái niệm, chọn giữ riêng. Không chọn toàn nhóm chỉ vì các thành viên có liên kết gợi ý bắc cầu.
5. Hệ thống kiểm tra loại mới với mọi quan hệ bị ảnh hưởng. Nếu không hợp lệ, sửa dữ liệu nguồn/ontology theo ý nghĩa đúng; không bỏ kiểm tra để ép gộp. Quan hệ cần loại khỏi bản xuất phải có lý do, nguồn gốc vẫn được giữ.
6. Sau thao tác làm thay đổi bản nháp, chạy đối chiếu lại trước khi chốt. Các quyết định đã lưu còn hiệu lực nếu không bị thay đổi bởi lần gộp tiếp theo.

Một tài liệu mới có thể tạo thêm gợi ý trùng với khái niệm đã duyệt; bản này không tự gộp chỉ dựa vào tên. Các quyết định là ở cấp nhóm của kho chung, không phải duyệt lần lượt từng tài liệu.

Khẳng định/phủ định và điều kiện được lưu ở cấp phát biểu nguồn. Bộ kiểm tra hiện phát hiện trường hợp `negated` trái nhau với các thuộc tính điều kiện còn lại giống nhau; chưa phải hệ thống phát hiện mọi mâu thuẫn y khoa. Chấp nhận cảnh báo giữ cả hai nguồn, không biến một phát biểu thành chân lý duy nhất.

## 4. Chốt, đồng bộ và kích hoạt

Ba bước riêng biệt:

1. **Chốt phiên bản**: kiểm tra gợi ý chưa duyệt, xung đột cấu trúc và kế hoạch thay đổi. Tạo snapshot bất biến, có thể tải JSON global.
2. **Đồng bộ**: ghi MongoDB, Neo4j và Qdrant (nếu embedding bật). Lỗi dịch vụ làm phiên bản thất bại; phiên bản đang trả lời không đổi. Khi dịch vụ ổn định, đồng bộ lại cùng snapshot. Các ghi được upsert để tránh nhân bản khi thử lại.
3. **Kích hoạt**: chỉ khả dụng khi đồng bộ hoàn tất. Truy vấn KG chuyển sang snapshot này. Phiên bản cũ còn nguyên để quay lui.

**Bản này ghi đầy đủ một snapshot CSDL độc lập cho mỗi phiên bản, chưa chỉ ghi phần chênh lệch.** Kế hoạch hiển thị số đối tượng thêm/xóa/đổi để kiểm tra, nhưng không có nghĩa thao tác vật lý là đồng bộ delta. Đổi lại, không sửa graph đang phục vụ giữa chừng. Cần dự trù dung lượng; chưa có chức năng tự dọn snapshot cũ.

Neo4j dùng nhãn riêng theo snapshot; MongoDB dùng `global_documents`, `global_evidence`, `global_assertions`; Qdrant dùng collection riêng theo snapshot. Dữ liệu KG cũ không bị xóa. Sau khi global hoạt động, luồng nhập/gộp cũ và retry nhập cũ bị chặn ghi để tránh hai luồng thay đổi độc lập.

## 5. Chuyển từ KG cũ và quay lui

Chức năng đối chiếu KG cũ chỉ tạo báo cáo ứng viên ánh xạ theo tên/bí danh và loại. Nó không tự gộp hay sửa node đang có. Quy trình chuyển là nạp lại bộ tài liệu nguồn vào kho nháp, duyệt tập trung, đồng bộ snapshot riêng rồi kích hoạt.

Có thể kích hoạt lại một snapshot đã đồng bộ trước đó, hoặc chọn quay về KG cũ. Yêu cầu đang chạy dùng phiên bản đã chọn lúc bắt đầu; yêu cầu mới dùng phiên bản mới. Không xóa snapshot còn cần quay lui.

## 6. Sao lưu và phục hồi

- Tải JSON global sau khi chốt. File gồm tài liệu gốc, lịch sử tài liệu, ánh xạ, thực thể, bộ ba, phát biểu nguồn, bằng chứng và quyết định duyệt.
- Để sao lưu đầy đủ trạng thái vận hành, dừng backend rồi sao chép **toàn bộ** `backend/data/kg_global/` (hoặc `<BATCH_DATA_ROOT>/kg_global/`), cùng sao lưu CSDL. Không chỉ chép SQLite chính khi còn đang ghi WAL.
- Phục hồi JSON trên giao diện chỉ chấp nhận kho global trống, tối đa 512 MB. Phục hồi thành bản nháp, cần quét/chốt/đồng bộ/kích hoạt lại; không tự thay dữ liệu đang phục vụ.
- Dữ liệu nguồn bị rút khỏi bản nháp không biến mất khỏi lịch sử hoặc snapshot đã chốt.
- Nếu backend khởi động lại giữa tác vụ, hàng đợi trong bộ nhớ không còn. Xem trạng thái snapshot và thử đồng bộ lại; không coi trạng thái `syncing` cũ là đã thành công.

## 7. Giới hạn kiểm chứng

Bản này đã có kiểm thử tự động và kiểm tra nạp bộ 93 JSON. Chưa chạy đồng bộ đầu-cuối trên CSDL và GPU thực tế của bạn. Nên thử một nhóm tài liệu nhỏ ở snapshot riêng, kiểm tra nguồn trả lời rồi mới kích hoạt bộ lớn.

Các truy vấn global dùng tên/bí danh trên graph riêng; chưa dựng full-text index riêng cho mỗi snapshot. Qdrant được đồng bộ khi bật nhưng không có nghĩa mọi truy vấn KG đều dùng vector. Khối lượng lớn có thể cần tối ưu thêm bước đối chiếu và lưu snapshot.
