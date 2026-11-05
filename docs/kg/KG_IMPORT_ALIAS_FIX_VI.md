# Bản sửa import KG và alias — 05/11/2026

Đã sửa mã nguồn từ `pulmind-main(1).zip`. Chưa triển khai lên hệ thống đang chạy và chưa đọc/ghi Neo4j hoặc MongoDB thực tế. JSON nguồn không bị chỉnh sửa.

## Hành vi sau sửa

- Graph mới chỉ xuất entity là đầu mút của bộ ba trong snapshot. Entity không có cạnh vẫn nằm trong tài liệu nguồn, SQLite và JSON snapshot.
- Không tạo node `Term`, constraint cho Term hoặc cạnh `DENOTES` trong graph mới. Alias vẫn là thuộc tính node, có thêm `normalized_aliases` dùng cùng `fold()` với import.
- Tên chuẩn hoặc alias trùng chỉ tạo ứng viên tra cứu; **không tự hợp nhất**, kể cả trùng tên chuẩn cùng loại. ID cục bộ được giới hạn trong từng tài liệu. Bản cập nhật giữ ID toàn cục khi ID nguồn, loại và tên chuẩn sau `fold()` không đổi.
- Hợp nhất phải là quyết định rõ ràng. Kiểm tra thuộc tính mâu thuẫn, domain/range và self-loop trước khi ghi. Quyết định `distinct` tiếp tục có hiệu lực sau khi một thành viên hợp nhất với entity thứ ba.
- Tên chuẩn đã duyệt được giữ trong `reviewed_name`, có audit chứa tên, loại, ID đại diện và danh sách ID được gộp. Nếu chưa duyệt, giữ tên khai báo từ nguồn hiện hành; không tự chọn tên theo độ dài hay suy diễn chuyên môn.
- Alias và thuộc tính được dựng lại từ các nguồn đang active. Alias mất toàn bộ nguồn hỗ trợ không còn được dùng tìm kiếm; lịch sử khai báo vẫn còn. Alias có thể được chấp nhận/từ chối kèm lý do; quyết định từ chối được ưu tiên nếu các entity được hợp nhất.
- `exact_term_candidates` hỗ trợ nhiều entity cho một `(type, term)`. `exact_terms` được giữ làm chỉ mục tương thích và chỉ chứa thuật ngữ không mơ hồ.
- Truy vấn exact lấy cả tên chuẩn và alias phù hợp, tránh bỏ sót trường hợp một chuỗi vừa là tên chuẩn của A vừa là alias của B. Mặc định không mở rộng anchor qua `ALIAS_SIBLINGS`. `EntityLookup` hiện có đã hỗ trợ danh sách ứng viên và yêu cầu làm rõ khi mơ hồ nên không cần sửa file này.

## Kiểm soát publication

`build_projection()` kiểm tra loại quan hệ trong ontology, đầu mút, domain/range, tên entity, assertion và evidence trước khi ghi database. Các cạnh giữ `global_assertions` tương thích consumer hiện có, bổ sung `assertion_id`, phiên bản tài liệu và ID quan hệ gốc.

Trong cùng giao dịch ghi Neo4j, `verify_projection()` đọc lại toàn bộ node/cạnh thuộc snapshot và so sánh:

1. ID, tên chuẩn, loại, alias chuẩn hóa và thuộc tính node.
2. ID cạnh, source, target, loại quan hệ và toàn bộ assertion JSON.
3. Cạnh ngoại lai có một đầu mút thuộc snapshot, cạnh trùng ID, node thừa/thiếu và node Term; kiểm tra riêng cạnh trỏ ra ngoài label snapshot và node cô lập.

Vì tập node kỳ vọng chính là hợp các đầu mút nên so sánh chính xác cũng bảo đảm không có node cô lập. Sai lệch làm giao dịch graph thất bại và snapshot chuyển `failed`. Mongo có thể còn dữ liệu của snapshot thất bại, nhưng không được chọn làm active. Chỉ sau khi các bước ghi thành công, `ready` mới được ghi. `activate()` yêu cầu chứng nhận verification đúng phiên bản và đúng thống kê đối với snapshot `triples_only` mới.

Đồ thị không bắt buộc liên thông. Không tạo cạnh giả và không thay quan hệ y khoa bằng `RELATED_TO`.

## Những file thay đổi

| File (tính từ gốc dự án) | Thay đổi |
| --- | --- |
| `backend/app/direct_import/store.py` | Chính sách identity v2; ngừng tự gộp; chỉ mục nhiều ứng viên; alias theo nguồn hiện hành; quyết định alias; phục hồi metadata |
| `backend/app/kg_global/projection.py` (mới) | Xây projection bộ ba và đối chiếu graph thực ghi |
| `backend/app/kg_global/publish.py` | Lọc node theo đầu mút; bỏ Term/DENOTES; verify trong transaction; vector index dùng đúng entity trên graph |
| `backend/app/kg_global/store.py` | Bảo toàn mappings gốc bằng redirects; tên chuẩn được duyệt; duy trì distinct qua merge; gate activate; hook phục hồi metadata |
| `backend/app/direct_import/service.py` | Kết quả nhập bổ sung thống kê graph, số thuật ngữ mơ hồ và cảnh báo identity cũ |
| `backend/app/direct_import/api.py` | API đọc và quyết định identity/alias trên bản nháp, bảo vệ bằng revision và khóa thao tác |
| `backend/app/direct_import/web/index.html`, `web/app.js` | Hiển thị thống kê nguồn/graph, cảnh báo, danh sách ứng viên và thao tác duyệt |
| `backend/app/modules/kg_query/cypher.py` | Tìm tên và alias chuẩn hóa trong cùng bước exact; fallback cho graph cũ chưa có normalized_aliases |
| `backend/app/modules/kg_query/service.py` | Tắt mặc định alias-sibling expansion; giữ matched_by cho từng ứng viên |
| `backend/tests/test_direct_import.py`, `test_kg_global.py` | Cập nhật kỳ vọng theo chính sách mới; kiểm tra lỗi ghi/thiếu cạnh và activation |
| `backend/tests/test_kg_projection.py` (mới) | Hồi quy projection, provenance, alias, identity, restore và dựng lại registry |
| `backend/tests/direct_import_ui.cjs` (mới) | Kiểm tra UI gửi quyết định rõ ràng với revision, không tự publish |
| `backend/scripts/kg/audit_kg_source.py` (mới) | Kiểm toán JSON chỉ đọc |
| `backend/scripts/kg/audit_neo4j_graph.py` (mới) | So sánh projection của snapshot với Neo4j, chỉ đọc |
| `backend/scripts/kg/rebuild_identity_registry.py` (mới) | Dựng registry mới từ nguồn active của kho cũ; không kế thừa các merge cũ |
| `backend/scripts/kg/verify_kg_fixture.py` (mới) | Hồi quy toàn bộ JSON qua SQLite/snapshot/projection tạm |

Luồng `/direct-import` hiện có là luồng chính; `LegacyImportGuard` chặn các đường ghi import/review cũ. Không sửa adapter legacy. Kiểm tra `data_workspace/api.py` và lớp truy vấn snapshot cho thấy đã dùng label active; không cần thay chúng. Không tìm thấy consumer backend cần đọc Term/DENOTES. Các truy vấn/script tự viết bên ngoài dự án vẫn cần được kiểm tra khi triển khai.

## Sử dụng giao diện và API identity

Trong `/direct-import`, chọn **Đọc danh sách** ở phần tên/alias cần phân biệt. Chọn đúng các entity, ID đại diện và tên chuẩn trước khi hợp nhất. Có thể xác nhận các entity khác nhau hoặc loại alias khai báo sai. Những thay đổi này chỉ tác động bản nháp; **nhập lại file** để tạo, verify và kích hoạt snapshot mới. Snapshot active trước đó tiếp tục phục vụ cho đến khi bước này hoàn tất.

- `GET /api/v1/direct-import/identity`: revision, entities, ambiguous_terms, cảnh báo và alias_decisions của bản nháp.
- `POST /api/v1/direct-import/identity`: thao tác `merge`/`distinct` với `revision`, `ids`; merge cần thêm `target_id`, `type`, `name`.
- Với alias: `action: "alias"`, `revision`, `entity_id`, `term`, `status: "accepted" | "rejected"`, `reason`. Canonical name không thể bị loại qua thao tác alias. Chỉ áp dụng alias có khai báo trong nguồn active.
- Mỗi quyết định thay revision; yêu cầu dùng revision cũ bị từ chối. Việc chấp nhận alias không xác nhận các entity dùng alias đó là cùng một định danh.

## Dữ liệu thực được kiểm tra

Chạy bằng ontology mặc định hiện có, không sửa ontology để làm dữ liệu hợp lệ.

| Chỉ số | Kết quả offline |
| --- | ---: |
| Entity nguồn | 6.194 |
| Relation nguồn / bộ ba duy nhất | 6.930 / 6.930 |
| Proposition nguồn | 4.483 |
| Entity thuộc projection | 5.324 |
| Entity chỉ giữ ở nguồn | 870 |
| Assertion | 6.930 |
| Evidence | 4.974 |
| Nhóm tên/alias trùng cùng loại | 50 |
| Alias khai báo | 402 |
| Đầu mút không tồn tại / lỗi validation | 0 / 0 |
| Redirect tự sinh trong kho mới | 0 |

Toàn bộ source/type/target và proposition_ids đã được so sánh sau ánh xạ. Nhập lại JSON giữ nguyên snapshot. Số cạnh sau các quyết định hợp nhất thủ công có thể giảm; phải đối chiếu snapshot mới, không áp đặt 6.930 cho mọi trường hợp.

`kg_merged (5).json` đơn lẻ không có các sidecar ánh xạ tài liệu gốc. Kiểm thử bảo toàn những liên kết proposition/evidence có trong file; không suy ra nguồn bên ngoài mà JSON không cung cấp. Muốn truy vết sâu đến tài liệu thành phần, cần gói mapping nguồn đúng theo hợp đồng ZIP hiện có.

## Kết quả kiểm thử và giới hạn

Xem `validation/focused-tests.txt`, `patched-tests.txt`, `consumer-tests.txt`, các log baseline và JSON audit kèm theo. Các nhóm lỗi có sẵn được đối chiếu với mã gốc cùng môi trường; không sửa ontology/preset hoặc luồng legacy review ngoài phạm vi để làm xanh kiểm thử.

- Kiểm thử trọng tâm mới: **82 pass**, không có lỗi; xem `validation/focused-tests.txt`.
- Kiểm thử mở rộng import/query/workspace: 5 lỗi đã tồn tại trong bản gốc, do ontology/preset không khớp (`DrugCombination`, `regimen_dosage`, `guideline_interventions`, số loại/quan hệ kỳ vọng).
- Nhóm consumer chat/RAG/review: 10 lỗi đã tồn tại trong bản gốc; bản gốc và bản sửa cùng 249 pass, 2 skip. Chủ yếu là preset/chuỗi truy vấn và workflow review legacy.
- 27 bài integration được bỏ qua tổng cộng trong hai nhóm mở rộng do điều kiện môi trường của chúng.
- JavaScript đã kiểm tra cú pháp và chạy tương tác với DOM mô phỏng. Chưa kiểm tra trình duyệt thật.
- Chưa chạy Neo4j/MongoDB server thật; kiểm thử Publisher dùng kết nối mô phỏng để đưa lỗi ghi và làm mất cạnh có chủ ý. Không coi số liệu projection offline là số liệu đã ghi lên máy chủ của bạn.

## Triển khai, di trú và rollback

1. Dừng writer/import job; ghi lại snapshot active và cấu hình ontology/đường dẫn dữ liệu. Sao lưu nhất quán SQLite bằng SQLite backup API; sao lưu MongoDB/Neo4j theo công cụ vận hành tương ứng. Không chỉ chép file SQLite khi WAL đang có writer.
2. Triển khai mã vào môi trường thử, giữ nguyên cấu hình nguồn và không gộp dữ liệu mới với bản cũ chỉ vì tên giống.
3. Nếu kho cũ từng tự gộp alias: bản sửa **không tự tách các merge đã lưu**. Có cảnh báo dựa trên audit cũ. Chạy công cụ dưới đây với **đường dẫn đích mới**, giữ nguyên kho cũ để truy vết/rollback. Công cụ chỉ chuyển các tài liệu active và provenance; lịch sử cũ, quyết định duyệt cũ và snapshot cũ vẫn nằm trong kho nguồn, không tự chuyển thành quyết định mới.
4. Kiểm tra bản nháp và duyệt identity cần thiết. Nếu dùng registry mới, chỉ đổi đường dẫn cấu hình khi đã kiểm tra và sao lưu; công cụ không tự đổi cấu hình hoặc active pointer.
5. Nhập qua `/direct-import` với gói nguồn đúng. Publisher tạo label snapshot mới, verify rồi mới activate. Theo dõi job để phân biệt phần KG và RAG khi `target=both`.
6. Chạy `audit_neo4j_graph.py` sau publish, đối chiếu một số truy vấn tên chuẩn, alias mơ hồ và nguồn evidence trong KG Explorer/RAG. Chỉ nghiệm thu live sau bước này.
7. Rollback: dừng writer, phục hồi bản mã và bộ dữ liệu/cấu hình đã sao lưu, hoặc chọn snapshot cũ đã ready trong kho tương ứng bằng quy trình vận hành sẵn có. Snapshot cũ không bị viết lại. Không chạy `MATCH (n) DETACH DELETE n`; không xóa graph legacy/Term cũ trong bản vá này.

Các lệnh chạy từ thư mục `backend`:

```bash
python scripts/kg/audit_kg_source.py "/path/kg_merged (5).json"
python scripts/kg/verify_kg_fixture.py "/path/kg_merged (5).json"
python scripts/kg/rebuild_identity_registry.py --source "/path/old/global.sqlite3" --destination "/path/new/global.sqlite3"
python scripts/kg/audit_neo4j_graph.py --snapshot S_0123456789abcdef0123456789abcdef
python -m pytest tests/test_direct_import.py tests/test_kg_global.py tests/test_kg_projection.py -q
```

Dùng `--ontology` cho các script nguồn/di trú khi không dùng ontology mặc định. Script audit live lấy cấu hình `KG_*` và kho `BATCH_DATA_ROOT` như ứng dụng. Thay ID snapshot minh họa bằng ID thật; bỏ `--snapshot` để đọc active. Không đưa mật khẩu vào dòng lệnh. Công cụ rebuild từ chối ghi đè file đích có sẵn; nếu thất bại, giữ file đích dở dang để kiểm tra và chọn đường dẫn mới khi chạy lại.
