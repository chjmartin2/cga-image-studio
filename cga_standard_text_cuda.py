"""Optional exhaustive float64 CUDA text matching. No candidate pruning."""
import os
from pathlib import Path
import tempfile
import threading
import warnings
from functools import lru_cache

import numpy as np

_LOCK=threading.RLock()
_CP=None
_INFO=None


def device_info():
    global _CP,_INFO
    with _LOCK:
        if _INFO is not None: return dict(_INFO)
        try:
            os.environ.setdefault('CUPY_CACHE_DIR',str(Path(tempfile.gettempdir())/'cga-studio-cupy'))
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',message='CUDA path could not be detected.*')
                import cupy as cp
            if cp.cuda.runtime.getDeviceCount()<1: raise RuntimeError('No CUDA GPU detected')
            with cp.cuda.Device(0):
                probe=cp.asarray([1.,2.],dtype=cp.float64)
                if float(cp.sum(probe).get())!=3: raise RuntimeError('CUDA probe failed')
                name=cp.cuda.runtime.getDeviceProperties(0)['name']
            _CP=cp
            _INFO=dict(available=True,name=name.decode() if isinstance(name,bytes) else str(name))
        except Exception as exc:
            _INFO=dict(available=False,name='CPU',reason=f'{type(exc).__name__}: {exc}')
        return dict(_INFO)


def disable(reason):
    global _INFO
    with _LOCK:
        _INFO=dict(available=False,name='CPU',reason=str(reason))


@lru_cache(maxsize=16)
def _render_id(font_bytes,height):
    """Same ID for glyph/color combinations with identical rendered indices."""
    masks=np.frombuffer(font_bytes,np.uint8).reshape(256,8)[:,:height]
    _,ids=np.unique(np.concatenate((masks,masks^255)),axis=0,return_inverse=True)
    fg=np.arange(16)[None,:,None];bg=np.arange(16)[None,None,:]
    shape=np.where(fg<bg,ids[:256,None,None],ids[256:,None,None])
    result=16+(np.minimum(fg,bg)*16+np.maximum(fg,bg))*512+shape
    result=np.where((masks==0).all(1)[:,None,None],bg,result)
    result=np.where((masks==255).all(1)[:,None,None],fg,result)
    result=np.where(fg==bg,fg,result)
    return result.astype(np.int32)


def match_tiles(tiles,font,palette,method,*,dct_settings,progress_cb=None,cancel_event=None,backend_info=None):
    from cga_standard_text import feature_operator,glyph_masks,Cancelled,HEIGHTS
    from cga_scanline_color import srgb_to_linear
    raw=np.asarray(tiles);palette=np.asarray(palette)
    if raw.ndim!=4 or raw.shape[2:]!=(8,3) or raw.dtype!=np.uint8 or not len(raw):
        raise ValueError('Tiles must be nonempty uint8 B,H,8,3')
    if raw.shape[1] not in HEIGHTS: raise ValueError('Unsupported character height')
    if palette.shape!=(16,3) or palette.dtype!=np.uint8: raise ValueError('Palette must contain sixteen RGB byte colors')
    info=device_info()
    if not info['available']: raise RuntimeError(info.get('reason','CUDA unavailable'))
    cp=_CP;height=raw.shape[1]
    def check():
        if cancel_event is not None and cancel_event.is_set(): raise Cancelled()
    check();refine=set()
    # One active matcher owns the device. Other optimizer threads can prepare
    # CPU scores concurrently without creating competing CUDA contexts.
    with _LOCK,cp.cuda.Device(0):
        check()
        transform=cp.asarray(feature_operator(height,method,dct_settings))
        masks=cp.asarray(glyph_masks(font,height).reshape(256,-1))
        fg_features=masks@transform.T
        bg_features=transform.sum(axis=1)[None]-fg_features
        ff=cp.square(fg_features).sum(1);bb=cp.square(bg_features).sum(1)
        fb=(fg_features*bg_features).sum(1)
        colors=cp.asarray(srgb_to_linear(palette));norms=cp.square(colors).sum(1)
        cross=colors@colors.T
        independent=float(cp.abs(fb).max().get())<1e-12
        identities=cp.asarray(_render_id(np.asarray(font,np.uint8).tobytes(),height))
        pairs=np.empty((len(raw),2),np.uint8);errors=np.empty(len(raw))
        free,_=cp.cuda.runtime.memGetInfo()
        # Three score-sized temporaries can be live. Limit batches by free VRAM.
        batch_size=max(1,min(128,int(free*.2)//(256*256*8*3)))
        for first in range(0,len(raw),batch_size):
            check()
            batch=cp.asarray(srgb_to_linear(raw[first:first+batch_size]).reshape(-1,height*8,3))
            features=cp.matmul(transform,batch)
            target_norm=cp.square(features).sum((1,2))
            fcor=cp.matmul(fg_features,features);bcor=cp.matmul(bg_features,features)
            fscore=ff[None,:,None]*norms-2*(fcor@colors.T)
            bscore=bb[None,:,None]*norms-2*(bcor@colors.T)
            ix=cp.arange(len(batch))
            if independent:
                fs=fscore.argmin(-1);bs=bscore.argmin(-1)
                fm=cp.take_along_axis(fscore,fs[...,None],-1)[...,0]
                bm=cp.take_along_axis(bscore,bs[...,None],-1)[...,0]
                scores=fm+bm
                glyph=scores.argmin(-1);fg=fs[ix,glyph];bg=bs[ix,glyph]
                best=scores[ix,glyph]
                color_tie=(((fscore<=fm[...,None]+1e-12).sum(-1)>1)&(ff[None]>1e-14))|(
                    ((bscore<=bm[...,None]+1e-12).sum(-1)>1)&(bb[None]>1e-14))
                different=identities[cp.arange(256)[None],fs,bs]!=identities[glyph,fg,bg][:,None]
                ambiguous=((scores<=best[:,None]+1e-12)&(different|color_tie)).any(1)
            else:
                scores=fscore[:,:,:,None]+bscore[:,:,None,:]+2*fb[None,:,None,None]*cross
                flat=scores.reshape(len(batch),-1);winner=flat.argmin(-1)
                glyph=winner//256;fg=(winner%256)//16;bg=winner%16
                best=flat[ix,winner]
                different=identities.reshape(1,-1)!=identities.reshape(-1)[winner][:,None]
                ambiguous=((flat<=best[:,None]+1e-12)&different).any(1)
            pairs[first:first+len(batch),0]=cp.asnumpy(glyph)
            pairs[first:first+len(batch),1]=cp.asnumpy(fg+(bg<<4))
            errors[first:first+len(batch)]=cp.asnumpy(cp.maximum(0,best+target_norm))
            refine.update((first+int(index))//16 for index in cp.asnumpy(cp.flatnonzero(ambiguous)))
            if progress_cb: progress_cb((first+len(batch))/len(raw))
        check()
    # Some averaging objectives give different patterns exactly equal feature
    # scores. CPU/GPU roundoff must not change which pattern reaches the visual
    # scorer. Re-run ambiguous CPU-sized batches with the original arithmetic.
    from cga_standard_text import _match_tiles_cpu
    refined=0
    for group in sorted(refine):
        check();first=group*16;last=min(first+16,len(raw))
        pairs[first:last],errors[first:last]=_match_tiles_cpu(raw[first:last],font,palette,method,
            dct_settings=dct_settings,cancel_event=cancel_event)
        refined+=last-first
    if backend_info is not None: backend_info['cpu_tie_tiles']=refined
    check()
    return pairs,errors
