#!/usr/bin/env python3
"""Standalone entry for project-01-speculator-benchmark; no external project library is required."""
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
x*ej+%0hFdg_<6h)jP_O9KQH000080000XT(i47ybc5a00|2K02}}S0B~qwb7eDZVPY?HXkl_?WG`iQX=G(?V`VOId8JlMkJ~m7z
WZ0OyhH-D%BDaA)PM{0kVAo@heg|qVGy)5wi#2TN>ban?*8`<U)Ce;wn+A{mWK2AzK_G9D5W2sMGL9{B9w!p5$-
~o6EtT_xN3=kKL)VwLBcag!jDG-NA84Hwx*P>RtKXy!q{POg8{~f=z47&hAQo%-
)fa?CvHzt?DOkKt5pnlmtLr24*gMGD)N&9!}k(Wf%@cJ&l)K}x$O58kv&19O`F^-*0k9{a)-
Pw%nn`04JI{cSglqq90;hk*GQNhuriq5;Bzq;xhB?`igdaKY1c#w>$Ygwp$VK3jb--4zy0og@FRbdU$g?U2|p!y_`zG(D}sMLzev
qnT=P8ZcIbLrTq%~IYl8o4gRY`4=v!J=gvNrnWDz;EMSKq{u`Vvn5xi8vm!08aH@}(z%23w;ZiLEO*U`5~Xlm306BlJ!pWss~j;L
QzCQ1BG3*5sNISbV|mNl|on5h_nsiz#NDs4J0#b4mrZlAdvV9Jghv?0NY9p<UqT?i8gB0&{nbV<J11d|0fHJ7nWV8?|8^1Dy=!5D
1{+UTz5Mxe&GJ+-78tRs6MnF{&s>1Rtb(bx}|nwii$wn)G0Tib1C%@ql^q6zdX-
=VvRDbTV=+iR24l$jnLf#mTT1EupJBPjum8SKzBVC`X$Ue~x5#7vK<W~wg^$yV!g6!*Y|jQjB)aUSC$)_@(PTQ3M>uIr5jO^AJ4`
W=h;%4&2N!6%o|Fm;PKlS_QLlZE+{i%$NhSSFhSn8t#a*8|*MGh8NoDdC{2M+=@YKQ;!-
{MpFs6H}FP<)!fQ5)}3CUeAbp7puSI{U1?I_CJWbrD-
@(uj^t^728lITRS@|H74Dax2$?_{ot6>XHdQ!V}`l)eiD!Kj<c|#GyEan-KwDL%xh#dWj1pO{E$~MvzD_!i|wacn;ici_maFN?;a
l??;@~Z1ea`9lJ#I%tQ0UAJ*c+$92w^A_@^Ras>nNd_#S)g{cO6%LTQ|Ei}f5+nhlCO9DDl#Cpa4iQ?ch3q`+~xI8qg9@QM{Jl3g
w>Mr@kR{y<-8o^v$c8~(xauE!cj|NN&mXFu-KO+jNrdLbp>gRI7BTog2e!@&HAd~vX5XmkQ|I*U7Dt-
rQ6`Odn5e24{Ve>LG<Gwq)gwCJ4WOgzwQK>9+mp!gx-
doqWU>zj(asXw9&MY5GI^fq`ik?p9}ZgwSYHY2Bhb9!xN=K|pq>6Xd&g_h4ioF?uB1os4Px6(ayarbuq-kZQl*4OIyJP19x{F3-
~EbO>Bf{ULr#DC&B{It7=;?_D#AmhRpVu@87E=f*>huz_oe6;s~Ec<qe=d<;%l_)1fF#iBhO9KQH000080000XT>t#(=Y|LX09qR
W03QGV0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-wd~bS`jt?OENA<F*lh_g}#>FH)e@`YugS7*Nn_a&0asa)-;NFNPs#C3?-
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
5rZn|~DaWx#G4sAcZG_xXCR{;v!x52$Q2`1sp8TA)E%>DyVO9KQH000080000XT!M$o2_Xvr0M;P@04@Lk0B~qwb7eDZVPY?Ea&K
y7V{~&ba4<1nb8uy2b!=gDZ*pH^Wo~0=ZDDe2E^v9Z8eNavR`q><#l;e;NAh@Q1BsFmgOs2MilQ`1QeH+Q>(2Pjj<X)y_+BTwU5y
l4BtVT&RPt1iC=Z~Df+8VA8)*7tAe&8}`WHCoe)(R{%w~f`9uoWde1D%i34-8OUEX6eK?Zx|-w&S<Dny-
48^O|uR5YtuO72u_*5p)_HMzQbjZ9fFTP$gP5C=i9voo*DB}tNbBbu5e3CWgKSqnmoq7+nQWx;oL%vrr((V8>!zMy=OXH)ZfkC%m
cu9+fSQGp<a>MeNHEGxif-
^uAT<_ij9#_WEUf@sW2z&Wc$Qj|$kv|1&zatT6Yz$*eSKW#w8B+a<UikV1Qkyd3^2p$pMEJ4ZaJ(kpLR@N!s!ge7<mCW*t6~b`74
P+S?w<TUgkYmo!6cGVVv+_QxlVzE*9M~)wNH*h%k$wx8x+w})8wNM%6rB>0TPRzRW=Q;cU6(cJ)D$Sr7CIb!!VMYa-vk5^bPN20v
OdU5ni>>*PS8>L&d!}%*MC4pMwoDiz#l+OvUC(wDysT}y*{_$)3>1$L=swLB4;Bf1i$(6<D2YI^nb`eTNyoW^j+(q@0T<m1*cCwJ
$d}-
#TO4xKL6v3=f8XP_us#I{`}=HAD=vZ_VVeIS6_W_`lp`(%!@C6ee(DzJh&83KmPgYhkrT!?8DQ~o}Rw{?3*tiojm);%TNCB^`9TT
`sz0)zxe0rUw`%DU!R|R^yupkK0ST@x0B}|o&5Hb|2%wOOHebKTi1=kz?$pMkFNGFT)Y%SB%rm(=5!`@Q&#2W(Gmm2px}3%WhV59
4mbRygM;vbR(w$k9`p=f8MtYZ6;&fRaGrwW@~mK%4&u)!#70Vme`<yN@tt>W-
f%@EOIl=e2wgnfB(7#(HbS#S;fbKrT&e<sgY=?coRfWEi)UbHKs_Qd%J9JEsb!|A(%Fnvf+|ZgNRlI|CqST`XA8#3v=j@gi!_mdq
Qb;3r;uY=vA^2}EHHui$^dIg#cbi*Luo*OJk5cuHr^Js$uuicPFieH5@RwHzPGcpld?IXX_|mI4I=YUmb!Xqt6qFnf4U_<^hp2v<
Yrm0p;TT$$1aI5==Y5}AQ^C=O)f?Oh(LFBf(`Z(0}{)$40>mgb8^vfwNJT)NeoQP4$;0$vN)SVYreh{<d(zP$V+<IudZC|%hU%na
a6I<9F!9+iM@DW>}`uth;3p>xPbZx6^P~XSz1^$Aon=UW<X+kBp9D4d#kvC@`Wu$;w#CrIf2HdKgStQ=2_0do<fqTM>EdW3vW0Nj
wS0AK@5_X5O_$59YS*%l4C`2r43Ni2f$l%f#^;XDO{+&-luuP;5+ITqn11b1W&+>X9btZ5=v-
nEi<tu=TGokSHNWhDK%w;$_hZrDMpeJj6okSh^7f#wXNYm#(sji0Erfw*ccLJT=Sj)&QO^eoo1rJfY~HUn%Z#_epIrzbaagaI~>~
z1<l1RSP8T#U1pUnRbQ2PT+_KQjTR4Th(`|Y3RaR&E1J*At&~=l?QC+|KvTl00)SHks94OQ!$^}y)}Dq_R**0ZoE$Wd(YgV85eb9
M&7(byHYwC|;$fL_2$_A*kwYVAX=r8XE9v3`b_4;~vltL*8mXo7n#jtyMIpy;MdYpc9@sL}XFU`Bu3bSOJqO0hc%d6fy?DV6(`+A
JLmU6CrsLLKlemUp%BnEf4SM8TBR|sIk7wk_#_Df7v(0JQP@I17?(G}FM(Mf%G(o}K!#9=1ihyZI#Dc+`T0!RnH@59`lO$f;dSZ0
Hol_)G-Znu~P1R5f$vmI4TFU`SCQx1>6$@~6&0-
vfv8L9+c+kH>`}4{1rSF=^z?7M1ELRz_p68D9bRl%;$MYu7rEfy;wvD5)Bsl5y2oUE?Z236C>>mWH*9N;mCC3t1Mm<VG;qRhf<#f
gtWuC&gZl=JVo{eRxP%)1(xc=E(M<!m)->hm&)+*>8t*f=}){V^1tCsE<$7{hp^djA@+EB!YPW-
v&lMU5<BdoE|)*3t{=dkZex3_tAi2G{@am<~O?Iv9^UV-MFCS|AX5gG3d2Js*wdwc4i!A14Y<#;fWux*(D;L8{A>y<tH`|@S^JTQ
QIsz$ItPRdg`v&v=`O!U|Q14moJE$QC4zc(Sf=G=%Uk3A>ZAdr(g2P2J-<)iWm6cu)eoHc<&$pl|?18Ya<&Zm`3U5&5i7sy~%z-
$LXvrsG7n?$|{X8!~_?yFV7nHYKws@yK1#{`OQg1rp5%C<Npck7O<FjOXLs2q~IYzpXp_!f~%J-LB#&QN`2-
tUbt0C)`3Xp6XVnClTp@;7r)s@ZBd6IZw(o;Ro<%RvDN9i#f#w`3=~@cQW!7jEnkq~Ax>KA@6oSMOZE@%GK@*d_}111|3G-
ne@Ao!d5rx7~wuq><2O;lNt7FcY+dGhaGzYS{JAyqOm@_rKb?n?OH-
{VNDOia@QshzLDYf57m^QWs4LykXaYcyKNVI!)D`w~}>o&Io2Y_O?Y@l@S$4KxpfD?Q7sqe4cN{d%9W3CY<EpN?A%eH%_4pD$G@k
1V~Yj$fTt}woeG?FO?w*a0Dg05oMs9)qXKit-
#J0Ik0ch;wV&ra=p<j2$!PjM>uqpJI78I;DBV?^<8I3u{#i~q4!~UnjUrU7CJG!aZ+_7e0@?imyURg1&*-
NIy=U&<HG^AGi8*a5)|Ie-G;0;f-NhosL-
t7eXw%wbK1t|o;Zc;490u^H^wTYUV9lEI@XeAaNkX6oAg1EF}S4;?x74MS24G+df1x_t2-
2#iuxX_OQg#VVeH6{h<H#!F*U?wK~?c-mK%MeJ7o~Mvgvp4c-L~!lT0`4GPgI+YIh#1>kSC~v3J2dnaI7>-eEyYpSaCW9<21W3-
o-HXkv$L-LW%puivn3EpKfE%wYN(k@mLHyHpEgA(sTnx5)*p3j<XWLI=p1E`oN~oHccg1rjt_*+Y~M?SO(w-
u`HA_p(tpi%<@Uh^5JLQ?lrR$ogH{5J<GQ^r0afnM^?I#1Ie5O6V7y4GQ)k5#<3Zcw{ar@$MV8VF}V6t@_6(&C1cY>*6uKOk!G94
2KhW=tFA@DL}bNA&do)t~L0_9;Q3r`GQ40+yVH`0O51z^Bg!}<&dtx9Q8lz2``a%ssLsLZXGa*1v@m8JNm|gwBg~y;F7tCPI=&ea
`DT9j$lq^Y@#LGcdvuvX3s`0U96R#{POPUf6e`N`aVDsIz(kQs7FBag2z!uhQ2%oLv$99^V4%Q-9S*Uqpp}h3y)k@-
P(G)DMYq3)z$B|q+rm5c{7_a&SAB+7ysRX$*_dE9M_=kZ*<`{v-
HO1hlpS@4sfbp@}O&;^AUAya|TtrIFM0?!!ArDhoP$ptc$FFrROYx?mmO%Ezd(t;&CU*Cen%WHyCiCECG7-
$n!*76Q@*YevY%`odBNM5-*bpPh9`4gQ*|g@N3O@lM8h-
3#_!axZ=rDxeYloL}c@xwto1Ut<9e3&COfU%uwU+ZC#<qX5E`8!&*C`4K`RGk6UMM+zq#E*zKCApPUuanQl<*_RWEDW?eIssW%tK
8#WNkJJ<jzE0Y5#-
`(Z5t(I?)UJe1bbiPS0o%3Qqm#<hS9%S4(D<cd=Z;0ziw<aFfa`E*`2`AY6%YY@#plA5M`{|$SL)^(D{};qa-
X28eZVG?(g36mD1zqBQw7}UWNswle1m?FBWU%vJP)h*<6ay3h000O8001Fea|GvIT>t<8U;qFB6#xJL0000000000q=5hc003}kV
RL0OY++(AUtei%X>?y-E^v8JO928D0~7!N00;m803lr5-
r9vO0000k0000U00000000000001_fsg<I0B~qwb7eDZVPY?Ea&Ky7V{~&bUtei%X>?y-
E^v8JO928D0~7!N00;m803lphz4;7N000180000S00000000000001_f%*Ud0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c~DCM
0u%!j000080000XT(i47ybc5a00|2K02}}S00000000000HlG30RRASXkl|@Gi+gEFLP*Na%E&MWp-&~Wo~0-
E^v8JO928D0~7!N00;m803lre{ORY02mk<D8vp<w00000000000001_fzJg10B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-
wd~bS`jtP)h*<6ay3h000O8001Fenp@7Z#0UTY4Hp0a8UO$Q0000000000q=AwS003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrP)
h*<6ay3h000O8001Fe^0?mzw*mkFlm`F+82|tP0000000000q=AkX003}kVRL0OY++(Ab7*05Wn?dNbYXOJE^v8JO928D0~7!N00
;m803lq<ZzimD1ONcd3;+Ne00000000000001_fqWVO0B~qwb7eDZVPY?HXkl_?WG{Dba%*gFVPr0Fc~DCM0u%!j000080000XT!
M$o2_Xvr0M;P@04@Lk00000000000HlE{9{>PwXkl|@Gi+gEFK}{iYGq?|b1!f(F<*0VWn*=0VRUbDUt(o$V`yz*a%(Pdc~DCQ1^
@s600{sI0Hp!|0GKKO0000""".replace("\n", ""))
_MODULE = 'phase3lab.projects.p01_speculator_benchmark'


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
