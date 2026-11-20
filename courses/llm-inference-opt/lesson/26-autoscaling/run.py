#!/usr/bin/env python3
"""Standalone entry for lesson-26-autoscaling; no external project library is required."""
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
U+<mm{!6LGx=mj%NE<ufAS_0saS2O9KQH000080000XTyaqaFS!K(0H_lH02=@R0B~qwb7eDZVPY?HXkl_?WG`@RVQy|^axQRrty
fEr+cprs`&Y0!NgLVqHhmyQylBuCJtYX*qL+n1a3y-pu0*OLm0c&;|K8zKq%3=LXn<gC&Tt;zd^1C5S@xb1IrOw%R-
_{pQ%AIKC{?IyNJU%96(YQb|A;<y4Fd&41|?)g8rmbNh@z+^)q!!k%Cc;+*!QAE81DxKRxw7b?L@DQZ~@9paJg8xvzDlX)vt*nRY
RntGF*@~t5i9Ptfo44jNf~ucl@|mEPf6;Ip}<*eEU~F&|+bZ(C^*w=fkjBAo#~gOE(a8Z@#s(75x$4v%3u>Er>Fw2Ql=`5m!R0_?
Yoe00!u9;G=rc>n{$?j{>x<a|uz5zC}%&@oOb`HS|5@m9uXy41h1=<gTGui3iFh?r4uC1?@VHt$XtWZe?;p$pfCxPeOi`L*b<?ex
+R_j+zA@D6Kbhk=L{Zf?SSoJ`hFvd#doDSi?RWYB(v{qV?*hwY^H7aFQMfU$58el@l}0+M&fg)#N17fCnnqNop>ekDk)Ai6rGo?A
Z#rf?m$_40#Te)V&Z8r_R$$9DaNBj}$zYwAmMEd4n|XZy}IU(|c!QwJ||Uan~4D9kSH-
p;tMsL#=YIi!~`;sS|{J8Yb1P?TK9pl`-9~mAour?#@Is0gmmF_OLovdh`~pqp%5+6#Y$_f&SL_qR%sX4-
nNe0o_rsb`Q9GqFE8_gJ2DIjGt4Yptn%sOD^mc6klnfo3t~=QNAwG_0D;_J7PcvIP(SmtlWfvgT3g@U(nacJv$cgngOq<M=L<H0}
Ho1qoi+k8a;hCK{!NgJzCc*h%`6)EBICf9e}}}8ls|awiXTh%?BsZ2f^uR*bNiK_&`rB+1}TtG8b2!eeGS_h3Ljb5&9DOY*&+^1F
AZ^=m0eB<?}i(L^DV|4FNir&!q{8uFlaXYAM_1U=R|@ZE%y3Qkp%rswivn%e4R27_lJ&!RYc$Q6%LI?rhfMO1Yf0g3a0Bu%Ev+dG
9UQ8OggMT}OGH2lnPk1cqYUk!@unh0wRYRZ@xfxDD8)iJcvx+g=P1PMT<mzAsV((R6h;0-
{$2(MVzDb~1!#UAhupEVHX@iGGai7s=#`ro?1M{V_moTQ{Zl85e#&)X{@WLVR-
1;4Nee@nx*Uvm07&7XVlD(OHQe=yBVS_O2#~DcWvOuK%R4EbUPOMrqW|_|ZGXuFH4fowo^_3S;OFg|S&bCAup81~!XQx5`uW&D_R
AhaVZQ#bemc-
+2)n@~QB32^}DsIni~oiQCC7iLH;pd~^Y%ygb<t(0Zg{wP!54(`1m@*sVH0KMGLrFcDi{D0of9JwSXscUQL`JY?M#VafgoN>ltmW
qLGsA%-qoi4W6DQ?%jA^eDY>VD|?g(_m_{PGyaFJSXx-PbKtI^!`YnKMs~aK*g#DM?M>yqZ%;LH*Dvhilr|v9w$#EJp2AE_3xTqo
$~hj;`?kI@QFXo%C%X2?oD&%Ib&9O>NkBzU1oChtBmn(P!X3oeT44!bd*DzUz;~dJ($-
}%txJsK8Ap748<&Mby2k13s!ENk=@zG$m2#TWAUpv>>}FO{|-!#OS`e-HZ5lij;niQ2Mqaqwoq3yr77YSe#-
vo$t$R%;em_tCQYfKE<guVfoKEuywF3FgQ@+uvHgiHQW<W+Tkimkm&H6y`Y~l#+Nw+aQ_72I<F7^;-
)!e+Rce*AE}szjGLC$Cip*(HPO_p;O21uhts{VB(lt9Mq~?b8S)z3@W9-
Zfn;TZMLo&_IBfZZ&44W@$2+!FJjALC>6qDUIk7J;^2halx&y$&Soz`{&%&Fr1{QjR{F>Jd4j9vr!hgf1Iv!=6+8z$+aE*twAG{!
FzEsqZ91fZrGfDnjBxF!mYexP!~)rqFf8x-w_QTjZ$_WWDid@H8E_RZ<yKTt~p1QY-
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
O00;m803lpjbHFOA1^@tu5C8xq0001RXkl|@Gi+gEFKlIVb8l{QFKjY4Utx80Z*yZ|Y-
w(1E^v9RS6h!1MHGIYUs3i`59uCf7XcY<5@LuiD{dtEvTiyx-8Hkt_Km9Q-5tp$3z3T`V7z1#LWsubgE1HrL`33`5qpp)|AMD(-
957xcyJ$fx2sNl=hQjhxs>BLON8@0LyO1JUprr+m@v9Q5H3Z|Bb*QhD-
q>1&o~;fJVh9#1oM)S7?CV4a+(PQf^^8R0I8niIGv7?48u_=KrjpuO^cifgtIIcN{n|pc8!e-
%s8>%f~Ld(6l<81qX{1N_!<U<y)_|<FiI!^okl#$(;^`f(nB%jQNBS~nC3A_xCfRBMk5}Q4H}ayA|7I87Djm%m5c$%0cwf_427E;
6{l-o93T&%E%7BhJXes&L(7bSs+daS&M=lUqduXX&bj3?Z=t}-
x*Y^RfEdy^a1s>|fAP3)qd>E<<0%<IMM45+Y3ZHXEZF?_$(`!{@6WH@o__Ofb?xfYolDQ}?o5BV{Orfw>h^bkKf3ko#>45(rRm+r
24<Y&Byg%L*Q@*YroVn#-
Tb=x<mc(#pZ@vt%j()=jrH%7&#J38r#EhBtm*E<=erN8$G5BNyHf1R_tm2xrhnY4KEG9c0g}H}Hy=E^^Kr{tPj@aGb&TMo4np8ME
xy3sg_3ZAq_bGe9S=F1I7$2{$)j~7@^z9SvBvUpyjGM#ZnwBeHY632eC%|srVAy7n1nO~X%4#bjG(ud-
}i?&T5oYy0>vc7S&Rh35wQSyDa^r|=8O~xjWDphz!4P_c~t4w>Xpgomfl5-@^!RHvpC=677j-dDFn9H)&Pj-
C5s56yv`+sDKHad0STAjiQFVxQZW^^LLZ<rRC2=6+Jp<j2&YO_x6|pwWQ1@WhmcTZD(!MrUa>))V!hL5Yguh{k$(!E1^*0`sam?%
hHxF<*G}?9A@2z~aG8j}d9ClA=z9yt`rhJV-
#gj&jvn(C`%d>Tq?BefEmPn4Q{st9K>~<IgS>D!1m1cv#OsGbfRo2W_@$r;{YX*Jf{c<Jw_y6c6NdtsaQQak2i!&nMtd<-
RC5{L93U=q020c@ic-C*<FJ7fNC+qndex<Zq+K-
1p}@d@h(gNX%^n8_fEk|CMRcTgdVoj^x4WuPU@;+?tHHYHO>`6i0?sCS2^RVaQ-1-
dk<>P*RKk=K^nqMf)oYdvHq$u5kbuBqA+wYaltJmr$QV2eZKTcylbp~FtR~A?o6N5A&7kcMuTHrEGQoiW@D`!Z;*@X@A&o0z8d*=
8A`!G|l50p9NT8ni2rZqUV`zezZT(Si&)i}~1NH=s)?K(J+4AZr7d%jx^la@2?M2j{{Q$-
&GKMWOYR!AsJ!JS68lP&xxkbYhZA~3ok^yO<+!`MPL$vQlbW8SU_fV%we`<Hu<tso7{eG{n7Ig`Pr6!OwTvt{$e(5$b)xn(c=|yK
he>sEJnYxIEx`@K2W9}i#q^ZaQW7oF1scb+mdrgx$%J3m{`mkh47rg?Pp3jXv4c>JMmdiE=r5i^gnIPGHd|$%&0Aun1s>ufQm0*5
gnbo<{U)ADj6QuPqSe7Pgg6f?>_e2K)25Ifs>u50;y(Ael%8Rcua`dr_>d&_9M-
o9FHy1gd4^^S6!Q2F=!x(D@2I}{qHKOggpr>u~(8#%{_P~E>A+|rv>M%pzk>H|&+IBo-
6En=nW~inE?%5eaPEVtnAih1+?bi0y*`dp5HZ}w`0EUgaf~wR~VUi<huOMs$qhpyt+jT8#)yM)8vty+z{bEe5SEGqOB!`=jD{u4t
v5{|e+W<<(!!cJY?B(m~BKk|+L>scFc)tgTfN!{2=Wl!b0y_kza=6DdQNxb*go&_Z8uSdSSPe(U?UE64dU#1&_DPod{Sebw-O-eR
hA>9e8>nTwd_$li@LWK@8<wJG<E(X%FJ-#F;b3q70ITN<-R!|vWq)wn5%kak@lSUD&r&F-
NXRLLw&Li*?yM?%^|&i5x>g0zF=7oYh@P^mQ1;>pEF5XBbOasHU{+@eaUDEe1)!knL~X6>x0T$Pdu6%$ruI{&x|%&^3aYGbEwmOT
0kKi9Hk(S{jLWkU?T~;RycV)}E>6e0b7y8k3x{UD=VT9POIlA8#XUOgqh^3s3=_}8)6VVg&%V{>^mfZPt=JCG;f!hyHIJllt|zvH
B-iZdAg=?Tde`>N6iS0T_f9ZxSXVw_z1bIsry8wi2Mam;0!70xgH{`cs!@fZ#0*16gJ}hw{{T=+0Rj{Q6aWAK2mk;8AzX6==UrU@
003YB000#L0000000000005+c00000aA;w3WixDHVlQ7`X>MtBUtcb8c~DCM0u%!j000080000XTye6{;5YyP0672v0384T00000
000000HlGC0001RXkl|@Gi+gEFKlIVb8l{QFJE72ZfSI1UoLQYP)h*<6ay3h000O8001FeSiSiSQvd(}T>t<88~^|S0000000000
q=5qg003}kVRL0OY++(Ab7*05Wn?d3UukY>bYEXCaCuNm0Rj{Q6aWAK2mk;8Azc6b>F0(B003GW0018V0000000000005+ckO2Sy
aA;w3WixDHVlQ)OVRB_;FKBdha9?9=X=QG7E^v8JO928D0~7!N00;m803lp)Q3Wr#1pol36951k00000000000001_fl~?q0B~qw
b7eDZVPY?HXkl_?WG`@RVQy|^axQRrP)h*<6ay3h000O8001Fenp@7Z#0UTY4Hp0a8UO$Q0000000000q=7{c003}kVRL0OY++(A
b7*05Wn?dMb#88DaxQRrP)h*<6ay3h000O8001FeT64fEs|El7hY$b&Bme*a0000000000q=7*h003}kVRL0OY++(AY-
MwEZ*FrhY%(@qVRdwGb7Ns_X>MmOaCuNm1qJ{B000L72LK2H001r^00000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l26_autoscaling'


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
