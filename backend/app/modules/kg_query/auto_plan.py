"""Shared bounded lexical planning; no generated Cypher or universal language claim."""
from .question_analysis import has_cue, text_key, detect_intents, comparison_mode
from .intents import PRESET_START_TYPES, PRESET_LABELS
ROUTE_CUES = {
 'drugs_for_disease': (('thuốc','hoạt chất','nhóm thuốc'),('điều trị','chữa','thuốc nào','thuốc gì','dùng thuốc')),
 'drug_adverse_effects': (('thuốc','hoạt chất','nhóm thuốc'),('tác dụng phụ','tác dụng không mong muốn','biến cố bất lợi')),
 'drug_contraindications': (('thuốc','hoạt chất','nhóm thuốc'),('chống chỉ định','thận trọng','không được dùng')),
 'regimen_medications': (('phác đồ',),('thành phần','gồm','bao gồm','thuốc','hoạt chất')),
 'regimen_adverse_effects': (('phác đồ',),('tác dụng phụ','tác dụng không mong muốn','biến cố bất lợi')),
 'regimen_dosage': (('phác đồ',),('liều','đường dùng','tần suất','thời gian dùng','thời gian điều trị','bao lâu')),
 'recommendation_interventions': (('khuyến nghị','khuyến cáo'),('can thiệp','biện pháp')),
 'recommendation_conditions': (('khuyến nghị','khuyến cáo'),('điều kiện','đối tượng','áp dụng khi nào','áp dụng cho ai')),
 'diagnostic_findings': (('xét nghiệm',),('phát hiện','đo gì','đo đại lượng','chỉ số nào')),
 'diagnostic_specimens': (('xét nghiệm',),('bệnh phẩm','lấy mẫu','mẫu nào','mẫu gì')),
 'criteria_thresholds': (('tiêu chuẩn','tiêu chí'),('ngưỡng','giá trị giới hạn')),
 'resistant_medications': (('hồ sơ kháng','kiểu kháng','kháng thuốc'),('thuốc','kháng sinh')),
 'pathogen_resistance': (('tác nhân','vi khuẩn','vi sinh vật'),('kháng thuốc','kháng kháng sinh','hồ sơ kháng')),
 'regimen_monitoring': (('phác đồ',),('theo dõi','giám sát')),
 'treatment_sequence': (('phác đồ','điều trị'),('trình tự','thứ tự','các bước','bước tiếp theo')),
 'prevention_settings': (('dự phòng','phòng ngừa','kiểm soát nhiễm khuẩn'),('môi trường','bối cảnh','áp dụng ở đâu','cơ sở nào','nơi nào')),
 'rehabilitation_goals': (('phục hồi','tập thở'),('mục tiêu','nhằm đạt')),
 'prognostic_outcomes': (('yếu tố tiên lượng',),('kết cục','dự báo','dự đoán')),
 'guideline_interventions': (('hướng dẫn',),('can thiệp','biện pháp','khuyến cáo','khuyến nghị')),
}
AUTO_EXAMPLES = {
 'drugs_for_disease':'Thuốc nào điều trị {name}?',
 'drug_adverse_effects':'Thuốc điều trị {name} có tác dụng phụ gì?',
 'drug_contraindications':'Thuốc điều trị {name} có chống chỉ định gì?',
 'regimen_medications':'Phác đồ của {name} gồm những thuốc nào?',
 'regimen_adverse_effects':'Thuốc trong phác đồ của {name} có tác dụng phụ gì?',
 'regimen_dosage':'Thuốc trong phác đồ của {name} có liều dùng nào?',
 'recommendation_interventions':'Khuyến cáo cho {name} đề xuất can thiệp nào?',
 'recommendation_conditions':'Khuyến cáo cho {name} áp dụng với đối tượng nào?',
 'diagnostic_findings':'Xét nghiệm của {name} đo đại lượng nào?',
 'diagnostic_specimens':'Xét nghiệm của {name} cần bệnh phẩm nào?',
 'criteria_thresholds':'Tiêu chuẩn của {name} có ngưỡng nào?',
 'resistant_medications':'Hồ sơ kháng của {name} liên quan thuốc nào?',
 'pathogen_resistance':'Tác nhân gây {name} có hồ sơ kháng thuốc nào?',
 'regimen_monitoring':'Phác đồ của {name} cần theo dõi gì?',
 'treatment_sequence':'Các bước trong phác đồ điều trị {name} theo trình tự nào?',
 'prevention_settings':'Biện pháp dự phòng {name} áp dụng ở đâu?',
 'rehabilitation_goals':'Phục hồi chức năng cho {name} có mục tiêu gì?',
 'prognostic_outcomes':'Yếu tố tiên lượng của {name} dự báo kết cục nào?',
 'guideline_interventions':'Hướng dẫn về {name} khuyến cáo can thiệp nào?',
}
DOMINATES = {
 'regimen_adverse_effects': {'regimen_medications','drug_adverse_effects','drugs_for_disease'},
 'regimen_dosage': {'regimen_medications','drugs_for_disease'},
 'regimen_monitoring': {'regimen_medications','drugs_for_disease'},
 'regimen_medications': {'drugs_for_disease'},
 'drug_adverse_effects': {'drugs_for_disease'}, 'drug_contraindications': {'drugs_for_disease'},
 'pathogen_resistance': {'resistant_medications','drugs_for_disease'},
 'resistant_medications': {'drugs_for_disease'},
 'guideline_interventions': {'recommendation_interventions'},
}
PATH_CUES=('mối liên hệ','mối liên quan','quan hệ giữa','liên kết giữa','đường liên kết','đường đi giữa','liên quan với','liên quan thế nào','liên quan như thế nào')
def without_mentions(question,mentions):
 text=' '+text_key(question,accents=False)+' '
 for name in sorted(set(mentions),key=len,reverse=True):text=text.replace(' '+text_key(name,accents=False)+' ',' ')
 return text

def candidates(question,types=None):
 found=[k for k,(a,b) in ROUTE_CUES.items() if has_cue(question,a) and has_cue(question,b)]
 if types is not None:found=[k for k in found if types and all(t in PRESET_START_TYPES[k] for t in types)]
 suppressed=set().union(*(DOMINATES.get(k,set()) for k in found)) if found else set()
 return [k for k in found if k not in suppressed]

def inference_plan(question):
 if not has_cue(question,('suy luận','bắc cầu','suy ra')) or has_cue(question,('không suy luận','không suy ra','không dùng suy luận')):return None,None
 taxonomy=has_cue(question,('phân loại','loại cha','lớp cha','phân cấp','is a'))
 anatomy=has_cue(question,('bộ phận','giải phẫu','part of'))
 if taxonomy==anatomy or has_cue(question,('nhân quả','nguyên nhân','điều trị','chẩn đoán','chống chỉ định')):
  return None,'Hiện chỉ hỗ trợ suy luận bắc cầu về phân loại hoặc bộ phận giải phẫu, mỗi lượt một quy tắc. Bạn muốn suy luận loại nào, cho thực thể nào?'
 return ('is_a_transitive' if taxonomy else 'part_of_transitive'),None

def constraint_issue(question):
 if has_cue(question,('không gây','không chứa','không có tác dụng phụ','ngoại trừ','loại trừ thuốc','chỉ lấy','vừa điều trị','đồng thời thỏa','đồng thời thoả')):
  return 'Câu hỏi có điều kiện lọc hoặc kết hợp nhiều yêu cầu chưa được bộ lập kế hoạch tự động hỗ trợ. Hãy tách từng tiêu chí để tra cứu; thiếu một quan hệ trong KG không chứng minh điều kiện phủ định.'
 return None

def routing_hint(question):
 if comparison_mode(question):return 'kg_comparison_cue'
 if has_cue(question,PATH_CUES):return 'kg_path_cue'
 rule,issue=inference_plan(question)
 if rule or issue:return 'kg_inference_cue'
 if candidates(question):return 'kg_multi_hop_cue'
 if detect_intents(question)!=['related']:return 'kg_relation_cue'
 return None

def suggestions(question,names):
 name=names[0] if names else 'TÊN_THỰC_THỂ'
 rule,issue=inference_plan(question)
 if rule or issue:return [f'Suy luận phân loại cho {name}.',f'Suy luận bộ phận giải phẫu cho {name}.']
 return [AUTO_EXAMPLES[k].format(name=name) for k in candidates(question)][:4]

def catalog():
 return [{'preset':k,'label':PRESET_LABELS[k],'example':AUTO_EXAMPLES[k].format(name='TÊN_THỰC_THỂ'),'start_types':list(PRESET_START_TYPES[k])} for k in ROUTE_CUES]
