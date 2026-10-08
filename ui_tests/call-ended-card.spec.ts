import {test,expect,type Page} from '@playwright/test';
// Runs on the :8000 server. Each test starts a real call; the event socket is mocked so the
// screen goes Live without a microphone.
async function liveCall(page:Page,request:any){
  const {call_id}=await (await request.post('/calls')).json();
  await page.routeWebSocket('**/ws/events*',ws=>{
    ws.send(JSON.stringify({type:'snapshot',status:'live',turns:[],suggestions:[],summary:{mood:'unknown'}}));
    const timer=setInterval(()=>ws.send(JSON.stringify({type:'heartbeat'})),1000);ws.onClose(()=>clearInterval(timer));
  });
  await page.routeWebSocket('**/ws/audio*',()=>{});
  await page.goto('/');
  await expect(page.locator('#connection')).toHaveText('Live');
  return call_id as string;
}
test('end call -> card -> Open log shows the timeline',async({page,request})=>{
  const cid=await liveCall(page,request);
  await page.getByRole('button',{name:'End call',exact:true}).click();
  const card=page.getByRole('dialog');
  await expect(card).toContainText('Log saved');
  await expect(card).toContainText(cid);
  await expect(page.getByRole('link',{name:'Open log'})).toHaveAttribute('href','/logs/'+cid);
  await page.getByRole('link',{name:'Open log'}).click();
  await expect(page).toHaveURL('/logs/'+cid);
  await expect(page.locator('.timeline .log-row').first()).toBeVisible();
  await expect(page.locator('.log-row summary',{hasText:'call ended'})).toHaveCount(1);
});
test('New call resets to Ready',async({page,request})=>{
  await liveCall(page,request);
  await page.getByRole('button',{name:'End call',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Log saved');
  await page.getByRole('button',{name:'New call'}).click();
  await expect(page.locator('#connection')).toHaveText('Ready');
  await expect(page.getByRole('button',{name:'Start call'})).toBeEnabled();
  await expect(page.getByRole('dialog')).toBeHidden();
});
test('log write failure shows call ID and no Open log (G-13)',async({page,request})=>{
  const cid=await liveCall(page,request);
  try{
    await page.route('**/calls/*/end',route=>route.fulfill({json:{call_id:cid,log_saved:false}}));
    await page.getByRole('button',{name:'End call',exact:true}).click();
    await expect(page.getByRole('dialog')).toContainText('Log could not be saved');
    await expect(page.getByRole('dialog')).toContainText(cid);
    await expect(page.getByRole('link',{name:'Open log'})).toBeHidden();
  }finally{await request.post('/calls/'+cid+'/end');}
});
