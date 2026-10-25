import {language,tr} from './i18n';
/** Actual prepared-file bytes only; no estimate or USB/optical inference. */
export function preparedFileSize(bytes:unknown){
 if(typeof bytes!=='number'||!Number.isSafeInteger(bytes)||bytes<=0)return undefined;
 const number=new Intl.NumberFormat(language()==='fr'?'fr-FR':'en-GB',{maximumFractionDigits:1});
 return bytes<1024?tr(`${number.format(bytes)} bytes`,`${number.format(bytes)} octets`):bytes<1048576?`${number.format(bytes/1024)} ${tr('KB','ko')}`:bytes<1073741824?`${number.format(bytes/1048576)} ${tr('MB','Mo')}`:`${number.format(bytes/1073741824)} ${tr('GB','Go')}`;
}
