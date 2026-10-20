"""Static CGA text: exhaustive glyph/attribute matching under linear metrics.

No glyph shortlist or color-pair pruning. Linear feature operators let us score
every candidate using sufficient statistics instead of rendering 65,536 tiles.
"""
from dataclasses import dataclass
from functools import lru_cache
import operator

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from cga_scanline_color import srgb_to_linear

MODES = {'40-column Text (RGB)': 40, '80-column Text (RGB)': 80}
METHODS = ('Pixel (linear RGB)', 'Average 2x2', 'Average 4x4',
           'Average whole character', 'DCT (structure)', 'Balanced (multiscale)')
DEFAULT_METHOD = 'DCT (structure)'
PREPROCESS = ('Original', 'Downsample 2x', 'Downsample 4x', 'Cartoon simplify')
HEIGHTS = tuple(range(2, 9))


@dataclass(frozen=True)
class DCTSettings:
    structure: float = 8.
    falloff: float = 1.
    color: float = 1.
    vertical: float = 1.

    def __post_init__(self):
        for name,low,high in (('structure',0,32),('falloff',.25,3),
                              ('color',.25,4),('vertical',.25,4)):
            value=getattr(self,name)
            if not np.isfinite(value) or not low<=value<=high:
                raise ValueError(f'DCT {name} must be between {low} and {high}')


@dataclass(frozen=True)
class Geometry:
    columns: int = 80
    height: int = 8

    def __post_init__(self):
        if operator.index(self.columns) not in (40,80):
            raise ValueError('CGA text requires 40 or 80 columns')
        if operator.index(self.height) not in HEIGHTS:
            raise ValueError('CGA text character height must be 2 through 8 scanlines')
        if self.memory_bytes > 16384:
            raise ValueError('Text cells exceed CGA video memory')

    @property
    def top_padding(self):
        # Vertical sync is specified in whole character rows. Keep the image
        # inside the usual 200-line aperture when 224 is not divisible by h.
        return 224 % self.height

    @property
    def rows(self): return (200-self.top_padding) // self.height

    @property
    def active_size(self): return self.columns*8, self.rows*self.height

    @property
    def memory_bytes(self): return self.columns*self.rows*2

    @property
    def crtc(self):
        total_rows = min(128,262//self.height)
        return {4:total_rows-1, 5:262-total_rows*self.height,
                6:self.rows, 7:224//self.height, 9:self.height-1,
                10:0x20, 12:0, 13:0}  # cursor off; page zero


def prepare(image, method='Original'):
    if method not in PREPROCESS:
        raise ValueError('Unknown text preprocessing option')
    image=image.convert('RGB')
    if method.startswith('Downsample'):
        factor=2 if method=='Downsample 2x' else 4
        small=(max(1,image.width//factor),max(1,image.height//factor))
        return image.resize(small,Image.Resampling.BOX).resize(image.size,Image.Resampling.NEAREST)
    if method=='Cartoon simplify':
        return ImageOps.posterize(image.filter(ImageFilter.MedianFilter(3)),4)
    return image.copy()


def glyph_masks(font,height):
    raw=np.asarray(font)
    if raw.shape!=(256,8) or not np.isfinite(raw).all() or (raw<0).any() or (raw>255).any():
        raise ValueError('Expected the 256-character, eight-row CGA ROM font')
    if height not in HEIGHTS:
        raise ValueError('CGA text character height must be 2 through 8 scanlines')
    rows=raw.astype(np.uint8)[:,:height]
    return ((rows[:,:,None] >> np.arange(7,-1,-1))&1).astype(np.float64)


def prequantize(image,palette,*,family='None',diffusion='Floyd-Steinberg',
                intensity=1.,serpentine=True,ordered_size=4,ordered_strength=1.,cancel_event=None):
    """Optional CGA-16 raster before matching; diffusion ends at this stage."""
    from cga_scanline import KERNELS, ordered_matrix
    if family not in ('None','Ordered','Diffusion','Error diffusion') or diffusion not in KERNELS:
        raise ValueError('Unknown prequantization dither')
    if not np.isfinite([intensity,ordered_strength]).all():
        raise ValueError('Dither strengths must be finite')
    rgb=np.asarray(palette,np.uint8); colors=srgb_to_linear(rgb)
    source=srgb_to_linear(np.asarray(image.convert('RGB')))
    h,w=source.shape[:2]; indices=np.empty((h,w),np.uint8)
    kernel=KERNELS[diffusion] if family in ('Diffusion','Error diffusion') else ()
    strength=max(0.,min(1.,float(intensity)))
    matrix=ordered_matrix(ordered_size)
    work=np.pad(source,((0,2),(0,0),(0,0)))
    for y in range(h):
        if cancel_event is not None and cancel_event.is_set(): raise Cancelled()
        if not kernel or strength==0:
            row=source[y].copy()
            if family=='Ordered':
                row+=(matrix[y%len(matrix),np.arange(w)%len(matrix)]-.5)[:,None]*.5*max(0.,min(3.,ordered_strength))
            indices[y]=np.square(np.clip(row,0,1)[:,None]-colors).sum(-1).argmin(-1)
            continue
        reverse=serpentine and y%2
        for x in range(w-1,-1,-1) if reverse else range(w):
            # Match and diffuse the SAME displayable corrected color. Sending
            # the unclipped residual stores impossible channel overflow in
            # saturated regions and leaks it into subsequent rows.
            old=np.clip(work[y,x],0,1)
            chosen=np.square(old-colors).sum(-1).argmin()
            indices[y,x]=chosen
            error=(old-colors[chosen])*strength
            for dx,dy,weight in kernel:
                xx=x-dx if reverse else x+dx
                if 0<=xx<w: work[y+dy,xx]+=error*weight
    return Image.fromarray(rgb[indices])


@lru_cache(maxsize=64)
def dct_operator(height,width,dct_settings=DCTSettings()):
    """Full weighted orthonormal DCT for a pixel block."""
    def dct(n):
        matrix=np.cos(np.pi*(np.arange(n)[None]+.5)*np.arange(n)[:,None]/n)*np.sqrt(2/n)
        matrix[0]/=np.sqrt(2)
        return matrix
    frequency=((np.arange(height)[:,None]/height)**2*dct_settings.vertical+
               (np.arange(width)[None]/width)**2/dct_settings.vertical)
    weights=1/(1+dct_settings.structure*frequency)**dct_settings.falloff
    weights[0,0]*=dct_settings.color
    result=np.kron(dct(height),dct(width))*np.sqrt(weights.ravel()[:,None]/(height*width))
    result.flags.writeable=False
    return result


@lru_cache(maxsize=64)
def feature_operator(height,method,dct_settings=DCTSettings()):
    if method not in METHODS:
        raise ValueError('Unknown text matching method')
    pixels=height*8
    def averages(size):
        rows=[]
        for y in range(0,height,size):
            for x in range(0,8,size):
                mask=np.zeros((height,8))
                mask[y:min(y+size,height),x:min(x+size,8)]=1
                count=mask.sum()
                rows.append(mask.ravel()/count*np.sqrt(count/pixels))
        return np.asarray(rows)
    if method=='Pixel (linear RGB)':
        result=np.eye(pixels)/np.sqrt(pixels)
    elif method=='Average whole character':
        result=np.ones((1,pixels))/pixels
    elif method.startswith('Average'):
        result=averages(2 if method=='Average 2x2' else 4)
    elif method==DEFAULT_METHOD:
        result=dct_operator(height,8,dct_settings)
    else:
        result=np.concatenate((np.sqrt(.4)*np.eye(pixels)/np.sqrt(pixels),
            np.sqrt(.3)*averages(2),np.sqrt(.2)*averages(4),
            np.sqrt(.1)*np.ones((1,pixels))/pixels))
    result.flags.writeable=False
    return result


class Cancelled(Exception): pass


def _match_tiles_cpu(tiles,font,palette,method=DEFAULT_METHOD,progress_cb=None,cancel_event=None,
                dct_settings=DCTSettings()):
    """Return [character, attribute] bytes per tile and chosen feature errors.

    Input is B,H,8,3 RGB bytes. Equal scores choose the first glyph then the
    lowest foreground/background indices. Solid colors and duplicate glyphs
    are legal. Scores use float64 to preserve exact-color matches.
    """
    raw=np.asarray(tiles)
    if raw.ndim!=4 or raw.shape[2:]!=(8,3) or raw.dtype!=np.uint8 or not len(raw):
        raise ValueError('Tiles must be nonempty uint8 B,H,8,3')
    height=raw.shape[1]
    if height not in HEIGHTS:
        raise ValueError('Unsupported character height')
    palette=np.asarray(palette)
    if palette.shape!=(16,3) or palette.dtype!=np.uint8:
        raise ValueError('Palette must contain sixteen RGB byte colors')
    transform=feature_operator(height,method,dct_settings)
    masks=glyph_masks(font,height).reshape(256,-1)
    fg_features=masks@transform.T
    constant=transform.sum(axis=1)
    bg_features=constant[None]-fg_features
    ff=np.square(fg_features).sum(1)
    bb=np.square(bg_features).sum(1)
    fb=(fg_features*bg_features).sum(1)
    colors=srgb_to_linear(palette)
    norms=np.square(colors).sum(1)
    cross=colors@colors.T
    pairs=np.empty((len(raw),2),np.uint8)
    errors=np.empty(len(raw))
    independent=np.max(np.abs(fb))<1e-12
    # At most 16*256*16*16 scores (~8 MiB) live at a time.
    for first in range(0,len(raw),16):
        if cancel_event is not None and cancel_event.is_set(): raise Cancelled()
        batch=srgb_to_linear(raw[first:first+16]).reshape(-1,height*8,3)
        features=np.einsum('kp,bpc->bkc',transform,batch,optimize=True)
        target_norm=np.square(features).sum((1,2))
        fcor=np.einsum('bkc,gk->bgc',features,fg_features,optimize=True)
        bcor=np.einsum('bkc,gk->bgc',features,bg_features,optimize=True)
        fscore=ff[None,:,None]*norms-2*(fcor@colors.T)
        bscore=bb[None,:,None]*norms-2*(bcor@colors.T)
        if independent:
            fs=fscore.argmin(-1); bs=bscore.argmin(-1)
            scores=np.take_along_axis(fscore,fs[...,None],-1)[...,0]+np.take_along_axis(bscore,bs[...,None],-1)[...,0]
            glyph=scores.argmin(-1)
            ix=np.arange(len(batch))
            fg,bg=fs[ix,glyph],bs[ix,glyph]
            best=scores[ix,glyph]
        else:
            scores=fscore[:,:,:,None]+bscore[:,:,None,:]+2*fb[None,:,None,None]*cross
            flat=scores.reshape(len(batch),-1)
            winner=flat.argmin(-1)
            glyph=winner//256; fg=(winner%256)//16; bg=winner%16
            best=flat[np.arange(len(batch)),winner]
        pairs[first:first+len(batch),0]=glyph
        pairs[first:first+len(batch),1]=fg+(bg<<4)
        errors[first:first+len(batch)]=np.maximum(0,best+target_norm)
        if progress_cb: progress_cb((first+len(batch))/len(raw))
    if cancel_event is not None and cancel_event.is_set(): raise Cancelled()
    return pairs,errors


def match_tiles(tiles,font,palette,method=DEFAULT_METHOD,progress_cb=None,cancel_event=None,
                dct_settings=DCTSettings(),backend='auto',backend_info=None):
    if method not in METHODS: raise ValueError('Unknown text matching method')
    if backend not in ('auto','cpu','cuda'): raise ValueError('Unknown text matching backend')
    options=dict(progress_cb=progress_cb,cancel_event=cancel_event,dct_settings=dct_settings)
    info={}
    if backend!='cpu':
        from cga_standard_text_cuda import device_info,match_tiles as cuda_match,disable
        device=device_info()
        if device['available']:
            try:
                result=cuda_match(tiles,font,palette,method,backend_info=backend_info,**options)
                if backend_info is not None: backend_info.update(backend='CUDA',device=device['name'])
                return result
            except Cancelled:
                raise
            except Exception as exc:
                if backend=='cuda': raise
                info['fallback_reason']=f'{type(exc).__name__}: {exc}'
                disable(info['fallback_reason'])
        elif backend=='cuda':
            raise RuntimeError(device.get('reason','CUDA unavailable'))
        else:
            info['fallback_reason']=device.get('reason','CUDA unavailable')
    result=_match_tiles_cpu(tiles,font,palette,method,**options)
    if backend_info is not None: backend_info.update(backend='CPU',**info)
    return result


def render(cells,font,palette,geometry):
    if len(cells)!=geometry.memory_bytes:
        raise ValueError('Character data does not match text geometry')
    pairs=np.frombuffer(cells,np.uint8).reshape(geometry.rows,geometry.columns,2)
    masks=glyph_masks(font,geometry.height).astype(bool)[pairs[:,:,0]]
    colors=np.asarray(palette,np.uint8)
    fg=colors[pairs[:,:,1]&15]; bg=colors[pairs[:,:,1]>>4]
    tiles=np.where(masks[:,:,:,:,None],fg[:,:,None,None],bg[:,:,None,None])
    active=tiles.transpose(0,2,1,3,4).reshape(geometry.active_size[1],geometry.active_size[0],3)
    canvas=np.zeros((200,geometry.columns*8,3),np.uint8)
    canvas[geometry.top_padding:geometry.top_padding+len(active)]=active
    return Image.fromarray(canvas)


def encode(image,font,palette,geometry=Geometry(),method=DEFAULT_METHOD,**kwargs):
    if image.size!=geometry.active_size:
        raise ValueError(f'Text input must be {geometry.active_size}; resize before encoding')
    rgb=np.asarray(image.convert('RGB'))
    tiles=rgb.reshape(geometry.rows,geometry.height,geometry.columns,8,3).transpose(0,2,1,3,4).reshape(-1,geometry.height,8,3)
    backend_info={}
    cells,errors=match_tiles(tiles,font,np.asarray(palette,np.uint8),method,backend_info=backend_info,**kwargs)
    payload=cells.tobytes()
    return render(payload,font,palette,geometry),payload,dict(metric=method,feature_error=float(errors.sum()),
        cells=len(cells),candidates_per_cell=65536,columns=geometry.columns,rows=geometry.rows,
        height=geometry.height,memory_bytes=geometry.memory_bytes,**backend_info)


def build_com(cells,geometry=Geometry()):
    """Static IBM CGA display, no raster loop. Load while video is disabled."""
    if len(cells)!=geometry.memory_bytes:
        raise ValueError('Character data does not match text geometry')
    mode=1 if geometry.columns==40 else 3
    control=0 if geometry.columns==40 else 1
    code=bytearray([0xB8,mode,0,0xCD,0x10,0x0E,0x1F,0xFC]) # BIOS; DS=CS; CLD
    code+=bytes([0xBA,0xD8,3,0xB0,control,0xEE]) # video off, blink off
    for index,value in geometry.crtc.items():
        code+=bytes([0xBA,0xD4,3,0xB0,index,0xEE,0x42,0xB0,value,0xEE])
    code+=bytes([0xBA,0xD9,3,0xB0,0,0xEE]) # black border
    code+=bytes([0xB8,0,0xB8,0x8E,0xC0,0x31,0xFF])
    patch=len(code)+1; code+=bytes([0xBE,0,0])
    count=len(cells)//2
    code+=bytes([0xB9,count&255,count>>8,0xF3,0xA5])
    code+=bytes([0xBA,0xD8,3,0xB0,control|8,0xEE]) # enable image, 16 BG colors
    code+=bytes([0xB4,0,0xCD,0x16]) # wait and consume key
    code+=bytes([0xB8,3,0,0xCD,0x10,0xB8,0,0x4C,0xCD,0x21])
    offset=0x100+len(code);code[patch:patch+2]=offset.to_bytes(2,'little')
    return bytes(code)+bytes(cells)
