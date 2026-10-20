"""Compare complete text renders against one fixed visual reference.

Every discrete option is visited; continuous dither strengths use a declared
quarter-step grid plus the current values. Only exact input duplicates share
work. Worker completion order never affects tie-breaking.
"""
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, asdict
import multiprocessing as mp
import os
import threading
import time

import numpy as np
from PIL import Image

import cga_standard_text as text
from cga_scanline import KERNELS
from cga_scanline_color import srgb_to_linear
from cga_repeat import _ImageScore

RESAMPLERS=('Lanczos','Lanczos + Unsharp','Gaussian (prefilter) + Lanczos',
            'Multi-pass Box (downscale)','Bicubic','Bilinear','Box (Area)','Hamming','Nearest')


@dataclass(frozen=True)
class Dither:
    family: str = 'None'
    diffusion: str = 'Floyd-Steinberg'
    intensity: float = 1.
    serpentine: bool = True
    ordered_size: int = 4
    ordered_strength: float = 1.

    def canonical(self):
        if self.family in ('Diffusion','Error diffusion'):
            if not np.isfinite(self.intensity): raise ValueError('Dither strength must be finite')
            intensity=max(0.,min(1.,float(self.intensity)))
            if self.diffusion=='None' or intensity==0: return Dither()
            return Dither('Diffusion',self.diffusion,intensity,self.serpentine)
        if self.family=='Ordered' and self.ordered_strength>0:
            return Dither('Ordered',ordered_size=self.ordered_size,ordered_strength=self.ordered_strength)
        return Dither()


def dither_options(quantize,current=Dither()):
    if not quantize: return (Dither(),)
    options=[current.canonical(),Dither()]
    strengths=sorted(set([.25,.5,.75,1.,float(current.intensity)]))
    for kernel in KERNELS:
        if kernel=='None': continue  # identical to quantization with no dither
        for serpentine in (False,True):
            for strength in strengths:
                options.append(Dither('Diffusion',kernel,strength,serpentine).canonical())
    strengths=sorted(set([i/4 for i in range(1,13)]+[float(current.ordered_strength)]))
    for size in range(2,17):
        for strength in strengths:
            options.append(Dither('Ordered',ordered_size=size,ordered_strength=strength).canonical())
    return tuple(dict.fromkeys(options))


def _check(event):
    if event is not None and event.is_set(): raise text.Cancelled()


def worker_count(jobs):
    cpu=getattr(os,'process_cpu_count',os.cpu_count)() or 1
    limit=min(cpu,61,jobs)  # Windows ProcessPoolExecutor limit
    try:
        if os.name=='nt':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
                    (name,ctypes.c_ulonglong) for name in
                    ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
            memory=Memory();memory.length=ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)): raise OSError()
            available=memory.available
        else:
            available=os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
        limit=min(limit,max(1,int(available*.5)//(256*1024*1024)))
    except (AttributeError,ValueError,OSError):
        limit=min(limit,16)
    return max(1,limit)


def _context(font,palette,geometry,reference,methods,dct,quantize,cancel,backend='cpu'):
    return dict(font=font,palette=palette,geometry=geometry,
        score=_ImageScore(srgb_to_linear(reference)),methods=methods,dct=dct,
        quantize=quantize,cancel=cancel,cache=OrderedDict(),backend=backend)


_WORKER=None
_BLAS_LIMIT=None
_GPU_THREAD=threading.local()


def _initialize(*args):
    global _WORKER,_BLAS_LIMIT
    try:
        from threadpoolctl import threadpool_limits
        _BLAS_LIMIT=threadpool_limits(limits=1,user_api='blas')
    except ImportError:
        pass
    _WORKER=_context(*args)


def _initialize_gpu(*args):
    _GPU_THREAD.context=_context(*args)


def _prepare_job(job):
    index,base,dither=job
    _check(_WORKER['cancel'])
    prepared=text.prequantize(base,_WORKER['palette'],cancel_event=_WORKER['cancel'],**asdict(dither))
    return index,prepared


def _evaluate_gpu(job):
    return _evaluate(job,_GPU_THREAD.context)


def _evaluate(job,context=None):
    context=_WORKER if context is None else context
    index,base,dither=job
    cancel=context['cancel'];_check(cancel)
    prepared=(text.prequantize(base,context['palette'],cancel_event=cancel,**asdict(dither))
              if context['quantize'] else base)
    key=prepared.tobytes()
    cache=context['cache']
    if key in cache:
        cache.move_to_end(key)
        return index,key,cache[key],True
    scores=[];winner=None;seen={}
    for method in context['methods']:
        _check(cancel)
        output,cells,diagnostics=text.encode(prepared,context['font'],context['palette'],
            context['geometry'],method,dct_settings=context['dct'],cancel_event=cancel,backend=context['backend'])
        pixels=output.tobytes()
        if pixels not in seen: seen[pixels]=context['score'](srgb_to_linear(output))
        score=seen[pixels]
        if not np.isfinite(score): raise ValueError('Non-finite text optimization score')
        scores.append(score)
        if winner is None or score<winner[0]: winner=(score,method,cells,diagnostics)
    _check(cancel)
    result=(scores,winner)
    cache[key]=result
    if len(cache)>8: cache.popitem(last=False)
    return index,key,result,False


def optimize(source,font,palette,geometry,resize,*,scale_mode='Stretch',
             current_method=text.DEFAULT_METHOD,current_preprocess='Original',
             current_resample='Lanczos',quantize=False,current_dither=Dither(),
             dct_settings=text.DCTSettings(),cancel_event=None,progress_cb=None,
             workers=None,resamplers=RESAMPLERS,preprocessors=text.PREPROCESS,
             methods=text.METHODS,profiles=None,backend='auto'):
    """source is the adjusted ORIGINAL. Height, columns, composition stay fixed.

    Restricted option lists are useful for oracle tests. The UI supplies the
    full lists. The quantize flag is fixed, never enabled by this function.
    """
    started=time.perf_counter();_check(cancel_event)
    if backend not in ('auto','cpu','cuda'): raise ValueError('Unknown optimization backend')
    from cga_standard_text_cuda import device_info
    device=device_info() if backend!='cpu' else dict(available=False,name='CPU')
    if backend=='cuda' and not device['available']: raise RuntimeError(device.get('reason','CUDA unavailable'))
    use_cuda=device['available']
    def ordered(values,current):
        values=tuple(values)
        return tuple(dict.fromkeys(([current] if current in values else [])+list(values)))
    methods=ordered(methods,current_method)
    if not methods or not resamplers or not preprocessors: raise ValueError('Empty search options')
    profiles=dither_options(quantize,current_dither) if profiles is None else tuple(profiles)
    if not profiles: raise ValueError('Empty dither options')
    # Fixed reference: canonical Lanczos, no simplification or color reduction.
    reference=Image.new('RGB',(geometry.columns*8,200))
    reference.paste(resize(source,*geometry.active_size,scale_mode,'Lanczos'),(0,geometry.top_padding))
    groups=[];unique={}
    for resample in ordered(resamplers,current_resample):
        _check(cancel_event)
        resized=resize(source,*geometry.active_size,scale_mode,resample).convert('RGB')
        for preprocess in ordered(preprocessors,current_preprocess):
            _check(cancel_event)
            prepared=text.prepare(resized,preprocess)
            key=prepared.tobytes();setting=dict(resample=resample,preprocess=preprocess)
            if key not in unique:
                unique[key]=len(groups);groups.append([prepared,[]])
            groups[unique[key]][1].append(setting)
    jobs=[(i,group[0],dither) for i,(group,dither) in enumerate(
        (group,dither) for group in groups for dither in profiles)]
    total=sum(len(group[1]) for group in groups)*len(profiles)*len(methods)
    count=worker_count(len(jobs)) if workers is None else max(1,min(int(workers),len(jobs)))
    report=dict(objective='CGA visual error v1: DE00 at three scales, edges and contrast',
        reference='Adjusted original; selected composition; fixed Lanczos; no preprocessing or quantization',
        columns=geometry.columns,height=geometry.height,quantize=quantize,
        dct=asdict(dct_settings),logical_candidates=total,unique_preparation_jobs=len(jobs),
        workers=count,backend=('CUDA: '+device['name'] if use_cuda else 'CPU'),
        fallback_reason=device.get('reason'),completed_candidates=0,cache_hits=0,baseline_error=None,trials=[])
    best=None;best_key=None

    def accept(result):
        nonlocal best,best_key
        if use_cuda and not device_info()['available']:
            report.update(backend='CPU fallback',fallback_reason=device_info().get('reason'))
        index,pixels,(scores,winner),cached=result
        group=groups[index//len(profiles)];profile=profiles[index%len(profiles)]
        report['completed_candidates']+=len(group[1])*len(methods)
        report['cache_hits']+=int(cached)
        report['trials'].append(dict(index=index,settings=group[1],dither=asdict(profile),
                                     scores=dict(zip(methods,scores))))
        if index==0: report['baseline_error']=scores[0]
        key=(winner[0],index,methods.index(winner[1]))
        if best_key is None or key<best_key:
            best_key=key
            best=dict(score=winner[0],method=winner[1],cells=winner[2],diagnostics=winner[3],
                prepared=Image.frombytes('RGB',geometry.active_size,pixels),
                **group[1][0],dither=profile)
        if progress_cb:
            progress_cb(dict(completed=report['completed_candidates'],total=total,
                             best_error=best['score'],workers=report['workers'],backend=report['backend']))

    if count==1:
        context=_context(font,palette,geometry,reference,methods,dct_settings,quantize,cancel_event,
                         backend if use_cuda else 'cpu')
        for job in jobs:
            _check(cancel_event);accept(_evaluate(job,context))
    elif use_cuda:
        # CPU processes perform sequential diffusion in parallel. A small
        # thread pool feeds the shared GPU and scores completed renders on CPU.
        # This avoids a CUDA context and memory pool per CPU process.
        gpu_workers=min(4,count-1 if quantize else count)
        cpu_workers=max(1,count-gpu_workers) if quantize else 0
        report.update(workers=cpu_workers+gpu_workers,cpu_preparation_workers=cpu_workers,
                      gpu_pipeline_workers=gpu_workers)
        spawn=mp.get_context('spawn');cancel=spawn.Event()
        cpu_pool=(ProcessPoolExecutor(max_workers=cpu_workers,mp_context=spawn,initializer=_initialize,
            initargs=(font,palette,geometry,reference,methods,dct_settings,quantize,cancel)) if quantize else None)
        gpu_pool=ThreadPoolExecutor(max_workers=gpu_workers,initializer=_initialize_gpu,
            initargs=(font,palette,geometry,reference,methods,dct_settings,False,cancel,backend))
        pending={};iterator=iter(jobs)
        try:
            while True:
                _check(cancel_event)
                while len(pending)<max(2,report['workers']*2):
                    job=next(iterator,None)
                    if job is None: break
                    if cpu_pool:
                        pending[cpu_pool.submit(_prepare_job,job)]='prepare'
                    else:
                        pending[gpu_pool.submit(_evaluate_gpu,job)]='evaluate'
                if not pending: break
                done,_=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
                for future in done:
                    stage=pending.pop(future)
                    _check(cancel_event)
                    result=future.result()
                    if stage=='prepare':
                        index,prepared=result
                        pending[gpu_pool.submit(_evaluate_gpu,(index,prepared,Dither()))]='evaluate'
                    else: accept(result)
        finally:
            cancel.set()
            for future in pending: future.cancel()
            if cpu_pool: cpu_pool.shutdown(wait=True,cancel_futures=True)
            gpu_pool.shutdown(wait=True,cancel_futures=True)
    else:
        spawn=mp.get_context('spawn');cancel=spawn.Event()
        pool=ProcessPoolExecutor(max_workers=count,mp_context=spawn,initializer=_initialize,
            initargs=(font,palette,geometry,reference,methods,dct_settings,quantize,cancel))
        pending={};iterator=iter(jobs)
        try:
            while True:
                _check(cancel_event)
                while len(pending)<count*2:
                    job=next(iterator,None)
                    if job is None: break
                    pending[pool.submit(_evaluate,job)]=job[0]
                if not pending: break
                done,_=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
                for future in done:
                    del pending[future]
                    _check(cancel_event);accept(future.result())
        finally:
            cancel.set()
            for future in pending: future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
    _check(cancel_event)
    report['trials'].sort(key=lambda trial:trial['index'])
    report.update(best_error=best['score'],seconds=time.perf_counter()-started,
                  selected=dict(method=best['method'],preprocess=best['preprocess'],
                                resample=best['resample'],dither=asdict(best['dither'])))
    if use_cuda and not device_info()['available']:
        report.update(backend='CPU fallback',fallback_reason=device_info().get('reason'))
    best['output']=text.render(best['cells'],font,palette,geometry)
    best['report']=report
    return best
