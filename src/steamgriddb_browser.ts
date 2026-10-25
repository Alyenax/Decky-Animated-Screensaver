import {Navigation} from '@decky/ui';

export const STEAMGRIDDB_API_KEY_URL='https://www.steamgriddb.com/profile/preferences/api';
// Same normal-navigation OpenID request as GabeCubeAura, not the site's popup.
export const STEAMGRIDDB_DIRECT_LOGIN_URL='https://steamcommunity.com/openid/login?openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.mode=checkid_setup&openid.realm=https%3A%2F%2Fwww.steamgriddb.com&openid.return_to=https%3A%2F%2Fwww.steamgriddb.com%2Flogin%2Fsteam&mobileminimal=1';

type BrowserSystem={OpenInSystemBrowser?:(url:string)=>void};

/** User-triggered navigation only. Never reads credentials or the clipboard. */
export function openSteamGridDBPage(page:'login'|'keys'):'system'|'steam'{
  const url=page==='login'?STEAMGRIDDB_DIRECT_LOGIN_URL:STEAMGRIDDB_API_KEY_URL;
  const system=(globalThis as typeof globalThis & {SteamClient?:{System?:BrowserSystem}}).SteamClient?.System;
  try{
    const open=system?.OpenInSystemBrowser;
    if(typeof open==='function'){open.call(system,url);return 'system';}
  }catch{/* Preserve GabeCubeAura's direct-navigation fallback in Steam. */}
  Navigation.NavigateToExternalWeb(url);
  return 'steam';
}
