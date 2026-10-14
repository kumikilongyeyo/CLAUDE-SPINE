/*TEMPLATE {"name": "energy_payline", "doc": "Slot payline energy beam on a straight strip, to bend along any winning line with ae_fx_along_path (corners=\"sharp\", baseline=0.5, ends=pad, parts from this result; feather ~0.03). White-hot core with a long dim tail, soft irregular aura whose edges wave, pieces of aura that peel off and dissipate, glowing embers, a head knot; energy streams from the head back along the trail. theme red: swirling ribbon strands; theme blue: the lightning template's strike (leader, return stroke + flash, restrikes) instead of swirls. Timeline: draw-on 0-0.35 s, loop 0.6-2.6 s (exact, every motion has a 2 s period), fade 2.6-3.0 s. Colours: core / hot / glow / ember / strand override the theme. For sharp corners render it twice and bend two meshes on one rig: layers=\"core\" (height ~192, small weight_window) and layers=\"aura\" (default height, weight_window ~1.6x its half height, then rig= the first). The comp keeps every control on 00_CONTROLS and its route on 01_PATH, so it also works as a full-screen payline comp. Needs the JavaScript expression engine. Additive.", "params": {"theme": "red", "layers": "all", "width": 2048, "height": 384, "fps": 30, "pad": 120, "core": "", "hot": "", "glow": "", "ember": "", "strand": ""}} */
// Ported from the payline_energy job (vfx recipe/payline_energy/ae/build_payline.jsx): the same rig, on a strip.
var THEMES = {
    red: { dir: 2, crackle: 0, wisp: 50,
        flow: -1, rnd: 1, puffs: true, tails: [0.62, 0.62, 0.66, 0.7], coreTaper: 72, coreOp: 78, coreBand: 0.8,
        op: { haze: 20, auraW: 40, auraM: 58 }, blur: { haze: 85, auraW: 42, auraM: 14 }, turbW: [24, 130],
        colors: { "Core Color": [1, 1, 1], "Hot Color": [1, 0.36, 0.56], "Glow Color": [1, 0.04, 0.14], "Ember Color": [1, 0.9, 0.78], "Strand Color": [1, 0.72, 0.84] } },
    blue: { dir: 2, crackle: 0, wisp: 50, swirls: false, recipeBolts: true,
        flow: -1, rnd: 1, puffs: true, tails: [0.62, 0.62, 0.66, 0.7], coreTaper: 72, coreOp: 78, coreBand: 0.8,
        op: { haze: 20, auraW: 40, auraM: 58 }, blur: { haze: 85, auraW: 42, auraM: 14 }, turbW: [24, 130],
        colors: { "Core Color": [0.92, 0.98, 1], "Hot Color": [0.3, 0.82, 1], "Glow Color": [0.05, 0.45, 1], "Ember Color": [0.82, 0.96, 1], "Strand Color": [0.62, 0.92, 1] } }
};
var TH = THEMES[P.theme];
if (!TH) throw new Error("theme must be one of: " + "red, blue");


// the comp's expressions use the JavaScript engine (default since AE 16); never switch an artist's project silently
if (app.project.expressionEngine !== "javascript-1.0")
  throw new Error("energy_payline needs File > Project Settings > Expressions > JavaScript");
var cmap = { core: "Core Color", hot: "Hot Color", glow: "Glow Color", ember: "Ember Color", strand: "Strand Color" };
for (var ck in cmap) if (P[ck]) TH.colors[cmap[ck]] = AEFX.rgb(P[ck]);
var W = P.width, H = P.height, FPS = P.fps, DUR = 3.0;
var comp = AEFX.comp(P.comp || "energy_payline", W, H, FPS, DUR);
var STRIP = [[P.pad, Math.round(H / 2)], [W - P.pad, Math.round(H / 2)]];

// ---------- library (evaluated by every expression) ----------
var LIB = [
"var _C=thisComp.layer('00_CONTROLS');var TP=2;",
"function cv(n){return _C.effect(n)(1).value;}",
"function PL(){var L=thisComp.layer('01_PATH');var a=L.content('Line').content('Path 1').path.points();var o=[];for(var i=0;i<a.length;i++)o.push(L.toComp(a[i]));",
"var d=Math.round(cv('Direction'));if((d==1&&o[0][0]<o[o.length-1][0])||(d==2&&o[0][0]>o[o.length-1][0]))o.reverse();return o;}",
"function GEO(P){var L=[0];for(var i=1;i<P.length;i++){var dx=P[i][0]-P[i-1][0],dy=P[i][1]-P[i-1][1];L.push(L[i-1]+Math.sqrt(dx*dx+dy*dy));}return {P:P,L:L,T:L[L.length-1]};}",
"function AT(G,s){var P=G.P,L=G.L,n=P.length;s=Math.max(0,Math.min(G.T,s));var i=1;while(i<n-1&&L[i]<s)i++;var l=L[i]-L[i-1]||1;var f=(s-L[i-1])/l;var a=P[i-1],b=P[i];return [a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,(b[0]-a[0])/l,(b[1]-a[1])/l];}",
"function NRM(G,s,R){var a=AT(G,s-R),b=AT(G,s+R),c=AT(G,s);var tx=a[2]+b[2]+c[2],ty=a[3]+b[3]+c[3];var m=Math.sqrt(tx*tx+ty*ty)||1;return [-ty/m,tx/m,tx/m,ty/m];}",
"function FADE(){return Math.max(0,Math.min(1,cv('Fade')/100));}",
"function FL(k,a){return 1-a+a*(0.5+0.25*Math.sin(2*Math.PI*k*time/TP)+0.25*Math.sin(2*Math.PI*(k*3+1)*time/TP+k));}",
"function STEP(){return Math.floor(time*15+0.001);}",
// own RNG: AE's seedRandom mixes the layer into the seed, so copies on different layers would not line up
"function RNG(seed){var t=seed>>>0;return function(a,b){t=(t+0x6D2B79F5)>>>0;var r=Math.imul(t^(t>>>15),1|t);r^=r+Math.imul(r^(r>>>7),61|r);var x=((r^(r>>>14))>>>0)/4294967296;if(a===undefined)return x;if(b===undefined)return x*a;return a+x*(b-a);};}",
// life cycle with loop-safe lengths (every life length divides 2 s; the seed repeats every 2 s)
"function LIFE(k,salt,LS){var R=RNG(k*7919+salt);var Lf=LS[Math.floor(R(LS.length))];var off=R(Lf);var tt=time+off;var c=Math.floor(tt/Lf);var age=tt/Lf-c;var per=Math.round(TP/Lf);return {age:age,R:RNG(salt*31+k*977+((c%per)+per)%per+101),Lf:Lf};}",
"function EMB(k){var X=LIFE(k,13,[0.5,2/3,1,1]),R=X.R;return {u:R(0.03,0.97),age:X.age,side:R()<0.5?-1:1,d0:R(8,58),dr:R(14,50),rot:R(-30,30),sz:R(0.7,1.5),al:(cv('Energy Flow')<0?-R(15,70):R(-30,30)),up:R(4,22)};}",
"function ARC(k){var X=LIFE(k,500,[1,1,2/3,2]),R=X.R,F=cv('Energy Flow');var o={age:X.age,u:R(-0.05,0.85),len:R(300,600),dist:R(260,560)*X.Lf,A:R(0.65,1.35),turns:R(0.35,0.95),th:R(0,6.283),tw:(R()<0.5?-1:1)*R(0.6,1.6),F:F};",
"if(F<0){o.u=1-Math.pow(R(),1.4)*0.75;o.dist=-R(220,480)*X.Lf;o.tw=-Math.abs(o.tw);}return o;}",
"function BPART(k){var X=LIFE(k,777,[1/3,0.5,2/3]),R=X.R;return {u:R(0.02,0.98),age:X.age,side:R()<0.5?-1:1,d0:R(10,40),dr:R(20,70),rot:R(0,360),sz:R(0.7,1.4),al:R(-40,40)};}",
// a closed band round the drawn line: tail taper, round head, both edges carry waves that travel toward the head
"function BAND(G,S,Wd,amp,lam,k,ph,tail){S=Math.max(2,S);var n=Math.max(4,Math.ceil(S/8)),A=[],B=[];for(var i=0;i<=n;i++){var s=S*i/n,p=AT(G,s),q=NRM(G,s,50);",
"var e=Math.pow(Math.min(1,s/(tail*G.T+1)),0.9)*Math.sqrt(Math.max(0,Math.min(1,(S-s)/(Wd*0.5+1))));",
"var w1=Wd*0.5*e*(1+amp*WV(s,lam,k,ph)),w2=Wd*0.5*e*(1+amp*WV(s,lam*1.37,k,ph+2.1));",
"A.push([p[0]+q[0]*w1,p[1]+q[1]*w1]);B.push([p[0]-q[0]*w2,p[1]-q[1]*w2]);}return A.concat(B.reverse());}",
"function WV(s,lam,k,ph){var F=cv('Energy Flow'),r=cv('Aura Randomness'),A=Math.sin(2*Math.PI*(s/lam-k*F*time/TP)+ph);if(r<=0)return A;",
"var B=Math.sin(2*Math.PI*(s/(lam*0.47)-2*k*F*time/TP)+ph*1.7),C=Math.sin(2*Math.PI*(s/(lam*2.3)-F*time/TP)+ph*0.6),D=Math.sin(2*Math.PI*(s/(lam*0.71)-3*k*F*time/TP)+ph*2.9);",
"return (1-r)*A+r*1.25*(0.45*A+0.3*B+0.35*C*(0.6+0.4*D));}",
"function key_t(){var p=_C.effect('Draw')(1);return p.numKeys?p.key(p.numKeys).time:0;}"
].join("\n");
var EV = "var _s=thisComp.layer('00_LIB').text.sourceText.value;eval(typeof _s=='string'?_s:_s.text);\n";
var DRAWN_PATH = EV + "var G=GEO(PL());createPath(G.P,[],[],false);";

// ---------- helpers ----------
function fx(layer) { return layer.property("ADBE Effect Parade"); }
function addEffect(layer, match, name) { var e = fx(layer).addProperty(match); if (name) e.name = name; return fx(layer).property(e.name); }
function setP(layer, effName, propName, v) { fx(layer).property(effName).property(propName).setValue(v); }
function exprP(layer, effName, propName, e) { fx(layer).property(effName).property(propName).expression = e; }
function ctlColor(n) { return "thisComp.layer('00_CONTROLS').effect('" + n + "')('Color')"; }
function shapeLayer(name) {
    var l = comp.layers.addShape(); l.name = name;
    l.property("ADBE Transform Group").property("ADBE Position").setValue([0, 0]);
    return l;
}
function vec(l) { return l.property("ADBE Root Vectors Group"); }
// one stroke group: path (expression) -> trim -> stroke
function strokeGroup(l, gname, pathExpr, o) {
    var g = vec(l).addProperty("ADBE Vector Group"); g.name = gname;
    var gv = function () { return vec(l).property(gname).property("ADBE Vectors Group"); };
    gv().addProperty("ADBE Vector Shape - Group");
    gv().property(1).property("ADBE Vector Shape").expression = pathExpr;
    if (o.trim) {
        var t = gv().addProperty("ADBE Vector Filter - Trim");
        t = gv().property(t.name);
        if (o.trim.start) t.property("ADBE Vector Trim Start").expression = o.trim.start;
        t.property("ADBE Vector Trim End").expression = o.trim.end;
    }
    var s = gv().addProperty("ADBE Vector Graphic - Stroke");
    s = gv().property(s.name);
    s.property("ADBE Vector Stroke Color").expression = ctlColor(o.color);
    s.property("ADBE Vector Stroke Width").expression = o.width;
    s.property("ADBE Vector Stroke Line Cap").setValue(2);   // round cap
    s.property("ADBE Vector Stroke Line Join").setValue(o.join || 2);  // round join: sharp payline corners stay clean
    if (o.taper) {
        var tp = s.property("ADBE Vector Stroke Taper");
        tp.property("ADBE Vector Taper Start Length").setValue(o.taper[0]);
        tp.property("ADBE Vector Taper End Length").setValue(o.taper[1]);
        tp.property("ADBE Vector Taper Start Width").setValue(o.taper[2]);
        tp.property("ADBE Vector Taper End Width").setValue(o.taper[3]);
        if (o.taper.length > 4) { tp.property("ADBE Vector Taper Start Ease").setValue(o.taper[4]); tp.property("ADBE Vector Taper End Ease").setValue(o.taper[5]); }
    }
    // NOTE: no Stroke > Wave here. Its Phase does not repeat at 360 deg (measured), so it breaks the loop; BAND() does the waves.
    return g;
}
// one filled band group (wavy aura body)
function bandGroup(l, gname, wd, amp, lam, k, ph, tail, colorName) {
    var g = vec(l).addProperty("ADBE Vector Group"); g.name = gname;
    var gv = function () { return vec(l).property(gname).property("ADBE Vectors Group"); };
    gv().addProperty("ADBE Vector Shape - Group");
    gv().property(1).property("ADBE Vector Shape").expression = EV +
        "var G=GEO(PL()),S=G.T*cv('Draw')/100;createPath(BAND(G,S," + wd + "*cv('Width')," + amp + "," + lam + "," + k + "," + ph + "," + tail + "),[],[],true);";
    gv().addProperty("ADBE Vector Graphic - Fill");
    gv().property(2).property("ADBE Vector Fill Color").expression = ctlColor(colorName);
    return g;
}
function blur(l, amt) { addEffect(l, "ADBE Gaussian Blur 2", "Blur"); setP(l, "Blur", "Blurriness", amt); setP(l, "Blur", "Repeat Edge Pixels", 0); }
function turb(l, amount, size, revs) {
    addEffect(l, "ADBE Turbulent Displace", "Wisp");
    var e = fx(l).property("Wisp");
    e.property("Amount").setValue(amount); e.property("Size").setValue(size);
    e.property("Complexity").setValue(2.2);
    e.property("Pinning").setValue(1);
    e.property("Cycle Evolution").setValue(1);
    e.property("Cycle (in Revolutions)").setValue(revs);
    fx(l).property("Wisp").property("Evolution").expression = "time*" + revs + "*360/2";
}
function opac(l, e) { l.property("ADBE Transform Group").property("ADBE Opacity").expression = EV + e; }

// ---------- path, library and controls first: expressions set before these exist get disabled ----------
var pathL = shapeLayer("01_PATH");
var pg = vec(pathL).addProperty("ADBE Vector Group"); pg.name = "Line";
vec(pathL).property("Line").property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Group");
var shp = new Shape(); shp.vertices = STRIP; shp.closed = false;
vec(pathL).property("Line").property("ADBE Vectors Group").property(1).property("ADBE Vector Shape").setValue(shp);
vec(pathL).property("Line").property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Stroke");
vec(pathL).property("Line").property("ADBE Vectors Group").property(2).property("ADBE Vector Stroke Color").setValue([0, 1, 1]);
pathL.enabled = false; pathL.guideLayer = true;
pathL.comment = "Edit Line > Path 1 vertices to re-route the payline. Keep segments straight (no bezier handles). Do not move/scale this layer. Flow direction: 00_CONTROLS > Direction.";

var libL = comp.layers.addText(LIB); libL.name = "00_LIB"; libL.enabled = false; libL.guideLayer = true;
libL.comment = "Shared expression library. Do not edit unless you know what you are doing.";
var ctrl = comp.layers.addNull(); ctrl.name = "00_CONTROLS";
function slider(n, v) { addEffect(ctrl, "ADBE Slider Control", n); setP(ctrl, n, "Slider", v); }
function color(n, c) { addEffect(ctrl, "ADBE Color Control", n); setP(ctrl, n, "Color", c); }
slider("Draw", 100); slider("Fade", 100); slider("Width", 1); slider("Wisp Amount", TH.wisp);
slider("Direction", TH.dir);   // 0 = as drawn, 1 = always flows right -> left, 2 = always left -> right
slider("Crackle", TH.crackle);
slider("Energy Flow", TH.flow);        // 1 = waves/swirls/pulses run toward the head, -1 = they stream back from the head toward the tail
slider("Aura Randomness", TH.rnd);     // 0 = even waves on the aura edge, 1 = irregular (unrelated wave sizes)
slider("Glow Strength", 100); slider("Ember Amount", 100); slider("Pulse Amount", 100); slider("Head Amount", 100);
if (TH.recipeBolts) slider("Lightning Amount", 100);
for (var cn in TH.colors) color(cn, TH.colors[cn]);

// timing: draw-on 0-0.35 s (fast start, eased landing), glow flash settles by 0.6, loop 0.6-2.6, fade 2.6-3.0
function keys(n, tv, easeIn) {
    var p = fx(ctrl).property(n).property("Slider");
    for (var i = 0; i < tv.length; i++) p.setValueAtTime(tv[i][0], tv[i][1]);
    for (var j = 1; j <= p.numKeys; j++) p.setTemporalEaseAtKey(j, [new KeyframeEase(0, easeIn || 33)], [new KeyframeEase(0, 33)]);
}
keys("Draw", [[0, 0], [0.35, 100]], 70);
fx(ctrl).property("Draw").property("Slider").setTemporalEaseAtKey(1, [new KeyframeEase(0, 33)], [new KeyframeEase(0, 5)]);
keys("Glow Strength", [[0.25, 100], [0.38, 165], [0.6, 100]]);
keys("Fade", [[2.6, 100], [3.0, 0]]);

// ---------- layers (created bottom-up; each new layer goes on top) ----------

// 06 haze: wide, soft light under everything
var haze = shapeLayer("06_HAZE");
bandGroup(haze, "G", 150, 0.3, 420, 2, 0.0, TH.tails[0], "Glow Color");
blur(haze, TH.blur.haze); haze.blendingMode = BlendingMode.ADD;
opac(haze, TH.op.haze + "*cv('Glow Strength')/100*FADE()*FL(1,0.25)");

// 05 aura wide: the energy body; wavy edges travel toward the head, turbulence adds breakup (cycles every 2 s)
var auraW = shapeLayer("05_AURA_WIDE");
bandGroup(auraW, "G", 96, 0.45, 260, 3, 1.0, TH.tails[1], "Glow Color");
turb(auraW, TH.turbW[0], TH.turbW[1], 1); blur(auraW, TH.blur.auraW); auraW.blendingMode = BlendingMode.ADD;
opac(auraW, TH.op.auraW + "*cv('Glow Strength')/100*FADE()*FL(2,0.3)");

// 05 aura drift (puffs theme): soft pieces of aura that peel off the beam, drift outward with the flow and dissipate
if (TH.puffs) {
    var NPF = 12;
    var puffLayer = shapeLayer("05_AURA_DRIFT");
    for (var pi = 0; pi < NPF; pi++) {
        var pg2 = vec(puffLayer).addProperty("ADBE Vector Group"); pg2.name = "Puff " + pi;
        var pv = function () { return vec(puffLayer).property("Puff " + pi).property("ADBE Vectors Group"); };
        pv().addProperty("ADBE Vector Shape - Group");
        pv().property(1).property("ADBE Vector Shape").expression = EV +
            "var X=LIFE(" + pi + ",1200,[1,2/3,2]),R=X.R,a=X.age,F=cv('Energy Flow'),G=GEO(PL()),S=G.T*cv('Draw')/100;" +
            "var u0=F<0?1-Math.pow(R(),1.2)*0.95:R(0.05,0.95),len=R(170,380),wd=R(34,80)*cv('Width'),side=R()<0.5?-1:1,drift=R(20,60),trav=R(90,280)*X.Lf;" +
            "var sc=u0*G.T+F*trav*a-len/2,n=24,A=[],B=[];" +
            "for(var i=0;i<=n;i++){var u=i/n,s=Math.max(0,Math.min(S,sc+len*u)),p=AT(G,s),q=NRM(G,s,50);" +
            "var off=side*(wd*0.25+drift*Math.pow(a,0.8)),w=wd*0.5*Math.sin(Math.PI*u)*(0.6+0.8*a);" +
            "var cx=p[0]+q[0]*off,cy=p[1]+q[1]*off;A.push([cx+q[0]*w,cy+q[1]*w]);B.push([cx-q[0]*w,cy-q[1]*w]);}" +
            "createPath(A.concat(B.reverse()),[],[],true);";
        pv().addProperty("ADBE Vector Graphic - Fill");
        pv().property(2).property("ADBE Vector Fill Color").expression = ctlColor("Glow Color");
        vec(puffLayer).property("Puff " + pi).property("ADBE Vector Transform Group").property("ADBE Vector Group Opacity").expression = EV +
            "var X=LIFE(" + pi + ",1200,[1,2/3,2]),R=X.R,a=X.age,F=cv('Energy Flow'),u0=F<0?1-Math.pow(R(),1.2)*0.95:R(0.05,0.95);" +
            "100*Math.min(1,a/0.25)*Math.pow(1-a,1.3)*(u0<=cv('Draw')/100?1:0)";
    }
    turb(puffLayer, 30, 60, 1); blur(puffLayer, 22); puffLayer.blendingMode = BlendingMode.ADD;
    opac(puffLayer, "80*cv('Glow Strength')/100*FADE()");
}

// 04 aura mid: tighter hot layer with its own faster waves
var auraM = shapeLayer("04_AURA_MID");
bandGroup(auraM, "G", 40, 0.35, 170, 4, 2.0, TH.tails[2], "Hot Color");
turb(auraM, 6, 40, 2); blur(auraM, TH.blur.auraM); auraM.blendingMode = BlendingMode.ADD;
opac(auraM, TH.op.auraM + "*cv('Glow Strength')/100*FADE()*FL(3,0.25)");

// 03 swirls: ribbon arcs that peel off the beam, wrap round it (side flips = swirl) and ride the flow,
// thick in the middle and tapered at both ends. Each arc is reborn at a new spot every life (loop-safe).
// Crackle > 0 adds an electric jitter that re-rolls 15 times a second.
var NA = 11;
function arcExpr(k) {
    return EV + "var R=ARC(" + k + "),G=GEO(PL()),S=G.T*cv('Draw')/100,a=R.age,n=44,pts=[],CR=cv('Crackle');\n" +
        "var J=RNG(" + k + "*7+(STEP()%30)*1000+3);var s0=R.u*G.T+R.dist*a-R.len*0.5,A=cv('Wisp Amount')*R.A*(R.F<0?0.35+0.85*a:1);\n" +
        "for(var i=0;i<=n;i++){var u=i/n,s=Math.max(0,Math.min(S,s0+R.len*u)),p=AT(G,s),q=NRM(G,s,40);" +
        "var e=Math.pow(Math.sin(Math.PI*u),1.2)*Math.max(0,Math.min(1,s/120))*Math.max(0,Math.min(1,(S-s)/80));" +
        "var d=A*e*Math.cos(R.th+2*Math.PI*(R.turns*u+R.tw*a))+CR*e*J(-1,1);pts.push([p[0]+q[0]*d,p[1]+q[1]*d]);}\n" +
        "createPath(pts,[],[],false);";
}
function swirlLayer(name, colorName, widthMul) {
    var l = shapeLayer(name);
    for (var i = 0; i < NA; i++) {
        strokeGroup(l, "Arc " + i, arcExpr(i), { color: colorName, width: EV + (3.4 * widthMul) + "*cv('Width')", taper: [45, 45, 0, 0, 55, 55], join: 2 });
        vec(l).property("Arc " + i).property("ADBE Vector Transform Group").property("ADBE Vector Group Opacity").expression =
            EV + "var R=ARC(" + i + "),a=R.age,T=GEO(PL()).T,uc=R.u+R.dist*a/T,tf=R.F<0?Math.pow(Math.max(0,Math.min(1,(uc-0.1)/0.5)),1.3):1;" +
            "100*tf*Math.min(1,a/0.2)*Math.min(1,(1-a)/0.3)*(R.u*T<T*cv('Draw')/100?1:0)";
    }
    l.blendingMode = BlendingMode.ADD;
    return l;
}
if (TH.swirls !== false) {
var strG = swirlLayer("03_SWIRLS_GLOW", "Hot Color", 3.2);
blur(strG, 7); opac(strG, "100*FADE()");
var str = swirlLayer("03_SWIRLS", "Strand Color", 1);
blur(str, 0.9); opac(str, "100*FADE()*FL(4,0.15)");
}

// 03 recipe bolts: the CLAUDE-SPINE `lightning` template's strike (ADBE Lightning on a black ADD solid: a thin jittering
// stepped leader, then the return stroke snaps wide + branchy with an air-glow flash, branches die first, 2 restrikes),
// each bolt struck along a stretch of the beam near the head and streaming back with the flow. Speed 0 + seed-only
// motion keeps it loop-safe (the effect's own Speed animation does not repeat).
if (TH.recipeBolts) {
    var NBL = 6;
    var BCOM = function (k) {
        return EV + "var k=" + k + ",X=LIFE(k,3000,[2/3,1,1,2]),R=X.R,a=X.age,tl=a*X.Lf,F=cv('Energy Flow'),G=GEO(PL()),S=G.T*cv('Draw')/100;" +
            "var u0=F<0?1-Math.pow(R(),1.3)*0.85:R(0.05,0.95),len=R(130,260)*cv('Width'),side=R()<0.5?-1:1,sh=R(4,16),dr=R(40,140),sd=Math.floor(R(0,900));" +
            "var c=u0*G.T+F*dr*a,s1=Math.max(0,Math.min(S,c-len/2)),s2=Math.max(0,Math.min(S,c+len/2));if(F<0){var sw=s1;s1=s2;s2=sw;}" +
            "var LEAD=0.08,ST=[LEAD,LEAD+R(0.11,0.18),LEAD+R(0.3,0.42)],si=-1;for(var j=0;j<3;j++)if(tl>=ST[j])si=j;var dt=si<0?0:tl-ST[si];" +
            "var uc=c/G.T,tf=F<0?Math.pow(Math.max(0,Math.min(1,(uc-0.1)/0.5)),1.3):1,on=u0<=cv('Draw')/100?1:0;" +
            "function PT(s){var p=AT(G,s),q=NRM(G,s,40);return [p[0]+q[0]*side*sh,p[1]+q[1]*side*sh];}\n";
    };
    var boltLayer = function (k, flash) {
        var l = comp.layers.addSolid([0, 0, 0], (flash ? "03_BOLT_FLASH " : "03_BOLT ") + k, W, H, 1);
        var lt = fx(l).addProperty("ADBE Lightning"); lt.name = "Bolt";
        var e = function () { return fx(l).property("Bolt"); };
        e().property("Segments").setValue(9);
        e().property("Amplitude").setValue(9);
        e().property("Core Width").setValue(0.16);
        e().property("Speed").setValue(1);   // min is 1; seam checked after render
        e().property("Start point").expression = BCOM(k) + "PT(s1)";
        e().property("End point").expression = BCOM(k) + "var A0=PT(s1),B0=PT(s2),f=Math.max(0.12,Math.min(1,tl/LEAD));[A0[0]+(B0[0]-A0[0])*f,A0[1]+(B0[1]-A0[1])*f]";
        e().property("Random Seed").expression = BCOM(k) + "si<0?sd+(STEP()%30):sd+100+si*7";
        e().property("Width").expression = BCOM(k) + "var wm=11*cv('Width');si<0?wm*0.3:wm*(1-0.5*Math.min(1,dt/0.15))*(si==0?1:0.8)";
        e().property("Branching").expression = BCOM(k) + "si<0?0.02:0.16*(si==0?1.5:1)*Math.max(0.1,1-dt/0.08)";
        e().property("Outside Color").expression = ctlColor("Hot Color");
        e().property("Inside Color").expression = ctlColor("Core Color");
        if (flash) {
            blur(l, 34);
            opac(l, BCOM(k).replace(EV, "") + "30*on*tf*(si<0?0:Math.max(0,1-dt/0.06))*(si==0?1:0.6)*cv('Lightning Amount')/100*FADE()");
        } else {
            var gl = fx(l).addProperty("ADBE Glo2"); gl.name = "Glow";
            fx(l).property("Glow").property("ADBE Glo2-0002").setValue(55);
            fx(l).property("Glow").property("ADBE Glo2-0003").setValue(12);
            fx(l).property("Glow").property("ADBE Glo2-0004").setValue(1.2);
            opac(l, BCOM(k).replace(EV, "") + "var o=si<0?42*tl/LEAD:(si<2?100-45*Math.min(1,dt/0.06):100*Math.max(0,1-dt/0.3)*(1-0.45*Math.min(1,dt/0.06)));" +
                "o*on*tf*cv('Lightning Amount')/100*FADE()");
        }
        l.blendingMode = BlendingMode.ADD;
        return l;
    };
    for (var bk = 0; bk < NBL; bk++) { boltLayer(bk, true); boltLayer(bk, false); }
}

// 02 core: hot body (wavy band) + white-hot centre with a long tapered tail
var coreH = shapeLayer("02_CORE_HOT");
bandGroup(coreH, "G", 18, 0.25, 160, 3, 0.5, TH.tails[3], "Hot Color");
blur(coreH, 4); coreH.blendingMode = BlendingMode.ADD;
opac(coreH, "100*Math.pow(FADE(),1.5)");
var coreW = shapeLayer("02_CORE_WHITE");
// coreBand > 0: the white centre is a band whose width ramps up over that fraction of the line, so the tail fades to nothing
if (TH.coreBand) bandGroup(coreW, "G", 9, 0.08, 200, 2, 0.3, TH.coreBand, "Core Color"); else
strokeGroup(coreW, "G", DRAWN_PATH, { color: "Core Color", width: EV + "10*cv('Width')", trim: { end: EV + "cv('Draw')" }, taper: [TH.coreTaper, 2, 0, 85, 60, 0] });
blur(coreW, 3); coreW.blendingMode = BlendingMode.ADD;
opac(coreW, TH.coreOp + "*Math.pow(FADE(),2)*FL(5,0.12)");


// 02 pulses: white comets riding the line toward the head
var pul = shapeLayer("02_PULSES");
var PU = [[1, 0.0], [1, 0.5], [2, 0.27]];
for (var i = 0; i < PU.length; i++) {
    var u = "var D=cv('Draw');var u=((time*" + PU[i][0] + "/TP+" + PU[i][1] + ")%1)*1.25-0.1;if(cv('Energy Flow')<0)u=1.12-u;";
    strokeGroup(pul, "Pulse " + (i + 1), DRAWN_PATH, {
        color: "Core Color", width: EV + "7*cv('Width')",
        trim: { start: EV + u + "Math.max(0,Math.min(1,u-0.12))*D", end: EV + u + "Math.max(0,Math.min(1,u))*D" },
        taper: TH.flow < 0 ? [0, 100, 100, 0] : [100, 0, 0, 100]
    });
}
blur(pul, 3); pul.blendingMode = BlendingMode.ADD;
opac(pul, "90*cv('Pulse Amount')/100*Math.pow(FADE(),2)");

// 07 embers: eye-shaped sparks (red) or sharp shards (blue) born along the drawn line, drifting out (loop-safe)
var NE = 26;
function embersLayer(name, colorName, sizeMul) {
    var l = shapeLayer(name);
    var eye = new Shape();
    {
        eye.vertices = [[0, -15], [4.6, 0], [0, 15], [-4.6, 0]];
        eye.inTangents = [[0, 0], [0, -7.5], [0, 0], [0, 7.5]];
        eye.outTangents = [[0, 0], [0, 7.5], [0, 0], [0, -7.5]];
    }
    eye.closed = true;
    var K = "var k=parseInt(thisProperty.propertyGroup(2).name.split(' ')[1]);var E=EMB(k);var D=cv('Draw')/100;var on=(E.u<=D&&k<" + NE + "*cv('Ember Amount')/100)?1:0;";
    for (var i = 0; i < NE; i++) {
        var g = vec(l).addProperty("ADBE Vector Group"); g.name = "E " + i;
        g = vec(l).property("E " + i);
        g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Group");
        g = vec(l).property("E " + i);
        g.property("ADBE Vectors Group").property(1).property("ADBE Vector Shape").setValue(eye);
        g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
        g = vec(l).property("E " + i);
        g.property("ADBE Vectors Group").property(2).property("ADBE Vector Fill Color").expression = ctlColor(colorName);
        var tr = function () { return vec(l).property("E " + i).property("ADBE Vector Transform Group"); };
        tr().property("ADBE Vector Position").expression = EV + K +
            "var G=GEO(PL()),s=E.u*G.T,p=AT(G,s),q=NRM(G,s,30);var a=1-Math.pow(1-E.age,2);var d=E.side*(E.d0+E.dr*a);" +
            "[p[0]+q[0]*d+q[2]*E.al*E.age, p[1]+q[1]*d+q[3]*E.al*E.age-E.up*E.age]";
        tr().property("ADBE Vector Rotation").expression = EV + K +
            "var G=GEO(PL()),p=AT(G,E.u*G.T);Math.atan2(p[3],p[2])*180/Math.PI+90+E.rot";
        tr().property("ADBE Vector Scale").expression = EV + K +
            "var a=E.age,pop=a<0.12?a/0.12:1-0.7*Math.pow((a-0.12)/0.88,1.5);var s=100*" + sizeMul + "*E.sz*pop*on;[s,s]";
        tr().property("ADBE Vector Group Opacity").expression = EV + K +
            "100*Math.min(1,E.age/0.08)*Math.pow(1-E.age,0.8)*on";
    }
    l.blendingMode = BlendingMode.ADD;
    return l;
}
// three soft passes of the same embers: wide halo, hot body, small white-hot centre
var emG = embersLayer("07_EMBERS_HALO", "Glow Color", 1.6);
blur(emG, 9); opac(emG, "100*Math.sqrt(FADE())");
var emM = embersLayer("07_EMBERS_BODY", "Hot Color", 1.15);
blur(emM, 3.5); opac(emM, "100*Math.sqrt(FADE())");
var em = embersLayer("07_EMBERS_CORE", "Ember Color", 0.75);
blur(em, 1.6); opac(em, "100*Math.sqrt(FADE())");


// 08 head: bright knot riding the draw-on tip, then resting on the line end and pulsing
var HEADPOS = EV + "var G=GEO(PL()),p=AT(G,G.T*cv('Draw')/100);[p[0],p[1]]";
// settles to 0.55 exactly at the loop start (draw ends 0.35 s, 0.25 s x 1.8 = 0.45) so the loop has no pop
var HEADOP = "var D=cv('Draw');var settle=D<100?1:Math.max(0.55,1-(time-key_t())*1.8);";
function headLayer(name, size, colorName, b, op) {
    var l = shapeLayer(name);
    var g = vec(l).addProperty("ADBE Vector Group"); g.name = "G";
    vec(l).property("G").property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Ellipse");
    vec(l).property("G").property("ADBE Vectors Group").property(1).property("ADBE Vector Ellipse Size").expression = EV + "var s=" + size + "*cv('Width');[s,s*0.8]";
    vec(l).property("G").property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
    vec(l).property("G").property("ADBE Vectors Group").property(2).property("ADBE Vector Fill Color").expression = ctlColor(colorName);
    var T = l.property("ADBE Transform Group");
    T.property("ADBE Position").expression = HEADPOS;
    T.property("ADBE Rotate Z").expression = EV + "var G=GEO(PL()),p=AT(G,G.T*cv('Draw')/100);Math.atan2(p[3],p[2])*180/Math.PI";
    blur(l, b); l.blendingMode = BlendingMode.ADD;
    // bright while drawing, settles to a pulsing knot once the line is complete (constant from the loop start on)
    opac(l, HEADOP + op + "*settle*(0.85+0.15*Math.sin(2*Math.PI*3*time/TP))*cv('Head Amount')/100*Math.pow(FADE(),1.5)");
    return l;
}
var headG = headLayer("08_HEAD_GLOW", 90, "Glow Color", 28, 85);
var headH = headLayer("08_HEAD_HOT", 30, "Hot Color", 7, 100);
var headW = headLayer("08_HEAD_CORE", 13, "Core Color", 2.5, 100);


pathL.moveToBeginning(); libL.moveToBeginning(); ctrl.moveToBeginning();
comp.markerProperty.setValueAtTime(0, new MarkerValue("intro"));
comp.markerProperty.setValueAtTime(0.6, new MarkerValue("loop start (seamless 2 s)"));
comp.markerProperty.setValueAtTime(2.6, new MarkerValue("outro"));
comp.workAreaStart = 0; comp.workAreaDuration = DUR;

// layers: "core" keeps the sharp line (core, pulses, swirls / bolts, head), "aura" the wide soft light (haze, aura,
// drifting puffs, embers); bend each with its own ae_fx_along_path mesh (the aura one with a big weight_window)
if (P.layers !== "all") {
  var KEEP = { core: ["02_", "03_", "08_"], aura: ["04_", "05_", "06_", "07_"] }[P.layers];
  if (!KEEP) throw new Error("layers must be all, core or aura");
  for (var li = 1; li <= comp.numLayers; li++) {
    var ln = comp.layer(li).name, pre = ln.substr(0, 3);
    if (pre === "00_" || pre === "01_") continue;
    var on = false; for (var kk = 0; kk < KEEP.length; kk++) if (pre === KEEP[kk]) on = true;
    comp.layer(li).enabled = on;
  }
}
var f0 = Math.round(0.6 * FPS), f1 = Math.round(2.6 * FPS), fN = Math.round(DUR * FPS) - 1;
return AEFX.done(comp, '"mode":"additive","baseline":0.5,"ends":' + P.pad + ',"parts":[{"name":"in","frames":[0,' + (f0 - 1) + '],"mode":"once"},' +
  '{"name":"loop","frames":[' + f0 + ',' + (f1 - 1) + '],"mode":"loop"},{"name":"out","frames":[' + f1 + ',' + fN + '],"mode":"once"}]');
