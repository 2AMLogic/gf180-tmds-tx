v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {tmds_final_mux -- the DR-0003 custom final 2:1 (DDR) multiplexer, one lane} -700 -820 0 0 0.5 0.5 {}
T {Current-mode-logic 2:1 selector. A clock-steered lower pair (MCP/MCN) routes the
tail current to one of two upper data pairs (MU0*/MU1*), which share one pair of
load resistors (RLP/RLN) returned to VDD through a common series resistor RC.
CLKP high selects the D0 pair, CLKP low selects the D1 pair -- so sampling one
2-bit synthesized-domain word on both edges of the half-rate clock (DR-0012
Decision 1) reconstructs the full bit-rate stream.

RC carries the whole tail current at all times, so it sets the HIGH level
(VDD - Itail*RC) while RLP/RLN set the swing (Itail*RL) -- that is what lets a
plain resistively-loaded stage land on design/cml-driver-sizing.md section 4.1's
asymmetric level pair (vih = 0.85*VDD, vil = 0.55*VDD, common mode 0.70*VDD)
instead of the rail-referenced levels an ordinary CML stage would give.

The tail current is self-biased from VDD through RREF, the SAME resistor type as
RC/RLP/RLN, so the output levels are set by a resistor RATIO and sheet-rho
process variation cancels. Sizing derivation and the measured PVT spread:
design/tmds-final-mux-sizing.md. Verification: sim/tmds-final-mux-eye/ and
sim/cml-driver-eye-realmux/.

The load (the CML driver's INP/INN gates) is OUTSIDE this cell. Every active
device is a 3.3 V core device (nfet_03v3), per DR-0002.} -700 -790 0 0 0.35 0.35 {}
T {Load / level network (ppolyf_u, unsilicided p+ poly)} -700 -520 0 0 0.3 0.3 {}
T {Upper data pairs: W=128u, nf=64 fingers of 2u, L=0.28u -- the same
switch-pair geometry the CML driver itself uses (cml-driver-sizing.md 4.2).} -700 -330 0 0 0.3 0.3 {}
T {Clock-steered lower pair (W=192u, nf=96) and the 1:20 self-biased mirror.
The lower pair is wider than the data pairs because its incomplete
commutation, not the data pairs', is what limits worst-corner swing.} -700 -130 0 0 0.3 0.3 {}
N -600 -630 -600 -660 {}
N -600 -570 -600 -540 {}
N -620 -600 -660 -600 {}
N -300 -630 -300 -660 {}
N -300 -570 -300 -540 {}
N -320 -600 -360 -600 {}
N 0 -630 0 -660 {}
N 0 -570 0 -540 {}
N -20 -600 -60 -600 {}
N 300 -630 300 -660 {}
N 300 -570 300 -540 {}
N 280 -600 240 -600 {}
N -580 -430 -580 -460 {}
N -580 -370 -580 -340 {}
N -620 -400 -660 -400 {}
N -580 -400 -540 -400 {}
N -280 -430 -280 -460 {}
N -280 -370 -280 -340 {}
N -320 -400 -360 -400 {}
N -280 -400 -240 -400 {}
N 20 -430 20 -460 {}
N 20 -370 20 -340 {}
N -20 -400 -60 -400 {}
N 20 -400 60 -400 {}
N 320 -430 320 -460 {}
N 320 -370 320 -340 {}
N 280 -400 240 -400 {}
N 320 -400 360 -400 {}
N -580 -230 -580 -260 {}
N -580 -170 -580 -140 {}
N -620 -200 -660 -200 {}
N -580 -200 -540 -200 {}
N -280 -230 -280 -260 {}
N -280 -170 -280 -140 {}
N -320 -200 -360 -200 {}
N -280 -200 -240 -200 {}
N 20 -230 20 -260 {}
N 20 -170 20 -140 {}
N -20 -200 -60 -200 {}
N 20 -200 60 -200 {}
N 320 -230 320 -260 {}
N 320 -170 320 -140 {}
N 280 -200 240 -200 {}
N 320 -200 360 -200 {}
C {symbols/ppolyf_u.sym} -600 -600 0 0 {name=RC
W=20u
L=2.65u
model=ppolyf_u
spiceprefix=X
m=1}
C {symbols/ppolyf_u.sym} -300 -600 0 0 {name=RLP
W=20u
L=5.90u
model=ppolyf_u
spiceprefix=X
m=1}
C {symbols/ppolyf_u.sym} 0 -600 0 0 {name=RLN
W=20u
L=5.90u
model=ppolyf_u
spiceprefix=X
m=1}
C {symbols/ppolyf_u.sym} 300 -600 0 0 {name=RREF
W=2u
L=24.8u
model=ppolyf_u
spiceprefix=X
m=1}
C {symbols/nfet_03v3.sym} -600 -400 0 0 {name=MU0P
L=0.28u
W=128u
nf=64
m=1
ad=11.52p
pd=139.52u
as=11.88p
ps=143.88u
nrd=1.40625m nrs=1.40625m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} -300 -400 0 0 {name=MU0N
L=0.28u
W=128u
nf=64
m=1
ad=11.52p
pd=139.52u
as=11.88p
ps=143.88u
nrd=1.40625m nrs=1.40625m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 0 -400 0 0 {name=MU1P
L=0.28u
W=128u
nf=64
m=1
ad=11.52p
pd=139.52u
as=11.88p
ps=143.88u
nrd=1.40625m nrs=1.40625m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 300 -400 0 0 {name=MU1N
L=0.28u
W=128u
nf=64
m=1
ad=11.52p
pd=139.52u
as=11.88p
ps=143.88u
nrd=1.40625m nrs=1.40625m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} -600 -200 0 0 {name=MCP
L=0.28u
W=192u
nf=96
m=1
ad=17.28p
pd=209.28u
as=17.64p
ps=213.64u
nrd=0.9375m nrs=0.9375m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} -300 -200 0 0 {name=MCN
L=0.28u
W=192u
nf=96
m=1
ad=17.28p
pd=209.28u
as=17.64p
ps=213.64u
nrd=0.9375m nrs=0.9375m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 0 -200 0 0 {name=MT
L=0.5u
W=20u
nf=10
m=20
ad=1.8p
pd=21.8u
as=2.16p
ps=26.16u
nrd=9m nrs=9m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 300 -200 0 0 {name=MB
L=0.5u
W=20u
nf=10
m=1
ad=1.8p
pd=21.8u
as=2.16p
ps=26.16u
nrd=9m nrs=9m
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {devices/lab_pin.sym} -600 -660 0 0 {name=l0 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -600 -540 0 0 {name=l1 sig_type=std_logic lab=TOP}
C {devices/lab_pin.sym} -660 -600 0 0 {name=l2 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -300 -660 0 0 {name=l3 sig_type=std_logic lab=TOP}
C {devices/lab_pin.sym} -300 -540 0 0 {name=l4 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} -360 -600 0 0 {name=l5 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 0 -660 0 0 {name=l6 sig_type=std_logic lab=TOP}
C {devices/lab_pin.sym} 0 -540 0 0 {name=l7 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} -60 -600 0 0 {name=l8 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 300 -660 0 0 {name=l9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 300 -540 0 0 {name=l10 sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 240 -600 0 0 {name=l11 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -580 -460 0 0 {name=l12 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} -580 -340 0 0 {name=l13 sig_type=std_logic lab=SA}
C {devices/lab_pin.sym} -660 -400 0 0 {name=l14 sig_type=std_logic lab=D0P}
C {devices/lab_pin.sym} -540 -400 0 0 {name=l15 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -280 -460 0 0 {name=l16 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} -280 -340 0 0 {name=l17 sig_type=std_logic lab=SA}
C {devices/lab_pin.sym} -360 -400 0 0 {name=l18 sig_type=std_logic lab=D0N}
C {devices/lab_pin.sym} -240 -400 0 0 {name=l19 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 20 -460 0 0 {name=l20 sig_type=std_logic lab=OUTP}
C {devices/lab_pin.sym} 20 -340 0 0 {name=l21 sig_type=std_logic lab=SB}
C {devices/lab_pin.sym} -60 -400 0 0 {name=l22 sig_type=std_logic lab=D1P}
C {devices/lab_pin.sym} 60 -400 0 0 {name=l23 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 320 -460 0 0 {name=l24 sig_type=std_logic lab=OUTN}
C {devices/lab_pin.sym} 320 -340 0 0 {name=l25 sig_type=std_logic lab=SB}
C {devices/lab_pin.sym} 240 -400 0 0 {name=l26 sig_type=std_logic lab=D1N}
C {devices/lab_pin.sym} 360 -400 0 0 {name=l27 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -580 -260 0 0 {name=l28 sig_type=std_logic lab=SA}
C {devices/lab_pin.sym} -580 -140 0 0 {name=l29 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} -660 -200 0 0 {name=l30 sig_type=std_logic lab=CLKP}
C {devices/lab_pin.sym} -540 -200 0 0 {name=l31 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -280 -260 0 0 {name=l32 sig_type=std_logic lab=SB}
C {devices/lab_pin.sym} -280 -140 0 0 {name=l33 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} -360 -200 0 0 {name=l34 sig_type=std_logic lab=CLKN}
C {devices/lab_pin.sym} -240 -200 0 0 {name=l35 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 20 -260 0 0 {name=l36 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} 20 -140 0 0 {name=l37 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -60 -200 0 0 {name=l38 sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 60 -200 0 0 {name=l39 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 320 -260 0 0 {name=l40 sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 320 -140 0 0 {name=l41 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 240 -200 0 0 {name=l42 sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 360 -200 0 0 {name=l43 sig_type=std_logic lab=VSS}
C {devices/opin.sym} -700 -60 0 0 {name=p1 lab=OUTP}
C {devices/opin.sym} -600 -60 0 0 {name=p2 lab=OUTN}
C {devices/ipin.sym} -500 -60 0 0 {name=p3 lab=D0P}
C {devices/ipin.sym} -400 -60 0 0 {name=p4 lab=D0N}
C {devices/ipin.sym} -300 -60 0 0 {name=p5 lab=D1P}
C {devices/ipin.sym} -200 -60 0 0 {name=p6 lab=D1N}
C {devices/ipin.sym} -100 -60 0 0 {name=p7 lab=CLKP}
C {devices/ipin.sym} 0 -60 0 0 {name=p8 lab=CLKN}
C {devices/iopin.sym} 100 -60 0 0 {name=p9 lab=VDD}
C {devices/iopin.sym} 200 -60 0 0 {name=p10 lab=VSS}
