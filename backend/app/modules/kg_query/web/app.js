(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const SVG = 'http://www.w3.org/2000/svg';
  const state = {mode:'related', result:null, facts:[], selected:-1, positions:new Map(), anchorIds:new Set()};
  const el = (name, cls, value) => { const x=document.createElement(name); if(cls)x.className=cls; if(value!==undefined)x.textContent=String(value); return x; };
  const svg = (name, attrs={}) => { const x=document.createElementNS(SVG,name); Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,String(v))); return x; };
  const show = (id, yes) => $(id).classList.toggle('hidden',!yes);
  const uniqueFacts = (result) => {
    const list=[...(result.facts||[]),...(result.paths||[]).flatMap(p=>p.facts||[])];
    const seen=new Map();
    for(const f of list){
      const key=`${f.subject.id}\u0000${f.predicate}\u0000${f.object.id}`;
      if(!seen.has(key))seen.set(key,{...f,doc_ids:[...(f.doc_ids||[])],evidence:[...(f.evidence||[])]});
      else {const old=seen.get(key); old.doc_ids=[...new Set([...old.doc_ids,...(f.doc_ids||[])])];
        const keys=new Set(old.evidence.map(e=>`${e.doc_id}/${e.evidence_id}`));
        for(const e of f.evidence||[]){const k=`${e.doc_id}/${e.evidence_id}`; if(!keys.has(k)){old.evidence.push(e);keys.add(k);}}}
    }
    return [...seen.values()];
  };
  const twoModes=['path','compare','common','difference'];
  let metadata=null,lastPayload=null;
  const extras=el('section','query-extras');extras.id='queryExplanations';$('results').before(extras);
  const confirmations=el('div','query-extras');$('feedback').after(confirmations);
  function option(select,value,label){const o=el('option',null,label);o.value=value;select.append(o);return o;}
  function addStep(){
    if(!metadata || $('stepRows').children.length>=4)return;
    const row=el('div','step-row'),rel=el('select'),dir=el('select'),type=el('select'),remove=el('button',null,'Xóa bước');
    rel.className='step-relation';dir.className='step-direction';type.className='step-type';
    rel.setAttribute('aria-label','Quan hệ của bước');dir.setAttribute('aria-label','Chiều truy vấn');type.setAttribute('aria-label','Loại đích');
    for(const r of metadata.relations)option(rel,r,r);
    option(dir,'out','Đi theo chiều quan hệ');option(dir,'in','Đi ngược chiều quan hệ');option(dir,'any','Cả hai chiều');
    option(type,'','Tất cả loại');for(const t of metadata.entity_types)option(type,t,t);
    remove.type='button';remove.onclick=()=>row.remove();row.append(rel,dir,type,remove);$('stepRows').append(row);
  }
  $('addStep').onclick=addStep;
  function setMode(mode){
    state.mode=mode;
    document.querySelectorAll('.mode').forEach(b=>{b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',b.dataset.mode===mode?'true':'false');});
    show('secondField',twoModes.includes(mode));show('intentField',mode==='related'||['compare','common','difference'].includes(mode));show('chainField',mode==='chain');
    show('ruleField',mode==='inference');show('scopeField',mode==='inference');show('depthField',['path','inference'].includes(mode));show('customFields',mode==='custom');show('targetTypeField',mode==='related');
    $('target').required=twoModes.includes(mode);
    $('modeHelp').textContent=mode==='inference'?'Chỉ suy ra phân loại/bộ phận bằng tiền đề có văn bản nguồn, không phủ định và không có thuộc tính điều kiện. Kết luận suy ra không được ghi vào CSDL.':
      mode==='chain'||mode==='custom'?'Chuỗi thể hiện các quan hệ được ghi nhận. Điều kiện, đối tượng và nguồn của từng bước cần được đọc cùng nhau; không tự suy ra chỉ định cá nhân.':
      ['compare','common','difference'].includes(mode)?'Chọn nhóm quan hệ cụ thể. Không tìm thấy ở một phía không có nghĩa là đặc điểm đó không tồn tại.':
      mode==='path'?'Đường liên kết không tự chứng minh quan hệ nhân quả.':'Tra quan hệ trực tiếp theo tên chuẩn hoặc alias.';
    confirmations.replaceChildren();
  }
  document.querySelectorAll('.mode').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
  document.querySelectorAll('[data-example]').forEach(b=>b.addEventListener('click',()=>{
    $('mention').value=b.dataset.example;
    if(b.dataset.target){setMode('path');$('target').value=b.dataset.target;}
    else {setMode('related');$('intent').value=b.dataset.intent;}
    $('queryForm').requestSubmit();
  }));
  fetch('/modules/kg-explorer/api/meta').then(async r=>{if(!r.ok)throw Error('Không tải được cấu hình truy vấn.');return r.json();}).then(meta=>{
    metadata=meta;
    const select=$('intent');for(const i of meta.intents||[]){if(i.id!=='related')option(select,i.id,i.description);}
    $('chain').replaceChildren();
    for (const preset of meta.preset_details || []) {
      const disabled = preset.available === false;
      const entry = option($('chain'), preset.id, disabled ? preset.label + ' (chưa khả dụng)' : preset.label);
      entry.disabled = disabled;
      if (disabled) entry.title = preset.unavailable_reason || '';
    }
    for(const r of meta.inference_rules||[])if(r.available)option($('inferenceRule'),r.id,r.label);
    for(const t of meta.entity_types||[])option($('targetType'),t,t);
    addStep();addStep();
  }).catch(e=>{$('feedback').textContent=e.message;});
  fetch('/modules/kg-explorer/api/health').then(r=>{ $('connection').textContent=r.ok?'Neo4j đã kết nối':'Chưa kết nối Neo4j';$('connection').parentElement.classList.toggle('offline',!r.ok); }).catch(()=>{ $('connection').textContent='Chưa kết nối Neo4j';$('connection').parentElement.classList.add('offline'); });
  $('queryForm').addEventListener('submit',async(ev)=>{
    ev.preventDefault();
    const mention=$('mention').value.trim(),target=$('target').value.trim();
    if(!mention||(twoModes.includes(state.mode)&&!target))return;
    const payload={question:mention+(target?' / '+target:''),mentions:twoModes.includes(state.mode)?[mention,target]:[mention],limit:100,mode:'one_hop'};
    if(state.mode==='path'){payload.mode='path';payload.max_hops=Number($('depth').value);}
    else if(state.mode==='chain'){payload.mode='multi_hop';payload.preset=$('chain').value;}
    else if(state.mode==='custom'){
      payload.mode='multi_hop';payload.steps=[...$('stepRows').children].map(row=>({rel_types:[row.querySelector('.step-relation').value],direction:row.querySelector('.step-direction').value,...(row.querySelector('.step-type').value?{target_types:[row.querySelector('.step-type').value]}:{})}));
      if(!payload.steps.length){$('feedback').textContent='Thêm ít nhất một bước.';return;}
    }else if(state.mode==='inference'){
      payload.mode='inference';payload.inference_rule=$('inferenceRule').value;payload.evidence_scope=$('evidenceScope').value;payload.max_hops=Number($('depth').value);
    }else{
      payload.mode=state.mode==='related'?'one_hop':state.mode;payload.intents=[$('intent').value];
      if(state.mode==='related'&&$('targetType').value)payload.target_types=[$('targetType').value];
    }
    lastPayload=payload;await submitPlan(payload,mention,target);
  });
  async function submitPlan(payload,mention,target){
    $('searchBtn').disabled=true;$('searchBtn').querySelector('span').textContent='Đang truy vấn…';
    $('feedback').textContent='';$('feedback').classList.remove('error');confirmations.replaceChildren();
    try{
      const response=await fetch('/modules/kg-explorer/api/query-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const envelope=await response.json();if(!response.ok)throw Error(envelope.error||envelope.detail?.message||JSON.stringify(envelope.detail)||'Truy vấn thất bại.');
      const ctx=envelope.llm_context||{},facts=ctx.facts||[];
      const data={...ctx,status:envelope.status,anchors:envelope.retrieval?.anchors||{},notes:envelope.warnings||[],
        chains:(ctx.chains||[]).map(c=>c.fact_indices.map(i=>facts[i])),paths:(ctx.paths||[]).map(p=>({nodes:p.nodes,facts:p.fact_indices.map(i=>facts[i])})),query:envelope.query};
      state.result=data;state.facts=uniqueFacts(data);state.selected=-1;render(data,mention,target);
      if(envelope.clarification){
        $('feedback').textContent=envelope.clarification.message;
        if(envelope.clarification.can_confirm){
          const selects=[];
          for(const group of envelope.clarification.groups){const label=el('label',null,group.mention+' '),select=el('select');option(select,'','Chọn đúng thực thể');for(const c of group.candidates)option(select,c.id,c.name+' · '+c.type);label.append(select);confirmations.append(label);selects.push(select);}
          const choose=el('button',null,'Truy vấn với các thực thể đã chọn');choose.type='button';choose.onclick=()=>{if(selects.some(s=>!s.value))return;const confirmed={...lastPayload,entity_ids:selects.map(s=>s.value)};delete confirmed.mentions;submitPlan(confirmed,mention,target);};confirmations.append(choose);
        }
      }
    }catch(error){$('feedback').textContent=error.message;$('feedback').classList.add('error');}
    finally{$('searchBtn').disabled=false;$('searchBtn').querySelector('span').textContent='Khám phá tri thức';}
  }
  function renderExtras(result){
    extras.replaceChildren();
    const triple=f=>f.subject.name+' — '+f.predicate+' → '+f.object.name;
    if(result.inferences?.length){
      extras.append(el('h3',null,'Kết luận suy ra · '+result.inferences.length));
      for(const proof of result.inferences){const card=el('article','proof-card');card.append(el('h4',null,triple(proof)),el('p',null,'Quy tắc: '+proof.rule+' · '+proof.hops+' bước · nguồn: '+proof.source_document_ids.join(', ')));const list=el('ol');
        for(const p of proof.premises){const item=el('li',null,triple(p));for(const [src,entries] of Object.entries(p.support_by_source))for(const e of entries)item.append(el('p','muted',src+' · '+e.evidence.evidence_id+': '+e.evidence.text));list.append(item);}card.append(list);extras.append(card);}
    }else if(state.mode==='inference')extras.append(el('p','proof-card','Không có kết luận đáp ứng đầy đủ quy tắc và bằng chứng trong phạm vi truy vấn.'));
    if(result.chains?.length&&!result.inferences?.length){extras.append(el('h3',null,'Chuỗi quan hệ hoàn chỉnh · '+result.chains.length));for(const chain of result.chains){const card=el('div','proof-card'),list=el('ol');for(const f of chain)list.append(el('li',null,triple(f)));card.append(list);extras.append(card);}}
    if(result.comparison){const card=el('div','proof-card');card.append(el('h3',null,'Đối chiếu: '+(result.comparison.entities||[]).map(e=>e.name).join(' / ')));for(const r of result.comparison.rows||[])card.append(el('p',null,(r.feature?.name||'')+' · '+r.predicate+' · '+r.label));extras.append(card);}
  }
  function render(result,mention,target){
    const facts=state.facts;renderExtras(result);
    if(result.status==='no_entity'){$('feedback').textContent='Không tìm thấy thực thể. Hãy thử tên đầy đủ hoặc một tên đồng nghĩa.';}
    else if(result.status==='no_facts'){$('feedback').textContent='Đã tìm thấy thực thể nhưng chưa có quan hệ phù hợp trong đồ thị.';}
    if(result.notes?.length){$('feedback').textContent+=($('feedback').textContent?' · ':'')+result.notes.join(' · ');}
    show('results',true);
    $('resultCount').textContent=facts.length;
    $('resultSubtitle').textContent=state.mode==='path'?`Đường đi từ “${mention}” đến “${target}”`:`Quan hệ liên quan đến “${mention}”`;
    const nodes=new Map();facts.forEach(f=>{nodes.set(f.subject.id,f.subject);nodes.set(f.object.id,f.object);});
    state.anchorIds=new Set(Object.values(result.anchors||{}).flat().map(a=>a.id));
    for(const anchors of Object.values(result.anchors||{}))for(const a of anchors)nodes.set(a.id,a);
    $('nodeCount').textContent=nodes.size;
    $('edgeCount').textContent=facts.length;
    $('docCount').textContent=new Set(facts.flatMap(f=>f.doc_ids||[])).size;
    $('factsMeta').textContent=`${facts.length} quan hệ · chọn để xem bằng chứng`;
    renderFacts();renderGraph([...nodes.values()],facts);
    $('detail').replaceChildren();const placeholder=el('div','detail-placeholder');placeholder.append(el('span',null,'✳'),el('strong',null,'Chọn một quan hệ'),el('p',null,'Nhấp vào đường nối hoặc một kết quả bên dưới để xem nguồn bằng chứng.'));$('detail').append(placeholder);
    if(facts.length)selectFact(0);
  }
  function renderFacts(){
    const list=$('factsList');list.replaceChildren();
    if(!state.facts.length){list.append(el('div','muted','Chưa có quan hệ phù hợp.'));list.lastChild.style.padding='20px';return;}
    state.facts.forEach((f,i)=>{
      const row=el('button','fact-row');row.type='button';row.dataset.index=i;
      row.append(el('span','fact-index',String(i+1).padStart(2,'0')));
      const body=el('div');const headline=el('div','fact-text');headline.append(el('span',null,f.subject.name),el('span','rel',`⟶ ${f.predicate} ⟶`),el('span',null,f.object.name));
      body.append(headline,el('div','fact-sub',`${f.subject.type} · ${f.object.type}  |  ${(f.doc_ids||[]).length} tài liệu`));
      row.append(body,el('span','fact-chevron','›'));row.addEventListener('click',()=>selectFact(i));list.append(row);
    });
  }
  function selectFact(index){
    state.selected=index;
    document.querySelectorAll('.fact-row').forEach(r=>r.classList.toggle('selected',Number(r.dataset.index)===index));
    document.querySelectorAll('[data-edge-index]').forEach(r=>r.classList.toggle('selected-edge',Number(r.dataset.edgeIndex)===index));
    const f=state.facts[index];if(!f)return;
    const detail=$('detail');detail.replaceChildren();
    detail.append(el('div','detail-kicker',`QUAN HỆ ${String(index+1).padStart(2,'0')}`),el('h4','detail-title',`${f.subject.name} → ${f.object.name}`));
    const triple=el('div','triple');triple.append(el('span','entity',f.subject.name),el('span','predicate',f.predicate),el('span','entity',f.object.name));detail.append(triple);
    detail.append(document.createElement('hr'));detail.lastChild.className='divider';
    detail.append(el('div','section-title',`BẰNG CHỨNG · ${(f.evidence||[]).length}`));
    const evidence=f.evidence||[];
    if(evidence.length){for(const e of evidence){const item=el('div','evidence-item');item.append(el('div','source',`${e.source_origin?.source_document_id||e.doc_id} · ${e.document_title||''} · ${e.evidence_id}`),el('p',null,e.text||'Chưa có nội dung bằng chứng.'));detail.append(item);}}
    else detail.append(el('p','muted','Chưa lấy được văn bản bằng chứng. Kiểm tra MongoDB hoặc mã bằng chứng của quan hệ.'));
    if(f.assertions?.length){detail.append(el('div','section-title','NGỮ CẢNH PHÁT BIỂU'));for(const a of f.assertions){const line=el('p','muted');line.textContent=(a.document_id||'')+' · '+JSON.stringify(a.properties||{});detail.append(line);}}
    if(f.doc_ids?.length){detail.append(el('div','section-title','TÀI LIỆU NGUỒN'));for(const d of f.doc_ids)detail.append(el('div','muted',d));}
    detail.scrollTop=0;
  }
  function renderGraph(nodes,facts){
    const area=$('graph'),canvas=$('graphSvg');
    show('graphEmpty',!facts.length);
    if(!facts.length){canvas.replaceChildren();state.graphControl=null;return;}
    const displayed=facts.slice(0,65);
    const used=new Set(displayed.flatMap(f=>[f.subject.id,f.object.id]));
    const visible=nodes.filter(n=>used.has(n.id)).map(n=>({id:n.id,name:n.name,type:n.type||'Entity',linked:state.anchorIds.has(n.id)}));
    const edges=displayed.map(f=>({source:f.subject.id,target:f.object.id,type:f.predicate}));
    state.graphControl=window.KGGraph.render(canvas,{nodes:visible,edges,width:area.clientWidth,height:area.clientHeight,
      onEdge:selectFact,onNode:n=>{const i=displayed.findIndex(f=>f.subject.id===n.id||f.object.id===n.id);if(i>=0)selectFact(i);}});
    $('graphEmpty').textContent=facts.length>displayed.length
      ?`Chỉ hiển thị ${displayed.length} quan hệ đầu tiên; xem đầy đủ trong danh sách.`:'';
  }
  $('queryZoomIn').addEventListener('click',()=>state.graphControl?.zoom(1.25));
  $('queryZoomOut').addEventListener('click',()=>state.graphControl?.zoom(1/1.25));
  $('queryFit').addEventListener('click',()=>state.graphControl?.fit());
  const queryPanel=$('graph').closest('.graph-card');
  $('queryFullscreen').addEventListener('click',async()=>{await window.KGGraph.toggleFullscreen(queryPanel);requestAnimationFrame(updateGraphSize);});
  function updateGraphSize(){state.graphControl?.resize($('graph').clientWidth,$('graph').clientHeight);$('queryFullscreen').setAttribute('aria-label',document.fullscreenElement===queryPanel||queryPanel.classList.contains('kg-fullscreen')?'Thoát toàn màn hình':'Toàn màn hình');}
  document.addEventListener('fullscreenchange',()=>requestAnimationFrame(updateGraphSize));
  window.addEventListener('resize',updateGraphSize);
  document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&queryPanel.classList.contains('kg-fullscreen')){queryPanel.classList.remove('kg-fullscreen');requestAnimationFrame(updateGraphSize);}});
  $('exportBtn').addEventListener('click',()=>{
    if(!state.result)return;const blob=new Blob([JSON.stringify(state.result,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='kg_query_result.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  setMode('related');
})();
