#!/usr/bin/env python3
"""Standalone entry for lesson-01-speculative-decode; no external project library is required."""
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
5?`V*+{f!`Tch}<o3>3ZsyvxrQ8P)h>@6aWAK2mk;8AzY!50%WKL003GP000~S003}kVRL0OY++(Ab7*05Wn?d7b!1^*Z*X%iaCx
OzOK;;g5Wf3Y5IV_$B4l^l9=vsdV*5aWZn1}KFGfHx(l}-#kt#_g@do+togpcSa-
76KeMn+z9^X8^;V4;_efs*#&rGPAHM$bbd8=z^SPR1T23k;#bw;+*$vd#+V(~}YY2z#t23RA$?U~iA(#jc8Id5ev9~^43Y6sP=Wu
{k5E7po?Cly$BFWpY}j=3GM-
@klaSSPC6l3nh=0^32;fw4@%9T>J1O~bD7F>{)I`tp@+wP9j_R+H&+k!9Ipu{FA7oNs&b%sG=DB*IbJ2`9C(i$y#mtnlC(c|Dvs*
+Q`3_MKEWgZ9sAU$9SzL0mTweU#`^A+#v+#Q@r?CAs+37;P4dMGaeK;NM;%5~oeI<5gdae7RaM{5Z1@f6!+DKvMn?9xCV@3pw@%n
Xq&^=@=m~QO_Lb*_Zt#*<ljXryY|DGut#!e;ocCP*F|o`AyfC?!jeC<^w|?-
i6$HZ4ap=;H9)&+zIKkFhubx5Z_OTqF1Bd$Ej#ob1K|RHO`jafdQ<fikUgcsS(OzC$!ioV^)3S>!W#pp7v1d#LQUn-
s#WO{=aGSN%U4Ue||3f>7~8}CBK3B-
({Nn{a>|8lT@4pK4g;e!a?0hqZK*Gy@eGu{F0sj#A;c&jdiA=ldBL@4R^9a`mWjL${!FHrK;fpe`2)i2J)n7f;g{qkLH(2*K|fB!
=3b|5``OZJSt5hxp%M}l_Q8!bRDQVe;gmsC-
cJDDxfOn&y;8ZA5Er9Iyn$>I4m08LaWW5U+*1QZ_VY2S}L<V(64mc^$w#Jow$~bbbHj_W{-(_EB?{ushk~2g-6+B>uE-TDag#H3r
&W!agO}4*jSuTx|y#n@{5MrC>jNQrsuLsjY331%&IN@@t~6@L1t-
HQLh1&$C5mkqTI#5!n3E?eT1wI+?@KZU|Y2shwWx_6?(5=X9c?#rtLfHOMy-EzQELUAl!KJz3*Drcc|G&>o(g)3wM>aFOIcnhW*G
c81`<ofnVPpvi5J$^bqMP)tzW$O{nQ=@S)prNZGz20Dox(BPsYqi0CpMnuE$#4U=i&fZeNVhnz&J#)nq47!(GYgf*vN;w?s$c*9X
*9M0UePkM<Rw++PulP_Pv^d_zZ+d#(rhzoW;Kv=Rf_U_{1V%FNxLJ<+f{)qguN_2Lo-K<GMLk)GmIG9#=8q58hJJ?yc-
5`<~v6CR9+fgod_A>2k#0lo^O&f#QF%zwL;BR9=p;PdX+?$vtTQA@mh>6{Wy!1B*Z`$1Nfn3%r=97E&Ec<wX3lsR~_&pPN)nv<&Z
-YKt56@1x9nXjLv$u}Xh{k=-
ucfRLZpXs@=Osjilf_D$7PL8BCbw#q5bLCCF<l&H%SGTIG*D5oe6%Q=c9jn+{!R+xnfmUBakj?qiNy7x$n|p>fAZn|+{%adv1)W>
<{r~>NcjO&+%9M`y)xdm8E#^IM{5j@iCE4@|NAMX@$DJnl044xTGF<H*EwKTardvsmMU=j!UAJMwwmrsJYN4M8XF_2x}H-
rzUnn}!TM-
@pE({gFd~@Gxsb5+Jb#l+qwhI^LLPDSa0Ba0(<jegh$aXGxc4A$cFvv{7p@st8{+TkF|ckZM|cc)DZPGwM2d%e(oXQE<M}o@7PSa
2i}@lFAM%zajzK$k0VHL6HunqmT{^giY&aeAnpinV)OpekCm5qhXPA=E&ku_5g1NBa`C<67r5D2+hUpF9Ya-
6=(DU*78uK=OpRP9C2;0uZVM{|>!9Dj1Vb3`}f$>cmS5Cf@bq$ImDo5MGwbn$9K&h8DdQjA<z9R-
$c>qzwUf>R$Yh%}0=VJR!N{_d&U$HxyB}co}Zzm{I1Q}XWqH-x6v^ZU#PVL{fM-cr}AzG4Z3kE#_r_84>tRYuuC2(l0&}@l6JBuj
iyZyW%>-pEYXsvlzY|<exe0oc-
2i5Lyf=mSDR4XnOAMhQKJXZDfvBOF2<Y55~?p;8=kC{4csq=aRTq;w5Qd+!JsS<XxDu&{3aHA%evbNb(X?LQ7&AY2rSZL`VGig8K
Ya}V<qwUQFZuRz7cHDMQN#toP2<7Od*QN$FRkcsqJOz0`{y>0eH7--HB2SfL1!l@4^rIRSFkSEXt2h|1-
p`7qp(D@eJs>|AHB|$`9KKL_+E2H?C&=`#uaYi(TnBCbtN&L9E?@~!k}d(v#y)iH@pl8-
DILcbkK19(q|T$==|50Q0|XQR000O8001Fenp@7Z#0UTY4Hp0a8UO$QaA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCxOzTW=&s6@Kqu
Q8cpDBW8NF3z%q<iLkPcuww68SrfDvt5xo<nW?yMsj41(uttgyQY3=JGmi)%B3^hvA{Y2K?B?>sU*J1cT{Ati<8dPV;OXi*w>p>a
oa*m???I#0gG*UH5ao>3b2F{V9|mC<zIA-W(yBCyr-tz|V@lMOGVEGOBNWq9u0+Nz=gdq6%lV~_gWzl`H7lyD$pxE&Cl{L4c~e0A
gjHoekJ*u7vNWPJvMPC=&#ewFOU=rPiJMv|SztGS6u~m7Yi`o1P(vnWLd_W@>Z-K%)T(-
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
8001Fe&QocP#|Qubg&F_=D*ylhaA;w3WixDHVlQlEb8~NQb1!T#F<*0VWn*=0VRUJBWnW}vV{c?-
E^v9BSzC)7#}$5`Us36&ZmVZBBZ+_~?trnJ5HMzm<h%?+Q`=oL(^212RlU+$Sx}M(6EIF7fk0l8JOvD~UQCchi2qCCl{ZiM3puB%
y1M!@o0SF@W~xqo=TcvtbE?+!ybqWVRY{gB@~>yVCwtCVdQL>mk|w7zJ7XkeNtI^ho;=Rvfux-
7<ZVg$o=I}Xc(%(DkgLjt=XtZ)j#mYV<6R>g&f=J4MO|@8XjxWLiHX^)9pn3&a>3f)GAoz?s1H=IyE#2why&#;T_jCP<Ej=dp8Cz
ovy4||!AcpDyrOBG&_>Wa&Wn(6_Om7f6J*7cLyYoApm|f4jJLoa(9;Ltdq_?=xLu|h+WbD}6$i+sjFUW@%^sY*{~n22S${_01Bh{
!MqaMMIbW{kP7LQNhRh3<sLW)}BJY6{<NGGY|NX}w?_+?;tKa<g>WeSFdGQ%}s6+jq&p*9-
{tJV!uV@~5uYUd4tG|3o)Pmcs*dPA(?Pt#~zxw;DKfkzq{?*l&pI?6ctE+$h?(&nD4%p?NUVi)X>u+8>yZYqIe?R-
BLFEi$$Ih~pl?jV{ujW-
<36>IBJz^#K(S6~C#G^^VY6+t?XS?hPsUdjDd6F}n)V!Eu?9XV9I3zi+<dGM&D%7r|aaPui6rd!jiW*{Ynlnu;pb99|W)={$Tq%9
;qx<iYAD(>F;#7@n*Q078IZaq+9Yw{QN;Px}8=hw+yPW`ZmcppxkiqMg0i=9fku(!BD-
&Y_(dHsr2Li6pT(l>~nA|EG*pdl?d@2Bif~%-
Dn9XJ>+Yy?kF|2Kn#==)8g0Jo2SiEbdPSiv|=HDkDRwY|2v$gcXh48)kTm^EjEC)M432ky2d9;z07ySQ)Dmv(_Jg-
@l;pu8I?p?ne$fLGlyl`pVHS~!!eSA$a2;`dN5c3VJ+J+{YD3fN1N*m6!3IcptJ6i{QjL1?A>?%%L>W0KXz<gGckF&Z{IHe`fnE1
(d7KMB#>To&<{G7s}d1ObdEw>`FGK7ajSlS5_1V!4I6`2sA^-W?B67~d09~&XHWox2B{uaztLJvVoQlsSOiZz%P3!0UXY1FWaq-
^S(ZPZc=za7Q)=)O&cQLP65q+V==H|rK>J2OGHI^H3WFgjdkD-6(r)-
@|rf2?m~QH|ytfct0wZ+%xe#&?5+2NVNDEO*e@`D%+>?+PBbYP=u86a&I`-
DYj=*&13vT(NBWfFYa|@F6Xjs3F0r?Lwcm5eeiP0ny!9ll;wU6_V8*_`3^#_kbpL<n6cBh)H-
_`VP$9xr0*XTW|L63TN&v+flt`D%GOar?x<NYf{_f4?m<+CgA6YIzXA=LZ4IkiU(7<vUTJ2RA+X9aH!FNj7@@C6VViYCRwrR)NK_
m4kE5v8o=7t)c#teh+c19f$TB{xG)=p74oLLgVYAeh03Y1E+bJybQVUQsoBAJ$1YAY!Ny&Ps>)cR$!P`MSTENrTF*`153Vz!Q+)%
4(`A`pn;@b4V_cA;5m5S=t(ueCb>!h3u7*l~Li2_hZT%u-kzsQ(?34gmvk=?5P#5y-
W5(MoWU~?WgTT^$Tj+O=V`;)_6=@6AcWreX631W-t_IriYoMJtA6EcjvCs>&^{h(hsUKjj8EEcJ181~z3)rGvwqK};Sb(5iI-Yu?
9mc4u{uoBhPA4=seUrk5&Xu3Hy8(?JxQs!umg{%`S&LeR=1|8HwzT3R@@k;SLN!&8Q^i77{?5Z5ef`vl)`g*wx_77zhb244v8_}w
_ML33=MiHe&dcNg7XvWE9|d0(ZPTR10{qn#3NIfEXk~YCQZ=On`^VxarsKb7aAklV&^L~Uq@YjYl07yg*L&U{13px-pam4$=m$_;
Afq*c0fC@Fjvn&HvG0w1DX<jy6Mm5S$l-vzMOMq@a%N$YhC^H>Kp2-
6Ne=bUiGt1h+ip?Y3*Ru1j}IC2>P8jbziPID5<9m#?a(`9B7*(StE=YGlrW(BH_#OHFsB-
^zRUR0XH>BlCXJGw1Xhq3%Lk|Bp7}*q`lCeX^kPBKcdb*BSNlxj#;TvbquFJTqEoQY!kcwS=1|So+YzQdz7ckQzUCNM1!41DWx&&
{h~_IepHKt+AQ-{eDA|Ur>voRE$&i{#f75eAkL%3fZ#D{RyS3TVk!`uZ)h4dS8he>_*x!|v)IFX`bUGB#5&7|cjGKKo6ehD-
H(PgXs5*yQQVtI?etufPAx-<iGV<Y2*K`zY^)tNDzkLmSlrudDb(T9~yQgP0aNaiH)?`Ddo*BqU1-jPIw+5{_a@DeKv)n>Cz|-
gVJyZSl6nUq0U9V-
5+oKj8gV4XJ9X|`<#FP!scv5*YG3;<Knx^J>k<BBK{ni)iyV<4sDVFv5YXWhUy+=rhrJ_v^{cA#ZYxKs~I3>^pZSoQUqsAy0G~X`
z>R&SpOo){&@;DFlbHM9V>aJQ|SE@%fwO^}kB{x+rvLl;iII3>zQDMC`RVxQ4t~0?ZG21?=W3alQGC4SQ8Ia8ykK+(J*kTSIj<#J
g?v;WY_OL&OctP|``|3Vc*A(BV;Tv!(CF;dj9$5QG_i*q?XI`_~yP?_#F#UC|hP`)^9>NVSro9WV_0e-
4wt?isw{D&NoSV9*ZXyL9pQp|xyt@a%nNejFM!Or#g#+L;ks!mtiPU$-LUPYl=Mve9yMqJy0TW=!U}O^83J-
@|>HZTzH!*%H=x>oDI(`}G^I?RF54y2>TyA|IZ2xV%4fq2TvVscqT{kRdgX~*5ZjWNSBU3Oc8p!G}8^dWpm0n4a=qKm$P(g#q%!L
T9qg71+NQFue0i^(MZQ^^txi;~^Wv;5><Uo!}d;jBk#CVC1#Y%Jg+JUviAG|o5|AF}UFOabRb{(qck+6Nm!UtbC!*N{F0{;_)Zya
%qm~m|0IkbY={{T=+0Rj{Q6aWAK2mk;8AzX6==UrU@003YB000#L0000000000005+c00000aA;w3WixDHVlQ7`X>MtBUtcb8c~D
CM0u%!j000080000XTye6{;5YyP0672v0384T00000000000HlGC0001RXkl|@Gi+gEFKlIVb8l{QFJE72ZfSI1UoLQYP)h*<6ay
3h000O8001FeSiSiSQvd(}T>t<88~^|S0000000000q=5qg003}kVRL0OY++(Ab7*05Wn?d3UukY>bYEXCaCuNm0Rj{Q6aWAK2mk
;8AzY!50%WKL003GP000~S0000000000005+ckO2SyaA;w3WixDHVlQ)OVRB_;FJpCNVP9`>b1rasP)h*<6ay3h000O8001Fenp@
7Z#0UTY4Hp0a8UO$Q0000000000q=9k>003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrP)h*<6ay3h000O8001Fe&QocP#|Qubg&F
_=D*ylh0000000000q=9Y`003}kVRL0OY++(AY-MwEZ*FrhY%nojb8uy2b!=gDX?A5_WMyM-
WMwXJc~DCQ1^@s600saC0K)+Q0Dc+(0000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l01_speculative_decode'


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
