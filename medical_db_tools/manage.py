"""Isolated local database setup. Python 3.11+, stdlib only; Windows entry points."""
from __future__ import annotations
import contextlib, datetime, hashlib, json, os, pathlib, re, secrets, shutil, socket, subprocess, sys, time, urllib.request, uuid
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIR = ROOT / 'medical_db_tools'
STATE = DIR / 'state.json'
OWNER = 'medical-ai.isolated.owner'
SERVICES = ('neo4j', 'mongo', 'qdrant')
DOCKER = 'docker'
LOG = None

def log(message):
    print(message, flush=True)
    if LOG:
        LOG.write(str(message) + '\n'); LOG.flush()

def command(args, *, capture=False, check=True, timeout=None):
    # Never use a shell, and never log command arguments containing credentials.
    if capture:
        p = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           encoding='utf-8', errors='replace', timeout=timeout)
        if check and p.returncode:
            raise RuntimeError('Lenh kiem tra that bai. Kiem tra Docker Desktop / nhat ky dich vu.')
        return p
    p = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         encoding='utf-8', errors='replace', bufsize=1)
    try:
        for line in p.stdout: log(line.rstrip())
        code = p.wait()
    except BaseException:
        p.terminate(); p.wait(); raise
    if check and code: raise RuntimeError(f'Tac vu ben ngoai that bai (ma {code}). Xem thong bao phia tren.')
    return code

def docker(*args, **kw): return command([DOCKER, *args], **kw)

def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(temp, path)

def docker_paths():
    bases = [pathlib.Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Docker' / 'Docker',
             pathlib.Path(os.environ.get('LOCALAPPDATA', '.')) / 'Programs' / 'DockerDesktop']
    return bases

def find_docker():
    p = shutil.which('docker')
    if p: return p
    for b in docker_paths():
        p = b / 'resources' / 'bin' / 'docker.exe'
        if p.exists(): return str(p)
    return None

def ensure_docker(setup):
    global DOCKER
    found = find_docker()
    if not found:
        if not setup: raise RuntimeError('Chua co Docker. Chay SETUP_DATABASES.bat truoc.')
        wsl = shutil.which('wsl.exe')
        status = command([wsl, '--status'], capture=True, check=False, timeout=30) if wsl else None
        if not status or status.returncode:
            log('Can khoi tao WSL 2. Windows se hien hop thoai quyen quan tri.')
            ps = "$p=Start-Process wsl.exe -Verb RunAs -ArgumentList '--install','--no-distribution' -Wait -PassThru; exit $p.ExitCode"
            command(['powershell.exe','-NoProfile','-Command',ps], check=False)
            raise RuntimeError('Hay khoi dong lai Windows, roi bam SETUP_DATABASES.bat. Neu WSL loi, kiem tra virtualization trong BIOS va thong bao Windows.')
        winget = shutil.which('winget.exe')
        if not winget:
            os.startfile('https://docs.docker.com/desktop/setup/install/windows-install/')
            raise RuntimeError('Khong co winget. Da mo trang cai Docker Desktop; cai xong bam SETUP_DATABASES.bat lai.')
        log('Dang cai Docker Desktop. Hoan tat cac buoc trong cua so trinh cai dat.')
        command([winget,'install','--exact','--id','Docker.DockerDesktop','--source','winget',
                 '--interactive','--accept-source-agreements'])
        found = find_docker()
        if not found: raise RuntimeError('Docker chua san sang. Khoi dong lai Windows va chay SETUP_DATABASES.bat.')
    DOCKER = found
    if os.environ.get('DOCKER_HOST'):
        raise RuntimeError('DOCKER_HOST dang duoc dat. Hay dung Docker Desktop cuc bo, khong dung daemon tu xa.')
    ctx = json.loads(docker('context','inspect',capture=True,timeout=30).stdout)[0]
    endpoint = ctx['Endpoints']['docker']['Host']
    if not endpoint.startswith(('npipe://','unix://')):
        raise RuntimeError('Docker context khong phai may cuc bo. Chon Docker Desktop Linux context truoc.')
    def ready():
        p = docker('info','--format','{{.OSType}}',capture=True,check=False,timeout=20)
        return p.returncode == 0 and p.stdout.strip() == 'linux'
    try:
        if ready():
            docker('compose','version',capture=True,timeout=20); return
    except subprocess.TimeoutExpired: pass
    desktop = next((b/'Docker Desktop.exe' for b in docker_paths() if (b/'Docker Desktop.exe').exists()), None)
    if desktop: subprocess.Popen([str(desktop)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log('Dang cho Docker Desktop - Linux engine. Neu Docker hien man hinh chao/WSL, hay hoan tat tren man hinh do.')
    end = time.monotonic()+240
    while time.monotonic()<end:
        try:
            if ready():
                docker('compose','version',capture=True,timeout=20); return
        except subprocess.TimeoutExpired: pass
        log('Docker chua san sang; dang cho...'); time.sleep(5)
    raise RuntimeError('Docker chua san sang sau 4 phut. Mo Docker Desktop, kiem tra Linux containers / WSL 2, roi chay lai. Khong co CSDL cu nao bi dung.')

def inspect(kind, name):
    p = docker(kind,'inspect',name,capture=True,check=False,timeout=20)
    if p.returncode: return None
    return json.loads(p.stdout)[0]

def names(s): return {x:f"{s['project']}-{x}" for x in SERVICES}

def check_owned(s):
    expected = [("container", n) for n in names(s).values()]
    expected += [('volume',f"{s['project']}-{v}") for v in ('neo4j-data','mongo-data','mongo-config','qdrant-data')]
    expected += [('network',s['project']+'-network')]
    for kind,name in expected:
        obj=inspect(kind,name)
        if obj:
            labels=(obj.get('Config',{}).get('Labels') if kind=='container' else obj.get('Labels')) or {}
            if labels.get(OWNER)!=s['id']:
                raise RuntimeError(f'Trung ten tai nguyen khong thuoc bo nay: {name}. Da dung, khong sua/xoa tai nguyen do.')

def occupied_docker_ports():
    ids=docker('ps','-aq',capture=True).stdout.split()
    if not ids:return set()
    ports=set()
    for c in json.loads(docker('container','inspect',*ids,capture=True).stdout):
        for bindings in (c.get('HostConfig',{}).get('PortBindings') or {}).values():
            for b in bindings or []:
                if b.get('HostPort','').isdigit():ports.add(int(b['HostPort']))
    return ports

def available(port):
    with socket.socket() as sock:
        try:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            sock.bind(('127.0.0.1',port)); return True
        except OSError:return False

def new_state():
    uid=uuid.uuid4().hex[:12]
    project='nckh-medai-'+uid
    used=occupied_docker_ports();ports={}
    for key,base in [('neo4j_http',17474),('neo4j_bolt',17687),('mongo',27027),('qdrant',16333)]:
        p=next((p for p in range(base,base+2000) if p not in used and available(p)),None)
        if p is None:raise RuntimeError('Khong tim duoc cong trong.')
        ports[key]=p;used.add(p)
    return dict(schema=1,id=uid,project=project,ports=ports,neo4j_db='medai-'+uid,
                rag_db='medai_'+uid+'_rag',kg_db='medai_'+uid+'_kg',
                neo4j_password=secrets.token_hex(20),mongo_password=secrets.token_hex(20),
                images={})

def compose_doc(s):
    label={OWNER:s['id']}; p=s['ports']; ns=names(s)
    def svc(name,ports,volumes,env=None):
        d=dict(image=s['images'][name],container_name=ns[name],labels=label,restart='unless-stopped',
               ports=[f'127.0.0.1:{h}:{c}' for h,c in ports],volumes=volumes)
        if env:d['environment']=env
        return d
    services={
     'neo4j':svc('neo4j',[(p['neo4j_http'],7474),(p['neo4j_bolt'],7687)],['neo4j-data:/data'],{
         'NEO4J_AUTH':'neo4j/'+s['neo4j_password'],'NEO4J_initial_dbms_default__database':s['neo4j_db'],
         'NEO4J_server_memory_heap_initial__size':'512m','NEO4J_server_memory_heap_max__size':'1G',
         'NEO4J_server_memory_pagecache_size':'512m','NEO4J_server_bolt_advertised__address':f"127.0.0.1:{p['neo4j_bolt']}"}),
     'mongo':svc('mongo',[(p['mongo'],27017)],['mongo-data:/data/db','mongo-config:/data/configdb'],{
         'MONGO_INITDB_ROOT_USERNAME':'medaiadmin','MONGO_INITDB_ROOT_PASSWORD':s['mongo_password']}),
     'qdrant':svc('qdrant',[(p['qdrant'],6333)],['qdrant-data:/qdrant/storage'])}
    volumes={v:{'name':s['project']+'-'+v,'labels':label} for v in ('neo4j-data','mongo-data','mongo-config','qdrant-data')}
    return {'name':s['project'],'services':services,'volumes':volumes,
            'networks':{'default':{'name':s['project']+'-network','labels':label}}}

def compose(s,*args):
    return docker('compose','--project-name',s['project'],'--project-directory',str(DIR),
                  '--env-file',str(DIR/'empty.env'),'-f',str(DIR/'compose.generated.json'),*args)

def http_json(port,path='/'):
    # Bypass proxy settings for loopback connections.
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(f'http://127.0.0.1:{port}{path}',timeout=5) as r:return json.load(r)

def service_ready(s,name):
    n=names(s)[name]
    if name=='neo4j':
        return docker('exec',n,'cypher-shell','-u','neo4j','-p',s['neo4j_password'],
                      '-d',s['neo4j_db'],'RETURN 1;',capture=True,check=False,timeout=20).returncode==0
    if name=='mongo':
        r=docker('exec',n,'mongosh','--quiet','--username','medaiadmin','--password',s['mongo_password'],
                 '--authenticationDatabase','admin','--eval','quit(db.adminCommand({ping:1}).ok === 1 ? 0 : 1)',capture=True,check=False,timeout=20)
        return r.returncode==0
    if name=='qdrant':return http_json(s['ports']['qdrant'],'/collections').get('status')=='ok'
    return False

def wait_services(s):
    pending=set(SERVICES);end=time.monotonic()+300
    while pending and time.monotonic()<end:
        for name in sorted(pending.copy()):
            try:
                if service_ready(s,name):log('[OK] '+name);pending.remove(name)
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
        if pending:log('Dang cho: '+', '.join(sorted(pending)));time.sleep(4)
    if pending:raise RuntimeError('Chua san sang: '+', '.join(sorted(pending))+'. Xem logs cua dung container trong Docker Desktop; chay lai khi da sua loi.')

def check_ports(s):
    mappings={'neo4j':['neo4j_http','neo4j_bolt'],'mongo':['mongo'],'qdrant':['qdrant']}
    for name,keys in mappings.items():
        c=inspect('container',names(s)[name])
        if c and c.get('State',{}).get('Running'):continue
        for key in keys:
            if not available(s['ports'][key]):raise RuntimeError(f"Cong {s['ports'][key]} bi ung dung khac chiem. Khong tu dung ung dung do; doi cong trong medical_db_tools/state.json khi cac container bo nay da dung, roi chay SETUP_DATABASES.bat.")

def mongo_init(s):
    # Single-quoted JS names avoid Windows native argument quote conversion issues.
    js=';'.join("db.getSiblingDB('%s').getCollection('_medical_setup').updateOne({_id:'instance'},{$setOnInsert:{createdAt:new Date()}},{upsert:true})"%db for db in (s['rag_db'],s['kg_db']))
    docker('exec',names(s)['mongo'],'mongosh','--quiet','--username','medaiadmin','--password',s['mongo_password'],
           '--authenticationDatabase','admin','--eval',js,capture=True,timeout=30)

def read_env(path):
    result={}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        m=re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$',line)
        if m:result[m[1]]=m[2].strip().strip('\"\'')
    return result

def env_changes(s):
    p=s['ports'];bolt=f"bolt://127.0.0.1:{p['neo4j_bolt']}";q=f"http://127.0.0.1:{p['qdrant']}"
    mongo=f"mongodb://medaiadmin:{s['mongo_password']}@127.0.0.1:{p['mongo']}/?authSource=admin"
    return {'CONTEXT_GRAPH_BACKEND':'neo4j','CONTEXT_NEO4J_URI':bolt,'CONTEXT_NEO4J_USER':'neo4j',
            'CONTEXT_NEO4J_PASSWORD':s['neo4j_password'],'CONTEXT_NEO4J_DATABASE':s['neo4j_db'],
            'KG_NEO4J_URI':bolt,'KG_NEO4J_USERNAME':'neo4j','KG_NEO4J_PASSWORD':s['neo4j_password'],
            'KG_NEO4J_DATABASE':s['neo4j_db'],'RAG_MODE':'live','RAG_MONGO_URI':mongo,'RAG_MONGO_DB':s['rag_db'],
            'KG_MONGODB_URI':mongo,'KG_MONGODB_DATABASE':s['kg_db'],'RAG_QDRANT_URL':q,'RAG_QDRANT_API_KEY':'',
            'KG_QDRANT_URL':q}

def merge_env(text, changes):
    lines=[];seen=set()
    for line in text.splitlines(keepends=True):
        m=re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=',line)
        if m and m[1] in changes:
            if m[1] not in seen:lines.append(m[1]+'='+changes[m[1]]+'\r\n');seen.add(m[1])
        else:lines.append(line)
    if lines and not lines[-1].endswith(('\n','\r')):lines[-1]+='\r\n'
    for k,v in changes.items():
        if k not in seen:lines.append(k+'='+v+'\r\n')
    return ''.join(lines)

def patch_env(s):
    path=ROOT/'backend'/'.env';original=path.read_bytes()
    text=original.decode('utf-8-sig'); updated=merge_env(text,env_changes(s)).encode('utf-8')
    if original.startswith(b'\xef\xbb\xbf'):updated=b'\xef\xbb\xbf'+updated
    if updated==original:log('.env da tro dung bo moi.');return
    backup=path.with_name('.env.before-isolated-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    backup.write_bytes(original)
    temp=path.with_name('.env.isolated.tmp');temp.write_bytes(updated)
    if path.read_bytes()!=original:temp.unlink();raise RuntimeError('.env da thay doi trong luc cap nhat. Hay chay SETUP lai.')
    os.replace(temp,path);log('Da sao luu .env: '+backup.name+'; da cap nhat ket noi bo moi.')

def run(mode):
    if os.name!='nt':raise RuntimeError('Bo chay nay danh cho Windows 10/11.')
    if not (ROOT/'backend'/'.env').is_file():raise RuntimeError('Dat 2 BAT va medical_db_tools canh backend/frontend; can backend/.env cua du an.')
    setup=mode=='setup'
    if not setup and not STATE.exists():raise RuntimeError('Chay SETUP_DATABASES.bat lan dau.')
    ensure_docker(setup)
    settings=json.loads((DIR/'settings.json').read_text(encoding='utf-8-sig'))
    if STATE.exists():
        s=json.loads(STATE.read_text(encoding='utf-8'))
        if s.get('schema')!=1 or not re.fullmatch(r'[0-9a-f]{12}',s.get('id','')):raise RuntimeError('state.json khong hop le; khong duoc xoa tep nay de sua loi.')
        if s['project']!='nckh-medai-'+s['id']:raise RuntimeError('Ten project khong khop ma so luu trong state.json.')
    else:
        s=new_state()
        check_owned(s);atomic_json(STATE,s)
    check_owned(s);check_ports(s)
    if setup:
        for name in SERVICES:
            if name in s['images']:continue
            tag=settings['images'][name];log('Tai image '+tag+' ...')
            docker('pull',tag)
            obj=json.loads(docker('image','inspect',tag,capture=True).stdout)[0]
            # Keep a repository digest so later runs can restore the same image.
            s['images'][name]=(obj.get('RepoDigests') or [obj['Id']])[0];atomic_json(STATE,s)
    if not set(SERVICES).issubset(s['images']):raise RuntimeError('Cai dat chua xong. Chay SETUP_DATABASES.bat lai.')
    atomic_json(DIR/'compose.generated.json',compose_doc(s));(DIR/'empty.env').touch()
    log('Khoi dong bo rieng: '+s['project'])
    # Explicit service list; never start or remove a legacy Ollama container.
    compose(s,'up','-d','--pull','missing',*SERVICES)
    wait_services(s)
    if setup:
        mongo_init(s)
        # Switch database connections only after all three databases respond.
        patch_env(s)
        s['setup_complete']=True;atomic_json(STATE,s)
    elif not s.get('setup_complete'):
        raise RuntimeError('Dich vu da mo nhung SETUP chua hoan tat. Chay SETUP_DATABASES.bat.')
    else:
        current=read_env(ROOT/'backend'/'.env')
        if any(current.get(k)!=v for k,v in env_changes(s).items()):
            raise RuntimeError('CSDL da mo, nhung backend/.env chua tro dung bo nay. Chay SETUP_DATABASES.bat de sao luu va cap nhat.')
    summary='\n'.join([f"Project: {s['project']}",f"Neo4j: http://127.0.0.1:{s['ports']['neo4j_http']} | database: {s['neo4j_db']}",
      f"MongoDB: 127.0.0.1:{s['ports']['mongo']} | {s['rag_db']} / {s['kg_db']}",
      f"Qdrant: http://127.0.0.1:{s['ports']['qdrant']}/dashboard",'Ollama: dung ban co san tren Windows; bo nay khong cai, khoi dong hay tai model.',
      'Mat khau: xem backend/.env hoac medical_db_tools/state.json tren may cua ban.',
      'CSDL moi khong co du lieu y khoa; can nap/khôi phuc du lieu rieng.',
      'Da san sang dich vu. Khoi dong lai backend neu no dang chay, sau do dung RUN.bat cua du an.'])
    # Old setup versions may already have redirected Ollama to their Docker port.
    # Keep the user's values unchanged and flag that case without blocking databases.
    old_port=s['ports'].get('ollama')
    current=read_env(ROOT/'backend'/'.env')
    if old_port and any(current.get(k,'').rstrip('/') in
                        (f'http://127.0.0.1:{old_port}',f'http://localhost:{old_port}')
                        for k in ('OLLAMA_BASE_URL','CONTEXT_OLLAMA_BASE_URL')):
        summary+='\n[LUU Y] .env van tro Ollama toi cong Docker cua bo cu. Can doi URL sang Ollama Windows truoc khi dung AI; bo cai khong tu sua cac dong nay.'
    (DIR/'CONNECTIONS.txt').write_text(summary,encoding='utf-8-sig');log(summary)

@contextlib.contextmanager
def instance_lock():
    # OS lock is released even when window/process crashes; lock file contains no secrets.
    import msvcrt
    with (DIR/'operation.lock').open('a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('SETUP/START khac dang chay. Cho cua so do ket thuc.')
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def main():
    global LOG
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode not in ('setup','start'):return 1
    logdir=ROOT/'logs';logdir.mkdir(exist_ok=True)
    logpath=logdir/('databases-'+mode+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    with logpath.open('w',encoding='utf-8') as logfile:
        LOG=logfile
        try:
            log('Nhat ky: '+str(logpath))
            with instance_lock():run(mode)
            log('[OK] Hoan tat.');return 0
        except KeyboardInterrupt:log('Da huy. Du lieu da tao duoc giu nguyen; co the chay lai.');return 1
        except Exception as e:log('[LOI] '+str(e));return 1
if __name__=='__main__':sys.exit(main())
