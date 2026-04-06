const catalogStatus = document.getElementById('catalogStatus');
const resultsMeta = document.getElementById('resultsMeta');
const searchInput = document.getElementById('searchInput');
const refreshCatalogBtn = document.getElementById('refreshCatalogBtn');
const budgetInput = document.getElementById('budgetInput');
const resetCartBtn = document.getElementById('resetCartBtn');
const searchResults = document.getElementById('searchResults');
const cartList = document.getElementById('cartList');
const cartMeta = document.getElementById('cartMeta');
const estimatedTotal = document.getElementById('estimatedTotal');
const pickedTotal = document.getElementById('pickedTotal');
const remainingTotal = document.getElementById('remainingTotal');
const budgetDelta = document.getElementById('budgetDelta');

const resultCardTemplate = document.getElementById('resultCardTemplate');
const cartItemTemplate = document.getElementById('cartItemTemplate');

const CART_STORAGE_KEY = 'shopping-cart-v1';
const BUDGET_STORAGE_KEY = 'shopping-budget-v1';

const state = {
  results: [],
  cart: loadCart(),
  budget: loadBudget(),
  fetchedAt: null,
  matchedCount: 0,
  totalCatalogCount: 0,
  mode: 'featured',
};

if (budgetInput) {
  budgetInput.value = state.budget ? String(state.budget) : '';
}

loadSearchResults();
bindEvents();
render();

function bindEvents() {
  if (searchInput) {
    let searchTimer = null;
    searchInput.addEventListener('input', () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        loadSearchResults();
      }, 220);
    });
  }

  if (refreshCatalogBtn) {
    refreshCatalogBtn.addEventListener('click', async () => {
      refreshCatalogBtn.disabled = true;
      await loadSearchResults(true);
      refreshCatalogBtn.disabled = false;
    });
  }

  if (budgetInput) {
    budgetInput.addEventListener('input', () => {
      state.budget = Number(budgetInput.value) || 0;
      saveBudget();
      renderSummary();
    });
  }

  if (resetCartBtn) {
    resetCartBtn.addEventListener('click', () => {
      state.cart = [];
      saveCart();
      render();
    });
  }
}

async function loadSearchResults(refresh = false) {
  const query = searchInput?.value || '';
  if (catalogStatus) {
    catalogStatus.textContent = refresh
      ? '공식몰 검색 결과를 다시 불러오는 중입니다.'
      : '공식몰 검색 결과를 불러오는 중입니다.';
  }

  try {
    const params = new URLSearchParams({
      q: query,
      limit: '12',
    });
    if (refresh) params.set('refresh', 'true');
    const url = `/api/shopping/search?${params.toString()}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('카탈로그 응답 실패');
    const payload = await response.json();
    state.results = Array.isArray(payload.items) ? payload.items : [];
    state.fetchedAt = payload.fetched_at;
    state.totalCatalogCount = Number(payload.total_catalog_count) || 0;
    state.matchedCount = Number(payload.matched_count) || 0;
    state.mode = payload.mode || 'search';
    if (catalogStatus) {
      catalogStatus.textContent = payload.message || '공식몰 검색 결과를 불러왔습니다.';
    }
  } catch (error) {
    state.results = [];
    state.totalCatalogCount = 0;
    state.matchedCount = 0;
    state.mode = 'error';
    if (catalogStatus) {
      catalogStatus.textContent = '공식몰 검색 결과를 불러오지 못했습니다.';
    }
  }

  renderResults();
}

function render() {
  renderResults();
  renderCart();
  renderSummary();
}

function renderResults() {
  if (!searchResults) return;
  const query = searchInput?.value?.trim() || '';
  const results = state.results;

  if (resultsMeta) {
    const syncedText = state.fetchedAt
      ? `최근 동기화 ${new Date(state.fetchedAt).toLocaleString('ko-KR')}`
      : '최근 동기화 기록 없음';
    if (query) {
      resultsMeta.textContent = `전체 상품 ${state.totalCatalogCount.toLocaleString('ko-KR')}개 중 ${state.matchedCount.toLocaleString('ko-KR')}개 매칭 · 현재 ${results.length}개 표시 · ${syncedText}`;
    } else {
      resultsMeta.textContent = `전체 상품 ${state.totalCatalogCount.toLocaleString('ko-KR')}개 · 현재 ${results.length}개 표시 · ${syncedText}`;
    }
  }

  searchResults.innerHTML = '';
  if (!results.length) {
    searchResults.appendChild(buildEmptyState(query ? '검색 결과가 없습니다. 영문 상품명이나 브랜드 키워드도 시도해보세요.' : '기본 노출 상품이 없습니다.'));
    return;
  }

  results.forEach(item => {
    const fragment = resultCardTemplate.content.cloneNode(true);
    const image = fragment.querySelector('[data-image]');
    const title = fragment.querySelector('[data-title]');
    const originalPrice = fragment.querySelector('[data-original-price]');
    const discount = fragment.querySelector('[data-discount]');
    const price = fragment.querySelector('[data-price]');
    const discountPeriod = fragment.querySelector('[data-discount-period]');
    const note = fragment.querySelector('[data-note]');
    const addBtn = fragment.querySelector('[data-add]');
    const openLink = fragment.querySelector('[data-open]');

    image.src = item.image_url || '';
    image.alt = item.title;
    title.textContent = item.title;
    if (item.has_discount && item.original_price_text && item.discount_text) {
      originalPrice.hidden = false;
      discount.hidden = false;
      originalPrice.textContent = `정가 ${item.original_price_text}`;
      discount.textContent = `할인 -${item.discount_text}`;
      price.textContent = `최종가 ${item.price_text || '가격 미노출'}`;
      if (item.discount_period_text) {
        discountPeriod.hidden = false;
        discountPeriod.textContent = `할인 기간 ${item.discount_period_text}`;
      } else {
        discountPeriod.hidden = true;
        discountPeriod.textContent = '';
      }
    } else {
      originalPrice.hidden = true;
      discount.hidden = true;
      originalPrice.textContent = '';
      discount.textContent = '';
      price.textContent = item.price_text || '가격 미노출';
      discountPeriod.hidden = true;
      discountPeriod.textContent = '';
    }
    if (item.member_only) {
      note.hidden = false;
      note.textContent = '회원 전용 또는 홈페이지 노출 기준으로 가격 확인이 제한될 수 있습니다.';
    } else {
      note.hidden = true;
      note.textContent = '';
    }
    openLink.href = item.url;

    addBtn.addEventListener('click', () => addToCart(item));
    searchResults.appendChild(fragment);
  });
}

function renderCart() {
  if (!cartList) return;

  cartList.innerHTML = '';
  if (cartMeta) {
    cartMeta.textContent = `${state.cart.length}개 담김`;
  }

  if (!state.cart.length) {
    cartList.appendChild(buildEmptyState('오른쪽 장보기 리스트는 브라우저에만 임시 저장됩니다. 공식몰 검색 결과에서 몇 개 담아보세요.'));
    return;
  }

  state.cart.forEach(item => {
    const fragment = cartItemTemplate.content.cloneNode(true);
    const image = fragment.querySelector('[data-image]');
    const title = fragment.querySelector('[data-title]');
    const check = fragment.querySelector('[data-check]');
    const qty = fragment.querySelector('[data-qty]');
    const price = fragment.querySelector('[data-price]');
    const total = fragment.querySelector('[data-total]');
    const removeBtn = fragment.querySelector('[data-remove]');
    const openLink = fragment.querySelector('[data-open]');

    image.src = item.image_url || '';
    image.alt = item.title;
    title.textContent = item.title;
    check.checked = Boolean(item.checked);
    qty.value = String(item.qty);
    price.value = String(item.price_value || 0);
    total.textContent = `소계 ${formatWon((item.price_value || 0) * item.qty)}`;
    openLink.href = item.url;

    check.addEventListener('change', () => {
      item.checked = check.checked;
      saveCart();
      renderSummary();
    });

    qty.addEventListener('input', () => {
      item.qty = Math.max(1, Number(qty.value) || 1);
      saveCart();
      render();
    });

    price.addEventListener('input', () => {
      item.price_value = Math.max(0, Number(price.value) || 0);
      item.price_text = formatWon(item.price_value);
      saveCart();
      render();
    });

    removeBtn.addEventListener('click', () => {
      state.cart = state.cart.filter(entry => entry.id !== item.id);
      saveCart();
      render();
    });

    cartList.appendChild(fragment);
  });
}

function renderSummary() {
  const estimated = state.cart.reduce((sum, item) => sum + (item.price_value || 0) * item.qty, 0);
  const picked = state.cart.reduce((sum, item) => {
    if (!item.checked) return sum;
    return sum + (item.price_value || 0) * item.qty;
  }, 0);
  const remaining = Math.max(estimated - picked, 0);

  estimatedTotal.textContent = formatWon(estimated);
  pickedTotal.textContent = formatWon(picked);
  remainingTotal.textContent = formatWon(remaining);

  if (!state.budget) {
    budgetDelta.textContent = '예산 미입력';
    budgetDelta.style.color = '';
    return;
  }

  const delta = state.budget - estimated;
  budgetDelta.textContent = delta >= 0
    ? `${formatWon(delta)} 남음`
    : `${formatWon(Math.abs(delta))} 초과`;
  budgetDelta.style.color = delta >= 0 ? 'var(--accent)' : '#b23a2b';
}

function addToCart(item) {
  const existing = state.cart.find(entry => entry.id === item.id);
  if (existing) {
    existing.qty += 1;
  } else {
    state.cart.unshift({
      id: item.id,
      title: item.title,
      image_url: item.image_url,
      url: item.url,
      qty: 1,
      checked: false,
      price_value: item.price_value || 0,
      price_text: item.price_text || '',
    });
  }

  saveCart();
  render();
}

function buildEmptyState(message) {
  const node = document.createElement('div');
  node.className = 'empty-state';
  node.textContent = message;
  return node;
}

function loadCart() {
  try {
    const raw = localStorage.getItem(CART_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveCart() {
  localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(state.cart));
}

function loadBudget() {
  const raw = localStorage.getItem(BUDGET_STORAGE_KEY);
  return raw ? Number(raw) || 0 : 0;
}

function saveBudget() {
  localStorage.setItem(BUDGET_STORAGE_KEY, String(state.budget || 0));
}

function normalize(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, '');
}

function formatWon(value) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`;
}
