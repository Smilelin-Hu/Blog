#!/usr/bin/env python3
"""Standalone entry for lesson-14-compound-chain; no external project library is required."""
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
U+<mm{!6LGx=mj%NE<ufAS_0saS2O9KQH000080000XT$)?Xv&0Ah01X!a02%-
Q0B~qwb7eDZVPY?HXkl_?WG`}cZf<3AE^v9JSX*x-M-_hWUr{u&)FWnkwF{VNl8Lagj<90yT3Hjc7^_w8u9>O0Z>g#td$2}|5K<(
9#50cwAtGLQKq43TH|*x}#9!b$Rb4YZv*U3h{NU;8I=4EP@0{xIfA2w~)q_h}J`m-
M)pIkg${z+{7`}CU#L}uXil>J0GGj{Al``yFNh1`~Q?5kDF6Ycl1<U!Rj)UNADm5#rtjPtNf+rW6)p=7u{Df6yK9AXvVX`!$G_op
rp3kigE=$eIiiw+AC|O`PfE2+pscUZ1sZc{EW<t#wB<iZP_SC9+U%)oq)O9YQNgB<n>k@|Y+)|9?jcJq!t}Asl&a3N~&J_e>RTV5
r#tm&I36q6A7%$7paI#AWfq$naHCI~r^_1&rE-
(G^ec0lkEA5}^oSSi_3cpscrCP4^d`W0<RA)`b4Nr5fH65c>tuvXL{%Xrn!XIRTr#i*bZJ2pYUT)tXl=D7&3l8R&xd?*5N?@l-
z}=aoLmnzssp#FNBrEKqHw+m5;G;8yREZB7p$%eO2(B9nHtA-
m^%GM~i9p)mr;Snw8AAd|Rh1OJ*g87+>C*TJHvU?aqchcrUTe)UzkF7U)M<sGiOhyf8)er<np~`wlZxl76-
77^Gnt7p1(9j$T%2RG&*C_~Xh}Y3B#cgESvN*+C#o8A_a;wMQ5(KhLl7Kf*@2ogbXd(sOIM$t`;>|O_9?B@MV~#XN^ueVqD{u_Oi
y?rkn^bkJ;mSYL^Ll*X(q<(l53GzVijp}pZ8;r4c=sTXm>t#Tu^)mRg?*xDp^x{j7WBDqtNRx$2`jt-
f~6ZV1VLGuLe}xVIMBDtf4j)D$5|&csUh$Jql+$m&gWTGiFuiD~P$4fS$%CR%sL2ggX_t#l2grxDhIqS~xXT&hly^Q>%+*0ytL4Q
fh-&tvLNUD+y^@v_sN!y)1y;2DxN{YD9@Qxfz8JhhP1`$%+Xrc8kygO8QjFVg!_2iTcS-HcE*>qw<a~cwLJ!>lkx>;e7&Y1UC!_#
R}|5WHx&W>Vu;}S{0~qiIhY!XLSV|^lpoN5q@X&*Hhupqs1Ba^LLLKx(8<yWXUz3vr8m{7mxU%E|>*6&SuBQC#Zw;igfHWkGe?SF
{9G)1Ys{{QF!w7@!@fD^ccG#Z%h^T?w6!@iF$Hya`=p-
g*|^(SY2>L6*4*H5(Li(P)Qbp|9Qr1YNkhz?{PDFT~V*)*4Kak^y|O=`J0b^$KH7lK!P&-
@4tWl^7DUw^{+p^{OF4ppMCh^v%kIk^e<n1^6{7d_~gsq{^7+JAAj?w&;Rq`Z+0tcqoKEE;cL5*pekJ_NatI*AMN%pzZsO`dSEI<
b-VigAN5*jN2QjnpcWN@8cCYVbworycC-
NIyP(~7UBu4@L*{|G@3COZp2b+g@eM%T1Z8LFn)b+Tw>xS=U8D7d{UJ&nxor=Y2_;Zfx-I(G3+%oeTM4lR--N)|*<)=|a9TuI6K7
3P>*#j5WxKn^jMM0F$U+ajiB%W&*XhuiK;)(nccu*jOd7eMquH4Wv}^v1lf(^zNwVTw^noh`r3u%ml%uzKu0<bn1d5yzq_?DWF?O
eQ^HWUVXq{l69I37v1#}p((6@u7Z`v0ORV!GygmA}ZxW)F79l>Jy7x~;Gs2*<gUJ$Ol7;3n^;0d~fb_ajd54O0sZDe70)0&G-
_t4pK;}7jn+jXnXw(Y}y*DgAnl>3&~Jw#m*Z0WGRKXq^2T6&dm1NO$G3Aq9<i#pmu-5KyezL8h%>VWrt{Egik@26-
pe>~k9OZ(6zUUV#2RulPxk42}vY<YA@eRgk6;)R<rRi|!Tvqq#htKUi9o>yxr-
&W{KAf?i|&j?DQu%;2eO~NjXQ*LS8qooixG=aW4wbM+3z2R<E9j;`|Wxh?XAaRx+xgJ60%KR}+M$^Pmy1H`{PQT?|CDckRr&;US9
M^{8@J5>GQP1^kNba8K(Edoe$bE~G+;99iyrp(w4*=jPF+?ZH0x60Yi}3$HQt(~5T~oRf#)s_Hfq$d5_;m9PnZ3at4mTYA9?u(hb
?dfnOm!HiE(NPAjp)xr+wqr8W7Vhc7uqGhM=m;ef)1Xz4t~Gr^^U(yy7S_?-{}r&FM|C$uzDGVAwyAev*A~tJWi^EK1!i=@awdN-
WuCAu55|6mF2QiRZW?7>Dj;=&}aLO8B2_cAg0^8Jwf+9wST%Y7gw27ky~hcQAW4C!R;ieuG)KZhsl11NsPEz>-
9bncXnC!0~Y?O42deOGPI~s*qHI)H9r|{4iMi;XqR^!I+oF`Gj_3z<rd7ovliCFI`o4PavYwVfx+P|^0}V3-
5Y_y;9%>Yh;DHYk;#>q+Zi9%d97V`(%R9|6M-
@?JPTb{po<ZB?AHyt_D4=>Z<Wo+co4*Ze2jZNB3x7K`2BW_ONyooXA~x_&W@<nq0Yf$;qDELDd<}wdo%2gyN;^$V|%X1Ito4-
b}2hIlc%SLPY#ZfgVUqrox|sJ*u#_4v**ir*b7SHM7wj^+OlGEq#pVIVomrt(hjqjQL=`1@)f-
xA6WKS*Ew)M?1#2vc8UE5jP}b6K(RrtINd|1&DAg6$&02KGCTcakP-
RHsx^enMd_mhyzzV+sPpPaFSH9Qb>VHnwbMWt2Lj!;QWmYlUk6PpBwgEXJL*;`-40!y?^i$|LGWYE-vUO<c-
4H4mzir|PQYS#OU(4sGRFI3tXxcMDC#ZN(xUw$8S5#3^yB@g6&c&oCiIG@;wF<5;9Ar>A3ogoQCP>jHuPI;Y}HtR!^^P+xp43KV6
PbLWoLUo8}6M9_n!TdZfry|DJ+E**jxGtaFD2~0yN0HlVXI2YicY&5={?{PgnU2M`-
a;pFi@p(?Afxbj>GXTV^;EY6<8%my3~}V+=MKW`-
8fH%FC+z2JXPO9KQH000080000XTxk>bHERa|0G$v304D$d0B~qwb7eDZVPY?AWpi_HZgVeeF*ILeZ*6dIb#7!|V`yP%ZZ2?njaO
T56Gs$&_pg}l3+rm_*g&f)l94DvDiVUI@Mf&lW_KKKS??}0vydo?6k0ARga(zAa=)~t7bKFRst^dJ|E0us^2A^0IdiesCS39m@6M
b#*YA9D*0QXFl=CDe)!pR3`DMcCiHyb~^dhn^X{SjR2W0O7!f=@jGR3^KMNWmHMFLNFBno5dP0_MtS%pHAC2ium%}ivBx-JRfJQK
u=<3xBOOk!Rrm^C()dW=)^-tu@W3Mb902-
{TaOJR%dioD4(Z+VOc<(3es>qjAY*|(61mfNCUKpA&P5OO~`NtxSD0vf>rofgdVg)88}A#EyH=yR8z3<Dbb)G@)iUqK$;Vw7cZOq
sEF(3?DxQr{sHjQU9&gc#g@#u5g~vKYN96pl>n-$!aj)-
DkE1C4GN)T~J6yj0y?@^z9+e#;AE%aLLt6cMdixdOa?aig<vuJ?HT)%@wr)zjTeE4}5r-G$2=Yu|Nl-swGB-
n#N~^XaNSKb3e<&Dvb~qr1Aau{OVT?MZj#@7|3wy<2xXD|a?uUg?~FE)PH7Si9I4!1c2aUcXrEJbSY7@9oZ`Yn`Rl?!C3n>N7ao{
ozlrx_N)T_u|^C`LDGlM!l$?$(n6(0cap$oMvJy$prk!(o$|Y#7ZeEDS^lna9{=(Da0<468sRX619p(^NB2k)Vop{2i-
|b$>Eg7dk@I00iq@&O5k9cgt0(foU)TNAhPa8kMcsEXMhjbRxV)WSRnn<AVx4BmkZ4>2K?vzH_ANUr>XE%tfIvzRoXaUjQW|t(22
BzYJ%ic%mt*Vtug}t{U{4SI!pDsvLS7HVFYc%L1B^-
(V|2l0xTB`g+f4^#0vr!8YgQ5^tmnjhmH4Jsk~QjO~{QRDeWPLAZO#!b0uBQtFWz-DhI|aW>Q*%G(!8(rk6#cw#xwzlF+BTR^Qby
KF9-Z3QdxN4;kpxFXONU@Ym@chh%b5hoy#er2nS9QRksO>P@SA;lkFBD_cKZQwRrCcISWF{N^8kdS~U?*7+rP=sx<ncYg)ey9-
x4XP<1WUqzfQJycj$2Rq*{0+u^V4|<o+^_Cw)%N&bma~{rF4QV`V_PvzvIfu$#3IGdiaO&POfV)y`TJ78J?fcLYTMrkZ1)(K6Pap
Jtzo^;~+}T*WwE64l-um_Kt@+;i0yJg!{(|&Et69I&y>kl|X0`cxr7?FbR<YyqkgrAKYeZvPA1IPNr1}o0AtB1|jr9l6*-
A5}(d0){$NF_70O_S-57qSD#q+SPWH6W~e|3I2BLmppM-
$i^A(@m6ma7dD5u<QB#Kw1xs%AKicZLnn<T*qi^4gTAKnfB=LFkL|d`}~MEQJ;9AZ3;8ef{F5e*Ap!xK9^<fV^QOqvf)C>4SL4;a
SCPt`CeXtZ`WueYiN_5ZI_|Nq7w7fKJ1v?0z^I3+QMLHi0pdj2j73tC0%OhOt{$t0huxAfM=LlO{-LjcN%uX$-
y0fKL0)H0E?teJ_e!>54rG*O_imNsjt?sB@(xdW3hRH|>h#IE}enkm(m$8qqoy0cHE0?9D`p7eGE|EycUz$^?WB#p9A*WKviXVNN
VW5S9zmL1ij+fDJs-
H;j7vFR&wMJH<c&Ca_hRlh(m!CMa6RiJ=SvO;sSu?4pqn8JwR?f*FUnAeq1IZENE2k)z;E)0)K`l^H}9ruL4p9mTn^lhrZcU@?Zb
O+@7Y1EM-&N1B9+)vBLW9HOU>T7DF<i^>NYc`27(+S|AZb=F}N$;YHxsZ>noE8odSHL|l(8MHm~LQct-
a2%A$sRLTy%n|x_o0UIv8oXfpi=#&;<SJ-1t%&mwIF%odY|PUT?(NyW;XbbAuQOOz_=Ztw=O>@SwjSonYC!|D3>QA&0&-
Gr(di%rTnM|EQ=-8CRxRk=dv)kWgPDyFwdgi>@<OOPFQUg2w~Yb}(`xG)I%KyNoO5LU%)N+%(1+5OCUr?Uh&nf8Q4z~r9WC-
3^QCP;Ksate)u3k448f_WR6;c+P@^lW2cg>NEIe!z$XbcZO{7G543^PFDXMpB!~$R^7C;%i8tj;Glo*WpNJ&b|`$K6e!XUHqXO4t
iYEZ{@Aa9NnNcs&8P&vU37LXv#018%PAiiD2(d+WVn7=M%8iN?5EyuJ>j#@`E>KOVnDpj-SqyeMF^ps|`Vqg7sBgw#Q-
7+_ZJKQ9gjFC1mS4gSa*uGmnNI$%D<YqLG(>S<|MiSGXLDcKOh(2t#RmbRvvDlDDeWpA`h5c4X9CDOp&_`HeB`<5Nj2GX@jRR_w1
GV{Ng*WOSCpdQZ(Ppmt0TT>gX}NXv5s5n^pOdyign30&;MG3d?AUqE2(L=6Q32()AZvgY7k_eW#Iv?-
YL_Fc##{0;U@fUre%`pFe5-}A&h-&8ZfMHWT-Sy)+9Tf=`m@)@uU=>POU04o=$Ii78564Sx-rnB>q>HQUDWBimQtn+6#fTLO928D
0~7!N00;m803lp+1m|5{0001B0000L00000000000001_fdBvi0B~qwb7eDZVPY>|UukY>bYEXCaCuNm0Rj{Q6aWAK2mk;8AzX2?
(BL=#0021v0012T0000000000005+ckN^MxaA;w3WixDHVlQlEb8~NQb1z?CX>MtBUtcb8c~DCM0u%!j000080000XTv)yN3{wCA
09^n802}}S00000000000HlEf0RRASXkl|@Gi+gEFLP*Na%E&MUtei%X>?y-
E^v8JO928D0~7!N00;m803lre{ORY02mk<D8vp<w00000000000001_fsg?J0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-
wd~bS`jtP)h*<6ay3h000O8001Fenp@7Z#0UTY4Hp0a8UO$Q0000000000q=8ck003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrP)
h*<6ay3h000O8001FeX%qG}YX<-Toe%&3CjbBd0000000000q=8Qp003}kVRL0OY++(AY-
MwEZ*FrhY%w%nV{dJ6Z*^{DUt?%tX>KlXc~DCQ1^@s600saC0Kx$P0RI{Q0000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l14_compound_chain'


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
