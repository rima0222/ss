function filterRows(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  document.querySelectorAll('#userRows tr').forEach(row=>{
    row.hidden=q && !row.dataset.search.includes(q);
  });
}

async function refreshStats(){
  try{
    const response=await fetch('/api/stats',{cache:'no-store'});
    if(!response.ok) return;
    const data=await response.json();

    for(const key of ['total_users','active_users','online_users','total_limit_gb','total_used_gb','memory_percent']){
      const el=document.getElementById(key);
      if(el) el.textContent=data[key] ?? 0;
    }

    for(const [username,item] of Object.entries(data.users||{})){
      const used=document.querySelector(`[data-used="${CSS.escape(username)}"]`);
      if(used) used.textContent=Number(item.used_gb||0).toFixed(3);

      const ssh=document.querySelector(`[data-ssh-online="${CSS.escape(username)}"]`);
      if(ssh){
        ssh.textContent=(item.ssh_online?'●':'○')+' SSH';
        ssh.classList.toggle('is-online',Boolean(item.ssh_online));
      }

      const xray=document.querySelector(`[data-xray-online="${CSS.escape(username)}"]`);
      if(xray){
        xray.textContent=(item.xray_online?'●':'○')+' Xray';
        xray.classList.toggle('is-online',Boolean(item.xray_online));
      }
    }
  }catch(_){}
}

refreshStats();
setInterval(refreshStats,10000);
