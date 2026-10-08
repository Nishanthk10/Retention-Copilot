const cid=location.pathname.split('/').pop();document.getElementById('log-id').textContent=cid;
fetch('/api/logs/'+encodeURIComponent(cid)).then(async response=>{
  if(!response.ok)throw Error();
  const rows=await response.json();document.getElementById('log-status').textContent=rows.length+' recorded steps';
  let turn=null;
  for(const row of rows){
    if(row.turn_no!==turn){turn=row.turn_no;const h=document.createElement('h3');h.className='turn-label';h.textContent='TURN '+turn;document.getElementById('timeline').append(h);}
    const d=document.createElement('details');d.className='log-row '+(row.permission_outcome||'');
    const s=document.createElement('summary');s.textContent=row.step.replaceAll('_',' ')+' · '+new Date(row.ts).toLocaleTimeString()+(row.permission_outcome?' · '+row.permission_outcome.toUpperCase():'');
    const p=document.createElement('p');p.textContent=row.message||row.reason||row.shown?.text||row.model_reasoning||row.input?.text||'Expand to inspect the recorded step.';
    const pre=document.createElement('pre');pre.textContent=JSON.stringify(row,null,2);d.append(s,p,pre);document.getElementById('timeline').append(d);
  }
}).catch(()=>document.getElementById('log-status').textContent='Log not found for this call');
