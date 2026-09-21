const STORAGE_KEY = 'aurelia-marketplace-listings';

const seedListings = [
  { id: 'seed-1', title: 'Minimalist interiors', platform: 'Instagram', price: 320, handle: '@minimal.home', followers: '84.2K', color: 'coral', verified: true, addedAt: '2026-09-18' },
  { id: 'seed-2', title: 'Daily tech reviews', platform: 'YouTube', price: 580, handle: 'TechBrief', followers: '126K', color: 'blue', verified: true, addedAt: '2026-09-16' },
  { id: 'seed-3', title: 'Streetwear archive', platform: 'Instagram', price: 145, handle: '@archive.studio', followers: '31.8K', color: 'violet', verified: true, addedAt: '2026-09-14' },
  { id: 'seed-4', title: 'Healthy meal prep', platform: 'TikTok', price: 89, handle: '@prepwithme', followers: '19.4K', color: 'lime', verified: false, addedAt: '2026-09-12' },
  { id: 'seed-5', title: 'Indie game discovery', platform: 'X / Twitter', price: 210, handle: '@indie_arcade', followers: '42.6K', color: 'gold', verified: true, addedAt: '2026-09-10' },
  { id: 'seed-6', title: 'Remote work resources', platform: 'Facebook', price: 75, handle: 'Remote Collective', followers: '8.9K', color: 'sky', verified: false, addedAt: '2026-09-08' }
];

let listings = loadListings();
const elements = {
  grid: document.querySelector('#listing-grid'), empty: document.querySelector('#empty-state'),
  search: document.querySelector('#search-input'), platform: document.querySelector('#platform-filter'),
  price: document.querySelector('#price-filter'), sort: document.querySelector('#sort-select'),
  resultCount: document.querySelector('#result-count'), activeCount: document.querySelector('#active-count'),
  averagePrice: document.querySelector('#average-price'), newCount: document.querySelector('#new-count'),
  dialog: document.querySelector('#listing-dialog'), form: document.querySelector('#listing-form'), toast: document.querySelector('#toast')
};

function loadListings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(saved) && saved.length ? saved : seedListings;
  } catch { return seedListings; }
}
function saveListings() { localStorage.setItem(STORAGE_KEY, JSON.stringify(listings)); }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character])); }
function platformClass(platform) { return platform.toLowerCase().replace(/[^a-z]/g, '').slice(0, 8); }
function priceMatches(price, range) {
  if (range === '0-100') return price < 100;
  if (range === '100-250') return price >= 100 && price <= 250;
  if (range === '250-500') return price > 250 && price <= 500;
  if (range === '500-plus') return price > 500;
  return true;
}
function filteredListings() {
  const keyword = elements.search.value.trim().toLowerCase();
  const platform = elements.platform.value;
  const range = elements.price.value;
  const filtered = listings.filter(listing => {
    const searchable = `${listing.title} ${listing.platform} ${listing.handle}`.toLowerCase();
    return (!keyword || searchable.includes(keyword)) && (platform === 'all' || listing.platform === platform) && priceMatches(listing.price, range);
  });
  return filtered.sort((a, b) => {
    if (elements.sort.value === 'price-low') return a.price - b.price;
    if (elements.sort.value === 'price-high') return b.price - a.price;
    if (elements.sort.value === 'newest') return new Date(b.addedAt) - new Date(a.addedAt);
    return 0;
  });
}
function render() {
  const visible = filteredListings();
  elements.resultCount.textContent = visible.length;
  elements.grid.innerHTML = visible.map(listing => `<article class="listing-card"><div class="listing-visual ${escapeHtml(listing.color || 'blue')}"><span class="visual-orbit"></span><span class="visual-initial">${escapeHtml(listing.platform[0])}</span><button class="save-button" aria-label="Save ${escapeHtml(listing.title)}">♡</button><span class="platform-badge">${escapeHtml(listing.platform)}</span></div><div class="listing-body"><div class="listing-title-row"><div><h2>${escapeHtml(listing.title)}</h2><p>${escapeHtml(listing.handle)}</p></div>${listing.verified ? '<span class="verified" title="Verified seller">✓</span>' : ''}</div><div class="listing-meta"><span>♧ ${escapeHtml(listing.followers || 'New')}</span><span class="price">$${Number(listing.price).toLocaleString()}</span></div><button class="view-button">View details <span>→</span></button></div></article>`).join('');
  elements.empty.hidden = visible.length > 0;
  elements.grid.hidden = visible.length === 0;
  updateStats();
}
function updateStats() {
  const average = listings.reduce((sum, listing) => sum + Number(listing.price), 0) / Math.max(listings.length, 1);
  elements.activeCount.textContent = listings.length;
  elements.averagePrice.textContent = `$${Math.round(average).toLocaleString()}`;
  elements.newCount.textContent = String(listings.filter(listing => new Date(listing.addedAt) >= new Date('2026-09-13')).length).padStart(2, '0');
}
function showToast(message) { elements.toast.textContent = message; elements.toast.classList.add('visible'); setTimeout(() => elements.toast.classList.remove('visible'), 2800); }
function clearErrors() { document.querySelectorAll('.field-error').forEach(error => { error.textContent = ''; }); document.querySelectorAll('.field.invalid').forEach(field => field.classList.remove('invalid')); }
function validateForm(data) {
  const errors = {};
  if (data.title.trim().length < 3) errors.title = 'Add a title with at least 3 characters.';
  if (!data.platform) errors.platform = 'Choose a platform.';
  if (!Number.isFinite(data.price) || data.price <= 0) errors.price = 'Enter a price greater than $0.';
  if (!data.contact.trim() || (!data.contact.includes('@') && data.contact.trim().length < 5)) errors.contact = 'Enter an email or contact handle.';
  Object.entries(errors).forEach(([name, message]) => { document.querySelector(`[data-error="${name}"]`).textContent = message; document.querySelector(`#${name}`).closest('.field').classList.add('invalid'); });
  return Object.keys(errors).length === 0;
}

document.querySelectorAll('select, input[type="search"]').forEach(control => control.addEventListener('input', render));
document.querySelector('#clear-filters').addEventListener('click', () => { elements.search.value = ''; elements.platform.value = 'all'; elements.price.value = 'all'; render(); });
document.querySelector('#empty-clear').addEventListener('click', () => document.querySelector('#clear-filters').click());
document.querySelector('#open-form').addEventListener('click', () => { clearErrors(); elements.form.reset(); elements.dialog.showModal(); });
document.querySelector('#close-form').addEventListener('click', () => elements.dialog.close());
document.querySelector('#cancel-form').addEventListener('click', () => elements.dialog.close());
elements.dialog.addEventListener('click', event => { if (event.target === elements.dialog) elements.dialog.close(); });
elements.form.addEventListener('submit', event => {
  event.preventDefault(); clearErrors();
  const data = { title: document.querySelector('#title').value, platform: document.querySelector('#platform').value, price: Number(document.querySelector('#price').value), contact: document.querySelector('#contact').value };
  if (!validateForm(data)) return;
  listings.unshift({ id: `listing-${Date.now()}`, title: data.title.trim(), platform: data.platform, price: data.price, handle: data.contact.trim(), followers: 'New seller', color: ['coral', 'violet', 'gold', 'sky'][listings.length % 4], verified: false, addedAt: new Date().toISOString().slice(0, 10) });
  saveListings(); render(); elements.dialog.close(); showToast('Your listing is now live in the marketplace.');
});
render();
