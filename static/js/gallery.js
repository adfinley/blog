(function () {
  var lb = document.createElement('div');
  lb.className = 'lb';
  lb.innerHTML = '<button class="lb-btn lb-close" aria-label="Close">✕</button>' +
    '<div class="lb-stage"><button class="lb-btn lb-prev" aria-label="Previous">←</button><img alt="">' +
    '<button class="lb-btn lb-next" aria-label="Next">→</button></div>' +
    '<div class="lb-cap"><div class="cap-row"><span class="c1"></span><span class="c2"></span></div><div class="dots"></div></div>';
  document.body.appendChild(lb);
  var q = function (s) { return lb.querySelector(s); };
  var img = q('img'), stage = q('.lb-stage'), c1 = q('.c1'), c2 = q('.c2'), dots = q('.dots'), prev = q('.lb-prev'), next = q('.lb-next');
  var list = [], date = '', loc = '', i = 0, moved = false;
  var sc = 1, tx = 0, ty = 0;
  var canHover = window.matchMedia && window.matchMedia('(hover: hover)').matches;

  // ---- zoom helpers (pinch / double-tap / pan on touch) ----
  function applyT() { img.style.transform = (sc === 1 && !tx && !ty) ? '' : 'translate(' + tx + 'px,' + ty + 'px) scale(' + sc + ')'; }
  function clampT() {
    var mx = (sc - 1) * img.offsetWidth / 2, my = (sc - 1) * img.offsetHeight / 2;
    tx = Math.max(-mx, Math.min(mx, tx)); ty = Math.max(-my, Math.min(my, ty));
  }
  function resetZoom() { sc = 1; tx = ty = 0; img.style.transform = ''; }
  function easeT() { img.style.transition = 'transform .25s ease'; setTimeout(function () { img.style.transition = ''; }, 270); }

  // "Focus" mode hides everything but the photo. On desktop a portrait photo is shown at double width and scrolls.
  function setFocus(on) {
    var fw = img.getBoundingClientRect().width;
    lb.classList.toggle('zoom', on);
    img.style.width = img.style.height = img.style.maxWidth = img.style.maxHeight = img.style.flex = '';
    stage.classList.remove('scroll');
    stage.scrollTop = 0;
    if (on && canHover && img.naturalHeight > img.naturalWidth) {
      img.style.width = Math.min(fw * 2, window.innerWidth) + 'px';
      img.style.height = 'auto';
      img.style.maxWidth = img.style.maxHeight = 'none';
      img.style.flex = 'none';
      stage.classList.add('scroll');
    }
  }
  function dblTap(px, py) {
    easeT();
    if (sc > 1) { resetZoom(); return; }
    if (!lb.classList.contains('zoom')) lb.classList.add('zoom');
    var r = img.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    sc = 2.5; tx = (px - cx) * (1 - sc); ty = (py - cy) * (1 - sc);
    clampT(); applyT();
  }

  function show(n, dir) {
    if (sc !== 1) resetZoom();
    if (stage.classList.contains('scroll')) setFocus(false);
    var old = null, slide = dir && img.animate && lb.classList.contains('open');
    if (slide) {  // keep a copy of the outgoing photo so both slide across together
      var r = img.getBoundingClientRect();
      old = img.cloneNode();
      old.className = 'lb-old';
      old.style.cssText = 'left:' + r.left + 'px;top:' + r.top + 'px;width:' + r.width + 'px;height:' + r.height + 'px';
      lb.appendChild(old);
      img.style.opacity = 0;
    }
    i = (n + list.length) % list.length;
    var it = list[i];
    img.src = it.src;
    img.alt = it.alt || '';
    c1.textContent = [it.date || date, loc].filter(Boolean).join(' · ');
    c2.textContent = it.exif || '';
    var multi = list.length > 1;
    prev.style.visibility = next.style.visibility = multi ? 'visible' : 'hidden';
    dots.style.display = multi ? 'flex' : 'none';
    dots.innerHTML = list.map(function (_, k) { return '<i data-i="' + k + '" class="' + (k === i ? 'on' : '') + '"></i>'; }).join('');
    if (!slide) return;
    var W = window.innerWidth, opts = { duration: 600, easing: 'cubic-bezier(.22,.8,.3,1)' };
    var go = function () {
      img.style.opacity = '';
      img.animate([{ transform: 'translateX(' + dir * W + 'px)' }, { transform: 'none' }], opts);
      old.animate([{ transform: 'none' }, { transform: 'translateX(' + -dir * W + 'px)' }], { duration: opts.duration, easing: opts.easing, fill: 'forwards' })
        .onfinish = function () { old.remove(); };
    };
    if (img.decode) { img.decode().then(go, go); } else { go(); }
  }
  function close() { resetZoom(); setFocus(false); lb.classList.remove('open'); document.body.style.overflow = ''; }

  document.addEventListener('click', function (e) {
    var t = e.target.closest('.tile');
    if (!t) return;
    var post = t.closest('.post');
    list = JSON.parse(post.querySelector('.imgs').textContent);
    date = post.dataset.date || '';
    loc = post.dataset.loc || '';
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
    show(+t.dataset.i);
  });
  q('.lb-close').onclick = close;
  prev.onclick = function () { show(i - 1, -1); };
  next.onclick = function () { show(i + 1, 1); };
  img.onclick = function () { if (moved) { moved = false; return; } setFocus(!lb.classList.contains('zoom')); };
  dots.onclick = function (e) {
    if (e.target.dataset.i === undefined) return;
    var n = +e.target.dataset.i;
    if (n !== i) show(n, n > i ? 1 : -1);
  };
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    if (list.length > 1 && e.key === 'ArrowLeft') show(i - 1, -1);
    if (list.length > 1 && e.key === 'ArrowRight') show(i + 1, 1);
  });

  // ---- touch: swipe, swipe-down to close, tap, double-tap zoom, pinch, pan ----
  var sx = 0, sy = 0, dx = 0, dy = 0, tracking = false, pinching = false, d0 = 1, s0 = 1, tx0 = 0, ty0 = 0;
  var startTarget = null, lastTap = 0, tapTimer = null;
  function dist(e) { var a = e.touches[0], b = e.touches[1]; return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY); }
  stage.addEventListener('touchstart', function (e) {
    startTarget = e.target; moved = false;
    if (e.touches.length === 2) { pinching = true; tracking = false; d0 = dist(e); s0 = sc; return; }
    pinching = false; tracking = e.touches.length === 1; dx = dy = 0;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; tx0 = tx; ty0 = ty;
  }, { passive: true });
  stage.addEventListener('touchmove', function (e) {
    if (pinching && e.touches.length === 2) {
      moved = true; sc = Math.max(1, Math.min(5, s0 * dist(e) / d0)); clampT(); applyT(); return;
    }
    if (!tracking) return;
    dx = e.touches[0].clientX - sx; dy = e.touches[0].clientY - sy;
    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) moved = true;
    if (sc > 1) { tx = tx0 + dx; ty = ty0 + dy; clampT(); applyT(); return; }
    if (Math.abs(dx) > Math.abs(dy)) { if (list.length > 1) img.style.transform = 'translateX(' + dx + 'px)'; }
    else img.style.transform = 'translateY(' + dy * 0.6 + 'px)';
  }, { passive: true });
  stage.addEventListener('touchend', function (e) {
    if (pinching) { if (e.touches.length < 2) { pinching = false; if (sc < 1.05) resetZoom(); } return; }
    if (!tracking) return;
    tracking = false;
    if (!moved && startTarget === img) {  // tap on the photo: single = focus mode, double = zoom
      if (e.cancelable) e.preventDefault();
      var t = e.changedTouches[0], now = Date.now();
      if (now - lastTap < 300) { clearTimeout(tapTimer); lastTap = 0; dblTap(t.clientX, t.clientY); }
      else {
        lastTap = now;
        tapTimer = setTimeout(function () { lastTap = 0; if (sc === 1) setFocus(!lb.classList.contains('zoom')); }, 300);
      }
      return;
    }
    if (sc > 1) return;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50 && list.length > 1) {
      var d = dx < 0 ? 1 : -1;
      show(i + d, d);
      img.style.transform = '';
    } else if (Math.abs(dy) > Math.abs(dx) && dy > 90) {
      img.style.transform = ''; close();
    } else if (moved) {
      var from = img.style.transform || 'none';
      img.style.transform = '';
      if (img.animate) img.animate([{ transform: from }, { transform: 'none' }], { duration: 200, easing: 'ease-out' });
    }
  });
})();
