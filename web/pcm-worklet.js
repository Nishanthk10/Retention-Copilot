class PCMProcessor extends AudioWorkletProcessor {
  constructor(){
    super();this.buffer=[];this.position=0;this.input=[];this.role='none';
    this.port.onmessage=e=>{
      if(e.data.type!=='role')return;
      this.flush();this.input=[];this.position=0;this.role=e.data.role;
      this.port.postMessage({type:'role',role:this.role});
    };
  }
  flush(){
    if(this.buffer.length&&this.role!=='none'){
      const pcm=new Int16Array(this.buffer);
      this.port.postMessage({type:'pcm',role:this.role,buffer:pcm.buffer},[pcm.buffer]);
    }
    this.buffer=[];
  }
  process(inputs){
    const channel=inputs[0]?.[0];if(!channel||this.role==='none')return true;
    for(const x of channel)this.input.push(x);
    const step=sampleRate/16000;
    while(this.position+1<this.input.length){
      const i=Math.floor(this.position),fraction=this.position-i;
      const x=this.input[i]*(1-fraction)+this.input[i+1]*fraction;
      this.buffer.push(Math.max(-32768,Math.min(32767,Math.round(x*32767))));
      this.position+=step;
      if(this.buffer.length===1600)this.flush();
    }
    const used=Math.floor(this.position);this.input.splice(0,used);this.position-=used;
    return true;
  }
}
registerProcessor('pcm-processor',PCMProcessor);
