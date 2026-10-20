"""Optional CUDA scorers for the NEW text search; no approximation to RGB decode.

One thread evaluates one complete candidate (both glyph scanlines). Kernels use
the same integer signal equations and a shared RGB-byte -> Lab lookup table.
No fast-math, half precision, or reduced RGB palette is used.
"""
import numpy as np


REFERENCE_SOURCE = r'''
__device__ int pixel(const unsigned char* image, const unsigned char* candidates,
                    int row, int line, int width, int x, int cell,
                    int left, int middle, int right, int triple) {
    if (x < 0 || x >= width) return 0;
    int c = x / 8, label = -1;
    if (c == cell) label = middle;
    if (triple && c == cell-1) label = left;
    if (triple && c == cell+1) label = right;
    if (label >= 0) return candidates[label*16 + line*8 + (x&7)];
    return image[(row*2+line)*width+x];
}
__device__ double score(const unsigned char* image, const unsigned char* candidates,
                       const float* target, const int* ct, const int* coeff,
                       const float* lab, int row, int cell, int width,
                       int left, int middle, int right, int triple) {
    int lo = cell*8 - (triple ? 0 : 6);
    int hi = cell*8 + (triple ? 7 : 12);
    lo = max(lo, 0); hi = min(hi, width-1);
    double total = 0.0;
    for (int line=0; line<2; ++line) {
        int wave[29], a[21], b[21], lum[21];
        int count = hi-lo+1;
        for(int j=0; j<count+10; ++j) {
            int q = lo-5+j;
            int p = pixel(image,candidates,row,line,width,q,cell,left,middle,right,triple);
            int n = pixel(image,candidates,row,line,width,q+1,cell,left,middle,right,triple);
            wave[j] = ct[(p<<6)|(n<<2)|(q&3)];
        }
        for(int j=0; j<count+2; ++j) {
            int i=j+4;
            a[j] = wave[i-4]-2*(wave[i-2]-wave[i]+wave[i+2])+wave[i+4];
            b[j] = 2*(wave[i-3]-wave[i-1]+wave[i+1]-wave[i+3]);
            lum[j] = 8*wave[i]-a[j];
        }
        for(int j=0; j<count; ++j) {
            int x=lo+j, c=2*lum[j+1], d=lum[j]+lum[j+2];
            int y=(c+d)*256 + coeff[0]*(c-d);
            int aa=a[j+1], bb=b[j+1], i, q;
            switch(x&3) {
                case 0: i=aa; q=bb; break;
                case 1: i=-bb; q=aa; break;
                case 2: i=-aa; q=-bb; break;
                default:i=bb; q=-aa;
            }
            int r=max(0,min(255,(y+coeff[1]*i+coeff[2]*q)>>13));
            int g=max(0,min(255,(y+coeff[3]*i+coeff[4]*q)>>13));
            int blue=max(0,min(255,(y+coeff[5]*i+coeff[6]*q)>>13));
            int rgb=((r<<16)|(g<<8)|blue)*3;
            int t=((row*2+line)*width+x)*3;
            for(int k=0;k<3;++k) {
                double diff=(double)lab[rgb+k]-(double)target[t+k];
                total+=diff*diff;
            }
        }
    }
    return total;
}
extern "C" __global__ void candidate_scores(
    const unsigned char* image, const unsigned char* candidates, const float* target,
    const int* ct,const int* coeff,const float* lab,const int* positions,
    int n,int m,int width,double* output) {
    long long job=(long long)blockIdx.x*blockDim.x+threadIdx.x;
    if(job >= (long long)n*m) return;
    int p=job/n, candidate=job%n;
    output[job]=score(image,candidates,target,ct,coeff,lab,
                      positions[2*p],positions[2*p+1],width,-1,candidate,-1,0);
}
extern "C" __global__ void triple_scores(
    const unsigned char* candidates,const int* domains,const float* target,
    const int* ct,const int* coeff,const float* lab,
    int rows,int cells,int k,double* output) {
    long long job=(long long)blockIdx.x*blockDim.x+threadIdx.x;
    long long size=(long long)rows*cells*k*k*k;
    if(job>=size) return;
    long long v=job;
    int r=v%k; v/=k; int m=v%k; v/=k; int l=v%k; v/=k;
    int cell=v%cells,row=v/cells;
    // Real borders have one legal state. Avoid redundant decoding there.
    if((cell==0 && l!=0)||(cell==cells-1 && r!=0)) {output[job]=1.0/0.0;return;}
    int left=cell>0 ? domains[(row*cells+cell-1)*k+l] : -1;
    int mid=domains[(row*cells+cell)*k+m];
    int right=cell+1<cells ? domains[(row*cells+cell+1)*k+r] : -1;
    output[job]=score(nullptr,candidates,target,ct,coeff,lab,row,cell,cells*8,
                      left,mid,right,1);
}
'''


SOURCE = r'''
// Cached linear integer responses preserve the exact decoder before clipping.
// The candidate dimension is contiguous so adjacent CUDA threads coalesce.
extern "C" __global__ void fixed_context(
    const unsigned char* image,const int* positions,const int* ct,
    const long long* matrix,int m,int width,long long* base) {
    int job=blockIdx.x*blockDim.x+threadIdx.x;
    if(job>=m*2*19*3) return;
    int ch=job%3, pixel=(job/3)%19, line=(job/(3*19))%2, pos=job/(2*19*3);
    int row=positions[pos*2], start=positions[pos*2+1]*8;
    long long value=0;
    for(int j=0;j<50;++j) {
        if(j>=20 && j<=28) continue;
        long long weight=matrix[(pixel*3+ch)*50+j];
        if(!weight) continue;
        int x=start-16+j-4;
        int a=(x-1<0 || x-1>=width) ? 0 : image[(row*2+line)*width+x-1];
        int b=(x<0 || x>=width) ? 0 : image[(row*2+line)*width+x];
        value+=weight*ct[(a<<6)|(b<<2)|((x-1)&3)];
    }
    base[job]=value;
}
extern "C" __global__ void candidate_scores(
    const unsigned char* image,const unsigned char* candidates,const float* target,
    const int* ct,const float* lab,const int* positions,const long long* core,
    const long long* lc,const long long* rc,const long long* base,
    int n,int m,int width,double* output) {
    long long job=(long long)blockIdx.x*blockDim.x+threadIdx.x;
    if(job >= (long long)n*m) return;
    int pos=job/n,candidate=job%n,row=positions[pos*2],start=positions[pos*2+1]*8;
    double total=0;
    for(int line=0;line<2;++line) {
        int left=start ? image[(row*2+line)*width+start-1] : 0;
        int right=start+8<width ? image[(row*2+line)*width+start+8] : 0;
        int lv=ct[(left<<6)|(candidates[candidate*16+line*8]<<2)|3];
        int rv=ct[(candidates[candidate*16+line*8+7]<<6)|(right<<2)|3];
        for(int pixel=0;pixel<19;++pixel) {
            int x=start-6+pixel;
            if(x<0 || x>=width) continue;
            int rgb=0;
            for(int ch=0;ch<3;++ch) {
                long long raw=core[((line*19+pixel)*3+ch)*n+candidate] +
                    base[((pos*2+line)*19+pixel)*3+ch] +
                    lc[pixel*3+ch]*lv + rc[pixel*3+ch]*rv;
                int component=(int)max(0LL,min(255LL,raw>>13));
                rgb=(rgb<<8)|component;
            }
            int t=((row*2+line)*width+x)*3;
            for(int ch=0;ch<3;++ch) {
                double diff=(double)lab[rgb*3+ch]-(double)target[t+ch];
                total+=diff*diff;
            }
        }
    }
    output[job]=total;
}
__device__ double triple_cost(
    const unsigned char* candidates,const int* domains,const float* target,
    const int* ct,const float* lab,const long long* left_core,
    const long long* middle_core,const long long* right_core,
    const long long* lc,const long long* rc,int n,int cells,int k,
    int row,int cell,int l,int m,int r) {
    if((cell==0 && l!=0)||(cell==cells-1 && r!=0)) return 1.0/0.0;
    int left=cell ? domains[(row*cells+cell-1)*k+l] : n-1;
    int mid=domains[(row*cells+cell)*k+m];
    int right=cell+1<cells ? domains[(row*cells+cell+1)*k+r] : n-1;
    double total=0;
    for(int line=0;line<2;++line) {
        int lv=ct[(candidates[left*16+line*8+7]<<6)|(candidates[mid*16+line*8]<<2)|3];
        int rv=ct[(candidates[mid*16+line*8+7]<<6)|(candidates[right*16+line*8]<<2)|3];
        for(int pixel=0;pixel<8;++pixel) {
            int rgb=0;
            for(int ch=0;ch<3;++ch) {
                int offset=((line*8+pixel)*3+ch)*n;
                long long raw=left_core[offset+left]+middle_core[offset+mid]+right_core[offset+right]+
                    lc[pixel*3+ch]*lv+rc[pixel*3+ch]*rv;
                int component=(int)max(0LL,min(255LL,raw>>13));
                rgb=(rgb<<8)|component;
            }
            int t=((row*2+line)*cells*8+cell*8+pixel)*3;
            for(int ch=0;ch<3;++ch) {
                double diff=(double)lab[rgb*3+ch]-(double)target[t+ch];
                total+=diff*diff;
            }
        }
    }
    return total;
}
extern "C" __global__ void triple_scores(
    const unsigned char* candidates,const int* domains,const float* target,
    const int* ct,const float* lab,const long long* left_core,
    const long long* middle_core,const long long* right_core,
    const long long* lc,const long long* rc,int n,int rows,int cells,int k,double* output) {
    long long job=(long long)blockIdx.x*blockDim.x+threadIdx.x;
    if(job >= (long long)rows*cells*k*k*k) return;
    long long v=job;
    int r=v%k;v/=k;int m=v%k;v/=k;int l=v%k;v/=k;
    int cell=v%cells,row=v/cells;
    output[job]=triple_cost(candidates,domains,target,ct,lab,left_core,middle_core,right_core,
                           lc,rc,n,cells,k,row,cell,l,m,r);
}
extern "C" __global__ void triple_cell_scores(
    const unsigned char* candidates,const int* domains,const float* target,
    const int* ct,const float* lab,const long long* left_core,
    const long long* middle_core,const long long* right_core,
    const long long* lc,const long long* rc,int n,int rows,int cells,int k,int cell,double* output) {
    long long job=(long long)blockIdx.x*blockDim.x+threadIdx.x;
    if(job >= (long long)rows*k*k*k) return;
    long long v=job;
    int r=v%k;v/=k;int m=v%k;v/=k;int l=v%k;int row=v/k;
    output[job]=triple_cost(candidates,domains,target,ct,lab,left_core,middle_core,right_core,
                           lc,rc,n,cells,k,row,cell,l,m,r);
}
extern "C" __global__ void chain_step(
    const double* factor,const double* previous,double* next,int* back,double* incumbent,
    int rows,int k,int cell,int last) {
    int job=blockIdx.x*blockDim.x+threadIdx.x;
    if(job>=rows*k*k) return;
    int right=job%k, current=(job/k)%k, row=job/(k*k);
    if(current==0 && right==0) {
        double value=factor[(long long)row*k*k*k];
        incumbent[row]=cell ? incumbent[row]+value : value;
    }
    if(cell==0) {
        next[job]=factor[(long long)row*k*k*k+current*k+right];
    } else if(last) {
        // The final state still names the last two real cells (left,current).
        next[job]=previous[job]+factor[((long long)row*k*k+current*k+right)*k];
    } else {
        double best=1.0/0.0;
        int parent=0;
        for(int left=0;left<k;++left) {
            double value=previous[(row*k+left)*k+current]+
                         factor[(((long long)row*k+left)*k+current)*k+right];
            if(value<best) {best=value;parent=left;}
        }
        next[job]=best;
        back[((long long)cell*rows+row)*k*k+current*k+right]=parent;
    }
}
extern "C" __global__ void chain_trace(
    const double* scores,const int* back,const double* incumbent,int rows,int cells,int k,int* labels) {
    int row=blockIdx.x*blockDim.x+threadIdx.x;
    if(row>=rows) return;
    double best=1.0/0.0;
    int arg=0;
    for(int state=0;state<k*k;++state) {
        double value=scores[row*k*k+state];
        if(value<best) {best=value;arg=state;}
    }
    if(incumbent[row]<=best) {
        for(int cell=0;cell<cells;++cell) labels[row*cells+cell]=0;
        return;
    }
    int left=arg/k,current=arg%k;
    if(cells==1) {labels[row]=left;return;}
    labels[row*cells+cells-2]=left;
    labels[row*cells+cells-1]=current;
    for(int cell=cells-2;cell>0;--cell) {
        int parent=back[((long long)cell*rows+row)*k*k+left*k+current];
        labels[row*cells+cell-1]=parent;
        current=left;left=parent;
    }
}
'''


class CudaScorer:
    """Bounded batches keep memory use and cancellation latency predictable."""
    def __init__(self, candidates, target, ct, coeffs, lab_table, device_id=0):
        import cupy as cp
        from cga_text_new_cpu import prepare_candidates, _triple_responses
        self.cp = cp
        self.device = cp.cuda.Device(device_id)
        self.device.use()
        props = cp.cuda.runtime.getDeviceProperties(device_id)
        self.name = 'CUDA / ' + props['name'].decode()
        self.workers = int(props['multiProcessorCount'])
        core, lc, rc, matrix, _ = prepare_candidates(candidates,ct,coeffs)
        padded, triple_cores, tlc, trc = _triple_responses(candidates,ct,coeffs)
        # Raw kernels use flat row-major indexing. cp.asarray defaults to
        # preserving Fortran order, so every kernel input explicitly uses C.
        self.candidates = cp.asarray(padded, dtype=cp.uint8, order='C')
        self.core = cp.asarray(core.transpose(1,2,3,0), order='C')
        self.lc, self.rc = cp.asarray(lc,order='C'),cp.asarray(rc,order='C')
        self.matrix = cp.asarray(matrix,order='C')
        self.triple_cores = [cp.asarray(c.transpose(1,2,3,0),order='C') for c in triple_cores]
        self.tlc,self.trc = cp.asarray(tlc,order='C'),cp.asarray(trc,order='C')
        self.target = cp.asarray(target, dtype=cp.float32, order='C')
        self.ct = cp.asarray(ct, dtype=cp.int32, order='C')
        self.coeffs = cp.asarray(coeffs, dtype=cp.int32, order='C')
        self.lab = cp.asarray(lab_table, dtype=cp.float32, order='C')
        self.n = len(candidates)
        self.width = target.shape[2]
        self.candidate_kernel = cp.RawKernel(SOURCE, 'candidate_scores', options=('--fmad=false',))
        self.triple_kernel = cp.RawKernel(SOURCE, 'triple_scores', options=('--fmad=false',))
        self.context_kernel = cp.RawKernel(SOURCE, 'fixed_context', options=('--fmad=false',))
        self.cell_kernel = cp.RawKernel(SOURCE, 'triple_cell_scores', options=('--fmad=false',))
        self.step_kernel = cp.RawKernel(SOURCE, 'chain_step', options=('--fmad=false',))
        self.trace_kernel = cp.RawKernel(SOURCE, 'chain_trace', options=('--fmad=false',))
        # Force compilation/device availability checks before selecting this backend.
        self.candidate_kernel.compile()
        self.triple_kernel.compile()
        self.context_kernel.compile()
        self.cell_kernel.compile()
        self.step_kernel.compile()
        self.trace_kernel.compile()

    def _score_batch(self,pixels,pos):
        cp=self.cp
        pixels=cp.ascontiguousarray(pixels,dtype=cp.uint8)
        pos=cp.ascontiguousarray(pos,dtype=cp.int32)
        base=cp.empty((len(pos),2,19,3),dtype=cp.int64)
        self.context_kernel(((base.size+127)//128,),(128,),
            (pixels,pos,self.ct,self.matrix,np.int32(len(pos)),np.int32(self.width),base))
        scores=cp.empty((len(pos),self.n),dtype=cp.float64)
        self.candidate_kernel(((scores.size+127)//128,),(128,),
            (pixels,self.candidates,self.target,self.ct,self.lab,pos,self.core,self.lc,self.rc,base,
             np.int32(self.n),np.int32(len(pos)),np.int32(self.width),scores))
        return scores

    def rank(self, pixels, positions, count, cancelled=lambda: False):
        cp = self.cp
        pixels = cp.asarray(pixels, dtype=cp.uint8, order='C')
        result = np.empty((len(positions), count), dtype=np.int32)
        for start in range(0, len(positions), 64):
            if cancelled():
                from cga_text_new import Cancelled
                raise Cancelled()
            # np.argwhere yields a Fortran-order (N,2) array. A full batch of
            # <=64 positions otherwise retains that layout, unlike slices of
            # larger batches, and flat kernels misread the row/cell pairs.
            pos = cp.asarray(positions[start:start+64], dtype=cp.int32, order='C')
            scores = self._score_batch(pixels,pos)
            # Stable rank gives reproducible candidate IDs at equal cost.
            best = cp.argsort(scores, axis=1, kind='stable')[:, :count]
            result[start:start+len(pos)] = cp.asnumpy(best)
        return result

    def factors(self, domains, row_indices):
        cp = self.cp
        rows, cells, k = domains.shape
        output = cp.empty((rows,cells,k,k,k), dtype=cp.float64)
        jobs = output.size
        self.triple_kernel(((jobs+127)//128,), (128,),
            (self.candidates,cp.asarray(domains,dtype=cp.int32,order='C'),
             cp.ascontiguousarray(self.target[row_indices]),
             self.ct,self.lab,*self.triple_cores,self.tlc,self.trc,np.int32(self.n+1),
             np.int32(rows),np.int32(cells),np.int32(k),output))
        return cp.asnumpy(output)

    def fuse(self,domains,row_indices,cancelled=lambda:False):
        """Exact pair-state DP entirely on GPU; transfer only chosen labels.

        Batched image rows stream one column of triple factors at a time. A
        single causal row batches its columns when memory permits. Traceback
        stays on device. Tie behavior matches solve_chain, including keeping
        domain-zero incumbents.
        """
        cp=self.cp
        rows,cells,k=domains.shape
        domain_gpu=cp.asarray(domains,dtype=cp.int32,order='C')
        target=cp.ascontiguousarray(self.target[row_indices])
        factor=cp.empty((rows,k,k,k),dtype=cp.float64)
        scores=cp.empty((rows,k,k),dtype=cp.float64)
        next_scores=cp.empty_like(scores)
        back=cp.empty((cells,rows,k,k),dtype=cp.int32)
        incumbent=cp.empty(rows,dtype=cp.float64)
        labels=cp.empty((rows,cells),dtype=cp.int32)
        shared=(self.candidates,domain_gpu,target,self.ct,self.lab,*self.triple_cores,
                self.tlc,self.trc,np.int32(self.n+1),np.int32(rows),np.int32(cells),np.int32(k))
        stream=cp.cuda.get_current_stream()
        # Causal diffusion supplies one row at a time. Score all of that row's
        # columns together for GPU occupancy, then retain the exact ordered DP.
        # K=64 at 80 cells costs 160 MiB; low-memory devices keep the streaming
        # path. No factors are approximated or omitted in either path.
        all_factors=None
        factor_bytes=rows*cells*k*k*k*np.dtype(np.float64).itemsize
        if rows==1 and factor_bytes <= (256 << 20):
            try:
                all_factors=cp.empty((rows,cells,k,k,k),dtype=cp.float64)
            except cp.cuda.memory.OutOfMemoryError:
                pass
            if all_factors is not None:
                self.triple_kernel(((all_factors.size+127)//128,),(128,),
                                   (*shared,all_factors))
                stream.synchronize()
        for cell in range(cells):
            if cancelled():
                from cga_text_new import Cancelled
                raise Cancelled()
            if all_factors is None:
                self.cell_kernel(((factor.size+127)//128,),(128,),
                                 (*shared,np.int32(cell),factor))
            else:
                factor=all_factors[:,cell]
            self.step_kernel(((scores.size+127)//128,),(128,),
                (factor,scores,next_scores,back,incumbent,np.int32(rows),np.int32(k),
                 np.int32(cell),np.int32(cell==cells-1)))
            scores,next_scores=next_scores,scores
            # Bound STOP latency and surface asynchronous driver errors while
            # preserving the current row solution for the CPU fallback.
            if all_factors is None or (cell+1)%8==0 or cell==cells-1:
                stream.synchronize()
        self.trace_kernel(((rows+127)//128,),(128,),
            (scores,back,incumbent,np.int32(rows),np.int32(cells),np.int32(k),labels))
        result=cp.asnumpy(labels)
        if cancelled():
            from cga_text_new import Cancelled
            raise Cancelled()
        return result
