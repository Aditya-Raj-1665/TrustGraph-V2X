import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const output=path.join(root,'midsem'),qa=path.join(root,'.qa');
await fs.mkdir(qa,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const page=await context.newPage();
const errors=[],checks=[];
page.on('pageerror',error=>errors.push(error.message));
const url=name=>pathToFileURL(path.join(output,name)).href;
const check=(name,condition)=>{assert.ok(condition,name);checks.push(name)};
try{
 await page.goto(url('index.html'));
 await page.waitForFunction(()=>typeof window.demoState==='function');
 check('offline app initializes',await page.locator('#vehicle-title').textContent());
 check('network labels synthetic scope',(await page.locator('#network .notice').innerText()).includes('Synthetic'));
 await page.getByRole('button',{name:'Attack starts',exact:true}).click();
 check('attack jump reaches 1.5 seconds',(await page.locator('#clock').textContent())==='1.5 s');
 check('selected attack actually active',(await page.locator('#attack-state').textContent()).includes('Injected attack active'));
 check('checkpoint predictions are visible',(await page.locator('#trust-value').textContent()).includes('Message multiplier'));
 await page.screenshot({path:path.join(qa,'network-attack.png'),fullPage:true});
 await page.locator('#truth').uncheck();
 check('truth overlay can be hidden',(await page.locator('#attack-state').textContent()).includes('hidden'));
 await page.locator('#truth').check();
 await page.getByRole('button',{name:'Next handover',exact:true}).click();
 check('handover shortcut selects a recorded transition',(await page.locator('#decision').textContent()).includes('→'));
 await page.screenshot({path:path.join(qa,'network-handover.png'),fullPage:true});
 const eventState=await page.evaluate(()=>window.demoState());
 await page.keyboard.press('ArrowRight');
 const causal=await page.evaluate(({frameIndex,selected})=>{const r=window.TRUSTGRAPH_DATA.replays[window.demoState().scenario];return r.frames[frameIndex].targets[selected]===r.frames[frameIndex+1].observed.serving[selected]},eventState);
 check('next snapshot reflects applied handover',causal);
 await page.locator('#play').click();
 await page.waitForFunction(start=>window.demoState().frameIndex>start,eventState.frameIndex+1);
 await page.locator('#play').click();
 check('play and pause respond',!(await page.evaluate(()=>window.demoState().playing)));
 await page.locator('#scenario').selectOption('clean');
 await page.locator('#attack-onset').click();
 check('clean scenario does not claim an injected attack',(await page.locator('#event-note').textContent()).includes('no injected attack'));
 await page.locator('[data-tab="sumo"]').click();
 await page.locator('#sumo-play').click();
 await page.waitForFunction(()=>window.demoState().sumoIndex>3);
 await page.locator('#sumo-play').click();
 check('SUMO replay advances',await page.evaluate(()=>window.demoState().sumoIndex>3));
 await page.locator('#sumo-timeline').fill('70');
 await page.locator('#sumo-timeline').dispatchEvent('input');
 await page.screenshot({path:path.join(qa,'sumo.png'),fullPage:true});
 await page.locator('[data-tab="results"]').click();
 check('fixed rule baseline included',(await page.locator('#results-content').innerText()).includes('Fixed rules'));
 await page.screenshot({path:path.join(qa,'results.png'),fullPage:true});
 check('desktop page has no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.setViewportSize({width:390,height:844});
 await page.locator('[data-tab="network"]').click();
 check('mobile page has no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:path.join(qa,'mobile.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:900});
 await page.goto(url('slides.html'));
 await page.waitForFunction(()=>window.slideIndex===0);
 const total=await page.locator('.slide').count();
 check('twelve slides present',total===12);
 for(let i=0;i<total;i++){
   const box=await page.locator('.slide.active').boundingBox();
   check(`slide ${i+1} fits viewport`,box.height<=901);
   await page.screenshot({path:path.join(qa,`slide-${String(i+1).padStart(2,'0')}.png`)});
   if(i<total-1)await page.locator('#next').click();
 }
 await page.locator('#show-notes').click();
 check('speaker notes work',await page.locator('#notes').isVisible());
 await page.locator('#show-notes').click();
 if(process.argv.includes('--pdf')){
   await page.pdf({path:path.join(output,'TrustGraph-V2X-Midsem-Slides.pdf'),preferCSSPageSize:true,printBackground:true});
 }
 await page.goto(url('report.html'));
 await page.waitForSelector('#report .page');
 check('seven report sections present',(await page.locator('#report .page').count())===7);
 for(let i=0;i<7;i++)await page.locator('#report .page').nth(i).screenshot({path:path.join(qa,`report-section-${i+1}.png`)});
 if(process.argv.includes('--pdf')){
   await page.pdf({path:path.join(output,'TrustGraph-V2X-Midsem-Report.pdf'),preferCSSPageSize:true,printBackground:true});
 }
 check('no browser JavaScript exceptions',errors.length===0);
 await fs.writeFile(path.join(qa,'browser-checks.json'),JSON.stringify({checks,errors,passed:checks.length},null,2));
 console.log(JSON.stringify({passed:checks.length,errors,pdf:process.argv.includes('--pdf'),screenshots:qa}));
}finally{await browser.close()}
