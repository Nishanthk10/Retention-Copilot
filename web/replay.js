export const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function replayAudio(scenario,socket,setRole,signal){
  const response=await fetch('/recordings/'+encodeURIComponent(scenario)+'/timing.json');
  if(!response.ok)throw Error('Record this scenario before replaying it.');
  const timeline=await response.json();
  for(const item of timeline.utterances){
    if(signal.aborted)return;
    await wait(item.gap_before_s*1000);
    if(signal.aborted)return;
    setRole(item.role);
    const file=await fetch('/recordings/'+encodeURIComponent(scenario)+'/'+encodeURIComponent(item.file));
    if(!file.ok)throw Error('A scenario recording is missing.');
    const buffer=await file.arrayBuffer(),view=new DataView(buffer);
    if(view.getUint32(0,false)!==0x52494646)throw Error('Expected WAV audio.');
    let offset=12,pcm=null;
    while(offset+8<=view.byteLength){
      const size=view.getUint32(offset+4,true),tag=view.getUint32(offset,false);
      if(tag===0x666d7420 && (view.getUint16(offset+8,true)!==1||view.getUint16(offset+10,true)!==1||view.getUint32(offset+12,true)!==16000||view.getUint16(offset+22,true)!==16))throw Error('Recordings must be 16 kHz mono PCM16.');
      if(tag===0x64617461){pcm=buffer.slice(offset+8,offset+8+size);break;}
      offset+=8+size+(size%2);
    }
    if(!pcm)throw Error('WAV has no audio data.');
    for(let i=0;i<pcm.byteLength;i+=3200){
      if(signal.aborted)return;
      if(socket.readyState!==WebSocket.OPEN)throw Error('Replay interrupted. Start a fresh replay for comparable results.');
      while(socket.bufferedAmount>64000){await wait(50);if(signal.aborted)return;}
      socket.send(pcm.slice(i,i+3200));await wait(100);
    }
  }
  setRole('none');
}
