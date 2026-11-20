#!/usr/bin/env python3
"""Standalone entry for lesson-17-prefix-affinity; no external project library is required."""
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
+MBNYl>MtEy4YZ<0HnrkK#JLzRw*Ide@q&zg@PoJ;P)h>@6aWAK2mk;8AzX2?(BL=#0021v0012T003}kVRL0OY++(AY-MwEZ*Fr
hUtei%X>?y-
E^v8MQc?=Z$Sf+URLDs!F3!)>EiOn+&P>ZpR!FTVNG;0DP0cG&$jmLsNd>VIOEUBGiuII~l(+y;O9KQH000080000XTv)yN3{wCA
09^n802}}S0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c@4_J5rZ%c1i(L4+^7H=po~<Y!AB6-
7GsIfe)#UJh<tV(ENIlY2OE3h8rCfB$5>Dq;T_t`%YJZ8JU-
5?`V*+{f!`Tch}<o3>3ZsyvxrQ8P)h>@6aWAK2mk;8Azc6b>F0(B003GW0018V003}kVRL0OY++(Ab7*05Wn?dCbaZfEV{B<<Zge
hidF@%<kK?uxfA?R(GA~k~)%q??P#93qYjSNaC~}9(rZ0veXeD~hoGd9MwY!e%|GhIq(xRlj{YYNB50=Ck4u`+_;0%{@{=O5<n|B
vwyYC7kuWP}6xVrklI@Mka&F-
YxF(rQMg*F$pxD_=Mx3UsVDN@e)VzE{2p5^(rH@y;h&g8ypm0?BGv<Bq0jb1F=SlKpZuasy^YT31?><YcB<+cC(Rkw|QH*zohd#`
HXN`+Fbnv8XY(o;UCwpFnzOi|W_*03qZb{<Mtp(|NBPIKsFbK{xbG>3$JSJZU@&?M}g5enbj##7ZdjZmKXgA%aGO5(oXqLv`Jlld
ocSS%KQKd-l-U-r@J_Yvl(YPDeS=Ty#RwPM;R8WT;`wX!k8$iA&aJ$z~ay4QILqbmlCG}wMxvFo<2>7y<TSnQDR^@?rlwy-
Q<;(cdw(|!_-
rkU)&?5DO7RzPpM{<Bmg?oF<D#p|!XAw@zO*=IJo7p6c2Rt%wD12sW#Hw&UxVoPR^w5Yc+yZCm(W#O?9f$KERVwN4i#raLE_C+m!
7x{IeMGjsN-4=B(NEMO^Pb&x+SjLE)Dj1es#4mYFM2Vsd@dV2j5~lnICy-
?$?(M>U`S@>ElEbrW!31D>aFWO?D_AJ>(iA@ECBhZXOIqGkmpic+q=0PLk?)M@c*5wZ`H8iPXpXxPrf$newA^ypz%FIQLUmW{NLx
Sg>GHi6swqGLsc9WFAFk=h9r*1Xcxy<07DlBKkTi@eYR&e&#$*7C*m&CkXw9uuZL<fKgajj|sEcg2ty9t&9zk;k_t8R*1OByZZP+
A;w|nb~12}v&^*ZO7U>bZR?8}5Q4LH4v5TJasOxR8ol~6jI4nLFW<XfiiYO$8Mf$>s_73f^}x~&dwnuVRzLp*6n)PNxFC$0K@rz1
y?Q;1)P?}+zid+|4i$X=)$a<3zQQ<kDLe8qUtb+s%h^<JVNe)1-
!r5`k$6}0BxwGAW+b8&U(1mA$*xil}#12d74_8kPdh#c8l?zbTZoY7L3{UR7nC>3X@U&5>%Gy6CjAhY6QpYW8Sjib%dPN*$pzaDf
~k>xPzFla_+*kpD1Y~kRG;QMU(%spdBE}*mS;P47SvL1d1t9lwpD=N35|Fg+BWU?bRGv1?>M(0?Hr!7Sbt_locIN@S2G+pPs2GY<
itnj+%AVwj{10{L@8Ft~3i`kd#)pEI<V?}8J=93Ge=jjO4NGmb&zBt@X^h+a=`aSWuV~^(l`1AXpg3<Va9b&@x2>OAxK4BdJo)g4
SMULvC9!0T;DwCt#{we0MO&}mLOc0iw*sUZ1EG}!@2sqW?_=<)k@lf=?UQWZBSi@L;+OM56^MAd);)5@T;fk7Ec6A{kQ2+1UpZD&
Gapz8%*t$b!TnWIl6g*Cz8wS=fDyhr%R;ZlnD;@bN;%O(TrKW_x8C4e#)Fb{S4hpw~*~FI<tig%qyaplyr=2cuUtL<w_{^w-
Zxy}S<?bVj&&Rt1^)IOMavFfMvNf8o=?nmVISN955?P*%AqtT+VxK~oMO;>pEZ7#zk7HQT;9e~ab3W{3y@^r5@tjRqh*{x(PU)t#
V%WRy^|+p}oX!OxUX?6$?t7dU_`pN;>PsB~lR+|0<mYU4-
ksBN?gW3@*iQ1}rmkfp$kO;irll7!EvlJns22?JL}XVY7L85j_>ofZX-
r!Y|H7LZYfhA^TMW$TXgN_<#E(2)FE{QBUq`E2ecVc(=`=F&@eBb6$RX>_u^c#pZi=tGWd`!lN&!_tPN|~7UJ3ha9Ezg;2>4uoo7
#bhfN}+09H%>RU&$LhGe(n(J)Ar_0RtlFxn6y>+=R-
&mTh7Kjv5j^f#IZ_oKItCUkfz%)SHJsGI7nIClvR2BkscHk9>d9o<0x^uU<pZ4BJ!1Qx*5~E9(dP<mU#~=c@lK^a+9i0HkMtE&#5
J8$y45<f^UFAvks=*pQXBR)!%9-6=E-
0%*ZQxg#_KE=YNBG!=Li0&GifHW$Sf#WT0tiZ8H<8nyvG>BHW}XTTE`yJvi`a(`hh^3;L$;r-
9k6Rq48=5laROlxkZj~sGi&4<##1?S7^-
^Y_?kVZy+7!9$IkUP3?O3ons6M9`3wK>9RMhU_NK=@0yZ>7npgozM7U_0`$=geH`H0&Hx3YARY6{R~dNX(g|M_&e(;Q*!)D54>m9
#4x$H#>pD?>q}Y7_s=iKO<yDBtj{h#M<N<E1RZWd!v<IseU4DNXOY6=n?1WwkreOBHI6&j|kjWBSf+&jmh!oVuZSNvfx<L@aimFY
Vh;VE;na+){?<}T=oY}oAb3@HW%$L?y@KS5wfE13&11zD)2Qd>P~~)Q3Lsw9<bwCkMM`%`DGEid|9wU`Z9+OQ*arlIi1jXep<034
4nA$;?`YY^-Vt9ibub;*Ki*CE9SMobzZMG$#^T9O)}i3mj^nahel+~YS9GIIT8U%e9%&(+fL6gyJ%h80*%_t`3-
)0wZr!9L)+GG??u@gNME?wyH<U|OdV)Rjb{gp!xByiR+C6bb$`8=q?~OU-~~%OuiIv(n-
u^Zr0#2QXqsflaGn#tacGZ^#c|C(G;h9U<ZpnzRq}Vb{Gy`qAEHnKlBK)Thcc7<B5Rg-
rzOYu{<++>vZRd<A>zhtLSBzLAV-?nhTH47tyE-L#|9O$s|&Qt`NUvXaf73@?@Ae9bX1>;Y=v|76RBkb5r=(|qY-fNOfN@W1SeCV
0*;J(Fya|6U|S)&xTlnd|7$vzv*V-kaj5-`)&Mlk<hDwQLmh*ASATibX#BTUp-
U+<mm{!6LGx=mj%NE<ufAS_0saS2O9KQH000080000XT#m~pLSY2}0LTvj02=@R0B~qwb7eDZVPY?HXkl_?WG`}Wb#!TNXD)Dgja
N}`+cpq>*RLS-B&CYyWJ|CabFn>iF9Y__40|yQftIM4EhTy))x^#G-*-
Hcq9{9Uinf;Sj>o(2?mkj!nm%Z%Su+UI%R%$*ksNy7a?QUmMFz!cvOA)R^+eE}BDAXs?=*YtVO<T@@)N7HTBK>3Buy_{QkKo2hn|
%s;q5{88rF0Yw&Ai<N#bOCs`i5K?2?*lS_!HYZ0gsjnpe6As)96}iP|pE$AgL0+5X-glO*|VG)?e-
@}a8_5@N*^R|$bX9c|f)DBa`R(2MZW%9;rU?@Vt%wnbq@547U?xH37DHMv3Qo>8IqAlykQK>Bw-FjVla5&Utlz4;QQ?5U-
tfEc>!Shlc5BP2y{3v19&E&wnUFH=KRF#|~~rZqi4H71dQ3Zcnr*3d!dvZ0lh{c#Njd4h{TLp~|lWr~R=C)e+ZLD#G<40>COj`{P
2ih+Sgi@&vxm7CN;m70we;LmC_TUha#wGa5r-Yde2o<ZYub|F;Mmhqvbz5a+TXv2h7dtd^(&h%!(sNy>=phyLDBWw6Gp-
sa(6zDzcNGJQ23jP(^RX|@8K)<&A>Y*u1V_%jSS3#I-9Kcv`r8iL{Z3}W$j9ZjX%og0&bh-
HP4%FhXr&HnWT^=yz4aB4;+l(3nfpW#jKL&#jeJ}egb@SITR;#co&F2o6<k$5)G9$YA-UjnE?Vtc$27mPv0|dXaUgG4-
j$Pc=Cj7R&(9-
X~JCZF6a<iSd#pW2(1o+11*km5{S?)7)+<0w6ja9a9O8L}5k4;9yP1nmQHm_O5m0>g2AMq@i6`O5nu4*r(Vy?BIb$a&iz?3d|jpS
2U=5fz1lF#gj0&tb4g`fGUh&@+gs98Osf&a)~P#@5n9~|-v42Xo})*5L2qwI~NEL5R_dUK#uW-
73Wit6h@8dx>HKq=$OMQfl}ykg<_6FX`Y8fwON0zYF^#sc9%sW-Jm6EFAF3%xkXJbRCUZ0D^TlDyQmABRr!)-
`UEcG5HdcrG9U7|!|ye@>G=#&$BCH*c}UBOo0rottRFD}me?)-
V}enLbjL>{;fMTgAo2a_iwB*ak_bAnwO>Mx2|WzsXPq<bEJ6ea_C%gXzp;2lgnN`j{PY&XxJcHEYk*1~sEFRShM`VJCL|OT3vMX^
-Q4=m9#1^Lo}x2;<Tnv7<XXN##y<gF<G$xidbT9DB+?Pg~BPRhPZGb1Oq=-
yz+Ts}ZN`ki>NyfGH2%307*(vcL;PoJl@^Po{JP=O9jU%eyRKSrF)?HMUHCW*tiY&R=QVOibt}O7N_OH^FjiOJhBo_+BB)1w9-
fkL)G#oQAa1)r1?1*b0XW4DffR3!#8Pc$rx_;K9T_&GbHnbQNbaGxOAB%<NspOY)iJSd0?OpkT#IRL7OMSOXyOVCS19TruwRGja{
ZJ%yc4XO|}*{Nw<VE%1V7v)j##LGWxkyQLOHezx~qWEjIrlXK*ZLe@C<%i@CSdP*a&632RaR$ooxfw9VNz)4W&pnuKJw5K6~i>KF
OykN&;Fh8yQ?c6ZTGIkZY^Jl~4djR!77_S5{dVbsf@7Lt^P5b{rVb4&1xIcd`t=6@`_!(5h-
!k8*F}Us6v(AvvBLbgY*C2G{eB@w&%rO|=Ns<fs5w2!ih6DIdcC?4DrM+*Y?4G6@_{_e8z4@+65<Flpaj}Cb3=O;@OgJ9adCece*
hFDJY8PrxZ}0Bm%J32#omS)YpHjf90w&Ayd|?;6i<g^W3=qC^%iR&iJ+mg8)z3f->5f09IUKOr?bX%&Pj;;S2T)4`1QY-
O00;m803lqOTh6n@2mk;L7XSbn0001RXkl|@Gi+gEFLP*Na%E&Ma&>NQWpXZXd8JreZzM+*e(zsVG_uqqW_q;?m}ruTu(FP@V((g
66SNqsRqn2tskm>csvdi=Mv4$pB!a{<j|d?mUU)zv7x*{q=JLc};5$`aGd;88aU%TS>FPSSI+yR9>hFK=L8H}!OIbb;<&4#HGp))
W24NV!b$rCqsx*qHhVe3EO4OAy>{>}96w_0#M8+=X%uEH#`K6A7;A|>2E2^x?1)G8=7n;?1Q$YNLRb@Vp*^yzgG@>-
JDtVsItqv|r&B}_2n_4JYU^jpi!7{09ZqlhxLndZI%^4)>s<ighs(N3*Hr>>9E}=;p&8q7XhVtA}jOC4KlnAaXbv4eb>zK|J1Y=b
dEJ?-<Z6*nmg*_NA%gS)FO9z2}rzSO5TKM&p>uD}8{qlX-;-
4$+pX!{Oait2sR<Na7uJn9KXmC_#O~wsRbFMWVqgAalnVSA;%TdA~WPztT#nNq<c}-q!-
yf9oK6?ue=9jq$g1|~(r%J%xnWRG=DpjfI-KHcf?4mae82;d+GlW!$4;rBjVq6HW8wxh*W~ucPQ%#9L+Tf>+QV1DC0!dYs6u#IxI
{4|*_y{)sT9l(R)reke%`v}xR*TeWg`tVehD;k}*G8ILtd^6C=c^S(I1w|Mi82L|Y3f{@W3$iVIKF5}K4>J2PGng(MsFvo8gut1P
g7AFzEwjI9Aw#nnlyA+%|=UCpP&1biT(B|t<*)IJ*i4@5&WV}#_dc`cp;GUsQ^92-|0j&FGy)7#_W=7kyv6CX>y<UV~-
8qWOrzHK6YGCd<RvO37slgQ+kX@c5I{2>oCVW%M#vlMd4t8;!LjwRNG-6F0-
tmHWez%Al7&}6?r`hXFQk424OR1Rp%>+xt4&Q#wJ#26WN426}QE`TdTMcDwSF|HC4{?Y9dpsi)8{hR>)FngIBFM{W>cNX<D>H(sR
8mfZYbUWP)l$i8r|!g%F2d{lLkJ2`zSu&;m;ORLWumlw67W$xb#(i9w_CjxTs!i!$pNbAI7{0&4^}3<$*v>_}ubdkX4<qd{5~sBw
vuL@{S|1sn8ki+vG(XZ6=p;n1VS8TRvcj~TiLXA@+}HJ`IfB!d@^_@OSC1v<`V$HynAgY=4Y>@<(MNZv7{((wdgFK1DB^7QfHadP
w+yCH8(7546zq<4vWa&U6^jHHD<e^yvsa6}a{Ipq=r&j?US7K8tJ#%pS(N00AuGkRT7ujSU)fB*FBzyA4~kABDAc@IE>GW_qqfB*
9He}46^Kfe6vix;1L_~Ns_z5MhqUw!iNm;d<W%isRt#TOrc^QX`M^WkrHD{7;mw`SpMyOE$OT_;HATe%<Y_AkE~l;V0|Dnxa=`u!
jET4+b5maU)`6@eN_n#*-WL_T)30Oq@(-FIEY&jv&0fw}LoV9TDxSi<oQK-
~moXXu*t$ZfYfYC>J3^@aT*N*%dv50(ifP*u7u`qvBWz8qT#u?63Rz}MMhZBlSrL|7ANO;PLUcDZG{yT**u=y1qF550+17xvfb(3
wEwrVw|g4FXIWxuB!jnF+LO{*05v4T4Fs;#>5AD+Hwp*Qu1Fw|TBbA9DnXoD!tBq;xTMr*-
pFOyFppV4obRt{Me&7_rc|gQaiU7YtP^Sh$36$7Z<2_K_XIV)_^P+#;wRZuDLduDlp(xV_*Bx`cKIf7B1QxVLR&VRzG-
i%s{?*>U3!?NHlwtIoFV!+zH;I-8XHme)N*T@h^Qu)aTaZ{1pYm2d<0#-s_k0xyd?+CtqK@IbziSMKV7_kR41-5c+xXfuC2-
5N{#&?R1UELc_(`GSu{r@U-=bVz-6Z%yKbn=w_VZd|iQq&KVIN#34UYboDW=t>}^(z(wFN}{l)5x-
5sE{#)eY22fw5H~b|zB;wjOoF}PZdDzwWXxs0O|KwvmL9ntLFUT*F-=C(#8JAsa}!R#<z6M!N-
U>Y>)9OFhT`x>n&?r_^=wG)p6Jm2NV>><i<8`M{5ZU&c3}?y;3+XgC&>aSiWiIU|36ajUAbLTx)a8S?A3vPqqX>S^9`B3!5$7b9Q
_{88+Uc<wr)&y7^f};t1FG@&qUktmrY~Ur|%cqCB8>4I(UK(p12Nvzv%UjzfHRH;=14I4r(ug{X4LF8HFK3QF624SD!pis)IgCp>
^=<w1wUp+cmCiiMEyHvQt$}nRV&ez#GtK`;Hk)jEW$p+qykL_dT_Lx-
u76nN*QmXnRpcx4gmaB&n|2dvk}$euhbmxLND<J`s0zS@r`K{;CX#Dy=fKs8QIM@!&N-8Ey^`-
%4ngcN{vF(XBIfv5e&w%)YZ0*26mVgAsBZo}7Wf;VtsHp10i_fx+Nl>z{~jaSxHnm6+QZAJ=)UU3Svi(b5xvGB7*~U00xs5qRv^4
Z8M6PHAtI&B%BV#DIK^dp#mtQ|$Qtc8p7krVD2jCaunnsMVp)!DHd>4U8%1TOxZi?2fyRs`X=guE;tHJ{oo@J2#W3r-
x4tj*^4ZqvV~#=XBV^lhd>3%XrueO5#MjbK2UnVsoS(`Tt@~_&L%JvzSq`hIaB5y&xZ0_E^_Ba6jyawqtgQ{RfQp%M3uVL9RI6L#
NHvFWt$DrWi6i{bP_3`O2y_gv>?hqXWG0d>g3q>PIiM3oCWuZNatEKo|!C-
L_H|t;1gjO)4Z^+ipARRw>;MU7hb&Kp;WzW6j?JM$35Be2$lyYhX^mVt7l;^wToN`(vzJOlv6WE!NVa{URCbDS!0i{iqcg+tMcVi
l^cxlM~=t)H@$O-1kvf$GbN4TWoCASb)RJu?4ws@A+V_80=+ddp{fQoecM${gQ5ML^CNYg%#La`Ur54sHy@q$h?zcgokTtEI<-
X4~<V(`3y&B@ll^Y^0w1J5W#fKCt_P>I239L=sK5+k)C4=HW_Ay7SK0Gm506He^5&U1QY-
O00;m803lpNv%8FH2LJ%65&!@w0001RXkl|@Gi+gEFKlIVb8l{QFKjV4UvP3|W@&g|VP<A&ZfSIRE^v9BSX+x6MHGIYUs0Bz-
P+T;6O$-|EyS>>5aW^!zN|}A+g-C$rl-
5Ds@@CZz$!=(HX3gr2EhkGP$cMsHx}|=G~>EY`3s)9^<{RGtma`e({;{w?%$~%jPVsJM3JMx^XSk0&r!+gi0$^tXvA_R_Yf~C$?`
2k@)RW`8B;{JSxWPSh8W{sZ^VlUisMlwD^BAWu}N8Q3F3JniDX4CdOi1yZ<T}#>b`So)ypvv^tp^|hGI-OO~bL2Wt?P;=F$Ns#iY
!r0t`^fL{e;19#4vtW+FgaRK}9-
$^cEM<SY@fbMheuTvQf(B~QzO<#G*NrU6=;5H7EQ2;~pcukxI7r+$TOu9Y+i&?=`%k*7?#xx#tD0|@e+ia}<QqRPQPP*j2SdTXmI
mr>+Yy&i&pU?65`gfm@{{^0rkLN#!p<s_3Cjqs{IM3+@n9vpr(|M1q);r{(Uex84NaJ>KFKfm6+|Jz4Lho8-
V{POREn}2_E(`s)OB#ZFz&0F(tZ_Pjc<aqzRqdULNZyy|ganC?JI6OH1{@|ax?*YWo=RX-lcsT$4m;3j=2Dtg{kB)x0i`w>)F#!N
@IKTJ9(FfoCwg0}g$SKL{ibNhZQK1`j52Z9=LUjoa5Z)xo4O;h^DJ9BSPW7qEBo(S{l7goK`wm<uIE`6eR#E^wktm}CB;`(lwy#`
y9Z_3fjRT!Dfqoa1Z_^a%7IIina);siUviRAt=4u5bR<E>qB_i=Z}Nmufi_`eXbFv~dcfh5B%!4wCVD|8RL9Qggs@y7aHhy98bg-
kSgU6&Aqv)ZGZ;#;Dy0hp*h-4fInI<ah(K%^O(aCu1P-
3~y<RV+BSg|PhFPp8FkZsbBgu#LbcUDg(W*Z1QU4`$75p3ONQ`vYhVXFT^{I-
S=#0p{l15B*JXj=ECZqHI82}O(uhZ2p49+?Kbrxcin^?DpSMh9!gf!k}OvrWkvSC~nFw_;0gdvC+hR)H2H^NiU3^@q1(tCR8X@9n
4bB>L>Y-IJ(6A?PMylfzK-w`J0$%(g^H4an+m@$W1yn6lmDw-
O!nT6NhgGcM?0~!@vKY@B{Z$kl{AWek6as@b53xt5erPyI|?BOS|ui2TyV@h~3_PCv}cXg&9ok~YhQTW;`SKqj{a{1EQiofCFbD-
kC$3}O{LO=j{VfV(;DWmJ#F;!_WkJg8S<>d`qP0&)S!-H-
RtuDL@QzA;3Jzdh2CDOQ8ceKh{hqpb<m(@t9<uP1Z(qE={f@gk!76k`w!9gu(a>6z91Ac1{c(q*<PCa4Zh0#*QV|hw<RrNT@w@gT
(Nla`<!*7!85COti43lvI>GbSOt5q=4Y|)=;;2HR-=_&$e1Do*}m?X0G?q9OWZhIJ#vIJ9g0AUV@jhHiS)+?>WplLLx?Zp!jLAg-
hM)wT55TN2lbe&hUQ`#wZCh@Sg4rz8&8iSLDbm2UsxhJUfoSg5YC_)1eZ#KfvIafcL*`85kch-jKEMQZTP1xo!G;)B>fx*Qa4{YI
P_)jSzdJ&yNQ0(@R<}En5cz$t+-
XvK?&Gg_3zIT?BLsa8SY(Y^mYJ@JHM+%xiinyC3ySSk77Vbfc1%2Iz@IiH9Cs@;^N<1SaXq)USsP*Lyzi#1e<*(W}*3SB1xY5Mq)
Soi?M%XB89~3U!h-m6rNgu%LJX(<mdZLmA)?qtD@SnD%T>ckTRNnJF&pcMl1&&&mPxIb?Jf~sUn{MX{G^rr#S{F$mvU<$zHNjAj-
M=cUiiWh;?T2-
DxZJyFRM&U3eYIB9(~h|Rs3z+79YSB3(rs<ro)8JUzu#9d&6#z2lR|!|>YCHnXQy#GK5jgYcSqQ!uf<b(x~4j7vj8?W3?|H0H1Hd
q3~FmRTm!g5>Sp0AY#gAPUUn$k8p~)oe8Ju{%s55J@i0)FM9(7p;P4Kt%x559yB;vk$vIwH(r0yDjH(a1AU^ON>*;G~cL8jHx21~
7Ybd#)n3r*@vj2HsoPB3ZwHvb&YeWC-EDkN`cTAYLz(DiH)$9&kRtp1m4ASha+*(B13D7`|X*1JgH_qu!EDN~c3-
ea=P<I#nIm?1FPKV7Cy`t>X;zk!ylZ48kIer`7wY*a#!m3PFQ%-
S{FxW}jS*WR_hS=TLhp4k+_2pdE5DrXWr{!6=^{h?WQPr!`^zIal4$;&Iub(u!q5H_zOf{12N;X1Hr{(>IVp8}p(^~2s<Pohpt9K
v}u9^i$lA5#z*0AMGz^UC14GVkz2_Cx!e8eV>$=nN%4YppuJ49$|Z|(~wFJxqh;D0ihyQb7WVMFRe+t97&_7z}=))#+Ic#NSINZU
yf8~O!A^WmX#Iz|xF|F@)U5sRH%T?B@<FYK;0z2j;c*aq*Egh@Jqip*M&kGg2J#N6xl(Djx%b5}9-3hOPrB-
$T2JoOt#(0$zu^xZ9Rw|@0X2OSp2YGUG8FZwuEm~o5^m@&}%7f?$90u%!j000080000XTyq5HU0nbG0AK(B02KfL00000000000H
lEc0001RXkl|@Gi+gEFJE72ZfSI1UoLQYP)h*<6ay3h000O8001Feak9|hH~;_uIRF3v9RL6T0000000000q=AqC003}kVRL0OY+
+(AY-MwEZ*FrhUtei%X>?y-
E^v8JO928D0~7!N00;m803lphz4;7N000180000S00000000000001_fdc^m0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c~DCM
0u%!j000080000XT>t#(=Y|LX09qRW03QGV00000000000HlGC0RRASXkl|@Gi+gEFLP*Na%E&MXmoUNUt?@(Wo~pXaCuNm0Rj{Q
6aWAK2mk;8AzY5jCqiKb0077j000{R0000000000005+cQwjh8aA;w3WixDHVlQ)OVRB_;FLG~nbZKs9E^v8JO928D0~7!N00;m8
03lqOTh6n@2mk;L7XSbn00000000000001_f$a|f0B~qwb7eDZVPY?HXkl_?WG`}cZf<3AE^v8JO928D0~7!N00;m803lpNv%8FH
2LJ%65&!@w00000000000001_f$10k0B~qwb7eDZVPY?AWpi_HZgVeeF*jdua%E;|cwb>=W@&C|ba^gtc~DCQ1^@s600#gE01N^E
0GS{F0000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l17_prefix_affinity'


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
