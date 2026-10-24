/* shared helpers for the per-project identity scripts (no dependencies) */
(function(){'use strict';
var d=document,R=d.documentElement;
var FX=window.FX={
 reduce:!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches),
 $:function(s,c){return(c||d).querySelector(s)},
 $$:function(s,c){return Array.prototype.slice.call((c||d).querySelectorAll(s))},
 mouse:{x:-1e3,y:-1e3,px:.5,py:.5},
 /* add .rv and reveal on scroll */
 reveal:function(sel,cls){cls=cls||'in';var els=FX.$$(sel);els.forEach(function(e){e.classList.add('rv')});
  if(FX.reduce||!('IntersectionObserver' in window)){els.forEach(function(e){e.classList.add(cls)});return}
  var io=new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add(cls);io.unobserve(x.target)}})},{rootMargin:'0px 0px -6% 0px'});els.forEach(function(e,i){e.style.setProperty('--i',i%6);io.observe(e)})},
 /* canvas loop: sizes to its box, pauses offscreen / hidden tab; draw(ctx,w,h,t,dt,m) with m = mouse in canvas px */
 loop:function(cv,draw,o){o=o||{};var ctx=cv.getContext('2d'),w=0,h=0,dpr=1,raf=0,on=false,vis=true,last=0,t0=performance.now(),m={x:-1e3,y:-1e3,in:false};
  function size(){var r=cv.getBoundingClientRect();w=r.width;h=r.height;dpr=Math.min(o.dpr||2,window.devicePixelRatio||1);cv.width=Math.max(1,Math.round(w*dpr));cv.height=Math.max(1,Math.round(h*dpr));ctx.setTransform(dpr,0,0,dpr,0,0);if(o.resize)o.resize(w,h)}
  function fr(now){if(!on)return;var t=(now-t0)/1000,dt=Math.min(.05,(now-last)/1000||.016);last=now;ctx.setTransform(dpr,0,0,dpr,0,0);draw(ctx,w,h,t,dt,m);raf=requestAnimationFrame(fr)}
  function go(){if(on||FX.reduce||d.hidden||!vis)return;on=true;last=performance.now();raf=requestAnimationFrame(fr)}
  function stop(){on=false;cancelAnimationFrame(raf)}
  size();addEventListener('resize',function(){size();if(!on){ctx.setTransform(dpr,0,0,dpr,0,0);draw(ctx,w,h,0,0,m)}});
  var host=o.host||cv.parentElement;host.addEventListener('pointermove',function(e){var r=cv.getBoundingClientRect();m.x=e.clientX-r.left;m.y=e.clientY-r.top;m.in=true},{passive:true});host.addEventListener('pointerleave',function(){m.in=false;m.x=m.y=-1e3});
  if(FX.reduce){draw(ctx,w,h,o.still||2,0,m)}else{
   if('IntersectionObserver' in window)new IntersectionObserver(function(es){vis=es[0].isIntersecting;vis?go():stop()},{threshold:0}).observe(cv);else go();
   d.addEventListener('visibilitychange',function(){d.hidden?stop():go()});draw(ctx,w,h,0,0,m)}
  return{size:size,draw:function(){draw(ctx,w,h,(performance.now()-t0)/1000,0,m)},ctx:ctx};},
 /* create an absolutely positioned canvas as the first child of host */
 layer:function(host,cls){var cv=d.createElement('canvas');cv.className='fx '+(cls||'');cv.setAttribute('aria-hidden','true');cv.setAttribute('role','presentation');if(getComputedStyle(host).position==='static')host.style.position='relative';host.insertBefore(cv,host.firstChild);return cv},
 css:function(n){return getComputedStyle(R).getPropertyValue(n).trim()},
 rnd:function(a,b){return a+Math.random()*(b-a)},
 theme:function(){return R.getAttribute('data-theme')==='dark'?'dark':'light'}
};
addEventListener('pointermove',function(e){FX.mouse.x=e.clientX;FX.mouse.y=e.clientY;FX.mouse.px=e.clientX/innerWidth;FX.mouse.py=e.clientY/innerHeight},{passive:true});
R.classList.add('fxjs');
})();

(function(){var hero=FX.$('.hero');if(!hero)return;var cv=document.createElement('canvas');cv.className='homes';cv.setAttribute('aria-hidden','true');hero.insertBefore(cv,hero.firstChild);
var par=[],st=[],lit=[0,0];for(var i=0;i<90;i++)st.push([Math.random(),Math.random()*.7,Math.random()*6.3,.3+Math.random()*.9]);
function house(c,x,y,s,D,warm,on){var body=D?'#050c2a':'#2b2f66',win=on?'rgba(255,196,60,'+(.7+.3*warm)+')':(D?'rgba(255,196,60,.35)':'rgba(255,255,255,.45)');
 c.fillStyle=body;c.beginPath();c.rect(x-60*s,y-70*s,120*s,70*s);c.fill();
 /* dome */ c.beginPath();c.moveTo(x-42*s,y-70*s);c.bezierCurveTo(x-42*s,y-130*s,x+42*s,y-130*s,x+42*s,y-70*s);c.closePath();c.fill();
 c.fillRect(x-1.5*s,y-150*s,3*s,24*s);c.beginPath();c.arc(x,y-152*s,4*s,0,6.3);c.fill();
 /* minaret-ish towers */ c.fillRect(x-76*s,y-96*s,12*s,96*s);c.fillRect(x+64*s,y-96*s,12*s,96*s);c.beginPath();c.moveTo(x-80*s,y-96*s);c.lineTo(x-70*s,y-116*s);c.lineTo(x-60*s,y-96*s);c.fill();c.beginPath();c.moveTo(x+60*s,y-96*s);c.lineTo(x+70*s,y-116*s);c.lineTo(x+80*s,y-96*s);c.fill();
 /* arched windows + door */ c.fillStyle=win;[-36,-12,12,36].forEach(function(dx){c.beginPath();c.arc(x+dx*s,y-44*s,6*s,Math.PI,0);c.lineTo(x+dx*s+6*s,y-30*s);c.lineTo(x+dx*s-6*s,y-30*s);c.fill()});
 c.beginPath();c.arc(x,y-18*s,9*s,Math.PI,0);c.lineTo(x+9*s,y);c.lineTo(x-9*s,y);c.fill()}
hero.addEventListener('pointerdown',function(e){if(e.target.closest('a,button,.map,.inst'))return;var r=cv.getBoundingClientRect(),dir=(e.clientX-r.left)<r.width/2?0:1;launch(dir,1)});
function launch(d,n){for(var i=0;i<n;i++)par.push({u:-i*.08,d:d,sp:.16+Math.random()*.05,h:.8+Math.random()*.4})}
var nxt=0;
FX.loop(cv,function(c,w,h,t,dt,m){var D=FX.theme()==='dark';c.clearRect(0,0,w,h);var s=Math.max(.45,Math.min(1,w/1100)),by=h-6,xl=w*.07,xr=w*.93;
 /* sky glow */ var g=c.createLinearGradient(0,h*.35,0,h);g.addColorStop(0,'rgba(255,179,0,0)');g.addColorStop(1,D?'rgba(255,150,0,.28)':'rgba(255,170,60,.45)');c.fillStyle=g;c.fillRect(0,h*.35,w,h*.65);
 /* stars */ if(D)st.forEach(function(q){c.globalAlpha=.4+.6*Math.abs(Math.sin(t*q[3]+q[2]));c.fillStyle='#fff3c9';c.fillRect(q[0]*w,q[1]*h,1.6,1.6)});c.globalAlpha=1;
 var mx=w<700?w*.9:w*.5,my=w<700?26:h*.14;/* moon crescent */ c.fillStyle=D?'#ffe9a8':'#f6a800';c.beginPath();c.arc(mx,my,16,0,6.3);c.fill();c.fillStyle=D?'#07123a':'#f6e8c6';c.beginPath();c.arc(mx+7,my-3,14,0,6.3);c.fill();
 /* arc path */ var ax=function(u,d){var x0=d?xr:xl,x1=d?xl:xr;return{x:x0+(x1-x0)*u,y:by-120*s-Math.sin(u*Math.PI)*h*.46}};
 c.setLineDash([3,7]);c.strokeStyle=D?'rgba(255,200,80,.35)':'rgba(150,90,0,.4)';c.lineWidth=1.2;c.beginPath();for(var u=0;u<=1.001;u+=.02){var p=ax(u,0);u?c.lineTo(p.x,p.y):c.moveTo(p.x,p.y)}c.stroke();c.setLineDash([]);
 if(t>nxt){nxt=t+2.4;launch(Math.random()<.5?0:1,2)}
 /* parcels */ for(var i=par.length-1;i>=0;i--){var q=par[i];q.u+=q.sp*dt;if(q.u>=1){lit[1-q.d]=1;par.splice(i,1);continue}if(q.u<0)continue;var p=ax(q.u,q.d),sz=7;
  c.save();c.translate(p.x,p.y);c.rotate(Math.sin(t*3+i)*.25);c.fillStyle=D?'#ffc933':'#c27a00';c.shadowColor='#ffb300';c.shadowBlur=D?16:6;c.fillRect(-sz,-sz*.7,sz*2,sz*1.4);c.fillStyle=D?'#07123a':'#fff6df';c.fillRect(-sz,-1,sz*2,2);c.fillRect(-1,-sz*.7,2,sz*1.4);c.restore()}
 lit[0]*=.96;lit[1]*=.96;
 house(c,xl,by,s,D,lit[0],true);house(c,xr,by,s,D,lit[1],true);
 /* ground */ c.fillStyle=D?'#050c2a':'#2b2f66';c.fillRect(0,by,w,6);
 /* labels */ c.font='700 12px Vazirmatn,sans-serif';c.fillStyle=D?'rgba(255,230,160,.85)':'rgba(40,30,90,.85)';c.textAlign='center';c.fillText('GitHub',xl,by-160*s-8);c.fillText('داخلی · mirrors',xr,by-160*s-8);c.textAlign='left';
},{still:2.2,dpr:1.5,host:hero});
})();
