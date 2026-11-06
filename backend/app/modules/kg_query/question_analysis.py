"""Bounded, deterministic Vietnamese question planning. Never generates Cypher.

This is lexical coverage, not a learned semantic parser. Unsupported/ambiguous
plans are returned to the caller for clarification instead of being guessed.
"""
from __future__ import annotations

import re
import unicodedata

from .intents import PRESET_CHAINS, DRUG_TYPES, PRESET_START_TYPES, preset_steps

COMPARISON_MODES = ('compare', 'common', 'difference')
DISEASE_TYPES = {'Disease', 'DiseaseSubtype', 'Syndrome', 'AcuteCondition', 'ClinicalCondition', 'Complication', 'Exacerbation'}


def text_key(value: str, *, accents: bool = True) -> str:
    value = unicodedata.normalize('NFC', value).casefold()
    # COVID19, COVID-19 and COVID 19 have the same token boundary.
    value = re.sub(r'([^\W\d_])(\d)', r'\1 \2', value)
    value = re.sub(r'(\d)([^\W\d_])', r'\1 \2', value)
    if not accents:
        value = ''.join(c for c in unicodedata.normalize('NFD', value)
                        if not unicodedata.combining(c)).replace('đ', 'd')
    return ' '.join(re.findall(r'\w+', value))


RULES = {
    'symptom': ('triệu chứng', 'dấu hiệu', 'biểu hiện'),
    'treatment': ('điều trị', 'chữa', 'trị bệnh', 'chỉ định', 'dùng thuốc', 'thuốc nào', 'thuốc gì'),
    'membership': ('thành phần', 'chứa thuốc', 'chứa hoạt chất', 'gồm thuốc', 'gồm những thuốc', 'gồm các thuốc'),
    'drug_class': ('thuộc nhóm thuốc', 'thuộc nhóm nào', 'thuộc loại thuốc', 'nhóm của thuốc'),
    'dosage': ('liều dùng', 'liều lượng', 'đường dùng', 'liều thuốc', 'dụng cụ đưa thuốc', 'uống bao nhiêu'),
    'adverse_effect': ('tác dụng phụ', 'tác dụng không mong muốn', 'độc tính', 'biến cố bất lợi'),
    'contraindication': ('chống chỉ định', 'thận trọng', 'không được dùng', 'không nên dùng'),
    'interaction': ('tương tác', 'tăng tác dụng', 'giảm tác dụng'),
    'risk_factor': ('yếu tố nguy cơ', 'nguy cơ mắc', 'yếu tố khởi phát', 'làm nặng', 'dễ mắc'),
    'cause': ('nguyên nhân', 'gây ra', 'do đâu', 'bệnh sinh'),
    'prevention': ('phòng ngừa', 'dự phòng', 'phòng tránh', 'vắc xin', 'vaccine'),
    'diagnosis': ('chẩn đoán', 'xét nghiệm', 'tiêu chuẩn xác định', 'hình ảnh học', 'x quang', 'ngưỡng chẩn đoán'),
    'differential': ('chẩn đoán phân biệt', 'phân biệt với bệnh'),
    'assessment': ('thang điểm', 'đánh giá bằng', 'phép đo', 'đo lường'),
    'classification': ('phân loại', 'giai đoạn', 'mức độ nặng', 'phân nhóm', 'phân độ'),
    'comorbidity': ('biến chứng', 'bệnh đi kèm', 'bệnh kèm', 'đồng mắc', 'đợt cấp', 'nguy hiểm'),
    'monitoring': ('theo dõi', 'giám sát', 'lịch tái khám'),
    'prognosis': ('tiên lượng', 'kết cục', 'tử vong', 'đáp ứng điều trị', 'diễn tiến', 'nguy hiểm'),
    'recommendation': ('khuyến cáo', 'khuyến nghị', 'nhập viện', 'mục tiêu điều trị', 'phác đồ', 'hướng dẫn điều trị'),
    'transmission': ('lây', 'lây truyền', 'ủ bệnh', 'phơi nhiễm'),
    'resistance': ('kháng thuốc', 'nhạy thuốc', 'nhạy cảm thuốc', 'đột biến kháng'),
    'rehabilitation': ('phục hồi chức năng', 'bài tập', 'tập thở'),
    'population': ('nhóm bệnh nhân', 'đối tượng', 'quần thể', 'áp dụng cho ai'),
    'mechanism': ('cơ chế sinh học', 'cơ chế tác động', 'cơ chế tác dụng', 'thụ thể', 'cytokine', 'tế bào'),
    'anatomy': ('vị trí', 'cơ quan', 'giải phẫu', 'bộ phận', 'ảnh hưởng ở đâu'),
}

RULES.update({
    'taxonomy': ('phân loại cha', 'phân loại con', 'thuộc lớp', 'loại con', 'phân cấp'),
    'screening': ('sàng lọc', 'tầm soát'),
    'epidemiology': ('tỷ lệ mắc', 'tỉ lệ mắc', 'dịch tễ', 'tỷ lệ hiện mắc'),
    'source_topic': ('tài liệu nào', 'hướng dẫn nào', 'nguồn nào đề cập'),
    'sequence': ('trình tự', 'bước tiếp theo', 'sau bước', 'thứ tự điều trị'),
    'setting': ('môi trường áp dụng', 'cơ sở y tế', 'cách ly ở đâu'),
    'applicability': ('điều kiện áp dụng', 'áp dụng khi nào', 'đối tượng áp dụng'),
    'regimen': ('thành phần phác đồ', 'phác đồ gồm', 'thuốc trong phác đồ'),
})
RULES['dosage'] += ('tần suất', 'thời gian dùng', 'thời gian điều trị', 'bao lâu')


def has_cue(text: str, cues) -> bool:
    padded = f' {text_key(text, accents=False)} '
    return any(f' {text_key(c, accents=False)} ' in padded for c in cues)


def detect_intents(question: str, mentions=()) -> list[str]:
    # A disease named "Lao kháng thuốc" is not itself a request about resistance.
    text = f' {text_key(question, accents=False)} '
    for mention in sorted(mentions, key=len, reverse=True):
        text = text.replace(f' {text_key(mention, accents=False)} ', ' ')
    text = re.sub(r"\bkhong (?:hoi|can hoi) ve [^,]*?\b(?=chi hoi|ma hoi)", " ", text)
    found = [key for key, cues in RULES.items() if has_cue(text, cues)]
    if 'differential' in found:
        found = [i for i in found if i != 'diagnosis']
    # "chỉ định" inside "chống chỉ định" does not ask about treatment.
    if 'contraindication' in found:
        stripped = text.replace('chong chi dinh', ' ')
        if not has_cue(stripped, RULES['treatment']):
            found = [i for i in found if i != 'treatment']
    return found or ['related']


def uses_context(question: str) -> bool:
    cues = ('nó', 'bệnh này', 'bệnh đó', 'thuốc này', 'thuốc đó', 'tình trạng này')
    text = text_key(question)
    return (any(f' {text_key(c)} ' in f' {text} ' for c in cues)
            or (text == text_key(question, accents=False) and has_cue(question, cues)))


def comparison_mode(question: str) -> str | None:
    if has_cue(question, ('không so sánh', 'không cần so sánh', 'đừng so sánh')):
        return None
    common = has_cue(question, ('điểm chung', 'giống nhau', 'tương đồng', 'triệu chứng chung',
                                'dấu hiệu chung', 'cùng có'))
    different = has_cue(question, ('điểm khác', 'khác nhau', 'khác biệt', 'khác gì'))
    if common and different:
        return 'compare'
    if common:
        return 'common'
    if different:
        return 'difference'
    if has_cue(question, ('so sánh', 'đối chiếu', 'phân biệt giữa')):
        return 'compare'
    return None


def choose_mode(question, anchors, intents, *, mode='auto', preset=None):
    if mode!='auto':return mode,preset,None
    from .auto_plan import PATH_CUES,candidates,constraint_issue,without_mentions
    entities=[a.entity for group in anchors.values() for a in group]
    text=without_mentions(question,[*anchors,*[e.name for e in entities]])
    if detected:=comparison_mode(text):
        if preset:return detected,None,'So sánh hiện đối chiếu các quan hệ trực tiếp. Hãy hỏi riêng từng bệnh nếu cần chuỗi thuốc điều trị.'
        return detected,None,None
    if preset:return 'multi_hop',preset,None
    issue=constraint_issue(text)
    if issue:return 'one_hop',None,issue
    if has_cue(text,PATH_CUES):return 'path',None,None
    plans=candidates(text,[e.type for e in entities])
    if len(plans)>1:
        from .intents import PRESET_LABELS
        return 'one_hop',None,'Câu hỏi khớp nhiều chuỗi: '+'; '.join(PRESET_LABELS[k] for k in plans)+'. Hãy chọn một nội dung mỗi lượt để giữ đủ các bước bằng chứng.'
    if plans:return 'multi_hop',plans[0],None
    if entities and all(e.type in DISEASE_TYPES for e in entities) and has_cue(text,('thuốc','hoạt chất','nhóm thuốc')) and any(i in intents for i in ('dosage','interaction','monitoring','resistance')):
        return 'one_hop',None,'Bạn vui lòng nêu tên thuốc cụ thể hoặc nói rõ thuốc trong phác đồ của bệnh để tra nội dung này.'
    return 'one_hop',None,None


def validate_mode(mode, preset, intents, anchors, service):
    if len(intents) > 6:
        return 'Câu hỏi chứa nhiều nội dung. Bạn hãy tách thành câu hỏi ngắn hơn.'
    if mode in COMPARISON_MODES:
        if len(anchors) != 2:
            return 'Bạn vui lòng nêu rõ hai bệnh hoặc hai thuốc cần so sánh.'
        entities = [a.entity for group in anchors.values() for a in group]
        left,right=({a.entity.id for a in group} for group in anchors.values())
        if left & right:
            return 'Hai tên đang trỏ đến cùng một thực thể. Vui lòng chọn hai thực thể khác nhau.'
        if not (all(e.type in DISEASE_TYPES for e in entities) or all(e.type in DRUG_TYPES for e in entities)):
            return 'Hãy chọn hai bệnh hoặc hai thuốc/nhóm thuốc để so sánh cùng loại.'
        if not intents or 'related' in intents:
            return 'Bạn muốn so sánh theo tiêu chí nào: triệu chứng, nguy cơ, điều trị, tác dụng phụ hay chống chỉ định? Vui lòng nêu tiêu chí cùng tên hai bệnh/thuốc.'
        if all(e.type in DISEASE_TYPES for e in entities) and any(
                i in intents for i in ('adverse_effect', 'contraindication', 'dosage', 'interaction', 'drug_class', 'membership')):
            return 'Với tiêu chí về thuốc, hãy nêu hai tên thuốc cụ thể. So sánh hiện dùng các quan hệ trực tiếp của từng bệnh/thuốc.'
    if mode == 'path':
        if len(anchors) != 2:
            return 'Bạn vui lòng nêu rõ hai bệnh, thuốc hoặc thực thể cần tìm đường liên kết.'
        ids = [{a.entity.id for a in group} for group in anchors.values()]
        if ids[0] & ids[1]:
            return 'Hai tên đang trỏ đến cùng một thực thể. Vui lòng chọn hai thực thể khác nhau.'
    if mode == 'multi_hop':
        if preset not in PRESET_CHAINS:
            return 'Bạn vui lòng chọn một mẫu chuỗi được hỗ trợ hoặc mô tả từng bước trong KG Explorer.'
        allowed=PRESET_START_TYPES[preset]
        if any(a.entity.type not in allowed for group in anchors.values() for a in group):
            return 'Chuỗi này cần thực thể bắt đầu thuộc một trong các loại: '+', '.join(allowed)
        try:preset_steps(preset,service.ontology)
        except ValueError as exc:return str(exc)
        required=[]
    elif mode == 'one_hop' or mode in COMPARISON_MODES:
        required = intents
    else:
        required = []
    missing = [i for i in required if i not in service.intents or not service.intents[i].relations]
    if missing:
        return 'Ontology hiện tại chưa có nhóm quan hệ cần thiết: ' + ', '.join(missing) + '.'
    return None
