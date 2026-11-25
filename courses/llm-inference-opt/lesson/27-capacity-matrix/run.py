#!/usr/bin/env python3
"""Standalone entry for lesson-27-capacity-matrix; no external project library is required."""
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
8fH%FC+z2JXPO9KQH000080000XT=KZz2e$$M0F(y+02u%P0B~qwb7eDZVPY?HXkl_?WG{1cVRUmYaCx0oO>Y`85WVlOnC@w}1qx
M(1S-
At&~v3;P=p+I7A*N=vAs=6+yCD2$1WQPNm>*I$20GFJoBED=lM6ugcw1E4XO&&_BgH$B1mMmH7HRzV7r~c9dleOJIV7r%W9(~Y&L
c4C}*<)E*otqQ7P?WUY4aj$=tqMTOYKJZ*637$A+t2hyLo&useZSmQ`3ogJw&obAiPVCR()1K4V=A&D`w>4oe8j62_n7YMB9jER&
5u3oEe1j8ze0k*9=O8wg9_DlTjpV7vypK!=W0{$m)o2;Y6?7h|+3@>6kO@X&HYhcO3&y5>MDOdR<m-YI-
q!NLEUJ;!|j*%Heg(vQ1GRPcaCQ*$fNoG2S@xo<RGu@I<=R5LXKW+l9ZL&y^Po)Y{BCe#5U?_iN+&v*MSzC|w1!c=x3ScSwv$w*^
YU7OaFa~op!NNJ7;`{Kr)AiIL0DvKGVL|6&$`lvt7hhrq^K``g#xv{O3%p9+YB1oa)Ter5(jG`#uH%;2zo@-
<Mk}7WhQ5C5~NF|=6k+5lYsTaR`rhKbg<?<yACpkKW$&6|vEhQLAtcsJ5Cbf^9Fz|7RYv$7-
Y~ZK_7{PQhpI*Qg^Os?Z`6X=e3fSTtCfUy+jQ)J$I)9P~40X6rt)!7VZIb)_>!q~hYOr_yBBY+jGveHPniAfFKQ?X;xTt^`j%Od}
`=;!kB}NmiHWdoTiaTaeaD_BEnn(XEZON;=qEa92zo<;_HxfWcTEd%E*y!m>AdPx0_UAtLM1?|oxp!}h(rS#damVnWkU*L6hwR)w
sWaRx*uw-nlZUZ(!5)4wg1Aj4dEiZ7?BLR6w2krq2nIZ{$B`m-^*=Z-
oa1k4lXGI_kBw7tvQ7wG(Pji)H^S?%mu^T$hb}yYjqT~rz3GMi7f?$B1QY-
O00;m803lrQ5Y*eq1^@tM5C8xu0001RXkl|@Gi+gEFKlIVb8l{QFKjY5Ut?i#VPk1@d0%Z|baH8UE^v9BSIdtSMHs)&Us2Yn+jI}
Ri-
?T0i6O)bAsdNa)=8(PyJol8eo<Au%w{qPAtVGP+4u?ui9`>IlHkEW00|!aPn6k(6aRu=y?Ul+cTwB}Ojmv1?|VNAV|<1RQ5I<BIQ
r|-S16}M)SRX$DT}1$oEFLUk+POmEyIi!>v97nq#_BE+bAcJvr!jg-
02K?nWH!!))Khm7_q!6xkRKWN=YOu3(@JgGrnFCE~xuvl5$y=nQ#Y^<<ufp8${5f85wlN1_8CY8&Xzrk}+CHCnG8IDx*q9fKn!sa
*OgfFH@R{0PF!B6A{xbmVzxbK)f#E#yEM17$7PrcM{H!!MTbi0b1o0SW~8io#wpc7A|9l;0Q2YIGBt`<<3~tc~1Ctr*m%g^eGfMc
&~%t513<?MmW=930IDX&flT&Hx4wNWHO@>KIMY3nt`ubvHtSO&FP~D)1A-
JpEuC+r(aI5K7R4_AJfM_PVarUd;hb&+dsef=Dx*PFG&{R>8(4@9$tF(@Rz+?w}EKy?yq~7A3b~c>F%|=yE{7uZ2HA@i}k~my?Zx
aKDoYo?J0cj{{H>*2fv}!6UWet8+Uep`gZT;mFc}lFRtzY#^0ANTS1(XtO-HnVNNg9R7j-
U$y0$U@O4773<n5bBv}?FS($7ixxveNeFJh&T__>z;6m&>&<iyKC&#P+3IVWXLD2`RAB6*wY(fgtBCSeRXl6nA798ocZ~!K)72`r
mD~2Hy0vlu$L0}8XC|8G^Ty#1+5RxRclEm0GD4{;chzhg?0ahH8Bpcc^1gU{ok<tp(QrT;LAha+m1Jwd}n;Ha*l^DO%>7;asNSek
_JarE2!qYXxdrdiY-?vw*`oc%yd+029q^H$1)ZKXq4~OBb${AIffEZF|GQ!KjO7Ir;U&Y(%3N7ZNE5Y*0JFn)hP8<tGR))Fal-
m`JhFMAE4CUC;(vq{hDh1Ts7LCb>2@j&sLqbCFL9x)x{?1v!@;dK<lO+_@igrN8gj|DzzVX5q$-
w7uE1(`}>Io`6xb>g~<vtpgTs5N{5D>`diYjBEYk+;khWZBTnX}6CePbG&g7uz3_0dVE0|FpYY?})>Ue?g&3$QJ{QAuYqVS=KM)v
@j>-
Vl$qX%m#!LUp)85@00ILm)RK8e2h=#xoYw`kYf}!%mR(;gF3~Z}uPvVlHdWlAH?2eyaVIvP2raTA2YJYllFAbXz2l#d9OW>S1%^V
0M!~v84fib6}a;mW;8gA%S~nZQPR6L(rCSPDXJ-FUGRmq=lj?RI!=@gJxet59mQ{kBnefc>zk$n~*3I9Uj0bRCJng)U9}#)`|2M?
6eB|{fYIg>Tdtltu|$}9s?K_am_Oyy%C}1#dO#=Ydj1JsUC{xh$J%GMylV1p@Ink#(K<lx@d70wq>p@^$oecR28Aw;8>}sN$pL9F
sWsU5n#}{8)uFogE6n1XHfp#lp!{3WBuO*F`*F*yEQ~d95h?&>rWk{S>yxM%AbQH_qs_N{GU9XD`cH&pz=YfHj|^1uHiXf4z!icf
%@|@k`Gd%2gWGU{{lqRvcHI0n)T)up?$FqOqc=$okib)hw@5JJ}KPji<P^haWWZ=i^;nQutsAocLMzx%E?s|>?ROAJtjk-
4uLv!gudT0Liba3V;X9)PCf0Q8CAde1&fmE$lwUI{dHj>7@ESR+?&z6eIZ)d;ymTVmXBvVYM(e57KKi1Lk#(>@(@@&Bdc3(YCFuA
HpJ*K7xh`9e+bAR$K`mlR_Fy_PCM}P>|^3mIU2VD3T=t7tSJYpo|-
F8HA8Kho+=?V?q5UO13HXbnV@;3+7p~E?AWfy&Xm#zu}gheZV%QE)LJ@3xdzH^$N;mjD|>4e)1BwyV66TOO!tp2sno*dja&9Fj*z
*sYSZl-EUgGF5H}lL&oqLCYn6zx&@NXbu-bxN>M%fW`wO%!*8%aIk6%R@LxNiojfDB|9MPT0$Xur33I71m*2BPWe=Xd@(iT@lh#A
2ehGh;Sg8S%XWF~|<P=vYI=OeQ{!yva2JrB<u&p#xZGwz8AY_pa_$JAA&$AbC+TxMcGk*FVQGfn$;g19Z)G-
wAEpiR0R*@mk)dzSxD*Y@>7*r=ihqpH33#$w(YJ=b}$eTu4+g-
5Ap`nCI1JzKAkttCNCY`yB}7mCqQ%)K4p$o+)VSpaZvF(htp$ziAT7TyW=IqRvXY0!Rg1bWd4+#;!VbMQhO7qIHUi(f4YajY=o7#
lDnpz{w<O928D0~7!N00;m803lp+1m|5{0001B0000L00000000000001_fdBvi0B~qwb7eDZVPY>|UukY>bYEXCaCuNm0Rj{Q6a
WAK2mk;8AzX2?(BL=#0021v0012T0000000000005+ckN^MxaA;w3WixDHVlQlEb8~NQb1z?CX>MtBUtcb8c~DCM0u%!j0000800
00XTv)yN3{wCA09^n802}}S00000000000HlEf0RRASXkl|@Gi+gEFLP*Na%E&MUtei%X>?y-
E^v8JO928D0~7!N00;m803lre{ORY02mk<D8vp<w00000000000001_fsg?J0B~qwb7eDZVPY?HXkl_?WG`rRbZ}o|Y-
wd~bS`jtP)h*<6ay3h000O8001Fenp@7Z#0UTY4Hp0a8UO$Q0000000000q=8ck003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrP)
h*<6ay3h000O8001Fe^0?mzw*mkFlm`F+82|tP0000000000q=8Qp003}kVRL0OY++(Ab7*05Wn?dNbYXOJE^v8JO928D0~7!N00
;m803lrQ5Y*eq1^@tM5C8xu00000000000001_fjt%g0B~qwb7eDZVPY?AWpi_HZgVeeGB;miVQ^t%X>@sCZDDkBX?QMhc~DCQ1^
@s600#gE015&C081SJ0000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l27_capacity_matrix'


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
