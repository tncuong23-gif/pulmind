SAO LUU MODELS + DATA + CAC FILE BI .GITIGNORE BO QUA
==================================================
Chep backup_models_and_data.py va run_backup_models_and_data.bat vao thu muc goc
medical-ai-integrated (noi co .git, backend, frontend).

CMD:
  cd /d D:\medical_wed\banzip\medical-ai-integrated
  python backup_models_and_data.py --dry-run --list
  python backup_models_and_data.py

Mac dinh tao ZIP ben ngoai thu muc project:
  D:\medical_wed\banzip\medical-ai-integrated_models_data_YYYYMMDD_HHMMSS.zip

Hoac:
  python backup_models_and_data.py --folder
  python backup_models_and_data.py --output "D:\Backup\pulmograph-data-models.zip"

NHIEM VU:
- Lay tat ca file bi gitignore bo qua.
- Lay them model va data ben trong cac thu muc co ten data/dataset/datasets,
  model/models/weights/checkpoint/checkpoints/hf-cache, ke ca khi khong ignored.
- Lay file trong project co cac duoi model: .pt .pth .ckpt .safetensors
  .onnx .gguf .ggml .joblib .pkl .h5 .keras .tflite.
- LUON bo venv, .venv, .venv-*, node_modules, .git o moi cap.
- De an toan, mac dinh KHONG lay .env, .env.*, keys va credential files.
  Neu can sao luu bi mat vao noi AN TOAN, co tuy chon --include-secrets.
- Khong sao luu du lieu Docker volume ngoai thu muc project hay Hugging Face
  cache nam ngoai project. Khong tai truc tiep len Google Drive.

KHOI PHUC:
1. Clone GitHub repository.
2. Giai nen ZIP sao cho cac duong dan backend/models, backend/data,...
   nam duoi thu muc goc medical-ai-integrated.
3. Restore .env PRIVATE va Docker volume tu ban sao luu rieng neu can.
4. Model Ollama co the can keo lai qua 'ollama pull <model>' tren may moi.

CANH BAO: Kiem tra noi dung data truoc khi upload Drive, nhat la benh an,
hinh X-quang/du lieu benh nhan. Khong upload neu khong co quyen chia se.
