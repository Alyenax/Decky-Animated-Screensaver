import path from 'node:path';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {steamBootstrap55} from '../tests/steam-runtime/loader55.mjs';
import {navigationScenarios55} from '../tests/steam-runtime/navigation55.mjs';
import {auditStructure55} from '../tests/steam-runtime/structure55.mjs';

const root=process.cwd(),require=createRequire(path.join(root,'package.json'));
const {chromium}=require('playwright');
const reference=process.env.DAS_STEAM_REFERENCE||'/private/tmp/decky-native-audit-20261022/steam-reference.json';
const steamRoot=process.env.DAS_STEAM_ROOT||JSON.parse(await fs.readFile(reference,'utf8')).steamRoot;
const bootstrap=await steamBootstrap55(steamRoot);
const structure=await auditStructure55(root);
const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{
 const page=await browser.newPage({viewport:{width:800,height:800}});
 await page.setContent('<!doctype html><html><body></body></html>');
 await page.addScriptTag({content:bootstrap.source});
 const result=await page.evaluate(navigationScenarios55);
 console.log(JSON.stringify({purpose:'Native navigation algorithm topology reproduction, not physical or complete production acceptance',metadata:bootstrap.metadata,result,productionStructure:structure},null,2));
 if(process.argv.includes('--require-production-structure')&&structure.blockers.length)process.exitCode=1;
}finally{await browser.close();}
