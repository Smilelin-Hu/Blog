#!/usr/bin/env python3
"""Standalone entry for project-05-fleet-planner; no external project library is required."""
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
WAK2mk;8AzYeU&a=b_000da000^Q003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrrC3{UBu5o~?_W_gveYAHdbJCfXp)JrvW~D~?^
;<Cv>2;Z?yi}sxNoVd9(%AxiV#vHg2XeA2q7X~ct9c-
_&4n4^2A@@J5^mXJ+tF+BK+X#>N>YNm+zeF?|<(>qt$~;Sw0ZujMZ~9t;!z;VHm!3e8keKG>WH&@iJpd)Ri*qT1g`m(^IZQ#xCc~
Oa;sNrH+H(Y$`P?s;tQcn}R17n$>wzK>UPNWj>GDkzuklqBOE9d7jU$4lYa0%8H4bS}0jyH-
HquGO25B(y35GCT2p-86@hewD#1hdSAdc-PCn1p-
CFes_PPl^4wC4<&9~S2(Bx2HO{N+n9dahV^tL_NyZIrCJB>;Js2;`%5btv2Z4X5CN)=D`1O?QX)Z7Q@_pFipDXR3>YST#r3$}Ru%
%kA^n6KZa8zea#tlz%t~DK_Rjo6bn*M6bQNkZ&fu}mf(ruV|O<r!_AC&VxdkYTcm$?Xnz)E1JO2FNjq(dGmRjKIRrX(xuqBjf}{@
|lCgj9(S8leqhTnMfk3O4Cxsr3_6O^HC-
;HQmJ2pK~HNmZ2;zSufC`03L42sZv&l%q4%h+b>WF~59Pi_~d_p^40fOdDm_Mw(o#mXnI-s})5!5i^;IG6j)o>Rg;-
v(Mr<zGz84Xe5kIWLY;xZzrl6bN41sQ&AhfRYMRQWZ8k5G;~<aMoU+ppZk=F{q`xX)J2~?sY-DX{Gv_9?MzR2A&~Q_06oRu=|nUy
NNFa<?2>DdSYj1va-
a8Oj}6{rcW8G$c3e<=2UU~_ohn&VdW=YRY@^WYFvmR065et};b4H`Os@u1+hHFrv#g;u6)MXh)_6G;c|8heJeSA@VKZh`=PQW0mV
lndCRS+^*@Qb4x5d3%tGE#=m0CD8RnGEiB2%l2Wdb->$Wm&9SFJexIx7ijTC_vbbG<Bp-
3Ga2f@(yGH@O*w5Qks=z{!dUEq0600!sQ+%3=hRT#5S0PBu!3L8J1HFL+&xGV2&~e&KxrYXmn82*nEQNMts93hINSL0T24afy^fF
=urJ8}x3AeGz_V_19D3(4)l}_Vag-8M+5&6J*IXpR-FOgBOqZp)QyOI?iUt$0w+R^on%sG>^JS-
Z7)n@dRNnXHj_a^zq?wa`YIxA#Y3-
_U@OYcZqs(aB}#Jq=h|yR#;tdL=`eQ<q`zX2vA8Dga3KPYig!PkMD6adR<Yk<<{4K|Mcs>{`s4ae#hQ<4?u!4{O`Yi|MK&He)X?E
zWnHm7oUCj;<LZK{PZthee&^_|M=v~-~Qpn7axD~r_cZM;cs>;YNMgIX5nkQk)SGFCrIa8xgYKJFTWX-
;(A~zM0LCR{U7yOXh)@%t)Lbaff`Ag%XLIVK6bPK=DVQXcU{EK21Dk7x$m)H%bvwp!to72-
2`Q4=$iJ(ZMQpWLS3Wvh5aE)9l31}mI)<LRk|(u*9+{v99s#o1>c0g*V$ujQgB*CSQBSWQS0b-
xn;Y%#*EYGaL7Ury@^#9_SfmqnLy;G5O<~x0!$jYprhHD3AAhejFZF-
f=ROCTl9e|1f>brsg$F)d9Fnta|DW<5~R1JbTM|Pb@Nk9;Aov-pB$;K8U=J1vCy}JrEl673{@*wxP)-WX1K-
nksZNe`WN}!BB&m2^j;9IyclY@z2FJDgmwpi)DO0}w{2u$chj1SP502*apMo|P}_B@&bIBte%CHKo0R*O*F8jC5p3zOzCU$u-
CBB;a0B+nqzSnKFN-?bLfskgK)#Vz?&^T|e*BHy8}FxRGk-kY8cX}oC0=waSXLAHf{#U~yli=NNPTv1P2z={F;%B-T(d@`H>=-C-
kw)$Dc@G;N+6}uxz7knqOhhBzfHm}jZ<!E+@qxsH#C91I<?bGg1zBxRUNKm%w@h!uOM-j9=RSt=F0prO-
9qiQM$Tw6HdS7UM18@ET>uP*&Nq~;_ybA=uyx0Y)I~&=+OR1y2yQtliY9oIJ~8HVGjV{DKSJR$pR^g7mM)!KT_~rxm{Db6UK+^)q
#JbwfJ=N4Vk^c9u7Ag{T|O7cXjKwZcKF;r!EDnD~;&SMBDL~O=H!k?-
$x7zDF)Pc!Ca|xDI~5==F}jO}g{qy5H#zYA=HQJFt2gg&{*xa<k!ApFB>ggFZ^3b@1!7h29$5HLh%lww2|wQ&mlwb?Mo_8_;L_ju
}ggiXf)jx;;VnJ+*(jG8b2wRFPX~dr?NWyus}xsjk|4bBD=(hDnULS?l#a5qEZ3_5&9Fstk!LtunNzQP`OA;59!PZVnLNN@$mN96
FZKtuuD9jO7;0zOxqA!#ebX5po=!oPojNE%LdZx7{0o!Qf!)pNMX850S~0nA;g2*Lkg7cGB9>(i4F)Fgy!gSD=d#c<k2=y7os-
X>XOy$aoOMfP9R5JtACF?D+k5j7y593uhE2t<H|9)uGP8W8v-
%j49|_B6~CJj=PSk^<#Uk$T|u>8g?l=H<PEQhffZUl7rKu<ekIkblAg_)3fKxc-RX{;zYZ1+S;;WbEF>m|6)z}InoZZm{GEZcJdX
yARk!vSl2mlKkSFLV|I!C2aNX13_!6#t~lL8r_I$b-
N}ol7&1HkV~`Q~%BnSl%th&=1HAEk8>sW@M=!JsD|O**!L`#s7zYB~wo(?Y!(RtYDkNRoZaeB$DcufTo$psbAVKhB&EEn>%Xrm%j
+dEhU{1hdcuUOm(=x{UW2{_EYbfe1*3zQ=A{px`fAr)1s1+I8(kAqZr{X4)6X06ZJ0CvW_fc5KyEgP&Y;4t7fWynN1-
WqV`CzXY>}6+rKO63y4ELV>l5T87Gbt>E71&$)2yl?7ssc2~ypv*thihsqKoU(4jZatk3`c13QJ+8Zw$nfm!F0_hVq0c76lw|RI+
u%)o?{F)8D@qS&^JewhrQr`P)h>@6aWAK2mk;8AzaSn)Um4z002B9001Wd003}kVRL0OY++(AaB^>IWn*-
6FK{q5UuJA&WprO~Y+-J0WpXZXd9_+wj~vAne&1hF=@)vOo?*TA8Z+@kvIrqckXdC#URI-
0ZFkLVvpwCNuI{~LwUV)N0erzqA|W9JilSV2F+w7Qo5X(!%-
Vk9FK|xXyJtMMCBg&Rsmr;a@0?TZAPBaq;x!)EWPOwT@A_ZKj5E<xJn6@*WN}&_lb5z$B|pzNugO-
%@|;(M<q5gk)P;yy#;ZXP1Z!)Ps+bW<Cru5vDJAKwEUFrg=0(lww8+KUnpvx+C94ECzxSBf%hFx*^EFZA=I@Ft!X>Nmh@rX#KQ+q
|Zu1Kn+Z~8K267Mf>bj(Hmh!wd$KzsFW*mixNRo=UIN%kX6$#Ho1Pa$x8Vkw~(uC(Re+1c5>#j*U^&|3vw$xUU=5<7V#>=cYo&o=
BoF@@^scg3Qn}{F<n%K=p@TnS~&C6_eyX0|1wkjSMd6J?MFIH6nY~dv8xwf{w_2LU;WX^_b1pWhxG)+c9sl3}?-
|SD&hkdO_5Xob8T4#LZ#lUx8y}R7s+b>`3Up)j7J=HalX~D8l@a>oXn1A-q`JE5u|GN3$qu0-F-
<$vCjrnJ{?!Wu{`Mvkg{&RDF@AHR$di(y3&*!hdD}(Cc^*875-
~9HoI}iT;hx_+F{_d+=^FQ96fAsmo_pYCPeB<n$PanSX$^47A=Wo38;On~&{&ow=-
~DL**1zXpe){0+55Bqn`q`K7&+p!u{~0d+cYga5V0HH9hxfnw5Ln%R>(eth@ZJ~ST)&~^tT@Z8n@3?_LY>%9M<Z8>2qF^1O;uqC@
jNNfuLLZ)%jH&@AHYsg9YbK{qOKTh%ME5NLpUBGSuqWIhWT%s6qwO8FPmBbdq?J%+pk=cJdGSiNV}8p89D)YnMF;uXlhNa<ZK^fE
an(pc<C_Blj4vhJWd5Bpkz^q8oWN^S(<aTU{oLzIG^TIVQ8~B=4H*4u_oyeX123cDnKWU8lE5>%NbS$gkdcpvu2>(vsTY%w_kn*k
BXXAbyI?18Pjx1xCDn3sjle-
!LXC|Pf)hr+S*#eCxj&l1uSWhs|Y2eR6~m{gR6RLOK$W?|EJ_yk@KO{O`RV2B*LKIx3Yp9z=AbdJqi+5vuAZ8t#49$W`IZ)^j6U`
)>=W%92xK<hA{O6R8=&rps5Z#0VVB<z6uqLkovgfBZ*^%_=d4J<WEA8W{7Y+BoH?d0u9gP-_pWBEaN*#8Uq1X8!KxAmnq=MNCLOK
t)xmP1j>Wn9;AX!(u{{abxCFoO9fv9zi<+qNXDlmDY%eC_)#kAAvsaRPPN_@I|R0xfmC4kxaJ~My9X?5IP9ZRgREeQ2;o9YHb@;v
5KMwlp2i9i*9#*42KTzM%^FCyT~3%xSyJqxdyHTl(kUmJrY?b41U5D=Ng)P%{3uDMT-
2d)fOMh;kkE!9l{AJ#8Qp|adsPL5zos=1`;7nt?5H9Y=4{4C;J2_U4tE0l6^wh4&SW}GcSjR2Q?0h$sywt;G*xy?5n=pO-
m*Mq<;EyeM_ks8dp$BKDgw)JkaTn$fD^+2MTS7#8TZD%qogJU7OUeB{vJ5#$dwUU$1Pm;#A&TNG`>R4OBrAlWk9;C+}$n*H6W=#x
mlJbvdV4$>Q$kAt_zODD>S;2-
@)97oSe!f&jf9MDhv2@lqEd*be%zBXetC$+3IMpSKt~SOCW~$1bNwR#%W#b^IXspIwK*oO@jLKn{+1Y238m9IUH|;C1Y7bOu3>ee
C3i>Dmb;0%~AomGzGx~v^G2mt*CuecCgQnAuoIOJor^#aoRm1;cQV-
r5Z|#xk*l*iO4g9*I+%=YdwPvnu!cSt<0GGXhdvd5Ilx)hp$ixzsC+ZQS?TJ(ocx4p8_0;Eip-|^Z=0oKs#w-
L^jzVdZPJOMWdOl>{@%=(gtZ)d@yOUY{u$%FRX%{_5Sm$KN+7~x_An{@$dI!_(M#!7e^R8>%r+0>)(;dL%zJo`?5FKE3yO{qwQZ@
?W5FAXyvm}yNwQ8oFR@KDq&DdP{OEo%PPom!;5l<F@ETeb%SHcugU`-%T^~0@>Ut+-
_beL<=IK7){RcCAzd9$E;JprmiwhK2cEJL&cMlPW2FKX57k*Ecz3Zao7{a|lq~ky63c{*lCls`+Yh)G6h6caSXly|gi-
=8KMZc}bV6g?$`%7e<5pSs>8}F!#g^QHd|tGuXyNzs;xMPWte#+H!7AD<C<+yuymeZ`;)!+@oSqoF<2|3*DPX3%Yc=x;uIx}2)vE
Y}W59r0G!<F7S^(;kw<xMxN33TmhNW{=8CU%k$nN(as)p%nOY4qb+B2Sq`fLwk`GP6&iu4tT%@!kbbd^tA!&DA4It&;vtATl;72T
^im!OsNDZ`*NB(=JD9&~LF`3|idDETV;=%m*dac0Jjtfos^t`5BxJXrRs(WOnDX6f(bv&)j($^nZ<!Sd^a=X%JT9nlt&b(q`j7V}
w}r?X~8VVuj-m<b8Ki;TO+fbIF7Ce!MTG0dV?*henuBjcAyx<q%#y2^&2oA5@#YmkBhBA&|`1>4`H-
ET0xcp0R*csU{)gY}49>Y3LY*t)z9TbE(=!T|O!>Ik)++fKWDX;MMF$8Z+E2oyKq?(^$N;8NuE7`@H|l3``8BC`u{>$y$%-
{wZ^>Uc#+n){a|%MIyUu=EE0Jg<jBJF}0vuTx<z->#Gkl#=R>e%}~*&p@H}=;*wR9QkL?kLs}9S9c%~liR}MXyk-
J<kM}S;F)}20Ctj~!on6RY6sZTha48DsXqI_^xgX1vQFcD7^4z?<g&69BlTxQbbQ(YU2YnQR#(z!St6oE2aD@CC(9w6>VO_$@D4h
Q3Qt?YqV_z8QNCg|4|il}qI0FgH!xao>EgNpQ=L^O?x`jidUle7eNT4tvYZXI!Mt}Vs=MSNG0#C1q@paF7FAmB%_vOPH7)Y&7}|d
OW{^E;Hg={xZ&cJRuzP@zCbHZ9o1BK}_Soc&#Y-uf-
DPiZnxKzkHe8kxGx5`^Gn&fNKpH0Hih(~`(9sw1=@Q%*sGWJ#bmv%|mgQe-rd^qZ@)=oe%W8-
RWKO7GZr3%QYTH&Dh)x(1M;V*#CQKb3K1pNSYt7kIz2v$9TmzHygoG&7j9KRl(wfh3J{`7eJ<{oXQ?QrXgPBuRzANSW{<7|Q*@Kr
0Od}=AjUDDGwxU^)PdUzV)dA>s;<)+KuGAa^b{|BntdS>RL}Vbt=~)RI0PiZY(Gxj8)CPt!f&~(%cue~gCZ#}sV?Z{2DO#{FoXX8
XvA<03UpG0vO<R?hzQL0TOEX9htA4OJ6KEfs$w9q@43(GNNH8Q$d)1*K?3oWkfuw;LDJ8b}s6QCt$<C)E=lIi37Rh`drYJsLDST|
%RgUX)Rjw5KLO9Iq)<kQ<AD}qWC&<bFLy5F1Jf>8(&X4tXF!e>G4GQWb4&FUz&xsHb2lAVWL}|IZ6JQxQ4#woiW&uMl&8NZGwdb0
RjmvZA<XMO+?_H8MB7x|tiUx;XkJY(WK>1IZ*pT7}r~^n1W$#j05*_)@k*Dz!9Dk%&Bu|kQE(%H}Z0E2OxVQnfR~8KQLkV))ni@{
5wF6l=DZZ_9l<LIm5{B*O!Yll+<u?nqj>EdE`loK{S=~;#V^&vZEDb^(D^Q9p5vAVU4y<{=rB}SO_T%2rhMTwRzUiSsS`ZwtEb9m
-sCx<}upMeY$u<y?%FQB=?g}~&U(N|se<_sIo#hOIVZ<!Qt`0#x3;Wa*B(|QZTBO`ohn7S?%H)GA+F3L+lRs)vKM~_=X0Qw-
y4qrTRH@iEC<Qcku$9=+FCaiq!WAqb5er1-^OHQfm}BFy<D-MowA?dDp|JD0Q~z6m5dWz_)c$Z9$sRp2qceVM0^XEjF``sDnNp-l
seTVv4A#B}P)h*<6ay3h000O8001Fea|GvIT>t<8U;qFB6#xJL0000000000q=5hc003}kVRL0OY++(AUtei%X>?y-
E^v8JO928D0~7!N00;m803lr5-r9vO0000k0000U00000000000001_fsg<I0B~qwb7eDZVPY?Ea&Ky7V{~&bUtei%X>?y-
E^v8JO928D0~7!N00;m803lphz4;7N000180000S00000000000001_f%*Ud0B~qwb7eDZVPY?HXkl_?WG`P|X>MtBUtcb8c~DCM
0u%!j000080000XT>t#(=Y|LX09qRW03QGV00000000000HlG30RRASXkl|@Gi+gEFLP*Na%E&MXmoUNUt?@(Wo~pXaCuNm0Rj{Q
6aWAK2mk;8AzX1$1uwY;005{H000{R0000000000005+cN(uk~aA;w3WixDHVlQ)OVRB_;FK}#OZf<3AE^v8JO928D0~7!N00;m8
03lqOTh6n@2mk;L7XSbn00000000000001_fjkfZ0B~qwb7eDZVPY?HXkl_?WG`}cZf<3AE^v8JO928D0~7!N00;m803lq?<kYdN
3jhE-A^-
p<00000000000001_fjAie0B~qwb7eDZVPY?Ea&Ky7V{~&ba4<DrW^83;bYF06VQy|^axQRrP)h{{000002LJ~E3<3ZEC?x;@000""".replace("\n", ""))
_MODULE = 'phase3lab.projects.p05_fleet_planner'


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
