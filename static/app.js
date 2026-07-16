function filterRows(){
 const q=document.getElementById('search').value.trim().toLowerCase();
 document.querySelectorAll('#rows tr').forEach(r=>r.hidden=q&&!r.dataset.search.includes(q));
}
async function refreshStats(){
 try{
  const r=await fetch('/api/stats',{cache:'no-store'});
  if(!r.ok)return;
  const d=await r.json();
  for(const k of ['total_users','active_users','online_users','total_limit_gb','total_used_gb','memory_percent']){
   const el=document.getElementById(k);if(el)el.textContent=d[k]??0;
  }
  for(const [name,item] of Object.entries(d.users||{})){
   const used=document.querySelector(`[data-used="${CSS.escape(name)}"]`);
   if(used)used.textContent=Number(item.used_gb||0).toFixed(3);
   const online=document.querySelector(`[data-online="${CSS.escape(name)}"]`);
   if(online){online.textContent=item.online?'● Online':'○ Offline';online.classList.toggle('active',Boolean(item.online));}
  }
 }catch(_){}
}
refreshStats();setInterval(refreshStats,5000);
