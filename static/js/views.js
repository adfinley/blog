(function () {
  var root = document.documentElement;
  var bar = document.querySelector('.viewtoggle');
  if (!bar) return;
  function apply(v) {
    root.classList.toggle('view-grid', v === 'grid');
    root.classList.toggle('view-mosaic', v === 'mosaic');
    bar.querySelectorAll('button[data-view]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === v));
    });
  }
  var saved = 'card';
  try { saved = localStorage.getItem('view') || 'card'; } catch (e) {}
  apply(saved);
  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-view]');
    if (!b) return;
    e.stopPropagation();
    var v = b.getAttribute('data-view');
    apply(v);
    try { localStorage.setItem('view', v); } catch (err) {}
  }, true);
})();
