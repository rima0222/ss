function filterRows(){
 const q=document.getElementById('search').value.trim().toLowerCase();
 document.querySelectorAll('#rows tr').forEach(r=>r.hidden=q&&!r.dataset.search.includes(q));
}
async function refreshStats(){
 try{
  const response=await fetch('/api/stats',{cache:'no-store'});
  if(!response.ok)return;
  const data=await response.json();
  for(const key of ['total_users','active_users','online_users','total_limit_gb','total_used','memory_percent']){
   const el=document.getElementById(key);if(el)el.textContent=data[key]??0;
  }
  for(const [name,item] of Object.entries(data.users||{})){
   const used=document.querySelector(`[data-used="${CSS.escape(name)}"]`);
   if(used)used.textContent=item.used;
   const online=document.querySelector(`[data-online="${CSS.escape(name)}"]`);
   if(online){online.textContent=item.online?'● Online':'○ Offline';online.classList.toggle('active',item.online);}
   const days=document.querySelector(`[data-days="${CSS.escape(name)}"]`);
   if(days)days.textContent=`${item.remaining_days} روز`;
   const progress=document.querySelector(`[data-progress="${CSS.escape(name)}"]`);
   if(progress){
    const percent=item.limit_bytes>0?Math.min(100,item.used_bytes/item.limit_bytes*100):0;
    progress.style.width=`${percent}%`;
   }
  }
 }catch(_){}
}
refreshStats();
setInterval(refreshStats,5000);
