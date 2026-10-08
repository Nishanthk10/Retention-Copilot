"""Bounded PCM windows with VAD; role changes flush the old speaker's samples.
Whisper uses batch inference over incremental windows, not token streaming.
"""
import asyncio, time
import numpy as np

class Transcriber:
    def __init__(self, offline=False):
        from faster_whisper import WhisperModel
        self.model=WhisperModel('small.en',device='cpu',compute_type='int8',local_files_only=offline)
        self.lock=asyncio.Lock()
    async def transcribe(self, pcm):
        async with self.lock:
            def run():
                audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
                if len(audio)<1600: return ''
                segments,_=self.model.transcribe(audio,language='en',vad_filter=True,condition_on_previous_text=False)
                return ' '.join(s.text.strip() for s in segments)
            return await asyncio.to_thread(run)

class AudioTurns:
    def __init__(self, transcriber, on_close, on_customer_start):
        self.transcriber=transcriber; self.on_close=on_close; self.on_customer_start=on_customer_start
        self.role='none'; self.buffer=bytearray(); self.parts=[]; self.start=0
    async def flush(self):
        if self.buffer:
            audio=bytes(self.buffer); self.buffer.clear()
            if not self.transcriber: raise RuntimeError('Speech recognition unavailable')
            text=await self.transcriber.transcribe(audio)
            if text: self.parts.append(text)
    async def switch(self,role):
        if role not in {'rep','customer','none'}: raise ValueError('Unknown speaker role')
        if role==self.role: return
        await self.flush()
        if self.parts: await self.on_close(self.role,' '.join(self.parts),self.start,time.time())
        self.parts=[]; self.role=role; self.start=time.time()
        if role=='customer': await self.on_customer_start()
    async def feed(self,pcm):
        if self.role=='none': return
        if len(pcm)%2 or len(pcm)>64000: raise ValueError('Expected bounded 16 kHz PCM16 frames')
        self.buffer.extend(pcm)
        if len(self.buffer)>=128000: await self.flush()
