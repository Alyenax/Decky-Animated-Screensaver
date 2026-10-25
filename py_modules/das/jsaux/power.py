"""Offline RGB332 power limiter. Never change hardware brightness or settings.

Use the same decoded average-RGB proxy as GCA's guard, not a physical wattage
claim. Balanced rounding preserves channel averages without periodic grids.
"""
from bisect import bisect_right
from .protocol import BrokerError

PALETTE=tuple((round(r*255/7),round(g*255/7),round(b*255/3)) for r in range(8) for g in range(8) for b in range(4))
LOADS=tuple(sum(rgb) for rgb in PALETTE)
PIXELS=64*54
ENERGY=PIXELS*765
POWER_BUDGET_PPM=500000
POWER_POLICY='rgb332-balanced-power-v1'
MAX_ENERGY=ENERGY*POWER_BUDGET_PPM//1000000

def energy(frame):
    return sum(map(LOADS.__getitem__,frame))

def load_ppm(value):
    return (value*1000000+ENERGY-1)//ENERGY

def _tie(position,channel):
    # Fixed in image coordinates, never frame/time: no moving point or grid.
    value=(position+1+(channel+1)*0x9e3779b9)&0xffffffff
    value=((value^(value>>16))*0x45d9f3b)&0xffffffff
    value=((value^(value>>16))*0x45d9f3b)&0xffffffff
    return value^(value>>16)

def limit_frame(frame,checkpoint=lambda:None):
    """Return safe native indices; leave every already-safe frame byte-identical.

    Limit each channel's aggregate to its proportional share of the budget.
    Floors are safe; largest-remainder upgrades recover detail/colour up to
    that channel budget. Every chosen colour still belongs to native RGB332.
    Working memory is one frame plus at most 3456 rounding candidates.
    """
    if len(frame)!=PIXELS:raise BrokerError('CONTENT_INVALID')
    total=energy(frame)
    if total<=MAX_ENERGY:return bytes(frame)
    out=bytearray(PIXELS)
    for channel,(bits,shift) in enumerate(((7,5),(7,2),(3,0))):
        checkpoint()
        levels=tuple(round(n*255/bits) for n in range(bits+1))
        source_sum=0;base_sum=0;candidates=[]
        for position,index in enumerate(frame):
            source=levels[(index>>shift)&bits];source_sum+=source
            scaled=source*MAX_ENERGY
            level=bisect_right(levels,scaled//total)-1
            base=levels[level];base_sum+=base;out[position]|=level<<shift
            if level<bits:
                delta=levels[level+1]-base
                fraction=(scaled-base*total)*1000000//(delta*total)
                if fraction:candidates.append((fraction,_tie(position,channel),position,delta))
        remaining=source_sum*MAX_ENERGY//total-base_sum
        candidates.sort(reverse=True)
        quantum=min(b-a for a,b in zip(levels,levels[1:]))
        for _,_,position,delta in candidates:
            if delta<=remaining:out[position]+=1<<shift;remaining-=delta
            if remaining<quantum:break
    checkpoint()
    if energy(out)>MAX_ENERGY:raise BrokerError('CONTENT_INVALID')
    return bytes(out)
