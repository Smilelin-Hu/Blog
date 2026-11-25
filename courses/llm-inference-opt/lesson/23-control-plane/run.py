#!/usr/bin/env python3
"""Standalone entry for lesson-23-control-plane; no external project library is required."""
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
8fH%FC+z2JXPO9KQH000080000XTn~BNw^jxK04)#z044wc0B~qwb7eDZVPY?AWpi_HZgVeeGBaOeZ*FvQZ){(1Y+-
I?E^v93S4(dcM-aa6ujtH$S!s408-
>Fv8wmlI2oXz0xj5FSJ=5!LJkv9o?(sv`N`P_z$$=z791sf1A<7{U&MAb1Uz22QZv2H*^<y5pi-A4Oc2|A%b#>L(-
Ja)NXHw>ZtX(Ak+<rt#7Uv@7DI*D!ykrTHtlZ;bhe$;gBXoyyAr(pa9wSU7Mb3pH372uc$I8Rd^SoYfT;>^xqH(3Fl0^~WS&^5DP
$6;v;kl5#o*OH73R+6${!gf!q<q``y#>?^TtO91IIMN}YXcSF!!D+DJCqX&jKhgiMHHu;0W)hJ=UI_53?0;DqbyHYDg%-
+Rq|LyY>y{Q#Oy7wWhDeF9pZJmy-
~0@AnQ712}kg2Wto=&0ZWYE>us!GyFy0J*6$Jc0b<0Hk(cVc57sUYz+IJjIw(>qm=|a(#Z}5i-
iA&76=Ooy(d5mmCs)nptXz&&MN@K>kH_S{KOX>@eA_|n<TM?5uTTD-J$!t2|K91--)6^;iS;BKxSela9nT(qfA-
+_v!~By&wo7o_2lgC%h}66&K^BGz4zVh;mPU!Uta%oeD>s<*^B41S9fPW9MA6jJp1d#>ytaD-#-
8M_FWsRWHhbwH}XAOJOfiSxT#)1JY6(8>rKVrc)`j+$%>T6loWaeeFyt>g*XuxMWy5d@aG#}+%UjW!J1q>O6Q+f%KEvw=DPj}jdd
BKFEuIDfSL>v(0x!QH4u$sRw&w89N6q}iD+CBc7XJ`LIj5EYMKLP-D+8a^9k-
2`ecPVB)Lcr$^L{1;_^o_s^SUL!TY^lFJWUslO%#(sWK>P>Fbs$hjsUam+jQLp6HXoXXHjM*ie%<)?pjM_XY#I3}6HSXqBpw=ecl
uH022-B(g?63{-3g3yGCR$B$uWkD$(vAT>prA7TVts7nxj>uooKdZTsjn+=<4tc**E<vt=3dJMwW-
~*x=guCoe`u)DP=40nzm}oYXOGds#TiuNQxZW;PGLU!YM2;>5<U)8082EOqKlN&C5G$}owZnZk8Q5&-
Zv_OH_eoxog(>nWSv`kStAdON$tuuPD7zw;AS8S2T`Zc!0S&Bv%>!*04c>=HZC*2>fF=f}L@_|aXmPb4jY!JG5^ntuPXcT>bYtB-
ab95y38E&jb7>yKBq*q5Q!+SVgkfYW7n>{6TkYEbrfLIX8hxl&vx!4nx{{l}L)+?F8lVO@xAedmGTSt>a0lbta-
8pjt6&Gp_qk%3cGn+VSPGa#9BB|Bhoey)BrGKyNQLjMc>R8$8@XTOgD-
}FWHb%#ewKPjivqCxBhL(YL+rX8)W|ZbL$=xv4BY3miNsQfRWH``@0O`YfgJ2uXZ7!3k>)gs+N!XGL9G?Th2U*TY0cJSTl4IZtY)
f3J<4}KfGd_IjagKQ2^?-}a(I5mY$;kmTa06VfL9<NWLLJ-`UcIIEC75?N?k|HDJhVNC$y`mNN~+-
<;u&}I_f$kYaM|dl1&dUM#Ghr@?*4ge^w!FuJExqq3(~`>+E{jEk`s6xaH1EOzn`|EGsq*$a449dH2<&?py6_9yyU{w!1#DVaR-
#5q+Ewm$biY{QlH#3f@)TcSjUhFa<fm`=)jZEo?`ijakTLG={6QzaV=Hcf{8DYh=%;i^@TF7q2)3QJv&b)E65NmXbu<hl;_OI9EX
nCpccELu^3l14eU%>P2nCT{o)A6z=E=*)&IOONF$E=~1m>Z4a&f@A6nCndhEMg8||XkdX$Fa1e+wRJJ1fTusQrxn;A{)NrHSTqNu
u=twvda0@D1Me?>&%hW62%{>}?XWj^oxi^klPYu73v_&Nwdq+Bt;09;x^ebUs0g=WT9ck86=$Q;|C)zTj2a#a=k;-
?OfM?6<B{&@Lg2bf47sc4C9});La1aeelbu@ZI!d@q+S(f$bgk<~wvVXpY^$mDXPECUv#6)BHvNSV=2?a@<{oHG_8XUJf9~`?M+r
I-QzJO7F-
{S@`qn<V1kvr2G&BRcdBO=hNcavUzRh}xST%F=qScwP;$^>DbFiaObUPXog{EWS1TBLnxj%R3w@*+XU!Xzv^$=(U4BX*_SALLzC=
#H7@K}e7h!;hO8AYA}GXZ-
415ir=0u%!j000080000XTyq5HU0nbG0AK(B02KfL00000000000HlEc0001RXkl|@Gi+gEFJE72ZfSI1UoLQYP)h*<6ay3h000O
8001Feak9|hH~;_uIRF3v9RL6T0000000000q=AqC003}kVRL0OY++(AY-MwEZ*FrhUtei%X>?y-
E^v8JO928D0~7!N00;m803lphz4;7N000180000S00000000000001_fdc^m0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c~DCM
0u%!j000080000XT>t#(=Y|LX09qRW03QGV00000000000HlGC0RRASXkl|@Gi+gEFLP*Na%E&MXmoUNUt?@(Wo~pXaCuNm0Rj{Q
6aWAK2mk;8AzYeU&a=b_000da000^Q0000000000005+cQwjh8aA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCuNm0Rj{Q6aWAK2mk;8
AzTl6+_zQ+001oz001Tc0000000000005+cPZIzDaA;w3WixDHVlQlEb8~NQb1!T%GhbtGZgg^QY+rC}VQytEaCuNm1qJ{B000I6
1^~eU008M300000""".replace("\n", ""))
_MODULE = 'phase3lab.lessons.l23_control_plane'


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
