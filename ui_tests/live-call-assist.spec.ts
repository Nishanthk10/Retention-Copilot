import {test,expect} from '@playwright/test';
test('ready screen and missing recording state',async({page})=>{
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Start call'})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Replay test call'})).toBeDisabled();
  await expect(page.getByText('No suggestions at the moment')).toBeVisible();
});
test('microphone denied explains how to retry',async({page})=>{
  await page.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError')}});
  await page.goto('/');await page.getByRole('button',{name:'Start call'}).click();
  await expect(page.getByRole('alert')).toContainText('Microphone access is needed');
});
test('live roles, checked cards and end card',async({page,request})=>{
  const roles:string[]=[];
  const response=await request.post('/calls');const {call_id}=await response.json();
  try{
    await page.routeWebSocket('**/ws/events*',ws=>{
      ws.send(JSON.stringify({type:'snapshot',status:'live',turns:[],suggestions:[],summary:{mood:'neutral',mood_trend:'stable'}}));
      const timer=setInterval(()=>ws.send(JSON.stringify({type:'heartbeat'})),1000);
      setTimeout(()=>{for(let i=0;i<4;i++)ws.send(JSON.stringify({type:'suggestion',suggestion:{suggestion_id:String(i),text:'Guidance '+i,lane:i%2?'slow':'fast'}}));},500);
      ws.onClose(()=>clearInterval(timer));
    });
    await page.routeWebSocket('**/ws/audio*',ws=>{ws.onMessage(message=>{if(typeof message!=='string')return;const data=JSON.parse(message);roles.push(data.role);ws.send(JSON.stringify({type:'role_ack',role:data.role}));});});
    await page.goto('/');
    await expect(page.getByRole('button',{name:'Customer',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'Sales Rep',exact:true}).click();
    await expect.poll(()=>roles.at(-1)).toBe('rep');
    await page.getByRole('button',{name:'Customer',exact:true}).click();
    await expect.poll(()=>roles.at(-1)).toBe('customer');
    await page.getByRole('button',{name:'Customer',exact:true}).click();
    await expect.poll(()=>roles.at(-1)).toBe('none');
    await expect(page.locator('.tip')).toHaveCount(3);
    await expect(page.getByText('Guidance 0',{exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'End call',exact:true}).click();
    await expect(page.getByRole('dialog')).toContainText('Log saved');
    await expect(page.getByRole('link',{name:'Open log'})).toHaveAttribute('href','/logs/'+call_id);
  }finally{await request.post('/calls/'+call_id+'/end');}
});
test('backend silence banner and manual reconnect',async({page,request})=>{
  const response=await request.post('/calls');const {call_id}=await response.json();let connections=0;
  try{
    await page.routeWebSocket('**/ws/events*',ws=>{
      connections++;ws.send(JSON.stringify({type:'snapshot',status:'live',turns:[],suggestions:[],summary:{mood:'unknown'}}));
    });
    await page.routeWebSocket('**/ws/audio*',()=>{});
    await page.goto('/');
    await expect(page.getByRole('alert')).toContainText('Copilot is disconnected',{timeout:8000});
    await page.getByRole('button',{name:'Retry connection'}).click();
    await expect.poll(()=>connections).toBeGreaterThan(1);
    await expect(page.getByRole('alert')).toBeHidden();
  }finally{await request.post('/calls/'+call_id+'/end');}
});
