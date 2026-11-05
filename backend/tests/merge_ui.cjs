// Run with Node.js and jsdom available in NODE_PATH.
const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
const w=new JSDOM('<body></body>',{runScripts:'outside-only',url:'http://localhost:8100'}).window;
w.HTMLDialogElement.prototype.showModal=function(){};w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new w.Event('close'))};
w.fetch=async()=>({ok:true,json:async()=>({types:['Disease','Complication','ClinicalFinding']})});
w.eval(fs.readFileSync(require('path').join(__dirname,'../app/modules/kg_query/web/merge.js'),'utf8'));
const requests=[];let applied=0;
await w.openConceptMerge({entities:[{id:'A',canonical_name:'Name',type:'Disease'},{id:'B',canonical_name:'Name',type:'Complication'}],selectedIds:['A','B'],request:async body=>{requests.push(body);return body.operation==='preview'?{target:{canonical_name:'Name',entity_type:body.choice.type},members:[{},{}],stored_nodes:0,stored_relations:[],document_relations:[],conflicts:[],can_apply:true,token:'T'}:{applied:true,message:'Done'}},onApplied:async()=>applied++});
const buttons=[...w.document.querySelectorAll('button')],preview=buttons.find(b=>b.textContent==='Xem trước gộp'),apply=buttons.find(b=>b.textContent.startsWith('Xác nhận'));
assert.equal(apply.disabled,true);assert.equal(requests.length,0);
await preview.onclick();assert.equal(apply.disabled,false);assert.deepEqual(Array.from(requests[0].choice.ids),['A','B']);assert.equal(applied,0);
const type=w.document.querySelector('[aria-label="Loại sau gộp"]');type.value='ClinicalFinding';type.onchange();assert.equal(apply.disabled,true);
await preview.onclick();assert.equal(requests[1].choice.type,'ClinicalFinding');await apply.onclick();assert.equal(requests[2].confirmed,true);assert.equal(applied,1);assert.equal(w.document.querySelector('dialog'),null);
console.log('PASS: cross-type choice, read-only preview, stale choice invalidation, explicit apply');
})().catch(e=>{console.error(e);process.exit(1)});
