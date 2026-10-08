import {test,expect} from '@playwright/test';
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
