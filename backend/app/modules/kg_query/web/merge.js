/* Explicit concept merge: preview is read-only; apply requires a separate click. */
window.openConceptMerge = async function ({entities, selectedIds=[], request, onApplied}) {
  const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
  const dialog=make('dialog');dialog.style.cssText='width:min(960px,92vw);max-height:88vh;overflow:auto;border:1px solid #b7d8d8;border-radius:16px;padding:24px;color:#123b42;background:white';
  const title=make('h2','Gộp cùng khái niệm');const note=make('p','Chọn các thực thể, tên chuẩn và loại sau gộp. Xác nhận sẽ lưu node chuẩn và chuyển các quan hệ đã có trong KG; tài liệu vẫn cần được nạp riêng.');
  const close=make('button','Đóng');close.type='button';close.onclick=()=>dialog.close();dialog.append(title,note,close);
  const list=make('div');list.style.cssText='max-height:230px;overflow:auto;margin:16px 0';
  const unique=[...new Map(entities.map(e=>[e.id,e])).values()];const checked=new Map();
  const target=make('select');target.setAttribute('aria-label','ID chuẩn');target.style.width='100%';
  const name=make('input');name.setAttribute('aria-label','Tên chuẩn');name.style.width='100%';
  const type=make('select');type.setAttribute('aria-label','Loại sau gộp');type.style.width='100%';
  const result=make('div');result.setAttribute('role','status');const preview=make('button','Xem trước gộp');preview.type='button';const apply=make('button','Xác nhận gộp và lưu node chuẩn');apply.type='button';apply.disabled=true;let token=null;
  const invalidate=()=>{token=null;apply.disabled=true;result.replaceChildren();};
  const refresh=()=>{const previous=target.value;target.replaceChildren();for(const e of unique)if(checked.get(e.id)?.checked)target.append(new Option(`${e.canonical_name||e.name} · ${e.entity_type||e.type||'chưa rõ'} · ${e.id}`,e.id));if([...target.options].some(o=>o.value===previous))target.value=previous;invalidate();};
  for(const e of unique){const row=make('label');row.style.cssText='display:block;padding:8px;border-bottom:1px solid #e4eeee';const box=make('input');box.type='checkbox';box.checked=selectedIds.includes(e.id);checked.set(e.id,box);box.onchange=refresh;row.append(box,document.createTextNode(` ${e.canonical_name||e.name} · ${e.entity_type||e.type||'chưa rõ'} · ${e.id}`));list.append(row);}
  refresh();const initial=unique.find(e=>e.id===target.value)||unique[0];name.value=initial?.canonical_name||initial?.name||'';
  name.oninput=invalidate;type.onchange=invalidate;target.onchange=invalidate;
  dialog.append(list,make('p','ID chuẩn'),target,make('p','Tên chuẩn'),name,make('p','Loại sau gộp'),type,preview,apply,result);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
  try{const r=await fetch('/modules/kg-explorer/api/review/merge/types');if(!r.ok)throw Error('Không tải được ontology.');const data=await r.json();for(const t of data.types)type.append(new Option(t,t));type.value=initial?.entity_type||initial?.type||data.types[0];}catch(e){result.textContent=e.message;preview.disabled=true;}
  const lock=v=>{for(const e of dialog.querySelectorAll('input,select,button'))e.disabled=v;apply.disabled=v||!token;};
  preview.onclick=async()=>{invalidate();lock(true);result.textContent='Đang kiểm tra quan hệ và nguồn…';try{
    const data=await request({operation:'preview',choice:{ids:unique.filter(e=>checked.get(e.id).checked).map(e=>e.id),target_id:target.value,name:name.value,type:type.value}});
    result.replaceChildren(make('h3',`${data.target.canonical_name} · ${data.target.entity_type}`),make('p',`${data.members.length} thực thể → 1 node. ${data.stored_nodes} node đã có trong KG; ${data.stored_relations.length} quan hệ đã lưu và ${data.document_relations.length} quan hệ trong tài liệu được kiểm tra.`));
    if(data.conflicts.length){result.append(make('h4','Chưa thể gộp'));for(const c of data.conflicts)result.append(make('p',`${c.relation_id||c.entity_id||''}: ${c.message}`));}
    const details=make('details');details.append(make('summary','Xem các quan hệ và tài liệu nguồn'));
    for(const r of data.stored_relations)details.append(make('p',`${r.relation} · ${r.id} · ${r.before.join(' → ')} ⇒ ${r.after.join(' → ')} · nguồn ${r.document_id||'không rõ'}`));
    for(const r of data.document_relations)details.append(make('p',`Tài liệu đang duyệt: ${r.relation} · ${r.id} · ${r.after.join(' → ')}`));result.append(details);
    token=data.can_apply?data.token:null;
  }catch(e){result.textContent=e.message;}finally{lock(false);}};
  apply.onclick=async()=>{if(!token)return;lock(true);try{const data=await request({operation:'apply',token,confirmed:true});token=null;result.textContent=data.warning||data.message;await onApplied(data);if(!data.warning)dialog.close();}catch(e){token=null;result.textContent=e.message+' Hãy xem trước lại trước khi thử tiếp.';}finally{lock(false);}};
};
