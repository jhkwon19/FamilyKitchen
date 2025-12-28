const API_BASE = '/api/recipes';

const form = document.getElementById('recipeForm');
const recipeList = document.getElementById('recipeList');
const emptyState = document.getElementById('emptyState');
const searchInput = document.getElementById('searchInput');
const sortSelect = document.getElementById('sortSelect');
const newRecipeBtn = document.getElementById('newRecipeBtn');
const resetBtn = document.getElementById('resetBtn');
const toggleFormBtn = document.getElementById('toggleFormBtn');
const drawer = document.getElementById('drawer');
const drawerBackdrop = document.getElementById('drawerBackdrop');
const closeDrawerBtn = document.getElementById('closeDrawerBtn');
const ingInput = document.getElementById('ingredientInput');
const ingAmountInput = document.getElementById('ingredientAmount');
const ingAddBtn = document.getElementById('addIngredientBtn');
const ingList = document.getElementById('ingredientList');
const ingDrawer = document.getElementById('ingredientDrawer');
const ingDrawerBackdrop = document.getElementById('ingDrawerBackdrop');
const closeIngDrawerBtn = document.getElementById('closeIngDrawerBtn');
const ingModalName = document.getElementById('ingModalName');
const ingModalAmount = document.getElementById('ingModalAmount');
const ingModalAddBtn = document.getElementById('ingModalAddBtn');
const ingModalList = document.getElementById('ingModalList');
const recipeDrawerEyebrow = document.getElementById('recipeDrawerEyebrow');
const recipeDrawerTitle = document.getElementById('recipeDrawerTitle');

let recipes = [];
const previewCache = new Map();
let ingredientDrafts = [];
let activeIngredientRecipeId = null;
let editingRecipeId = null;
let editingIngredientId = null;

async function fetchRecipes() {
  const res = await fetch(API_BASE);
  if (!res.ok) throw new Error('목록을 불러오지 못했습니다.');
  recipes = await res.json();
  render();
}

function handleSubmit(event) {
  event.preventDefault();
  const data = new FormData(form);
  const payload = {
    title: data.get('title').trim(),
    url: data.get('url').trim(),
    notes: data.get('notes').trim(),
    tags: data.get('tags').split(',').map(t => t.trim()).filter(Boolean),
    source: data.get('source'),
    ingredients: ingredientDrafts.map(({ name, amount }) => ({ name, amount })),
  };

  const isEdit = Boolean(editingRecipeId);
  const method = isEdit ? 'PUT' : 'POST';
  const targetUrl = isEdit ? `${API_BASE}/${editingRecipeId}` : API_BASE;

  // only include ingredients on create
  if (isEdit) {
    payload.ingredients = [];
  }

  fetch(targetUrl, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(async res => {
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || '저장 실패');
      }
      return res.json();
    })
    .then(created => {
      if (isEdit) {
        const idx = recipes.findIndex(r => r.id === editingRecipeId);
        if (idx >= 0) {
          recipes[idx] = { ...recipes[idx], ...created };
        }
      } else {
        recipes.unshift(created);
      }
      render();
      form.reset();
      ingredientDrafts = [];
      renderIngredientDrafts();
      closeDrawer();
      editingRecipeId = null;
    })
    .catch(err => {
      alert('저장 실패: ' + err.message);
    });
}

function handleSearch() {
  render();
}

function handleSort() {
  render();
}

function focusForm() {
  const titleInput = document.getElementById('title');
  if (titleInput) titleInput.focus({ preventScroll: false });
}

function resetForm() {
  form.reset();
  focusForm();
  ingredientDrafts = [];
  renderIngredientDrafts();
  editingRecipeId = null;
  updateRecipeDrawerCopy(false);
}

function addIngredientDraft() {
  const name = ingInput.value.trim();
  const amount = ingAmountInput.value.trim();
  if (!name) return;
  ingredientDrafts.push({ name, amount: amount || '' });
  ingInput.value = '';
  ingAmountInput.value = '';
  renderIngredientDrafts();
  ingInput.focus();
}

function removeIngredientDraft(idx) {
  ingredientDrafts.splice(idx, 1);
  renderIngredientDrafts();
}

function renderIngredientDrafts() {
  if (!ingList) return;
  ingList.innerHTML = '';
  ingredientDrafts.forEach((ing, idx) => {
    const li = document.createElement('li');
    li.textContent = ing.amount ? `${ing.name} - ${ing.amount}` : ing.name;
    const btn = document.createElement('button');
    btn.textContent = '삭제';
    btn.className = 'icon-btn';
    btn.addEventListener('click', () => removeIngredientDraft(idx));
    li.appendChild(btn);
    ingList.appendChild(li);
  });
}
function openDrawer(shouldReset = false) {
  if (!drawer) return;
  if (shouldReset) {
    form.reset();
    ingredientDrafts = [];
    renderIngredientDrafts();
    editingRecipeId = null;
    updateRecipeDrawerCopy(false);
  }
  drawer.classList.add('open');
  setTimeout(() => focusForm(), 50);
}

function closeDrawer() {
  if (!drawer) return;
  drawer.classList.remove('open');
  editingRecipeId = null;
  updateRecipeDrawerCopy(false);
}

function buildPreview(url, source) {
  if (source === 'youtube') {
    const embed = toYouTubeEmbed(url);
    if (embed) {
      const iframe = document.createElement('iframe');
      iframe.src = embed;
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
      iframe.allowFullscreen = true;
      return iframe;
    }
  }
  const container = document.createElement('div');
  container.className = 'link-preview';
  const top = document.createElement('div');
  top.className = 'link-preview__top';
  const titleEl = document.createElement('div');
  titleEl.className = 'link-preview__title';
  const descEl = document.createElement('p');
  descEl.className = 'link-preview__desc';
  const snippetEl = document.createElement('p');
  snippetEl.className = 'link-preview__snippet';
  const imgWrap = document.createElement('div');
  imgWrap.className = 'link-preview__image';
  const domainEl = document.createElement('span');
  domainEl.className = 'link-preview__domain';
  const openBtn = document.createElement('button');
  openBtn.className = 'btn btn-ghost';
  openBtn.textContent = '링크 열기';
  openBtn.addEventListener('click', () => openLink(url));

  titleEl.textContent = '블로그 링크';
  descEl.textContent = '';
  domainEl.textContent = safeDomain(url);

  top.appendChild(titleEl);
  top.appendChild(domainEl);
  container.appendChild(top);
  container.appendChild(descEl);
  container.appendChild(snippetEl);
  container.appendChild(imgWrap);
  container.appendChild(openBtn);

  loadPreview(url).then(meta => {
    if (!meta) return;
    if (meta.title) titleEl.textContent = meta.title;
    if (meta.description) descEl.textContent = meta.description;
    if (meta.site) domainEl.textContent = meta.site;
    let snippetText = meta.snippet || '';
    if (snippetText && meta.description && snippetText.trim() === meta.description.trim()) {
      snippetText = '';
    }
    if (!meta.description && snippetText) {
      descEl.textContent = snippetText;
      snippetText = '';
    }
    if (!descEl.textContent) descEl.remove();
    if (snippetText) {
      snippetEl.textContent = snippetText;
    } else {
      snippetEl.remove();
    }
    if (meta.image) {
      const img = document.createElement('img');
      img.src = meta.image;
      img.alt = meta.title || 'preview';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.onerror = () => imgWrap.remove();
      imgWrap.appendChild(img);
    } else {
      imgWrap.remove();
    }
  });

  return container;
}

function toYouTubeEmbed(url) {
  try {
    const u = new URL(url);
    if (!u.hostname.includes('youtube.com') && !u.hostname.includes('youtu.be')) return null;
    if (u.hostname === 'youtu.be') {
      return `https://www.youtube.com/embed/${u.pathname.slice(1)}`;
    }
    if (u.searchParams.get('v')) {
      return `https://www.youtube.com/embed/${u.searchParams.get('v')}`;
    }
    if (u.pathname.startsWith('/shorts/')) {
      return `https://www.youtube.com/embed/${u.pathname.split('/')[2]}`;
    }
    return null;
  } catch (err) {
    console.error('Embed parse failed', err);
    return null;
  }
}

function copyText(text) {
  return navigator.clipboard.writeText(text);
}

function openLink(url) {
  window.open(url, '_blank', 'noopener');
}

function shareRecipe(recipe) {
  const message = `${recipe.title}\n${recipe.url}\n${recipe.notes || ''}`;
  if (navigator.share) {
    navigator.share({ title: recipe.title, text: recipe.notes, url: recipe.url }).catch(() => {});
  } else {
    copyText(message).then(() => alert('클립보드에 복사되었습니다.'));
  }
}

function deleteRecipe(id) {
  if (!confirm('정말 삭제할까요?')) return;
  fetch(`${API_BASE}/${id}`, { method: 'DELETE' })
    .then(res => {
      if (!res.ok) throw new Error('삭제 실패');
      recipes = recipes.filter(r => r.id !== id);
      render();
    })
    .catch(err => alert(err.message));
}

function render() {
  const keyword = searchInput.value.trim().toLowerCase();
  const sortBy = sortSelect.value;

  let filtered = recipes.filter(r => {
    const haystack = [r.title, r.notes, r.tags.join(' '), (r.ingredients || []).map(i => i.name).join(' ')].join(' ').toLowerCase();
    return haystack.includes(keyword);
  });

  filtered.sort((a, b) => {
    if (sortBy === 'title') return a.title.localeCompare(b.title);
    if (sortBy === 'oldest') return new Date(a.created_at) - new Date(b.created_at);
    return new Date(b.created_at) - new Date(a.created_at);
  });

  recipeList.innerHTML = '';
  filtered.forEach(recipe => {
    const card = buildRecipeCard(recipe);
    recipeList.appendChild(card);
  });

  emptyState.style.display = filtered.length ? 'none' : 'block';
}

function buildRecipeCard(recipe) {
  const tpl = document.getElementById('recipeCardTemplate');
  const fragment = tpl.content.cloneNode(true);
  const root = fragment.querySelector('.recipe');

  const sourceBadge = fragment.querySelector('[data-source]');
  sourceBadge.textContent = sourceLabel(recipe.source);

  fragment.querySelector('[data-title]').textContent = recipe.title;
  fragment.querySelector('[data-tags]').textContent = recipe.tags.length ? `#${recipe.tags.join(' #')}` : '태그 없음';
  fragment.querySelector('[data-notes]').textContent = recipe.notes || '메모 없음';

  const preview = fragment.querySelector('[data-preview]');
  preview.appendChild(buildPreview(recipe.url, recipe.source));

  fragment.querySelector('[data-open]').addEventListener('click', () => openLink(recipe.url));
  fragment.querySelector('[data-delete]').addEventListener('click', () => deleteRecipe(recipe.id));
  const editBtn = fragment.querySelector('[data-edit]');
  if (editBtn) editBtn.addEventListener('click', () => openRecipeEditor(recipe));
  const ingListEl = fragment.querySelector('[data-ingredients]');
  const addIngBtn = fragment.querySelector('[data-add-ingredient]');
  if (ingListEl) {
    ingListEl.innerHTML = '';
    (recipe.ingredients || []).forEach(ing => {
      const li = document.createElement('li');
      li.textContent = ing.amount ? `${ing.name} - ${ing.amount}` : ing.name;
      ingListEl.appendChild(li);
    });
  }
  if (addIngBtn) {
    addIngBtn.addEventListener('click', () => openIngredientDrawer(recipe));
  }

  return fragment;
}

function sourceLabel(source) {
  switch (source) {
    case 'youtube': return 'YouTube';
    case 'blog': return '블로그';
    case 'instagram': return '인스타';
    default: return '기타';
  }
}

function safeDomain(url) {
  try {
    return new URL(url).host;
  } catch {
    return '링크';
  }
}

async function loadPreview(url) {
  if (previewCache.has(url)) return previewCache.get(url);
  const promise = fetch(`/api/preview?url=${encodeURIComponent(url)}`)
    .then(res => res.ok ? res.json() : null)
    .catch(() => null);
  previewCache.set(url, promise);
  return promise;
}

function addIngredient(recipeId) {
  // kept for backward compatibility; now modal is used
  openIngredientDrawer(recipes.find(r => r.id === recipeId));
}

function openIngredientDrawer(recipe) {
  activeIngredientRecipeId = recipe.id;
  renderIngredientModalList(recipe);
  if (ingModalName) ingModalName.value = '';
  if (ingModalAmount) ingModalAmount.value = '';
  editingIngredientId = null;
  if (ingModalAddBtn) ingModalAddBtn.textContent = '추가';
  if (ingDrawer) ingDrawer.classList.add('open');
  setTimeout(() => ingModalName && ingModalName.focus(), 50);
}

function closeIngredientDrawer() {
  activeIngredientRecipeId = null;
  editingIngredientId = null;
  if (ingModalAddBtn) ingModalAddBtn.textContent = '추가';
  if (ingDrawer) ingDrawer.classList.remove('open');
}

function renderIngredientModalList(recipe) {
  if (!ingModalList) return;
  ingModalList.innerHTML = '';
  (recipe.ingredients || []).forEach(ing => {
    const li = document.createElement('li');
    const text = document.createElement('span');
    text.textContent = ing.amount ? `${ing.name} - ${ing.amount}` : ing.name;
    const actions = document.createElement('div');
    actions.className = 'ingredient-actions';
    const editBtn = document.createElement('button');
    editBtn.className = 'icon-btn';
    editBtn.textContent = '✎';
    editBtn.addEventListener('click', () => startEditIngredient(ing));
    const delBtn = document.createElement('button');
    delBtn.className = 'icon-btn';
    delBtn.textContent = '🗑️';
    delBtn.addEventListener('click', () => deleteIngredient(ing));
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    li.appendChild(text);
    li.appendChild(actions);
    ingModalList.appendChild(li);
  });
}

function submitIngredientFromModal() {
  if (!activeIngredientRecipeId) return;
  const name = ingModalName.value.trim();
  const amount = ingModalAmount.value.trim();
  if (!name) return;
  const isEdit = Boolean(editingIngredientId);
  const targetUrl = isEdit
    ? `/api/ingredients/${editingIngredientId}`
    : `${API_BASE}/${activeIngredientRecipeId}/ingredients`;
  const method = isEdit ? 'PUT' : 'POST';

  fetch(targetUrl, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, amount }),
  })
    .then(async res => {
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || '재료 추가 실패');
      }
      return res.json();
    })
    .then(ing => {
      const target = recipes.find(r => r.id === activeIngredientRecipeId);
      if (target) {
        target.ingredients = target.ingredients || [];
        if (isEdit) {
          const idx = target.ingredients.findIndex(x => x.id === ing.id);
          if (idx >= 0) target.ingredients[idx] = ing;
        } else {
          target.ingredients.push(ing);
        }
        render();
        renderIngredientModalList(target);
      } else {
        fetchRecipes();
      }
      ingModalName.value = '';
      ingModalAmount.value = '';
      editingIngredientId = null;
      if (ingModalAddBtn) ingModalAddBtn.textContent = '추가';
      ingModalName.focus();
    })
    .catch(err => alert(err.message));
}

function startEditIngredient(ing) {
  editingIngredientId = ing.id;
  if (ingModalName) ingModalName.value = ing.name;
  if (ingModalAmount) ingModalAmount.value = ing.amount || '';
  if (ingModalAddBtn) ingModalAddBtn.textContent = '수정';
  ingModalName.focus();
}

function deleteIngredient(ing) {
  if (!confirm('재료를 삭제할까요?')) return;
  fetch(`/api/ingredients/${ing.id}`, { method: 'DELETE' })
    .then(res => {
      if (!res.ok) throw new Error('삭제 실패');
      const target = recipes.find(r => r.id === activeIngredientRecipeId);
      if (target) {
        target.ingredients = (target.ingredients || []).filter(x => x.id !== ing.id);
        render();
        renderIngredientModalList(target);
      } else {
        fetchRecipes();
      }
      editingIngredientId = null;
      if (ingModalAddBtn) ingModalAddBtn.textContent = '추가';
    })
    .catch(err => alert(err.message));
}

function openRecipeEditor(recipe) {
  editingRecipeId = recipe.id;
  document.getElementById('title').value = recipe.title;
  document.getElementById('url').value = recipe.url;
  document.getElementById('notes').value = recipe.notes || '';
  document.getElementById('tags').value = recipe.tags.join(', ');
  document.getElementById('source').value = recipe.source || 'other';
  ingredientDrafts = (recipe.ingredients || []).map(ing => ({ name: ing.name, amount: ing.amount || '' }));
  renderIngredientDrafts();
  updateRecipeDrawerCopy(true);
  openDrawer(false);
}

function updateRecipeDrawerCopy(isEdit) {
  if (recipeDrawerEyebrow) recipeDrawerEyebrow.textContent = isEdit ? '레시피 수정' : '레시피 등록';
  if (recipeDrawerTitle) recipeDrawerTitle.textContent = '';
}

form.addEventListener('submit', handleSubmit);
searchInput.addEventListener('input', handleSearch);
sortSelect.addEventListener('change', handleSort);
if (newRecipeBtn) newRecipeBtn.addEventListener('click', () => openDrawer(true));
resetBtn.addEventListener('click', resetForm);
if (toggleFormBtn) toggleFormBtn.addEventListener('click', () => openDrawer(true));
if (drawerBackdrop) drawerBackdrop.addEventListener('click', closeDrawer);
if (closeDrawerBtn) closeDrawerBtn.addEventListener('click', closeDrawer);
if (ingAddBtn) ingAddBtn.addEventListener('click', addIngredientDraft);
if (ingModalAddBtn) ingModalAddBtn.addEventListener('click', submitIngredientFromModal);
if (ingDrawerBackdrop) ingDrawerBackdrop.addEventListener('click', closeIngredientDrawer);
if (closeIngDrawerBtn) closeIngDrawerBtn.addEventListener('click', closeIngredientDrawer);
window.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeDrawer();
    closeIngredientDrawer();
  }
});

fetchRecipes().catch(err => alert(err.message));
renderIngredientDrafts();
