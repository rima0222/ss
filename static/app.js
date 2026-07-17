const formatBytes = value => {
  let n=Number(value||0); const units=["B","KB","MB","GB","TB"];
  for(const unit of units){if(n<1024||unit==="TB")return `${n.toFixed(2)} ${unit}`;n/=1024;}
};
const postForm=(url,label,confirmText)=>{
  const form=document.createElement("form");form.method="post";form.action=url;
  const csrf=document.createElement("input");csrf.type="hidden";csrf.name="_csrf";csrf.value=window.CSRF;form.append(csrf);
  const button=document.createElement("button");button.className="action";button.textContent=label;
  if(confirmText)form.onsubmit=()=>confirm(confirmText);
  form.append(button);return form;
};
function filterUsers(){
  const q=document.getElementById("search").value.trim().toLowerCase();
  document.querySelectorAll(".user-card").forEach(card=>card.hidden=q&&!card.dataset.username.includes(q));
}
function buildUser(user){
  const node=document.getElementById("user-template").content.firstElementChild.cloneNode(true);
  node.dataset.username=user.username.toLowerCase();
  node.querySelector(".avatar").textContent=user.username[0].toUpperCase();
  node.querySelector(".username").textContent=user.username;
  const endpoints=[];
  if(user.tcp_enabled)endpoints.push(`TCP:${user.tcp_port}`);
  if(user.ws_enabled)endpoints.push("WS");
  node.querySelector(".ports").textContent=endpoints.join(" • ");
  const status=node.querySelector(".status");
  status.textContent=user.paused?"متوقف":user.status==="expired"?"منقضی":"فعال";
  status.className=`status ${user.paused?"paused":"active"}`;
  const online=node.querySelector(".auth-online");
  online.textContent=user.online?`● آنلاین (${user.authenticated_sessions})`:"○ آفلاین";
  online.className=user.online?"auth-online online":"auth-online";
  node.querySelector(".connections").textContent=`Gateway: TCP ${user.tcp_connections} / WS ${user.ws_connections}`;
  node.querySelector(".used").textContent=formatBytes(user.download_bytes);
  node.querySelector(".quota").textContent=user.quota_bytes?formatBytes(user.quota_bytes):"نامحدود";
  node.querySelector(".remaining").textContent=user.remaining;
  node.querySelector(".progress i").style.width=user.quota_bytes?`${Math.min(100,user.download_bytes/user.quota_bytes*100)}%`:"0%";
  const actions=node.querySelector(".actions");
  const config=document.createElement("a");config.className="action";config.href=`/users/${encodeURIComponent(user.username)}/config`;config.textContent="کانفیگ";actions.append(config);
  actions.append(postForm(`/users/${encodeURIComponent(user.username)}/${user.paused?"resume":"pause"}`,user.paused?"فعال":"توقف"));
  actions.append(postForm(`/users/${encodeURIComponent(user.username)}/reset-usage`,"ریست مصرف","مصرف صفر شود؟"));
  actions.append(postForm(`/users/${encodeURIComponent(user.username)}/delete`,"حذف","کاربر کامل حذف شود؟"));
  const edit=node.querySelector(".edit-form");
  edit.action=`/users/${encodeURIComponent(user.username)}/edit`;
  edit.querySelector('[name="quota_gb"]').value=(user.quota_bytes/1073741824).toFixed(2);
  const daysText=user.remaining.match(/\d+/); edit.querySelector('[name="days"]').value=daysText?daysText[0]:0;
  edit.querySelector('[name="tcp_enabled"]').checked=user.tcp_enabled;
  edit.querySelector('[name="ws_enabled"]').checked=user.ws_enabled;
  return node;
}
async function refresh(){
  try{
    const response=await fetch("/api/stats",{cache:"no-store"});const data=await response.json();
    document.getElementById("total_users").textContent=data.total_users;
    document.getElementById("active_users").textContent=data.active_users;
    document.getElementById("online_users").textContent=data.online_users;
    document.getElementById("total_download").textContent=formatBytes(data.total_download_bytes);
    document.getElementById("total_quota").textContent=formatBytes(data.total_quota_bytes);
    const gateway=document.getElementById("gateway");
    gateway.textContent=data.gateway_live?"Gateway آنلاین و حسابداری فعال":"Gateway در دسترس نیست";
    gateway.classList.toggle("active",data.gateway_live);
    const list=document.getElementById("user-list");list.replaceChildren(...data.users.map(buildUser));
    if(!data.users.length)list.innerHTML='<div class="empty">هنوز کاربری ساخته نشده است.</div>';
  }catch(e){document.getElementById("gateway").textContent="خطا در دریافت وضعیت";}
}
refresh();setInterval(refresh,2000);
