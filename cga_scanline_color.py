"""Display-referred sRGB, linear-light mixtures, and CIEDE2000 for CGA rows.

No CRT gamma or exposure correction is applied. Palette bytes and input image
bytes describe the same sRGB display space; only mixing/error transport is linear.
"""
import numpy as np

XYZ = np.array([[.4124564,.3575761,.1804375],
                [.2126729,.7151522,.0721750],
                [.0193339,.1191920,.9503041]])
WHITE = np.array([.95047,1.,1.08883])


def srgb_to_linear(rgb):
    value = np.clip(np.asarray(rgb,dtype=np.float64)/255.,0,1)
    return np.where(value <= .04045,value/12.92,((value+.055)/1.055)**2.4)


def linear_to_srgb(light):
    value = np.clip(np.asarray(light,dtype=np.float64),0,1)
    return np.rint(255*np.where(value <= .0031308,12.92*value,
                                1.055*value**(1/2.4)-.055)).astype(np.uint8)


def linear_to_lab(light):
    xyz = np.asarray(light,dtype=np.float64)@XYZ.T/WHITE
    f = np.where(xyz > (6/29)**3,np.cbrt(xyz),xyz/(3*(6/29)**2)+4/29)
    return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),
                     200*(f[...,1]-f[...,2])),axis=-1)


def delta_e_2000(first,second):
    """Broadcasting CIEDE2000, kL=kC=kH=1, including achromatic branches."""
    x,y = np.asarray(first,dtype=np.float64),np.asarray(second,dtype=np.float64)
    l1,a1,b1 = np.moveaxis(x,-1,0)
    l2,a2,b2 = np.moveaxis(y,-1,0)
    c1,c2 = np.hypot(a1,b1),np.hypot(a2,b2)
    cm = (c1+c2)/2
    g = .5*(1-np.sqrt(cm**7/(cm**7+25**7)))
    ap1,ap2 = (1+g)*a1,(1+g)*a2
    cp1,cp2 = np.hypot(ap1,b1),np.hypot(ap2,b2)
    h1 = np.mod(np.degrees(np.arctan2(b1,ap1)),360)
    h2 = np.mod(np.degrees(np.arctan2(b2,ap2)),360)
    zero = cp1*cp2 == 0
    dh = h2-h1
    dh = np.where(zero,0,np.where(dh>180,dh-360,np.where(dh < -180,dh+360,dh)))
    dl,dc = l2-l1,cp2-cp1
    dh = 2*np.sqrt(cp1*cp2)*np.sin(np.radians(dh/2))
    lm,cp = (l1+l2)/2,(cp1+cp2)/2
    hm = np.where(zero,h1+h2,np.where(np.abs(h1-h2)<=180,(h1+h2)/2,
        np.where(h1+h2<360,(h1+h2+360)/2,(h1+h2-360)/2)))
    t = (1-.17*np.cos(np.radians(hm-30))+.24*np.cos(np.radians(2*hm))
         +.32*np.cos(np.radians(3*hm+6))-.20*np.cos(np.radians(4*hm-63)))
    sl = 1+.015*(lm-50)**2/np.sqrt(20+(lm-50)**2)
    sc,sh = 1+.045*cp,1+.015*cp*t
    rt = -2*np.sqrt(cp**7/(cp**7+25**7))*np.sin(
        np.radians(60*np.exp(-((hm-275)/25)**2)))
    v,w,z = dl/sl,dc/sc,dh/sh
    return np.sqrt(np.maximum(0,v*v+w*w+z*z+rt*w*z))
