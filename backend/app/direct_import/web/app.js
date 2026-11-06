'use strict';
const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);const initial=params.get('target')||params.get('module');
if(['kg','rag','both'].includes(initial))$('target').value=initial;
if(params.get('embed')==='1'){document.documentElement.dataset.workspaceEmbedded='true';parent.postMessage({type:'medical-data:ready'},location.origin);}
const labels={queued:'Đang chờ',running:'Đang xử lý',completed:'Hoàn tất',partial:'Hoàn tất một phần',failed:'Có lỗi',interrupted:'Đã gián đoạn'};
const stages={validation:'Kiểm tra dữ liệu và ontology…',identity:'Kiểm tra định danh và lập chỉ mục tên/alias…',databases:'Lưu KG và bằng chứng vào CSDL…',kg_completed:'KG đã hoàn tất.',rag_embedding:'Tạo embedding và lưu RAG…',queued:'Đang chờ xử lý…'};
let timer=null,working=false;
async function request(path,options){const r=await fetch(path,options);const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail||v));return v;}
function message(text,state=''){const n=$('status');n.textContent=text;n.dataset.state=state;}
function busy(value){working=value;$('submit').disabled=value;$('file').disabled=value;$('target').disabled=value;$('selection').disabled=value;}
function render(job){
  const result=job.results||{};let text=['queued','running'].includes(job.status)?(stages[job.stage]||labels[job.status]):(labels[job.status]||job.status);
  if(job.error)text+='\n'+job.error;
  if(job.message)text+='\n'+job.message;
  if(result.kg)text+='\nKG: '+(labels[result.kg.status]||result.kg.status);
  if(result.kg?.ambiguous_terms)text+='\nCó '+result.kg.ambiguous_terms+' tên/alias trùng; các thực thể được giữ riêng.';
  for(const warning of result.kg?.warnings||[])text+='\n'+warning;
  if(result.rag)text+='\nRAG: '+(labels[result.rag.status]||({skipped:'Dữ liệu đã có'}[result.rag.status])||result.rag.status)+(result.rag.error?' — '+result.rag.error:'');
  message(text,job.status);$('details').hidden=false;$('result').textContent=JSON.stringify(job,null,2);$('counts').replaceChildren();
  const sid=result.kg?.snapshot_id;$('download').hidden=!sid;if(sid)$('download').href='/api/v1/direct-import/snapshots/'+encodeURIComponent(sid);
  for(const [k,v] of Object.entries({...result.kg?.counts,...result.kg?.graph_counts})){const n=document.createElement('span');n.textContent=({entities:'Thực thể nguồn',source_entities:'Thực thể nguồn',graph_entities:'Thực thể trên graph',isolated_source_entities:'Thực thể chỉ lưu ở nguồn',relations:'Quan hệ',assertions:'Phát biểu nguồn',evidence:'Bằng chứng'}[k]||k)+': '+v;$('counts').append(n);}
}
async function poll(id){
  clearTimeout(timer);
  try{const job=await request('/api/v1/direct-import/jobs/'+encodeURIComponent(id));render(job);
    if(['queued','running'].includes(job.status)){busy(true);timer=setTimeout(()=>poll(id),1800);}
    else{busy(false);localStorage.removeItem('medical-direct-import-job');await history();}
  }catch(e){message('Chưa đọc được tiến trình: '+e.message+'. Nhấn Làm mới để kiểm tra lại.','failed');busy(false);}
}
async function history(){
  try{const jobs=await request('/api/v1/direct-import/jobs');$('history').replaceChildren();
    for(const job of jobs){const tr=document.createElement('tr');for(const val of [job.filename,job.target,labels[job.status]||job.status]){const td=document.createElement('td');td.textContent=val||'';tr.append(td);}const td=document.createElement('td'),b=document.createElement('button');b.textContent='Xem';b.onclick=()=>poll(job.id);td.append(b);tr.append(td);$('history').append(tr);}
  }catch(e){message(e.message,'failed');}
}
$('submit').onclick=async()=>{
  const f=$('file').files[0];if(!f){message('Hãy chọn file JSON hoặc ZIP.');return;}
  const max=f.name.toLowerCase().endsWith('.zip')?64:20;if(f.size>max*1024*1024){message('File vượt giới hạn '+max+' MiB.','failed');return;}
  busy(true);message('Đang đọc và kiểm tra gói dữ liệu…');
  try{const q=new URLSearchParams({filename:f.name,target:$('target').value,selection:$('selection').value});const job=await request('/api/v1/direct-import?'+q,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});localStorage.setItem('medical-direct-import-job',job.id);await poll(job.id);}
  catch(e){message(e.message,'failed');busy(false);}
};
$('refresh').onclick=()=>{const id=localStorage.getItem('medical-direct-import-job');if(id)poll(id);else history();};
history();const last=localStorage.getItem('medical-direct-import-job');if(last)poll(last);

let identityData=null;
function identityCandidates(){
  const group=identityData?.ambiguous_terms[Number($('identity-term').value)];
  $('identity-candidates').replaceChildren();$('identity-target').replaceChildren();
  if(!group)return;
  for(const id of group.entity_ids){
    const entity=identityData.entities[id],row=document.createElement('div'),label=document.createElement('label'),check=document.createElement('input');
    check.type='checkbox';check.value=id;check.style.width='auto';check.className='identity-choice';
    label.append(check,document.createTextNode(' '+entity.canonical_name+' ['+id+']'));row.append(label);
    if(entity.canonical_name.toLocaleLowerCase()!==group.term){
      const reject=document.createElement('button');reject.className='secondary';reject.textContent='Loại alias này khỏi thực thể';
      reject.onclick=()=>identitySave({action:'alias',entity_id:id,term:group.term,status:'rejected',reason:'Người dùng loại alias khỏi thực thể trong màn hình kiểm tra.'});row.append(reject);
    }
    $('identity-candidates').append(row);
    const option=document.createElement('option');option.value=id;option.textContent=entity.canonical_name;$('identity-target').append(option);
  }
  $('identity-name').value=identityData.entities[group.entity_ids[0]].canonical_name;
}
async function identityLoad(){
  try{
    identityData=await request('/api/v1/direct-import/identity');$('identity-term').replaceChildren();
    identityData.ambiguous_terms.forEach((g,i)=>{const option=document.createElement('option');option.value=i;option.textContent=g.term+' ('+g.type+', '+g.entity_ids.length+' thực thể)';$('identity-term').append(option);});
    $('identity-panel').hidden=!identityData.ambiguous_terms.length;
    $('identity-status').textContent=identityData.ambiguous_terms.length+' nhóm tên/alias trùng. '+identityData.warnings.join(' ');identityCandidates();
  }catch(e){$('identity-status').textContent=e.message;}
}
async function identitySave(body){
  if(!identityData||working)return;
  const buttons=[$('identity-merge'),$('identity-distinct'),$('identity-refresh')];buttons.forEach(b=>b.disabled=true);
  try{await request('/api/v1/direct-import/identity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:identityData.revision,...body})});await identityLoad();}
  catch(e){$('identity-status').textContent=e.message;}
  finally{buttons.forEach(b=>b.disabled=false);}
}
function identityChoose(action){
  const group=identityData?.ambiguous_terms[Number($('identity-term').value)];if(!group)return;
  const ids=Array.from(document.querySelectorAll('.identity-choice:checked'),e=>e.value);
  if(ids.length<2){$('identity-status').textContent='Chọn ít nhất hai thực thể.';return;}
  identitySave({action,ids,target_id:$('identity-target').value,name:$('identity-name').value,type:group.type});
}
$('identity-refresh').onclick=identityLoad;$('identity-term').onchange=identityCandidates;
$('identity-target').onchange=()=>{$('identity-name').value=identityData.entities[$('identity-target').value].canonical_name;};
$('identity-merge').onclick=()=>identityChoose('merge');$('identity-distinct').onclick=()=>identityChoose('distinct');

let v71bPreview=null;
const v71bLabels={
  staged:'Chờ đủ hai phần',preview_pending:'Đã lưu hai phần. Tải lại một phần để thử dựng bản xem trước.',sealed:'Đã có bản xem trước',syncing:'Đang đồng bộ',
  ready:'Đã xác minh, chờ kích hoạt',active:'Đang phục vụ truy vấn',failed:'Đồng bộ lỗi, có thể thử lại'
};
function renderV71b(data){
  v71bPreview=data;
  $('v71b-publish').hidden=!['sealed','failed','syncing'].includes(data?.state);
  $('v71b-activate').hidden=data?.state!=='ready';
  if(!data)return;
  const lines=[v71bLabels[data.state]||data.state,'Mã bộ KG: '+data.dataset_id];
  for(const part of data.parts)lines.push('Phần '+part.part_number+' · '+part.document_id+' · SHA-256 '+part.archive_sha256);
  if(data.counts){
    const counts=data.counts;
    lines.push('Thực thể trong registry: '+counts.source_entities,'Node có cạnh: '+counts.graph_entities,
      'Cạnh logic: '+counts.relations,'Khẳng định quan hệ: '+counts.assertions,
      'Mệnh đề: '+counts.propositions,'Câu nguồn: '+counts.sentences,
      'Thực thể dùng chung: '+counts.shared_entities,'Quan hệ dùng chung: '+counts.shared_relations,
      'Snapshot: '+data.snapshot_id);
  }
  $('v71b-result').textContent=lines.join('\n');
}
async function v71bOperation(action){
  const dataset=$('v71b-dataset').value;
  const output=$('v71b-result');
  if(!/^[A-Za-z0-9_-]{1,80}$/.test(dataset)){output.textContent='Nhập mã bộ KG hợp lệ.';return;}
  const path='/api/v1/direct-import/v71b/'+encodeURIComponent(dataset);
  const controls=['dataset','part','file','stage','status','publish','activate'].map(id=>$('v71b-'+id));
  controls.forEach(node=>node.disabled=true);
  try{
    let data;
    if(action==='stage'){
      const file=$('v71b-file').files[0];
      if(!file||!file.name.toLowerCase().endsWith('.zip')||file.size>64*1024*1024)throw Error('Chọn tệp ZIP V71B tối đa 64 MiB.');
      output.textContent='Đang kiểm tra và lưu phần…';
      const query=new URLSearchParams({total_parts:'2',filename:file.name});
      data=await request(path+'/parts/'+$('v71b-part').value+'?'+query,
        {method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file});
    }else if(action==='status'){
      data=await request(path);
    }else{
      if(v71bPreview?.dataset_id!==dataset||!v71bPreview.snapshot_id)throw Error('Tải lại bản xem trước.');
      output.textContent=action==='publish'?'Đang đồng bộ và xác minh…':'Đang kích hoạt snapshot…';
      data=await request(path+'/'+action,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({confirmed:true,snapshot_id:v71bPreview.snapshot_id})});
    }
    renderV71b(data);
  }catch(error){output.textContent=error.message+' Tải trạng thái để kiểm tra trước khi thử lại.';}
  finally{controls.forEach(node=>node.disabled=false);}
}
$('v71b-dataset').oninput=()=>{renderV71b(null);$('v71b-result').textContent='Tải trạng thái hoặc chọn phần cần nhập.';};
for(const action of ['stage','status','publish','activate'])$('v71b-'+action).onclick=()=>v71bOperation(action);

let identityBatch=null;
const batchPath='/api/v1/direct-import/identity/batch';
$('identity-batch-preview').onclick=async()=>{
  const scan=$('identity-batch-preview'), confirm=$('identity-batch-confirm'), status=$('identity-batch-status');
  scan.disabled=true;
  confirm.hidden=true;
  identityBatch=null;
  $('identity-batch-details').hidden=true;
  status.textContent='Đang quét các nhóm cùng tên chuẩn và cùng loại…';
  try{
    identityBatch=await request(batchPath);
    const {eligible,blocked}=identityBatch;
    status.textContent=eligible.length+' nhóm đủ điều kiện, '+blocked.length+' nhóm bị chặn. Quyết định áp dụng vào bản nháp.';
    $('identity-batch-result').textContent=[
      ...eligible.map(row=>'Đủ điều kiện · '+row.name+' ('+row.type+') · Giữ '+row.target_id+' · ID: '+row.ids.join(', ')),
      ...blocked.map(row=>'Bị chặn · '+row.name+' ('+row.type+') · '+row.reason+' · ID: '+row.ids.join(', '))
    ].join('\n');
    $('identity-batch-details').hidden=!(eligible.length||blocked.length);
    confirm.hidden=!eligible.length;
  }catch(error){status.textContent=error.message;}
  finally{scan.disabled=false;}
};
$('identity-batch-confirm').onclick=async()=>{
  if(!identityBatch?.eligible.length||working)return;
  const scan=$('identity-batch-preview'), confirm=$('identity-batch-confirm'), status=$('identity-batch-status');
  scan.disabled=true;
  confirm.disabled=true;
  try{
    const {revision,token}=identityBatch;
    const result=await request(batchPath,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({confirmed:true,revision,token})});
    status.textContent='Đã gộp '+result.merged_groups+' nhóm vào bản nháp. '+result.blocked_groups+' nhóm bị chặn.';
    await identityLoad();
  }catch(error){status.textContent=error.message+' Quét lại để tiếp tục.';}
  finally{scan.disabled=false;confirm.disabled=false;confirm.hidden=true;identityBatch=null;$('identity-batch-details').hidden=true;}
};
