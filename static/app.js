function filterRows(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  document.querySelectorAll('#rows tr').forEach(r=>r.hidden=q&&!r.dataset.q.includes(q));
}

function bytes(v){
  v=Number(v)||0;
  const units=['B','KB','MB','GB','TB'];
  let i=0;
  while(v>=1024&&i<units.length-1){v/=1024;i++;}
  return `${v.toFixed(i?2:0)} ${units[i]}`;
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
      const rx=document.querySelector(`[data-rx="${CSS.escape(name)}"]`);
      const tx=document.querySelector(`[data-tx="${CSS.escape(name)}"]`);
      if(rx) rx.textContent='↓ '+bytes(s.rx_bytes);
      if(tx) tx.textContent='↑ '+bytes(s.tx_bytes);
    }
  }catch(e){}
}

stats(); live();
setInterval(stats,15000);
setInterval(live,10000);
