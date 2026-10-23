// No browser or dependencies needed: exercise the shipped UI with a tiny DOM surface.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '..', 'index.html'), 'utf8');
new vm.Script(source.split('<script>')[1].split('</script>')[0]);
const part = (from, to) => source.slice(source.indexOf(from), source.indexOf(to));
const nodes = {};
const routingCases = JSON.parse(fs.readFileSync(require('node:path').join(__dirname, 'routing_cases.json'), 'utf8'));
const c = vm.createContext({assert, console, setTimeout: () => {}, nodes, routingCases});
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
