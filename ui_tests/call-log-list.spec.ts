import {test,expect} from '@playwright/test';
// Runs on the seeded :8001 server (tests/fixtures/logs + calls.json); the live-call test uses :8000.
const LIVE='http://127.0.0.1:8000';
const ENDED='11111111-1111-4111-8111-111111111111',RESUMED='22222222-2222-4222-8222-222222222222';
const LOG_ONLY='33333333-3333-4333-8333-333333333333',NO_END='44444444-4444-4444-8444-444444444444';
const row=(page:any,cid:string)=>page.locator('tr.call-row',{hasText:cid});

test('lists fixture calls newest first with counts and status labels',async({page})=>{
  await page.goto('/logs');
  await expect(page.locator('tr.call-row')).toHaveCount(4);
  await expect(page.locator('tr.call-row td:first-child')).toHaveText([LOG_ONLY,RESUMED,ENDED,NO_END]);
  await expect(page.getByRole('columnheader')).toHaveText(['Call ID','Started','Ended','Suggestions shown','Mask/Deny']);
  await expect(row(page,LOG_ONLY).locator('td').nth(2)).toHaveText('Interrupted');
  await expect(row(page,NO_END).locator('td').nth(2)).toHaveText('Ended (time not recorded)');
  await expect(row(page,ENDED).locator('td').nth(2)).not.toHaveText(/Interrupted|In progress|not recorded/);
  await expect(row(page,ENDED).locator('td').nth(3)).toHaveText('2');
  await expect(row(page,ENDED).locator('td').nth(4)).toHaveText('2');
  await expect(row(page,RESUMED).locator('td').nth(4)).toHaveText('0');
  await expect(page.getByRole('link',{name:'All logs'})).toBeHidden();
});
test('no logs -> "No call logs yet"',async({page})=>{
  await page.route('**/api/calls',route=>route.fulfill({json:[]}));
  await page.goto('/logs');
  await expect(page.getByText('No call logs yet')).toBeVisible();
  await expect(page.locator('#calls')).toBeHidden();
  await page.getByRole('link',{name:'Back to call screen'}).click();
  await expect(page).toHaveURL('/');
});
test('load failure -> "Could not load call logs" and Try again recovers',async({page})=>{
  await page.route('**/api/calls',route=>route.fulfill({status:500,json:{detail:'x'}}));
  await page.goto('/logs');
  await expect(page.getByText('Could not load call logs')).toBeVisible();
  await page.unroute('**/api/calls');
  await page.getByRole('button',{name:'Try again'}).click();
  await expect(page.locator('tr.call-row')).toHaveCount(4);
});
test('row click opens that call in the viewer',async({page})=>{
  await page.goto('/logs');
  await row(page,ENDED).locator('td').nth(1).click();
  await expect(page).toHaveURL('/logs/'+ENDED);
  await expect(page.locator('#log-id')).toHaveText(ENDED);
  await expect(page.locator('.log-row').first()).toBeVisible();
});
test('See logs navigates to /logs when no call is live',async({page})=>{
  await page.goto('/');
  await expect(page.locator('#connection')).toHaveText('Ready');
  await page.getByRole('button',{name:'See logs'}).click();
  await expect(page).toHaveURL('/logs');
});
test('See logs during a Live call opens a new tab; call screen unchanged (G-17)',async({page,context,request})=>{
  const {call_id}=await (await request.post(LIVE+'/calls')).json();
  try{
    await page.routeWebSocket('**/ws/events*',ws=>{
      ws.send(JSON.stringify({type:'snapshot',status:'live',turns:[],suggestions:[],summary:{mood:'unknown'}}));
      const timer=setInterval(()=>ws.send(JSON.stringify({type:'heartbeat'})),1000);ws.onClose(()=>clearInterval(timer));
    });
    await page.routeWebSocket('**/ws/audio*',()=>{});
    await page.goto(LIVE+'/');
    await expect(page.locator('#connection')).toHaveText('Live');
    const [tab]=await Promise.all([context.waitForEvent('page'),page.getByRole('button',{name:'See logs'}).click()]);
    await tab.waitForLoadState();
    expect(tab.url()).toBe(LIVE+'/logs');
    await expect(tab.locator('tr.call-row',{hasText:call_id}).locator('td').nth(2)).toHaveText('In progress');
    expect(page.url()).toBe(LIVE+'/');
    await expect(page.locator('#connection')).toHaveText('Live');
    await expect(page.locator('#call-id')).toHaveText(call_id);
    await expect(page.getByRole('button',{name:'End call',exact:true})).toBeVisible();
    await tab.close();
  }finally{await request.post(LIVE+'/calls/'+call_id+'/end');}
});
