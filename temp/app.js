// ═══ Society — قرية الرياح · Ghibli edition ═══
// Live data comes from the FastAPI backend (same origin). No fake data here.

// ── API layer ──
async function apiGet(path){
  const r = await fetch(path);
  if(!r.ok) throw new Error('GET ' + path + ' → ' + r.status);
  return r.json();
}
async function apiPost(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});
  const j = await r.json().catch(()=>({success:false, error:'bad response'}));
  if(!r.ok) throw new Error(j.detail || j.error || ('POST ' + path + ' → ' + r.status));
  return j;
}

// ── live state (filled by loadFromAPI) ──
let myUser = {
  id: 'me', name: 'Hana', nickname: 'هانا 🌸', handle: '@hana',
  avatar: 'https://i.pravatar.cc/100?img=5',
  banner: 'https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?w=800',
  bio: '', status: '🌿 متاحة', statusText: '🌿 متاحة'
};

function imgFallback(name){
  return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect fill="%2376B086" width="100" height="100"/><text fill="white" x="50" y="50" font-family="sans-serif" font-size="40" dominant-baseline="middle" text-anchor="middle">${encodeURIComponent(name?name.charAt(0):'?')}</text></svg>`;
}

document.addEventListener('error', function(e) {
  if (e.target.tagName && e.target.tagName.toLowerCase() === 'img') {
    if(!e.target.dataset.failed){
       e.target.dataset.failed = "true";
       e.target.src = imgFallback(e.target.alt || '?');
    }
  }
}, true);

let users = [];
let servers = [];
let groups = [];
let friendRequests = [];

let currentChat = {type:'group', id:null};
let dmConversations = [];
let blockedUsers = new Set();
let mutedUsers = new Set();
let selectedUserForAction = null;

let messagesByChat = {};

function mapMsg(m){
  const u = m.from_id==='me' ? myUser : (users.find(x=>x.id===m.from_id) || {name:m.from_id, avatar:''});
  return {id:m.id, from:m.from_id, name:u.name||m.from_id, avatar:u.avatar||'', text:m.text||'', time:m.time||'', mine:m.from_id==='me'};
}

async function fetchSnapshot(){
  const [meRes, usersRes, serversRes, groupsRes, reqRes] = await Promise.all([
    apiGet('/tools/profile?current_user_id=me'),
    apiGet('/tools/users?limit=50'),
    apiGet('/tools/groups'),
    apiGet('/tools/servers'),
    apiGet('/tools/friend_requests'),
  ]);
  if(!meRes.success) throw new Error(meRes.error || 'profile failed');
  return {meRes, usersRes, serversRes, groupsRes, reqRes};
}

function applySnapshot({meRes, usersRes, serversRes, groupsRes, reqRes}){
  const me = meRes.data;
  myUser = {...myUser, ...me};
  myUser.statusText = me.status || myUser.statusText;
  blockedUsers = new Set(me.blocked || []);
  mutedUsers = new Set(me.muted || []);
  const friends = new Set(me.friends || []);
  const allUsers = (usersRes.data || usersRes) instanceof Array ? (usersRes.data || usersRes) : [];
  users = allUsers.filter(u=>u.id!=='me').map(u=>({...u, isFriend: friends.has(u.id)}));
  servers = (serversRes.data || []).map(s=>({id:s.id, name:s.name, desc:s.description||'', img:s.img||''}));
  groups = (groupsRes.data || []).map(g=>({id:g.id, name:g.name, members:g.members||[], avatar:g.avatar||''}));
  friendRequests = (reqRes.data || []).filter(r=>r.to_id==='me' && r.status==='pending').map(r=>{
    const u = users.find(x=>x.id===r.from_id) || {};
    const uFriends = new Set(u.friends || []);
    const mutual = [...friends].filter(f=>uFriends.has(f)).length;
    return {id:r.id, from:r.from_id, name:u.name||r.from_id, avatar:u.avatar||'', handle:u.handle||'', mutual};
  });
  const savedDMs = JSON.parse(localStorage.getItem('saved_dms') || '[]');
  const dmSet = new Set([...users.filter(u=>u.isFriend).map(u=>u.id), ...savedDMs]);
  if(currentChat.type === 'dm' && currentChat.id) dmSet.add(currentChat.id);
  dmConversations = Array.from(dmSet).filter(id => id && id !== 'me' && !blockedUsers.has(id));
  if(!currentChat.id || (currentChat.type==='group' && !groups.find(g=>g.id===currentChat.id))){
    currentChat = groups.length ? {type:'group', id:groups[0].id} : {type:'group', id:null};
  }
}

async function loadChatMessages(id){
  try{
    const m = await apiGet('/tools/messages?chat_id=' + encodeURIComponent(id));
    messagesByChat[id] = (m.data || []).map(mapMsg);
  }catch(e){ messagesByChat[id] = messagesByChat[id] || []; }
}

async function loadFromAPI(){
  const snap = await fetchSnapshot();
  applySnapshot(snap);
  const chats = [...groups.map(g=>g.id), ...servers.map(s=>s.id), ...dmConversations];
  await Promise.all(chats.map(loadChatMessages));
}

async function ensureChatLoaded(id){
  if(!id) return;
  await loadChatMessages(id);
}

// Render guard: remember what is currently shown so we don't rebuild the DOM
// (or yank the scroll) when nothing actually changed.
let renderedMsgKey = '';       // 'chatId::lastMsgId::count'
let renderedWasNearBottom = true;

function msgKey(id){
  const msgs = messagesByChat[id] || [];
  const last = msgs[msgs.length-1];
  return id + '::' + (last ? last.id : '') + '::' + msgs.length;
}

// Silent background refresh (shows agent activity live).
// Only the OPEN chat is re-fetched each tick; chats are always re-fetched
// fresh when you open them (ensureChatLoaded), so no need to poll every chat.
async function refreshFromAPI(){
  try{
    const snap = await fetchSnapshot();
    const keepChat = {...currentChat};
    applySnapshot(snap);
    if(keepChat.id) currentChat = keepChat;
    if(currentChat.id && !currentChat._loading){
      currentChat._loading = true;
      try { await loadChatMessages(currentChat.id); }
      finally { currentChat._loading = false; }
    }
    renderAll();
  }catch(e){ /* server unreachable — keep last state */ }
}

function renderMe(){
  if($('sidebarName')) $('sidebarName').textContent = myUser.name;
  if($('sidebarStatusText')) $('sidebarStatusText').textContent = myUser.status;
  if($('railAvatar')) $('railAvatar').src = myUser.avatar || imgFallback(myUser.name);
  if($('sidebarAvatar')) $('sidebarAvatar').src = myUser.avatar || imgFallback(myUser.name);
  if($('bannerPreview') && myUser.banner) $('bannerPreview').style.backgroundImage = `url(${myUser.banner})`;
  if($('accountAvatarPreview') && myUser.avatar) $('accountAvatarPreview').src = myUser.avatar || imgFallback(myUser.name);
}
function renderAll(){
  renderMe();
  renderServersRail(); renderSidebarServers(); renderDMs(); renderGroups();
  renderFriends(); renderRequests(); renderMembers(); renderMessages(); updateHeaderForChat();
}

// ── falling leaves ──
function spawnLeaves(){
  const layer = document.getElementById('leavesLayer');
  const colors = ['#7FB069','#A8C686','#E0A458','#C97B4A'];
  for(let i=0;i<12;i++){
    const l = document.createElement('div');
    l.className = 'leaf-fall';
    const size = 10 + Math.random()*10;
    const color = colors[i % colors.length];
    l.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 20 20"><path d="M10 1 C4 6 2 11 5 16 C8 19 12 19 15 16 C18 11 16 6 10 1Z" fill="${color}" opacity=".8"/></svg>`;
    l.style.left = Math.random()*100 + 'vw';
    l.style.animationDuration = (9 + Math.random()*10) + 's';
    l.style.animationDelay = (-Math.random()*12) + 's';
    layer.appendChild(l);
  }
}

// ── helpers ──
function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = '✦ ' + msg;
  t.classList.remove('hidden');
  clearTimeout(t._h);
  t._h = setTimeout(()=>t.classList.add('hidden'), 2600);
}
const uid = () => Math.random().toString(36).slice(2,9);
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const $ = id => document.getElementById(id);

// ── renders ──
function renderServersRail(){
  $('serversList').innerHTML = servers.map(s=>`
    <button class="server-leaf" data-ctx="server" data-id="${s.id}" data-tip="${s.name}" onclick="switchServer('${s.id}', this)" oncontextmenu="showContextMenu(event, 'server', '${s.id}')">
      <img src="${s.img}" alt="">
    </button>`).join('');
}
function renderSidebarServers(){
  $('sidebarServers').innerHTML = servers.map(s=>`
    <div class="server-row" data-ctx="server" data-id="${s.id}" onclick="switchServer('${s.id}')" oncontextmenu="showContextMenu(event, 'server', '${s.id}')">
      <img src="${s.img}" alt="">
      <div style="flex:1;min-width:0">
        <strong style="font-size:12.5px;display:block">${s.name}</strong>
        <span class="muted">${s.desc}</span>
      </div>
    </div>`).join('') || '<p class="muted" style="padding:8px">لا سيرفرات بعد</p>';
}
function renderDMs(){
  $('dmList').innerHTML = dmConversations.map(id=>{
    const u = users.find(x=>x.id===id);
    if(!u || blockedUsers.has(u.id)) return '';
    const active = currentChat.type==='dm' && currentChat.id===id ? 'active' : '';
    const nick = u.nickname && u.nickname!==u.name ? ` • ${u.nickname}` : '';
    return `<div class="dm-item ${active}" data-ctx="dm" data-id="${u.id}" onclick="openDM('${u.id}')" oncontextmenu="showContextMenu(event, 'dm', '${u.id}')">
      <img src="${u.avatar}" alt="">
      <div class="meta">
        <strong>${u.name}${mutedUsers.has(u.id)?' 🔇':''}</strong>
        <span class="muted">${u.status==='online'?'متصل الآن':u.status==='idle'?'مشغول':'غير متصل'}${nick}</span>
      </div>
      <span class="dot ${u.status}"></span>
    </div>`;
  }).join('') || '<p class="muted" style="padding:8px">لا محادثات</p>';
}
function renderGroups(){
  $('groupsList').innerHTML = groups.map(g=>{
    const active = currentChat.type==='group' && currentChat.id===g.id ? 'active' : '';
    return `<div class="group-item ${active}" data-ctx="group" data-id="${g.id}" onclick="openGroup('${g.id}')" oncontextmenu="showContextMenu(event, 'group', '${g.id}')">
      <div class="g-icon">✿</div>
      <div style="flex:1;min-width:0">
        <strong style="font-size:13px;display:block">${g.name}</strong>
        <span class="muted">${g.members.length} أرواح</span>
      </div>
    </div>`;
  }).join('');
}
function renderFriends(){
  const friends = users.filter(u=>u.isFriend && !blockedUsers.has(u.id));
  $('friendsList').innerHTML = friends.length ? friends.map(u=>`
    <div class="friend-row" data-ctx="friend" data-id="${u.id}">
      <img src="${u.avatar}" alt="">
      <div class="meta">
        <strong>${u.name} ${u.nickname && u.nickname!==u.name ? `<span style="color:var(--ghibli-gold);font-weight:500">(${u.nickname})</span>`:''} ${mutedUsers.has(u.id)?'🔇':''}</strong>
        <span class="muted">${u.handle} • ${u.bio.slice(0,28)}</span>
      </div>
      <div class="friend-actions">
        <button class="icon-btn-sm" title="دردشة" onclick="openDM('${u.id}')">🍃</button>
        <button class="icon-btn-sm" title="خيارات" onclick="openUserActions('${u.id}')">⋯</button>
      </div>
    </div>`).join('')
  : '<p class="muted" style="padding:16px;text-align:center">لا أصدقاء بعد — أرسل رسالة طائر! 🕊</p>';
}
function renderRequests(){
  const n = friendRequests.length;
  const b = $('reqBadge');
  b.textContent = n || '';
  b.style.display = n ? 'inline-block' : 'none';
  $('requestsList').innerHTML = n ? friendRequests.map(r=>`
    <div class="friend-row" data-ctx="request" data-id="${r.id}" style="background:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.8);border-radius:14px">
      <img src="${r.avatar}" alt="">
      <div class="meta">
        <strong>${r.name}</strong>
        <span class="muted">${r.handle} • ${r.mutual} أصدقاء مشتركون</span>
      </div>
      <div class="friend-actions">
        <button class="icon-btn-sm primary" onclick="acceptRequest('${r.id}')">✓</button>
        <button class="icon-btn-sm" onclick="declineRequest('${r.id}')">✕</button>
      </div>
    </div>`).join('')
  : '<p class="muted" style="padding:16px;text-align:center">لا طلبات جديدة</p>';
}
function renderMembers(){
  let ids = [];
  if(currentChat.type==='group'){ const g=groups.find(x=>x.id===currentChat.id); ids=g?g.members:[]; }
  else if(currentChat.type==='dm'){ ids=[currentChat.id]; }
  else { ids = users.slice(0,5).map(u=>u.id); }
  const list = ids.map(id => id==='me' ? {id:'me',name:myUser.name,avatar:myUser.avatar,status:'online'} : users.find(u=>u.id===id)).filter(Boolean);
  $('memberCount').textContent = list.length;
  $('membersList').innerHTML = list.map(m=>`
    <div class="member-row" data-ctx="member" data-id="${m.id}" onclick="openUserActions('${m.id}')" oncontextmenu="showContextMenu(event, 'member', '${m.id}')" style="display:flex;align-items:center;gap:8px">
      <img src="${m.avatar}" alt="${m.name}">
      <strong style="flex:1;min-width:0">${m.name}</strong>
      ${m.id!=='me' ? `<button class="icon-btn-sm" title="محادثة خاصة 🍃" onclick="event.stopPropagation();openDM('${m.id}')" style="font-size:13px;padding:3px 6px">🍃</button>` : ''}
      <span class="dot ${m.status||'online'}"></span>
    </div>`).join('');
}
function renderMessages(){
  const c = $('chatMessages');
  const msgs = messagesByChat[currentChat.id] || [];
  const key = msgKey(currentChat.id);
  const nearBottom = c.scrollHeight - c.scrollTop - c.clientHeight < 120;

  // Empty chat: render once (key includes count so we recover when msgs arrive).
  if(!msgs.length){
    if(renderedMsgKey === key) return;
    renderedMsgKey = key;
    c.innerHTML = `<div class="day-sep"><span>بداية الحكاية ✦</span></div>
      <div style="text-align:center;padding:36px 20px;color:var(--ink-soft)">
        <div style="font-size:42px;margin-bottom:10px">🌱</div>
        <p style="font-family:'Amiri',serif;font-size:15px">لا رسائل بعد — ازرع أول كلمة</p>
      </div>`;
    return;
  }

  // Rebuild only when the chat content actually changed.
  if(renderedMsgKey === key) return;
  renderedMsgKey = key;
  renderedWasNearBottom = nearBottom;

  c.innerHTML = `<div class="day-sep"><span>اليوم • ${new Date().toLocaleDateString('ar-EG')}</span></div>` + msgs.map(m=>`
    <div class="msg ${m.mine?'mine':''}">
      <img class="msg-avatar" src="${m.avatar}" alt="">
      <div class="msg-bubble">
        <div class="msg-meta"><strong class="${m.mine?'profile-font':''}">${m.name}</strong><span>${m.time}</span></div>
        <div class="msg-text">${esc(m.text)}</div>
        ${m.image?`<img class="msg-img" src="${m.image}" alt="">`:''}
      </div>
    </div>`).join('');
  // Keep the user's scroll position unless they were already at the bottom
  // (only then auto-follow new messages).
  const atBottom = c.scrollHeight - c.scrollTop - c.clientHeight < 120;
  if(renderedWasNearBottom || atBottom) c.scrollTop = c.scrollHeight;
  renderedWasNearBottom = c.scrollHeight - c.scrollTop - c.clientHeight < 120;
}

function updateHeaderForChat(){
  if(currentChat.type==='group'){
    const g = groups.find(x=>x.id===currentChat.id);
    $('chatName').textContent = g?g.name:'';
    $('chatSubtitle').textContent = g?`مجموعة • ${g.members.length} أرواح • نشطة الآن`:'';
    $('chatAvatar').src = g?g.avatar:'';
    $('chatAvatar').alt = g?g.name:'';
    $('rightName').textContent = g?g.name:'';
    $('rightAvatar').src = g?g.avatar:'';
    $('rightAvatar').alt = g?g.name:'';
    $('rightBio').textContent = 'مكان هادئ لمحبي الاستوديو، نتشارك الرسم والموسيقى تحت ضوء الفانوس 🌙';
    $('rightBanner').src = (g && g.banner) ? g.banner : 'https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?w=600';
  } else if(currentChat.type==='dm'){
    const u = users.find(x=>x.id===currentChat.id);
    $('chatName').textContent = u?u.name:'';
    $('chatSubtitle').textContent = u?`${u.handle}${u.nickname && u.nickname!==u.name ? ' • '+u.nickname : ''}`:'';
    $('chatAvatar').src = u?u.avatar:'';
    $('chatAvatar').alt = u?u.name:'';
    $('rightName').textContent = u?u.name:'';
    $('rightAvatar').src = u?u.avatar:'';
    $('rightAvatar').alt = u?u.name:'';
    $('rightBio').textContent = u?u.bio:'';
    $('rightBanner').src = (u && u.banner) ? u.banner : 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600';
    $('rightStatus').textContent = mutedUsers.has(u.id)?'🔇 مكتوم':blockedUsers.has(u.id)?'⛔ محظور':'🌿 متصل الآن';
  } else {
    const s = servers.find(x=>x.id===currentChat.id);
    $('chatName').textContent = s?s.name:'';
    $('chatSubtitle').textContent = s?s.desc:'';
    $('chatAvatar').src = s?s.img:'';
    $('chatAvatar').alt = s?s.name:'';
    $('rightName').textContent = s?s.name:'';
    $('rightAvatar').src = s?s.img:'';
    $('rightAvatar').alt = s?s.name:'';
    $('rightBio').textContent = s?`سيرفر • ${s.desc}`:'';
    $('rightBanner').src = (s && s.banner) ? s.banner : 'https://images.unsplash.com/photo-1448375240586-882707db888b?w=600';
  }
  $('chatStatusDot').className = 'status-leaf ' + (currentChat.type==='dm' ? (users.find(x=>x.id===currentChat.id)?.status || 'online') : 'online');
}

// ── navigation ──
function switchTab(tab){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===tab));
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
  $('tab-'+tab).classList.add('active');
}
function openGroup(id){ currentChat={type:'group',id}; updateHeaderForChat(); renderGroups(); renderDMs(); renderMembers(); renderMessages(); ensureChatLoaded(id).then(renderMessages); }
function openDM(id){
  if(!id || id==='me'){ toast('لا يمكنك محادثة نفسك 🌸'); return; }
  if(blockedUsers.has(id)){ toast('هذا المستخدم محظور'); return; }
  currentChat={type:'dm',id};
  if(!dmConversations.includes(id)){
    dmConversations.unshift(id);
    const saved = Array.from(new Set([id, ...JSON.parse(localStorage.getItem('saved_dms') || '[]')]));
    localStorage.setItem('saved_dms', JSON.stringify(saved));
  }
  if(!messagesByChat[id]) messagesByChat[id]=[];
  closeModal('userActionModal');
  closeModal('newDMModal');
  updateHeaderForChat(); renderDMs(); renderGroups(); renderMembers(); renderMessages();
  ensureChatLoaded(id).then(renderMessages);
  switchTab('chats');
  setTimeout(()=> $('messageInput')?.focus(), 80);
}

function openNewDMModal(){
  renderNewDMList();
  openModal('newDMModal');
}

function renderNewDMList(){
  const list = users.filter(u=>!blockedUsers.has(u.id));
  $('newDMList').innerHTML = list.length ? list.map(u=>`
    <div class="friend-row" style="cursor:pointer;background:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.8);border-radius:14px;padding:10px 14px;display:flex;align-items:center;gap:12px" onclick="openDM('${u.id}')">
      <img src="${u.avatar}" alt="${u.name}" style="width:42px;height:42px;border-radius:50%;object-fit:cover">
      <div class="meta" style="flex:1;min-width:0">
        <strong style="display:block;font-size:14px">${u.name} ${u.nickname && u.nickname!==u.name ? `<span style="color:var(--ghibli-gold);font-weight:500">(${u.nickname})</span>`:''}</strong>
        <span class="muted" style="display:block;font-size:12px">${u.bio || u.handle}</span>
      </div>
      <button class="primary-btn" style="padding:6px 14px;font-size:12.5px" onclick="event.stopPropagation();openDM('${u.id}')">محادثة 💬</button>
    </div>
  `).join('') : '<p class="muted" style="text-align:center;padding:16px">لا يوجد سكان حالياً</p>';
}

function startDMFromModal(){
  if(selectedUserForAction){
    openDM(selectedUserForAction.id);
  }
}

function startDMWithCurrentProfile(){
  if(currentChat.type==='dm'){
    $('messageInput')?.focus();
  } else if(selectedUserForAction){
    openDM(selectedUserForAction.id);
  } else {
    openNewDMModal();
  }
}
function switchServer(id, btn){
  document.querySelectorAll('.server-leaf').forEach(b=>b.classList.remove('active'));
  if(id==='home'){
    document.querySelector('.server-leaf.home').classList.add('active');
    currentChat = groups.length ? {type:'group', id: groups[0].id} : {type:'group', id:null};
  } else {
    if(!btn) btn = document.querySelector(`.server-leaf[data-id="${id}"]`);
    btn?.classList.add('active');
    currentChat={type:'server', id};
    if(!messagesByChat[id]) messagesByChat[id]=[];
    ensureChatLoaded(id).then(renderMessages);
  }
  updateHeaderForChat(); renderMembers(); renderMessages(); renderServersRail(); renderSidebarServers();
}

// ── messages (live via API) ──
async function sendMessage(){
  const inp = $('messageInput');
  const text = inp.value.trim();
  if(!text) return;
  if(!currentChat.id){ toast('لا توجد محادثة بعد — أنشئ مجموعة أولاً'); return; }
  try{
    const res = await apiPost('/tools/send_message', {chat_id: currentChat.id, text});
    if(!res.success){ toast(res.error || 'تعذر الإرسال'); return; }
    if(!messagesByChat[currentChat.id]) messagesByChat[currentChat.id]=[];
    messagesByChat[currentChat.id].push(mapMsg(res.data));
    inp.value='';
    renderMessages();
  }catch(e){ toast('تعذر الإرسال — تأكد أن السيرفر يعمل'); }
}

// ── search ──
function handleSearch(q){
  const box = $('searchResults');
  if(!q.trim()){ box.classList.add('hidden'); return; }
  const ql = q.toLowerCase();
  const res = users.filter(u=>!blockedUsers.has(u.id) &&
    (u.name.toLowerCase().includes(ql) || (u.nickname&&u.nickname.toLowerCase().includes(ql)) || u.handle.toLowerCase().includes(ql))
  ).slice(0,6);
  box.innerHTML = res.length ? res.map(u=>`
    <div class="search-item" onclick="selectSearchUser('${u.id}')">
      <img src="${u.avatar}" alt="">
      <div class="meta"><strong>${u.name}${u.nickname && u.nickname!==u.name ? ' ('+u.nickname+')':''}</strong><span>${u.handle}</span></div>
      <span style="font-size:11px;color:var(--ghibli-forest-light)">${u.isFriend?'صديق':'—'}</span>
    </div>`).join('')
  : '<div style="padding:12px;text-align:center;color:var(--ghibli-ink-soft);font-size:12.5px">لا نتائج في القرية</div>';
  box.classList.remove('hidden');
}
function selectSearchUser(id){
  $('searchResults').classList.add('hidden');
  $('searchInput').value='';
  openUserActions(id);
}

// ── modals ──
function openModal(id){ $(id).classList.remove('hidden'); if(id==='createGroupModal') renderGroupPick(); if(id==='accountModal'){ renderStatusPicker(); renderFontPicker(); } }
function closeModal(id){ $(id).classList.add('hidden'); }
document.querySelectorAll('.modal').forEach(m=>m.addEventListener('click', e=>{ if(e.target===m) m.classList.add('hidden'); }));

async function createServer(){
  const name = $('serverNameInput').value.trim();
  const desc = $('serverDescInput').value.trim();
  if(!name){ toast('اكتب اسم السيرفر أولاً'); return; }
  try{
    const res = await apiPost('/tools/create_server', {name, description: desc});
    if(!res.success){ toast(res.error || 'تعذر إنشاء السيرفر'); return; }
    const s = res.data;
    servers.push({id:s.id, name:s.name, desc:s.description||'', img:s.img||''});
    messagesByChat[s.id]=[];
    renderServersRail(); renderSidebarServers();
    closeModal('createServerModal');
    $('serverNameInput').value=''; $('serverDescInput').value='';
    toast(`نبت السيرفر "${name}" 🌱`);
  }catch(e){ toast('تعذر إنشاء السيرفر — تأكد أن السيرفر يعمل'); }
}
function renderGroupPick(){
  $('groupMembersPick').innerHTML = users.filter(u=>!blockedUsers.has(u.id)).map(u=>`
    <label class="pick-chip" data-id="${u.id}" onclick="togglePick(this)">
      <img src="${u.avatar}" alt=""> ${u.name}
    </label>`).join('');
}
function togglePick(el){ el.classList.toggle('selected'); }
async function createGroup(){
  const name = $('groupNameInput').value.trim();
  if(!name){ toast('اكتب اسم المجموعة'); return; }
  const picks = [...document.querySelectorAll('.pick-chip.selected')].map(e=>e.dataset.id);
  try{
    const res = await apiPost('/tools/create_group', {name, member_ids: picks});
    if(!res.success){ toast(res.error || 'تعذر إنشاء المجموعة'); return; }
    const g = res.data;
    groups.push({id:g.id, name:g.name, members:g.members||['me'], avatar:g.avatar||''});
    messagesByChat[g.id]=[];
    renderGroups(); closeModal('createGroupModal');
    $('groupNameInput').value='';
    toast(`اجتمعت دائرة "${name}" ✿`);
    openGroup(g.id);
  }catch(e){ toast('تعذر إنشاء المجموعة — تأكد أن السيرفر يعمل'); }
}

// ── friend requests (live via API) ──
async function sendFriendRequestFromInput(){
  const q = $('friendSearchInput').value.trim();
  if(!q){ toast('اكتب اسم المستخدم'); return; }
  const found = users.find(u=>u.name.toLowerCase()===q.toLowerCase() || u.nickname===q || u.handle.toLowerCase()===q.toLowerCase());
  if(!found){ toast('لم نجد هذا المستخدم في القرية'); return; }
  if(found.isFriend){ toast('أنتم أصدقاء بالفعل'); return; }
  try{
    const res = await apiPost('/tools/send_friend_request', {to_user_id: found.id});
    if(!res.success){ toast(res.error || 'تعذر الإرسال'); return; }
    toast(res.data?.already_pending ? `طلبك إلى ${found.name} معلق بالفعل` : `طار الطائر إلى ${found.name} 🕊`);
  }catch(e){ toast('تعذر الإرسال — تأكد أن السيرفر يعمل'); }
  $('friendSearchResults').innerHTML = `<div class="mini-result"><img src="${found.avatar}"><div><strong>${esc(found.name)}</strong><br><span class="muted">أُرسل ✦</span></div></div>`;
}
async function acceptRequest(id){
  const r = friendRequests.find(x=>x.id===id); if(!r) return;
  try{
    const res = await apiPost('/tools/accept_friend_request', {request_id: id});
    if(!res.success){ toast(res.error || 'تعذر القبول'); return; }
    const u = users.find(x=>x.id===r.from); if(u) u.isFriend=true;
    if(!dmConversations.includes(r.from)) dmConversations.push(r.from);
    friendRequests = friendRequests.filter(x=>x.id!==id);
    renderRequests(); renderFriends(); renderDMs();
    toast(`صار ${u?u.name:''} صديقاً 🌿`);
  }catch(e){ toast('تعذر القبول — تأكد أن السيرفر يعمل'); }
}
async function declineRequest(id){
  try{
    const res = await apiPost('/tools/decline_friend_request', {request_id: id});
    if(!res.success){ toast(res.error || 'تعذر الرفض'); return; }
  }catch(e){ toast('تعذر الرفض — تأكد أن السيرفر يعمل'); return; }
  friendRequests = friendRequests.filter(x=>x.id!==id);
  renderRequests(); toast('رُفض الطلب بلطف');
}

// ── account ──
function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = error => reject(error);
  });
}
async function updateBannerPreview(e){
  const f = e.target.files[0]; if(!f) return;
  const b64 = await toBase64(f);
  try {
    const res = await apiPost('/tools/update_profile_banner', { banner_url: b64 });
    if (res.success) {
      myUser.banner = b64;
      $('bannerPreview').style.backgroundImage = `url(${b64})`;
      $('rightBanner').src = b64;
      toast('تم تحديث الغلاف ✨');
    } else {
      toast(res.error || 'تعذر تحديث الغلاف');
    }
  } catch(err) { toast('تعذر الاتصال بالسيرفر'); }
}
async function updateAvatarPreview(e){
  const f = e.target.files[0]; if(!f) return;
  const b64 = await toBase64(f);
  try {
    const res = await apiPost('/tools/update_profile_avatar', { avatar_url: b64 });
    if (res.success) {
      myUser.avatar = b64;
      $('accountAvatarPreview').src = b64;
      $('railAvatar').src = b64; 
      $('sidebarAvatar').src = b64;
      toast('تم تحديث الصورة ✨');
    } else {
      toast(res.error || 'تعذر تحديث الصورة');
    }
  } catch(err) { toast('تعذر الاتصال بالسيرفر'); }
}
const statusOptions = [
  {value:'🌿 متاحة', emoji:'🌿', label:'متاحة'},
  {value:'🍵 تحتسي الشاي', emoji:'🍵', label:'الشاي'},
  {value:'🎨 ترسم الآن', emoji:'🎨', label:'ترسم'},
  {value:'🌙 مشغولة قليلاً', emoji:'🌙', label:'مشغولة'},
  {value:'💤 نائمة', emoji:'💤', label:'نائمة'},
];
const fontOptions = [
  {value:"'Cairo', 'Noto Sans Arabic', sans-serif", name:'Cairo', preview:'العربية / English'},
  {value:"'Tajawal', 'Noto Sans Arabic', sans-serif", name:'Tajawal', preview:'العربية / English'},
  {value:"'Readex Pro', 'Noto Sans Arabic', sans-serif", name:'Readex Pro', preview:'العربية / English'},
  {value:"'Almarai', 'Noto Sans Arabic', sans-serif", name:'Almarai', preview:'العربية / English'},
  {value:"'Amiri', 'Outfit', serif", name:'Amiri', preview:'العربية / English'},
  {value:"'Outfit', 'Noto Sans Arabic', sans-serif", name:'Outfit', preview:'العربية / English'},
  {value:"'Noto Sans Arabic', 'Outfit', sans-serif", name:'Noto Arabic', preview:'العربية / English'},
];
let selectedStatus = '🌿 متاحة';
let selectedFont = "'Outfit', 'Noto Sans Arabic', sans-serif";
function renderStatusPicker(){
  const current = $('accStatus').value;
  selectedStatus = current;
  $('statusPicker').innerHTML = statusOptions.map(s=>`
    <button class="status-option ${s.value===current?'selected':''}" data-value="${s.value}" onclick="selectStatus('${s.value}')">
      <span class="status-emoji">${s.emoji}</span>
      <span>${s.label}</span>
    </button>`).join('');
}
function selectStatus(val){
  selectedStatus = val;
  $('accStatus').value = val;
  document.querySelectorAll('.status-option').forEach(b=>b.classList.toggle('selected', b.dataset.value===val));
}
function renderFontPicker(){
  const current = $('accFont').value;
  selectedFont = current;
  $('fontPicker').innerHTML = fontOptions.map(f=>`
    <button class="font-option ${f.value===current?'selected':''}" data-value="${f.value}" onclick="selectFont(this)" style="font-family:${f.value}">
      <div>${f.name}</div>
      <div class="font-preview">${f.preview}</div>
    </button>`).join('');
}
function selectFont(btn){
  const val = btn.dataset.value;
  selectedFont = val;
  $('accFont').value = val;
  document.querySelectorAll('.font-option').forEach(b=>b.classList.toggle('selected', b===btn));
}
function applyFontTheme(fontFamily){
  document.querySelectorAll('.profile-font').forEach(el=> el.style.fontFamily = fontFamily);
}
async function saveAccount(){
  const name = $('accName').value.trim();
  const nickname = $('accNickname').value.trim();
  const bio = $('accBio').value.trim();
  try{
    if(name && name!==myUser.name){
      const r = await apiPost('/tools/update_profile_name', {name});
      if(r.success) myUser.name = r.data.name;
      else toast(r.error || 'تعذر حفظ الاسم');
    }
    if(nickname && nickname!==myUser.nickname){
      const r = await apiPost('/tools/update_profile_nickname', {nickname});
      if(r.success) myUser.nickname = r.data.nickname;
    }
    const rb = await apiPost('/tools/update_profile_bio', {bio});
    if(rb.success) myUser.bio = rb.data.bio;
    const rs = await apiPost('/tools/update_profile_status', {status: selectedStatus});
    if(rs.success){ myUser.status = rs.data.status; myUser.statusText = rs.data.status; }
  }catch(e){ toast('تعذر الحفظ — تأكد أن السيرفر يعمل'); }
  myUser.fontTheme = selectedFont;
  $('sidebarName').textContent = myUser.name;
  $('sidebarStatusText').textContent = myUser.status;
  applyFontTheme(myUser.fontTheme);
  localStorage.setItem('fontTheme', myUser.fontTheme);
  closeModal('accountModal');
  toast('حُفظت بذورك ✨');
  renderMessages();
}

// ── user actions ──
function openUserActions(userId){
  if(!userId){
    if(currentChat.type==='dm') userId = currentChat.id;
    else { const g=groups.find(x=>x.id===currentChat.id); userId = g?g.members[0]:users[0]?.id; }
  }
  if(userId==='me'){ toast('هذا أنت! 🌸'); return; }
  const u = users.find(x=>x.id===userId); if(!u) return;
  selectedUserForAction = u;
  $('actionAvatar').src = u.avatar;
  $('actionName').textContent = u.name + (u.nickname && u.nickname!==u.name ? ` (${u.nickname})` : '');
  $('actionHandle').textContent = u.handle + (mutedUsers.has(u.id)?' • مكتوم':'') + (blockedUsers.has(u.id)?' • محظور':'');
  openModal('userActionModal');
}
function openNicknameModal(){
  if(!selectedUserForAction){ toast('اختر عضواً أولاً'); return; }
  $('nicknameInput').value = selectedUserForAction.nickname===selectedUserForAction.name ? '' : (selectedUserForAction.nickname||'');
  closeModal('userActionModal');
  openModal('nicknameModal');
}
const setNicknamePrompt = openNicknameModal;
function saveNickname(){
  if(!selectedUserForAction) return;
  const nick = $('nicknameInput').value.trim();
  selectedUserForAction.nickname = nick || selectedUserForAction.name;
  toast(`حُفظ اللقب: ${selectedUserForAction.nickname}`);
  closeModal('nicknameModal');
  renderFriends(); renderDMs(); renderMembers();
  if(currentChat.type==='dm' && currentChat.id===selectedUserForAction.id) updateHeaderForChat();
}
async function muteUserAction(){
  if(!selectedUserForAction) return;
  const id = selectedUserForAction.id;
  try{
    if(mutedUsers.has(id)){
      const res = await apiPost('/tools/unmute_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر إلغاء الكتم'); return; }
      mutedUsers.delete(id); toast(`أُلغي كتم ${selectedUserForAction.name}`);
    } else {
      const res = await apiPost('/tools/mute_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر الكتم'); return; }
      mutedUsers.add(id); toast(`كُتم ${selectedUserForAction.name} 🔇`);
    }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  renderFriends(); renderDMs(); renderMembers(); updateHeaderForChat();
  closeModal('userActionModal');
}
async function blockUserAction(){
  if(!selectedUserForAction) return;
  const id = selectedUserForAction.id;
  try{
    if(blockedUsers.has(id)){
      const res = await apiPost('/tools/unblock_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر إلغاء الحظر'); return; }
      blockedUsers.delete(id); toast(`أُلغي حظر ${selectedUserForAction.name}`);
    } else {
      const res = await apiPost('/tools/block_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر الحظر'); return; }
      blockedUsers.add(id);
      mutedUsers.delete(id);
      toast(`حُظر ${selectedUserForAction.name} ⛔`);
      if(currentChat.type==='dm' && currentChat.id===id){
        currentChat = groups.length ? {type:'group', id:groups[0].id} : {type:'group', id:null};
        updateHeaderForChat(); renderMessages();
      }
    }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  renderFriends(); renderDMs(); renderRequests();
  closeModal('userActionModal');
}
async function unfriendAction(){
  if(!selectedUserForAction) return;
  if(!selectedUserForAction.isFriend){ toast('ليس صديقاً'); return; }
  try{
    const res = await apiPost('/tools/remove_friend', {user_id: selectedUserForAction.id});
    if(!res.success){ toast(res.error || 'تعذر الإزالة'); return; }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  selectedUserForAction.isFriend = false;
  dmConversations = dmConversations.filter(x=>x!==selectedUserForAction.id);
  toast(`ورقت ${selectedUserForAction.name} من دفتر الأصدقاء 🍂`);
  renderFriends(); renderDMs();
  closeModal('userActionModal');
}

function toggleRightPanel(){ $('rightPanel').classList.toggle('hidden'); }

// ── context menu ──
function showContextMenu(e, type, id){
  e.preventDefault();
  const menu = $('contextMenu');
  const head = $('ctxHead');
  const list = $('ctxList');
  let items = [];
  if(type==='group'){
    const g = groups.find(x=>x.id===id);
    head.textContent = g?g.name:'';
    items = [
      {label:'فتح المجموعة', icon:'💬', action:()=>{ openGroup(id); hideContextMenu(); }},
      {label:'مغادرة بهدوء', icon:'🍂', action:()=>{ leaveGroupById(id); hideContextMenu(); }, danger:true},
      {label:'نسخ الاسم', icon:'📋', action:()=>{ navigator.clipboard?.writeText(g?g.name:''); toast('نُسخ الاسم'); hideContextMenu(); }},
    ];
  } else if(type==='server'){
    const s = servers.find(x=>x.id===id);
    head.textContent = s?s.name:'';
    items = [
      {label:'فتح السيرفر', icon:'💬', action:()=>{ switchServer(id); hideContextMenu(); }},
      {label:'مغادرة بهدوء', icon:'🍂', action:()=>{ leaveServerById(id); hideContextMenu(); }, danger:true},
      {label:'نسخ الاسم', icon:'📋', action:()=>{ navigator.clipboard?.writeText(s?s.name:''); toast('نُسخ الاسم'); hideContextMenu(); }},
    ];
  } else if(type==='dm'){
    const u = users.find(x=>x.id===id);
    head.textContent = u?u.name:'';
    items = [
      {label:'فتح المحادثة', icon:'💬', action:()=>{ openDM(id); hideContextMenu(); }},
      {label:mutedUsers.has(id)?'إلغاء الكتم':'كتم', icon:'🔇', action:()=>{ muteUserById(id); hideContextMenu(); }},
      {label:blockedUsers.has(id)?'إلغاء الحظر':'حظر', icon:'⛔', action:()=>{ blockUserById(id); hideContextMenu(); }, danger:true},
      {label:'نسخ الاسم', icon:'📋', action:()=>{ navigator.clipboard?.writeText(u?u.name:''); toast('نُسخ الاسم'); hideContextMenu(); }},
    ];
  } else if(type==='friend'){
    const u = users.find(x=>x.id===id);
    head.textContent = u?u.name:'';
    items = [
      {label:'دردشة', icon:'🍃', action:()=>{ openDM(id); hideContextMenu(); }},
      {label:'إعطاء لقب', icon:'🏷️', action:()=>{ openUserActions(id); openNicknameModal(); hideContextMenu(); }},
      {label:mutedUsers.has(id)?'إلغاء الكتم':'كتم', icon:'🔇', action:()=>{ muteUserById(id); hideContextMenu(); }},
      {label:blockedUsers.has(id)?'إلغاء الحظر':'حظر', icon:'⛔', action:()=>{ blockUserById(id); hideContextMenu(); }, danger:true},
      {label:'إزالة الصداقة', icon:'🍂', action:()=>{ unfriendById(id); hideContextMenu(); }, danger:true},
    ];
  } else if(type==='member'){
    const u = users.find(x=>x.id===id) || (id==='me' ? myUser : null);
    head.textContent = u ? u.name : id;
    if(id === 'me'){
      items = [
        {label:'ملفي الشخصي', icon:'🌸', action:()=>{ openModal('accountModal'); hideContextMenu(); }},
      ];
    } else {
      items = [
        {label:'محادثة خاصة 🍃', icon:'💬', action:()=>{ openDM(id); hideContextMenu(); }},
        {label:'خيارات العضو', icon:'⋯', action:()=>{ openUserActions(id); hideContextMenu(); }},
        {label:'إعطاء لقب', icon:'🏷️', action:()=>{ openUserActions(id); openNicknameModal(); hideContextMenu(); }},
        {label:mutedUsers.has(id)?'إلغاء الكتم':'كتم', icon:'🔇', action:()=>{ muteUserById(id); hideContextMenu(); }},
        {label:blockedUsers.has(id)?'إلغاء الحظر':'حظر', icon:'⛔', action:()=>{ blockUserById(id); hideContextMenu(); }, danger:true},
      ];
    }
  } else if(type==='request'){
    const r = friendRequests.find(x=>x.id===id);
    head.textContent = r?r.name:'';
    items = [
      {label:'قبول', icon:'✓', action:()=>{ acceptRequest(id); hideContextMenu(); }},
      {label:'رفض', icon:'✕', action:()=>{ declineRequest(id); hideContextMenu(); }, danger:true},
    ];
  }
  list.innerHTML = items.map(it=>`<button class="ctx-item ${it.danger?'danger':''}" data-label="${it.label}"><span class="ctx-icon">${it.icon}</span>${it.label}</button>`).join('');
  list.querySelectorAll('.ctx-item').forEach((btn, i)=>{
    btn.onclick = ()=>{ items[i].action(); };
  });
  menu.classList.remove('hidden');
  const x = Math.min(e.clientX, window.innerWidth - 260);
  const y = Math.min(e.clientY, window.innerHeight - (items.length*48 + 60));
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
}
function hideContextMenu(){ $('contextMenu').classList.add('hidden'); }
async function muteUserById(id){
  try{
    if(mutedUsers.has(id)){
      const res = await apiPost('/tools/unmute_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر إلغاء الكتم'); return; }
      mutedUsers.delete(id); toast(`أُلغي كتم ${users.find(x=>x.id===id)?.name}`);
    } else {
      const res = await apiPost('/tools/mute_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر الكتم'); return; }
      mutedUsers.add(id); toast(`كُتم ${users.find(x=>x.id===id)?.name} 🔇`);
    }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  renderFriends(); renderDMs(); renderMembers(); updateHeaderForChat();
}
async function blockUserById(id){
  try{
    if(blockedUsers.has(id)){
      const res = await apiPost('/tools/unblock_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر إلغاء الحظر'); return; }
      blockedUsers.delete(id); toast(`أُلغي حظر ${users.find(x=>x.id===id)?.name}`);
    } else {
      const res = await apiPost('/tools/block_user', {user_id: id});
      if(!res.success){ toast(res.error || 'تعذر الحظر'); return; }
      blockedUsers.add(id);
      mutedUsers.delete(id);
      toast(`حُظر ${users.find(x=>x.id===id)?.name} ⛔`);
      if(currentChat.type==='dm' && currentChat.id===id){
        currentChat = groups.length ? {type:'group', id:groups[0].id} : {type:'group', id:null};
        updateHeaderForChat(); renderMessages();
      }
    }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  renderFriends(); renderDMs(); renderRequests();
}
async function unfriendById(id){
  const u = users.find(x=>x.id===id);
  if(!u || !u.isFriend){ toast('ليس صديقاً'); return; }
  try{
    const res = await apiPost('/tools/remove_friend', {user_id: id});
    if(!res.success){ toast(res.error || 'تعذر الإزالة'); return; }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  u.isFriend = false;
  dmConversations = dmConversations.filter(x=>x!==id);
  toast(`ورقت ${u.name} من دفتر الأصدقاء 🍂`);
  renderFriends(); renderDMs();
}
async function leaveGroupById(id){
  const g = groups.find(x=>x.id===id);
  if(!g) return;
  try{
    const res = await apiPost('/tools/leave_group', {group_id: id});
    if(!res.success){ toast(res.error || 'تعذر المغادرة'); return; }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  g.members = g.members.filter(m=>m!=='me');
  if(!g.members.length){ groups = groups.filter(x=>x.id!==id); delete messagesByChat[id]; }
  toast('غادرت المجموعة بهدوء 🍂');
  if(currentChat.type==='group' && currentChat.id===id){
    currentChat = groups.length ? {type:'group', id: groups[0].id} : {type:'group', id:null};
    updateHeaderForChat(); renderGroups(); renderMembers(); renderMessages(); renderDMs(); renderSidebarServers();
  } else {
    renderGroups(); renderDMs(); renderSidebarServers();
  }
}
async function leaveServerById(id){
  const s = servers.find(x=>x.id===id);
  if(!s) return;
  try{
    const res = await apiPost('/tools/leave_server', {server_id: id});
    if(!res.success){ toast(res.error || 'تعذر المغادرة'); return; }
  }catch(e){ toast('تعذر الاتصال بالسيرفر'); return; }
  servers = servers.filter(x=>x.id!==id);
  delete messagesByChat[id];
  toast('غادرت السيرفر بهدوء 🍂');
  if(currentChat.type==='server' && currentChat.id===id){
    currentChat = groups.length ? {type:'group', id: groups[0].id} : {type:'group', id:null};
    updateHeaderForChat(); renderServersRail(); renderSidebarServers(); renderMembers(); renderMessages();
  } else {
    renderServersRail(); renderSidebarServers();
  }
}

document.addEventListener('click', e=>{ if(!e.target.closest('.context-menu')) hideContextMenu(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') hideContextMenu(); });

// friend search inside modal
$('friendSearchInput').addEventListener('input', e=>{
  const q = e.target.value.toLowerCase().trim();
  const box = $('friendSearchResults');
  if(!q){ box.innerHTML=''; return; }
  const res = users.filter(u=>!blockedUsers.has(u.id) &&
    (u.name.toLowerCase().includes(q) || (u.nickname&&u.nickname.toLowerCase().includes(q)) || u.handle.toLowerCase().includes(q))
  ).slice(0,5);
  box.innerHTML = res.map(u=>`
    <div class="mini-result" onclick="pickFriendResult('${u.id}')">
      <img src="${u.avatar}"><div><strong>${u.name}</strong> <span class="muted">${u.handle}</span><br><span class="muted" style="font-size:11px">${u.nickname&&u.nickname!==u.name?u.nickname:''}</span></div>
      <span style="margin-right:auto;font-size:11px;color:${u.isFriend?'var(--ghibli-forest-light)':'var(--ghibli-gold)'}">${u.isFriend?'صديق':'إرسال'}</span>
    </div>`).join('') || '<p class="muted" style="padding:8px;font-size:12px">لا نتائج</p>';
});
function pickFriendResult(id){
  const u = users.find(x=>x.id===id);
  if(u) $('friendSearchInput').value = u.handle;
}

// ── theme ──
function toggleTheme(){
  const isDark = document.body.getAttribute('data-theme')==='dark';
  document.body.setAttribute('data-theme', isDark?'light':'dark');
  localStorage.setItem('theme', isDark?'light':'dark');
  updateThemeIcon();
}
function updateThemeIcon(){
  const isDark = document.body.getAttribute('data-theme')==='dark';
  const svg = document.querySelector('#themeToggle svg');
  if(isDark){
    svg.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  } else {
    svg.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
  }
}
function initTheme(){
  const saved = localStorage.getItem('theme');
  if(saved==='dark') document.body.setAttribute('data-theme','dark');
  updateThemeIcon();
  const font = localStorage.getItem('fontTheme');
  if(font){
    selectedFont = font;
    myUser.fontTheme = font;
    applyFontTheme(font);
  }
}

// ── init (live) ──
spawnLeaves();
initTheme();
(async function init(){
  if(location.protocol === 'file:'){
    toast('افتح الموقع من http://localhost:8000 بدل فتح الملف مباشرة');
  }
  try{
    await loadFromAPI();
  }catch(e){
    if(location.protocol === 'file:')
      toast('هذه نسخة ملف مباشرة — شغّل run_server.py وافتح http://localhost:8000');
    else
      toast('تعذر الاتصال بالسيرفر — شغّل run_server.py أولاً');
  }
  renderAll();
  // Live updates: poll every 2.5s so agent replies appear quickly
  setInterval(refreshFromAPI, 2500);
})();

window.SocietyAPI = { createServer, createGroup, sendFriendRequestFromInput, blockUserAction, muteUserAction, unfriendAction, saveNickname, handleSearch, refreshFromAPI };
