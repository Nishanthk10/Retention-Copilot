import {replayAudio,wait} from './replay.js';
const $=id=>document.getElementById(id);
let callId=null,audio=null,events=null,role='none',media=null,context=null,processor=null;
let suggestions=[],lastBeat=Date.now(),started=0,replaying=false,ending=false,callOver=false,connecting=false,reconnectTimer=null,abortReplay=null,scenarios=[],seenTurns=new Set(),active=true;
const base=(location.protocol==='https:'?'wss://':'ws://')+location.host;
const text=(id,value)=>$(id).textContent=value;
function banner(message){text('banner-text',message);$('banner').hidden=!message;}
async function api(path,method='GET'){const r=await fetch(path,{method});const data=await r.json();if(!r.ok)throw Error(data.detail||'Connection failed');return data;}
function controls(){
  $('start').hidden=!!callId;$('end').hidden=!callId;
  for(const name of ['rep','customer']){$(name).disabled=!callId||replaying||ending||!audio||audio.readyState!==1;$(name).setAttribute('aria-pressed',String(role===name));}
  $('replay').disabled=!!callId||!scenarios.find(s=>s.id===$('scenario').value)?.recorded;
  $('scenario').disabled=!!callId;
}
function showRole(next){
  role=next;text('role-label',role==='none'?'Choose who is speaking':'Speaking as: '+(role==='rep'?'Sales Rep':'Customer'));controls();
}
function switchRole(next){
  if(!audio||audio.readyState!==1)return;
  if(processor&&!replaying)processor.port.postMessage({type:'role',role:next});
  else {audio.send(JSON.stringify({type:'role',role:next}));showRole(next);}
}
function addTurn(turn){
  if(seenTurns.has(turn.turn_no))return;seenTurns.add(turn.turn_no);
  if($('transcript').querySelector('.transcript-empty'))$('transcript').replaceChildren();
  const el=document.createElement('div');el.className='turn '+turn.speaker;
  const who=document.createElement('strong');who.textContent=(turn.speaker==='rep'?'Sales Rep':'Customer')+' · '+turn.turn_no;
  const content=document.createElement('p');content.textContent=turn.text;el.append(who,content);$('transcript').append(el);$('transcript').scrollTop=$('transcript').scrollHeight;
}
function renderSuggestions(){
  $('suggestions').replaceChildren();$('empty').hidden=suggestions.length>0;
  [...suggestions].reverse().forEach(s=>{
    const card=document.createElement('article');card.className='tip '+s.lane;card.dataset.id=s.suggestion_id;
    const lane=document.createElement('span');lane.className='lane';lane.textContent=s.lane==='fast'?'Quick tip':'Suggested approach';
    const p=document.createElement('p');p.textContent=s.text;card.append(lane,p);$('suggestions').append(card);
  });
}
function ended(data){
  if(!callId)return;
  ending=true;callOver=true;abortReplay?.abort();role='none';stopMic();clearTimeout(reconnectTimer);
  audio?.close();events?.close();text('connection','Ended');text('save-state',data.log_saved?'Log saved':'Log could not be saved');
  text('ended-id',callId);$('open-log').href='/logs/'+callId;$('open-log').hidden=!data.log_saved;
  if(!$('ended').open)$('ended').showModal();controls();localStorage.removeItem('retention-call');
}
function receive(event){
  lastBeat=Date.now();const e=JSON.parse(event.data);
  if(e.type==='snapshot'){
    if(e.status==='ended'){ended({log_saved:true});return;}
    e.turns.forEach(addTurn);suggestions=e.suggestions.slice(-3);renderSuggestions();
    if(e.summary)showSummary(e.summary);
  }
  if(e.type==='transcript')addTurn(e.turn);
  if(e.type==='suggestion'){
    if(!suggestions.some(s=>s.suggestion_id===e.suggestion.suggestion_id)){
      const oldest=$('suggestions').lastElementChild;if(suggestions.length===3)oldest?.classList.add('faded');
      suggestions=[...suggestions,e.suggestion].slice(-3);setTimeout(renderSuggestions,200);
    }
  }
  if(e.type==='summary')showSummary(e.summary);
  if(e.type==='status')text('guidance-status',e.message);
  if(e.type==='call_ended')ended(e);
  if(e.type==='reconnect_required'){events?.close();scheduleReconnect();}
}
function showSummary(s){$('mood').hidden=s.mood==='unknown';text('mood','Customer mood · '+s.mood+' / '+s.mood_trend);}
function scheduleReconnect(){
  if(!callId||ending||replaying||reconnectTimer)return;
  stopMic();showRole('none');reconnectTimer=setTimeout(()=>{reconnectTimer=null;connect(true).catch(scheduleReconnect);},1800);
}
async function openSocket(path){
  const ws=new WebSocket(base+path+'?call_id='+callId);
  return await new Promise((resolve,reject)=>{ws.onopen=()=>resolve(ws);ws.onerror=()=>reject(Error('Could not connect'));});
}
async function connect(resume=false){
  if(connecting||ending)return;
  connecting=true;
  if(audio){audio.onclose=null;audio.close();}if(events){events.onclose=null;events.close();}
  try{
    // Install handler before opening to avoid losing the initial snapshot.
    events=new WebSocket(base+'/ws/events?call_id='+callId);events.onmessage=receive;
    await new Promise((resolve,reject)=>{events.onopen=resolve;events.onerror=reject;});
    audio=await openSocket('/ws/audio');
    audio.onclose=scheduleReconnect;events.onclose=scheduleReconnect;
    lastBeat=Date.now();banner('');showRole('none');text('connection','Live');$('connection').classList.add('live');
    if(resume)text('guidance-status','Reconnected — some speech may have been missed. Choose who is speaking.');
    controls();
  }finally{connecting=false;}
}
async function getMic(){
  media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true},video:false});
  context=new AudioContext();await context.audioWorklet.addModule('/static/pcm-worklet.js');
  processor=new AudioWorkletNode(context,'pcm-processor');const source=context.createMediaStreamSource(media);source.connect(processor);
  const mute=context.createGain();mute.gain.value=0;processor.connect(mute).connect(context.destination);
  processor.port.onmessage=e=>{
    if(audio?.readyState!==1||ending)return;
    if(e.data.type==='role'){audio.send(JSON.stringify({type:'role',role:e.data.role}));showRole(e.data.role);return;}
    if(e.data.type==='pcm'){
      if(audio.bufferedAmount>64000){switchRole('none');banner('Audio connection is falling behind. Pause and retry the connection.');}
      else audio.send(e.data.buffer);
    }
  };
}
function stopMic(){media?.getTracks().forEach(t=>t.stop());media=null;processor?.disconnect();processor=null;context?.close();context=null;}
async function start(replay=false){
  $('start').disabled=true;banner('');ending=false;
  try{
    if(!replay)await getMic();
    const data=await api('/calls','POST');callId=data.call_id;localStorage.setItem('retention-call',callId);started=Date.now();
    text('call-id',callId);await connect();
  }catch(e){
    if(!callId)stopMic();
    banner(e.name==='NotAllowedError'?'Microphone access is needed to start a call. Try again.':e.message||'Could not start the call.');
  }finally{$('start').disabled=false;controls();}
}
$('start').onclick=()=>start();
for(const name of ['rep','customer'])$(name).onclick=async()=>{
  if(!media&&!replaying){try{await getMic();}catch{banner('Microphone access is needed. Try again.');return;}}
  switchRole(role===name?'none':name);
};
async function endCall(){
  if(!callId||ending)return;
  ending=true;abortReplay?.abort();showRole('none');stopMic();controls();
  $('ended').showModal();text('save-state','Saving log…');text('ended-id',callId);$('open-log').hidden=true;
  try{const data=await api('/calls/'+callId+'/end','POST');ending=false;ended(data);}
  catch(e){ending=false;banner('Could not end the call. Retry when the connection returns.');text('save-state','Call could not be ended');controls();}
}
$('end').onclick=endCall;
// G-17: while a call is in progress (live, reconnecting or replaying), keep this tab on the call.
$('see-logs').onclick=()=>{if(callId&&!callOver)window.open('/logs','_blank','noopener');else location.href='/logs';};
$('new').onclick=()=>{if(!ending&&callId){$('ended').close();return;}location.reload();};
$('retry').onclick=async()=>{clearTimeout(reconnectTimer);reconnectTimer=null;if(callId)await connect(true).catch(()=>banner('Connection unavailable. Handle the call or call the customer back later.'));else start();};
$('scenario').onchange=controls;
$('replay').onclick=async()=>{
  replaying=true;abortReplay=new AbortController();await start(true);
  if(!callId){replaying=false;controls();return;}
  text('guidance-status','Replaying '+$('scenario').value);controls();
  try{
    await replayAudio($('scenario').value,audio,switchRole,abortReplay.signal);
    if(!abortReplay.signal.aborted){
      // Wait for flush acknowledgement, then bounded grace for last-turn guidance.
      await wait(3000);text('guidance-status','Replay audio finished. Review guidance, then end the call.');
    }
  }catch(e){banner(e.message);}
};
setInterval(()=>{
  if(callId&&!ending){
    if(Date.now()-lastBeat>5000){banner('Copilot is disconnected. Handle the call or call the customer back later.');text('connection','Reconnecting');scheduleReconnect();}
    const seconds=Math.floor((Date.now()-started)/1000);text('timer',String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0'));
  }
},500);
async function boot(){
  try{
    const h=await api('/health');
    text('mode',h.test_mode?'TEST MODE · speech recognition disabled':h.variant!=='full'?'EVALUATION · '+h.variant:'');
    if(!h.ready){text('connection',h.error?'Setup needed':'Starting up…');if(h.error)banner('Local models could not load. Check setup instructions and restart the app.');setTimeout(boot,2000);return;}
    text('connection','Ready');$('start').disabled=false;
    scenarios=await api('/api/scenarios');
    scenarios.forEach(s=>{const o=document.createElement('option');o.value=s.id;o.textContent=s.id+' · '+s.title+(s.recorded?'':' (not recorded)');$('scenario').append(o);});
    if(!scenarios.some(s=>s.recorded))text('recording-note','Five scripts are included. Record their utterances to enable audio replay.');
    const existing=await api('/api/active-call');
    if(existing){callId=existing.call_id;started=Date.now();text('call-id',callId);await connect(true);}
    controls();
  }catch{banner('Could not reach Copilot. Check the local server.');setTimeout(boot,2000);}
}
boot();
