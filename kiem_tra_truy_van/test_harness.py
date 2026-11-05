"""Self-tests for the diagnostic tool. No models or live databases required."""
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import zipfile
import shutil
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import unittest
from unittest.mock import patch
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('diagnostics',BASE/'test_queries.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class Handler(BaseHTTPRequestHandler):
    requests=[]
    def log_message(self,*args):pass
    def send(self,code,value):
        self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(value).encode())
    def do_GET(self):
        if self.path.endswith('/meta'):return self.send(200,self.catalog)
        return self.send(200,{'status':'ok'})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));self.requests.append((self.path,body))
        if self.path.endswith('/api/v1/chat/message'):return self.send(502,{'detail':{'code':'UPSTREAM_FAILURE','request_id':'test'}})
        if self.path.endswith('/query'):
            sys.path.insert(0,str(Path(os.environ.get('MEDICAL_TEST_PROJECT',str(BASE)))/'backend'))
            from app.modules.kg_query.retrieval_api import QueryRequest
            try:QueryRequest.model_validate(body)
            except Exception:return self.send(422,{'error':'validation'})
            return self.send(200,{'status':'no_facts','llm_context':{'facts':[]}})
        if self.path.endswith('/search'):return self.send(200,{'ok':True,'hits':[]})
        return self.send(200,{'items':[]})

class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project=Path(os.environ.get('MEDICAL_TEST_PROJECT',str(BASE)))
        sys.path.insert(0,str(project/'backend'))
        from app.modules.kg_query.intents import describe_intents,PRESET_CHAINS
        ontology=json.loads((project/'backend/examples/kg/kg_ontology.example.json').read_text(encoding='utf-8-sig'))
        Handler.catalog={'intents':[{'id':k,'description':v} for k,v in describe_intents()],
                         'presets':list(PRESET_CHAINS),'ontology':{'relations':list(ontology['relation_types']),'entity_types':ontology['entity_types']}}
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_complete_suite_covers_modes_and_records_http_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            runner=d.Runner('http://127.0.0.1:'+str(self.server.server_port),Path(folder),5)
            d.suite(runner,{'samples':{'Disease':[{'id':'D1'},{'id':'D2'}],'AnatomicalStructure':[{'id':'A1'}],'Symptom':[{'id':'S1'}]}},quick=False,chat=True)
            invalid=[r for r in runner.records if r['group']=='validation']
            self.assertEqual(len(invalid),7);self.assertTrue(all(r['http_status']==422 and r['outcome']=='HTTP_OK' for r in invalid))
            self.assertTrue(any(r['case']=='relation:HAS_SYMPTOM' for r in runner.records))
            for mode in ('auto','one_hop','path','compare','common','difference'):
                self.assertTrue(any(r['case']=='mode:'+mode for r in runner.records))
            self.assertTrue(all(r['outcome']=='HTTP_ERROR' for r in runner.records if r['group']=='chat'))
            self.assertEqual(len((Path(folder)/'requests.jsonl').read_text(encoding='utf-8').splitlines()),len(runner.records))
            # All positive KG payloads must satisfy the actual project's request schema.
            self.assertFalse([r['case'] for r in runner.records if r['group']=='kg' and r.get('http_status')==422])
    def test_startup_failure_still_builds_shareable_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'medical-ai-integrated';backend=root/'backend/app';backend.mkdir(parents=True)
            (backend/'__init__.py').write_text('')
            (backend/'main.py').write_text("raise RuntimeError('SIMULATED_STARTUP_FAILURE')")
            result=subprocess.run([sys.executable,str(BASE/'test_queries.py'),'--project',str(root),
                '--startup-timeout','5','--probe-timeout','5','--no-chat'],capture_output=True,text=True,encoding='utf-8',timeout=20)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            archive=Path(result.stdout.split('SEND THIS ZIP: ')[-1].strip())
            try:
                with zipfile.ZipFile(archive) as z:
                    self.assertIn('backend.log',z.namelist());self.assertIn('summary.json',z.namelist())
                    self.assertIn('SIMULATED_STARTUP_FAILURE',z.read('backend.log').decode())
                    self.assertFalse(any('.sqlite' in name or '.env' in name for name in z.namelist()))
                    self.assertTrue(json.loads(z.read('summary.json'))['fatal_error'])
            finally:
                if archive.exists():
                    shutil.rmtree(archive.parent/archive.name.removesuffix('-query-logs.zip'),ignore_errors=True)
                    archive.unlink()
    def test_traceback_captures_an_empty_assertion(self):
        stream=io.StringIO();logger=logging.getLogger('diagnostic-self-test');logger.handlers=[];logger.propagate=False
        handler=logging.StreamHandler(stream);logger.addHandler(handler);logger.addFilter(d.TracebackFilter());logger.setLevel(logging.INFO)
        try:
            assert False
        except AssertionError:logger.error('chat.failed error_type=AssertionError')
        self.assertIn('Traceback (most recent call last)',stream.getvalue());self.assertIn('AssertionError',stream.getvalue())
    def test_utf8_catalog_on_windows_legacy_default_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.json'
            expected={'Định danh':'Triệu chứng và thuốc', 'disease':'Bệnh phổi tắc nghẽn mạn tính'}
            path.write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8')
            original=Path.read_text
            def windows_read_text(self,*args,**kwargs):
                kwargs.setdefault('encoding','cp1252')
                return original(self,*args,**kwargs)
            with patch.object(Path,'read_text',windows_read_text):
                with self.assertRaises(UnicodeDecodeError):path.read_text()
                self.assertEqual(d.read_json(path),expected)
            path.write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8-sig')
            self.assertEqual(d.read_json(path),expected)
    def test_redaction(self):
        text='mongodb://user:password123@localhost password=abc api_key=xyz Authorization: Bearer SECRET'
        result=d.redact(text)
        for secret in ('password123','abc','xyz','SECRET'):self.assertNotIn(secret,result)
    def test_windows_bat_structure(self):
        for p in BASE.glob('*.bat'):
            raw=p.read_bytes();self.assertNotIn(b'\n',raw.replace(b'\r\n',b''));self.assertIn(b'%~dp0backend',raw);self.assertIn(b'if not exist "%~dp0test_queries.py"',raw)
if __name__=='__main__':unittest.main(verbosity=2)
