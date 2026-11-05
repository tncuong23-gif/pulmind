import copy,json,unittest
from unittest.mock import Mock
from tests.upstream.kg.helpers import ServiceTestCase
from app.modules.kg_import.manual_merge import manager,resolve_redirects

class MergeTests(ServiceTestCase):
    def merge_payload(self):
        p=self.p();p['entities']=[{'id':'A','type':'Disease','canonical_name':'Same'}, {'id':'B','type':'Complication','canonical_name':'Same'}];p['relations']=[];p['propositions']=[];return p
    def choice(self,kind='Disease'):
        return {'ids':['A','B'],'target_id':'A','type':kind,'name':'Same canonical'}
    def seed(self):
        p=self.merge_payload();p['entity_type_decisions']={'A':'distinct','B':'distinct'}
        self.assertEqual(self.svc.import_kg(p).status,'completed')
    def test_new_cross_type_merge_and_original_ids_survive(self):
        m=manager(self.svc);p=self.merge_payload();q=m.preview(p,self.choice());self.assertTrue(q['can_apply']);self.assertFalse(self.graph.entities)
        out=m.apply(p,q['token']);self.assertEqual(len(out['payload']['entities']),1);self.assertEqual(self.graph.merge_aliases['B']['merged_into'],'A')
        self.assertEqual(self.svc.import_kg(out['payload']).status,'completed')
        self.assertEqual(resolve_redirects(p,self.graph)['entities'][0]['id'],'A')
    def test_same_type_merge(self):
        p=self.merge_payload();p['entities'][1]['type']='Disease';m=manager(self.svc);q=m.preview(p,self.choice());self.assertTrue(q['can_apply'])
    def test_select_third_type(self):
        p=self.merge_payload();m=manager(self.svc);q=m.preview(p,self.choice('ClinicalFinding'));self.assertTrue(q['can_apply']);out=m.apply(p,q['token']);self.assertEqual(out['payload']['entities'][0]['type'],'ClinicalFinding')
    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):manager(self.svc).preview(self.merge_payload(),self.choice('ImaginaryType'))
    def test_stale_payload(self):
        m=manager(self.svc);p=self.merge_payload();q=m.preview(p,self.choice());p['document']['title']='changed'
        with self.assertRaises(ValueError):m.apply(p,q['token'])
        self.assertFalse(self.graph.entities)
    def test_stale_graph(self):
        self.seed();m=manager(self.svc);q=m.preview(None,self.choice());self.graph.entities['B']['aliases']=['changed']
        with self.assertRaises(ValueError):m.apply(None,q['token'])
        self.assertIn('B',self.graph.entities)
    def test_stored_relations_preserve_ids_and_sources(self):
        self.seed();self.graph.entities['C']={**copy.deepcopy(self.graph.entities['A']),'id':'C','entity_type':'Symptom'}
        self.graph.relations['R']={'id':'R','type':'HAS_SYMPTOM','source_id':'B','target_id':'C','source_document_id':'D',
            'proposition_ids':['P'],'evidence_ids':['E'],'properties_json':'{"negated":true}','confidence':0.9,'content_hash':'old'}
        m=manager(self.svc);q=m.preview(None,self.choice());self.assertTrue(q['can_apply']);out=m.apply(None,q['token'])
        edge=self.graph.relations['R'];self.assertEqual(edge['source_id'],'A');self.assertEqual(edge['evidence_ids'],['E']);self.assertEqual(edge['properties_json'],'{"negated":true}');self.assertNotIn('B',self.graph.entities)
    def test_invalid_relation_blocks_before_write(self):
        self.seed();self.graph.entities['C']={**copy.deepcopy(self.graph.entities['A']),'id':'C','entity_type':'Symptom'}
        self.graph.relations['R']={'id':'R','type':'HAS_SYMPTOM','source_id':'B','target_id':'C','properties_json':'{}'}
        q=manager(self.svc).preview(None,self.choice('Medication'));self.assertFalse(q['can_apply']);self.assertNotIn('token',q)
    def test_property_conflict_blocks(self):
        p=self.merge_payload();p['entities'][0]['properties']={'severity':'high'};p['entities'][1]['properties']={'severity':'low'}
        q=manager(self.svc).preview(p,self.choice());self.assertFalse(q['can_apply'])
    def test_self_edge_blocks(self):
        self.seed();self.graph.relations['R']={'id':'R','type':'HAS_COMPLICATION','source_id':'A','target_id':'B','properties_json':'{}'}
        q=manager(self.svc).preview(None,self.choice());self.assertFalse(q['can_apply']);self.assertIn('SELF_RELATION',[x['code'] for x in q['conflicts']])
    def test_apply_failure_keeps_original_graph(self):
        self.seed();before=copy.deepcopy(self.graph.entities);m=manager(self.svc);q=m.preview(None,self.choice());self.graph.fail_on_write=True
        with self.assertRaises(RuntimeError):m.apply(None,q['token'])
        self.assertEqual(self.graph.entities,before)
    def test_vector_failure_returns_partial_warning(self):
        m=manager(self.svc);p=self.merge_payload();q=m.preview(p,self.choice());index=Mock();index.delete_entities.side_effect=RuntimeError('offline');self.svc.entity_index=index
        out=m.apply(p,q['token']);self.assertTrue(out['warning']);self.assertIn('A',self.graph.entities)
    def test_token_cannot_replay(self):
        m=manager(self.svc);p=self.merge_payload();q=m.preview(p,self.choice());m.apply(p,q['token'])
        with self.assertRaises(ValueError):m.apply(p,q['token'])
    def test_original_input_unchanged(self):
        p=self.merge_payload();old=copy.deepcopy(p);manager(self.svc).preview(p,self.choice());self.assertEqual(p,old)
