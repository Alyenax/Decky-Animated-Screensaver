import {DialogControlsSection,DialogControlsSectionHeader,SteamSpinner} from '@decky/ui';
import type {ReactNode} from 'react';
export function SettingsSection({title,children,spinner}:{title?:string;children?:ReactNode;spinner?:boolean}){
  return <DialogControlsSection>{title&&<DialogControlsSectionHeader>{title}</DialogControlsSectionHeader>}{spinner&&<SteamSpinner/>}{children}</DialogControlsSection>;
}
export function SettingsRow({children}:{children?:ReactNode}){return <>{children}</>;}
