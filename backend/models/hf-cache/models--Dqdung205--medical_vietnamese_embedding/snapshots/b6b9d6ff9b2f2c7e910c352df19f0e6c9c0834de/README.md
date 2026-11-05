---
language:
- vi
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:12234
- loss:MultipleNegativesRankingLoss
base_model: Alibaba-NLP/gte-multilingual-base

datasets:
- Dqdung205/medical-vietnamese-qa
pipeline_tag: sentence-similarity
library_name: sentence-transformers
---

# SentenceTransformer based on Alibaba-NLP/gte-multilingual-base

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [Alibaba-NLP/gte-multilingual-base](https://huggingface.co/Alibaba-NLP/gte-multilingual-base) on the [medical-vietnamese-qa](https://huggingface.co/datasets/Dqdung205/medical-vietnamese-qa) dataset. It maps sentences & paragraphs to a 768-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [Alibaba-NLP/gte-multilingual-base](https://huggingface.co/Alibaba-NLP/gte-multilingual-base) <!-- at revision 9bbca17d9273fd0d03d5725c7a4b0f6b45142062 -->
- **Maximum Sequence Length:** 8192 tokens
- **Output Dimensionality:** 768 dimensions
- **Similarity Function:** Cosine Similarity
- **Training Dataset:**
    - [medical-vietnamese-qa](https://huggingface.co/datasets/Dqdung205/medical-vietnamese-qa)
- **Language:** vi
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/UKPLab/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'max_seq_length': 8192, 'do_lower_case': False, 'architecture': 'NewModel'})
  (1): Pooling({'word_embedding_dimension': 768, 'pooling_mode_cls_token': True, 'pooling_mode_mean_tokens': False, 'pooling_mode_max_tokens': False, 'pooling_mode_mean_sqrt_len_tokens': False, 'pooling_mode_weightedmean_tokens': False, 'pooling_mode_lasttoken': False, 'include_prompt': True})
  (2): Normalize()
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```

Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
queries = [
    "Em bị nổi cục u trong cổ họng nhưng không đau, nổi hạch quanh tai, nổi nốt đỏ khắp người và ngứa, do em đang bị 1 vết thương hở ở chân nên đang dùng thuốc trong đó có Amoxicillin. Vậy bác sĩ cho em hỏi nổi u trong cổ kèm hạch quanh tai là dấu hiệu bệnh gì? Em cần làm gì, thưa bác sĩ? Em cảm ơn bác sĩ.",
]
documents = [
    'bác sĩ xin giải đáp như sau: Vớiu trong họngcó nổi hạch bạn nên đi khám chuyên khoa Tai mũi họng để được kiểm tra và điều trị cụ thể.Vết thương hở ở chânđiều trị kháng sinh có nổi mẩn ngứa chưa loại trừ dị ứng thuốc, bạn nên tạm ngưng thuốc đang uống tái khám đề trước đánh giá, thay đổi thuốc nếu cần.',
    'bác sĩ xin giải đáp như sau: Trước khi lập kế hoạch điều trị ung thư vú, người bệnh sẽ được đánh giá giai đoạn trước điều trị, trong đó bao gồm xác định tình trạng di căn xa của bệnh. Các bộ phận ung thư vú hay di căn đến như: Phổi, gan, não, xương. Người bệnh sẽ được thực hiện chỉ định cận lâm sàng phù hợp với tình trạng khối u (kích thước khối u, tình trạng ER, PR, Her2, tình trạng hạch di căn,...), triệu chứng lâm sàng, bao gồm: Chụp cắt lớp vi tính lồng ngực, bụng, MRI bụng - tiểu khung, MRI sọ não, xạ hình xương, PET/CT,....Việc chỉ định đánh giá di căn bằng phương pháp nào, bác sĩ sẽ căn cứ vào tình trạng của từng người bệnh cụ thể. Trường hợp của bạn đã được bác sĩ đánh giá giai đoạn trước mổ bằng chụp cắt lớp vi tính ngực bụng. Sau phẫu thuật từ 4 - 12 tuần, người bệnh sẽ được điều trị hoá chất bổ trợ (nếu có chỉ định). Nếu không có các triệu chứng bất thường nghi ngờ di căn xa thì sẽ không thực hiện các chỉ định đánh giá di căn bổ xung sau mổ như: Xạ hình xương, PET/CT,... Với trường hợp của bạn, PET/CT có thể cân nhắc thực hiện để đánh giá di căn xa trong quá trình theo dõi sau điều trị nếu người bệnh có các triệu chứng nghi ngờ tái phát, di căn. Để có được tư vấn, bạn nên trao đổi trực tiếp với bác sĩ điều trị của mình hoặc khám tư vấn với bác sĩ chuyên khoa Ung thư Vú cùng với hồ sơ bệnh của bạn.',
    'Chào bạn! Bác sĩ xin hỏi bạn có sử dụng thêm các thuốc hoặc thực phẩm chức năng nào không? Hoặc bạn có đang dùng thuốc điều trị sau khi khám và được chẩn đoánrối loạn nội tiếtkhông? Một số trường hợp thuốc sẽ gây rối loạn kinh nguyệt,xuất huyết âm đạo bất thường(như thuốc tránh thai khẩn cấp,thuốc corticoid,...). Bên cạnh đó, tính chất ra máu như số lượng, màu sắc, ra máu kéo dài trong thời gian bao nhiêu lâu cũng sẽ giúp bác sĩ tìm ra nguyên nhân chính xác hơn. Với trường hợp của bạn, bác sĩ khuyên bạn nên đi khám lại ở cơ sở y tế có chuyên khoa sâu về Phụ khoa để chẩn đoán và điều trị chính xác cho bạn. Cảm ơn bạn đã đặt câu hỏi tớiHệ thống Y tế Vinmec, rất mong được gặp bạn để được tư vấn trực tiếp. Trân trọng! Để được tư vấn trực tiếp, Quý Khách vui lòng bấm sốHOTLINEhoặc đăng ký trực tuyếnTẠI ĐÂY. Bác sĩ chuyên khoa II Nguyễn Thu Hoài- Trưởng đơn nguyên phòng khám Sản - Trung tâm Phụ sản - Bệnh viện Đa khoa Quốc tế Vinmec Times City.',
]
query_embeddings = model.encode_query(queries)
document_embeddings = model.encode_document(documents)
print(query_embeddings.shape, document_embeddings.shape)
# [1, 768] [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(query_embeddings, document_embeddings)
print(similarities)
# tensor([[ 0.7499, -0.0280,  0.0504]])
```

<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->


### Training Hyperparameters
#### Non-Default Hyperparameters

- `eval_strategy`: steps
- `per_device_train_batch_size`: 16
- `per_device_eval_batch_size`: 24
- `learning_rate`: 1e-05
- `num_train_epochs`: 8
- `warmup_ratio`: 0.05
- `bf16`: True
- `load_best_model_at_end`: True
- `batch_sampler`: no_duplicates


## Evaluation

### Metrics

#### Information Retrieval

* Datasets: [tarudesu/ViHealthQA](https://huggingface.co/datasets/tarudesu/ViHealthQA)
* Evaluated with [<code>InformationRetrievalEvaluator</code>](https://sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.evaluation.InformationRetrievalEvaluator)

| model                                        |Model size|   ndcg@3 |   ndcg@5 |   ndcg@10 |    mrr@3 |    mrr@5 |   mrr@10 |
|:---------------------------------------------|---------:|---------:|---------:|----------:|---------:|---------:|---------:|
| Dqdung205/medical_vietnamese_embedding       |  305M    | 0.874165 | 0.880625 |  0.883869 | 0.856667 | 0.860417 | 0.861756 |
| BAAI/bge-m3                                  |  568M    | 0.83601  | 0.848273 |  0.856249 | 0.820833 | 0.827583 | 0.830812 |
| dangvantuan/vietnamese-document-embedding    |  305M    | 0.827201 | 0.833223 |  0.847393 | 0.815833 | 0.819083 | 0.824692 |
| Alibaba-NLP/gte-multilingual-base            |  305M    | 0.816428 | 0.837523 |  0.847238 | 0.81     | 0.822    | 0.826012 |
| AITeamVN/Vietnamese_Embedding                |  568M    | 0.787201 | 0.799683 |  0.816054 | 0.7775   | 0.7845   | 0.791387 |
| strongpear/M3-retriever-MEDICAL              |  560M    | 0.777856 | 0.800667 |  0.81552  | 0.765    | 0.77775  | 0.784054 |
| hiieu/halong_embedding                       |  278M    | 0.774284 | 0.784612 |  0.796095 | 0.756667 | 0.762417 | 0.767248 |
| bkai-foundation-models/vietnamese-bi-encoder |  125M    | 0.73601  | 0.744186 |  0.753977 | 0.719167 | 0.723667 | 0.727754 |
| NovaSearch/stella_en_1.5B_v5                 |  1.5B    | 0.612438 |  0.64795 |  0.683937 | 0.595833 | 0.615833 | 0.630935 |
| keepitreal/vietnamese-sbert                  |          | 0.618629 | 0.639944 |  0.661153 | 0.595833 | 0.608083 | 0.616954 |
| google/embeddinggemma-300M                   |  300M    | 0.543748 | 0.579698 |  0.611724 | 0.519167 | 0.539667 | 0.552694 |
| VoVanPhuc/sup-SimCSE-VietNamese-phobert-base |  136M    | 0.508748 | 0.543164 |  0.575335 | 0.4825   | 0.50125  | 0.514405 |



### Framework Versions
- Python: 3.10.12
- Sentence Transformers: 5.1.0
- Transformers: 4.56.1
- PyTorch: 2.8.0+cu128
- Accelerate: 1.10.1
- Datasets: 4.0.0
- Tokenizers: 0.22.0

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

#### MultipleNegativesRankingLoss
```bibtex
@misc{henderson2017efficient,
    title={Efficient Natural Language Response Suggestion for Smart Reply},
    author={Matthew Henderson and Rami Al-Rfou and Brian Strope and Yun-hsuan Sung and Laszlo Lukacs and Ruiqi Guo and Sanjiv Kumar and Balint Miklos and Ray Kurzweil},
    year={2017},
    eprint={1705.00652},
    archivePrefix={arXiv},
    primaryClass={cs.CL}
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->