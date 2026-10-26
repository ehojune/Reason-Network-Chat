// No browser or dependencies needed: exercise the shipped UI with a tiny DOM surface.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '..', 'index.html'), 'utf8');
new vm.Script(source.split('<script>')[1].split('</script>')[0]);
const part = (from, to) => source.slice(source.indexOf(from), source.indexOf(to));
const speed = vm.createContext({assert});
vm.runInContext(`
const fields = {'#lfSpeedRow':{}, '#lfSpeed':{}, '#lfModel':{value:'m'}, '#lfEffort':{value:'high'},
  '#lfGo':{}, '#dlg':{close(){this.closed=true}}};
const $ = id => fields[id], t = key => key, esc = value => value;
let LF = {agent:'codex',fast:true,full:false};
const posted = [], hint=()=>{}, say=()=>{}, poll=()=>{};
const post = async (path, body) => { posted.push({path,body}); return {restarted:false}; };
`, speed);
vm.runInContext(part('function renderSpeed()', 'function renderPerms()'), speed);
vm.runInContext(part('async function configureWorker(force)', '// ---- rooms:'), speed);
vm.runInContext(`
(async () => {
  renderSpeed(); assert.equal(fields['#lfSpeed'].value,'fast');
  LF.fast=false; renderSpeed(); assert.equal(fields['#lfSpeed'].value,'standard');
  LF.fast=null; renderSpeed(); assert.equal(fields['#lfSpeed'].value,'');
  LF.agent='claude'; LF.fast=true; renderSpeed();
  assert.equal(fields['#lfSpeedRow'].hidden,true); assert.equal(LF.fast,null);
  LF.agent='codex'; LF.fast=true;
  LF.w={name:'c',model:'m',effort:'high',fullAccess:false,liveSettings:true,fast:null};
  await configureWorker(false);
  assert.equal(posted.length,1); assert.equal(posted[0].path,'/api/workers/configure');
  assert.equal(posted[0].body.fast,true); assert.equal(posted[0].body.force,false);
  assert.equal(fields['#dlg'].closed,true);
})().catch(error=>{throw error});
`, speed);
const nodes = {};
const routingCases = JSON.parse(fs.readFileSync(require('node:path').join(__dirname, 'routing_cases.json'), 'utf8'));
const workerReplyCases = JSON.parse(fs.readFileSync(require('node:path').join(__dirname, 'worker_reply_cases.json'), 'utf8'));
const c = vm.createContext({assert, console, setTimeout: () => {}, nodes, routingCases, workerReplyCases});
const errors = vm.createContext({assert});
vm.runInContext('const t = k => "localized:" + k; ' + part('const displayError', 'async function post'), errors);
vm.runInContext(`
assert.equal(displayError('Message blocked: suspected text encoding damage. details'), 'localized:encodingBlocked');
assert.equal(displayError('ordinary error'), 'ordinary error');
`, errors);
vm.runInContext(String.raw`
let S, sel = '';
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short = a => (a || '').split('/').pop();
const t = k => k, fmtT = x => String(x), fmtD = x => String(Math.floor(x / 86400000));
const $ = s => nodes[s] ||= {innerHTML:'', dataset:{}, addEventListener:() => {}, scrollHeight:0, scrollTop:0, clientHeight:0};
const roomOf = k => S.rooms.find(x => k === 'room:' + x.id);
const shown = m => {const r = roomOf(sel); return r ? r.members.includes(m.sender) || r.members.includes(m.recipient) : !sel || m.sender === sel || m.recipient === sel;};
const agentTag = () => '', unreadHow = () => '';
const groupRoomsOf = a => S.rooms.filter(r => r.group && r.members.includes(a));
const DM_MARK = '\n\n(1:1 message from ';
const reach = s => s.live === false || s.status === 'offline' ? 'offline' : 'now';
const base = () => ({me:'p/terminal', now:86400000, sessions:[{address:'p/a', tier:'turn', status:'idle', live:true}, {address:'p/b', tier:'turn', status:'offline', live:true}], rooms:[{id:'r', name:'Room', members:['p/a','p/b']}], messages:[], relays:{}, settled:{}});
const msg = (id, sender, recipient, body, reply_to=null) => ({id,sender,recipient,body,reply_to,sent_at:85000000,read_at:85100000,wake:1});
`, c);
vm.runInContext(part('function mdEmphasis', 'const rawIds'), c);
vm.runInContext(part('function relayOf', '// Who a group-room message'), c);
vm.runInContext(part('const MENTION_RE', '// A message to one session'), c);
vm.runInContext(part('function memberMentions', 'async function forwardToRoom'), c);
vm.runInContext(part('const rawIds', 'function render(force)'), c);
vm.runInContext(String.raw`
assert.match(md('[**API docs**](https://example.com/page_(v2))'), /href="https:\/\/example.com\/page_\(v2\)"[^>]*><strong>API docs<\/strong>/);
assert.match(md('(https://example.com/page_(v2)).'), /href="https:\/\/example.com\/page_\(v2\)"/);
assert.match(md('[*docs*](https://example.com/a)'), /<em>docs<\/em>/);
assert.ok(!md('<img src=x onerror=alert(1)>').includes('<img'));
assert.ok(!md('[x](javascript:alert(1))').includes('<a'));
assert.ok(!md('[x](https://e.test/" onclick="alert(1))').includes('href="https://e.test/&quot;'));
assert.match(md('- code:\n  \`\`\`python\n  if True:\n      print(1)\n\n  \`\`\`\n- next'), /<li><p>code:<\/p><pre><code>if True:\n    print\(1\)\n<\/code><\/pre><\/li><li><p>next/);
assert.match(md('- \`\`\`\n  - kept as code\n  \`\`\`'), /<pre><code>- kept as code<\/code><\/pre>/);
assert.ok(md('- '.repeat(2000) + 'end').length > 0); // bounded recursion on untrusted list text
for (const example of workerReplyCases) {
  assert.equal(isLogOnly(example.text),example.logOnly,example.name);
  assert.equal(isFailure(example.text),example.logOnly,example.name);
}
S=base(); sel=''; S.rooms[0].group=true;
const diagnostic='Reading additional input from stdin...\n2026-10-26T08:58:19Z WARN codex_core::test: @b <script>unsafe</script>';
S.messages=[msg('request','p/terminal','p/a','question'),msg('log','p/a','p/terminal',diagnostic,'request')];
TR=troubles(); assert.equal(TR.get('request').kind,'failed');
assert.equal(forwardRooms({...S.messages[1],to:['p/terminal']}).length,0);
renderTl();
assert.ok(nodes['#tl'].innerHTML.includes('logOnlyReply'));
assert.ok(nodes['#tl'].innerHTML.includes('<details><summary>executionLog'));
assert.ok(nodes['#tl'].innerHTML.includes('&lt;script&gt;unsafe'));
assert.ok(!nodes['#tl'].innerHTML.includes('<script>'));
assert.equal((nodes['#tl'].innerHTML.match(/class="msg /g)||[]).length,1);
S.messages=[msg('old-copy','p/terminal','p/b','old envelope')];
S.relays={'old-copy':{room:'r',hop:1,speaker:'p/a',core:diagnostic,source:'unloaded'}};
TR=troubles(); renderTl();
assert.ok(nodes['#tl'].innerHTML.includes('logOnlyReply'));
assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,0);
S=base(); sel=''; S.messages=[msg('human','p/terminal','p/a',diagnostic)];
TR=troubles(); renderTl();
assert.ok(!nodes['#tl'].innerHTML.includes('logOnlyReply'));
assert.equal((nodes['#tl'].innerHTML.match(/class="msg /g)||[]).length,1);
S.messages.push(msg('answer','p/a','p/terminal',diagnostic+'\nThe change is ready.','human'));
TR=troubles(); renderTl();
assert.equal(TR.size,0);
assert.equal((nodes['#tl'].innerHTML.match(/class="msg /g)||[]).length,2);
S=base();
S.messages=[msg('m','p/terminal','p/a','<script>alert(1)</script>'), msg('f','p/a','p/terminal',"You've hit your session limit · resets 5am",'m'), msg('n','p/terminal','p/b','second')];
TR=troubles();
assert.equal(TR.size,2); assert.equal(TR.get('m').kind,'failed'); assert.equal(TR.get('n').kind,'noanswer');
let html=troubleListHtml(troublesInView());
assert.ok(html.includes('&lt;script&gt;')); assert.ok(!html.includes('<script>'));
assert.ok(html.includes('session limit')); assert.ok(html.includes('data-action="resend" disabled'));
assert.equal((html.match(/class="troubleItem"/g)||[]).length,2);
renderTroubleList();
const expanded = nodes['#troubleItems'].innerHTML.replace('<details>', '<details open>');
nodes['#troubleItems'].innerHTML = expanded;
renderTroubleList(); assert.equal(nodes['#troubleItems'].innerHTML, expanded); // polling keeps failure details open
S.messages[0].body = 'updated message'; renderTroubleList();
assert.ok(nodes['#troubleItems'].innerHTML.includes('updated message')); // actual data changes still refresh
sel='p/a'; assert.equal(troublesInView().length,1);
S.settled.m={how:'dismissed',at:S.now}; TR=troubles(); assert.equal(troublesInView().length,0);
S=base(); sel='';
S.messages=[msg('m','p/terminal','p/a','@all question'),msg('copy','p/terminal','p/b','@all question')];
for(let i=0;i<9;i++) S.messages.push(msg('ack'+i, i%2?'p/a':'p/b','p/terminal', i%2?'-':'(해당 없음)',i%2?'m':'copy'));
S.messages.push(msg('real','p/a','p/terminal','4','m'));
TR=troubles(); renderTl(); html=nodes['#tl'].innerHTML;
assert.equal((html.match(/class="ack"/g)||[]).length,1);
assert.equal((html.match(/class="msg /g)||[]).length,2);
assert.ok(html.includes('data-ids="[&quot;m&quot;,&quot;copy&quot;]"'));
assert.ok(html.includes('data-target="m"')); assert.ok(html.includes('ack8'));
S.messages.push(msg('missing','p/a','p/terminal','answer','unloaded')); renderTl();
assert.ok(nodes['#tl'].innerHTML.includes('missingOriginal'));
assert.ok(!noAnswer('4')); assert.ok(!noAnswer('no')); assert.ok(noAnswer('—'));
for (const example of routingCases) {
  const room={members:['p/a','p/b','p/c']};
  assert.equal(JSON.stringify(roomTargets(room,example.text).to),JSON.stringify(example.to),example.text);
  assert.equal(JSON.stringify(memberMentions(room,example.text,'')),JSON.stringify(example.to),example.text);
}
assert.equal(memberMentions({members:['p/all','p/a']},'@all','').length,0);
S=base(); sel=''; S.rooms[0].group=true;
S.messages=[msg('seed','p/terminal','p/a','question'), msg('source','p/a','p/terminal','@b result','seed'),
  msg('d1','p/terminal','p/b','envelope one'),msg('d2','p/terminal','p/b','envelope two'),
  msg('answer','p/b','p/terminal','4','d1')];
S.relays={seed:{room:'r',hop:0,speaker:'p/terminal',core:'question'},
  d1:{room:'r',hop:1,speaker:'p/a',core:'@b result',source:'source'},
  d2:{room:'r',hop:1,speaker:'p/a',core:'@b result',source:'source'}};
TR=troubles(); renderTl(); html=nodes['#tl'].innerHTML;
assert.equal((html.match(/class="relay /g)||[]).length,0); // copies are delivery records, not new statements
assert.equal((html.match(/class="msg /g)||[]).length,3); // "4" remains a real answer
assert.equal((html.match(/class="deliveries"/g)||[]).length,1);
assert.ok(html.includes('data-ids="[&quot;source&quot;,&quot;d1&quot;,&quot;d2&quot;]"'));
assert.ok(html.includes('data-target="d1"')); // a quote of a folded delivery still finds its source bubble
sel='p/b'; renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,2);
sel='room:r'; renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,0);
delete S.relays.d1.source; delete S.relays.d2.source;
renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,0); // proven legacy source
S.messages.push(msg('separate','p/a','p/terminal','@b result','seed'));
renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,2); // ambiguous legacy text is kept
S.relays.d1.source='not-loaded'; S.relays.d2.source='not-loaded'; S.messages.pop();
renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,2); // no guessing when source is absent
S.relays.d1.source='source'; S.relays.d2.source='source';
S.messages.push(msg('fail','p/b','p/terminal',"You've hit your session limit",'d2'));
TR=troubles(); renderTl(); html=nodes['#tl'].innerHTML;
assert.ok(html.includes('data-id="d2"')); // inspection/retry stays available on the folded delivery
S=base(); sel='';
S.messages=[msg('p1','p/terminal','p/a','envelope one'),msg('p2','p/terminal','p/b','envelope two')];
S.relays={p1:{room:'r',hop:1,speaker:'p/a',core:'same post',source:'post-1',post:'managed'},
  p2:{room:'r',hop:1,speaker:'p/a',core:'same post',source:'post-2',post:'managed'}};
TR=troubles(); renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,2);
S.relays.p2.source='post-1'; renderTl(); assert.equal((nodes['#tl'].innerHTML.match(/class="relay /g)||[]).length,1);
S=base(); S.rooms[0].group=true;
S.messages=[msg('original','p/terminal','p/a','[Group room "test"] same complete envelope'),
  msg('copy','p/terminal','p/a','[Group room "test"] same complete envelope')];
S.relays={original:{room:'r',hop:0,speaker:'p/terminal',core:'@a start'}};
assert.equal(forwardRooms({...msg('reply','p/a','p/terminal','@b result','copy'),to:['p/terminal']}).length,0);
S.messages.push(msg('separate','p/terminal','p/a',S.messages[0].body));
S.relays.separate={...S.relays.original};
assert.equal(relayOf(S.messages[1]),null); // two independently recorded sends are ambiguous
S.relays.separate.copyOf='original';
assert.equal(relayOf(S.messages[1]).room,'r'); // proven aliases share one family
console.log('UI regression checks passed');
`, c);
// Sidebar preferences and context menus, isolated from timeline state.
const side = vm.createContext({assert, console});
vm.runInContext(String.raw`
let S, sel='';
const nodes={};
const $=s => nodes[s] ||= {innerHTML:'',dataset:{},style:{},hidden:false,focus(){},querySelectorAll(){return [];},
  showModal(){this.open=true;},close(){this.open=false;},getBoundingClientRect(){return {left:0,bottom:0};},offsetWidth:200,offsetHeight:200};
const document={activeElement:null}, innerWidth=1200, innerHeight=800;
const esc=v=>String(v ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const t=k=>k, short=a=>a.split('/').pop(), st=s=>s;
const autoOn=a=>(S.prefs.autoWake||[]).includes(a);
const store={get:()=>null}, person=()=> 'p', isAck=()=>false, inRoom=()=>false;
const launchedHere=()=>false, stoppedWorkers=()=>[];
const roomOf=k=>S.rooms.find(r=>'room:'+r.id===k);
const reach=s=>s.status==='gone'?'gone':s.status==='offline'?'offline':s.tier==='pull'?'pull':'now';
const reachLabel=s=>reach(s), NOW=['now'], LATER=['pull'];
`, side);
vm.runInContext(part('let sideSelection', '// Preferences live'), side);
vm.runInContext(part('function pref(key)', 'async function setPref'), side);
vm.runInContext(part('// Orders rank existing rows only.', 'function renderTo()'), side);
vm.runInContext(part('let ctxKey = null;', '$("#list").addEventListener("contextmenu"'), side);
vm.runInContext(String.raw`
S={messages:[],team:'test',me:'p/terminal',launched:[],foreignWorkers:[],rooms:[{id:'r',name:'room',members:[]}],
  prefs:{favorites:['p/fav'],autoWake:[],collapsedSections:[]},
  sessions:[{address:'p/fav',name:'fav',agent:'codex',live:true,worker:true,status:'idle'},
    {address:'p/now',name:'now',agent:'codex',live:true,status:'idle',resumable:true},
    {address:'p/later',name:'later',agent:'codex',live:true,status:'idle',tier:'pull'},
    {address:'p/off',name:'off',agent:'codex',live:true,status:'offline'},
    {address:'p/gone',name:'gone',agent:'codex',live:false,status:'gone'}]};
renderSide();
assert.equal((nodes['#list'].innerHTML.match(/data-section=/g)||[]).length,6);
for(const key of ['favorites','rooms','now','later','offline','history']) {
  S.prefs.collapsedSections=[key]; renderSide();
  assert.ok(nodes['#list'].innerHTML.includes('id="section-'+key+'" hidden></div>'));
  assert.equal((nodes['#list'].innerHTML.match(/aria-expanded="false"/g)||[]).length,1);
}
S.prefs.collapsedSections=['favorites']; renderSide();
assert.ok(!nodes['#list'].innerHTML.includes('data-a="p/fav"'));
assert.ok(nodes['#list'].innerHTML.includes('data-a="p/now"'));
S.prefs.collapsedSections=[]; renderSide();
const row=a=>({dataset:{a},getBoundingClientRect(){return {left:0,bottom:0};}});
openCtx(row('p/fav'),null);
assert.equal(nodes['#ctxAuto'].hidden,true);
assert.equal(nodes['#ctxAutoNote'].textContent,'workerAuto');
openCtx(row('p/now'),null);
assert.equal(nodes['#ctxAuto'].hidden,false); // ordinary Codex conversations still get the toggle
assert.equal(nodes['#ctxAutoNote'].hidden,true);
S.prefs.favorites=['p/now']; renderSide(); openCtx(row('p/now'),null);
assert.equal(nodes['#ctxAuto'].hidden,false); // favoriting never removes the toggle
S.sessions[0].stale=true; openCtx(row('p/fav'),null);
assert.equal(nodes['#ctxAutoNote'].textContent,'workerStopped');
openCtx(row('room:r'),null); assert.equal(nodes['#ctxAutoNote'].hidden,true);
// A selected row moving into a closed bucket stays reachable, while explicit collapse wins.
sel='p/now'; S.prefs.favorites=[]; S.prefs.collapsedSections=['offline','history']; renderSide();
S.sessions[1].status='offline'; renderSide();
assert.ok(nodes['#list'].innerHTML.includes('data-a="p/now"'));
assert.ok(!nodes['#list'].innerHTML.includes('id="section-offline" hidden'));
revealedSection=null; renderSide(); // the disclosure click explicitly closed this bucket
assert.ok(!nodes['#list'].innerHTML.includes('data-a="p/now"'));
S.sessions[1].status='gone'; S.sessions[1].live=false; renderSide();
assert.ok(nodes['#list'].innerHTML.includes('data-a="p/now"'));
// An unadopted serve worker is still a worker; no adoption or auto-wake is needed.
S.foreignWorkers=[{name:'outside'}];
S.sessions.push({address:'p/outside',name:'outside',agent:'cli',live:true,status:'idle'});
openCtx(row('p/outside'),null);
assert.equal(nodes['#ctxAutoNote'].textContent,'workerAuto');
assert.equal(nodes['#ctxAuto'].hidden,true);
assert.equal(nodes['#ctxAdopt'].hidden,false);
console.log('Sidebar regression checks passed');
`, side);
vm.runInContext(String.raw`
(async () => {
  sel=''; S.prefs={favorites:['p/fav'],collapsedSections:[],sidebarOrder:{now:['p/off','p/b','p/a'],later:['p/c']}};
  S.sessions=[{address:'p/a',name:'a',status:'busy',live:true}, {address:'p/b',name:'b',status:'idle',live:true},
    {address:'p/c',name:'c',status:'idle',live:true,tier:'pull'}, {address:'p/off',name:'off',status:'offline',live:true},
    {address:'p/fav',name:'fav',status:'idle',live:true}];
  renderSide();
  assert.equal(sidebarSections.get('now').keys.join(','),'p/b,p/a'); // saved order beats busy-first
  assert.equal(sidebarSections.get('offline').keys.join(','),'p/off'); // cannot move between sections
  assert.equal(sidebarSections.get('favorites').keys.join(','),'p/fav');
  S.sessions.push({address:'p/new',name:'new',status:'idle',live:true}); renderSide();
  assert.equal(sidebarSections.get('now').keys.join(','),'p/b,p/a,p/new'); // new rows append
  openOrder('now');
  assert.equal(nodes['#orderDlg'].open,true);
  assert.equal(moveOrder('p/c','p/b'),false); // another section's key cannot be dragged in
  assert.equal(moveOrder('p/b','p/off'),false);
  assert.equal(moveOrder('p/b','p/new'),true);
  assert.equal(orderDraft.keys.join(','),'p/a,p/new,p/b');
  assert.equal(S.prefs.sidebarOrder.now.join(','),'p/off,p/b,p/a'); // editing changes nothing until Save
  assert.ok(nodes['#orderList'].innerHTML.includes('draggable="true"'));
  assert.ok(nodes['#orderList'].innerHTML.includes('aria-label="orderUp: a" disabled'));
  S.sessions[0].status='offline'; // state may change while the modal stays open
  S.sessions.push({address:'p/arrived',name:'arrived',status:'idle',live:true});
  let saved;
  globalThis.setPref=async (key,value)=>{saved={key,value}; S.prefs[key]=value; renderSide(); return true;};
  await saveOrder();
  assert.equal(saved.key,'sidebarOrder');
  assert.equal(saved.value.now.join(','),'p/new,p/b,p/arrived');
  assert.equal(saved.value.later.join(','),'p/c'); // other section's preference preserved
  assert.equal(S.prefs.favorites.join(','),'p/fav'); // no favoriting/unfavoriting side effect
  assert.equal(sidebarSections.get('offline').keys.includes('p/a'),true);
  assert.equal(nodes['#orderDlg'].open,false);
  openOrder('now');
  globalThis.setPref=async ()=>false;
  await saveOrder(); assert.equal(nodes['#orderDlg'].open,true); // rejected save stays reviewable
  S.prefs.sidebarOrder.favorites=['room:r','p/fav'];
  S.prefs.favorites=['p/fav','room:r']; renderSide();
  assert.equal(sidebarSections.get('favorites').keys.join(','),'room:r,p/fav');
  console.log('Section order regression checks passed');
})()
`, side).catch(error => { console.error(error); process.exitCode=1; });
