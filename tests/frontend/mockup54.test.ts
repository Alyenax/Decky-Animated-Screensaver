import test from 'node:test';
import assert from 'node:assert/strict';
import {preparedFileSize} from '../../src/faceplatePreparation';
import {faceplateNeedsCorrection} from '../../src/faceplateUX';
import {setLanguage} from '../../src/i18n';
import type {StudioState} from '../../src/types';
test('Prepared GIF size admits only safe positive actual bytes',()=>{
 for(const bytes of [undefined,null,0,-1,NaN,Infinity,'123',Number.MAX_SAFE_INTEGER+1])assert.equal(preparedFileSize(bytes),undefined);
 setLanguage('en');assert.equal(preparedFileSize(358400),'350 KB');assert.equal(preparedFileSize(1048576),'1 MB');
});
test('Only actionable failures expose Faceplate correction; prepared files and USB result stay independent',()=>{
 const state=(reason:string,patch:any={})=>({job:{},workspace:{task:{}},jsaux:{enabled:true,detected:true,compatible:true,mode:'async',reason,prepared:{ready:true,bytes:123},...patch}} as StudioState);
 for(const reason of ['','STEAM_INACTIVE','FLASH_DEFERRED','DISPLAY_OFF','SUSPENDED','PRIORITY_ACTIVE','PREPARATION_STALE'])assert.equal(faceplateNeedsCorrection(state(reason)),false,reason);
 for(const reason of ['USB_FAILED','USB_UNCONFIRMED','CONTENT_INVALID','CONTENT_TOO_LARGE','PREPARATION_FAILED'])assert.equal(faceplateNeedsCorrection(state(reason)),true,reason);
 assert.equal(faceplateNeedsCorrection(state('JSAUX_SYNC_WINDOW',{mode:'sync'})),true);
 assert.equal(faceplateNeedsCorrection(state('JSAUX_SYNC_WINDOW',{mode:'async'})),false);
 assert.equal(faceplateNeedsCorrection(state('USB_FAILED',{detected:false,configured:true})),false);
 assert.equal(faceplateNeedsCorrection(state('USB_FAILED',{enabled:false})),false);
 assert.equal(state('USB_FAILED').jsaux!.prepared!.ready,true);
});
