(function () {
  var lb = document.createElement('div');
  lb.className = 'lb';
  lb.innerHTML = '<button class="lb-btn lb-close" aria-label="Close">✕</button>' +
    '<div class="lb-stage"><button class="lb-btn lb-prev" aria-label="Previous">←</button><img alt="">' +
    '<button class="lb-btn lb-next" aria-label="Next">→</button></div>' +
    '<div class="lb-cap"><div class="cap-row"><span class="c1"></span><span class="c2"></span></div><div class="dots"></div></div>';
  document.body.appendChild(lb);
  var q = function (s) { return lb.querySelector(s); };
  var img = q('img'), c1 = q('.c1'), c2 = q('.c2'), dots = q('.dots'), prev = q('.lb-prev'), next = q('.lb-next');
  var list = [], date = '', loc = '', i = 0, moved = false;

  function show(n, dir) {
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
  function close() { lb.classList.remove('open', 'zoom'); document.body.style.overflow = ''; }

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
  img.onclick = function () { if (moved) { moved = false; return; } lb.classList.toggle('zoom'); };
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
  // Touch: drag to follow the finger, swipe left/right to change photo, swipe down to close.
  var stage = q('.lb-stage'), sx = 0, sy = 0, dx = 0, dy = 0, tracking = false;
  stage.addEventListener('touchstart', function (e) {
    if (e.touches.length !== 1) { tracking = false; return; }
    tracking = true; moved = false; dx = dy = 0;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
  }, { passive: true });
  stage.addEventListener('touchmove', function (e) {
    if (!tracking) return;
    dx = e.touches[0].clientX - sx; dy = e.touches[0].clientY - sy;
    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) moved = true;
    if (Math.abs(dx) > Math.abs(dy)) { if (list.length > 1) img.style.transform = 'translateX(' + dx + 'px)'; }
    else img.style.transform = 'translateY(' + dy * 0.6 + 'px)';
  }, { passive: true });
  stage.addEventListener('touchend', function () {
    if (!tracking) return;
    tracking = false;
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
