// Public Steam Item props, shared with GCA's native settings presentation.
// Steam owns fonts, colours, separators, popups and focus behaviour.
import {type ComponentProps} from 'react';
import {ButtonItem as NativeButton,DropdownItem as NativeDropdown,ToggleField as NativeToggle,SliderField as NativeSlider} from '@decky/ui';
export const ButtonItem=(props:ComponentProps<typeof NativeButton>)=><NativeButton layout="inline" childrenContainerWidth="fixed" {...props}/>;
export const DropdownItem=(props:ComponentProps<typeof NativeDropdown>)=><NativeDropdown layout="inline" childrenContainerWidth="fixed" {...props}/>;
export const ToggleField=(props:ComponentProps<typeof NativeToggle>)=><NativeToggle layout="inline" childrenContainerWidth="min" {...props}/>;
export const SliderField=(props:ComponentProps<typeof NativeSlider>)=><NativeSlider layout="inline" childrenContainerWidth="fixed" {...props}/>;
