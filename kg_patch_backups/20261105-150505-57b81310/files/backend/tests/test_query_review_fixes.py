from app.modules.kg_query.intents import preset_catalog
from app.modules.kg_query.question_analysis import comparison_mode, detect_intents
from app.modules.kg_query.retrieval_api import QueryRequest, retrieve
from app.services.evidence import prepare_evidence
from app.services.retrieval_quality import usable_fact
from tests.test_kg_chat_query import fixture_service


def test_negative_intent_does_not_override_positive_question():
    assert comparison_mode("Không so sánh, chỉ nêu triệu chứng của COPD.") is None
    assert detect_intents("Tôi không hỏi về điều trị, chỉ hỏi triệu chứng COPD.") == ["symptom"]


def test_partial_path_identifies_the_missing_endpoint():
    result = retrieve(fixture_service(), QueryRequest(question="Mối liên hệ giữa lao và COPD?"))
    assert result.status == "needs_clarification"
    assert result.query["mode"] == "path"
    assert result.clarification["reason"] == "missing_entity"
    assert "lao" in result.clarification["message"]
    assert result.clarification["groups"][1]["candidates"][0]["id"] == "D1"


def test_preset_catalog_reports_unavailable_templates():
    entries = {entry["id"]: entry for entry in preset_catalog(fixture_service().ontology)}
    assert entries["regimen_dosage"]["available"] is False
    assert entries["regimen_dosage"]["unavailable_reason"]
    assert entries["drugs_for_disease"]["available"] is True


def test_evidence_is_reserved_for_each_assertion():
    from app.modules.kg_query.models import EntityRef, Fact
    from app.modules.kg_query.service import KGQueryService

    class EvidenceStore:
        def fetch(self, document_id, ids):
            return {eid: {"text": "Source text"} for eid in ids}

    service = KGQueryService(None, fixture_service().ontology, evidence_store=EvidenceStore())
    fact = Fact(EntityRef("A", "A", "Disease"), "HAS_SYMPTOM",
                EntityRef("B", "B", "Symptom"), "A")
    for i in range(4):
        fact.add_row({"rel_id": str(i), "doc_id": str(i), "evidence_ids": [str(i)], "properties_json": "{}"})
    service.attach_evidence([fact])
    assert len(fact.evidence_texts) == 4
    assert usable_fact(fact.to_dict())


def test_budget_keeps_complete_chains_and_remaps_references():
    facts = []
    for index in range(4):
        key = str(index)
        facts.append({
            "subject": {"name": key, "type": "Disease"},
            "object": {"name": str(index + 1), "type": "Disease"},
            "predicate": "IS_A",
            "evidence": [{"doc_id": key, "evidence_id": key, "text": key * 2500}],
            "assertions": [{"document_id": key, "evidence_ids": [key], "properties": {}, "properties_valid": True}],
        })
    result = {"status": "ok", "llm_context": {
        "facts": facts, "chains": [{"fact_indices": [0, 1]}, {"fact_indices": [2, 3]}],
    }}
    pack = prepare_evidence({"module_results": {"kg": result}}, max_bytes=8500)
    kg = pack.payload["module_results"]["kg"]
    assert kg["chains"] == [{"fact_indices": [0, 1]}]
    assert len(kg["facts"]) == 2
    assert len(pack.sources) == 2
    assert kg["facts"][1]["assertions"][0]["source_refs"] == [2]


def test_short_path_endpoint_offers_top_three_for_confirmation():
    service = fixture_service()
    for i, name in enumerate(["Lao phổi", "Bệnh lao", "Lao màng phổi", "Lao ngoài phổi", "Lào thử nghiệm dài"]):
        service.driver.g.entities[f"TB{i}"] = {
            "id": f"TB{i}", "canonical_name": name, "entity_type": "Disease", "aliases": [],
        }
    result = retrieve(service, QueryRequest(question="Mối liên hệ giữa lao và COPD"))
    assert result.status == "needs_clarification"
    assert result.query["mode"] == "path"
    assert result.clarification["can_confirm"]
    candidates = result.clarification["groups"][0]["candidates"]
    assert [c["name"] for c in candidates] == ["Bệnh lao", "Lao phổi", "Lao màng phổi"]
    assert all(c["matched_by"] == "fuzzy" for c in candidates)
    assert result.clarification["groups"][1]["candidates"][0]["id"] == "D1"
    assert not result.llm_context["facts"]
