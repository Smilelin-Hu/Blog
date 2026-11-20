#!/usr/bin/env python3
"""Standalone entry for lesson-16-load-router; no external project library is required."""
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
O00;m803losM4&!J1^@t=4gdfo0001RXkl|@Gi+gEFKlIVb8l{QFKjV3Uu<t-WM6V`b#!HNE^v8`S6ho5MHGIYUs3jh^kC0qCu-
2a7J{rG#IR(8KCDYq+kIxY+`gr%dM_*so8Uu?F$oe8LU0L05tYQi5_2X0MR#^5Px%X;y7lzzC1xIm?y7S?-
}$QA^Sm=4M3Ix;De}+OO_CNg>Cjcmf$*Y|EMFuv=7kW15)L%QzcOVpB?4sE^SoATz>ADT(V&tQhbST}D+?|O&GSN1$%<UGT5gRmm
Xr%{?{SgG73Yx4u2C0mM=qhW1if4P<q{R}Zb}!rVhLkQx=T`)QJgZ=CAGDzOhI`JNWw&1tN@R)B7sx{Bm>D=EFxH83FI*xW7g$tO
-|=YS+HErVkQuf*^F{|4n=?;r(fkcaHoETF3gq?2V{l==9(}S+%)F}53r6GDuxA%iz=7+TIDL8R%>=<`V$g5Rlh~>hYli^gkGv!)
#;t;=r(a3i5F-
Y$z%$lch0tF7UZjEw}#tKcAs1$pXGy;EiOs2`{){({_^wFWdGJTqn+*1^XH?#@9*DyU~McGG!4Ds?cauXZ|y$%egF3M@ZQh+f85`
{^mzC2cQ1e1*?+pTcjfNr#f{OOtNT|T?rmLs_3Y~C-
e1G#KknVXzW3*yms{VW#o^<J!|UI_{PptQ<r~8*+y8D|9Nv8}+WBSp!`0!_hocv`a>=?>n5vr+`ku*&BoH%!#X>wTdI9lD;2noNR
XGrnsG9ObsO^-kfJv+>6Ks|6+RnVLauTt;tfW8(RFV`Zs>{`afbFj~g80eMqX51F3DLlDW-utLUI!*QjX|k78$>9OsFiVmqDo~Q3
yotaB{g{pNFi2mAWRTggBa6J$N~%soIF6}uDd*yMdlia!Z>)?=|n9LD8nZ=k^<E+2Oum5lx7PlDA(;)tChfj&?Jd)0ILi~M)-
OTdA}aX?rFO<qc_^5^D#MF<j~il8|iM-gzt4+M>;VrY0Tt0#w6EE2$@1O`lOhCc+v$hU~6i|eY7ANj?dBz1nPtKnXp(IpLK6=8s_
wh`b|tE!evU;L6JfK#0mYf;bq=tKwL=S$$-
FWMxzwv^LRbVMEJp!?Z{CEdrgDAH#69K&sm%|s52lAn}p%l`LwmnfN_LKXl1+cQc(!-
ZO`?zUr_027={>v(Gr?RUa!_WtmdQ*LxQiJ2c(h0hf@J5mc#SBf}>T8=LwzO`$p+gnhK`{*y0>(X7G(L?UOm}t(#+?1Dk+;na4uA
aS|wJJ=ROOtw&1j%`pjC_iJQ7zfEvPh<Zn$k5MweX<?=q<xMd*LBd+8yMT-
yRXh#INj=JzbL_c*Ol(Wa21LtSiOAuDd_;Qv8eN<+0ptssR-k$RsHq`Yg-BQcQWgSFh!v=Nt%(THf8aFpF+5WRd{9N02;4wWiKnz
gZR88zn3|iKx7b5fV@he;&0c?g9Jf<{+vpo%qpY8mT|D6+@vUSVjn_4?A|df;B?}Ml0!eKV?Lb4y)e<iY*0PJOp^r;6UpG-
`NsQXYe^e^%gY`dj{Ngc?reogJ4bZxH@c`nm>&}3~bTmmC0|%4N2Fnvz+r$CX2-
?sFn&fdLWR4(|sVVXf(Z(#?)nnlL4LMRUSFR^I-
+puUNsD+HCF*Nd_Y5xh$kb|6O_4waUwiGNM|ogw)Nhr^C2eQC)U4C%IBMYO`^&gmhOYE~d)zyHzN4M-
#jZ}HtLv*30y6M6bR9~(l9h7vt6W*f>Iw+QE)3-8T9m_TB#UKG1ao{$?f=X3AV0duCK%GB&>gR6zO<{w^4Q6WVhB|-
vt@{Ga(Axg)W`zJn@5ehB8pNQwbMMT6-`rh8iz03-
SZj(Gewb3>sts8hpN(Q!Iyyx1K3(EUT+hemlCD>2l}MuB4tAQY7+}x`U*l=Vwx{noZ4!Oc6&^rIM#Ir^)2VEkW6XV*I;Tg{h{$bh
vdyNN3a(Dc*$GF5w2}wt~lW4gT$LWtZH+f8Th^h)_C3UiltxNH}4Gr`+1>Gs)Jt|huGQ_!)>d<)dV*=$qn1DJtN0r?mFCe4QcGT+
C}D$ic!`@Z=9(|R@+A6PS=bwB|dRGwBIhi`g92<@0o!<jsti1Q&&OkdK4+J;<uur_$X2~qsTMHjDyyHP)h*<6ay3h000O8001Fea
|GvIT>t<8U;qFB6#xJL0000000000q=5hc003}kVRL0OY++(AUtei%X>?y-E^v8JO928D0~7!N00;m803lp)ve4i-
0000v0000T00000000000001_fsg<I0B~qwb7eDZVPY?AWpi_HZgVeRUukY>bYEXCaCuNm0Rj{Q6aWAK2mk;8AzWC!`3zG4003P8
000~S0000000000005+c0|5X4aA;w3WixDHVlQ)OVRB_;FJE72ZfSI1UoLQYP)h*<6ay3h000O8001Fe|NQCah6n%vS{ncW9{>OV
0000000000q=AqD003}kVRL0OY++(Ab7*05Wn?dCbaZfEV{B<<Zgehic~DCM0u%!j000080000XT#m~pLSY2}0LTvj02=@R00000
000000HlFa3IG6bXkl|@Gi+gEFLP*Na%E&Ma&L8XX>MmOaCuNm0Rj{Q6aWAK2mk;8AzYeU&a=b_000da000^Q0000000000005+c
?GFF|aA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCuNm0Rj{Q6aWAK2mk;8AzThbpgu(g005Z|001Na0000000000005+c=@<Y2aA;w3
WixDHVlQlEb8~NQb1!T$HeYOSVPs!&Z*_EKaxQRrP)h{{000002LJ~E2m$~Aa325w000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l16_load_router'


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
