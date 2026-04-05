const API_BASE = '/api/recipes';

const form = document.getElementById('recipeForm');
const recipeList = document.getElementById('recipeList');
const emptyState = document.getElementById('emptyState');
const searchInput = document.getElementById('searchInput');
const sortSelect = document.getElementById('sortSelect');
const cuisineSelect = document.getElementById('cuisine');
const allFilterBtn = document.getElementById('allFilterBtn');
const cuisineFilterBtn = document.getElementById('cuisineFilterBtn');
const favoriteFilterBtn = document.getElementById('favoriteFilterBtn');
const cuisineFilterBar = document.getElementById('cuisineFilterBar');
const newRecipeBtn = document.getElementById('newRecipeBtn');
const resetBtn = document.getElementById('resetBtn');
const toggleFormBtn = document.getElementById('toggleFormBtn');
const refreshRecipesBtn = document.getElementById('refreshRecipesBtn');
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
const articleCache = new Map();
let ingredientDrafts = [];
let activeIngredientRecipeId = null;
let editingRecipeId = null;
let editingIngredientId = null;
let activeRecipeFilter = 'all';
let activeCuisineFilter = 'all';
const favoritePendingIds = new Set();
const expandedRecipeIds = new Set();
const CUISINE_LABELS = {
  korean: '한식',
  chinese: '중식',
  japanese: '일식',
  western: '양식',
  asian: '아시안',
  dessert: '디저트',
  snack: '간식',
  fusion: '퓨전',
  other: '기타',
  auto: '자동 분류',
};

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
    cuisine: data.get('cuisine'),
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

function setRecipeFilter(nextFilter) {
  activeRecipeFilter = nextFilter;
  if (allFilterBtn) {
    const isActive = nextFilter === 'all';
    allFilterBtn.classList.toggle('is-active', isActive);
    allFilterBtn.setAttribute('aria-pressed', String(isActive));
  }
  if (cuisineFilterBtn) {
    const isActive = nextFilter === 'cuisine';
    cuisineFilterBtn.classList.toggle('is-active', isActive);
    cuisineFilterBtn.setAttribute('aria-pressed', String(isActive));
  }
  if (favoriteFilterBtn) {
    const isActive = nextFilter === 'favorites';
    favoriteFilterBtn.classList.toggle('is-active', isActive);
    favoriteFilterBtn.setAttribute('aria-pressed', String(isActive));
  }
  if (cuisineFilterBar) {
    cuisineFilterBar.hidden = nextFilter !== 'cuisine';
  }
  render();
}

function setCuisineFilter(nextCuisine) {
  activeCuisineFilter = nextCuisine;
  if (cuisineFilterBar) {
    cuisineFilterBar.querySelectorAll('[data-cuisine-filter]').forEach(button => {
      const isActive = button.dataset.cuisineFilter === nextCuisine;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', String(isActive));
    });
  }
  if (activeRecipeFilter !== 'cuisine') {
    setRecipeFilter('cuisine');
    return;
  }
  render();
}

function focusForm() {
  const titleInput = document.getElementById('title');
  if (titleInput) titleInput.focus({ preventScroll: false });
}

function resetForm() {
  form.reset();
  if (cuisineSelect) cuisineSelect.value = 'auto';
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

function buildPreview(url, source, options = {}) {
  const { compact = false } = options;
  if (compact) {
    return buildCompactPreview(url, source);
  }
  if (source === 'youtube') {
    const embed = toYouTubeEmbed(url);
    if (embed) {
      const frame = document.createElement('div');
      frame.className = 'preview-frame';
      const iframe = document.createElement('iframe');
      iframe.src = embed;
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
      iframe.allowFullscreen = true;
      const label = document.createElement('span');
      label.className = 'preview-frame__label';
      label.textContent = sourceLabel(source);
      frame.appendChild(iframe);
      frame.appendChild(label);
      return frame;
    }
    return buildCompactPreview(url, source);
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

function buildCompactPreview(url, source) {
  const tile = document.createElement('div');
  tile.className = 'preview-tile';

  const label = document.createElement('span');
  label.className = 'preview-tile__label';
  label.textContent = sourceLabel(source);

  const site = document.createElement('span');
  site.className = 'preview-tile__site';
  site.textContent = safeDomain(url);

  const placeholder = document.createElement('div');
  placeholder.className = 'preview-tile__placeholder';
  placeholder.textContent = source === 'youtube' ? 'VIDEO' : 'LINK';

  tile.appendChild(placeholder);
  tile.appendChild(label);
  tile.appendChild(site);

  const youtubeThumb = toYouTubeThumbnail(url);
  if (youtubeThumb) {
    const img = document.createElement('img');
    img.src = youtubeThumb;
    img.alt = 'video thumbnail';
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';
    img.onerror = () => img.remove();
    tile.prepend(img);
    return tile;
  }

  loadPreview(url).then(meta => {
    if (!meta) return;
    if (meta.site) site.textContent = meta.site;
    if (meta.image) {
      const img = document.createElement('img');
      img.src = meta.image;
      img.alt = meta.title || 'link preview';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.onerror = () => img.remove();
      tile.prepend(img);
    }
  });

  return tile;
}

function toYouTubeEmbed(url) {
  const videoId = extractYouTubeId(url);
  return videoId ? `https://www.youtube.com/embed/${videoId}?playsinline=1&rel=0` : null;
}

function toYouTubeThumbnail(url) {
  const videoId = extractYouTubeId(url);
  return videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null;
}

function extractYouTubeId(url) {
  try {
    const u = new URL(url);
    if (!u.hostname.includes('youtube.com') && !u.hostname.includes('youtu.be')) return null;
    if (u.hostname === 'youtu.be') {
      return u.pathname.slice(1);
    }
    if (u.searchParams.get('v')) {
      return u.searchParams.get('v');
    }
    if (u.pathname.startsWith('/shorts/')) {
      return u.pathname.split('/')[2];
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
      expandedRecipeIds.delete(id);
      render();
    })
    .catch(err => alert(err.message));
}

function syncFavoriteButton(button, isFavorite, pending = false) {
  if (!button) return;
  button.textContent = isFavorite ? '★' : '☆';
  button.classList.toggle('is-active', Boolean(isFavorite));
  button.setAttribute('aria-pressed', String(Boolean(isFavorite)));
  button.setAttribute('aria-label', isFavorite ? '즐겨찾기 해제' : '즐겨찾기 추가');
}

function toggleFavorite(recipe, button) {
  if (favoritePendingIds.has(recipe.id)) return;

  const prevValue = Boolean(recipe.is_favorite);
  const nextValue = !prevValue;
  const recipeIndex = recipes.findIndex(item => item.id === recipe.id);
  if (recipeIndex >= 0) {
    recipes[recipeIndex] = { ...recipes[recipeIndex], is_favorite: nextValue };
    recipe = recipes[recipeIndex];
  } else {
    recipe.is_favorite = nextValue;
  }

  favoritePendingIds.add(recipe.id);
  if (activeRecipeFilter === 'favorites') {
    render();
  } else {
    syncFavoriteButton(button, nextValue, true);
  }

  fetch(`${API_BASE}/${recipe.id}/favorite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_favorite: nextValue }),
  })
    .then(async res => {
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || '즐겨찾기 변경 실패');
      }
      return res.json();
    })
    .then(updated => {
      if (recipeIndex >= 0) {
        recipes[recipeIndex] = { ...recipes[recipeIndex], ...updated };
      }
      favoritePendingIds.delete(recipe.id);
      if (activeRecipeFilter === 'favorites') {
        render();
      } else {
        syncFavoriteButton(button, Boolean(updated.is_favorite), false);
      }
    })
    .catch(err => {
      favoritePendingIds.delete(recipe.id);
      if (recipeIndex >= 0) {
        recipes[recipeIndex] = { ...recipes[recipeIndex], is_favorite: prevValue };
      } else {
        recipe.is_favorite = prevValue;
      }

      if (activeRecipeFilter === 'favorites') {
        render();
      } else {
        syncFavoriteButton(button, prevValue, false);
      }
      alert(err.message);
    });
}

function setRecipeExpanded(recipeId, expanded, root, details, toggleBtn) {
  if (expanded) {
    expandedRecipeIds.add(recipeId);
  } else {
    expandedRecipeIds.delete(recipeId);
  }
  if (root) root.classList.toggle('is-open', expanded);
  if (details) details.hidden = !expanded;
  if (toggleBtn) {
    toggleBtn.setAttribute('aria-expanded', String(expanded));
    toggleBtn.setAttribute('aria-label', expanded ? '상세 접기' : '상세 보기');
  }
}

function render() {
  const keyword = searchInput.value.trim().toLowerCase();
  const sortBy = sortSelect.value;

  let filtered = recipes.filter(r => {
    if (activeRecipeFilter === 'favorites' && !r.is_favorite) return false;
    if (activeRecipeFilter === 'cuisine' && activeCuisineFilter !== 'all' && r.cuisine !== activeCuisineFilter) return false;
    const haystack = [r.title, r.notes, r.cuisine, cuisineLabel(r.cuisine), r.tags.join(' '), (r.ingredients || []).map(i => i.name).join(' ')].join(' ').toLowerCase();
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

  if (emptyState) {
    if (activeRecipeFilter === 'favorites') {
      emptyState.textContent = '아직 즐겨찾기한 레시피가 없습니다.';
    } else if (activeRecipeFilter === 'cuisine') {
      emptyState.textContent = activeCuisineFilter === 'all'
        ? '아직 분류된 레시피가 없습니다.'
        : `${cuisineLabel(activeCuisineFilter)} 레시피가 없습니다.`;
    } else {
      emptyState.textContent = '아직 저장된 레시피가 없습니다. 위에 링크를 추가해보세요.';
    }
  }
  emptyState.style.display = filtered.length ? 'none' : 'block';
}

function buildRecipeCard(recipe) {
  const tpl = document.getElementById('recipeCardTemplate');
  const fragment = tpl.content.cloneNode(true);
  const root = fragment.querySelector('.recipe');
  const isExpanded = expandedRecipeIds.has(recipe.id);
  const tags = Array.isArray(recipe.tags) ? recipe.tags.filter(Boolean) : [];
  const notes = (recipe.notes || '').trim();
  const ingredients = Array.isArray(recipe.ingredients)
    ? recipe.ingredients.filter(ing => ing && String(ing.name || '').trim())
    : [];

  fragment.querySelector('[data-title]').textContent = recipe.title;
  const cuisinePill = fragment.querySelector('[data-cuisine-pill]');
  const cuisineText = cuisineLabel(recipe.cuisine);
  if (cuisinePill) {
    if (cuisineText) {
      cuisinePill.textContent = cuisineText;
      cuisinePill.hidden = false;
      cuisinePill.className = `recipe__cuisine recipe__cuisine--${recipe.cuisine || 'other'}`;
    } else {
      cuisinePill.hidden = true;
    }
  }
  const favoriteBtn = fragment.querySelector('[data-toggle-favorite]');
  if (favoriteBtn) {
    syncFavoriteButton(favoriteBtn, Boolean(recipe.is_favorite), favoritePendingIds.has(recipe.id));
    favoriteBtn.addEventListener('click', () => toggleFavorite(recipe, favoriteBtn));
  }
  const metaBlock = fragment.querySelector('[data-meta-block]');
  const tagsEl = fragment.querySelector('[data-tags]');
  if (metaBlock && tagsEl) {
    if (tags.length) {
      tagsEl.textContent = `#${tags.join(' #')}`;
      tagsEl.hidden = false;
      metaBlock.hidden = false;
    } else {
      tagsEl.textContent = '';
      tagsEl.hidden = true;
      metaBlock.hidden = true;
    }
  }

  const notesEl = fragment.querySelector('[data-notes]');
  if (notesEl) {
    if (notes) {
      notesEl.textContent = notes;
      notesEl.hidden = false;
    } else {
      notesEl.hidden = true;
    }
  }

  const preview = fragment.querySelector('[data-preview]');
  const previewEl = recipe.source === 'youtube'
    ? buildPreview(recipe.url, recipe.source)
    : buildPreview(recipe.url, recipe.source, { compact: true });
  preview.appendChild(previewEl);
  if (recipe.source === 'blog') {
    preview.classList.add('recipe__preview--clickable');
    preview.setAttribute('role', 'link');
    preview.setAttribute('tabindex', '0');
    preview.setAttribute('aria-label', `${recipe.title} 원문 보기`);
    preview.addEventListener('click', () => openLink(recipe.url));
    preview.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openLink(recipe.url);
      }
    });
  }

  const details = fragment.querySelector('[data-details]');
  const contentEl = fragment.querySelector('[data-content]');
  const toggleBtn = fragment.querySelector('[data-toggle-details]');
  if (toggleBtn) {
    setRecipeExpanded(recipe.id, isExpanded, root, details, toggleBtn);
    toggleBtn.addEventListener('click', () => {
      const next = !expandedRecipeIds.has(recipe.id);
      setRecipeExpanded(recipe.id, next, root, details, toggleBtn);
      if (next) ensureRecipeContent(contentEl);
    });
  }

  fragment.querySelector('[data-open]').addEventListener('click', () => openLink(recipe.url));
  fragment.querySelector('[data-delete]').addEventListener('click', () => deleteRecipe(recipe.id));
  const editBtn = fragment.querySelector('[data-edit]');
  if (editBtn) editBtn.addEventListener('click', () => openRecipeEditor(recipe));
  const ingListEl = fragment.querySelector('[data-ingredients]');
  const ingredientsSection = fragment.querySelector('[data-ingredients-section]');
  const addIngBtn = fragment.querySelector('[data-add-ingredient]');
  if (ingListEl) {
    ingListEl.innerHTML = '';
    ingredients.forEach(ing => {
      const li = document.createElement('li');
      li.textContent = ing.amount ? `${ing.name} - ${ing.amount}` : ing.name;
      ingListEl.appendChild(li);
    });
  }
  if (ingredientsSection) {
    ingredientsSection.hidden = ingredients.length === 0;
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

function cuisineLabel(cuisine) {
  return CUISINE_LABELS[cuisine] || '';
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

async function loadArticle(url) {
  if (articleCache.has(url)) return articleCache.get(url);
  const promise = fetch(`/api/article?url=${encodeURIComponent(url)}`)
    .then(res => res.ok ? res.json() : null)
    .catch(() => null);
  articleCache.set(url, promise);
  return promise;
}

function buildArticleViewer(url) {
  const viewer = document.createElement('section');
  viewer.className = 'article-viewer';

  const status = document.createElement('p');
  status.className = 'article-viewer__status';
  status.textContent = '본문을 불러오는 중...';
  viewer.appendChild(status);

  loadArticle(url).then(article => {
    viewer.innerHTML = '';
    const paragraphs = article?.paragraphs || [];
    if (!article || (!article.title && !paragraphs.length && !article.description && !article.snippet)) {
      const empty = document.createElement('p');
      empty.className = 'article-viewer__status';
      empty.textContent = '이 링크는 앱 안에서 본문을 읽기 어렵습니다.';
      viewer.appendChild(empty);
      return;
    }

    if (article.image) {
      const hero = document.createElement('img');
      hero.className = 'article-viewer__image';
      hero.src = article.image;
      hero.alt = article.title || 'article image';
      hero.loading = 'lazy';
      hero.referrerPolicy = 'no-referrer';
      hero.onerror = () => hero.remove();
      viewer.appendChild(hero);
    }

    if (article.title) {
      const title = document.createElement('h4');
      title.className = 'article-viewer__title';
      title.textContent = article.title;
      viewer.appendChild(title);
    }

    const subtitleText = article.description || article.snippet || '';
    if (subtitleText) {
      const subtitle = document.createElement('p');
      subtitle.className = 'article-viewer__subtitle';
      subtitle.textContent = subtitleText;
      viewer.appendChild(subtitle);
    }

    if (paragraphs.length) {
      const body = document.createElement('div');
      body.className = 'article-viewer__body';
      paragraphs.forEach(text => {
        const p = document.createElement('p');
        p.textContent = text;
        body.appendChild(p);
      });
      viewer.appendChild(body);
    }

    const footer = document.createElement('div');
    footer.className = 'article-viewer__footer';

    const site = document.createElement('span');
    site.className = 'article-viewer__site';
    site.textContent = article.site || safeDomain(url);

    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = 'btn btn-ghost';
    openBtn.textContent = '원문 열기';
    openBtn.addEventListener('click', () => openLink(url));

    footer.appendChild(site);
    footer.appendChild(openBtn);
    viewer.appendChild(footer);
  });

  return viewer;
}

function ensureRecipeContent(contentEl) {
  if (!contentEl) return;
  contentEl.hidden = true;
  contentEl.replaceChildren();
  delete contentEl.dataset.loaded;
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
  if (cuisineSelect) cuisineSelect.value = recipe.cuisine || 'auto';
  ingredientDrafts = (recipe.ingredients || []).map(ing => ({ name: ing.name, amount: ing.amount || '' }));
  renderIngredientDrafts();
  updateRecipeDrawerCopy(true);
  openDrawer(false);
}

function updateRecipeDrawerCopy(isEdit) {
  if (recipeDrawerEyebrow) recipeDrawerEyebrow.textContent = isEdit ? '레시피 수정' : '레시피 등록';
  if (recipeDrawerTitle) recipeDrawerTitle.textContent = '';
}

function initPullToRefresh() {
  if (document.documentElement.dataset.variant !== 'mobile') return;

  const indicator = document.createElement('div');
  indicator.className = 'pull-refresh-indicator';
  indicator.textContent = '당겨서 새로고침';
  document.body.appendChild(indicator);

  let tracking = false;
  let startY = 0;
  let pullDistance = 0;

  const resetIndicator = () => {
    indicator.classList.remove('is-visible', 'is-ready');
    indicator.style.removeProperty('--pull-offset');
  };

  const shouldIgnoreTarget = target => (
    target instanceof Element &&
    Boolean(target.closest('input, textarea, select, button, a, .drawer__panel'))
  );

  window.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) return;
    if (window.scrollY > 0) return;
    if (drawer?.classList.contains('open') || ingDrawer?.classList.contains('open')) return;
    if (shouldIgnoreTarget(event.target)) return;

    tracking = true;
    startY = event.touches[0].clientY;
    pullDistance = 0;
    resetIndicator();
  }, { passive: true });

  window.addEventListener('touchmove', event => {
    if (!tracking) return;
    pullDistance = Math.max(0, event.touches[0].clientY - startY);
    if (pullDistance <= 0) {
      resetIndicator();
      return;
    }

    const offset = Math.min(pullDistance * 0.45, 72);
    indicator.classList.add('is-visible');
    indicator.style.setProperty('--pull-offset', `${offset}px`);

    if (pullDistance >= 90) {
      indicator.classList.add('is-ready');
      indicator.textContent = '놓으면 새로고침';
    } else {
      indicator.classList.remove('is-ready');
      indicator.textContent = '당겨서 새로고침';
    }
  }, { passive: true });

  window.addEventListener('touchend', () => {
    if (!tracking) return;

    const shouldRefresh = window.scrollY === 0 && pullDistance >= 90;
    tracking = false;

    if (shouldRefresh) {
      indicator.classList.add('is-visible');
      indicator.classList.remove('is-ready');
      indicator.textContent = '새로고침 중...';
      indicator.style.setProperty('--pull-offset', '48px');
      window.location.reload();
      return;
    }

    resetIndicator();
  }, { passive: true });

  window.addEventListener('touchcancel', () => {
    tracking = false;
    resetIndicator();
  }, { passive: true });
}

function initDesktopRecipeWheelScroll() {
  if (document.documentElement.dataset.variant !== 'pc') return;
  if (!recipeList) return;

  const shouldIgnoreTarget = target => (
    target instanceof Element &&
    Boolean(target.closest('input, textarea, select, button, a, .drawer__panel'))
  );

  window.addEventListener('wheel', event => {
    if (drawer?.classList.contains('open') || ingDrawer?.classList.contains('open')) return;
    if (shouldIgnoreTarget(event.target)) return;

    const canScroll = recipeList.scrollHeight > recipeList.clientHeight;
    if (!canScroll) return;

    const { scrollTop, scrollHeight, clientHeight } = recipeList;
    const nextScrollTop = scrollTop + event.deltaY;
    const atTop = scrollTop <= 0 && event.deltaY < 0;
    const atBottom = scrollTop + clientHeight >= scrollHeight - 1 && event.deltaY > 0;

    if (atTop || atBottom) return;

    recipeList.scrollTop = nextScrollTop;
    event.preventDefault();
  }, { passive: false });
}

function initDesktopRecipeAutoScroll() {
  if (document.documentElement.dataset.variant !== 'pc') return;
  if (!recipeList) return;

  const shouldIgnoreTarget = target => (
    target instanceof Element &&
    Boolean(target.closest('input, textarea, select, button, a, .drawer__panel'))
  );

  let active = false;
  let anchorY = 0;
  let pointerY = 0;
  let frameId = 0;

  const stop = () => {
    active = false;
    if (frameId) {
      cancelAnimationFrame(frameId);
      frameId = 0;
    }
    document.body.classList.remove('pc-autoscroll-active');
  };

  const tick = () => {
    if (!active) return;

    const delta = pointerY - anchorY;
    if (Math.abs(delta) > 8) {
      const maxStep = 28;
      const step = Math.max(-maxStep, Math.min(maxStep, delta * 0.12));
      const nextScrollTop = recipeList.scrollTop + step;
      const maxScrollTop = recipeList.scrollHeight - recipeList.clientHeight;
      recipeList.scrollTop = Math.max(0, Math.min(maxScrollTop, nextScrollTop));
    }

    frameId = requestAnimationFrame(tick);
  };

  window.addEventListener('mousedown', event => {
    if (event.button !== 1) return;
    if (drawer?.classList.contains('open') || ingDrawer?.classList.contains('open')) return;
    if (shouldIgnoreTarget(event.target)) return;
    if (recipeList.scrollHeight <= recipeList.clientHeight) return;

    event.preventDefault();

    if (active) {
      stop();
      return;
    }

    active = true;
    anchorY = event.clientY;
    pointerY = event.clientY;
    document.body.classList.add('pc-autoscroll-active');
    frameId = requestAnimationFrame(tick);
  });

  window.addEventListener('mousemove', event => {
    if (!active) return;
    pointerY = event.clientY;
  });

  window.addEventListener('mousedown', event => {
    if (!active) return;
    if (event.button !== 1) stop();
  });

  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') stop();
  });

  window.addEventListener('blur', stop);
}

form.addEventListener('submit', handleSubmit);
searchInput.addEventListener('input', handleSearch);
sortSelect.addEventListener('change', handleSort);
if (allFilterBtn) allFilterBtn.addEventListener('click', () => setRecipeFilter('all'));
if (cuisineFilterBtn) cuisineFilterBtn.addEventListener('click', () => setRecipeFilter('cuisine'));
if (favoriteFilterBtn) favoriteFilterBtn.addEventListener('click', () => setRecipeFilter('favorites'));
if (cuisineFilterBar) {
  cuisineFilterBar.addEventListener('click', event => {
    const button = event.target.closest('[data-cuisine-filter]');
    if (!button) return;
    setCuisineFilter(button.dataset.cuisineFilter || 'all');
  });
}
if (newRecipeBtn) newRecipeBtn.addEventListener('click', () => openDrawer(true));
resetBtn.addEventListener('click', resetForm);
if (refreshRecipesBtn) refreshRecipesBtn.addEventListener('click', () => window.location.reload());
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

setRecipeFilter('all');
initPullToRefresh();
initDesktopRecipeWheelScroll();
initDesktopRecipeAutoScroll();
fetchRecipes().catch(err => alert(err.message));
renderIngredientDrafts();
