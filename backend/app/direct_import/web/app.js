'use strict';
const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);const initial=params.get('target')||params.get('module');
if(['kg','rag','both'].includes(initial))$('target').value=initial;
if(params.get('embed')==='1'){document.documentElement.dataset.workspaceEmbedded='true';parent.postMessage({type:'medical-data:ready'},location.origin);}
const labels={queued:'Đang chờ',running:'Đang xử lý',completed:'Hoàn tất',partial:'Hoàn tất một phần',failed:'Có lỗi',interrupted:'Đã gián đoạn'};
const stages={validation:'Kiểm tra dữ liệu và ontology…',identity:'Hợp nhất tên/alias cùng loại…',databases:'Lưu KG và bằng chứng vào CSDL…',kg_completed:'KG đã hoàn tất.',rag_embedding:'Tạo embedding và lưu RAG…',queued:'Đang chờ xử lý…'};
let timer=null,working=false;
async function request(path,options){const r=await fetch(path,options);const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail||v));return v;}
function message(text,state=''){const n=$('status');n.textContent=text;n.dataset.state=state;}
function busy(value){working=value;$('submit').disabled=value;$('file').disabled=value;$('target').disabled=value;$('selection').disabled=value;}
function render(job){
  const result=job.results||{};let text=['queued','running'].includes(job.status)?(stages[job.stage]||labels[job.status]):(labels[job.status]||job.status);
  if(job.error)text+='\n'+job.error;
  if(job.message)text+='\n'+job.message;
  if(result.kg)text+='\nKG: '+(labels[result.kg.status]||result.kg.status);
  if(result.rag)text+='\nRAG: '+(labels[result.rag.status]||({skipped:'Dữ liệu đã có'}[result.rag.status])||result.rag.status)+(result.rag.error?' — '+result.rag.error:'');
  message(text,job.status);$('details').hidden=false;$('result').textContent=JSON.stringify(job,null,2);$('counts').replaceChildren();
  const sid=result.kg?.snapshot_id;$('download').hidden=!sid;if(sid)$('download').href='/api/v1/direct-import/snapshots/'+encodeURIComponent(sid);
  for(const [k,v] of Object.entries(result.kg?.counts||{})){const n=document.createElement('span');n.textContent=({entities:'Thực thể',relations:'Quan hệ',assertions:'Phát biểu nguồn',evidence:'Bằng chứng'}[k]||k)+': '+v;$('counts').append(n);}
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
