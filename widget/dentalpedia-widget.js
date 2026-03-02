(function() {
  var style = document.createElement('style');
  style.textContent = '.dp-widget{font-family:Inter,-apple-system,sans-serif;border:1px solid #e2e8f0;border-radius:12px;padding:1.25rem;max-width:400px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,0.08)}.dp-widget h3{margin:0 0 .75rem;font-size:1.1rem;color:#1a1a2e}.dp-widget a{display:block;padding:.5rem 0;color:#2563eb;text-decoration:none;font-size:.95rem;border-bottom:1px solid #f1f5f9}.dp-widget a:hover{color:#1d4ed8}.dp-widget .dp-footer{margin-top:.75rem;font-size:.8rem;color:#94a3b8;text-align:right}.dp-widget .dp-footer a{display:inline;border:none;padding:0}';
  document.head.appendChild(style);
  var containers = document.querySelectorAll('[data-dentalpedia-widget]');
  containers.forEach(function(el) {
    var category = el.getAttribute('data-category') || 'general-dentistry';
    var count = parseInt(el.getAttribute('data-count') || '5');
    var widget = document.createElement('div');
    widget.className = 'dp-widget';
    widget.innerHTML = '<h3>Learn More from DentalPedia</h3><div class="dp-articles"></div><div class="dp-footer">Powered by <a href="https://dentalpedia.co" target="_blank">DentalPedia</a></div>';
    el.appendChild(widget);
    fetch('https://dentalpedia.co/widget/articles.json')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var articles = data.filter(function(a) { return !category || a.category_slug === category; }).slice(0, count);
        var html = '';
        articles.forEach(function(a) {
          html += '<a href="https://dentalpedia.co/article/' + a.slug + '.html" target="_blank">' + a.title + '</a>';
        });
        widget.querySelector('.dp-articles').innerHTML = html || '<p>No articles found.</p>';
      })
      .catch(function() {
        widget.querySelector('.dp-articles').innerHTML = '<p>Visit <a href="https://dentalpedia.co">DentalPedia</a></p>';
      });
  });
})();