const catalogStatus = document.getElementById('catalogStatus');
const resultsMeta = document.getElementById('resultsMeta');
const searchInput = document.getElementById('searchInput');
const categoryFilterGroup = document.getElementById('categoryFilterGroup');
const categoryPickerBtn = document.getElementById('categoryPickerBtn');
const categoryPickerPanel = document.getElementById('categoryPickerPanel');
const categoryPickerBackdrop = document.getElementById('categoryPickerBackdrop');
const categoryPickerPath = document.getElementById('categoryPickerPath');
const categoryPickerTrail = document.getElementById('categoryPickerTrail');
const categoryPickerList = document.getElementById('categoryPickerList');
const categorySelectCurrentBtn = document.getElementById('categorySelectCurrentBtn');
const categoryPickerCloseBtn = document.getElementById('categoryPickerCloseBtn');
const categoryClearBtn = document.getElementById('categoryClearBtn');
const refreshCatalogBtn = document.getElementById('refreshCatalogBtn');
const budgetInput = document.getElementById('budgetInput');
const resetCartBtn = document.getElementById('resetCartBtn');
const historyMonthSelect = document.getElementById('historyMonthSelect');
const shoppingListSelect = document.getElementById('shoppingListSelect');
const saveListBtn = document.getElementById('saveListBtn');
const saveAsNewListBtn = document.getElementById('saveAsNewListBtn');
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
const PLACEHOLDER_IMAGE = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 240">
    <defs>
      <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stop-color="#efe2d2"/>
        <stop offset="1" stop-color="#e2eadc"/>
      </linearGradient>
    </defs>
    <rect width="320" height="240" rx="28" fill="url(#bg)"/>
    <circle cx="114" cy="98" r="30" fill="#d2b896"/>
    <path d="M62 184l62-62 39 39 27-27 68 50H62z" fill="#b8a56f" opacity="0.86"/>
    <text x="160" y="215" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#8a6044">이미지 준비중</text>
  </svg>
)}`;

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
  categoryTree: [],
  selectedCategoryPath: '',
  browsingCategoryPath: '',
  searchRequestId: 0,
  categoryLoading: false,
};

if (budgetInput) {
  budgetInput.value = state.budget ? String(state.budget) : '';
}

bindEvents();
boot().catch(error => {
  console.error(error);
  if (catalogStatus) {
    catalogStatus.textContent = '장보기 화면 초기화 중 오류가 발생했습니다. 새로고침 후 다시 시도해보세요.';
  }
});

async function boot() {
  render();
  loadHistoryMonths().then(() => render()).catch(() => render());
  loadCategoryTree().catch(() => renderCategoryFilters());
  loadSearchResults().catch(() => renderResults());
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

  if (categoryPickerBtn) {
    categoryPickerBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      toggleCategoryPicker();
    });
  }

  if (categorySelectCurrentBtn) {
    categorySelectCurrentBtn.addEventListener('click', async event => {
      event.preventDefault();
      event.stopPropagation();
      await selectCategoryPath(state.browsingCategoryPath);
    });
  }

  if (categoryPickerCloseBtn) {
    categoryPickerCloseBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      closeCategoryPicker();
    });
  }

  if (categoryClearBtn) {
    categoryClearBtn.addEventListener('click', async event => {
      event.preventDefault();
      event.stopPropagation();
      await selectCategoryPath('');
    });
  }

  if (categoryPickerBackdrop) {
    categoryPickerBackdrop.addEventListener('click', () => {
      closeCategoryPicker();
    });
  }

  document.addEventListener('click', event => {
    if (!categoryPickerPanel || categoryPickerPanel.hidden) return;
    if (
      !categoryPickerPanel.contains(event.target)
      && (!categoryPickerBtn || !categoryPickerBtn.contains(event.target))
    ) {
      closeCategoryPicker();
    }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeCategoryPicker();
    }
  });

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

  if (historyMonthSelect) {
    historyMonthSelect.addEventListener('change', async () => {
      await loadSavedListsForSelectedMonth({ autoLoad: true, clearWhenEmpty: true });
    });
  }

  if (shoppingListSelect) {
    shoppingListSelect.addEventListener('change', async () => {
      updateListControlState();
      await loadSelectedShoppingList();
    });
  }

  if (saveListBtn) {
    saveListBtn.addEventListener('click', async () => {
      await saveCurrentShoppingList();
    });
  }

  if (saveAsNewListBtn) {
    saveAsNewListBtn.addEventListener('click', async () => {
      await createShoppingListFromCurrentState();
    });
  }

  if (deleteListBtn) {
    deleteListBtn.addEventListener('click', async () => {
      await deleteSelectedShoppingList();
    });
  }
}

async function loadCategoryTree() {
  if (!categoryFilterGroup) return;
  if (state.categoryLoading) return;
  state.categoryLoading = true;
  renderCategoryFilters();
  try {
    const payload = await requestJson('/api/shopping/categories');
    state.categoryTree = Array.isArray(payload.items) ? payload.items : [];
  } catch (error) {
    state.categoryTree = [];
  } finally {
    state.categoryLoading = false;
  }
  renderCategoryFilters();
}

function renderCategoryFilters() {
  if (!categoryPickerBtn) return;
  const selectedLabel = getCategoryLabel(state.selectedCategoryPath);
  categoryPickerBtn.textContent = selectedLabel || '전체';
  renderCategoryPicker();
}

function renderCategoryPicker() {
  if (!categoryPickerList || !categoryPickerTrail || !categoryPickerPath) return;

  const currentNode = findCategoryNode(state.browsingCategoryPath);
  const children = currentNode ? currentNode.children || [] : state.categoryTree;
  const currentLabel = getCategoryLabel(state.browsingCategoryPath);

  categoryPickerPath.textContent = currentLabel || '전체 카테고리';
  if (categorySelectCurrentBtn) {
    categorySelectCurrentBtn.disabled = !state.browsingCategoryPath;
  }
  renderCategoryTrail();

  categoryPickerList.innerHTML = '';
  if (state.categoryLoading) {
    const loading = document.createElement('p');
    loading.className = 'category-picker__empty';
    loading.textContent = '카테고리를 불러오는 중입니다.';
    categoryPickerList.appendChild(loading);
    return;
  }
  if (!children.length) {
    const empty = document.createElement('p');
    empty.className = 'category-picker__empty';
    empty.textContent = '더 이상 하위 메뉴가 없습니다.';
    categoryPickerList.appendChild(empty);
    return;
  }

  children.forEach(node => {
    const hasChildren = Array.isArray(node.children) && node.children.length > 0;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'category-picker__item';
    if (node.key === state.selectedCategoryPath) {
      button.classList.add('is-selected');
    }

    const label = document.createElement('span');
    label.textContent = node.label;
    button.appendChild(label);

    const meta = document.createElement('em');
    meta.textContent = hasChildren ? '하위 메뉴 ›' : '선택';
    button.appendChild(meta);

    button.addEventListener('click', async event => {
      event.preventDefault();
      event.stopPropagation();
      if (hasChildren) {
        state.browsingCategoryPath = node.key;
        renderCategoryPicker();
        return;
      }
      await selectCategoryPath(node.key);
    });
    categoryPickerList.appendChild(button);
  });
}

function renderCategoryTrail() {
  categoryPickerTrail.innerHTML = '';

  const rootButton = document.createElement('button');
  rootButton.type = 'button';
  rootButton.textContent = '전체';
  rootButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    state.browsingCategoryPath = '';
    renderCategoryPicker();
  });
  categoryPickerTrail.appendChild(rootButton);

  if (!state.browsingCategoryPath) return;

  state.browsingCategoryPath.split('/').forEach((part, index, parts) => {
    const key = parts.slice(0, index + 1).join('/');
    const node = findCategoryNode(key);
    if (!node) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = node.label;
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      state.browsingCategoryPath = key;
      renderCategoryPicker();
    });
    categoryPickerTrail.appendChild(button);
  });
}

function toggleCategoryPicker() {
  if (!categoryPickerPanel || !categoryPickerBtn) return;
  const willOpen = categoryPickerPanel.hidden;
  if (willOpen) {
    state.browsingCategoryPath = state.selectedCategoryPath;
    renderCategoryPicker();
    if (!state.categoryTree.length && !state.categoryLoading) {
      loadCategoryTree().catch(() => renderCategoryFilters());
    }
  }
  categoryPickerPanel.hidden = !willOpen;
  if (categoryPickerBackdrop) {
    categoryPickerBackdrop.hidden = !willOpen;
  }
  categoryPickerBtn.setAttribute('aria-expanded', String(willOpen));
}

function closeCategoryPicker() {
  if (!categoryPickerPanel || !categoryPickerBtn) return;
  categoryPickerPanel.hidden = true;
  if (categoryPickerBackdrop) {
    categoryPickerBackdrop.hidden = true;
  }
  categoryPickerBtn.setAttribute('aria-expanded', 'false');
}

async function selectCategoryPath(path) {
  state.selectedCategoryPath = path || '';
  state.browsingCategoryPath = state.selectedCategoryPath;
  renderCategoryFilters();
  closeCategoryPicker();
  await loadSearchResults();
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

async function loadSavedListsForSelectedMonth({ autoLoad = false, preferredListId = null, clearWhenEmpty = false } = {}) {
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
    if (clearWhenEmpty) {
      clearActiveShoppingList();
    }
    updateListControlState();
    return;
  }

  state.savedLists.forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = item.title;
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
  const listId = shoppingListSelect ? shoppingListSelect.value : '';
  if (!listId) return;

  const payload = await requestJson(`/api/shopping/lists/${listId}`);
  applyShoppingList(payload);
}

async function saveCurrentShoppingList() {
  if (state.currentListId) {
    await requestJson(`/api/shopping/lists/${state.currentListId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget: state.budget }),
    });
    const updated = await replaceCurrentShoppingListItems();
    applyShoppingList(updated);
    return;
  }

  await createShoppingListFromCurrentState();
}

async function createShoppingListFromCurrentState() {
  const selected = getSelectedHistoryMonth() || getCurrentYearMonth();
  const nextSequence = state.savedLists.filter(item => (
    Number(item.target_year) === selected.year && Number(item.target_month) === selected.month
  )).length + 1;
  const payload = {
    title: `${formatDateTimeWithSeconds(new Date())} #${nextSequence}`,
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
  const listId = (shoppingListSelect ? shoppingListSelect.value : '') || state.currentListId;
  if (!listId) return;

  const selected = state.savedLists.find(item => item.id === listId);
  const label = (selected && selected.title) || state.currentListTitle || '선택한 리스트';
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

function clearActiveShoppingList() {
  state.currentListId = null;
  state.currentListTitle = '';
  state.currentListYear = null;
  state.currentListMonth = null;
  state.cart = [];
  state.budget = 0;
  if (budgetInput) {
    budgetInput.value = '';
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
  const query = searchInput ? searchInput.value : '';
  const category = state.selectedCategoryPath || '';
  const requestId = ++state.searchRequestId;
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
    if (category) params.set('category', category);
    if (refresh) params.set('refresh', 'true');
    const payload = await requestJson(`/api/shopping/search?${params.toString()}`);
    if (requestId !== state.searchRequestId) return;
    state.results = Array.isArray(payload.items) ? payload.items : [];
    state.fetchedAt = payload.fetched_at;
    state.totalCatalogCount = Number(payload.total_catalog_count) || 0;
    state.matchedCount = Number(payload.matched_count) || 0;
    state.mode = payload.mode || 'search';
    if (catalogStatus) {
      catalogStatus.textContent = payload.message || '공식몰 검색 결과를 불러왔습니다.';
    }
  } catch (error) {
    if (requestId !== state.searchRequestId) return;
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
  const query = searchInput && searchInput.value ? searchInput.value.trim() : '';
  const categoryLabel = getSelectedCategoryLabel();
  const results = state.results;

  if (resultsMeta) {
    const syncedText = state.fetchedAt
      ? `최근 동기화 ${new Date(state.fetchedAt).toLocaleString('ko-KR')}`
      : '최근 동기화 기록 없음';
    if (query || categoryLabel) {
      const scope = [categoryLabel, query ? `"${query}"` : ''].filter(Boolean).join(' · ');
      resultsMeta.textContent = `전체 상품 ${state.totalCatalogCount.toLocaleString('ko-KR')}개 중 ${state.matchedCount.toLocaleString('ko-KR')}개 매칭 · 현재 ${results.length}개 표시 · ${syncedText}`;
      if (scope) {
        resultsMeta.textContent = `${scope} · ${resultsMeta.textContent}`;
      }
    } else {
      resultsMeta.textContent = `전체 상품 ${state.totalCatalogCount.toLocaleString('ko-KR')}개 · 현재 ${results.length}개 표시 · ${syncedText}`;
    }
  }

  searchResults.innerHTML = '';
  if (!results.length) {
    searchResults.appendChild(buildEmptyState(query || categoryLabel ? '검색 결과가 없습니다. 다른 하위 카테고리나 키워드도 시도해보세요.' : '기본 노출 상품이 없습니다.'));
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
    const category = fragment.querySelector('[data-category]');
    const addBtn = fragment.querySelector('[data-add]');
    const openLink = fragment.querySelector('[data-open]');

    setImageOrPlaceholder(image, item.image_url, item.title);
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
    if (item.category_text) {
      category.hidden = false;
      category.textContent = item.category_text;
    } else {
      category.hidden = true;
      category.textContent = '';
    }

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
          : '검색 결과에서 상품을 담은 뒤 현재 리스트 저장 버튼으로 DB에 저장하세요.'
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

    setImageOrPlaceholder(image, item.image_url, item.title);
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
    });

    qty.addEventListener('input', () => {
      item.qty = Math.max(1, Number(qty.value) || 1);
      total.textContent = `소계 ${formatWon((item.price_value || 0) * item.qty)}`;
      saveCart();
      renderSummary();
    });
    qty.addEventListener('change', async () => {
      item.qty = Math.max(1, Number(qty.value) || 1);
      saveCart();
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
      saveCart();
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
      original_price: item.original_price_value || null,
      original_price_text: item.original_price_text || null,
      discount_amount: item.discount_value || null,
      discount_text: item.discount_text || null,
      discount_period_text: item.discount_period_text || null,
      member_only: Boolean(item.member_only),
    });
  }

  saveCart();
  render();
}

async function removeCartItem(item) {
  state.cart = state.cart.filter(entry => entry.id !== item.id);
  saveCart();
  render();
}

function findExistingCartEntry(item) {
  return state.cart.find(entry => {
    if (entry.costco_product_id && item.id && entry.costco_product_id === item.id) return true;
    if (entry.url && item.url && entry.url === item.url) return true;
    return normalize(entry.title) === normalize(item.title);
  });
}

async function replaceCurrentShoppingListItems() {
  if (!state.currentListId) return null;
  return requestJson(`/api/shopping/lists/${state.currentListId}/items`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state.cart.map((item, index) => serializeCartEntryForRequest(item, index))),
  });
}

function updateListControlState() {
  if (saveListBtn) {
    saveListBtn.textContent = state.currentListId ? '변경 저장' : '현재 리스트 저장';
  }
  if (deleteListBtn) {
    deleteListBtn.disabled = !shoppingListSelect || !shoppingListSelect.value;
  }
}

function getSelectedHistoryMonth() {
  if (!historyMonthSelect || !historyMonthSelect.value) return null;
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

function setImageOrPlaceholder(image, src, alt) {
  if (!image) return;
  image.alt = alt || '상품 이미지';
  image.classList.toggle('is-placeholder', !src);
  image.onerror = () => {
    image.onerror = null;
    image.classList.add('is-placeholder');
    image.src = PLACEHOLDER_IMAGE;
  };
  image.src = src || PLACEHOLDER_IMAGE;
}

function getSelectedCategoryLabel() {
  return getCategoryLabel(state.selectedCategoryPath);
}

function getCategoryLabel(path) {
  if (!path) return '';
  const labels = [];
  let nodes = state.categoryTree;
  path.split('/').forEach((part, index, parts) => {
    const key = parts.slice(0, index + 1).join('/');
    const node = nodes.find(item => item.key === key);
    if (!node) return;
    labels.push(node.label);
    nodes = Array.isArray(node.children) ? node.children : [];
  });
  return labels.join(' > ');
}

function findCategoryNode(path) {
  if (!path) return null;
  let nodes = state.categoryTree;
  let found = null;
  path.split('/').forEach((part, index, parts) => {
    if (!Array.isArray(nodes) || !nodes.length) return;
    const key = parts.slice(0, index + 1).join('/');
    found = nodes.find(item => item.key === key) || null;
    nodes = found && Array.isArray(found.children) ? found.children : [];
  });
  return found;
}

function formatWon(value) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`;
}

function formatDateTime(value) {
  if (!value) return '날짜 없음';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '날짜 없음';
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDateTimeWithSeconds(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '날짜 없음';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');
  return `${year}.${month}.${day} ${hour}:${minute}:${second}`;
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
