/* ================================================================
   绘卷水浒 · 全站统一背景音乐
   ----------------------------------------------------------------
   一首曲子贯穿「书页 → 长卷 → 人物页」：全站唯一曲目 audio/bgm.mp3
   （堂前燕 改编 · 笛子版「牵丝戏」纯音乐）。

   翻页不断的关键：把「播到第几秒 + 存下的时刻」写进 localStorage，
   下一页按「离开到回来的这段时间」把进度往前推，接上它本该播到的位置。
   所以甲 → 乙 → 首页之间来回走，曲子的时间是往前走、不是从头再来。

   开关：localStorage.jssh_bgm      = on | off       （全站共用，关掉就一直安静）
   进度：localStorage.jssh_bgm_pos  = {"t":秒,"at":毫秒时间戳}

   本文件自己创建音频元素与右下角浮标，各页只需：
       <script src="music.js"></script>
   页面里不再各自放 <audio> 与音乐区。
   ================================================================ */
(function(){
  /* 在外壳（shell.html）的 iframe 里：音乐由外壳那一层统一负责，
     本层不再自建音频与浮标，否则会变成两份声音叠着放。
     但要帮外壳一个忙：读者点按的是本层页面，事件传不到外壳 window；
     而线上空间（github.io 等陌生域名）没有自动播放特权，曲子只能静音起播、
     等「读者第一次动手」才开声——所以本层把点按/按键如实上报给外壳。 */
  try{
    if(window.self !== window.top){
      var tell = function(){ try{ window.parent && window.parent.__jsshGesture && window.parent.__jsshGesture(); }catch(e){} };
      ['pointerdown','keydown','touchstart'].forEach(function(ev){ addEventListener(ev, tell, {passive:true}); });
      return;
    }
  }catch(e){ return; }

  if(window.__jsshBgm)return;           /* 同一页被引两次也不重复初始化 */
  window.__jsshBgm = true;

  var SRC = 'audio/bgm.mp3';
  /* v3 键名：线上初版（修复前）可能把「止乐=off」误存进读者浏览器，
     换掉键名等于全站重新来过，不被旧状态闷住 */
  var K_ON = 'jssh_bgm_v3', K_POS = 'jssh_bgm_pos_v3';
  var LS = {
    get: function(k, d){ try{ var v = localStorage.getItem(k); return v === null ? d : v; }catch(e){ return d; } },
    set: function(k, v){ try{ localStorage.setItem(k, v); }catch(e){} }
  };

  /* ---------- 音频：全站唯一的一轨 ---------- */
  var audio = document.createElement('audio');
  audio.loop = true;
  audio.preload = 'metadata';
  audio.src = SRC;
  audio.setAttribute('aria-hidden', 'true');
  audio.style.display = 'none';
  (document.body || document.documentElement).appendChild(audio);

  /* ---------- 右下角浮标：全站唯一的音乐开关 ---------- */
  var btn = document.createElement('button');
  btn.className = 'bgm off';
  btn.id = 'bgmBtn';
  btn.hidden = true;
  btn.setAttribute('aria-label', '背景音乐开关');
  btn.title = '笛子版「牵丝戏」· 堂前燕 改编（纯音乐）';
  btn.innerHTML = '<span class="bars"><i></i><i></i><i></i></span><span id="bgmLbl">启卷</span>';
  (document.body || document.documentElement).appendChild(btn);
  var lbl = btn.querySelector('#bgmLbl');

  var want = LS.get(K_ON, 'on') !== 'off';   /* 读者此前止过乐就一直安静 */
  var armed = false, lastSaveAt = 0;

  /* ---------- 手势总线：外壳自己窗口的点按 + iframe 里上报上来的点按，都算数 ----------
     读者实际点的是 iframe 里的书页，DOM 事件传不到外壳 window；
     iframe 里的 music.js 分身会把「动手了」通过 __jsshGesture 报上来。 */
  var gestureFns = [];
  function onGesture(fn){
    var evs = ['pointerdown','keydown','touchstart'], done = false;
    function off(){
      if(done) return; done = true;
      evs.forEach(function(ev){ removeEventListener(ev, fire); });
      var i = gestureFns.indexOf(fire); if(i > -1) gestureFns.splice(i, 1);
    }
    function fire(e){ if(!done) fn(e, off); }
    evs.forEach(function(ev){ addEventListener(ev, fire, {passive:true}); });
    gestureFns.push(fire);
    return off;
  }
  window.__jsshGesture = function(){
    gestureFns.slice().forEach(function(f){ f(); });
  };

  function label(t){ btn.hidden = false; lbl.textContent = t; }
  function state(on){ btn.hidden = false; btn.classList.toggle('on', on); btn.classList.toggle('off', !on); lbl.textContent = on ? '止乐' : '启卷'; }

  /* ---------- 进度：存 / 取（翻页接续的核心） ---------- */
  function savePos(){
    if(audio.currentTime > 0.5) LS.set(K_POS, JSON.stringify({ t: audio.currentTime, at: Date.now() }));
  }
  function restorePos(dur){
    try{
      var r = JSON.parse(LS.get(K_POS, 'null'));
      if(!r || typeof r.t !== 'number') return;
      var s = r.t + (Date.now() - (r.at || Date.now())) / 1000;   /* 离开这段时间，曲子本也走到了这里 */
      if(dur > 0) s = s % dur;
      if(s > 0.5) audio.currentTime = s;
    }catch(e){}
  }

  /* 有声自动播放被拦时：立刻改为「静音起播」——浏览器一律放行，
     曲子从进门那一刻就在走；读者第一次点按/按键时取消静音，
     听感上就是「一进来音乐就在放」，无需去按浮标。
     点按无论落在外壳窗口还是 iframe 书页里，都经手势总线开声。 */
  function startMuted(){
    audio.muted = true;
    audio.play().then(function(){
      onGesture(function(e, off){ audio.muted = false; off(); });
    }).catch(armGesture);   /* 连静音都被拦（极少见）→ 退回首次点按起播 */
  }

  /* 自动播放被拦时：读者第一次点按/按键就接着起播（只在「本来就想放」时武装） */
  function armGesture(){
    if(armed) return; armed = true; btn.hidden = false; label('点按开乐');
    onGesture(function(e, off){
      if(e && e.target && e.target.closest && e.target.closest('#bgmBtn')) return;   /* 点浮标本身：交给它自己的 click，免得刚起播又被按停 */
      audio.muted = false;   /* 关键：muted 可能还挂着（静音起播失败时挂上的），有意起播必须先开声 */
      audio.play().then(off).catch(function(err){   /* 起播成功才撤哨；被拦则把原因亮在浮标上，便于排查 */
        lbl.textContent = '仍被拦:' + (err && err.name || '?');
      });
    });
  }

  audio.addEventListener('loadedmetadata', function(){
    restorePos(audio.duration || 0);
    if(want){
      var p = audio.play();
      if(p && p.catch) p.catch(startMuted);   /* 有声被拦 → 静音起播，首次交互时开声 */
    } else {
      label('启卷');
    }
  });
  audio.addEventListener('play', function(){ state(true); });
  audio.addEventListener('pause', function(){ state(false); });
  audio.addEventListener('error', function(){ btn.hidden = true; });   /* 无曲目：不出现任何音乐 UI */

  audio.addEventListener('timeupdate', function(){
    var n = Date.now();
    if(n - lastSaveAt > 3000){ lastSaveAt = n; savePos(); }            /* 每 3 秒记一次，翻页才有得接 */
  });

  btn.addEventListener('click', function(e){
    e.stopPropagation();
    if(audio.paused){
      audio.muted = false;   /* 关键：起播前先开声——曾被静音起播挂过 muted 的话，不放哑剧 */
      audio.play().then(function(){ want = true; LS.set(K_ON, 'on'); }).catch(function(err){
        lbl.textContent = '被拦:' + (err && err.name || '?');   /* 诊断：把浏览器拒绝的原因直接亮出来 */
        armGesture();
      });
    }else{
      audio.pause(); savePos(); want = false; LS.set(K_ON, 'off');
    }
  });

  /* 离开页面前把进度落盘：pagehide / beforeunload / 切到后台 三条都兜住 */
  addEventListener('pagehide', savePos);
  addEventListener('beforeunload', savePos);
  addEventListener('visibilitychange', function(){ if(document.hidden) savePos(); });
})();
