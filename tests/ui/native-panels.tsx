import {root} from './collection';
import {useState} from 'react';
import {FirstRunOnboarding} from 'gca-onboarding-production';
import {CompactQuickPanel} from 'gca-quick-production';
import {GabeCubeAuraSettings} from 'gca-settings-production';
import {setUILanguage} from 'gca-language';
import {ButtonItem,DropdownItem,PanelSection,PanelSectionRow,SliderField,ToggleField} from 'gca-localized-production';
const status:any={version:'1.4.1-lab.197',ui_language:'fr',game:{appid:0,title:''},display_preset:'moderate',current_display:'customization',artwork_source:'hero',countdown:{active:false},personal_timer:{active:false,remaining_seconds:0},timer_end_action:{phase:'idle'},thermal_protection:{active:false},debug:{engine_running:true},light_bar_day_brightness:128,faceplate_brightness:70,signalbar_enabled:true,active:true,faceplate:{available:true,powered:true,routing:{routes:{home:'dashboard',game:'artwork'},preference_revision:1}},faceplate_dashboard_home_source:'weather'};
function Quick(){const [value,setValue]=useState(status);return <CompactQuickPanel active={false} status={value} setStatus={setValue} colors={Array.from({length:17},()=>[20,90,160])} onOpenGame={()=>{}} onOpenSettings={()=>{}}/>;}
function Settings(){return <GabeCubeAuraSettings/>;}
(window as any).__gcaStatus=status;
(window as any).__gca={mount:(mode:string,lang='fr')=>{status.ui_language=lang;(window as any).__gcaQaData.status.ui_language=lang;setUILanguage(lang);root.render(mode==='onboarding'?<FirstRunOnboarding status={(window as any).__gcaQaData.status} setStatus={()=>{}} onClose={()=>{}} openBrowser={()=>{}}/>:mode==='quick'?<Quick key={mode+lang}/>:<Settings key={mode+lang}/>);}};
