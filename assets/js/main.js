/* ============================================
   DentalPedia — Main JavaScript
   ============================================ */

// ---- Theme Toggle ----
(function initTheme() {
  const saved = localStorage.getItem('dentalpedia-theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
  } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('dentalpedia-theme', next);
  const btn = document.querySelector('.theme-toggle');
  if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}

// ---- Search ----
let searchIndex = [];

async function loadSearchIndex() {
  try {
    const resp = await fetch('/search-index.json');
    if (resp.ok) searchIndex = await resp.json();
  } catch (e) {
    console.log('Search index not yet available');
  }
}

function handleSearch(query) {
  const container = document.querySelector('.search-results');
  if (!container) return;

  if (!query || query.length < 2) {
    container.classList.remove('active');
    return;
  }

  const q = query.toLowerCase();
  const results = searchIndex.filter(item =>
    item.title.toLowerCase().includes(q) ||
    (item.category && item.category.toLowerCase().includes(q)) ||
    (item.excerpt && item.excerpt.toLowerCase().includes(q))
  ).slice(0, 8);

  if (results.length === 0) {
    container.innerHTML = '<div class="search-result-item"><span class="result-title">No articles found</span></div>';
    container.classList.add('active');
    return;
  }

  container.innerHTML = results.map(r => `
    <a href="${r.url}" class="search-result-item">
      <div class="result-title">${highlightMatch(r.title, q)}</div>
      <div class="result-category">${r.category || ''}</div>
    </a>
  `).join('');
  container.classList.add('active');
}

function highlightMatch(text, query) {
  const idx = text.toLowerCase().indexOf(query);
  if (idx === -1) return text;
  return text.slice(0, idx) + '<strong>' + text.slice(idx, idx + query.length) + '</strong>' + text.slice(idx + query.length);
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  // Theme toggle button
  const themeBtn = document.querySelector('.theme-toggle');
  if (themeBtn) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    themeBtn.textContent = isDark ? '☀️' : '🌙';
    themeBtn.addEventListener('click', toggleTheme);
  }

  // Search
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    loadSearchIndex();
    searchInput.addEventListener('input', (e) => handleSearch(e.target.value));
    searchInput.addEventListener('focus', (e) => {
      if (e.target.value.length >= 2) handleSearch(e.target.value);
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-container')) {
        const sr = document.querySelector('.search-results');
        if (sr) sr.classList.remove('active');
      }
    });
  }

  // Article count animation
  const countEl = document.querySelector('.article-count');
  if (countEl) {
    const target = parseInt(countEl.dataset.count || '0');
    animateCount(countEl, target);
  }
});

function animateCount(el, target) {
  let current = 0;
  const step = Math.max(1, Math.floor(target / 60));
  const interval = setInterval(() => {
    current += step;
    if (current >= target) {
      current = target;
      clearInterval(interval);
    }
    el.textContent = current.toLocaleString();
  }, 20);
}
