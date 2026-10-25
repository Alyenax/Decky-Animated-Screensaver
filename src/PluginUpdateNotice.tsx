import {DialogButton} from '@decky/ui';
import {QuickAction} from './QuickControls';
import {tr,useLanguage} from './i18n';
import {useUpdateNotice,visibleUpdate} from './update_notice';

/** Subscribes to cached status, including updates detected while this view is open. */
export function PluginUpdateNotice({onOpen,quick=false}:{onOpen:()=>void;quick?:boolean}){
  useLanguage();const update=useUpdateNotice();
  if(!visibleUpdate(update))return null;
  const label=(update.phase==='ready'?tr('Update ready','Mise à jour prête'):tr('Update available','Mise à jour disponible'))+' · '+update.version;
  return quick?<QuickAction onClick={onOpen}>{label}</QuickAction>
    :<DialogButton className="collection-action" data-plugin-update onClick={onOpen}>{label}</DialogButton>;
}
