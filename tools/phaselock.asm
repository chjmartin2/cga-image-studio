; ============================================================================
;  PHASE-LOCK PREAMBLE for the dense Mode-Switch lockstep COM
;  Goal: pin DRAM-refresh phase (PIT ch1) to the CGA frame DETERMINISTICALLY,
;  so the 13-write stream lands on the same columns on every cold run.
;
;  Facts (verified from MartyPC source):
;    * master 14.318MHz -> CGA /1, CPU /3, PIT /12. All locked to one oscillator.
;    * PIT ch1 count=19, mode2 -> refresh every 19*12 = 228 hdots; scanline=912 = 4x.
;    * frame = 262*912 = 238944 hdots = 19912 PIT ticks = 1048 * 19  (commensurate!)
;    * a write to a PIT counter latches on the NEXT PIT input edge (every 12 hdots),
;      needs >=3 sys-ticks setup (PIT_WRITE_LATENCY=3). So phase is set on the
;      12-hdot grid, deterministically relative to the cycle you write it.
;    * counter-latch command lets us read the live count to remove poll jitter.
;
;  The ONLY run-to-run variance today is that the COM does `out 41h` during VRAM
;  load (random frame phase). Fix: do it at a beam-pinned, PIT-edge-aligned cycle.
;
;  Magic cycle counts marked >>>TUNE<<< must be dialed against MartyPC (the
;  phaseprobe test below shows when they're right). DX is trashed; CLI assumed.
; ============================================================================

; ---- 1. coarse beam sync: catch the START of vertical sync ------------------
        mov     dx, 03DAh
.vs_lo: in      al, dx
        test    al, 08h          ; bit3 = vertical sync
        jnz     .vs_lo           ; wait until OUT of vsync
.vs_hi: in      al, dx
        test    al, 08h
        jz      .vs_hi           ; wait until vsync just BEGAN  (beam pinned +- poll slop)

; ---- 2. fine align to a PIT edge (kills the poll slop) ----------------------
; Read ch0's live count: it ticks on the same PIT clock as the refresh, so its
; low bits ARE our sub-line phase. We slide to a fixed PIT-tick boundary so the
; `out 41h` below always lands on the same edge regardless of boot phase.
        xor     al, al           ; 00b = counter-latch, channel 0
        out     043h, al
        in      al, 040h         ; AL = ch0 LSB (latched live count, no jitter)
        and     al, 00Fh         ; low 4 bits -> position within a 16-tick window
        mov     ah, al
        shl     al, 1            ; *2 : each nop-slide entry is 2 bytes (one NOP+?)
        ; jump into the slide so total delay == constant for every starting phase.
        ; slide is 16 entries; entry k delays (15-k) PIT-ticks-worth of NOPs.
        mov     bx, .slide_base
        ; (compute target = base + (15-AH)*ENTRY_BYTES ; >>>TUNE ENTRY_BYTES<<<)
        ; -- simple version: jump table of 16 near labels, each a run of NOPs --
        ; left as a 16-way dispatch; see phaseprobe to calibrate the entry size.
        jmp     .aligned         ; <<< replace with computed jmp into .slide_NN >>>

.slide_base:
        ; .slide_00: nop x60 ... .slide_15: nop x0   (>>>TUNE count per entry<<<)

; ---- 3. program refresh (ch1) AND a frame timer (ch0) at this pinned cycle ---
.aligned:
        ; ch1 = 19, mode2, LSB only, binary  -> 0x54  (refresh, 4 per scanline)
        mov     al, 054h
        out     043h, al
        mov     al, 19
        out     041h, al         ; <-- the critical write, now beam-pinned

        ; ch0 = 19912, mode2, LSB+MSB, binary -> 0x34  (one tick per frame)
        ; 19912 = 0x4DC8 . Used as a jitter-free per-frame heartbeat (option D).
        mov     al, 034h
        out     043h, al
        mov     al, 0C8h
        out     040h, al         ; LSB
        mov     al, 04Dh
        out     040h, al         ; MSB

; refresh + frame timer now share one phase, pinned to the beam. After this,
; the display loop can wait on ch0 (latch-read ch0, loop until it wraps) each
; frame instead of polling 3DA -> no CGA-poll jitter ever again.
; ============================================================================
