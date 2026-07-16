function filterRows(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  document.querySelectorAll('#rows tr').forEach(r=>r.hidden=q&&!r.dataset.q.includes(q));
}


async function stats(){
  try{
    const r=await fetch('/api/stats',{cache:'no-store'}),s=await r.json();
    const values={
      'st-users':s.users,
      'st-online':s.online,
      'st-active':s.active,
      'st-quota':Number(s.quota).toFixed(1),
      'st-used':Number(s.used).toFixed(2),
      'st-ram':s.memory_percent+'%',
      'st-load':s.load.one
    };
    for(const [id,v] of Object.entries(values)){
      const el=document.getElementById(id); if(el) el.textContent=v;
    }
    for(const [name,used] of Object.entries(s.user_usage||{})){
      const el=document.querySelector(`[data-used="${CSS.escape(name)}"]`);
      if(el) el.textContent=Number(used).toFixed(3);
    }
  }catch(e){}
}

async function live(){
  try{
    const r=await fetch('/api/live',{cache:'no-store'}),data=await r.json();
    for(const [name,s] of Object.entries(data.users||{})){
      const state=document.querySelector(`[data-online="${CSS.escape(name)}"]`);
      if(state){
        state.textContent=s.online?'آنلاین':'آفلاین';
        state.classList.toggle('online',!!s.online);
        state.classList.toggle('offline',!s.online);
        const onlineProtocols=Object.entries(s.protocols||{}).filter(([,v])=>v.online).map(([k])=>k);
        state.title=onlineProtocols.length?`Online: ${onlineProtocols.join(', ')}`:'No active connection';
      }
    }
  }catch(e){}
}

stats(); live();
setInterval(stats,15000);
setInterval(live,10000);
