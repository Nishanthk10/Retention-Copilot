// One page, two views: /logs (Call Log List) and /logs/{call_id} (Call Log Viewer). Read-only.
const $=id=>document.getElementById(id);
const when=ts=>new Date(ts).toLocaleString();
function ended(call){
  if(call.status==='live')return 'In progress';
  if(call.status==='interrupted')return 'Interrupted';
  return call.ended_at?when(call.ended_at):'Ended (time not recorded)';
}
function list(){
  document.title='Call logs · Retention Copilot';
  $('viewer').hidden=true;$('list-view').hidden=false;$('all-logs').hidden=true;
  const table=$('calls'),body=table.tBodies[0];
  $('list-status').textContent='Loading call logs…';$('list-retry').hidden=true;table.hidden=true;body.replaceChildren();
  fetch('/api/calls').then(async response=>{
    if(!response.ok)throw Error();
    const calls=await response.json();
    if(!calls.length){$('list-status').textContent='No call logs yet';return;}
    $('list-status').textContent=calls.length+(calls.length===1?' call':' calls');
    for(const call of calls){
      const href='/logs/'+encodeURIComponent(call.call_id);
      const row=document.createElement('tr');row.className='call-row '+call.status;row.onclick=()=>{location.href=href;};
      const link=document.createElement('a');link.href=href;link.textContent=call.call_id;
      const cells=[link,call.started_at?when(call.started_at):'—',ended(call),String(call.suggestions_shown),String(call.mask_deny_count)];
      for(const value of cells){const td=document.createElement('td');td.append(value);row.append(td);}
      body.append(row);
    }
    table.hidden=false;
  }).catch(()=>{$('list-status').textContent='Could not load call logs';$('list-retry').hidden=false;});
}
function viewer(){
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
}
$('list-retry').onclick=list;
if(location.pathname.replace(/\/+$/,'')==='/logs')list();else viewer();
