const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const html=fs.readFileSync(path.join(__dirname,'../app/direct_import/web/index.html'),'utf8');
  const w=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/direct-import'}).window;
  let state={revision:4,entities:{A:{canonical_name:'Concept A',type:'F'},B:{canonical_name:'Concept B',type:'F'}},ambiguous_terms:[{type:'F',term:'shared',entity_ids:['A','B']}],warnings:[]};
  const calls=[];
  w.fetch=async(url,options)=>{
    calls.push({url,options});
    if(options?.method==='POST'){state={...state,revision:5,ambiguous_terms:[]};return {ok:true,json:async()=>({})};}
    return {ok:true,json:async()=>url.endsWith('/identity')?state:[]};
  };
  w.eval(fs.readFileSync(path.join(__dirname,'../app/direct_import/web/app.js'),'utf8'));
  const settle=()=>new Promise(r=>setTimeout(r,10));await settle();
  w.document.getElementById('identity-refresh').click();await settle();
  assert.equal(w.document.querySelectorAll('.identity-choice').length,2);
  w.document.querySelectorAll('.identity-choice').forEach(c=>c.checked=true);
  w.document.getElementById('identity-name').value='Reviewed name';
  w.document.getElementById('identity-merge').click();await settle();
  const decision=calls.find(c=>c.options?.method==='POST');assert(decision);
  assert.deepEqual(JSON.parse(decision.options.body),{revision:4,action:'merge',ids:['A','B'],target_id:'A',name:'Reviewed name',type:'F'});
  assert(w.document.getElementById('identity-panel').hidden);
  assert(!calls.some(c=>/sync|activate/.test(c.url)));
  console.log('PASS: ambiguity candidates, explicit reviewed merge, revision, refresh; no automatic publication.');w.close();
})().catch(e=>{console.error(e);process.exit(1)});
