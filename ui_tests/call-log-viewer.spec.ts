import {test,expect,type Page} from '@playwright/test';
// Runs on the seeded :8001 server (tests/fixtures/logs + calls.json).
const ENDED='11111111-1111-4111-8111-111111111111',RESUMED='22222222-2222-4222-8222-222222222222';
test('missing log has explicit return path',async({page})=>{
  await page.goto('/logs/00000000-0000-0000-0000-000000000000');
  await expect(page.getByText('Log not found for this call')).toBeVisible();
  await page.getByRole('link',{name:'Back to call screen'}).click();
  await expect(page).toHaveURL('/');
});
test('mask/deny and resume visible; unsafe HTML stays text',async({page})=>{
  await page.route('**/api/logs/*',route=>route.fulfill({json:[
    {turn_no:2,ts:new Date().toISOString(),step:'permission',permission_outcome:'deny',reason:'Unknown offer_id',input:'<img src=x onerror=alert(1)>'},
    {turn_no:3,ts:new Date().toISOString(),step:'resume',message:'Possible missed turns during restart'}
  ]}));
  await page.goto('/logs/00000000-0000-0000-0000-000000000000');
  await expect(page.locator('.log-row.deny')).toHaveCount(1);
  await page.locator('.log-row').first().locator('summary').click();
  await expect(page.locator('pre').first()).toContainText('<img');
  await expect(page.locator('.timeline img')).toHaveCount(0);
});
test('timeline by turn; expanding a record shows raw JSON; Mask/Deny flagged',async({page})=>{
  await page.goto('/logs/'+ENDED);
  await expect(page.locator('.turn-label')).toHaveText(['TURN 0','TURN 1','TURN 2']);
  await expect(page.locator('.log-row')).toHaveCount(8);
  await expect(page.locator('.log-row.deny')).toHaveCount(1);
  await expect(page.locator('.log-row.mask')).toHaveCount(1);
  const first=page.locator('.log-row').first();
  await expect(first.locator('pre')).toBeHidden();
  await first.locator('summary').click();
  await expect(first.locator('pre')).toContainText('"step": "call_started"');
});
test('restart marker rendered',async({page})=>{
  await page.goto('/logs/'+RESUMED);
  await expect(page.locator('.log-row',{hasText:'Possible missed turns during restart'})).toHaveCount(1);
});
test('unknown call_id shows not-found message',async({page})=>{
  await page.goto('/logs/99999999-9999-4999-8999-999999999999');
  await expect(page.getByText('Log not found for this call')).toBeVisible();
  await expect(page.getByRole('link',{name:'All logs'})).toBeVisible();
});
// The Call Ended Card's Open log links to /logs/{id} (call-ended-card.spec.ts); the list's row
// click lands on the same URL. Compare the rendered structure from both entry points.
async function outline(page:Page){
  await expect(page.locator('.log-row').first()).toBeVisible();
  return page.evaluate(()=>[...document.querySelectorAll('header *, main *')].filter(e=>(e as HTMLElement).offsetParent!==null)
    .map(e=>e.tagName+'#'+e.id+'.'+e.className));
}
test('viewer layout identical from the list and from the card link',async({page})=>{
  await page.goto('/logs');
  await page.locator('tr.call-row',{hasText:ENDED}).click();
  await expect(page).toHaveURL('/logs/'+ENDED);
  const fromList=await outline(page);
  await page.goto('/logs/'+ENDED);
  expect(await outline(page)).toEqual(fromList);
  await expect(page.locator('#list-view')).toBeHidden();
});
test('"All logs" returns to /logs; "Back to call screen" returns to /',async({page})=>{
  await page.goto('/logs/'+ENDED);
  await page.getByRole('link',{name:'All logs'}).click();
  await expect(page).toHaveURL('/logs');
  await page.goto('/logs/'+ENDED);
  await page.getByRole('link',{name:'Back to call screen'}).click();
  await expect(page).toHaveURL('/');
});
