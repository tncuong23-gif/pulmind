const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
const html=fs.readFileSync(require('path').join(__dirname,'../app/kg_global/web/index.html'),'utf8');const w=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost:8100/kg-global'}).window;
const calls=[];const state={revision:1,counts:{documents:2,entities:2,relations:0,assertions:0,evidence:0},entities:{A:{canonical_name:'Name',type:'Disease'},B:{canonical_name:'Name',type:'Complication'}},pairs:[{ids:['A','B']}],documents:[],conflicts:[],snapshots:[],types:['Disease','Complication'],active:null};
w.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>state}};
w.confirm=()=>true;w.eval(fs.readFileSync(require('path').join(__dirname,'../app/kg_global/web/app.js'),'utf8'));await new Promise(r=>setTimeout(r,20));
assert.equal(w.document.querySelectorAll('#groupList .card').length,1);assert.equal(calls.length,1);
const boxes=w.document.querySelectorAll('#groupList input[type=checkbox]');boxes.forEach(b=>b.checked=true);
const b=[...w.document.querySelectorAll('#groupList button')].find(b=>b.textContent.startsWith('Gộp thành viên'));b.click();await new Promise(r=>setTimeout(r,20));
const mutation=calls.find(c=>c.url.endsWith('/decide'));assert(mutation);assert.deepEqual(JSON.parse(mutation.options.body).ids,['A','B']);assert.equal(JSON.parse(mutation.options.body).revision,1);
assert(!calls.some(c=>/sync|activate/.test(c.url)));console.log('PASS: group review sends both documents through one decision; does not publish');
})().catch(e=>{console.error(e);process.exit(1)});
