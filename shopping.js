const catalogStatus = document.getElementById('catalogStatus');
const resultsMeta = document.getElementById('resultsMeta');
const searchInput = document.getElementById('searchInput');
const refreshCatalogBtn = document.getElementById('refreshCatalogBtn');
const budgetInput = document.getElementById('budgetInput');
const resetCartBtn = document.getElementById('resetCartBtn');
const historyMonthSelect = document.getElementById('historyMonthSelect');
const shoppingListSelect = document.getElementById('shoppingListSelect');
const loadListBtn = document.getElementById('loadListBtn');
const createListBtn = document.getElementById('createListBtn');
const deleteListBtn = document.getElementById('deleteListBtn');
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
  historyMonths: [],
  savedLists: [],
  currentListId: null,
  currentListTitle: '',
  currentListYear: null,
  currentListMonth: null,
  budgetSaveTimer: null,
};

if (budgetInput) {
  budgetInput.value = state.budget ? String(state.budget) : '';
}

bindEvents();
boot();

async function boot() {
  await loadHistoryMonths();
  await loadSearchResults();
  render();
}

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
      queueBudgetSave();
    });
  }

  if (resetCartBtn) {
    resetCartBtn.addEventListener('click', async () => {
      if (state.currentListId) {
        await request(`/api/shopping/lists/${state.currentListId}/items`, { method: 'DELETE' });
      }
      state.cart = [];
      saveCart();
      render();
    });
  }

  if (historyMonthSelect) {
    historyMonthSelect.addEventListener('change', async () => {
      await loadSavedListsForSelectedMonth();
    });
  }

  if (shoppingListSelect) {
    shoppingListSelect.addEventListener('change', () => {
      updateListControlState();
    });
  }

  if (loadListBtn) {
    loadListBtn.addEventListener('click', async () => {
      await loadSelectedShoppingList();
    });
  }

  if (createListBtn) {
    createListBtn.addEventListener('click', async () => {
      await createShoppingListFromCurrentState();
    });
  }

  if (deleteListBtn) {
    deleteListBtn.addEventListener('click', async () => {
      await deleteSelectedShoppingList();
    });
  }
}

async function loadHistoryMonths() {
  try {
    const months = await requestJson('/api/shopping/lists/history');
    state.historyMonths = Array.isArray(months) ? months : [];
  } catch (error) {
    state.historyMonths = [];
  }

  populateHistoryMonthOptions();
  await loadSavedListsForSelectedMonth({ autoLoad: true });
}

function populateHistoryMonthOptions() {
  if (!historyMonthSelect) return;

  const current = getCurrentYearMonth();
  const monthMap = new Map();
  state.historyMonths.forEach(entry => {
    monthMap.set(monthKey(entry.target_year, entry.target_month), {
      year: entry.target_year,
      month: entry.target_month,
    });
  });
  monthMap.set(monthKey(current.year, current.month), {
    year: current.year,
    month: current.month,
  });

  const monthOptions = Array.from(monthMap.values()).sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year;
    return b.month - a.month;
  });

  const currentValue = historyMonthSelect.value;
  historyMonthSelect.innerHTML = '';
  monthOptions.forEach(entry => {
    const option = document.createElement('option');
    option.value = monthKey(entry.year, entry.month);
    option.textContent = `${entry.year}.${String(entry.month).padStart(2, '0')}`;
    historyMonthSelect.appendChild(option);
  });

  if (currentValue && monthOptions.some(entry => monthKey(entry.year, entry.month) === currentValue)) {
    historyMonthSelect.value = currentValue;
  } else {
    historyMonthSelect.value = monthKey(current.year, current.month);
  }
}

async function loadSavedListsForSelectedMonth({ autoLoad = false, preferredListId = null } = {}) {
  const selected = getSelectedHistoryMonth();
  if (!selected || !shoppingListSelect) return;

  try {
    const params = new URLSearchParams({
      year: String(selected.year),
      month: String(selected.month),
    });
    const lists = await requestJson(`/api/shopping/lists?${params.toString()}`);
    state.savedLists = Array.isArray(lists) ? lists : [];
  } catch (error) {
    state.savedLists = [];
  }

  shoppingListSelect.innerHTML = '';
  if (!state.savedLists.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '저장된 리스트 없음';
    shoppingListSelect.appendChild(option);
    shoppingListSelect.disabled = true;
    updateListControlState();
    return;
  }

  state.savedLists.forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = `${item.title} (${item.item_count}개)`;
    shoppingListSelect.appendChild(option);
  });
  shoppingListSelect.disabled = false;

  if (preferredListId && state.savedLists.some(item => item.id === preferredListId)) {
    shoppingListSelect.value = preferredListId;
  } else if (state.currentListId && state.savedLists.some(item => item.id === state.currentListId)) {
    shoppingListSelect.value = state.currentListId;
  } else {
    shoppingListSelect.value = state.savedLists[0].id;
  }

  updateListControlState();

  if (autoLoad && shoppingListSelect.value) {
    await loadSelectedShoppingList();
  }
}

async function loadSelectedShoppingList() {
  const listId = shoppingListSelect?.value;
  if (!listId) return;

  const payload = await requestJson(`/api/shopping/lists/${listId}`);
  applyShoppingList(payload);
}

async function createShoppingListFromCurrentState() {
  const selected = getSelectedHistoryMonth() || getCurrentYearMonth();
  const payload = {
    title: `${selected.year}년 ${selected.month}월 코스트코 장보기`,
    target_year: selected.year,
    target_month: selected.month,
    budget: state.budget || 0,
    status: 'active',
    items: state.cart.map((item, index) => serializeCartEntryForRequest(item, index)),
  };

  const created = await requestJson('/api/shopping/lists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  populateHistoryMonthOptions();
  if (historyMonthSelect) {
    historyMonthSelect.value = monthKey(selected.year, selected.month);
  }
  await loadSavedListsForSelectedMonth({ preferredListId: created.id });
  applyShoppingList(created);
}

async function deleteSelectedShoppingList() {
  const listId = shoppingListSelect?.value || state.currentListId;
  if (!listId) return;

  const selected = state.savedLists.find(item => item.id === listId);
  const label = selected?.title || state.currentListTitle || '선택한 리스트';
  if (!window.confirm(`'${label}' 리스트를 삭제할까요?`)) return;

  await request(`/api/shopping/lists/${listId}`, { method: 'DELETE' });
  if (state.currentListId === listId) {
    state.currentListId = null;
    state.currentListTitle = '';
    state.currentListYear = null;
    state.currentListMonth = null;
    state.cart = [];
    state.budget = 0;
    if (budgetInput) budgetInput.value = '';
    saveCart();
    saveBudget();
  }

  await loadHistoryMonths();
  render();
}

function applyShoppingList(payload) {
  state.currentListId = payload.id;
  state.currentListTitle = payload.title || '';
  state.currentListYear = payload.target_year || null;
  state.currentListMonth = payload.target_month || null;
  state.budget = Number(payload.budget) || 0;
  state.cart = Array.isArray(payload.items) ? payload.items.map(deserializeShoppingItem) : [];

  if (budgetInput) {
    budgetInput.value = state.budget ? String(state.budget) : '';
  }

  saveBudget();
  saveCart();
  render();
}

function render() {
  renderResults();
  renderCart();
  renderSummary();
  updateListControlState();
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
    const payload = await requestJson(`/api/shopping/search?${params.toString()}`);
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

    addBtn.addEventListener('click', async () => {
      addBtn.disabled = true;
      await addToCart(item);
      addBtn.disabled = false;
    });
    searchResults.appendChild(fragment);
  });
}

function renderCart() {
  if (!cartList) return;

  cartList.innerHTML = '';
  if (cartMeta) {
    cartMeta.textContent = state.currentListTitle
      ? `${state.currentListTitle} · ${state.cart.length}개 담김`
      : `${state.cart.length}개 담김`;
  }

  if (!state.cart.length) {
    cartList.appendChild(
      buildEmptyState(
        state.currentListId
          ? '선택한 장보기 리스트가 비어 있습니다. 검색 결과에서 몇 개 담아보세요.'
          : '저장된 리스트를 불러오거나 이번 달 새 리스트를 만든 뒤 상품을 담아보세요.'
      )
    );
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
    openLink.href = item.url || '#';

    check.addEventListener('change', async () => {
      item.checked = check.checked;
      saveCart();
      renderSummary();
      await persistCartItem(item, { is_checked: item.checked });
    });

    qty.addEventListener('input', () => {
      item.qty = Math.max(1, Number(qty.value) || 1);
      total.textContent = `소계 ${formatWon((item.price_value || 0) * item.qty)}`;
      saveCart();
      renderSummary();
    });
    qty.addEventListener('change', async () => {
      item.qty = Math.max(1, Number(qty.value) || 1);
      await persistCartItem(item, { quantity: item.qty });
      render();
    });

    price.addEventListener('input', () => {
      item.price_value = Math.max(0, Number(price.value) || 0);
      item.price_text = formatWon(item.price_value);
      total.textContent = `소계 ${formatWon((item.price_value || 0) * item.qty)}`;
      saveCart();
      renderSummary();
    });
    price.addEventListener('change', async () => {
      item.price_value = Math.max(0, Number(price.value) || 0);
      item.price_text = formatWon(item.price_value);
      await persistCartItem(item, {
        expected_price: item.price_value,
        price_text: item.price_text,
      });
      render();
    });

    removeBtn.addEventListener('click', async () => {
      await removeCartItem(item);
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

async function addToCart(item) {
  const existing = findExistingCartEntry(item);
  if (state.currentListId) {
    if (existing) {
      existing.qty += 1;
      saveCart();
      render();
      await persistCartItem(existing, { quantity: existing.qty });
      return;
    }

    const created = await requestJson(`/api/shopping/lists/${state.currentListId}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(serializeResultItemForRequest(item)),
    });
    state.cart.unshift(deserializeShoppingItem(created));
    saveCart();
    render();
    return;
  }

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
      costco_product_id: item.id || '',
    });
  }

  saveCart();
  render();
}

async function persistCartItem(item, payload) {
  if (!state.currentListId) {
    saveCart();
    return;
  }

  const updated = await requestJson(`/api/shopping/items/${item.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  syncCartEntry(updated);
  saveCart();
}

async function removeCartItem(item) {
  if (state.currentListId) {
    await request(`/api/shopping/items/${item.id}`, { method: 'DELETE' });
  }
  state.cart = state.cart.filter(entry => entry.id !== item.id);
  saveCart();
  render();
}

function syncCartEntry(payload) {
  const next = deserializeShoppingItem(payload);
  const index = state.cart.findIndex(entry => entry.id === next.id);
  if (index >= 0) {
    state.cart[index] = next;
  } else {
    state.cart.unshift(next);
  }
}

function findExistingCartEntry(item) {
  return state.cart.find(entry => {
    if (entry.costco_product_id && item.id && entry.costco_product_id === item.id) return true;
    if (entry.url && item.url && entry.url === item.url) return true;
    return normalize(entry.title) === normalize(item.title);
  });
}

function queueBudgetSave() {
  if (!state.currentListId) return;
  window.clearTimeout(state.budgetSaveTimer);
  state.budgetSaveTimer = window.setTimeout(async () => {
    await requestJson(`/api/shopping/lists/${state.currentListId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget: state.budget }),
    });
  }, 280);
}

function updateListControlState() {
  if (loadListBtn) {
    loadListBtn.disabled = !shoppingListSelect || !shoppingListSelect.value;
  }
  if (deleteListBtn) {
    deleteListBtn.disabled = !shoppingListSelect || !shoppingListSelect.value;
  }
}

function getSelectedHistoryMonth() {
  if (!historyMonthSelect?.value) return null;
  const [yearText, monthText] = historyMonthSelect.value.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  if (!year || !month) return null;
  return { year, month };
}

function getCurrentYearMonth() {
  const now = new Date();
  return {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
  };
}

function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`;
}

function deserializeShoppingItem(item) {
  return {
    id: item.id,
    title: item.product_name,
    image_url: item.image_url,
    url: item.product_url,
    qty: Number(item.quantity) || 1,
    checked: Boolean(item.is_checked),
    price_value: Number(item.expected_price) || 0,
    price_text: item.price_text || formatWon(item.expected_price || 0),
    costco_product_id: item.costco_product_id || '',
    original_price: item.original_price,
    original_price_text: item.original_price_text,
    discount_amount: item.discount_amount,
    discount_text: item.discount_text,
    discount_period_text: item.discount_period_text,
    member_only: Boolean(item.member_only),
    note: item.note || '',
    sort_order: Number(item.sort_order) || 0,
  };
}

function serializeResultItemForRequest(item) {
  return {
    product_name: item.title,
    product_url: item.url || null,
    image_url: item.image_url || null,
    costco_product_id: item.id || null,
    quantity: 1,
    expected_price: item.price_value || 0,
    price_text: item.price_text || '',
    original_price: item.original_price_value || null,
    original_price_text: item.original_price_text || null,
    discount_amount: item.discount_value || null,
    discount_text: item.discount_text || null,
    discount_period_text: item.discount_period_text || null,
    member_only: Boolean(item.member_only),
    is_checked: false,
    note: null,
    sort_order: 0,
  };
}

function serializeCartEntryForRequest(item, index) {
  return {
    product_name: item.title,
    product_url: item.url || null,
    image_url: item.image_url || null,
    costco_product_id: item.costco_product_id || null,
    quantity: Math.max(1, Number(item.qty) || 1),
    expected_price: Math.max(0, Number(item.price_value) || 0),
    price_text: item.price_text || formatWon(item.price_value || 0),
    original_price: item.original_price || null,
    original_price_text: item.original_price_text || null,
    discount_amount: item.discount_amount || null,
    discount_text: item.discount_text || null,
    discount_period_text: item.discount_period_text || null,
    member_only: Boolean(item.member_only),
    is_checked: Boolean(item.checked),
    note: item.note || null,
    sort_order: Number(item.sort_order) || index,
  };
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

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
}
