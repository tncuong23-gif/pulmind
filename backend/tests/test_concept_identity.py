import copy,json,unittest
from pathlib import Path
from app.modules.kg_import.concept_identity import policy,normalize_concepts,normalization_issues
from app.modules.kg_import.errors import ValidationError
from app.modules.kg_import.service import KGImportService
from app.modules.kg_import.ontology import Ontology
from app.modules.kg_import.adapters.memory import MemoryDocumentStore,MemoryGraphStore,MemoryJobStore

ROOT=Path(__file__).resolve().parents[1]
def sample():
    group=next(g for g in policy()['groups'] if g['canonical_name']=='Hen phế quản')
    members=copy.deepcopy(group['members'])
    return {'schema_version':'1.0','document':{'document_id':'TEST','title':'Test','document_type':'clinical_guideline','language':'vi','sections':[]},'entities':members,'relations':[],'propositions':[]}
class ConceptTests(unittest.TestCase):
    def test_original_untouched(self):
        p=sample();before=copy.deepcopy(p);normalize_concepts(p);self.assertEqual(p,before)
    def test_merge_and_idempotence(self):
        p=sample();out,m=normalize_concepts(p);self.assertEqual(len(out['entities']),1);self.assertEqual(normalize_concepts(out)[0],out);self.assertEqual(len(set(m.values())),1)
    def test_old_ids_blocked(self):
        self.assertTrue(normalization_issues(sample()));self.assertFalse(normalization_issues(normalize_concepts(sample())[0]))
    def test_mismatched_id_blocked(self):
        p=sample();p['entities'][0]['canonical_name']='Completely different concept'
        with self.assertRaises(ValidationError):normalize_concepts(p)
    def test_property_conflict(self):
        p=sample();p['entities'][0]['properties']={'qualifier':'different'}
        with self.assertRaises(ValidationError):normalize_concepts(p)
    def test_sources_and_relation_ids_unchanged(self):
        p=sample();a,b=p['entities'][:2];p['relations']=[{'id':'R','source':a['id'],'target':b['id'],'type':'RELATED_TO','proposition_ids':['P']}];p['propositions']=[{'id':'P','text':'source','evidence':[{'text':'original'}],'entity_ids':[a['id'],b['id']]}]
        out,m=normalize_concepts(p);self.assertEqual(out['relations'][0]['id'],'R');self.assertEqual(out['propositions'][0]['evidence'],p['propositions'][0]['evidence']);self.assertEqual(out['relations'][0]['source'],m[a['id']])
    def test_unknown_same_name_not_automerged(self):
        p=sample();p['entities']=[{'id':'unknown1','type':'Disease','canonical_name':'Ho'},{'id':'unknown2','type':'RiskFactor','canonical_name':'Ho'}];self.assertEqual(len(normalize_concepts(p)[0]['entities']),2)
    def test_import_normalized_and_preserve_original_map(self):
        p,m=normalize_concepts(sample());docs=MemoryDocumentStore();svc=KGImportService(Ontology.load(ROOT/'examples/kg/kg_ontology.example.json'),docs,MemoryGraphStore(),MemoryJobStore())
        self.assertEqual(svc.import_kg(sample()).status,'failed');self.assertEqual(svc.import_kg(p).status,'completed')
        saved=docs.data['documents'][('TEST','TEST')];self.assertEqual(saved['entity_id_map'],m)
    def test_ontology_supports_roles(self):
        o=Ontology.load(ROOT/'examples/kg/kg_ontology.example.json');self.assertIsNone(o.domain_range_error('RISK_FACTOR_FOR','Disease','Disease'));self.assertIsNone(o.domain_range_error('HAS_ADVERSE_EFFECT','Medication','Symptom'))
    def test_query_keeps_normalized_adverse_effects(self):
        from app.modules.kg_query.intents import PRESET_CHAINS
        types=PRESET_CHAINS['drug_adverse_effects'][-1].target_types
        self.assertIn('Symptom',types);self.assertIn('Disease',types)
    def test_risk_query_can_traverse_disease_role(self):
        from app.modules.kg_query.service import KGQueryService
        svc=KGQueryService(None,Ontology.load(ROOT/'examples/kg/kg_ontology.example.json'))
        plan=svc.direction_plan('Disease',['RISK_FACTOR_FOR'])
        self.assertIn('RISK_FACTOR_FOR',plan['any'])
    def test_candidate_dedup(self):
        # Duplicate retrieval hits must have one review row.
        from unittest.mock import Mock
        idx=Mock();idx.ready.return_value=True;idx.suggest_many.return_value=[[{'entity_id':'OLD','canonical_name':'Other','entity_type':'Disease','score':0.9}]*2]
        graph=MemoryGraphStore();graph.entities['OLD']={'id':'OLD','canonical_name':'Other','normalized_name':'other','content_hash':'test','entity_type':'Disease','aliases':[],'properties':{}}
        p=sample();p['entities']=[{'id':'NEW','canonical_name':'Something else','type':'Disease'}]
        svc=KGImportService(Ontology.load(ROOT/'examples/kg/kg_ontology.example.json'),MemoryDocumentStore(),graph,MemoryJobStore(),entity_index=idx)
        r=svc.import_kg(p,dry_run=True);self.assertEqual(len(r.plan['entity_candidates']['NEW']),1)
if __name__=='__main__':unittest.main()
