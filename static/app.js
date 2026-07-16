function filterRows(){const q=document.getElementById('search').value.trim().toLowerCase();document.querySelectorAll('#rows tr').forEach(r=>r.hidden=q&&!r.dataset.q.includes(q))}
async function stats(){try{const r=await fetch('/api/stats',{cache:'no-store'}),s=await r.json();for(const [id,v] of Object.entries({'st-users':s.users,'st-active':s.active,'st-quota':Number(s.quota).toFixed(1),'st-used':Number(s.used).toFixed(2),'st-ram':s.memory_percent+'%','st-load':s.load.one}))document.getElementById(id).textContent=v}catch(e){}}
stats();setInterval(stats,15000);
