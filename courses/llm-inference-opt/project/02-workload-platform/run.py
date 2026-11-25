#!/usr/bin/env python3
"""Standalone entry for project-02-workload-platform; no external project library is required."""
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
x*ej+%0hFdg_<6h)jP_O9KQH000080000XT>t#(=Y|LX09qRW03QGV0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-
wd~bS`jt?OENA<F*lh_g}#>FH)e@`YugS7*Nn_a&0asa)-;NFNPs#C3?-
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
?0|XQR000O8001Fenp@7Z#0UTY4Hp0a8UO$QaA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCxOzTW=&s6@KquQ8cpDBW8NF3z%q<iLkP
cuww68SrfDvt5xo<nW?yMsj41(uttgyQY3=JGmi)%B3^hvA{Y2K?B?>sU*J1cT{Ati<8dPV;OXi*w>p>aoa*m???I#0gG*UH5ao>
3b2F{V9|mC<zIA-W(yBCyr-tz|V@lMOGVEGOBNWq9u0+Nz=gdq6%lV~_gWzl`H7lyD$pxE&Cl{L4c~e0AgjHoekJ*u7vNWPJvMPC
=&#ewFOU=rPiJMv|SztGS6u~m7Yi`o1P(vnWLd_W@>Z-K%)T(-
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
8AzaIECaiS?007Ml000~S003}kVRL0OY++(Ab7*05Wn?dRZ*psFZ((FEaCxm(OK;;g5Wf3YuslhrtWD4!3S+%!(e9x|v0b1+doTi
lmPRofid0D|wwva^cS!0%zp_5mhalq2e4P1aI5U*eKbYVZvrv&=e*f*$uVkzAlTfTOgvp99t@$$(bGBs~h=x|MeNHKz&1$V0QWSM
(I}Jrac+)Cv(MT%GELYOZX8l>IWZ7vA(&j<k43fW$lEeR&HxN+K9aaiv444ttRJ^p=Bnp}>vm3$JgVtyK3<A4vxqKYXe~|l({K$l
0YXP&_?E4WWLG6D)F7I^*>C7LIKaqi-Ei{W6!Jme|J21B3)q)tS{n-
<j(N~KXws!h%*shSUEv$M1X%>V_>(6^Gizb|rCAszI79^9w9?xh6HS2_>0ZUaNMiJ|*3g@h1tpz<wXzvNsd{;cd{z$+Z_6UVz>qt
-ms|1%2IrYsg{${<j_9;pXh&m<n55#3*g$SAB^dT@5Si-
!@K21R#d3N@$mI?<VlIi|`eX2a7;Kr^7%6ml1^dmT5oR&9BLl`x|>gvTgH$}|_Bx&RZ;|2(pbO#@`RywKaP|w8al1gDsISkn0y$k
XZuwH3@0s4SM9QuTQtRB3$R+@OWWY??#NziPItP#L((D;aw-
ZhQ178Z6k0a>aFOL0j%ThG6vX>MA<twS+MnvuK6`#wAb&5<PD#*w)nz9Y+J2jijD`$LUq7diUt_|E++P7o~}bzoOQ8=hV6p8HRL-
UX^KcTRkWcZSb_vBgWo#H%ZwXV*!57ojQfuMqJr`|7wxR|lGtn;Y-_iL>|n_W$)Tst6Djruzj^U(fmc-1o-
9`I@*t8M%Z{C&zsi<*aQ%R^IBMdP9v}Rk9od#@4bwty65zSd|VcpBj{}Pfsh>q`&52xLANp&?qHeE&cxntp9%N?M!||SNI$m(sag
>HIPnn6!l*9O~7Ewg%G&O2sWdoV9mN>-lYZcf_!R*8953g9a_gJ{fn_&GP2!(hOwOuzEa;*J}C){W74B5-
lYG<BV)ltVPhuT7uQhHlWgXG9$W?KG`|4WkCUt5g6?@h4|X_<$a`{k9q^IeknUC)Zuv7D-
7+N;Z@9hghRCM$OM}Cg@W{^KM^ozh5MrY<{)Z9^8%=Vy?`On-oAblsu!=>8gAfmHvT4sL_kNgWey1r+$pjW^jpgZP+FgD-
4Zb6ov1TKvFGNgZ)ysLBJR$FwZ{~<bsu%DKb|bejE<J4Cg072FbrLs{B%M|VQ*NN@MBfXhxBKQMQTYKj-
0<~DyCCn#9WE%2#CK6tlRaQU5y9ci&-xdQ+o1d*=EKh_XJrIHn|O`Mrs4+Ik#ch(^l2R`m3I7?!x1paR&-
>in1Z8j**FUL#BlIo(ARi<l_aBU^MSpT+<2}s@@;y&sRgi*t1Y*iGfR4Yzj1raXQjl)9hA6x>csU0*J?qVWmI^no6RjMPCWJ?ZcI
5rZn|~DaWx#G4sAcZG_xXCR{;v!x52$Q2`1sp8TA)E%>DyVO9KQH000080000XTpap{A5IMb0O2G604o3h0B~qwb7eDZVPY?Ea&K
y7V{~&ba4<4ocW-iQY;R#?UvO+;bY^dIZ7y(mwHn)!+{E>LzM`WSOQ6xN7l(&QCRGNUKw``m>x748O4TFv?8vK;gj!nf)@G_qk^;
K|BoD4KAtVJMR4P!IB$W_z^T&kUHT%Rb<ebypYH9X@ae^N_Qupc8=YG>Vj<Z_kS432?<rVgyYd6_cRHDo`L?-
fDvLu^`Qe=@}SMzc+&3Vj9QKWo_!GF~xFK2<{IKAGa%x5eNCv{bqA`DqFEAp~pJj?QmS4p19UeBzR8wD?=Fz;h7#iQrUTa;%}UBZ
=BppZ$kGv#ucCS&t@Mdq1#u9BHhBt&_d0yB7_p&=F%UZ+)@M3sUmc!h|}{wlm`1`4=CJd*NpAg8<(aWJi_B8<`m$Z1%rt7$kDJQk
(&S)9ly-x6gw%VUwkg4nJ~9#vrl4?dfTs!SpoimfC@Df%G27iuA^kjOv&(z4DnQJVWM^6^?BBA>060)!JM$lQgp%u7I4XGq-
%cqB-^kpgH72-
pc_J)7}z=Y%7TlJ%+Q;Qgse%zTEcM0DzF3+VOMRxdoxhK547$KW3z3zK;06w0dl%PW0@v~Ntt@d>m_s#FYH_V?9iZ#>ztzNZ@Nd(
IH{7`#q_gH5*D#kP_2bm$zsa%2Dc-@d$i_u$q?hqwND`0}d<H}A4%1qaHLY~zb-FP;bFRT9C|T2<B&npg}kPlJghphTXsy*sb5$8
!)soyBbLlbiSc{^|a|-
`)HC&4Yiv_|<2x?0@{x{`HskufKor)}4E|Z{2(UL%0$CXKNRq`Qq9yG&!Z<X`}X`>um8fi9rW3`|;W{mo75265;sF*-
WyyFF}6EB#FR$L{y`O*+$8WDFVoP9Pu<|sQxmRxWvmc0fb9nePGPdlpFxmJu9T+nfqU;6JRY&vZAgeQ1GMGpZ3Q*+5{3r78iMvRf
ubnY>7S+VLhBE#J!mn$|TuFQ5p1kU1_w1DAjRo>v#?%!M2h-
Ri58wB26;EH;8c!&t%36InAqvbRI>bsJN0F9zqhq{j)d)pF^W>$$)`O&{-
raAXbQSOT=_vqgzcXLNq!+h)8RAi7SJkuprrtZwf|y7pXvUQC>(ok>~Y#D4cNZ@h2}leI9Iomne3sokBPR=Hz2EWo-iJ10bC$5fb
)x9iGXnqNGOy4`hN>I&-
2Yn<#7PKxFl742R}(jnn8A_SOx??&*<+<gtnsJY8+m@k5?U;rHgfUJoK81E>%pay<hfNS6Y0IcQ>Za9(e%(uT+SKVX;gObqA>1s$
|exK6+Ecc4qh-
k}3x=Sw;!EU$zHB%p}mc&DL5+wMzH0a^`;WjKMOl|_CwSoSnG(Uey%CX@jK(L(&isH~si_E}Mx4Za;#`KHL^0CF54Llr~d(%TPVk
dp-
%uLv>5a5#qvg#Db@2gT!$&#Z$Cz*gkKK8dTU!I0MRu#dP$N_3#F3X{sPg@PrM&YNVAJQY4jEkZM(MYTho3I^y9kDyrkCBKpqY#Md
FzU!2EN_JGs#!&ELSkh1P5uRzpfry$H*n!{=w!_Ky2W)vx*8`yo;%QT>IBb!*?kqq%BcOa?jSfK!D=|h6DWU~%^CXPGOCc$^o`I-
pAZ(n+J3b2ukIksAv--^1W#Dt-?4lV2C3;xlo>@BM&6l>$E}?-
eq3fr@#3oIoPgg>)7_OXK_L<J`!*;rNJx}L2l}l$5u6K{2l=TfK9(#zLU0z;R2@h%lIMFT<T;#(;fhxw>aL87cmzBbyuu`EM13&3
nTPbQ!JyEE`gK&9_8Zz>6^3CQ=BZWmvIc$~~{#?7{vvVH6P{IhIAXxeCqX4DLu0SogDCHooA=9|pfS~5dBvyS~MoBVM@r6k!AHq$
sBZrsET6h860R(~sgQ?h#6R^+9#oJVLKJhw~(bt^?otDT?Dl&ri=2~oEw3(KkPr}zxqBP~eNueSEs~<GQ54kZq@Svp*WqVD$@s0c
8(Li~senEH2#MQ>7z%*&y*liNemlQ=h4r;=8l?v5$>-aLViIlusZQ-iUY+%upJan!^zi)Vj6r$O;x$yz{?|S~Qm95Y^LK#iPjAO8
Azam{3pAp#D6mg-
=VCbk3#wD~Dd^g8h33op4Xh8eZ|4Rv0F3yqgKU{cMnwmh}1ER$+us%{QUhdfN2U@8y7m&|jjFHMd8vvWN0g9l54FO57mCY?M#t7I
XFpqs_Xe)|t{+~lhM6o!LNhYa|a$C6d8IQ7&cMPmW<ujLZBjsC<U{8P>=XvT`#@n(9cu_#T>1u_Bvqa9YX4RaDZ7lYfiYut<Cj>g
XZg74gcJ$L_urPXTU327$BqK+lRPeRV1kGtoyc;wR;9VV)aSS5ZF^`SY=_>PqJWg3MS(&k0wKRV|gI46==7;P&^iKP~dGFxH-Ggg
?`SO>aAHMV2;qU%R?Fc*R%wzV<2k+c_`!<}k$CNo=O{(cJEqQQx3UMV~1+8D8h9xgu^e`;zFlnxMj6*>V+g4fQ60Bw_kPEDoT-
*h>EFb~R#xaL9oIv4u)R%F6{p{!)__4aFze^{VM{~4w0d+K%F~Zft^mHy)z@cugP{iabaE^heYZp$khI}O#xsz4!lE_e@gLBUQZ?
8jZxOeBz2Y+~5Nf?^NgV$dJ$?m`Ok9+Sy@A$^^nZq7t&huHn--qYm3Up!0If2FFFKi+W^pmHjo<*X*N$4|2wb$r24Xy!iuml2GM>
s!)=&tV}rjGyNNnP7CM~xyp^3FEbEvMDgb^Ucgkq?8fv`(My#@ac_hj|7qb7=b1fw`=4WYaf3kS9+PC`iE?x0<MbRE^I5^;`Qdf3
pAkKi>P`=E03?hi_iH_r|aG?%X(h`{OS^eDUDb+l?VTSe`StYh6nkD_KLHIES}xAO7iexMeYJK(Ki0V<2Gf(|7mo{8|yC=tN+Hck
Z<Co@lJ?TfYJECVd@aU?kj@nW!sT3ys*(j=T4FBEQy>0y*7sj5VO?SerTVqQ;7BpZ7p^l+2WO;_T8T8PQ6JGYrqPXq4A+IRI~+Bq
>zTHXN5cfez!yOwpaRhd%0>I2Wq96Wb8DK>)NoH#*=~fe>{MCWUakQwgcNwHfqA7#nGOsemdJ2~)tbo=lQ$sEe*r%LF}&6A*;zeb
kXFh1hTwI_C9;30rt#UFG=tchGhWJvixtD{0kbif8N#Dp&nZXkszgMF!^IQzL4BSN#U#N6+b&1eo`NSg7`7-b`sm-
&&)v1qE1+^DnEVp_a_I&^*{ntej5j)JPQF{!ASpd(iC}0+A0qdH&K97cV@!M%{z$Q3kd*>kRRzl{GKE4cG%ySG5LuG}=&)oe?HZH
kudXhicv`LKJk{6ZLE<yl;=xQUiVrYgBHN0&zUrc%=bM<ifB-dF0P9l^R#9p|LJ-5HDKOS;U4;XfPW`BvRr24(a4>WL#<&oQy-
crk%|0+~@QKYCk{?0Gf-
VCf$Y$>H^2D?yh4^*f^(M(KB$ffzPP7g{f8yp#=l18eI@%YY70L0RYbl@uxN2xWDNPPCn*s%GVv4<`7M#G@~k7Y%+;i=w3Qv-
ya?!tvidrW7_oeMBU}(hHOn-FF}ti3m%CD14Fqq#j~+7uN7#hcwG?n#L>6(ca^DFVQV>CZ#OvCac2~SA$IFwXv2n*AV5BXRz)*^v
M23}%A{60dyP-3&9ieV`e++cBe68<hAlJZZ-N)<7B45@Fb3|EjOGLwPsj__8zxjuiED^npPy51L1;qZ*>4A-`jDk(4s$ylO7B-
Gz$+p~=m1>-vk3L(XTLtv;^zUZ6Ceihs7iMj4to22MAOG4q;%W3{jl{3PF-lWypDa?z|awf0iNr;ETNI#0B}js#l^`&V^rWEN>qk
N4Ss5@Y6xwW3!;n=&gc}P))}9jQC*M5>CKxm6u;eI{OW#E?FtwAvTn3f$FN-kItldHNN0B%o(PO;q)cPEuj+`7?b6TOOuhAYC*4s
BkULgAiywbo#fo`Fc5tN9HJ*k+>(t6hT_a$h>5f_DqfQ1}lvOu0`?i&jc7_DoT2KS<kiN92P5Z7$;**Lp-
2cYd21MpU+C+uk<YH9Qoo=Tq)KajTQK#2UVMD=eG%^z)wX8oUfeEQV#CGQmY8CdVVa300(D(wBk8Ib+=Cq22&6hs&&xBc1*eHaa-
vw%t2viXD%vHgvm08*jdIE+zio^nfrg=X7s2=Pif!%Na?z+OWn7odn933U6DIk#^<XkglHb&m*q;+QVR;CO2-
mW(v6R|YK_Qn~oPV~e4bV5l=-
BCAGc3PAp^(q>HR%mmg)jya|)}eB796Hd$F%aY`NGkre_KjJ=mU(RLnos;T_t`!BRa|{chLmXHYG@)Y)yWXa4Qk4KozSk6sj=RW>
`TOS5(hLVSeTj0=;L6*G6YsThfc6-
b5zT*X@EK8fQ9eL`p;Qh{JRpr`(@gvwCtOr3BUJ33^z3jMf)&BoMGrFWa@(6e*sWS0Rj{Q6aWAK2mk;8AzX6==UrU@003YB000#L
0000000000005+c00000aA;w3WixDHVlQ7`X>MtBUtcb8c~DCM0u%!j000080000XT-
@H;g)RU904@Lk03HAU00000000000HlGC0001RXkl|@Gi+gEFK}{iYGq?|b1z?CX>MtBUtcb8c~DCM0u%!j000080000XTv)yN3{
wCA09^n802}}S00000000000HlHX0001RXkl|@Gi+gEFLP*Na%E&MUtei%X>?y-
E^v8JO928D0~7!N00;m803lre{ORY02mk<D8vp<w00000000000001_frkMA0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-
wd~bS`jtP)h*<6ay3h000O8001Fenp@7Z#0UTY4Hp0a8UO$Q0000000000q=8Bb003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrP)
h*<6ay3h000O8001Fe^0?mzw*mkFlm`F+82|tP0000000000q=7~g003}kVRL0OY++(Ab7*05Wn?dNbYXOJE^v8JO928D0~7!N00
;m803lq<ZzimD1ONcd3;+Ne00000000000001_fixBX0B~qwb7eDZVPY?HXkl_?WG{Dba%*gFVPr0Fc~DCM0u%!j000080000XTp
ap{A5IMb0O2G604o3h00000000000HlHA8UO%rXkl|@Gi+gEFK}{iYGq?|b1!f(GGBLZa%*gFVPs!$Y+-
a}Z*pxeaCuNm1qJ{B000O82mn|D004R@00000""".replace("\n", ""))
_MODULE = 'phase3lab.projects.p02_workload_platform'


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
