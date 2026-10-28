"""Browser visual smoke with an isolated preview (no external fonts, keys or network)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient
from retailiq.api import app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs'/'ui_previews'
OUT.mkdir(parents=True,exist_ok=True)
client = TestClient(app)
html=client.get('/').text
css=client.get('/assets/styles.css').text.replace("@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');",'')
js=client.get('/assets/app.js').text
html=html.replace('<link rel="preconnect" href="https://fonts.googleapis.com">','').replace('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>','')
html=html.replace('<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">','')
html=html.replace('<link rel="stylesheet" href="/assets/styles.css">','<style>'+css+'</style>')
html=html.replace('<script defer src="/assets/app.js"></script>','')
html=html.replace('</body>','<script>'+js+'</script></body>')
# Browser has no direct network access; use real offline API outputs from TestClient.
from unittest.mock import patch
with patch.dict('os.environ',{'RETAILIQ_MODE':'offline'}):
    response=client.post('/ask',json={'question':'How many units of AlphaBook Pro 14 are currently in stock?'}).json()
roi60=client.post('/api/roi/estimate',json={}).json()
roi30=client.post('/api/roi/estimate',json={'assisted_share':.3}).json()

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    errors=[]
    for width,height,name in [(1440,960,'desktop'),(390,844,'mobile')]:
        page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_content(html,wait_until='domcontentloaded')
        page.evaluate('''({response,roi60,roi30}) => {
          window.fetch=async(url,options)=>({ok:true,json:async()=>{
            if(url==='/ask')return response;
            const body=JSON.parse(options.body);
            return body.assisted_share===.3 ? roi30 : roi60;
          }});
        }''',{'response':response,'roi60':roi60,'roi30':roi30})
        page.locator('button#ask-submit').click()
        page.locator('#response-state').get_by_text('COMPLETE').wait_for(timeout=10000)
        assert 'AlphaBook' in page.locator('#answer').inner_text()
        page.screenshot(path=str(OUT/f'assistant_{name}.png'),full_page=True)
        page.locator('#tab-roi').click()
        page.locator('#roi-payback').get_by_text('3.75 months').wait_for(timeout=10000)
        page.screenshot(path=str(OUT/f'roi_{name}.png'),full_page=True)
        page.locator('input[name="assisted_share_percent"]').fill('30')
        page.locator('#roi-run').click()
        page.locator('#roi-payback').get_by_text('10.00 months').wait_for(timeout=10000)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),f'overflow on {name}'
        page.close()
    assert not errors,errors
    print('PASS: Desktop and mobile assistant, ROI interactions, no JS errors, no horizontal overflow')
    browser.close()
