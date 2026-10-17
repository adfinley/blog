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
  var list = [], meta = '', i = 0;

  function show(n) {
    i = (n + list.length) % list.length;
    img.src = list[i].src;
    img.alt = list[i].alt || '';
    c1.textContent = meta;
    c2.textContent = list[i].exif || '';
    var multi = list.length > 1;
    prev.style.visibility = next.style.visibility = multi ? 'visible' : 'hidden';
    dots.style.display = multi ? 'flex' : 'none';
    dots.innerHTML = list.map(function (_, k) { return '<i class="' + (k === i ? 'on' : '') + '"></i>'; }).join('');
  }
  function close() { lb.classList.remove('open'); document.body.style.overflow = ''; }

  document.addEventListener('click', function (e) {
    var t = e.target.closest('.tile');
    if (!t) return;
    var post = t.closest('.post');
    list = JSON.parse(post.querySelector('.imgs').textContent);
    meta = post.dataset.meta || '';
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
    show(+t.dataset.i);
  });
  q('.lb-close').onclick = close;
  prev.onclick = function () { show(i - 1); };
  next.onclick = function () { show(i + 1); };
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    if (list.length > 1 && e.key === 'ArrowLeft') show(i - 1);
    if (list.length > 1 && e.key === 'ArrowRight') show(i + 1);
  });
})();
