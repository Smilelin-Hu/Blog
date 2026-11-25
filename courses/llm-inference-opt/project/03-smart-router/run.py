#!/usr/bin/env python3
"""Standalone entry for project-03-smart-router; no external project library is required."""
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
?0|XQR000O8001Fej>{)PVFdsH$PWMj8vp<RaA;w3WixDHVlQ)OVRB_;FLG~nbZKs9E^v8`S5a@<HV}T-
uORd!rHbcdORyPpu|0Gz1NP7idoc`wmZ+F5C3+&&#LfKQcRZ4!C_8P6wwCUW$Gh+DK2m9#K4_|0GYHblLG$jB9D3ez&A%{32E}T!
JEDs9M9`fgw5tj4G<)n}T@BXq6RWgZq-mNYO)pzgmd&7to|Prx?Lqb$)^rlK;j&Xn;$(ZO_JZ&1lA3B-
391xq>er~6SGowQf;60o+Ah$?gNfDI{@xvvB>8PLP4Iv6p{oxPV#O3!34uQyZP|(_-
Q(NPi}2FQnh6E(Om9H8MPWq`wBq`>GC7kqxk2fkQK9!B+({`w`gcDtRPe45{Bf_n`4Xk<simcW7`p0Mwy;GbBt>rvYtT?G05BCVQ
$tlT14%5VH9bHzCXs>)p~-
62&_U?3p_P{XaSaA}f{Q>yJ}KE{iisvC*YAlz*Q_oKdRvQ*`SXQ}fq_ShzqOB*o76&;nvE6U&uTPVSn-
*)5BSX9E5eGNLF06GAym|s@u8)?{)jDT!-
Q6QU;?_%^k&1T;yW&&NCk8wYxpyvO~X4B=soL5C;OHP{uSC)KwlF;zqbAAp(#saUzQkGL6~bCz*umlH&G*P3vyMATa-
`C7Tni#x%lx8)Z(zGQ{nAh9x&z&#H1(Nj2Z-
ia>d9$27?cMFZ(QY^Vcy}tFS7~=MI<T*Y!LyBf9zC2J<!Tpa5J3fAtds1i!Lg;^fPYUEJ0t{I<Q&((k}Kk}V5zvz@rb<`~li_{Qh
hWFGZd?lW`Tcx^+CRkm+R`P4y=O-92_*UKq3uUW;FVKdhs@hq7Yn{8;WYA>Z?uC<_bdiL+YlrDLV<WpGYanCN2&+Lc-aFwQopZTe
XJy&9=Sv{eF|HxlZAJCg09P$ech=k<U8fg8a?2V%=RH1@;bD&gaDzJ%)>gz!oST(*tDdWmTYoJ%WV&V7`J8BdfYQ}Z~KVwwJ0^vc
aH?>3)FZa|7y*SD|dyj!^=dBx(ywtWIhfed>HExr3(lh^fE+7IJ&iVy^PLn>yb~2ndZ?VNAARQ{5n`pu-
f!r9@Fd1E$K2nwJS>}^l#l^*P>){~S21%zN?#FaSoSUJ)$xsF4ejqJ<&d$(-
>C9sX_9&bBm>qG>mHEdtYtPgMHKQ<94JF87CwBcyyqO<qkK=sk0Xm2Cde%z_<I)|mqdPlE<xX~kLT0|XGd`Rgd&)mgTh5<Vm%X}k
D?@1CA>EU!5vS{r#C05iDG%KVR%*_&zzap3Nj`s1rgQ}7AWm}2yDVT?5a^^ewoHCz9ZLSrUuoP-Oz0;{@T`S5!E$R$V?CSrULnf`
Jscp9>?QJ?hP2bwgd2<43Wo~}@OP#Qp@2bnnOQmD!Nfhy^ge}j6=yRu^VDR_>|Mr7@|opWj1tSBV8u&R$CbHQ10eBW=bI&5G4As-
at*~jg`G}kmnR?m<N%T_@PcNu+s%wY@N7D}r4~efw)b3Q7{f}FbL5Od);Rae;)3dWN+Yil$9j5JUrpkHvC3}1Nl@pYf6dRdry+rh
r`KY<V8>%HKdt=j+%U{Cb``nvXT#)s0QEo^uLLl9e%t=<*W~t1`~N{<&rpB3KYuQ**0sR+8C1mIGT*2%xb4`p&XCX}0-
s&iAavw><Y0izF&N%Sk_-
6}u4Y??1NcvNw1=;yy>F!Ko~9f4%)W!Y`L0S5JYX+zv4bfL4ZI>uI3Ct{%^$(oL}5Q_7iv#$@9yEs@Dd!IR^#-
aQoySMCd=}CVHdlLmz!Y>5WaKE-4Vt;vnHF>&p-
_6jz6Y39I)B#)z$q^cC7vfP)h>@6aWAK2mk;8AzYeU&a=b_000da000^Q003}kVRL0OY++(Ab7*05Wn?dMb#88DaxQRrrC3{UBu5
o~?_W_gveYAHdbJCfXp)JrvW~D~?^;<Cv>2;Z?yi}sxNoVd9(%AxiV#vHg2XeA2q7X~ct9c-
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
u%)o?{F)8D@qS&^JewhrQr`P)h>@6aWAK2mk;8AzV&jiGYCv004#x000{R003}kVRL0OY++(Ab7*05Wn?dOWo}_^V|gxcd7V{DkJ
~m7zUx;EbdpiWXs$-INRXzN7Aa6HdNB-vD~)%F$fQD1PTe&By)%4?a=ee!z+%PWJiqxkQ<mi|DxoZVp0pJp+E!1>N_7uHb#O<A4m
%K?7%UnvILZ!Hd)|~~SriAOkI*!S$xa5F2IO(j#*(EXUsh^02Ax*-J+@8~mHsdt8ti_NtzAQh2Ql@wqk}i-
gcWTs#u1Z25_t`K9yrTz`A(gSqHx!6t3RRo9lLup+XCoE-YH9|q-~mN#Qv~`ULK_#x4;p1qcv-
g%I;TQpMUZIR7B7NZK$YobrSuA@CIJPfh7JURZ!Zv^H{AiFZ?q?jtGD8<p*Q5sY>e+55AAnXyFcF(4(~SgykxkbFQ19R=Zp)f4We
iwxBs-cUcb`&B#_Hx-e`Xgt`A8c6dU?@bz-EyV;hyuxI1lzDU4_+yd^t^es4bgP#d7+sG~mEO(CFazJ=>L-f=Aq9p-
2?hN6c!E+7r-|*}KKa`XDr1Te+!hiK2-
!iP(y9>|#eXfJPC`a+9`X^38_TsKb!X!&}=cDi8)uIcR;@H(FpWU`C(sS&{YfQPGW91b^&1F4Ty~9t@+qG72#4w=hs;{Lxms<!JV
7Z1sXcGF5HDAWol5{?>u8YCC?t>&TNs`6SZ!?AlX}G9#GZSk>Yx|e+YJMM*vlFeIL_gE)qgJ?G!o~_jgrD8Z_otiL%`@x>2B9~RA
9rZKAS(C=jdsH|x?7U)dUM`98T?Nk*~b{(19PM{0sh@0b~L{xJ6ej#6Eov(`N$lZnOLW|R|iK<9$)nf$>VeUQSKzfwka*g9}eu;!
ym+*qIf%R3%?ZJ`3?4g6Yvm*o#rUw1P_u3#3RR@@I+$`J%iw1$C0#Qg0uIceZWUoOe+S_N_!5Z<2%W$b2F2i?t@o)#r$u%d!q46h
EZJ3$>zC@k`(J?bI~?sjYJy6*^>4Xo-
^eMpIub5cixII8=B9dWPU@t{gn}9_0&F8!C*DNY%ljH=3R1+_4`I<>pE&L5%UuyH;h5+k|;=huW!wS>)7+!^&|P9d#X6AE5|5l1>
4ZgJTd0g_r(YM%~7AQvAW?0lAuUV`w^G6<gZ6n<t|omQ!g94G|94CLlaj~j6di>T0B-nY+L^-
DB$YRWOpIK{biL;K^*>joat|dIs9K0{{c`-
0|XQR000O8001Fe%Wo#Ebp!wa%?tnl8~^|SaA;w3WixDHVlQ)OVRB_;FL!TpYiw^}WG--
dtyW8K<2De!`&Y0$NvW(&&>jk7y=c+yp+&J>ph0^u0)duBF&m0hNh-FR=D&AH>OsG<KGcUG;>>)U`DQpXl+r(#;1#n_kzaoQ?bEM
htMrpltTKejiZHGDGZS;RWg3WvR<M0eDV@z~tr}7kb!R&bML~GeDs9n7D$6Wa(#&T4S*c{%X${imLEQ|Jzl@T@|CTopP|+P$3T6z
L5!O_^wAmyInk};%!PkS<XZ#ETyKlLC9L|4``;7d^gkWm{v)SzX5hg+He?TtpbqDFpACW(ifuAijiy6V6hQB*7w&2x*7_0r+6PM9
fix;+b`fk{+kgzSRdID({giGtsdoGJ6oRKBD_2(8OlffR(XazOvgrxyXRUk$Y>#PdrtYWPNJxXZr3DkU7Ji-
1*z#H}mg=6bTPywq1mk>Gi%`N_By|nfzN(_iPCG!u&WnqN~nd9^!FcetAyvjaJK^=K^_O6x+2O^T`{(pU{Jfh&nt_I3`M9cIeIA5
HWH%mhpHNooY#W^=c%>^WB<Obsg2$pmQAGKCGsp(M9#OabsVNE#<*x|hk@)EFKX@3FwfJ7Yngnq0Zytr1Hc(!EMtN}^TY>TWBz;D
p_h?3qljkFdPb~XW7stQYSNjqE5zoThxTEVSDF-
e+{yU6=KJOs^=B;Ll6xgWkG%Vh`Sq1F3Cjb|4*`s?`4{VProEgf}WS3(<}UGARyPk`P9sxWs>e2903&w;VUOT@&hE1qZ9NqiTfDe
<om@h<!7xJFk8nv<Iw@BN9h_xtw$^)RXk5EZ8T1yNtm`TX4X#=`lUxIY=Wgij~OeHG=bZ9!Jv>Y#c<ja^l;90SJIvOld;Y|mJg4l
17-
l&?=uE7qjH=3%&4fK1RRC0{N5{|2o8e(UW_eneOJ92wGd#*#IVPI46WUiD4DV9SLNxXB1MqorWYx?<j?1@VG>YK9p(3L_m_$0_}b
v0O5;-GGL%oejQH-&8&+35#RWqbuH||HUI?!9-zWCfpa-
P|=fY=6)Vr1?e=u0M?I_tKfp}c|Z?#IE%=8a(5l@k=>B)RvB*jGaTJAB@=JBz3zs{ru0jL!<X>L&frH=>iQ63qci@85(^tma<=bh
#DJUg!{V@tMTdhB4{ow)&nfqQm}Y*bDNM-
(7HW;<>1Ntpemf1mBbc#fBd9M#Ok>r{d73;S@0V}ph(@Xx@C<e%w=pg~Y~F&di&AwGH<BcsRtHmVpz1{53#PaG<|a}30XE$5^+~%
R@5mi4D2~K;QB;#XU_ueW;mpta7meGX{2}JU&njnS1VEd3jmf6s2G@~tb0PF;9V(S}{FuWLFv(VQWT%*dqi)$a3i!lu@L|x`czu;
5qigely_DQ|t}^m%dc3Ixu#l@Qx0^FddVargd(3C0#K#?!xO?iv^##{zL7Qb%c&VGsEh<ht_8@LdIYDl^b;EHr9HI_wKfN@wB3D-
d3fs5Ay*LRb;mjHJ7d_1W15ir?1QY-
O00;m803lre=Uwo|3jhFVBLDy<0001RXkl|@Gi+gEFK}{iYGq?|b1!f(GhcIUVRCd|a&L8XWpXZXd97MsZ`{Taf4@($<x5C_N1fz
4Z4Y69pmhruhHKbq`yd<$irmxD;*m7Dw0sZ_P=W?XfCNE{=Al80AVFKd1PD?DaM9LZripFosb8Tpv%BOjbtgG#{o>o*+1c6o``e)
$$GKCN_jw}N<Qn_;>F-
%1V!`Ka&h9PaTClriD|pS0GqGR~+ET<mi|6yK$ixbM6)Bs?SzbQmb>KM8Xf&_OC5xhYE83bz5zCfU30&f$fUP1ci)J*^bM;{r*A3
U>Mcgd%>_89iH)WxJi$%@jG%F4z|0)(pshQt_p*pz&Cj43+9|X-
Ju6Y_Pgs7q<&v+p;c~UN`oTDs0OS2|H;iF}l^1Sicl8ZV^nutHlQeGr{3)>pB0^(?vH;S|>vqIcM-
T6{;QgPe%w?zS3RoidH2lpzT`0P&2ld?!N6z)b{m$lD;66N2*NAMypl9gukW_iSmTRc77dhl^sALV77>K(s^@lC;(KEv4vm7c?)y
vpO%Xmsz+jUTg6%jb?5`~zlDmWECx-DW(wHg52~<C-q)_(UZ#k@L{-
t^fS%V;H1uf_GzY++;rkRUOAG@*&gJ6obPu&O_(<dymgPegDPdPoBT~<oulv&OiIp`Ded*@zEc?K7H%#t543JK0QBu@9fDJFa*`j
vq$WkfBfy)@7~AdFP=RA^6h6I{`UOzEf_xg^Ot8|{pHz*ADsX7T_E`8@2Af{|MdAs@0@@9$FrxOzj*x5uTS4rCxffyo&7`Cc^Kze
3c{vL-Vhw9m}iHM&zzJeS%de<OBz>o1~*yl)Zj%cVDzBnjbLchI&F}EB8cT=A;;6_J!mtqO_UW?D;hX47C;iiPH|i^u6&F3lf4Dg
R_s~+{N68aYla}DVnhNnQO5~KQXQ)OjAkyQzGv5P0rp#RJXUdylZ00ymOA0UWu>N2G3ut^Z7gP5EBZ(vP>NyvQIfYQZy=)KlHKW`
K~kC2AsJF98J0C&O2XxuH@to*Q;8B2CG<w4QOf5mPSXeyOG~1=lway;muiAH)Y2VV@YwiucDpS2lx`@g1Cxd8jFn%HJFCMnahr?K
0jG#}R2WRIMUpPS5OTcB7#h~w#!HhBxBPN;WU)(l(R%X|a*1ro$4wIF=m=s}@o)|@h@SIqFu9Zg8hfmbYDxsZ7d)>*2b|yttj$#n
L5)azFKCMegq~Qe*a4rHHCJiK(YD1JKpD!#0x$))s6A;p0a9=QnF>n*tx7qwIfJ^RmV>N`=HQL4+C;GzXAQrYcHOz71td>nxR0eJ
I4<(zkFrKg*@@)4R$2uQZtH^TR)Dr^Ty-wVE%+nhLPjaEjD=1s=Hnkap6BbbhY5P``m5HSgO%Wo>v_R~KT5Mhh%i^{g0gj&8VrS?
ON$l?+<p#1?pu{<<|D~WULVq0%dr9?Ur?Q`U3I1MxPc`i4L~f{>9diC+J!hT8cGUo$1f2cgIdZdvP?4=#K;&*4oK*+vW9F|(3Hns
V|zpE{0bRMvp7};W(DUdB%ICJQr@5&!!`D2GzG4O7h_pL_cM-Di5N&voFZOQK5T1BI}#t@uOzPG1QL_8?lvy7ra?3ivIc4@Pu-
5w7>@{!_zKO~(SttJmj3XK_nqqtcQFFlP;X@?ulVeh;6BW|YR=QXXk9&ss|p6L<qNKLGTt@>-#{zu%e&81-q-
&?5j_QJW#$DnOk|bo>^K8rsjd+6vx|GkH$2ij{ZzW&*J>S}rF9&FwDQ1C>qF8wjiCh9SDq!^S5t!__h+8L%Igva`r=6jkSIVk5FZ
>Nn@*!^k9{vB%5JLjW4RX;^zvIT^Z3s4C{06X>6dqJffuyk@dq4|W(Kv_PC*@K9o{NwKwU*x?m~)bjG}lOIfHsRB@YbX>BZQwoyV
ys7z>E5r#m||IB^oF>CW2kt+xm1ZMbjO+_$@J-%O<+a{kZ+)UI(kjS-
?_o*gbkI0=3r^)SzBnbTxRP8Ma^a95!eLa*@{&nEW^r2syY$RmPih4myU+d_<Ety#rMz8$zrCqM>+O9B3lmQA?3H}P3{6#g`Z+-
Hap=%N-fTGEE9S62x*)|lvJ#Pl_`O2ZR*E;`J5v-HH+lKw|h_&4iT$u2P}h-
kbi+!Fwx@e)p(vfar<G4D`ds5S)>qk***HCSBg`}-
4<c_882CNiJxUAJ8NL}P0>y1yRbK|z!Bzn)C9`JC5)O1cthZNmt(=m{c4`XWH9e;OFS!9%1TyD3;!SbnPS1jrbpyoW6Lw+=U7)wc
*B0V>rl^~f!df<%%|DoWl#Rbe@h`}@L9TWQJLQkN|zvXny-Ln344vUDY%4+NJeLoMTqsYlDrp8)JHSyeUwv>w8<1RV=7z%uKq^=7
BTtPbApO&OL0BfrC>-zRxP!T{4Qlw9SZ-J>@&Ub#{mdP%#oXyNfEs}jP1b%z-G3T))pUK4UBY#DSEx^#sV!5fe(n*ELj-Ejs?<nj
i5(NQW9$M^(tCHc$Zi%n?v#1diMLtP4F6RpdGE%2d0kH#P!2mvuj$M`Jh9JrTAJq<&EaR7~7s+1c`CIQW^Acx@wu25(YZCWZ&`~f
lbPrU7pJ9xd|Hj0g6@ap#l@^4P>-?eb%WpV`Dx_(!13nmcs<02-M27w$ZW7@TD25CelO=-
7K>TMZ6iVA)lQN%SJ74`J+L|Zr8^Eok-
(d<jkeZ}(ip`OJ|r5MfAKFP}OJu6727nrNghhEY`IM^C!F*U0kUUPi)a_WqfM=(!DLBhO@s<>&4saOE3O5oJ~Y;8%V`xTc|=nEps
DlHX`Kdnkl)BV`jxK%EwL9aT}WD0Dx2^9rX@gYwb4aALPrwR7-
Jx*7xVgB)ZzRG@84TRd5www6OxGZFd!F|^|x*&U3In)q+sEro>ux}9bD+EghtL2fANtF>1qk<EaIY(#EvKcKdnAWQ3paXL2=QVq(
mEL;RM|xIJZnx=110TO2q^$*j8yCHQi^h!LxZDXh*~LbU|BFAGn9|hU+8b?@bff=Cp!I+EK6y*;TWj=6By8Sf=!e#t>4igY)KBi-
BfI{l;g1#u?Yz-CMET;yleABo)D{t#4pJ_=3(tdWDXScd8=RhgC$W)%Lp>%Jc$gw}*k=h~faD5f3tHI{lh&lK4^*2a)sbuzO|Hry
_Iu%_%8<{7s0c0w0wH9;MoqhP)vaY`K&c<zqiavj^tOlDiA0=g3&H}eGjB93WtQld*EO4TV~w*(D3UdW3~QS}g{~&ik!%z7fv@R|
RA7_#1y)9{bJ2XN$?ptyQu)=CL#}-_?s#Eq!?4k7s`90Pgz~K57=t#Go)~RJuQTx7eij~*-
cUPz$=5%7iuFjnIO%f@#TNFTUHwMz34PJ)ENSZ+og*YDYE1YHqb;H?x?JqXp8h(6kF8V!`V(p8sd~nsk7>{D9yT@#OZDRh4M8+(j
kXQe!#A3l1_1B3g^Z<CzM7c%RRyrU!AOI7{q2Yft;+M%NtHhlCo8?F9-
2yEvhAkTF57PGb+&8tVml7q8Pf|*%t*Gs;A|^uyJUJHJSErt{^%LKM>cPsnYG;P&B<dy;E?TU2Q?P<Co_DH3?_GHn;sjM1^Q2Mm|
!!ogII7j{8-k>C;J2HlVk+76g5HKWlmzA-M_s1I2&zDR8HS;*t`BJ1V=ya!^7#C3X-N98YDVYdaA+a4f;T1zr449>o6Ew4`yo67-
NG@e`}p;cQn_q_D7fYb4F%zkv5fIMyE=%vL0_y?gd@RX3(%XWRR&pH$e8ozdUfUVL%6=HSrwN{xeHA`pYcv8C0J*&m%LqBNg{RiI
~+0^g*W74jNH|k*)y6T?gneubPi9rCY49ItWz}p<o$4)HY|4;Q^}nT*6kDr>oel<xkzATgDk0)cO#t{^r8PKY#G;Ps%>E^nBe)$I
o$)G9rrnC?Y|k2zf@4BbmtqM*js+O928D0~7!N00;m803lp+1m|5{0001B0000L00000000000001_fdBvi0B~qwb7eDZVPY>|Uu
kY>bYEXCaCuNm0Rj{Q6aWAK2mk;8Aza+v+J!Cv001rk0015U0000000000005+ckN^MxaA;w3WixDHVlQxVZ)#;@baO9XUukY>bY
EXCaCuNm0Rj{Q6aWAK2mk;8AzWC!`3zG4003P8000~S0000000000005+c`Tzg`aA;w3WixDHVlQ)OVRB_;FJE72ZfSI1UoLQYP)
h*<6ay3h000O8001Fe|NQCah6n%vS{ncW9{>OV0000000000q=AP4003}kVRL0OY++(Ab7*05Wn?dCbaZfEV{B<<Zgehic~DCM0u
%!j000080000XT#m~pLSY2}0LTvj02=@R00000000000HlFR3IG6bXkl|@Gi+gEFLP*Na%E&Ma&L8XX>MmOaCuNm0Rj{Q6aWAK2m
k;8AzYeU&a=b_000da000^Q0000000000005+c<PQJ<aA;w3WixDHVlQ)OVRB_;FLHHmZe?;VaCuNm0Rj{Q6aWAK2mk;8AzV&jiG
YCv004#x000{R0000000000005+c;1~b^aA;w3WixDHVlQ)OVRB_;FLY&YVQyo2E^v8JO928D0~7!N00;m803lq<ZzimD1ONcd3;
+Ne00000000000001_ftnlu0B~qwb7eDZVPY?HXkl_?WG{Dba%*gFVPr0Fc~DCM0u%!j000080000XT>s}?@Wu-
O0BIut044wc00000000000HlFQApihyXkl|@Gi+gEFK}{iYGq?|b1!f(GhcIUVRCd|a&L8XWpXZXc~DCQ1^@s600{sI0G<K>08=d
h0000""".replace("\n", ""))
_MODULE = 'phase3lab.projects.p03_smart_router'


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
