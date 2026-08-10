v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {cml_driver -- one lane of the DVI-mode TMDS CML output driver} -560 -560 0 0 0.5 0.5 {}
T {Open-drain current-mode differential pair (DR-0002). The 50 ohm/leg
termination to the receiver's 3.3 V AVCC rail and the pad capacitance are
OUTSIDE this cell -- see sim/cml-driver-eye/testbench/cml_driver_eye.spice.
Every device is a 3.3 V core device (nfet_03v3), per DR-0002.
Sizing derivation, including ad/as/pd/ps and the finger counts:
design/cml-driver-sizing.md} -560 -530 0 0 0.35 0.35 {}
T {M1/M2: switching pair.
W=128u in nf=64 fingers of 2u, L=0.28u (minimum L).} -560 -350 0 0 0.3 0.3 {}
T {MB:MT = 1:20 current mirror.
Unit device W=20u, nf=10 fingers of 2u, L=0.5u.
IBIAS = 500 uA in  ->  tail = 10 mA.} -700 -420 0 0 0.3 0.3 {}
T {TAIL} -30 -280 0 0 0.3 0.3 {}
N -180 -330 -180 -420 {}
N -180 -420 360 -420 {}
N 220 -330 220 -380 {}
N 220 -380 360 -380 {}
N -180 -270 220 -270 {}
N -40 -270 -40 -220 {}
N -40 -220 -40 -180 {}
N -220 -300 -280 -300 {}
N 180 -300 120 -300 {}
N -180 -300 -140 -300 {}
N 220 -300 260 -300 {}
N -40 -120 -40 -60 {}
N -400 -60 280 -60 {}
N -40 -150 0 -150 {}
N -300 -120 -300 -60 {}
N -300 -150 -260 -150 {}
N -80 -150 -140 -150 {}
N -340 -150 -400 -150 {}
N -300 -180 -300 -280 {}
C {symbols/nfet_03v3.sym} -200 -300 0 0 {name=M1
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
C {symbols/nfet_03v3.sym} 200 -300 0 0 {name=M2
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
C {symbols/nfet_03v3.sym} -60 -150 0 0 {name=MT
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
C {symbols/nfet_03v3.sym} -320 -150 0 0 {name=MB
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
C {devices/ipin.sym} -280 -300 0 0 {name=p1 lab=INP}
C {devices/ipin.sym} 120 -300 0 0 {name=p2 lab=INN}
C {devices/opin.sym} 360 -420 0 0 {name=p3 lab=OUTP}
C {devices/opin.sym} 360 -380 0 0 {name=p4 lab=OUTN}
C {devices/iopin.sym} -300 -280 0 0 {name=p5 lab=IBIAS}
C {devices/iopin.sym} 280 -60 0 0 {name=p6 lab=VSS}
C {devices/lab_pin.sym} -40 -220 0 0 {name=l0 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} -140 -300 0 0 {name=l1 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 260 -300 0 0 {name=l2 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 0 -150 0 0 {name=l3 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -260 -150 0 0 {name=l4 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -140 -150 0 0 {name=l5 sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} -400 -150 0 0 {name=l6 sig_type=std_logic lab=IBIAS}
