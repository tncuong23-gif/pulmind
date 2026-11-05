"""Intent -> relation-type groups.

The ontology has ~250 relation types, far too many to write one query each. Instead every question is
reduced to (entity mention(s), intent). An intent is just a NAMED GROUP of relation types; the Cypher is
generated from the group, and the direction of each relation is inferred from the ontology's domain/range
and the anchor's entity type (see KGQueryService.direction_plan). Adding coverage = adding a name to a group.

Safety net: intent `related` = ALL ontology relations, so a question that fits no specific intent still
gets an evidence-backed answer instead of nothing. `uncovered_relations()` lists relations that only
`related` reaches, so you can see (and later assign) what is not yet covered by a specific intent.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.kg_import.ontology import Ontology

from .models import Step

CATCH_ALL = "related"

# name -> (description shown to the question-analysis LLM, relation types)
_DEFS: dict[str, tuple[str, tuple[str, ...]]] = {
    "symptom": ("Triệu chứng / dấu hiệu của bệnh",
                ("HAS_SYMPTOM", "HAS_CLINICAL_SIGN", "HAS_MANIFESTATION", "HAS_PERSISTENT_SYMPTOM",
                 "HAS_EMERGENCY_SIGN", "HAS_PHENOTYPE")),
    "treatment": ("Điều trị / thuốc / can thiệp cho bệnh (hoặc thuốc dùng cho bệnh gì)",
                  ("TREATED_BY", "TREATS", "INDICATED_FOR", "HAS_INDICATION", "MANAGED_BY", "ETIOLOGICALLY_TREATED_BY",
                   "RECOMMENDS_TREATMENT", "RECOMMENDS_INTERVENTION", "HAS_TREATMENT_INDICATION", "INDICATED_TREATMENT",
                   "INDICATES_TREATMENT", "HAS_TREATMENT_PRINCIPLE", "HAS_TREATMENT_STEP", "HAS_TREATMENT_TRACK",
                   "HAS_REGIMEN", "HAS_MEDICATION_REGIMEN", "USES_MEDICATION")),
    "membership": ("Nhóm thuốc gồm những thuốc nào / chế phẩm phối hợp chứa gì (đi xuống)",
                   ("HAS_MEMBER", "CONTAINS", "CONTAINS_MEDICATION", "INCLUDES_MEDICATION", "HAS_ACTIVE_INGREDIENT",
                    "HAS_REGIMEN_COMPONENT")),
    "drug_class": ("Thuốc thuộc nhóm nào", ("BELONGS_TO_DRUG_CLASS",)),
    "dosage": ("Liều dùng, đường dùng, phác đồ, dụng cụ đưa thuốc",
               ("HAS_DOSE", "HAS_ROUTE", "HAS_REGIMEN", "HAS_REGIMEN_COMPONENT", "DELIVERED_BY", "USES_DEVICE")),
    "adverse_effect": ("Tác dụng phụ / độc tính của thuốc hoặc can thiệp",
                       ("HAS_ADVERSE_EFFECT", "CAUSES_ADVERSE_EVENT", "HAS_TOXICITY", "HAS_ANTIDOTE", "MONITORS_TOXICITY")),
    "contraindication": ("Chống chỉ định / thận trọng",
                         ("HAS_CONTRAINDICATION", "CONTRAINDICATED_IN", "CONTRAINDICATED_WHEN", "REQUIRES_CAUTION_IN")),
    "interaction": ("Tương tác thuốc",
                    ("INTERACTS_WITH", "HAS_DRUG_INTERACTION", "INCREASES_EFFECT_OF", "DECREASES_EFFECT_OF",
                     "MODIFIES_EFFECT_OF")),
    "risk_factor": ("Yếu tố nguy cơ / yếu tố khởi phát / làm nặng bệnh",
                    ("RISK_FACTOR_FOR", "HAS_RISK_FACTOR", "PREDISPOSES_TO", "INCREASES_RISK_OF", "CONTRIBUTES_TO",
                     "TRIGGERED_BY", "HAS_TRIGGER", "WORSENED_BY")),
    "cause": ("Nguyên nhân / cơ chế bệnh sinh",
              ("CAUSES", "CAUSED_BY", "CAUSED_BY_CONDITION", "HAS_CAUSE", "HAS_ETIOLOGIC_CATEGORY", "HAS_MECHANISM",
               "HAS_PATHOPHYSIOLOGY")),
    "prevention": ("Phòng ngừa / dự phòng / vắc-xin",
                   ("PREVENTS", "PREVENTED_BY", "PROTECTS_AGAINST", "POST_EXPOSURE_PROPHYLAXIS_WITH")),
    "diagnosis": ("Chẩn đoán: xét nghiệm, hình ảnh, tiêu chuẩn, ngưỡng",
                  ("DIAGNOSED_BY", "HAS_DIAGNOSTIC_CRITERION", "HAS_DIAGNOSTIC_TEST", "HAS_DIAGNOSTIC_THRESHOLD",
                   "HAS_IMAGING_FINDING", "HAS_IMAGING_SIGN", "HAS_PATHOLOGY_FINDING",
                   "SUPPORTS_DIAGNOSIS_OF", "SUPPORTED_BY", "CONFIRMED_BY_SPECIMEN", "HAS_FINDING", "HAS_LAB_CRITERION",
                   "HAS_CRITERION", "HAS_MAJOR_CRITERION", "HAS_MINOR_CRITERION", "HAS_ONSET_CRITERION",
                   "HAS_BLOOD_GAS_FINDING", "HAS_HEMODYNAMIC_FINDING", "HAS_HISTOPATHOLOGICAL_FINDING",
                   "HAS_MICROBIOLOGICAL_EVIDENCE", "PRODUCES_FINDING", "HAS_BIOMARKER", "TARGETS_BIOMARKER",
                   "HAS_DIAGNOSTIC_PERFORMANCE", "DETECTS", "USES_SPECIMEN", "OBTAINED_FROM")),
    "differential": ("Chẩn đoán phân biệt",
                     ("DIFFERENTIAL_DIAGNOSIS_OF", "HAS_DIFFERENTIAL_DIAGNOSIS", "DIFFERENTIAL_DIAGNOSIS",
                      "EXCLUDES_DIAGNOSIS_OF")),
    "assessment": ("Đánh giá bằng thang điểm / phép đo",
                   ("ASSESSED_BY", "ASSESSED_BY_RULE", "USES_SCORE", "HAS_SCORE", "USES_MEASUREMENT", "MEASURED_BY",
                    "MEASURES", "MEASURES_BIOMARKER", "HAS_THRESHOLD")),
    "classification": ("Phân loại, mức độ nặng, giai đoạn, nhóm",
                       ("HAS_SEVERITY_GRADE", "HAS_SEVERITY", "HAS_STAGE", "HAS_STAGE_ASSESSMENT", "CLASSIFIED_BY",
                        "CLASSIFIED_AS", "HAS_CLASSIFICATION_SYSTEM", "HAS_GROUP", "HAS_TNM_CATEGORY", "HAS_SUBTYPE",
                        "HAS_TYPE", "HAS_SEVERITY_CRITERION", "ASSOCIATED_WITH_SEVERITY", "HAS_DISEASE_PHASE")),
    "comorbidity": ("Bệnh đi kèm, biến chứng, đợt cấp, tiến triển",
                    ("HAS_COMORBIDITY", "HAS_COMPLICATION", "COMPLICATED_BY", "HAS_EXACERBATION", "PROGRESSES_TO",
                     "HAS_POST_ACUTE_CONDITION")),
    "monitoring": ("Theo dõi bệnh / theo dõi điều trị",
                   ("MONITORED_BY", "HAS_MONITORING", "REQUIRES_MONITORING", "HAS_MONITORING_PARAMETER",
                    "HAS_MONITORING_SCHEDULE")),
    "prognosis": ("Tiên lượng, kết cục, diễn tiến, đáp ứng điều trị",
                  ("HAS_OUTCOME", "HAS_PROGNOSTIC_FINDING", "PREDICTS", "HAS_TREATMENT_OUTCOME",
                   "HAS_TREATMENT_RESPONSE", "HAS_TIME_COURSE", "HAS_PREVALENCE", "PREDICTS_TREATMENT_RESPONSE",
                   "ASSOCIATED_WITH_RESPONSE", "CAUSES_FUNCTIONAL_IMPAIRMENT", "LIMITS_ACTIVITY")),
    "recommendation": ("Khuyến cáo, phác đồ từng bậc, mục tiêu điều trị, khi nào nhập viện",
                       ("HAS_RECOMMENDATION", "RECOMMENDS", "RECOMMENDED_FOR", "RECOMMENDS_AT_STEP", "HAS_STEP",
                        "STEP_UP_TO", "STEP_DOWN_TO", "ESCALATES_TO", "HAS_PROTOCOL", "HAS_TREATMENT_PHASE",
                        "HAS_TREATMENT_GOAL", "HAS_GOAL", "INDICATED_WHEN", "BIOMARKER_GUIDES_TREATMENT",
                        "HAS_THERAPEUTIC_TARGET", "HAS_TREATMENT_EFFECT", "HAS_NUTRITION_SUPPORT",
                        "HAS_VENTILATION_MODE", "REQUIRES_HOSPITALIZATION", "REQUIRES_ISOLATION")),
    "transmission": ("Lây truyền, tính lây nhiễm, ủ bệnh, giảm phơi nhiễm",
                     ("TRANSMITTED_VIA", "SPREADS_VIA", "INCREASES_TRANSMISSION_RISK",
                      "REDUCES_TRANSMISSION", "REDUCES_EXPOSURE_TO", "CONTROLS_EXPOSURE_TO", "HAS_INFECTIOUSNESS",
                      "INCREASES_INFECTIOUSNESS", "DECREASES_INFECTIOUSNESS", "HAS_INCUBATION_PERIOD")),
    "resistance": ("Kháng thuốc / nhạy cảm thuốc",
                   ("RESISTANT_TO", "CONFERS_RESISTANCE_TO", "HAS_RESISTANCE_TYPE", "HAS_MUTATION_IN",
                    "TESTS_SUSCEPTIBILITY_TO", "HAS_SUSCEPTIBILITY", "SUSCEPTIBLE_TO", "DETECTS_RESISTANCE_TO",
                    "ASSESSES_RESISTANCE_TO")),
    "rehabilitation": ("Phục hồi chức năng, bài tập", ("HAS_EXERCISE", "HAS_EXERCISE_STAGE", "IMPROVES", "HAS_ADAPTATION")),
    "population": ("Nhóm bệnh nhân / đối tượng áp dụng",
                   ("FOR_PATIENT_GROUP", "HAS_PATIENT_GROUP", "ASSOCIATED_WITH_POPULATION", "HAS_COHORT",
                    "HAS_ELIGIBILITY_CRITERION", "HAS_CONDITION")),
    "mechanism": ("Cơ chế sinh học (tế bào, cytokine, thụ thể)",
                  ("ACTIVATES", "STIMULATES", "RECRUITS", "SECRETES", "BINDS_TO", "MEDIATES", "MEDIATED_BY",
                   "DIFFERENTIATES_INTO", "EXPRESSES", "INFILTRATES", "GENERATES", "INDUCES_IMMUNE_RESPONSE", "TARGETS",
                   "MEMBER_OF_COMPLEX")),
    "anatomy": ("Vị trí giải phẫu, cơ quan bị ảnh hưởng",
                ("LOCATED_IN", "PART_OF", "AFFECTS", "AFFECTS_SITE")),
}

# Compact ontology coverage. Keep legacy relation names for older active snapshots.
_ADDITIONS = {
    'dosage': ('HAS_DURATION', 'HAS_FREQUENCY'),
    'diagnosis': ('HAS_LABORATORY_FINDING', 'INDICATES', 'SPECIFIES_CRITERION'),
    'prognosis': ('HAS_PROGNOSTIC_FACTOR',),
    'resistance': ('HAS_DRUG_RESISTANCE',),
    'membership': ('HAS_TREATMENT_COMPONENT', 'USES_MEDICATION'),
    'recommendation': ('NOT_RECOMMENDED_FOR',),
}
for _name, _rels in _ADDITIONS.items():
    _desc, _old = _DEFS[_name]
    _DEFS[_name] = (_desc, tuple(dict.fromkeys((*_old, *_rels))))
_DEFS.update({
    'taxonomy': ('Phân loại cha/con (IS_A)', ('IS_A',)),
    'screening': ('Sàng lọc (tách biệt với chẩn đoán)', ('SCREENED_BY',)),
    'epidemiology': ('Chỉ số dịch tễ và quần thể nghiên cứu', ('HAS_EPIDEMIOLOGICAL_MEASURE', 'HAS_COHORT')),
    'source_topic': ('Tài liệu/hướng dẫn đề cập chủ đề', ('COVERS_TOPIC',)),
    'sequence': ('Trình tự và các bước điều trị', ('FOLLOWED_BY', 'HAS_TREATMENT_STEP')),
    'setting': ('Môi trường áp dụng, cách ly và nhập viện', ('APPLIED_IN', 'REQUIRES_ISOLATION', 'REQUIRES_HOSPITALIZATION')),
    'applicability': ('Điều kiện và nhóm đối tượng áp dụng', ('HAS_CONDITION', 'FOR_PATIENT_GROUP')),
    'regimen': ('Phác đồ và các thành phần điều trị', ('HAS_REGIMEN', 'HAS_REGIMEN_COMPONENT', 'HAS_TREATMENT_COMPONENT', 'USES_MEDICATION')),
    'rehabilitation': ('Can thiệp phục hồi và mục tiêu (cần lọc loại Rehabilitation)', ('TREATS', 'INDICATED_FOR', 'HAS_TREATMENT_GOAL', 'USES_DEVICE', 'HAS_TREATMENT_COMPONENT')),
})

DRUG_TYPES = ("Medication", "DrugClass", "DrugCombination", "ActiveIngredient")

# Multi-hop = a chain of intents; each step expands from the previous step's result.
# `include_previous` keeps the step's input in its output (so a drug that is NOT in a class is not lost).
PRESET_CHAINS: dict[str, tuple[Step, ...]] = {
    "drugs_for_disease": (
        Step("treatment", DRUG_TYPES),
        Step("membership", DRUG_TYPES, include_previous=True),
    ),
    "drug_adverse_effects": (
        Step("treatment", DRUG_TYPES),
        Step("membership", DRUG_TYPES, include_previous=True),
        Step("adverse_effect", ("AdverseEffect", "AdverseEvent", "AdverseDrugReaction",
                                "Symptom", "ClinicalSign", "LaboratoryFinding", "Disease")),
    ),
    "drug_contraindications": (
        Step("treatment", DRUG_TYPES),
        Step("membership", DRUG_TYPES, include_previous=True),
        Step("contraindication"),
    ),
}


# Explicit directional paths preserve the meaning of every individual edge.
DISEASE_TYPES = ('Disease', 'DiseaseSubtype', 'Syndrome', 'ClinicalCondition', 'Complication', 'Exacerbation')
TEST_TYPES = ('DiagnosticTest', 'LaboratoryTest', 'Imaging', 'FunctionalTest', 'ClinicalAssessment')
INTERVENTION_TYPES = (*DRUG_TYPES, 'Treatment', 'TreatmentRegimen', 'Procedure', 'Surgery', 'Rehabilitation', 'RespiratorySupport')
def edge(*relations, direction='out', targets=None, optional=False):
    return Step('related', tuple(targets) if targets else None, optional, tuple(relations), direction)

# Correct class-to-member traversal: BELONGS_TO_DRUG_CLASS must be read backwards.
# Direction is auto only in the legacy-compatible first three presets.
_member = Step('membership', DRUG_TYPES, True,
    ('HAS_MEMBER','CONTAINS','CONTAINS_MEDICATION','INCLUDES_MEDICATION','HAS_ACTIVE_INGREDIENT','BELONGS_TO_DRUG_CLASS'))
PRESET_CHAINS['drugs_for_disease'] = (PRESET_CHAINS['drugs_for_disease'][0], _member)
PRESET_CHAINS['drug_adverse_effects'] = (*PRESET_CHAINS['drugs_for_disease'], Step('adverse_effect', ('AdverseEvent','AdverseEffect','AdverseDrugReaction','Symptom','ClinicalSign','LaboratoryFinding','Disease')))
PRESET_CHAINS['drug_contraindications'] = (*PRESET_CHAINS['drugs_for_disease'], Step('contraindication'))
PRESET_CHAINS.update({
    'regimen_medications': (edge('HAS_REGIMEN', targets=('TreatmentRegimen',)), edge('HAS_REGIMEN_COMPONENT','USES_MEDICATION','HAS_TREATMENT_COMPONENT', targets=DRUG_TYPES)),
    'regimen_adverse_effects': (edge('HAS_REGIMEN', targets=('TreatmentRegimen',)), edge('HAS_REGIMEN_COMPONENT','USES_MEDICATION','HAS_TREATMENT_COMPONENT', targets=DRUG_TYPES), edge('HAS_ADVERSE_EFFECT','CAUSES_ADVERSE_EVENT')),
    'regimen_dosage': (edge('HAS_REGIMEN', targets=('TreatmentRegimen',)), edge('HAS_REGIMEN_COMPONENT','USES_MEDICATION', targets=DRUG_TYPES), edge('HAS_DOSE','HAS_ROUTE','HAS_FREQUENCY','HAS_DURATION')),
    'recommendation_interventions': (edge('HAS_RECOMMENDATION', targets=('Recommendation',)), edge('RECOMMENDS_INTERVENTION')),
    'recommendation_conditions': (edge('HAS_RECOMMENDATION', targets=('Recommendation',)), edge('HAS_CONDITION','FOR_PATIENT_GROUP')),
    'diagnostic_findings': (edge('DIAGNOSED_BY', targets=TEST_TYPES), edge('PRODUCES_FINDING','MEASURES')),
    'diagnostic_specimens': (edge('DIAGNOSED_BY', targets=TEST_TYPES), edge('USES_SPECIMEN')),
    'criteria_thresholds': (edge('HAS_DIAGNOSTIC_CRITERION','SPECIFIES_CRITERION'), edge('HAS_THRESHOLD')),
    'resistant_medications': (edge('HAS_DRUG_RESISTANCE'), edge('RESISTANT_TO','CONFERS_RESISTANCE_TO')),
    'pathogen_resistance': (edge('CAUSED_BY'), edge('HAS_DRUG_RESISTANCE'), edge('RESISTANT_TO','CONFERS_RESISTANCE_TO')),
    'regimen_monitoring': (edge('HAS_REGIMEN'), edge('MONITORED_BY')),
    'treatment_sequence': (edge('HAS_REGIMEN','HAS_TREATMENT_STEP'), edge('HAS_TREATMENT_STEP','FOLLOWED_BY'), edge('FOLLOWED_BY', optional=True)),
    'prevention_settings': (edge('PREVENTS','REDUCES_TRANSMISSION', direction='in', targets=('PreventiveMeasure','InfectionControlMeasure')), edge('APPLIED_IN')),
    'rehabilitation_goals': (edge('TREATS','INDICATED_FOR', direction='in', targets=('Rehabilitation',)), edge('HAS_TREATMENT_GOAL')),
    'prognostic_outcomes': (edge('HAS_PROGNOSTIC_FACTOR'), edge('PREDICTS')),
    'guideline_interventions': (edge('COVERS_TOPIC', direction='in', targets=('ClinicalGuideline',)), edge('RECOMMENDS','HAS_RECOMMENDATION'), edge('RECOMMENDS_INTERVENTION', optional=True)),
})
PRESET_LABELS = {
    'drugs_for_disease':'Bệnh → thuốc/nhóm thuốc → thành phần',
    'drug_adverse_effects':'Bệnh → thuốc → tác dụng bất lợi',
    'drug_contraindications':'Bệnh → thuốc → chống chỉ định/thận trọng',
    'regimen_medications':'Bệnh → phác đồ → thuốc/thành phần',
    'regimen_adverse_effects':'Bệnh → phác đồ → thuốc → tác dụng bất lợi',
    'regimen_dosage':'Bệnh → phác đồ → thuốc → liều/đường/tần suất/thời gian',
    'recommendation_interventions':'Chủ đề → khuyến nghị → can thiệp',
    'recommendation_conditions':'Chủ đề → khuyến nghị → điều kiện/đối tượng',
    'diagnostic_findings':'Bệnh → xét nghiệm → phát hiện/đại lượng',
    'diagnostic_specimens':'Bệnh → xét nghiệm → bệnh phẩm',
    'criteria_thresholds':'Bệnh/hướng dẫn → tiêu chuẩn → ngưỡng',
    'resistant_medications':'Bệnh/tác nhân → hồ sơ kháng → thuốc',
    'pathogen_resistance':'Bệnh → tác nhân → hồ sơ kháng → thuốc',
    'regimen_monitoring':'Bệnh → phác đồ → theo dõi',
    'treatment_sequence':'Bệnh → phác đồ/bước → trình tự',
    'prevention_settings':'Bệnh → biện pháp dự phòng → môi trường áp dụng',
    'rehabilitation_goals':'Bệnh → phục hồi chức năng → mục tiêu',
    'prognostic_outcomes':'Bệnh → yếu tố tiên lượng → kết cục',
    'guideline_interventions':'Chủ đề → hướng dẫn → khuyến cáo/can thiệp',
}
PRESET_START_TYPES = {k: DISEASE_TYPES for k in PRESET_CHAINS}
PRESET_START_TYPES.update({
    'recommendation_interventions': (*DISEASE_TYPES, 'ClinicalGuideline'),
    'recommendation_conditions': (*DISEASE_TYPES, 'ClinicalGuideline'),
    'criteria_thresholds': (*DISEASE_TYPES, 'ClinicalGuideline', 'ClinicalRule'),
    'resistant_medications': (*DISEASE_TYPES, 'Pathogen','Bacterium','Virus'),
    'guideline_interventions': (*DISEASE_TYPES, 'Symptom','Treatment','Procedure','DiagnosticTest','Pathogen'),
})

def preset_catalog(ontology):
    intents = build_intents(ontology)
    catalog = [{'id': key, 'label': PRESET_LABELS[key], 'start_types': [t for t in PRESET_START_TYPES[key] if ontology.has_entity_type(t)],
        'steps': [{'intent': s.intent, 'relations': [r for r in (s.rel_types or intents[s.intent].relations) if ontology.has_relation(r)],
                   'direction': s.direction, 'target_types': [t for t in (s.target_types or ()) if ontology.has_entity_type(t)],
                   'optional': s.include_previous} for s in steps]}
        for key, steps in PRESET_CHAINS.items()]
    for entry in catalog:
        try:
            preset_steps(entry['id'], ontology)
            entry.update(available=True, unavailable_reason=None)
        except ValueError as error:
            entry.update(available=False, unavailable_reason=str(error))
    return catalog


def preset_steps(key, ontology):
    if key not in PRESET_CHAINS:raise ValueError('Chuỗi truy vấn không tồn tại.')
    intents=build_intents(ontology);steps=[]
    for s in PRESET_CHAINS[key]:
        rels=tuple(r for r in (s.rel_types or intents[s.intent].relations) if ontology.has_relation(r))
        types=tuple(t for t in s.target_types if ontology.has_entity_type(t)) if s.target_types else None
        if not rels or s.target_types and not types:
            if s.include_previous:continue
            raise ValueError('Ontology thiếu quan hệ/loại đích cho chuỗi '+key)
        steps.append(Step(s.intent,types,s.include_previous,rels,s.direction))
    return steps


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    relations: tuple[str, ...]


def build_intents(ontology: Ontology) -> dict[str, Intent]:
    """Relations missing from the ontology are dropped (never interpolated into Cypher)."""
    out = {name: Intent(name, desc, tuple(r for r in rels if ontology.has_relation(r)))
           for name, (desc, rels) in _DEFS.items()}
    out[CATCH_ALL] = Intent(CATCH_ALL, "Bất kỳ quan hệ nào (dùng khi không xác định được ý định cụ thể)",
                            tuple(ontology.relation_names()))
    return out


def unknown_relation_names(ontology: Ontology) -> dict[str, list[str]]:
    """Typo detector: names used in the groups that the ontology does not define."""
    return {n: bad for n, (_, rels) in _DEFS.items() if (bad := [r for r in rels if not ontology.has_relation(r)])}


def uncovered_relations(ontology: Ontology) -> list[str]:
    """Ontology relations that no specific intent contains (reachable only through `related`)."""
    used = {r for _, rels in _DEFS.values() for r in rels}
    return [r for r in ontology.relation_names() if r not in used]


def describe_intents() -> list[tuple[str, str]]:
    """(name, description) pairs to paste into the question-analysis prompt."""
    return [(n, d) for n, (d, _) in _DEFS.items()] + [(CATCH_ALL, "Không rõ ý định cụ thể")]
