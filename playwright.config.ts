import {defineConfig} from '@playwright/test';
// Two servers (Task 6.2): :8000 for live-call specs; :8001 serves a fresh copy of tests/fixtures.
// outputDir is a subfolder so Playwright's cleanup never deletes the servers' data/log dirs.
const LIVE='http://127.0.0.1:8000',SEEDED='http://127.0.0.1:8001';
export default defineConfig({testDir:'./ui_tests',workers:1,outputDir:'test-results/artifacts',
  use:{launchOptions:{args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']}},
  projects:[
    {name:'live',testMatch:/(live-call-assist|call-ended-card)\.spec\.ts/,use:{baseURL:LIVE}},
    {name:'seeded',testMatch:/call-log-(list|viewer)\.spec\.ts/,use:{baseURL:SEEDED}},
  ],
  webServer:[
    {command:'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',url:LIVE+'/health',env:{TEST_MODE:'true',DATA_DIR:'test-results/server-data',LOG_DIR:'test-results/server-logs'},reuseExistingServer:false},
    {command:'python tests/fixtures/seed_ui_server.py test-results/seeded && python -m uvicorn app.main:app --host 127.0.0.1 --port 8001',url:SEEDED+'/health',env:{TEST_MODE:'true',DATA_DIR:'test-results/seeded/data',LOG_DIR:'test-results/seeded/logs'},reuseExistingServer:false},
  ]});
