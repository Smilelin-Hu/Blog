#!/usr/bin/env python3
"""Standalone entry for project-06-inference-platform; no external project library is required."""
from __future__ import annotations

import base64
import importlib.abc
import importlib.util
import io
import os
import sys
import zipfile
from pathlib import Path

_BUNDLE = base64.b85decode("""P)h>@6aWAK2mk;8AzX6==UrU@003YB000#L003}kVRL0OY++(AUtei%X>?y-
E^v7b$w3N(Fc1aMeNOS20|c?VLT?bEc!3bhPaLolNz_G8Z{PNb$b6cmWh1t<bmZFbUQ;I?PlPZ*Ewj-
+MBNYl>MtEy4YZ<0HnrkK#JLzRw*Ide@q&zg@PoJ;P)h>@6aWAK2mk;8Aza+v+J!Cv001rk0015U003}kVRL0OY++(AaB^>IWn*-
6FJE72ZfSI1UoLQYQ&Lh2&a6;K%}dcO$=3x^3I#>^S*gh-
3YobDIjOm+c_oP@nfZCedP+)4TmVo@0|XQR000O8001FeSiSiSQvd(}T>t<88~^|SaA;w3WixDHVlQ)OVRB_;FJE72ZfSI1UoLQY
4a&h0gD?yPz&};or~n$Ej8ve(M-bQ+V~Nmy`0lKTe0CiyXw<j|8++m!)-3JESWp?^9ooywesE1ZKF+QB6R7Wj-
x*ej+%0hFdg_<6h)jP_O9KQH000080000XT)!$s8C3%S0G0^=03iSX0B~qwb7eDZVPY?HXkl_?WG`cHZgg^QY+rC}VQytEaCxm&+
in^$5PjdTu>8bEgbzR^Dk?NWibw<~QiWD4ch^u?i;Zl9iYWiy@ol{qn!Yp-WbHYg%bDXb#(4hgSh0d>bPy%2kfdj(nBa);5*EfrP
{nq%xD*vdCq+y2{etuliWt{)FNuboqZB`Bp+^|wB-
u%EKzY79>64^+j@aQSqy~pvXrjTl@|conQdC4Ks%nrbS)qr~<dFJuWPBe$Q+`R3<bC?GnB|+*bh%z^7O%@SnxJcf;193n&x`eDzM
9YQ7+vwp>vXnQKI7ZanZw%HR`coX8y+J3b-H)~e89MUgP5(Ri=~10LAA-
?)|=P2H!${Le%VX~Kmi|6VLe8Q>One8ZcyasNQC`GE7y{-
J>&b6vl0$z>Gxa%;|}HJQ9!fej)Fc=y9CafY(Yd9W(J<c<v_XqBDj{Ks;G1^OS*&RGR}0K4-~C-
soS@HVL9?isWCFG+(M9H$T~AEy0zi-3_$=~F{QWh1oSvF@NJgVVM$rqh{I6$I5<wx;}cp6PGc@?7f_=}6KJ-RWR17n5vC}5C)J70
r4(|o!{x~WHH|T^eZM!H-
V1DbMj(3=x2M;C#%BCXDoEP5>)LYL4B0Aa+fUCB=~ws2ACcn`L^8Nyy9NbfN%znXDrpH)eRy!!a^QWWw=_0IOTra1*Sg)CAj%=qM
DD5fiw6TB%Iot^-
@?q9+^@=1)1=xt|0~Da7H8Q#%2y|@*`Y^ztgB1><I~key`i0uwY4LIqq&IUq$2h1c(+h5l8LY6!~V3gkIjmy;$a&SQv+OF^iXbOM
9e5`b&zHl11i+kv1$P}S4J;_X}R@pKBBd$B(Rm2T11U0hJIU(07vGZ)r_4MVX8F618)vTq3gCk;k$eFM`v@_)FAEO*vTY30QMOi)
Q=)lE|ciCX3882-)YvYst~+j74?;sR57?#&FKiUIg3?wW?(Fi6!!7_XjBHMtJ}8_6#^t~>i4lnOw$7t-
o6dRNlFluar7~Lrb~@Vn?8Wait>SXm7-5Bb~{j`mN<D@8VreJ2QwNkAg-q7-
LxKI%T@K*3V2Ifk!aOT=;^;DRKoP&CZC`u*xVXoo6n6Q(CiuZd=6WeK$bOf^|JLjB!2)<O9KQH000080000XT>t#(=Y|LX09qRW0
3QGV0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-wd~bS`jt?OENA<F*lh_g}#>FH)e@`YugS7*Nn_a&0asa)-;NFNPs#C3?-
AEGZ<lyN>Jsy)#47qNKh3NM5@Smc$tjhrjvY43~5Mz7x%xcNb;5?+PQYYr%fFy86I6)m{tD?xfi<C4TFLHW#(H6*UvLvJy=xQqK8
eu~qG!<@vTZy%KrO<i2Z_VMWul2IRGkUM$>L**0ablxR$9*|n$a3cai4wg3E8w~c={axeUQuWH~*g;K4WjCF<5Q$DA*Rk12eQPzd
luqnrO9!glDD_J^DbLeDq<C)$xhlG7s)O7*SB<!6L3g6tuQ`I+(P@egN60pfi;=bRamLR#4`6qE$EEa!1ueYFI_R;G15$33BwP5h
)RL*6!V%jJg6HV2%vN6NRzO6((d};u?*Lew}D+Y`-
*nV2E>$a`wqb>|s?2zyEif!w*uq<HWeP?pheiDtQne4ypr?wGRKySMKvs5GQO|Eyv>#x5dMM4_cXEwSQra%N%453~FH9>GU3!+wH
OJ<L>sJAh@_;$i&;js{b>om?{mL0&w`Aw_#MJ<09`E{X14qg!57IiO36_N>0D+n1_#)zCM7?xecFL_KviJ}bg1j`l@ru+vdkYyw8
?ZSTf_-|H{!?SC_1Ymk_lE^D7SSa+;6h7!B!WGU-THaKbJFyp}fNa>2?~Lhq!sw~_iM5Joj=K@2Zp%ls+;Z8#E@j0+byw_2TR-
vX^1T+SDL?_KX&p2luIb1f`0X8dYe;?;Mx_#vG>j~2&Gx;<WB`lUc-sMJ&8<{zvj>)h1S6)Xi)^;7Q_>k8L30N8(L#;`{<Uju*d&
Ozd+Uk=ID9qrI_H^S8hj+|%Y-
rwIK7JypnS7T*iICcP&%9rKa=U?Tc+=7v6i@j@luHu=v?@^tqyLQg`LzxJZVVOfFSNCt@?eZBS()@h+l~Bi1%iD@i&LaUZ@*#uOo
j`mZCF!#dy(mwJa(1UZNm=@+PLGA2gg5wC3Nn4I~P4adqef-
+<t`G%w5pGm(+@9R#_E9NAm$w;=|c(NdTFA{b666=$el!mJ%L`#2jQv*Kf)@RXsAqs`Jzs4Zl_9&}fc<uK|nXhvt)WOev#;oytl`
)v8lJ!42NptJ7a@Crb(9)1U_dKyS8Dz~Elv&lGQvLiM#-
lLU9=U9rTEkz5i3JhU5;bJf}UFW<8($Foe@Ve+AMj^=qC3*lEcHxnW*_Z6qa=DyiMQH)%lMABf=?K(FD>3rEINVM2OCyo`J@L3>k
LLgQ^ZTEI(fENKV#4?c`hm7SVI2XU6U0zOj_RTwMX`t~lcU}KDdw?FARsbK5SE<Stt0^~E^FKfIMv|ziiRZdQ1riEPQ#j5!&rXWu
bngVf4#lpgD;2Sike(@bs-^8|L@(O_wI>t=T4c}x<hAN3Ba=yJWie)2G%husmu0OsGRC69r-
HaX(y?rri8y4RTmG`BmN~03b%yW#FrDS!HMR)1|kBdoi1-
*U0Tif%&3EJ6}{Qz?jwrN$GZddFR1cz8i2F1HJY#K3;=#P3POJpS)Pm`3XwEopF)^LTvm`Q*cQx>V_4DPUM&rCKI~+@iBZAvoK0A
WS>b<9>87<}*t_rbxSp__&IKS|l`M7cdz=^ez(e)wOC14|K{8I{=WKP}ozrpd1b^DtPV(cXu4N<0()dEAr57+Qs+nr27Yy-
4WLF{<jZNnGky7w!Oj{BE!kZdvPL!%!49w_gIZ;-
`k33#4H|`5xN2^+W+)AG5G&1q=3;_qoA?wbu95{k*im$w72J+BK0aZaxsiMJN3HxgtilY7q_*{RR+JT6Gas^!+r#o?9$s0T~Mw5#
@oIE)J10v|TUVXLPgv!8{ZDIqC8WKK%;iR0LPh)3a3pDrCn}<F!am}D76!&=}?!xAee1FoOJ`fDAUPI9g+f&6;75DQi>j(Pe=LXj
2s{btX34#Ftq-TIG0IrK0LVtbas;$u>ICdr2kd?Mph9L{xDKrcMXu(6dBQygpNO^EH6?hc_Y)fx87sVFEGq>A{FR+OkwgEor!`{Y
cz!Md_XMC`7e_<{1)PeTl{m;`At=tvna&S>hYi_5H9CBmLhtk0X=gaEf$CGA|Mn--Z4Y81rJGyX6&LI2~dR-
W`Il^g13Bm<H_)E8MrOBy;i4Z<uJMyvT%v|X->>N`Hl}z9jr8_Z5%$cJ{Uj~-p0HzTrq9K_cPm4!4JAuRRJPSY=vG~3}BV<M-
LMfZX+T<E5o2FfRqm^B$ej;s1$Jrd{5$EW(D+Apk+W(r52;5d9M6xK2$?@o7gt~RI;8@e}>MUGp@bk|uH)na)lEHmk_6JUz^R-
<z7ws?ZvM2o!vZC(`z$5r7@HH&zPJ`T01NoL7u;W>e@Q361Wf8l4S+GL-GKUURa2cmLozQuHTCpPxocQzN)?HxrO+MU;N58h$a31
<A=C!|dUavRFcq^MtGTf$@2RfjKMr6!t(FD;s5&=ql&{Ct@PR}sAXkFU^joQrl4SssH!}je%+tzRIMcErjU%1)3R(--
u9cW37X9tYK5>5zKlSoK)f4!HaoNXH51xq}y+h(Sl6#yNi?rU&pnq<dto)f=uXpfJ@am_w7Z@y;aZ-Bj3@^`xYqN4F1qEG^orMuI
IGL!ovYnFJYCCB*wx!kp~q>T?D;>K)3UXMB;N1EA&+v~WkRAgDl1{Jca3$)Am#9&u(gQK+XN*Q2uRG*4$g>&{3sbvEZhkcQw5peN
LFGpPjCsUvTj*NRS;u$YsTOqo*r<8~PYdV*+<D>F%sQr!B05r|ywn~XZ9fNyUe|gks{I^!2ODQv#Bd|q5^J_YeX8TyLzFvX>{s&M
?0|XQR000O8001FeaZv>?xdi|Ks1pDH8vp<RaA;w3WixDHVlQ)OVRB_;FK}#OZf<3AE^v9RS4)rEHW0r1SFk!s8`<?XeIQ1>XwVi
tB?#K0mxV!aC3?-SM5-c{T_@Q8-r-
ZEEPHckfM9LTa30@$Gec)t_MQ?s^t4`9q$3qmN3?G!Rj6x7MO(@hBD{wGh(2`<0|i6|C1gb!+9RomqNpX+fpNOZvTU)~_o77@?*|
1|F-ENIM6Zo-0m@8pxmdWfmZ*c(uZbd6L!_iKT#z-ZR5^;QraE?v-
+QHZ{J2;wehxZ0=zOMp`&U2EVquQZ@7?g{!?0N(_{T|0HxPAizO}R!{Sn`@yA32Qh%%=KG4#z5S3;`znDI{l2Iz0#qk7TnFAmL*0
<^7j2~mu`MNOOWYbAI!^gZR3vu`d8fG^|ZuAx|o2g)VxXpbcY?K+OFd-DTsWpYBv1D?-
MLVlG);iW8orClSAngt&ytv7R#*R%zKT#j!(5JmcXs_>v#!#*2oI4Rnq_3Ed!y-
J>Nk{$?Ouh;996En`*p~XGb<RsF72P)S|YA&0Pp3<|4B;`r$*$TOWUe5Fkc@C7+y$}$m&eKaAetYzf6g-!-
*%xSegEa4NA&^qjduL;{F+odl*BDkEvefsXS2?ajt#Yo5H7Q=H6NG#kCe^L&iCqbmG2O3~yewhv&O|f;j_r~5usT<I^cJn7unChC
{Y{#I{?_-R&og@u5Y;mQ-BGZ154e1ySrP1mU=4PRpHrfsw@~6sF6<Q)UumJ6v@^z0zAn-
A&Uw2#Vn7Bs^9BB_+=PIGz39zf(AUU4I~MSo0k5b>D?qaY3%5I?q;GZ_J$*MpI7DncTGuOxG&lMy_*MiRfWe*`qM~oM77hE&2Pe@
7!Rct&4HL!qKu;~%-
q)rw7gwEq?Oof2=*C46`V#qUSCgRwsye&q05t98^Exj?Ge|uR0Xmn@r3s0y&e11oDcj~?5E9C5aFdZznmx6uC~NY|wExx^u^|G%=
<-cbB;^e5Y}VsSxtz3u&Dr3vpT9PF?=9FF$-5$5M|qtG_U1_hhGN^1ZDk^b(6_!-
Qi=Dt4cMiLogJauUJMXUnrMl>FH!^1bagiZqE`mdNMYu7GK6Pcx)NS2v#V^0evIrF$>fTr#AHVOF+gowH>LI&7k)m}(Su7ud~(m=
Eo2MvWvs-
r8(MA`09W(TS&1I#aodpgt|o{n+HO#;|D>=i?NI_oY1Ga5(L2Si%Xi_Ow+WjHW9SZru~|PQx+?t!Hj7fX%2V{s+{QzP9~rO3W7y8
$c@Z4)sql3P9Uz)H(RHzj+sQ47t&hQcbOEHiJlPM>dZb~sXDqtYWRTg|tvWwH3Q+Jc5nEp<cumDUKzuxRSGONLWZf2F$^HmRQ~W?
>dNg+-hAv!*57SFiwBgG1D7|oC_Xi-;U}~~XWsP_|C-
O#5CG=DD{z#uc4wgVb#i|EKJ{y~(8Zgl}Z0Dbfr7tfYCr>0i`~EET@0wnn^7i`T`)nNWi9gNCwOM`cO>^csV^(_VH+@K5W^(kajP
Y(z5tliAgzoorltY_en>R{5nAcFuN1cQ|hJb7g#Vl=gQMB3%R&Jb;-Py*-
<3=iD@vAuOBHGyh4or_ryRqXoEoTglt9xVz4EcPvP**dhDdH7=%KqueE2yL4fs67cO{t+SKnGNTXan`U&_k1hsr|RH{fRA78E(N_
?*NUL#XL>=F=bfVs!RP-%8O{@uSOZ)Z0BcHYL&DupAh*nj(mBF%xO?gvZ7B)zg=#vBY<SmH9IJz=7#lIqIEH2?92?C8&<PJGR@8-
z0W)hn=fey&)E!&V_j1elifFuW1zYR&;tw4lbLj#)^-BSsp9<n{-
0nmY`XxAUIY4vSYjo!rn8M3Ch4Ot8~YkG#xD~sj}GVrpr#st5Qs;(CJK&zpmM_1iKfjP6zzvm`aHMx{9D|7E2h8p&FSJlP)h>@6a
WAK2mk;8AzY5jCqiKb0077j000{R003}kVRL0OY++(Ab7*05Wn?dMZ*_EOZf7oVd5u?5Z`(Eye%G%c^dzN<=VVK;8FR5cbT0$;&<
uMq41t!Ym@OrGBGtsr{NHyxlA<U(ZHl&*?vBU1@9sWQX_`K0s#!A#(#t{f?vWgN-
g3>qFhvH%YO*_`iuFX$og%cW3GXy}>|tFE*76gpv|6NTnj}pxTT+(IpogB7CE@Ks_8Qi761L&8Q%T}vd#d(=@9dJAYFY`Z6m06(s
G3*02&#fKoQc{l(8q&`)!F{u9g`&aZ8S~rfAXQL4-
#U<6jup>KOJq^iYVRV+t7>f(#o0%1@BC6K(<9;MGv&%`nWPVlQp?P>7G%c_aNL!DM0#nKQL7At`Yokuf6#arR=GtrGOZ^>R7h0MI
$6dZwqVCP%Z#46)#gmRWSoeET%O*Ks6?jf(oI@YSz#}=(3@emi=)J26=*uKtnz$*=34}CMVbLi9y$_E)05Gi;ns8g^GcJM~lC;kC
mI$LY11072wZmG+S8lnY9o2%-
$=)ik?B^bao+B)Rys~rM>=$Eoj4pR(oIqy3X`w!>HmrE}%#SbR%o{GoekxI~3?W>qsa2mJ0qA+EqYb6F|SV{pz79OJiS_7*|1<Ya
GB>aHTg<BW(+ERg7DdPs|qF*L1n~@eb7Du%}bu?Oh%)<_*N8C)<n~1c7qJ$Ug>y4}CBDEOqnOF;=UvD$VB(m*m&=JTfD?`Q8TeHS
M4PTn2yj69WXlvR>lk%Z^>#)+YS6z0lI{z&nyH3v#oaxW(oe(**d&=h$Q(^;zySbKH1sLyc9oZ%X;pL61#F!%f%ADK@WJ#g$<**B
|jLnH8IDXs&86rDCqNpmloo@4%EUd5z>#SmtrhE|SmehyrkxriGvRsfaySVyIa?p@IL%Ur-;=n;#tV3k-
;a<klK!{iE!SqbyXRf_ihHRAwr$iHhp$K^j;!zCbDC%0+9SSG;23_!B#76dG#Ab^<?RRK^0~L8&*jL=!Lf)C;{h$~=3Ifo$ik8<M
=#wjYO1^VT(PlXlWG|9CDS0vOKv1%FPHKE`%3oHuW=#UmgcDxI5X!YhH?7}hWuU70>omF!vOlUv2b#d7Q6AlL>;ry%afbVi(;p})
yc1>}ApEq%_;(1YpBV+ZyqoBEg?an6<b$2Duu)CM)9FjWmD$YCdT{Y$)=A8C){eCPo>hx2;YO9<oA9kHW3J4xkEc7sA@zPU3#oE&
?~KTliEpH-K=x^pW-Xx|~-ldBP@>yX5C9Dpeg-
3eA|&a%J@MVv`Ke@~`#1m_@5a?86cU|A68q&2ooer6p?{?1=%+)Pa9Cra?Fg*U-
+YfEE2oA_QK%LP3gAdl=N@|=dW)769<i`WW>3k>jgrVF8fL3o*2IpD#>J<aq!g>)5XGc)tlWX$Yc#!K><<yedo%b;MzOH{{|xmW`
r@nGkhC0sG?^D}Y{#XW_cPG^@VAN=G1k}dFpX0zMPj6v{hI=iJ7M1HpSTx1x-N|STsj6&8p_simf>Uv5euM)?4dRAXe;(@WsZoo-
U=b(Sh&$Oo@fs3ctV!U9-
V=zCh{O#N@%rbTrx$|ek<a+@1Kp3wCFnWI5{_of1_D%c$L1E8Of4Dz?F0IzJ!1x(d#NRUCs4=+h*t5=%&?5q$UDqIV<b32{fXp!%
-bs=R`4O&WTZRMpPj<A2ucf_jr0kxi8~Dt=gT48#N)kL^FLAMhDGUv~B1||Q)_Khz!PrD$KWZ0hPjBz;;mYt59GzC<^q*3|s{$s=
@_b<zyNj2bVGIzybIaWk#yztpo7K-
i4C#(Pra2t2+3nTU{ZDqR{s&M?0|XQR000O8001Fenp@7Z#0UTY4Hp0a8UO$QaA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCxOzTW=&
s6@KquQ8cpDBW8NF3z%q<iLkPcuww68SrfDvt5xo<nW?yMsj41(uttgyQY3=JGmi)%B3^hvA{Y2K?B?>sU*J1cT{Ati<8dPV;OXi
*w>p>aoa*m???I#0gG*UH5ao>3b2F{V9|mC<zIA-W(yBCyr-tz|V@lMOGVEGOBNWq9u0+Nz=gdq6%lV~_gWzl`H7lyD$pxE&Cl{L
4c~e0AgjHoekJ*u7vNWPJvMPC=&#ewFOU=rPiJMv|SztGS6u~m7Yi`o1P(vnWLd_W@>Z-K%)T(-
4z&72~buOVv8qKQf5{B~JQjFz|X_N@AD|I!_tLvD~6$E2d6)Z`{4Q(a~lZ8DPFU!hsvP%bnf2SrjS6cY>l<R3OFa7d;*y5in?Vsw
Ln{lNIzgDoNTCVhbNoa6XXHCWpPjjv{9ivsPGntzHYRgf=A7p{2I>pj$n0ZZJZr>l2^FDhE4(6A+2!g;$V5dsJ-I=6A9x7F-=-
s9yE9{~-3>g04qcen5i4Pi~4Psmft{VzA>1L_*6H`rzK-%D^jZz31Ljp-vl@z|%Iy(62()b8A{#ulyGu4P*Yt1pgd{&FpX@#MQ%!
W)GW!FZUT&$Lpis!2pMK}>NnTaw5k!k8&oMW@k;yAu&Nj_*Kj80@(H%4zKsv2|mCQnmQ8@^RT5FBLLftoaQSj|RDSD&Bzl!^WJDX
r8+pFOEcaS{BYO~&m^Pk14a^Qizm#oy^fG%rYLCdTZNYmr!D6=`yx_hXL@-eh-ZcRqGpP<#hflnI?GSyOt9NOo+a(CaYAJj)W^az
)`_fZ|NA22|T&A1<@3p*9sN%OKWxITd+53THf*$Od6EW>x1ah`E-
4p2j9tX%pFmI~BLZy<4le5h|5hI5kzy@@gVetBYj<I9A9~YJ*p;IQ=>+329oiL(+4-
EP&kxxnzQBM2R=K8HEssU;V(ziU}=ti_ii}`c%qd1e9Ef`pHf<N{K<E@{TWfU5hg77;}E%eFAF)Hw*~H3hYQ^HhT){gQG!O6{vBE
lteLSbp;#rZi{^perNU9Q{m8~#ToYVcaIsm2WJyx$u*y|OC*CAkNBZ3m<2k{X2-
`TsDt#1bnG;bx=7wJqtfvNVJ~M<c=Gh|;c;^G7`q{FOcnO-m!x-
zdU9}b_>825J%3hMU2sGdGCAcE1kVUiNfv|udB$sMrbmzOaWi^dQLp9J*MI-?>%ac_n~#3S-gyr|f-
?N?zkmPo^M8KzuRp&0=!+MhefZ+DzrFnQFJFD~@t6Pj<jddw;l&ppfAgo$|MTH*b}MS5p|@t?YrB!4DqSZ?=UcfS?e;If8I<CBU@
Am)yZZef^;&30rIxLr78QXSNt(-bL_|Jzv;gM2pxt*}#Losp=7G8Iv0%%d#aP1e4M5!lWoPJ`_Q-
9wJ8D8*qxFUTAxa&&Z4Z_SB~VqmE&A6B?7kdZ39$v=guvI?V{KA!T0~eAXH8M-=ythfySv7W)97%>LJz%(RTuWx>Cl-
#<fagJrVRp28o8jO*_jEnYyOOr#0`Q;vf^9xfhz>13D>EVqqljkMIUnnikuRpx1@A2cBggoQ%vA!onW6FsjeCYbQrPFw}Yi`+7}E
}D_FRMaK~o2#rBaM!D9Ls`P?F?9&Yqr5U#u!YPh}N3A%)K2Y=KLwz#)#WMOyHnu|^M(Ajb05A9Ifb*s*{?ZbZ8E;^f(`<B-
|L|qYV>9D>(b#L8TdX;bk_Qs?MxdJbXI@&_r8Sp^9kyq~OfcJj<jolmXr)V>OJlz^g`_Ls`bSzj_6ZwLVMW?)Md2~p9c5hAMg_|)
|r*2%cMx-~Z-$~w{S8FNXR_IC~rP8_22uh-
`rV+nQ!Y++dZfV@3r4TnXfxbGm(@cWB;citOu4K$*zD=(nah4vr9zo{H{4q^N)5KA_x^ojwzvW&f)JiO;S?k#x*M{QoMw;kR&-
H9b?w;t-
{z$sWeT$RaZ~QpCrFLNt0N^PxL?_7tDT)`1@c%zj@LjoGQ@RtzhwRmXf1|bdbn^|Fy}=$1Hyr&Q&l`7j>$Yx8br`2E1*<EK=+8vk
@s~|w)u-<l+9ke6E;@LE4xYFUe!uATj=xR1^WwVS=?-
cyg8e(NdKrZwLs4?G;a8tLPO5`GN}+Y|>$HX58rwClY>Bp&<+4*%O__D+*}xmnXZwyBON@#jrrWwbLH9kif4VXkSD93iTWEVxMz_
4d?IfwL+Iw?{$$o}OjJR3r^*#}Ic3JiV7XGRXi7Kr!w5U<onDO8>KN)Tg5Z_8@mv<aGmeH*<cCn1*7R<i07S_W$^n(#{9G;wk!Qn
0Pxt_P(8-
c;#VC$cVZgCHh$(5Mf86VeqtzCA~+R@Szfif^W3td;BixGJ2*A2S%M^0&PmCeX_5X69djC(yITvP1${dSB?ilz%^6eg|Cj;Ph4&c
S2h?hTA7=vyLtGwhDLj;i%zd#=bj3O*WkDLXflr>BQc4vvz8)1%~_!{>C^!;{mq=gWB53rgZdyK~ywvSM?j9{K-
bP53#|4zrk1vW9l@6}=!ISoT=gIdDJhhqhyOiTwwR_R9=Fu|cjl-9x9%)i2%2i>4SdJN;vj5&6ohHH6GX>7xU@@q8Po^Xf-
0v<oYB;cdaS(?A#p0^PP!7Olfy2Tdv@UE6Lu>Q*V;4qct^S3n>^@MF#20!GVt)qIYZnQLH9z+!ky%=FVT#`|NeTuf^y>MhpNqWvN
n>nVTq<Nc@=8Qan(^opnACX*B3TGTrqKHT?FSjW3I^jmCf)mVVT%drKyaPRqGuNdrQXL~;z?wt(xp8b+;Y(z6DEQJ-
=Tlxrakf^ExG|0S@VuXilYAiq!O%IJvSNRM_Xz@{>Kk~NIKoG%n%_m}8W;hgT3FtbPi;<pV3^o~Nh8EB_N0o=Y;D1m{0|XQR000O
8001Fe^0?mzw*mkFlm`F+82|tPaA;w3WixDHVlQ)OVRB_;FLQKZbaO6nd7V{FZyGTWz3;D>?rFCL3RQ^&D!uj4bERHTgdBDjEcs)
xy-i8m|K9P(E*l6*S`-
DxGw*pk^PZFE`8Uag7(s;%stVQiIIayMNMyD(C{a0JyPd%ub6hJs$@4tRYNI7=Hg)SLXR`q=8*M02DeYojmZd$(+`d~|AGD5dZDe
rAhO1qN{_4=MJAql2RairVW=p4YfyECdTC~ePV_gf)-0cVsO9;yn#-HPAnE`z)lZ`+NE3m|jRS{y5r-
WJ?2ut89E^HZKyau{JhmKVKV;Hvx-
+ks6W3(yqQ*mJM&~ihEF$aRW=0Gb<9Qh;ODSTSN!T*{)$9(|V63ZRZkGn@y@PI~Bb1ToBC>w3LZ!}%85U7e&Gc^KcCA@`0$P)UV6
8s1z)Bz&zV3B0ccl$2BMJ~?5RCXX(g~UP0NMl!Bo7R+b8)ElJX^sf{;>MmJyMm!Aiy5UvSPAd?s6Wn!V<hQ8Fz4mDv8|NM9IuHYN
TK3ex3<oVqA1`uP1@a_Yh(SADsKN#6{$o>C7z^_uxWOw7r%O@e5+gK@+Ax>IXZ>OjA|n-
B^XMqij$8fwU3=J@NtN1=F=f;;HU%`!E`d8UceUfmtl+fC2a8u*y0=}+0P-
2{(Ry(f076cb+}Niq>(#qlKcJZrL^Q~uy_6<q@Kq!;@o?h65fM9Hf|5NsDK%cXCLVMrtF?2MiZ?z6$;0SJ7!UEg)}*uNB=Bs$*a7
gQXlQVs7&uS5<o{<!kbmt=;=xzje0Hi=RWsDg+hC|cW;W)YK*dR$MB$#K$-A|?A$)7Gu$lL!vs5%hp~3S9)2-
`xJ@Q`;7wob;L>HZjq(2o20XFHks@~WKR7R(<8Nt`b7JL>jZ<;5P6%AlW&~X~!t1b?Zb(OmE<A;e?di|G>4p9mP)h>@6aWAK2mk;
8AzV&jiGYCv004#x000{R003}kVRL0OY++(Ab7*05Wn?dOWo}_^V|gxcd7V{DkJ~m7zUx;EbdpiWXs$-INRXzN7Aa6HdNB-vD~)%
F$fQD1PTe&By)%4?a=ee!z+%PWJiqxkQ<mi|DxoZVp0pJp+E!1>N_7uHb#O<A4m%K?7%UnvILZ!Hd)|~~SriAOkI*!S$xa5F2IO(
j#*(EXUsh^02Ax*-J+@8~mHsdt8ti_NtzAQh2Ql@wqk}i-gcWTs#u1Z25_t`K9yrTz`A(gSqHx!6t3RRo9lLup+XCoE-YH9|q-
~mN#Qv~`ULK_#x4;p1qcv-
g%I;TQpMUZIR7B7NZK$YobrSuA@CIJPfh7JURZ!Zv^H{AiFZ?q?jtGD8<p*Q5sY>e+55AAnXyFcF(4(~SgykxkbFQ19R=Zp)f4We
iwxBs-cUcb`&B#_Hx-e`Xgt`A8c6dU?@bz-EyV;hyuxI1lzDU4_+yd^t^es4bgP#d7+sG~mEO(CFazJ=>L-f=Aq9p-
2?hN6c!E+7r-|*}KKa`XDr1Te+!hiK2-
!iP(y9>|#eXfJPC`a+9`X^38_TsKb!X!&}=cDi8)uIcR;@H(FpWU`C(sS&{YfQPGW91b^&1F4Ty~9t@+qG72#4w=hs;{Lxms<!JV
7Z1sXcGF5HDAWol5{?>u8YCC?t>&TNs`6SZ!?AlX}G9#GZSk>Yx|e+YJMM*vlFeIL_gE)qgJ?G!o~_jgrD8Z_otiL%`@x>2B9~RA
9rZKAS(C=jdsH|x?7U)dUM`98T?Nk*~b{(19PM{0sh@0b~L{xJ6ej#6Eov(`N$lZnOLW|R|iK<9$)nf$>VeUQSKzfwka*g9}eu;!
ym+*qIf%R3%?ZJ`3?4g6Yvm*o#rUw1P_u3#3RR@@I+$`J%iw1$C0#Qg0uIceZWUoOe+S_N_!5Z<2%W$b2F2i?t@o)#r$u%d!q46h
EZJ3$>zC@k`(J?bI~?sjYJy6*^>4Xo-
^eMpIub5cixII8=B9dWPU@t{gn}9_0&F8!C*DNY%ljH=3R1+_4`I<>pE&L5%UuyH;h5+k|;=huW!wS>)7+!^&|P9d#X6AE5|5l1>
4ZgJTd0g_r(YM%~7AQvAW?0lAuUV`w^G6<gZ6n<t|omQ!g94G|94CLlaj~j6di>T0B-nY+L^-
DB$YRWOpIK{biL;K^*>joat|dIs9K0{{c`-
0|XQR000O8001Fe%Wo#Ebp!wa%?tnl8~^|SaA;w3WixDHVlQ)OVRB_;FL!TpYiw^}WG--
dtyW8K<2De!`&Y0$NvW(&&>jk7y=c+yp+&J>ph0^u0)duBF&m0hNh-FR=D&AH>OsG<KGcUG;>>)U`DQpXl+r(#;1#n_kzaoQ?bEM
htMrpltTKejiZHGDGZS;RWg3WvR<M0eDV@z~tr}7kb!R&bML~GeDs9n7D$6Wa(#&T4S*c{%X${imLEQ|Jzl@T@|CTopP|+P$3T6z
L5!O_^wAmyInk};%!PkS<XZ#ETyKlLC9L|4``;7d^gkWm{v)SzX5hg+He?TtpbqDFpACW(ifuAijiy6V6hQB*7w&2x*7_0r+6PM9
fix;+b`fk{+kgzSRdID({giGtsdoGJ6oRKBD_2(8OlffR(XazOvgrxyXRUk$Y>#PdrtYWPNJxXZr3DkU7Ji-
1*z#H}mg=6bTPywq1mk>Gi%`N_By|nfzN(_iPCG!u&WnqN~nd9^!FcetAyvjaJK^=K^_O6x+2O^T`{(pU{Jfh&nt_I3`M9cIeIA5
HWH%mhpHNooY#W^=c%>^WB<Obsg2$pmQAGKCGsp(M9#OabsVNE#<*x|hk@)EFKX@3FwfJ7Yngnq0Zytr1Hc(!EMtN}^TY>TWBz;D
p_h?3qljkFdPb~XW7stQYSNjqE5zoThxTEVSDF-
e+{yU6=KJOs^=B;Ll6xgWkG%Vh`Sq1F3Cjb|4*`s?`4{VProEgf}WS3(<}UGARyPk`P9sxWs>e2903&w;VUOT@&hE1qZ9NqiTfDe
<om@h<!7xJFk8nv<Iw@BN9h_xtw$^)RXk5EZ8T1yNtm`TX4X#=`lUxIY=Wgij~OeHG=bZ9!Jv>Y#c<ja^l;90SJIvOld;Y|mJg4l
17-
l&?=uE7qjH=3%&4fK1RRC0{N5{|2o8e(UW_eneOJ92wGd#*#IVPI46WUiD4DV9SLNxXB1MqorWYx?<j?1@VG>YK9p(3L_m_$0_}b
v0O5;-GGL%oejQH-&8&+35#RWqbuH||HUI?!9-zWCfpa-
P|=fY=6)Vr1?e=u0M?I_tKfp}c|Z?#IE%=8a(5l@k=>B)RvB*jGaTJAB@=JBz3zs{ru0jL!<X>L&frH=>iQ63qci@85(^tma<=bh
#DJUg!{V@tMTdhB4{ow)&nfqQm}Y*bDNM-
(7HW;<>1Ntpemf1mBbc#fBd9M#Ok>r{d73;S@0V}ph(@Xx@C<e%w=pg~Y~F&di&AwGH<BcsRtHmVpz1{53#PaG<|a}30XE$5^+~%
R@5mi4D2~K;QB;#XU_ueW;mpta7meGX{2}JU&njnS1VEd3jmf6s2G@~tb0PF;9V(S}{FuWLFv(VQWT%*dqi)$a3i!lu@L|x`czu;
5qigely_DQ|t}^m%dc3Ixu#l@Qx0^FddVargd(3C0#K#?!xO?iv^##{zL7Qb%c&VGsEh<ht_8@LdIYDl^b;EHr9HI_wKfN@wB3D-
d3fs5Ay*LRb;mjHJ7d_1W15ir?1QY-
O00;m803lrY*{Hvr5C8y>H2?rC0001RXkl|@Gi+gEFK}{iYGq?|b1!f(HeYFOW@U0^ZewL%aBN|8W^ZzBE^v9Z8(oVW$MOAsMQ0#
*#+jYllj4iD@fw6BI|_<?NG1@DWtf}ky&K=`%y>R@cR3d1fP-!9U_$)jI0gp-
F&O(Hfh1t?e@UXV^pwAls;=&y?wQ>^$=G_3X1lAas_Uz(s#}iZ>{Z3<JZ{){m;L*}A6S|<{IH4|p1|jvS3Hk7E3>GX7uAAQJmXQ#
S(GR69T)d`b;eGL>Uf?NCxPQQTU+z0Sg<ghw@q8|Fl6bXEUE@p<V6!TX_41kTWYL2ETgLC>i1DpA7$x*`uTcY<m$W9Kux;fM5K%w
1XmRH;HM;C0w#Vniw=VND5`i8#6{jzMHa$Fa;_HK;AK{vEqLC%MAI3se0CQ`(>Pj#=%{JRFwRm~q|n60qRcq%%x6hj3!#LIBH>x>
vjuOeG_FH_KTS}SYtSNJIj<DT>upoiaRmIVfv<|TN%KPme=|?Y0yK9IB+PwwZxL0^T>x3XzBS3+jt=gXJoech>NHPM+|13YDnJ|n
iThoHrv`$xLR0c82Dzl!x?MIrkMj6T!M|1<^ZYhX4%f1YmX#GzqE_H{h-Q&(ZQa|u`4XEd-rX$*e_&~tCR3**n;wmKN7{%-
%7`6bz&2@<@u^|{|NH7A_>r_R?w;Mg{R?(WJHVd3_OOVusdMq}yWhO?_Ql7aU;OQ_4}bgKe;&N~Qj|y48GO6~dN_&B*y9K9Jo?9%
F!1=T_aFcHPw;W^;aiVC`uO1=KY9G%0segFvv0oo?BN&xdieYIF5dnCkUjeH&5QTHc=Yur7r*-
pjQsbX4=z6c^x+rpU3~cWM_+&N=u@Ec8_7n+qfA@Y)O9K{U6!SD9-qY-XZ$`Wq;`DfWa)kQDeZ)TZDnE@1f3KoV8a!tzR7uAgIlG
Qn0uoIkKK;6EpEp}-7rPZ@e~tpv?(YnO!KmBYG4D5;vnPOF$9S;0YPZ80;`TCU}^L85Ql_aG)!q*VFm-17y-ekDMs)QYpMun!y*-
m5+0{DXbi{ZQJO*2(V+>);;4+`v^f(oOY8u|1jeMOL~+c^CL#%@`TZzM6GMVPFRz6|)C|!RO0~1JW+cH8Mgg>0#RkOB4y@u33;_W
ko6pmjH3cIfAvCB00BT;{r|`&X-ZV5dPxB~4P$I=oQNO8R-P_vQO8A^bNfJUFZ8411t_Y{qL`T-(x}4e*6CNAA$nF$5pNOp!bYP-
zoso8wk=76pirTE1I<T8)TYA@cH&l=T`lRD+LaLR!9-
9IY*s{&&q^3tv0|=Y5l25_DI@DKvcEq!C>Y#OU(0Q6C{FFstWJhUy#4HU$v^)lNk=B07S}>~74(bS^xlodlHTWBa9~Y0F2`Gjn+O
%*0>?dgq9KhI&q}u?$ynzsf2a{MqJ4)vajzT#dq;)t4x~@lyghxdwurP?l?%W}Tw3RRvmK3}esQ77GHxqVFD3?-
lRdfQxB^kl`!CAv=muA7vTMqNModBg?yRg9G5Zo%Sg=e?|8jrWQ88G@woFfkV&dnAr$o>HG1@`lMuijzB0jgT@C!B&w)bi}d$baR
zUBOFm#7~p-
5Y*>tYp?6{Fc(H3H4E`xD8g6A&jeE#p%xgOnETmbFH98_eqOt_X)Cda<)MOCJ4ti4zvIK&ncT)f8y^cb16jAf3(aEyArn#p*RyuD
KY4!Uvz=X!{gCa9$EH}iAmbqalFAF3f5<L4lcCnp_9;SQcnGUp5ymGF$?8U!CJ<Ugr(t>Rxlq{8gh9?0fyHV<A$h=r9TY_-
B#7%Q5fai)YQ*cgQ-We3_D$H!5%49VbA%yb!koMaI|>vmLw&^1$ApcS0%r$U9D_vnaeCj7#BARwj-
43;6BDeUHUx^9ST3=fYe_(o?q%yiTM%ybT6zA2VtD<kj%hG{j`_`M&gE>ls8``a39s3%wYdR}!4994&PvhDWat0`VN)Zca|gTh**
LiNoX57&tXu=qW>kWKmGjXx52+93g(q`wd&0bhf#RV&*M|X`888NCrfV9DCvf1Xwt;R)=#PHV#=!S2R}fQZ-hEdv9r9dTeP`|T;h
QsL&l%6j0X<_9crjg}g~X#q;K62kYvh*f1>HV-(6-
f13<(&39XTxo0EMa|Ph9cKXS*i6B`$!pey_w!0tC?h5J4|x$eO38SSPx0O4UZ%awl5w8uB*Y3q!Fk)W8T<)o=22>)<eRaAi%WQq$
2`B#=A!Hx_i0?QI!Iz0J$@UL=Mq28PaUB@%Q!m63z@*~Cpu#))bW?h;Q|Vu5A1U%h_g)}2=X0|nTrBLxVV4+=y2$&;YEd-
M8@U#&oN1Vu%2#2_s@;LboC2CBX^UcP?o_RSkBFp88+doacz2wvw#oP*Q_gU^J$R$(e&Mz9IHHeULy7pyiefP)lQ^!)%qmlWRcd;
}hb$0bCm;L7ksoZ?z5X*qW~nS`>)nwWB;v93%JL;&Pa6zG)LhZWRPqI8+)le{ZpLRrKJC&J)_OZQdmnJEVn^$M~|8JA1{Oej^e(|
uK`!Pd_m(V%dAlW?aHU6X}bx=5*Rv-
2Sw!62|IkQhZ5ekXhZK;a3b;KfNDHl;v!RJ2ug7GgmbwsqoA0<cIS!OIVU!x~C7p17LlkxVIrV}1rXtWH$riVd0Ee2|r5&M%j-
^JjeaOz=9Cr>-3HR01s=xX8Hay|$bT&y@+%xucZ|kg!E(iN_5Q-
bZXRxr1)$8m`X~dZ~Dpf~c9oFAgmvAbnJoxtds~1ex8)!X2Fm1>97wf(W2QfGXPnfb11F;B<nvVQWwy_5j!qreFwQ;Vl{}1Bsy&D
jv++EL%iPeB@Tn{&;jP8qH_tyFXq6R+Em0OQ7I&?ZGLU=on-
Nvy=tc<Qr@q)o6@iEy^T7JN7&j^>}kqFQuf?dBr+)2coKiYy`HDV-XzlqasV-
s8PJJdq2BALdj^MNZzEt`!+qhoT1(l%~x4ql)cZLbrqSSY5VC+)@Vu*YoKsC%FkRZSw#H>j6!*Y22XV%Sp1r$fdD`c+_Wug5p8M_
m5hdKtgY1siD2FB6H_NedqwC#nX;>D10;XFh4JbwtVFYk{ow+ZbDq@LK)`Sg)%#J!xiFNRLtw^@NNBTLkUd3S1DyKuU+JM;y8*ET
DvHTSugmxq;h*MIKPAN8gX%*FRBFbC1CXx4>RPLN2#LR5v1=``8V+_PFXB9&J}L-
FEzyZIBLI2cgLCwtWEh5W1!LdL3o4jROV`=ffl!@D!^Ku<wPrn-ph<jcBiv*)v`j{lLGM$$b^;Z7n(H=*x-
yXGvfSUKf0f{NOnKHBG=#Jm_Lgc_=r1I95lUp|rS4p&#=(xA^`1U#O|9O0QV3E91(+Z9H#xWsXR3(>8zz-YlaMzh2OJpUwk-
O$C>w+^0PRcTyRIWv8>h|!W}a`@(^J(KYc1D8ZtrhUdW326-
BcfdXk`JCXz4N8?t(<Xdm5bmN`#D586vd@q*|#gk##plT9MdD7YjwBTvQj<g_x1Mb(-+mxuCQ3b!LMt<bf(F-!SsoE1m~Z?-
4LlXG<ZMkumf-ptJ*&WIsmS<-x{`n?1L;Z4!AVuG0Y0xLkA3(UKtR^h9q|9hYb%Fz8=?<fjc^Kpa@A5-2XJM2OkyOzG0D-
xibCAyaA&5{@=UwlT%W9(B6l0pxOXIK|q$(cXs~ipIUqkOgFs=k0>y^|U^2%;+R;Q3Oha53oSV`AJCGVn0<UQ3Z05D^}3XiCoZiZ
+(rrpSF`Mf~YJ(9qzf)t$|oHz=BrQv{)+A<r>s@*bt{%BciRA(XXXvkwa%n^Oozugx9j7Gdkk~vOR+{%ea}>QAl%Q2C-
q5pbAk)dR~MyR`?;^qr5nTz)8)`)M{UE?5+s|f*KhKhoah=>Y5ZawE^eA!bH<hF3`yNX`HnQovy-Df*g`CVO#QIEgwV>$^jH8lsF
cL%K_t<tO=(K;-
jLdxzYHa4zwZS!BqV1Lp<a2^fUxNB*5;suQ{Kp56`f4!Z*yLD2gb>h<P+dNtXSHIblfm?4hi8bsHiKq1?m0YeNtM6$>@xvPvNaQJ
JaUJ-A8^frxk(bJCX}ZZAsZShinw3qV>>_Vxs}+&;IZZyYX4=)?)veE6*E2u&r&K{w>H;#dzC$DSD()ZT4B$ELZ4x2L+a=q|)Ah-
5M&Qg_jW5DRwFK%4W^Qjo~bnCR*91g{-+S_B2?VH?3&*}%+5bwmal?L~%Rw8f^C9jr)Nc-
<LNm(M=9M0g$soTu;n&7C$s&Wn?Lq?;9VZcE<K_XcV<HWW25S2nUwh)Rd3Xc++zRf-
~sVE5YciGdkoA58S)Fk)lxUg}d6Sf1<*ic?2ix=$5A=j@a_RFH|F`6Ismk<!@+-
D%iy&5B^Q5vlfOL!C)5k;bJTPZ6i4UF7suVON}+j%&~*=l!mnR;HVRW{(}EUgOjx6+6}<Q(5K?l*VkNN^2&hsh$nz$Wy3^Udz~2u
op2D>GvT_+5Prb@I=|y6Xzjj#bi6eie5W?bo2erdf(~^T>es%4VbiSETV`dkTGiLGm0C!h+U+)D-
;_LO(`#w_}IwFL?@2Gj>*}_8kfxS=uOQNCV9T(z&vm5JkQd=W?|c)tCGAPh_qDmc0dmG0Et-
>&W@2bv^qdkR74)+XCJRlQi*~yl&^f^<n&f5&&F#<`Po6J@&QwS(LbnHr~YhYmIr3{!p_(?G$`zoSftwa6RV0ZB8aDLPIjSA(^VH
krhoaphVQx?5W6lXS?TVQeUEcl^=;MdH|}1)b;mBhyKakMURTCXf%V>NukP(xH+LOUj9P_V(c5=d%nFxOkAsC6+tPASm!VUWDLGj
0TS>*t4BZ0^fjlRts&_E?7D>zHvXnOdZ8D;vNO8?U6d$Xjf^U?le%I5x+Of^AyWrVhaU-HSsp9P>tnD5ZyAW5?MZ4&AA`~(zAta2
Fc})!o@rda1wFG0XecqFmX7`>{UYuf<M*~5V#>cL#_+<~iDeEcing%>yceWH&0i%BS^2J-
&HffgrTKM~Po!I1M(qIAJCIvt7sC8F0ZK<vTHtxCyD|<y|7lXE7_c1nJQq0sl-
{dSz+DcSwEn3JG9ZSWN)~OX%x7pR*@t8e3T=?vzH&$z&yy#cI6T17Bw-k68HZg83!1T>a0-
82QjJx5mf8RJ^s|>pjHCr0*O}cKiY<?T<aO+`?-
CZ{N#5Ax1GMd9_B)0o~w4u#6Gf(uApo14>T&SKs*Ys`&3p+hz08^Vu<CQ1q5GUm~qKXn<#+>zLZ(`+}7KY(Fhi-Q8-
oYL)pD^{q1LhL_F-v-NBec{rWf2Kwq%bUNVDR)-5xhjjD#KlbIBX9>@Xph^H&fl1csWH-nu-aAgBT70<{-^7#0&OXiuwl-
$Rq{tN=}NAAU{$E=Sh@hqc|(z6rnKTn0C}XWJh`Q60;12-6cSw%6sT($;RZWpB>uffY-
I=kav07x%x%eV1<7F0$G2keQ?m|z<}C6K)VyPkNZjOaA`kN!)(#*Kc}Jp8RO!AMDgu+_~O`y!cV?{!W&`8W5N*2^e`0sg(2b$Lz%
k}fvx`oP)h*<6ay3h000O8001Fea|GvIT>t<8U;qFB6#xJL0000000000q=5hc003}kVRL0OY++(AUtei%X>?y-
E^v8JO928D0~7!N00;m803lr5-r9vO0000k0000U00000000000001_fsg<I0B~qwb7eDZVPY?Ea&Ky7V{~&bUtei%X>?y-
E^v8JO928D0~7!N00;m803lphz4;7N000180000S00000000000001_f%*Ud0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c~DCM
0u%!j000080000XT)!$s8C3%S0G0^=03iSX00000000000HlG30RRASXkl|@Gi+gEFLP*Na%E&MV{dMBa&K&3aBN|2WiD`eP)h*<
6ay3h000O8001Fe|NQCah6n%vS{ncW9{>OV0000000000q=6d+003}kVRL0OY++(Ab7*05Wn?dCbaZfEV{B<<Zgehic~DCM0u%!j
000080000XTyaqaFS!K(0H_lH02=@R00000000000HlH54FCXeXkl|@Gi+gEFLP*Na%E&MaBN|2Ze?;VaCuNm0Rj{Q6aWAK2mk;8
AzY5jCqiKb0077j000{R0000000000005+c&=UXvaA;w3WixDHVlQ)OVRB_;FLG~nbZKs9E^v8JO928D0~7!N00;m803lqOTh6n@
2mk;L7XSbn00000000000001_fod550B~qwb7eDZVPY?HXkl_?WG`}cZf<3AE^v8JO928D0~7!N00;m803lrRxZel20ssJ%2LJ#W
00000000000001_fo38A0B~qwb7eDZVPY?HXkl_?WG{1cVRUmYaCuNm0Rj{Q6aWAK2mk;8AzV&jiGYCv004#x000{R0000000000
005+cR3!iaaA;w3WixDHVlQ)OVRB_;FLY&YVQyo2E^v8JO928D0~7!N00;m803lq<ZzimD1ONcd3;+Ne00000000000001_fetAE
0B~qwb7eDZVPY?HXkl_?WG{Dba%*gFVPr0Fc~DCM0u%!j000080000XT>06kznu^O0FX5R04x9i00000000000HlGvEdT&;Xkl|@
Gi+gEFK}{iYGq?|b1!f(HeYFOW@U0^ZewL%aBN|8W^ZzBE^v8JO9ci10000C01N<w0{{S|J^%m!00""".replace("\n", ""))
_MODULE = 'phase3lab.projects.p06_inference_platform'


class _BundleImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, raw: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.files = {name: archive.read(name) for name in archive.namelist()}

    def find_spec(self, fullname, path=None, target=None):
        stem = fullname.replace(".", "/")
        is_package = f"{stem}/__init__.py" in self.files
        if not is_package and f"{stem}.py" not in self.files:
            return None
        return importlib.util.spec_from_loader(fullname, self, is_package=is_package)

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        stem = module.__name__.replace(".", "/")
        is_package = f"{stem}/__init__.py" in self.files
        filename = f"{stem}/__init__.py" if is_package else f"{stem}.py"
        module.__file__ = f"{Path(__file__).name}!/" + filename
        if is_package:
            module.__path__ = [module.__file__]
        exec(compile(self.files[filename], module.__file__, "exec"), module.__dict__)


def main() -> None:
    os.chdir(Path(__file__).resolve().parent)
    real_mode = "--real" in sys.argv
    if real_mode:
        sys.argv.remove("--real")
    if real_mode and "--fixture" in sys.argv:
        raise SystemExit("--real and --fixture cannot be used together")
    if not real_mode and "--check-only" not in sys.argv and "--fixture" not in sys.argv:
        sys.argv.insert(1, "--fixture")
    sys.meta_path.insert(0, _BundleImporter(_BUNDLE))
    implementation = __import__(_MODULE, fromlist=["main"])
    implementation.main()


if __name__ == "__main__":
    main()
