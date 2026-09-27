; Raw linear disassembly of unpacked loader; embedded data may decode as false instructions.
0100  bd7a0e             mov bp, 0xe7a
0103  8be5               mov sp, bp
0105  c746000000         mov word ptr [bp], 0
010A  8c061a62           mov word ptr [0x621a], es
010E  e8fe07             call 0x90f
0111  e80502             call 0x319
0114  e85b07             call 0x872
0117  33c0               xor ax, ax
0119  50                 push ax
011A  e8b300             call 0x1d0
011D  e85301             call 0x273
0120  b401               mov ah, 1
0122  cdf0               int 0xf0
0124  2ec6067c0e01       mov byte ptr cs:[0xe7c], 1
012A  e83100             call 0x15e
012D  a1f50f             mov ax, word ptr [0xff5]
0130  50                 push ax
0131  e87000             call 0x1a4
0134  8b361c62           mov si, word ptr [0x621c]
0138  8a04               mov al, byte ptr [si]
013A  3c0c               cmp al, 0xc
013C  7713               ja 0x151
013E  33db               xor bx, bx
0140  8ad8               mov bl, al
0142  d1e3               shl bx, 1
0144  2eff97ea0c         call word ptr cs:[bx + 0xcea]
0149  0e                 push cs
014A  1f                 pop ds
014B  ff06f50f           inc word ptr [0xff5]
014F  ebd9               jmp 0x12a
0151  50                 push ax
0152  55                 push bp
0153  8bec               mov bp, sp
0155  c746022816         mov word ptr [bp + 2], 0x1628
015A  5d                 pop bp
015B  e8c506             call 0x823
015E  e460               in al, 0x60
0160  fec8               dec al
0162  750d               jne 0x171
0164  50                 push ax
0165  55                 push bp
0166  8bec               mov bp, sp
0168  c74602d316         mov word ptr [bp + 2], 0x16d3
016D  5d                 pop bp
016E  e8b206             call 0x823
0171  c3                 ret 
0172  0e                 push cs
0173  1f                 pop ds
0174  2e803e7c0e00       cmp byte ptr cs:[0xe7c], 0
017A  7423               je 0x19f
017C  b402               mov ah, 2
017E  cdf0               int 0xf0
0180  e80f02             call 0x392
0183  2ec6067c0e00       mov byte ptr cs:[0xe7c], 0
0189  50                 push ax
018A  55                 push bp
018B  8bec               mov bp, sp
018D  c746020000         mov word ptr [bp + 2], 0
0192  5d                 pop bp
0193  e87102             call 0x407
0196  a14a66             mov ax, word ptr [0x664a]
0199  e80608             call 0x9a2
019C  e8bc00             call 0x25b
019F  b8004c             mov ax, 0x4c00
01A2  cd21               int 0x21
01A4  55                 push bp
01A5  8bec               mov bp, sp
01A7  1e                 push ds
01A8  50                 push ax
01A9  56                 push si
01AA  0e                 push cs
01AB  1f                 pop ds
01AC  8b4604             mov ax, word ptr [bp + 4]
01AF  d1e0               shl ax, 1
01B1  d1e0               shl ax, 1
01B3  d1e0               shl ax, 1
01B5  d1e0               shl ax, 1
01B7  d1e0               shl ax, 1
01B9  d1e0               shl ax, 1
01BB  8bf0               mov si, ax
01BD  81c61817           add si, 0x1718
01C1  89361c62           mov word ptr [0x621c], si
01C5  8c1e1e62           mov word ptr [0x621e], ds
01C9  5e                 pop si
01CA  58                 pop ax
01CB  1f                 pop ds
01CC  5d                 pop bp
01CD  c20200             ret 2
01D0  55                 push bp
01D1  8bec               mov bp, sp
01D3  1e                 push ds
01D4  50                 push ax
01D5  56                 push si
01D6  0e                 push cs
01D7  1f                 pop ds
01D8  8b4604             mov ax, word ptr [bp + 4]
01DB  d1e0               shl ax, 1
01DD  d1e0               shl ax, 1
01DF  d1e0               shl ax, 1
01E1  d1e0               shl ax, 1
01E3  d1e0               shl ax, 1
01E5  d1e0               shl ax, 1
01E7  8bf0               mov si, ax
01E9  81c6f90f           add si, 0xff9
01ED  89362062           mov word ptr [0x6220], si
01F1  8c1e2262           mov word ptr [0x6222], ds
01F5  5e                 pop si
01F6  58                 pop ax
01F7  1f                 pop ds
01F8  5d                 pop bp
01F9  c20200             ret 2
01FC  55                 push bp
01FD  8bec               mov bp, sp
01FF  1e                 push ds
0200  56                 push si
0201  50                 push ax
0202  51                 push cx
0203  52                 push dx
0204  c57604             lds si, ptr [bp + 4]
0207  b9d007             mov cx, 0x7d0
020A  ac                 lodsb al, byte ptr [si]
020B  0ac0               or al, al
020D  7408               je 0x217
020F  8ad0               mov dl, al
0211  b402               mov ah, 2
0213  cd21               int 0x21
0215  e2f3               loop 0x20a
0217  5a                 pop dx
0218  59                 pop cx
0219  58                 pop ax
021A  5e                 pop si
021B  1f                 pop ds
021C  5d                 pop bp
021D  c20400             ret 4
0220  55                 push bp
0221  8bec               mov bp, sp
0223  1e                 push ds
0224  56                 push si
0225  53                 push bx
0226  55                 push bp
0227  50                 push ax
0228  51                 push cx
0229  c57604             lds si, ptr [bp + 4]
022C  33db               xor bx, bx
022E  33c0               xor ax, ax
0230  ac                 lodsb al, byte ptr [si]
0231  91                 xchg cx, ax
0232  ac                 lodsb al, byte ptr [si]
0233  b40e               mov ah, 0xe
0235  cd10               int 0x10
0237  e2f9               loop 0x232
0239  59                 pop cx
023A  58                 pop ax
023B  5d                 pop bp
023C  5b                 pop bx
023D  5e                 pop si
023E  1f                 pop ds
023F  5d                 pop bp
0240  c20400             ret 4
0243  53                 push bx
0244  8bd8               mov bx, ax
0246  b448               mov ah, 0x48
0248  cd21               int 0x21
024A  7202               jb 0x24e
024C  5b                 pop bx
024D  c3                 ret 
024E  50                 push ax
024F  55                 push bp
0250  8bec               mov bp, sp
0252  c746024f16         mov word ptr [bp + 2], 0x164f
0257  5d                 pop bp
0258  e8c805             call 0x823
025B  06                 push es
025C  8ec0               mov es, ax
025E  b449               mov ah, 0x49
0260  cd21               int 0x21
0262  7202               jb 0x266
0264  07                 pop es
0265  c3                 ret 
0266  50                 push ax
0267  55                 push bp
0268  8bec               mov bp, sp
026A  c746026916         mov word ptr [bp + 2], 0x1669
026F  5d                 pop bp
0270  e8b005             call 0x823
0273  50                 push ax
0274  55                 push bp
0275  8bec               mov bp, sp
0277  c746025051         mov word ptr [bp + 2], 0x5150
027C  5d                 pop bp
027D  e88701             call 0x407
0280  c70632625407       mov word ptr [0x6232], 0x754
0286  8c0e3462           mov word ptr [0x6234], cs
028A  50                 push ax
028B  53                 push bx
028C  1e                 push ds
028D  33c0               xor ax, ax
028F  50                 push ax
0290  0e                 push cs
0291  1f                 pop ds
0292  a13262             mov ax, word ptr [0x6232]
0295  8b1e3462           mov bx, word ptr [0x6234]
0299  1f                 pop ds
029A  9c                 pushf 
029B  fa                 cli 
029C  891e8200           mov word ptr [0x82], bx
02A0  a38000             mov word ptr [0x80], ax
02A3  9d                 popf 
02A4  1f                 pop ds
02A5  5b                 pop bx
02A6  58                 pop ax
02A7  c70642626207       mov word ptr [0x6242], 0x762
02AD  8c0e4462           mov word ptr [0x6244], cs
02B1  50                 push ax
02B2  53                 push bx
02B3  1e                 push ds
02B4  33c0               xor ax, ax
02B6  50                 push ax
02B7  0e                 push cs
02B8  1f                 pop ds
02B9  a14262             mov ax, word ptr [0x6242]
02BC  8b1e4462           mov bx, word ptr [0x6244]
02C0  1f                 pop ds
02C1  9c                 pushf 
02C2  fa                 cli 
02C3  891ec603           mov word ptr [0x3c6], bx
02C7  a3c403             mov word ptr [0x3c4], ax
02CA  9d                 popf 
02CB  1f                 pop ds
02CC  5b                 pop bx
02CD  58                 pop ax
02CE  c7063a62240a       mov word ptr [0x623a], 0xa24
02D4  8c0e3c62           mov word ptr [0x623c], cs
02D8  50                 push ax
02D9  53                 push bx
02DA  1e                 push ds
02DB  33c0               xor ax, ax
02DD  50                 push ax
02DE  0e                 push cs
02DF  1f                 pop ds
02E0  a13a62             mov ax, word ptr [0x623a]
02E3  8b1e3c62           mov bx, word ptr [0x623c]
02E7  1f                 pop ds
02E8  9c                 pushf 
02E9  fa                 cli 
02EA  891ec203           mov word ptr [0x3c2], bx
02EE  a3c003             mov word ptr [0x3c0], ax
02F1  9d                 popf 
02F2  1f                 pop ds
02F3  5b                 pop bx
02F4  58                 pop ax
02F5  c7062a62480a       mov word ptr [0x622a], 0xa48
02FB  8c0e2c62           mov word ptr [0x622c], cs
02FF  b80158             mov ax, 0x5801
0302  bb0200             mov bx, 2
0305  cd21               int 0x21
0307  b80010             mov ax, 0x1000
030A  e836ff             call 0x243
030D  a34a66             mov word ptr [0x664a], ax
0310  b80158             mov ax, 0x5801
0313  bb0100             mov bx, 1
0316  cd21               int 0x21
0318  c3                 ret 
0319  56                 push si
031A  06                 push es
031B  57                 push di
031C  50                 push ax
031D  1e                 push ds
031E  06                 push es
031F  0e                 push cs
0320  1f                 pop ds
0321  33c0               xor ax, ax
0323  8ec0               mov es, ax
0325  26a12000           mov ax, word ptr es:[0x20]
0329  a32662             mov word ptr [0x6226], ax
032C  26a12200           mov ax, word ptr es:[0x22]
0330  a32862             mov word ptr [0x6228], ax
0333  07                 pop es
0334  1f                 pop ds
0335  58                 pop ax
0336  50                 push ax
0337  1e                 push ds
0338  06                 push es
0339  0e                 push cs
033A  1f                 pop ds
033B  33c0               xor ax, ax
033D  8ec0               mov es, ax
033F  26a18000           mov ax, word ptr es:[0x80]
0343  a32e62             mov word ptr [0x622e], ax
0346  26a18200           mov ax, word ptr es:[0x82]
034A  a33062             mov word ptr [0x6230], ax
034D  07                 pop es
034E  1f                 pop ds
034F  58                 pop ax
0350  50                 push ax
0351  1e                 push ds
0352  06                 push es
0353  0e                 push cs
0354  1f                 pop ds
0355  33c0               xor ax, ax
0357  8ec0               mov es, ax
0359  26a1c003           mov ax, word ptr es:[0x3c0]
035D  a33662             mov word ptr [0x6236], ax
0360  26a1c203           mov ax, word ptr es:[0x3c2]
0364  a33862             mov word ptr [0x6238], ax
0367  07                 pop es
0368  1f                 pop ds
0369  58                 pop ax
036A  50                 push ax
036B  1e                 push ds
036C  06                 push es
036D  0e                 push cs
036E  1f                 pop ds
036F  33c0               xor ax, ax
0371  8ec0               mov es, ax
0373  26a1c403           mov ax, word ptr es:[0x3c4]
0377  a33e62             mov word ptr [0x623e], ax
037A  26a1c603           mov ax, word ptr es:[0x3c6]
037E  a34062             mov word ptr [0x6240], ax
0381  07                 pop es
0382  1f                 pop ds
0383  58                 pop ax
0384  be2662             mov si, 0x6226
0387  0e                 push cs
0388  07                 pop es
0389  bfb70a             mov di, 0xab7
038C  a5                 movsw word ptr es:[di], word ptr [si]
038D  a5                 movsw word ptr es:[di], word ptr [si]
038E  5f                 pop di
038F  07                 pop es
0390  5e                 pop si
0391  c3                 ret 
0392  50                 push ax
0393  53                 push bx
0394  1e                 push ds
0395  33c0               xor ax, ax
0397  50                 push ax
0398  0e                 push cs
0399  1f                 pop ds
039A  a12662             mov ax, word ptr [0x6226]
039D  8b1e2862           mov bx, word ptr [0x6228]
03A1  1f                 pop ds
03A2  9c                 pushf 
03A3  fa                 cli 
03A4  891e2200           mov word ptr [0x22], bx
03A8  a32000             mov word ptr [0x20], ax
03AB  9d                 popf 
03AC  1f                 pop ds
03AD  5b                 pop bx
03AE  58                 pop ax
03AF  50                 push ax
03B0  53                 push bx
03B1  1e                 push ds
03B2  33c0               xor ax, ax
03B4  50                 push ax
03B5  0e                 push cs
03B6  1f                 pop ds
03B7  a12e62             mov ax, word ptr [0x622e]
03BA  8b1e3062           mov bx, word ptr [0x6230]
03BE  1f                 pop ds
03BF  9c                 pushf 
03C0  fa                 cli 
03C1  891e8200           mov word ptr [0x82], bx
03C5  a38000             mov word ptr [0x80], ax
03C8  9d                 popf 
03C9  1f                 pop ds
03CA  5b                 pop bx
03CB  58                 pop ax
03CC  50                 push ax
03CD  53                 push bx
03CE  1e                 push ds
03CF  33c0               xor ax, ax
03D1  50                 push ax
03D2  0e                 push cs
03D3  1f                 pop ds
03D4  a13662             mov ax, word ptr [0x6236]
03D7  8b1e3862           mov bx, word ptr [0x6238]
03DB  1f                 pop ds
03DC  9c                 pushf 
03DD  fa                 cli 
03DE  891ec203           mov word ptr [0x3c2], bx
03E2  a3c003             mov word ptr [0x3c0], ax
03E5  9d                 popf 
03E6  1f                 pop ds
03E7  5b                 pop bx
03E8  58                 pop ax
03E9  50                 push ax
03EA  53                 push bx
03EB  1e                 push ds
03EC  33c0               xor ax, ax
03EE  50                 push ax
03EF  0e                 push cs
03F0  1f                 pop ds
03F1  a13e62             mov ax, word ptr [0x623e]
03F4  8b1e4062           mov bx, word ptr [0x6240]
03F8  1f                 pop ds
03F9  9c                 pushf 
03FA  fa                 cli 
03FB  891ec603           mov word ptr [0x3c6], bx
03FF  a3c403             mov word ptr [0x3c4], ax
0402  9d                 popf 
0403  1f                 pop ds
0404  5b                 pop bx
0405  58                 pop ax
0406  c3                 ret 
0407  55                 push bp
0408  8bec               mov bp, sp
040A  50                 push ax
040B  06                 push es
040C  57                 push di
040D  33c0               xor ax, ax
040F  8ec0               mov es, ax
0411  bff000             mov di, 0xf0
0414  8b4604             mov ax, word ptr [bp + 4]
0417  268905             mov word ptr es:[di], ax
041A  5f                 pop di
041B  07                 pop es
041C  58                 pop ax
041D  5d                 pop bp
041E  c20200             ret 2
0421  53                 push bx
0422  51                 push cx
0423  52                 push dx
0424  56                 push si
0425  bbf90f             mov bx, 0xff9
0428  b91800             mov cx, 0x18
042B  33d2               xor dx, dx
042D  8bc2               mov ax, dx
042F  42                 inc dx
0430  d1e0               shl ax, 1
0432  d1e0               shl ax, 1
0434  d1e0               shl ax, 1
0436  d1e0               shl ax, 1
0438  d1e0               shl ax, 1
043A  d1e0               shl ax, 1
043C  8bf0               mov si, ax
043E  32e4               xor ah, ah
0440  8a00               mov al, byte ptr [bx + si]
0442  0ac0               or al, al
0444  740f               je 0x455
0446  e2e5               loop 0x42d
0448  50                 push ax
0449  55                 push bp
044A  8bec               mov bp, sp
044C  c746024016         mov word ptr [bp + 2], 0x1640
0451  5d                 pop bp
0452  e8ce03             call 0x823
0455  8bc2               mov ax, dx
0457  48                 dec ax
0458  5e                 pop si
0459  5a                 pop dx
045A  59                 pop cx
045B  5b                 pop bx
045C  c3                 ret 
045D  8b361c62           mov si, word ptr [0x621c]
0461  8b3e2062           mov di, word ptr [0x6220]
0465  8b440e             mov ax, word ptr [si + 0xe]
0468  894510             mov word ptr [di + 0x10], ax
046B  8b5c10             mov bx, word ptr [si + 0x10]
046E  895d14             mov word ptr [di + 0x14], bx
0471  803d02             cmp byte ptr [di], 2
0474  7508               jne 0x47e
0476  8b4412             mov ax, word ptr [si + 0x12]
0479  050800             add ax, 8
047C  eb00               jmp 0x47e
047E  40                 inc ax
047F  c3                 ret 
0480  50                 push ax
0481  53                 push bx
0482  56                 push si
0483  57                 push di
0484  51                 push cx
0485  e899ff             call 0x421
0488  a3f70f             mov word ptr [0xff7], ax
048B  ff36f50f           push word ptr [0xff5]
048F  50                 push ax
0490  50                 push ax
0491  55                 push bp
0492  8bec               mov bp, sp
0494  c746020100         mov word ptr [bp + 2], 1
0499  5d                 pop bp
049A  e8f300             call 0x590
049D  e8bdff             call 0x45d
04A0  894512             mov word ptr [di + 0x12], ax
04A3  e89dfd             call 0x243
04A6  89450e             mov word ptr [di + 0xe], ax
04A9  8d5d01             lea bx, [di + 1]
04AC  8b4d14             mov cx, word ptr [di + 0x14]
04AF  1e                 push ds
04B0  53                 push bx
04B1  50                 push ax
04B2  50                 push ax
04B3  55                 push bp
04B4  8bec               mov bp, sp
04B6  c746020000         mov word ptr [bp + 2], 0
04BB  5d                 pop bp
04BC  51                 push cx
04BD  e80504             call 0x8c5
04C0  59                 pop cx
04C1  5f                 pop di
04C2  5e                 pop si
04C3  5b                 pop bx
04C4  58                 pop ax
04C5  c3                 ret 
04C6  50                 push ax
04C7  53                 push bx
04C8  56                 push si
04C9  57                 push di
04CA  06                 push es
04CB  51                 push cx
04CC  e852ff             call 0x421
04CF  a3f70f             mov word ptr [0xff7], ax
04D2  ff36f50f           push word ptr [0xff5]
04D6  50                 push ax
04D7  50                 push ax
04D8  55                 push bp
04D9  8bec               mov bp, sp
04DB  c746020200         mov word ptr [bp + 2], 2
04E0  5d                 pop bp
04E1  e8ac00             call 0x590
04E4  e876ff             call 0x45d
04E7  051000             add ax, 0x10
04EA  894512             mov word ptr [di + 0x12], ax
04ED  e853fd             call 0x243
04F0  89450e             mov word ptr [di + 0xe], ax
04F3  8bf7               mov si, di
04F5  8d5c01             lea bx, [si + 1]
04F8  8b4c14             mov cx, word ptr [si + 0x14]
04FB  1e                 push ds
04FC  53                 push bx
04FD  50                 push ax
04FE  50                 push ax
04FF  55                 push bp
0500  8bec               mov bp, sp
0502  c746020001         mov word ptr [bp + 2], 0x100
0507  5d                 pop bp
0508  51                 push cx
0509  e8b903             call 0x8c5
050C  8ec0               mov es, ax
050E  33ff               xor di, di
0510  26c705cd20         mov word ptr es:[di], 0x20cd
0515  8bd8               mov bx, ax
0517  035c12             add bx, word ptr [si + 0x12]
051A  26895d02           mov word ptr es:[di + 2], bx
051E  2ea12c00           mov ax, word ptr cs:[0x2c]
0522  2689452c           mov word ptr es:[di + 0x2c], ax
0526  ff36f70f           push word ptr [0xff7]
052A  e80700             call 0x534
052D  59                 pop cx
052E  07                 pop es
052F  5f                 pop di
0530  5e                 pop si
0531  5b                 pop bx
0532  58                 pop ax
0533  c3                 ret 
0534  55                 push bp
0535  8bec               mov bp, sp
0537  56                 push si
0538  50                 push ax
0539  06                 push es
053A  ff7604             push word ptr [bp + 4]
053D  e890fc             call 0x1d0
0540  8b362062           mov si, word ptr [0x6220]
0544  9c                 pushf 
0545  58                 pop ax
0546  80e4f0             and ah, 0xf0
0549  80cc02             or ah, 2
054C  b002               mov al, 2
054E  89441e             mov word ptr [si + 0x1e], ax
0551  8e440e             mov es, word ptr [si + 0xe]
0554  b80001             mov ax, 0x100
0557  894416             mov word ptr [si + 0x16], ax
055A  8c4418             mov word ptr [si + 0x18], es
055D  89441a             mov word ptr [si + 0x1a], ax
0560  8c441c             mov word ptr [si + 0x1c], es
0563  8c4420             mov word ptr [si + 0x20], es
0566  8c4424             mov word ptr [si + 0x24], es
0569  8c4428             mov word ptr [si + 0x28], es
056C  8b4412             mov ax, word ptr [si + 0x12]
056F  3dfe0f             cmp ax, 0xffe
0572  7603               jbe 0x577
0574  b8fe0f             mov ax, 0xffe
0577  d1e0               shl ax, 1
0579  d1e0               shl ax, 1
057B  d1e0               shl ax, 1
057D  d1e0               shl ax, 1
057F  48                 dec ax
0580  48                 dec ax
0581  89442a             mov word ptr [si + 0x2a], ax
0584  c74432ff00         mov word ptr [si + 0x32], 0xff
0589  07                 pop es
058A  58                 pop ax
058B  5e                 pop si
058C  5d                 pop bp
058D  c20200             ret 2
0590  55                 push bp
0591  8bec               mov bp, sp
0593  50                 push ax
0594  1e                 push ds
0595  56                 push si
0596  06                 push es
0597  57                 push di
0598  51                 push cx
0599  ff7606             push word ptr [bp + 6]
059C  e831fc             call 0x1d0
059F  c43e2062           les di, ptr [0x6220]
05A3  8a4604             mov al, byte ptr [bp + 4]
05A6  268805             mov byte ptr es:[di], al
05A9  8b361c62           mov si, word ptr [0x621c]
05AD  46                 inc si
05AE  47                 inc di
05AF  b90d00             mov cx, 0xd
05B2  fc                 cld 
05B3  f3a4               rep movsb byte ptr es:[di], byte ptr [si]
05B5  59                 pop cx
05B6  5f                 pop di
05B7  07                 pop es
05B8  5e                 pop si
05B9  1f                 pop ds
05BA  58                 pop ax
05BB  5d                 pop bp
05BC  c20600             ret 6
05BF  55                 push bp
05C0  8bec               mov bp, sp
05C2  51                 push cx
05C3  52                 push dx
05C4  1e                 push ds
05C5  56                 push si
05C6  06                 push es
05C7  57                 push di
05C8  53                 push bx
05C9  b218               mov dl, 0x18
05CB  c47e04             les di, ptr [bp + 4]
05CE  0e                 push cs
05CF  1f                 pop ds
05D0  bef90f             mov si, 0xff9
05D3  83c601             add si, 1
05D6  fc                 cld 
05D7  33c0               xor ax, ax
05D9  b90d00             mov cx, 0xd
05DC  8bd9               mov bx, cx
05DE  f3a6               repe cmpsb byte ptr [si], byte ptr es:[di]
05E0  80f900             cmp cl, 0
05E3  7411               je 0x5f6
05E5  2bd9               sub bx, cx
05E7  2bfb               sub di, bx
05E9  2bf3               sub si, bx
05EB  83c640             add si, 0x40
05EE  40                 inc ax
05EF  feca               dec dl
05F1  75e6               jne 0x5d9
05F3  f9                 stc 
05F4  eb01               jmp 0x5f7
05F6  f8                 clc 
05F7  5b                 pop bx
05F8  5f                 pop di
05F9  07                 pop es
05FA  5e                 pop si
05FB  1f                 pop ds
05FC  5a                 pop dx
05FD  59                 pop cx
05FE  5d                 pop bp
05FF  c20400             ret 4
0602  06                 push es
0603  57                 push di
0604  50                 push ax
0605  c43e1c62           les di, ptr [0x621c]
0609  83c701             add di, 1
060C  06                 push es
060D  57                 push di
060E  e8aeff             call 0x5bf
0611  730d               jae 0x620
0613  50                 push ax
0614  55                 push bp
0615  8bec               mov bp, sp
0617  c746028016         mov word ptr [bp + 2], 0x1680
061C  5d                 pop bp
061D  e80302             call 0x823
0620  a3f70f             mov word ptr [0xff7], ax
0623  50                 push ax
0624  e8a9fb             call 0x1d0
0627  58                 pop ax
0628  5f                 pop di
0629  07                 pop es
062A  c3                 ret 
062B  06                 push es
062C  57                 push di
062D  1e                 push ds
062E  56                 push si
062F  50                 push ax
0630  53                 push bx
0631  51                 push cx
0632  52                 push dx
0633  55                 push bp
0634  e8cbff             call 0x602
0637  8b1e2062           mov bx, word ptr [0x6220]
063B  33d2               xor dx, dx
063D  8a17               mov dl, byte ptr [bx]
063F  d0ea               shr dl, 1
0641  86f2               xchg dl, dh
0643  8b7714             mov si, word ptr [bx + 0x14]
0646  8bee               mov bp, si
0648  8bce               mov cx, si
064A  4e                 dec si
064B  83c50f             add bp, 0xf
064E  d1ed               shr bp, 1
0650  d1ed               shr bp, 1
0652  d1ed               shr bp, 1
0654  d1ed               shr bp, 1
0656  8b470e             mov ax, word ptr [bx + 0xe]
0659  034712             add ax, word ptr [bx + 0x12]
065C  2bc5               sub ax, bp
065E  8ec0               mov es, ax
0660  8bfe               mov di, si
0662  83cf0f             or di, 0xf
0665  8e5f0e             mov ds, word ptr [bx + 0xe]
0668  03f2               add si, dx
066A  fd                 std 
066B  f3a4               rep movsb byte ptr es:[di], byte ptr [si]
066D  1e                 push ds
066E  06                 push es
066F  1f                 pop ds
0670  07                 pop es
0671  87f7               xchg di, si
0673  46                 inc si
0674  8bfa               mov di, dx
0676  e80508             call 0xe7e
0679  0e                 push cs
067A  1f                 pop ds
067B  8b362062           mov si, word ptr [0x6220]
067F  803c02             cmp byte ptr [si], 2
0682  750b               jne 0x68f
0684  ff362262           push word ptr [0x6222]
0688  ff362062           push word ptr [0x6220]
068C  e80a00             call 0x699
068F  5d                 pop bp
0690  5a                 pop dx
0691  59                 pop cx
0692  5b                 pop bx
0693  58                 pop ax
0694  5e                 pop si
0695  1f                 pop ds
0696  5f                 pop di
0697  07                 pop es
0698  c3                 ret 
0699  55                 push bp
069A  8bec               mov bp, sp
069C  1e                 push ds
069D  56                 push si
069E  06                 push es
069F  57                 push di
06A0  50                 push ax
06A1  c57604             lds si, ptr [bp + 4]
06A4  8b440e             mov ax, word ptr [si + 0xe]
06A7  8ec0               mov es, ax
06A9  8b7c2a             mov di, word ptr [si + 0x2a]
06AC  26c7050000         mov word ptr es:[di], 0
06B1  58                 pop ax
06B2  5f                 pop di
06B3  07                 pop es
06B4  5e                 pop si
06B5  1f                 pop ds
06B6  5d                 pop bp
06B7  c20400             ret 4
06BA  50                 push ax
06BB  55                 push bp
06BC  8bec               mov bp, sp
06BE  c746029516         mov word ptr [bp + 2], 0x1695
06C3  5d                 pop bp
06C4  e85c01             call 0x823
06C7  e838ff             call 0x602
06CA  0e                 push cs
06CB  1f                 pop ds
06CC  8b362062           mov si, word ptr [0x6220]
06D0  8b441a             mov ax, word ptr [si + 0x1a]
06D3  2ea3280d           mov word ptr cs:[0xd28], ax
06D7  8b441c             mov ax, word ptr [si + 0x1c]
06DA  2ea32a0d           mov word ptr cs:[0xd2a], ax
06DE  2e8c16260d         mov word ptr cs:[0xd26], ss
06E3  2e8926240d         mov word ptr cs:[0xd24], sp
06E8  8b441e             mov ax, word ptr [si + 0x1e]
06EB  2ea3380d           mov word ptr cs:[0xd38], ax
06EF  8b4422             mov ax, word ptr [si + 0x22]
06F2  2ea3360d           mov word ptr cs:[0xd36], ax
06F6  8b442e             mov ax, word ptr [si + 0x2e]
06F9  8b5c30             mov bx, word ptr [si + 0x30]
06FC  8b4c32             mov cx, word ptr [si + 0x32]
06FF  8b5434             mov dx, word ptr [si + 0x34]
0702  8e5428             mov ss, word ptr [si + 0x28]
0705  8b642a             mov sp, word ptr [si + 0x2a]
0708  8b6c2c             mov bp, word ptr [si + 0x2c]
070B  8e4424             mov es, word ptr [si + 0x24]
070E  8b7c26             mov di, word ptr [si + 0x26]
0711  8e5c20             mov ds, word ptr [si + 0x20]
0714  2e8b36360d         mov si, word ptr cs:[0xd36]
0719  2eff36380d         push word ptr cs:[0xd38]
071E  2eff362a0d         push word ptr cs:[0xd2a]
0723  2eff36280d         push word ptr cs:[0xd28]
0728  cf                 iret 
0729  e8d6fe             call 0x602
072C  0e                 push cs
072D  1f                 pop ds
072E  8b362062           mov si, word ptr [0x6220]
0732  8b4416             mov ax, word ptr [si + 0x16]
0735  2ea3280d           mov word ptr cs:[0xd28], ax
0739  8b4418             mov ax, word ptr [si + 0x18]
073C  2ea32a0d           mov word ptr cs:[0xd2a], ax
0740  ff36f70f           push word ptr [0xff7]
0744  e8edfd             call 0x534
0747  ff362262           push word ptr [0x6222]
074B  ff362062           push word ptr [0x6220]
074F  e847ff             call 0x699
0752  eb8a               jmp 0x6de
0754  2e8e16260d         mov ss, word ptr cs:[0xd26]
0759  2e8b26240d         mov sp, word ptr cs:[0xd24]
075E  0e                 push cs
075F  1f                 pop ds
0760  fb                 sti 
0761  c3                 ret 
0762  2e8f062e0d         pop word ptr cs:[0xd2e]
0767  2e8f062c0d         pop word ptr cs:[0xd2c]
076C  2e8f06380d         pop word ptr cs:[0xd38]
0771  2e8c16300d         mov word ptr cs:[0xd30], ss
0776  2e8926320d         mov word ptr cs:[0xd32], sp
077B  2e8e16260d         mov ss, word ptr cs:[0xd26]
0780  2e8b26240d         mov sp, word ptr cs:[0xd24]
0785  1e                 push ds
0786  56                 push si
0787  0e                 push cs
0788  1f                 pop ds
0789  8b362062           mov si, word ptr [0x6220]
078D  8f4422             pop word ptr [si + 0x22]
0790  8f4420             pop word ptr [si + 0x20]
0793  2eff36380d         push word ptr cs:[0xd38]
0798  2eff362c0d         push word ptr cs:[0xd2c]
079D  2eff362e0d         push word ptr cs:[0xd2e]
07A2  8f441a             pop word ptr [si + 0x1a]
07A5  8f441c             pop word ptr [si + 0x1c]
07A8  8f441e             pop word ptr [si + 0x1e]
07AB  2eff36300d         push word ptr cs:[0xd30]
07B0  2eff36320d         push word ptr cs:[0xd32]
07B5  8f442a             pop word ptr [si + 0x2a]
07B8  8f4428             pop word ptr [si + 0x28]
07BB  8c4424             mov word ptr [si + 0x24], es
07BE  897c26             mov word ptr [si + 0x26], di
07C1  896c2c             mov word ptr [si + 0x2c], bp
07C4  89442e             mov word ptr [si + 0x2e], ax
07C7  895c30             mov word ptr [si + 0x30], bx
07CA  894c32             mov word ptr [si + 0x32], cx
07CD  895434             mov word ptr [si + 0x34], dx
07D0  fb                 sti 
07D1  c3                 ret 
07D2  1e                 push ds
07D3  56                 push si
07D4  06                 push es
07D5  57                 push di
07D6  51                 push cx
07D7  e828fe             call 0x602
07DA  0e                 push cs
07DB  1f                 pop ds
07DC  8b361c62           mov si, word ptr [0x621c]
07E0  83c612             add si, 0x12
07E3  8b3e2062           mov di, word ptr [0x6220]
07E7  83c70e             add di, 0xe
07EA  8e05               mov es, word ptr [di]
07EC  bf8000             mov di, 0x80
07EF  ac                 lodsb al, byte ptr [si]
07F0  33c9               xor cx, cx
07F2  8ac8               mov cl, al
07F4  fec8               dec al
07F6  aa                 stosb byte ptr es:[di], al
07F7  fc                 cld 
07F8  f3a4               rep movsb byte ptr es:[di], byte ptr [si]
07FA  59                 pop cx
07FB  5f                 pop di
07FC  07                 pop es
07FD  5e                 pop si
07FE  1f                 pop ds
07FF  c3                 ret 
0800  56                 push si
0801  06                 push es
0802  50                 push ax
0803  57                 push di
0804  51                 push cx
0805  e8fafd             call 0x602
0808  8b362062           mov si, word ptr [0x6220]
080C  8b440e             mov ax, word ptr [si + 0xe]
080F  e849fa             call 0x25b
0812  c43e2062           les di, ptr [0x6220]
0816  33c0               xor ax, ax
0818  b92000             mov cx, 0x20
081B  f3ab               rep stosw word ptr es:[di], ax
081D  59                 pop cx
081E  5f                 pop di
081F  58                 pop ax
0820  07                 pop es
0821  5e                 pop si
0822  c3                 ret 
0823  55                 push bp
0824  8bec               mov bp, sp
0826  0e                 push cs
0827  1f                 pop ds
0828  2e803e7c0e00       cmp byte ptr cs:[0xe7c], 0
082E  7423               je 0x853
0830  b402               mov ah, 2
0832  cdf0               int 0xf0
0834  e85bfb             call 0x392
0837  2ec6067c0e00       mov byte ptr cs:[0xe7c], 0
083D  50                 push ax
083E  55                 push bp
083F  8bec               mov bp, sp
0841  c746020000         mov word ptr [bp + 2], 0
0846  5d                 pop bp
0847  e8bdfb             call 0x407
084A  a14a66             mov ax, word ptr [0x664a]
084D  e85201             call 0x9a2
0850  e808fa             call 0x25b
0853  b80300             mov ax, 3
0856  cd10               int 0x10
0858  1e                 push ds
0859  50                 push ax
085A  55                 push bp
085B  8bec               mov bp, sp
085D  c74602f915         mov word ptr [bp + 2], 0x15f9
0862  5d                 pop bp
0863  e896f9             call 0x1fc
0866  1e                 push ds
0867  ff7604             push word ptr [bp + 4]
086A  e88ff9             call 0x1fc
086D  b8014c             mov ax, 0x4c01
0870  cd21               int 0x21
0872  06                 push es
0873  57                 push di
0874  1e                 push ds
0875  56                 push si
0876  51                 push cx
0877  50                 push ax
0878  1e                 push ds
0879  07                 pop es
087A  bfe80f             mov di, 0xfe8
087D  1e                 push ds
087E  8e1e1a62           mov ds, word ptr [0x621a]
0882  be8000             mov si, 0x80
0885  ac                 lodsb al, byte ptr [si]
0886  3c04               cmp al, 4
0888  7633               jbe 0x8bd
088A  803c20             cmp byte ptr [si], 0x20
088D  7503               jne 0x892
088F  46                 inc si
0890  fec8               dec al
0892  8ac8               mov cl, al
0894  fc                 cld 
0895  f3a4               rep movsb byte ptr es:[di], byte ptr [si]
0897  1f                 pop ds
0898  1e                 push ds
0899  50                 push ax
089A  55                 push bp
089B  8bec               mov bp, sp
089D  c74602e80f         mov word ptr [bp + 2], 0xfe8
08A2  5d                 pop bp
08A3  1e                 push ds
08A4  50                 push ax
08A5  55                 push bp
08A6  8bec               mov bp, sp
08A8  c746021817         mov word ptr [bp + 2], 0x1718
08AD  5d                 pop bp
08AE  50                 push ax
08AF  55                 push bp
08B0  8bec               mov bp, sp
08B2  c74602004b         mov word ptr [bp + 2], 0x4b00
08B7  5d                 pop bp
08B8  e80a00             call 0x8c5
08BB  eb01               jmp 0x8be
08BD  1f                 pop ds
08BE  58                 pop ax
08BF  59                 pop cx
08C0  5e                 pop si
08C1  1f                 pop ds
08C2  5f                 pop di
08C3  07                 pop es
08C4  c3                 ret 
08C5  55                 push bp
08C6  8bec               mov bp, sp
08C8  1e                 push ds
08C9  52                 push dx
08CA  50                 push ax
08CB  53                 push bx
08CC  51                 push cx
08CD  1e                 push ds
08CE  c5560a             lds dx, ptr [bp + 0xa]
08D1  b8003d             mov ax, 0x3d00
08D4  cd21               int 0x21
08D6  731a               jae 0x8f2
08D8  1e                 push ds
08D9  07                 pop es
08DA  8bf2               mov si, dx
08DC  bf1916             mov di, 0x1619
08DF  b90d00             mov cx, 0xd
08E2  fc                 cld 
08E3  f3a4               rep movsb byte ptr es:[di], byte ptr [si]
08E5  50                 push ax
08E6  55                 push bp
08E7  8bec               mov bp, sp
08E9  c746020916         mov word ptr [bp + 2], 0x1609
08EE  5d                 pop bp
08EF  e831ff             call 0x823
08F2  8bd8               mov bx, ax
08F4  8b4e04             mov cx, word ptr [bp + 4]
08F7  c55606             lds dx, ptr [bp + 6]
08FA  b43f               mov ah, 0x3f
08FC  cd21               int 0x21
08FE  1f                 pop ds
08FF  a31862             mov word ptr [0x6218], ax
0902  b43e               mov ah, 0x3e
0904  cd21               int 0x21
0906  59                 pop cx
0907  5b                 pop bx
0908  58                 pop ax
0909  5a                 pop dx
090A  1f                 pop ds
090B  5d                 pop bp
090C  c20a00             ret 0xa
090F  bb4c66             mov bx, 0x664c
0912  83c30f             add bx, 0xf
0915  d1eb               shr bx, 1
0917  d1eb               shr bx, 1
0919  d1eb               shr bx, 1
091B  d1eb               shr bx, 1
091D  b44a               mov ah, 0x4a
091F  cd21               int 0x21
0921  c3                 ret 
0922  1e                 push ds
0923  56                 push si
0924  06                 push es
0925  57                 push di
0926  50                 push ax
0927  53                 push bx
0928  51                 push cx
0929  e8d6fc             call 0x602
092C  8e064a66           mov es, word ptr [0x664a]
0930  8b3e0417           mov di, word ptr [0x1704]
0934  8bc7               mov ax, di
0936  2b060617           sub ax, word ptr [0x1706]
093A  bbfeff             mov bx, 0xfffe
093D  2bd8               sub bx, ax
093F  8b362062           mov si, word ptr [0x6220]
0943  8e5c0e             mov ds, word ptr [si + 0xe]
0946  33f6               xor si, si
0948  53                 push bx
0949  e83205             call 0xe7e
094C  5b                 pop bx
094D  0e                 push cs
094E  1f                 pop ds
094F  01060417           add word ptr [0x1704], ax
0953  3bd8               cmp bx, ax
0955  722c               jb 0x983
0957  803e021700         cmp byte ptr [0x1702], 0
095C  751d               jne 0x97b
095E  1e                 push ds
095F  07                 pop es
0960  bf4a62             mov di, 0x624a
0963  8b360617           mov si, word ptr [0x1706]
0967  8e1e4a66           mov ds, word ptr [0x664a]
096B  ad                 lodsw ax, word ptr [si]
096C  ab                 stosw word ptr es:[di], ax
096D  91                 xchg cx, ax
096E  41                 inc cx
096F  f3a5               rep movsw word ptr es:[di], word ptr [si]
0971  0e                 push cs
0972  1f                 pop ds
0973  89360617           mov word ptr [0x1706], si
0977  fe060217           inc byte ptr [0x1702]
097B  59                 pop cx
097C  5b                 pop bx
097D  58                 pop ax
097E  5f                 pop di
097F  07                 pop es
0980  5e                 pop si
0981  1f                 pop ds
0982  c3                 ret 
0983  50                 push ax
0984  55                 push bp
0985  8bec               mov bp, sp
0987  c74602ab16         mov word ptr [bp + 2], 0x16ab
098C  5d                 pop bp
098D  e893fe             call 0x823
0990  50                 push ax
0991  e461               in al, 0x61
0993  0c03               or al, 3
0995  e661               out 0x61, al
0997  b0b6               mov al, 0xb6
0999  e643               out 0x43, al
099B  c606011701         mov byte ptr [0x1701], 1
09A0  58                 pop ax
09A1  c3                 ret 
09A2  50                 push ax
09A3  c606011700         mov byte ptr [0x1701], 0
09A8  e461               in al, 0x61
09AA  24fc               and al, 0xfc
09AC  e661               out 0x61, al
09AE  58                 pop ax
09AF  c3                 ret 
09B0  55                 push bp
09B1  8bec               mov bp, sp
09B3  83ec02             sub sp, 2
09B6  50                 push ax
09B7  52                 push dx
09B8  56                 push si
09B9  8b361c62           mov si, word ptr [0x621c]
09BD  8b4412             mov ax, word ptr [si + 0x12]
09C0  8946fe             mov word ptr [bp - 2], ax
09C3  b409               mov ah, 9
09C5  cdf0               int 0xf0
09C7  3dffff             cmp ax, 0xffff
09CA  7407               je 0x9d3
09CC  3b56fe             cmp dx, word ptr [bp - 2]
09CF  7702               ja 0x9d3
09D1  ebf0               jmp 0x9c3
09D3  5e                 pop si
09D4  5a                 pop dx
09D5  58                 pop ax
09D6  8be5               mov sp, bp
09D8  5d                 pop bp
09D9  c3                 ret 
09DA  55                 push bp
09DB  8bec               mov bp, sp
09DD  50                 push ax
09DE  53                 push bx
09DF  51                 push cx
09E0  52                 push dx
09E1  06                 push es
09E2  57                 push di
09E3  56                 push si
09E4  9c                 pushf 
09E5  c4760a             les si, ptr [bp + 0xa]
09E8  8cc1               mov cx, es
09EA  c47e06             les di, ptr [bp + 6]
09ED  8b5e04             mov bx, word ptr [bp + 4]
09F0  fc                 cld 
09F1  b000               mov al, 0
09F3  50                 push ax
09F4  8bc1               mov ax, cx
09F6  33d2               xor dx, dx
09F8  f7f3               div bx
09FA  96                 xchg si, ax
09FB  f7f3               div bx
09FD  8bc8               mov cx, ax
09FF  87ce               xchg si, cx
0A01  8ac2               mov al, dl
0A03  0430               add al, 0x30
0A05  3c39               cmp al, 0x39
0A07  7602               jbe 0xa0b
0A09  0407               add al, 7
0A0B  50                 push ax
0A0C  8bc1               mov ax, cx
0A0E  0bc6               or ax, si
0A10  75e2               jne 0x9f4
0A12  58                 pop ax
0A13  aa                 stosb byte ptr es:[di], al
0A14  3c00               cmp al, 0
0A16  75fa               jne 0xa12
0A18  9d                 popf 
0A19  5e                 pop si
0A1A  5f                 pop di
0A1B  07                 pop es
0A1C  5a                 pop dx
0A1D  59                 pop cx
0A1E  5b                 pop bx
0A1F  58                 pop ax
0A20  5d                 pop bp
0A21  c20a00             ret 0xa
0A24  2e8c16300d         mov word ptr cs:[0xd30], ss
0A29  2e8926320d         mov word ptr cs:[0xd32], sp
0A2E  2e891e7a0d         mov word ptr cs:[0xd7a], bx
0A33  8ccb               mov bx, cs
0A35  8ed3               mov ss, bx
0A37  bc780d             mov sp, 0xd78
0A3A  33db               xor bx, bx
0A3C  8adc               mov bl, ah
0A3E  80e30f             and bl, 0xf
0A41  d1e3               shl bx, 1
0A43  2effa7040d         jmp word ptr cs:[bx + 0xd04]
0A48  51                 push cx
0A49  50                 push ax
0A4A  1e                 push ds
0A4B  56                 push si
0A4C  06                 push es
0A4D  0e                 push cs
0A4E  1f                 pop ds
0A4F  b80100             mov ax, 1
0A52  8a0e0317           mov cl, byte ptr [0x1703]
0A56  d3e0               shl ax, cl
0A58  01060c17           add word ptr [0x170c], ax
0A5C  83160e1700         adc word ptr [0x170e], 0
0A61  8bc8               mov cx, ax
0A63  8b362062           mov si, word ptr [0x6220]
0A67  834436ff           add word ptr [si + 0x36], -1
0A6B  1bc0               sbb ax, ax
0A6D  214436             and word ptr [si + 0x36], ax
0A70  803e011700         cmp byte ptr [0x1701], 0
0A75  7427               je 0xa9e
0A77  8b360617           mov si, word ptr [0x1706]
0A7B  3b360417           cmp si, word ptr [0x1704]
0A7F  741d               je 0xa9e
0A81  8e064a66           mov es, word ptr [0x664a]
0A85  fc                 cld 
0A86  26ad               lodsw ax, word ptr es:[si]
0A88  e642               out 0x42, al
0A8A  8ac4               mov al, ah
0A8C  e642               out 0x42, al
0A8E  8306081701         add word ptr [0x1708], 1
0A93  83160a1700         adc word ptr [0x170a], 0
0A98  e2ec               loop 0xa86
0A9A  89360617           mov word ptr [0x1706], si
0A9E  a11017             mov ax, word ptr [0x1710]
0AA1  01061217           add word ptr [0x1712], ax
0AA5  720a               jb 0xab1
0AA7  b020               mov al, 0x20
0AA9  e620               out 0x20, al
0AAB  07                 pop es
0AAC  5e                 pop si
0AAD  1f                 pop ds
0AAE  58                 pop ax
0AAF  59                 pop cx
0AB0  cf                 iret 
0AB1  07                 pop es
0AB2  5e                 pop si
0AB3  1f                 pop ds
0AB4  58                 pop ax
0AB5  59                 pop cx
0AB6  ea00000000         ljmp 0:0
0ABB  52                 push dx
0ABC  51                 push cx
0ABD  50                 push ax
0ABE  bada03             mov dx, 0x3da
0AC1  33c9               xor cx, cx
0AC3  ec                 in al, dx
0AC4  a808               test al, 8
0AC6  74fb               je 0xac3
0AC8  ec                 in al, dx
0AC9  a809               test al, 9
0ACB  75fb               jne 0xac8
0ACD  b106               mov cl, 6
0ACF  ec                 in al, dx
0AD0  a801               test al, 1
0AD2  e0fb               loopne 0xacf
0AD4  7502               jne 0xad8
0AD6  ebf5               jmp 0xacd
0AD8  50                 push ax
0AD9  b034               mov al, 0x34
0ADB  e643               out 0x43, al
0ADD  b8e426             mov ax, 0x26e4
0AE0  e640               out 0x40, al
0AE2  e461               in al, 0x61
0AE4  8ac4               mov al, ah
0AE6  e640               out 0x40, al
0AE8  58                 pop ax
0AE9  1e                 push ds
0AEA  0e                 push cs
0AEB  1f                 pop ds
0AEC  c7061017e426       mov word ptr [0x1710], 0x26e4
0AF2  1f                 pop ds
0AF3  58                 pop ax
0AF4  59                 pop cx
0AF5  5a                 pop dx
0AF6  e9d100             jmp 0xbca
0AF9  50                 push ax
0AFA  b034               mov al, 0x34
0AFC  e643               out 0x43, al
0AFE  b80000             mov ax, 0
0B01  e640               out 0x40, al
0B03  e461               in al, 0x61
0B05  8ac4               mov al, ah
0B07  e640               out 0x40, al
0B09  58                 pop ax
0B0A  1e                 push ds
0B0B  0e                 push cs
0B0C  1f                 pop ds
0B0D  c70610170000       mov word ptr [0x1710], 0
0B13  1f                 pop ds
0B14  50                 push ax
0B15  53                 push bx
0B16  1e                 push ds
0B17  33c0               xor ax, ax
0B19  50                 push ax
0B1A  0e                 push cs
0B1B  1f                 pop ds
0B1C  a12662             mov ax, word ptr [0x6226]
0B1F  8b1e2862           mov bx, word ptr [0x6228]
0B23  1f                 pop ds
0B24  9c                 pushf 
0B25  fa                 cli 
0B26  891e2200           mov word ptr [0x22], bx
0B2A  a32000             mov word ptr [0x20], ax
0B2D  9d                 popf 
0B2E  1f                 pop ds
0B2F  5b                 pop bx
0B30  58                 pop ax
0B31  e9a501             jmp 0xcd9
0B34  52                 push dx
0B35  51                 push cx
0B36  50                 push ax
0B37  bada03             mov dx, 0x3da
0B3A  33c9               xor cx, cx
0B3C  ec                 in al, dx
0B3D  a808               test al, 8
0B3F  74fb               je 0xb3c
0B41  ec                 in al, dx
0B42  a809               test al, 9
0B44  75fb               jne 0xb41
0B46  b106               mov cl, 6
0B48  ec                 in al, dx
0B49  a801               test al, 1
0B4B  e0fb               loopne 0xb48
0B4D  7502               jne 0xb51
0B4F  ebf5               jmp 0xb46
0B51  50                 push ax
0B52  b034               mov al, 0x34
0B54  e643               out 0x43, al
0B56  b8c84d             mov ax, 0x4dc8
0B59  e640               out 0x40, al
0B5B  e461               in al, 0x61
0B5D  8ac4               mov al, ah
0B5F  e640               out 0x40, al
0B61  58                 pop ax
0B62  1e                 push ds
0B63  0e                 push cs
0B64  1f                 pop ds
0B65  c7061017c84d       mov word ptr [0x1710], 0x4dc8
0B6B  1f                 pop ds
0B6C  58                 pop ax
0B6D  59                 pop cx
0B6E  5a                 pop dx
0B6F  1e                 push ds
0B70  0e                 push cs
0B71  1f                 pop ds
0B72  c606031701         mov byte ptr [0x1703], 1
0B77  1f                 pop ds
0B78  e95e01             jmp 0xcd9
0B7B  50                 push ax
0B7C  b8e426             mov ax, 0x26e4
0B7F  e640               out 0x40, al
0B81  e461               in al, 0x61
0B83  8ac4               mov al, ah
0B85  e640               out 0x40, al
0B87  58                 pop ax
0B88  1e                 push ds
0B89  0e                 push cs
0B8A  1f                 pop ds
0B8B  c7061017e426       mov word ptr [0x1710], 0x26e4
0B91  1f                 pop ds
0B92  1e                 push ds
0B93  0e                 push cs
0B94  1f                 pop ds
0B95  c606031700         mov byte ptr [0x1703], 0
0B9A  1f                 pop ds
0B9B  e93b01             jmp 0xcd9
0B9E  1e                 push ds
0B9F  0e                 push cs
0BA0  1f                 pop ds
0BA1  893e4662           mov word ptr [0x6246], di
0BA5  8c064862           mov word ptr [0x6248], es
0BA9  1f                 pop ds
0BAA  50                 push ax
0BAB  53                 push bx
0BAC  1e                 push ds
0BAD  33c0               xor ax, ax
0BAF  50                 push ax
0BB0  0e                 push cs
0BB1  1f                 pop ds
0BB2  a14662             mov ax, word ptr [0x6246]
0BB5  8b1e4862           mov bx, word ptr [0x6248]
0BB9  1f                 pop ds
0BBA  9c                 pushf 
0BBB  fa                 cli 
0BBC  891e2200           mov word ptr [0x22], bx
0BC0  a32000             mov word ptr [0x20], ax
0BC3  9d                 popf 
0BC4  1f                 pop ds
0BC5  5b                 pop bx
0BC6  58                 pop ax
0BC7  e90f01             jmp 0xcd9
0BCA  50                 push ax
0BCB  53                 push bx
0BCC  1e                 push ds
0BCD  33c0               xor ax, ax
0BCF  50                 push ax
0BD0  0e                 push cs
0BD1  1f                 pop ds
0BD2  a12a62             mov ax, word ptr [0x622a]
0BD5  8b1e2c62           mov bx, word ptr [0x622c]
0BD9  1f                 pop ds
0BDA  9c                 pushf 
0BDB  fa                 cli 
0BDC  891e2200           mov word ptr [0x22], bx
0BE0  a32000             mov word ptr [0x20], ax
0BE3  9d                 popf 
0BE4  1f                 pop ds
0BE5  5b                 pop bx
0BE6  58                 pop ax
0BE7  e9ef00             jmp 0xcd9
0BEA  1e                 push ds
0BEB  0e                 push cs
0BEC  1f                 pop ds
0BED  8b160e17           mov dx, word ptr [0x170e]
0BF1  a10c17             mov ax, word ptr [0x170c]
0BF4  1f                 pop ds
0BF5  e9e100             jmp 0xcd9
0BF8  1e                 push ds
0BF9  0e                 push cs
0BFA  1f                 pop ds
0BFB  3c00               cmp al, 0
0BFD  740c               je 0xc0b
0BFF  3c01               cmp al, 1
0C01  7412               je 0xc15
0C03  3c03               cmp al, 3
0C05  7228               jb 0xc2f
0C07  7446               je 0xc4f
0C09  774b               ja 0xc56
0C0B  8e064a66           mov es, word ptr [0x664a]
0C0F  8b3e0617           mov di, word ptr [0x1706]
0C13  eb48               jmp 0xc5d
0C15  010e0c17           add word ptr [0x170c], cx
0C19  83160e1700         adc word ptr [0x170e], 0
0C1E  010e0817           add word ptr [0x1708], cx
0C22  83160a1700         adc word ptr [0x170a], 0
0C27  d1e1               shl cx, 1
0C29  010e0617           add word ptr [0x1706], cx
0C2D  eb2e               jmp 0xc5d
0C2F  8bc7               mov ax, di
0C31  2b060617           sub ax, word ptr [0x1706]
0C35  893e0617           mov word ptr [0x1706], di
0C39  d1e8               shr ax, 1
0C3B  01060c17           add word ptr [0x170c], ax
0C3F  83160e1700         adc word ptr [0x170e], 0
0C44  01060817           add word ptr [0x1708], ax
0C48  83160a1700         adc word ptr [0x170a], 0
0C4D  eb0e               jmp 0xc5d
0C4F  c606011700         mov byte ptr [0x1701], 0
0C54  eb07               jmp 0xc5d
0C56  c606011701         mov byte ptr [0x1701], 1
0C5B  eb00               jmp 0xc5d
0C5D  1f                 pop ds
0C5E  eb79               jmp 0xcd9
0C60  1e                 push ds
0C61  51                 push cx
0C62  53                 push bx
0C63  56                 push si
0C64  57                 push di
0C65  0e                 push cs
0C66  1f                 pop ds
0C67  8b160a17           mov dx, word ptr [0x170a]
0C6B  8b1e0817           mov bx, word ptr [0x1708]
0C6F  be4a62             mov si, 0x624a
0C72  ad                 lodsw ax, word ptr [si]
0C73  91                 xchg cx, ax
0C74  33ff               xor di, di
0C76  ad                 lodsw ax, word ptr [si]
0C77  47                 inc di
0C78  2bd8               sub bx, ax
0C7A  83da00             sbb dx, 0
0C7D  7805               js 0xc84
0C7F  e2f5               loop 0xc76
0C81  ad                 lodsw ax, word ptr [si]
0C82  eb03               jmp 0xc87
0C84  93                 xchg bx, ax
0C85  f7d8               neg ax
0C87  8bd7               mov dx, di
0C89  5f                 pop di
0C8A  5e                 pop si
0C8B  5b                 pop bx
0C8C  59                 pop cx
0C8D  1f                 pop ds
0C8E  eb49               jmp 0xcd9
0C90  1e                 push ds
0C91  56                 push si
0C92  0e                 push cs
0C93  1f                 pop ds
0C94  8b362062           mov si, word ptr [0x6220]
0C98  894c36             mov word ptr [si + 0x36], cx
0C9B  5e                 pop si
0C9C  1f                 pop ds
0C9D  eb3a               jmp 0xcd9
0C9F  1e                 push ds
0CA0  56                 push si
0CA1  0e                 push cs
0CA2  1f                 pop ds
0CA3  8b362062           mov si, word ptr [0x6220]
0CA7  8b4436             mov ax, word ptr [si + 0x36]
0CAA  5e                 pop si
0CAB  1f                 pop ds
0CAC  eb2b               jmp 0xcd9
0CAE  1e                 push ds
0CAF  56                 push si
0CB0  0e                 push cs
0CB1  1f                 pop ds
0CB2  ff362262           push word ptr [0x6222]
0CB6  ff362062           push word ptr [0x6220]
0CBA  06                 push es
0CBB  57                 push di
0CBC  e800f9             call 0x5bf
0CBF  50                 push ax
0CC0  e80df5             call 0x1d0
0CC3  8b362062           mov si, word ptr [0x6220]
0CC7  8b4410             mov ax, word ptr [si + 0x10]
0CCA  8e440e             mov es, word ptr [si + 0xe]
0CCD  33ff               xor di, di
0CCF  8f062062           pop word ptr [0x6220]
0CD3  8f062262           pop word ptr [0x6222]
0CD7  5e                 pop si
0CD8  1f                 pop ds
0CD9  2e8b1e7a0d         mov bx, word ptr cs:[0xd7a]
0CDE  2e8e16300d         mov ss, word ptr cs:[0xd30]
0CE3  2e8b26320d         mov sp, word ptr cs:[0xd32]
0CE8  cf                 iret 
0CE9  90                 nop 
0CEA  7201               jb 0xced
0CEC  c60480             mov byte ptr [si], 0x80
0CEF  04ba               add al, 0xba
0CF1  06                 push es
0CF2  2b062209           sub ax, word ptr [0x922]
0CF6  90                 nop 
0CF7  09a209c7           or word ptr [bp + si - 0x38f7], sp
0CFB  06                 push es
0CFC  d207               rol byte ptr [bx], cl
0CFE  2907               sub word ptr [bx], ax
0D00  0008               add byte ptr [bx + si], cl
0D02  b009               mov al, 9
