// app.js
// Gümüş Veteriner sitesinin tüm etkileşimli JavaScript kodları burada bulunur.
// Sayfa geçişleri, sepet, ürün yükleme, giriş/kayıt, profil, sipariş, ödeme ve admin paneli bu dosyadan yönetilir.

// Bu script blogu sitenin tum etkilesimli kisimlarini yonetir:
// - Sepet islemleri
// - API'den urunleri cekme
// - Randevu, iletisim, uye kayit ve giris formlari
// - Profil adres/hayvan islemleri
// - Siparis ve odeme akisi
// - Admin paneli ve sayfa gecisleri
// ── Ürün verisi API'den gelir ────────────────────────────────────────────────
// -----------------------------------------------------------------------------
// Okuma notu
// -----------------------------------------------------------------------------
// Bu dosyanin ustundeki eski yorumlar projenin ilk halinden kaldi. Asil akisi
// su sekilde dusun: once global durumlar kurulur, sonra sepet/urun/profil
// fonksiyonlari gelir, en sonda da sayfa gecislerini yoneten go() fonksiyonu var.
let PRODUCTS = [];
let currentUser = JSON.parse(localStorage.getItem('gvUser') || sessionStorage.getItem('gvUser') || 'null');
let userToken = localStorage.getItem('gvUserToken') || sessionStorage.getItem('gvUserToken') || '';
let adminToken = localStorage.getItem('gvAdminToken') || sessionStorage.getItem('gvAdminToken') || '';
let PROFILE = {addresses:[], pets:[]};
let PENDING_ORDER = null;
let SITE_REVIEWS = [];
document.documentElement.dataset.theme=localStorage.getItem('gvTheme') || 'light';

window.addEventListener('load',()=>setTimeout(()=>document.getElementById('loader').classList.add('done'),650));
document.addEventListener('mousemove',event=>{
  document.documentElement.style.setProperty('--mx',`${event.clientX}px`);
  document.documentElement.style.setProperty('--my',`${event.clientY}px`);
  const glow=document.getElementById('cursorGlow');
  glow.style.left=`${event.clientX}px`;glow.style.top=`${event.clientY}px`;
  document.querySelectorAll('.animal-face.look').forEach(face=>{
    const rect=face.getBoundingClientRect();
    const x=Math.max(-6,Math.min(6,(event.clientX-(rect.left+rect.width/2))/28));
    const y=Math.max(-5,Math.min(5,(event.clientY-(rect.top+rect.height/2))/34));
    face.style.setProperty('--eye-x',`${x}px`);
    face.style.setProperty('--eye-y',`${y}px`);
  });
});

function toast(message,type='ok'){
  // Sayfanin sag altinda kisa basari/hata bildirimi gosterir.
  const wrap=document.getElementById('toastWrap');
  const item=document.createElement('div');
  item.className='toast';
  item.textContent=(type==='err'?'⚠️ ':'✅ ')+message;
  wrap.appendChild(item);
  setTimeout(()=>item.remove(),3200);
}
function toggleTheme(){
  const next=document.documentElement.dataset.theme==='dark'?'light':'dark';
  document.documentElement.dataset.theme=next;
  localStorage.setItem('gvTheme',next);
}
function toggleMobileMenu(){
  // Telefonda ust menuyu acar/kapatir.
  const nav=document.querySelector('nav');
  nav?.classList.toggle('mobile-open');
  document.getElementById('mobileMenuScrim')?.classList.toggle('open', nav?.classList.contains('mobile-open'));
}
function closeMobileMenu(){
  // Bir sayfaya tiklandiginda mobil menuyu kapatir.
  document.querySelector('nav')?.classList.remove('mobile-open');
  document.getElementById('mobileMenuScrim')?.classList.remove('open');
}
function authHeaders(extra={}){
  const token=userToken || adminToken;
  return token ? {...extra, Authorization:`Bearer ${token}`} : extra;
}

function readCookie(name){
  // CSRF token gibi tarayici cookie degerlerini guvenli sekilde okur.
  const target=`${name}=`;
  return document.cookie.split(';').map(part=>part.trim()).find(part=>part.startsWith(target))?.slice(target.length) || '';
}

const nativeFetch=window.fetch.bind(window);
window.fetch=(input,init={})=>{
  // Ayni domain icindeki POST/PATCH/DELETE isteklerine CSRF header'i ekler.
  const requestUrl=typeof input==='string' ? input : input.url;
  const method=(init.method || (typeof input==='object' && input.method) || 'GET').toUpperCase();
  const isSameOrigin=requestUrl.startsWith('/') || requestUrl.startsWith(location.origin);
  if(isSameOrigin && !['GET','HEAD','OPTIONS'].includes(method)){
    const headers=new Headers(init.headers || {});
    if(!headers.has('X-CSRF-Token')){
      headers.set('X-CSRF-Token',document.querySelector('meta[name="csrf-token"]')?.content || readCookie('csrf_token'));
    }
    init={...init,headers};
  }
  return nativeFetch(input,init);
};

function saveUserSession(token,user,remember){
  // Beni hatirla seciliyse oturum tarayici kapanip acilsa da kalir.
  const persistent=remember ? localStorage : sessionStorage;
  const temporary=remember ? sessionStorage : localStorage;
  temporary.removeItem('gvUserToken');
  temporary.removeItem('gvUser');
  persistent.setItem('gvUserToken',token);
  persistent.setItem('gvUser',JSON.stringify(user));
  localStorage.setItem('gvRememberMe',remember ? '1' : '0');
}

async function restoreServerSession(){
  // Google OAuth donusunden sonra Flask session cookie'sindeki kullaniciyi alir.
  if(userToken)return;
  const params=new URLSearchParams(location.search);
  const googleError=params.get('google_error');
  if(googleError){
    toast('Google ile giriş tamamlanamadı. OAuth ayarlarını kontrol edin.','err');
    history.replaceState({},'',location.pathname);
    return;
  }
  try{
    const res=await fetch('/api/session',{credentials:'same-origin'});
    const payload=await res.json();
    if(!res.ok || payload.success!==true)return;
    userToken=payload.data.token;
    currentUser=payload.data.user;
    const remember=localStorage.getItem('gvGoogleRemember')==='1' || localStorage.getItem('gvRememberMe')==='1';
    saveUserSession(userToken,currentUser,remember);
    if(params.get('google_login')==='success'){
      toast('Google ile giriş yapıldı.','ok');
      history.replaceState({},'',location.pathname);
    }
  }catch(e){
    console.warn('Sunucu oturumu okunamadı:',e);
  }
}

async function loadSiteContent(){
  // Admin uygulamasindan duzenlenen site yazilarini API'den ceker.
  try{
    const res=await fetch('/api/site/content');
    const payload=await res.json();
    if(!res.ok || payload.success!==true)return;
    const texts={};
    (payload.data.texts || []).forEach(item=>texts[item.text_key]=item.value);
    if(texts.hero_title){
      document.getElementById('site-hero-title').innerHTML=texts.hero_title.replace(/\n/g,'<br>');
    }
    if(texts.hero_subtitle){
      document.getElementById('site-hero-subtitle').textContent=texts.hero_subtitle;
    }
    const bindings={
      home_services_title:'site-home-services-title',
      home_services_subtitle:'site-home-services-subtitle',
      home_products_title:'site-home-products-title',
      home_products_subtitle:'site-home-products-subtitle',
      home_reviews_title:'site-home-reviews-title',
      home_reviews_subtitle:'site-home-reviews-subtitle',
      about_title:'site-about-title',
      about_subtitle:'site-about-subtitle',
      about_intro:'site-about-intro',
      services_title:'site-services-title',
      services_subtitle:'site-services-subtitle',
      appointment_title:'site-appointment-title',
      appointment_subtitle:'site-appointment-subtitle',
      appointment_info:'site-appointment-info',
      blog_title:'site-blog-title',
      blog_subtitle:'site-blog-subtitle',
      contact_title:'site-contact-title',
      contact_subtitle:'site-contact-subtitle',
      footer_title:'site-footer-title',
      footer_rights:'site-footer-rights'
    };
    Object.entries(bindings).forEach(([key,id])=>{
      if(texts[key]){
        const el=document.getElementById(id);
        if(el)el.textContent=texts[key];
      }
    });
    SITE_REVIEWS = payload.data.reviews || [];
    renderSiteReviews(SITE_REVIEWS);
    renderAllSiteReviews(SITE_REVIEWS);
  }catch(e){}
}

function renderSiteReviews(reviews){
  const wrap=document.getElementById('site-reviews');
  if(!wrap || !reviews.length)return;
  wrap.innerHTML=reviews.slice(0,6).map(item=>{
    const rating=Math.max(0,Math.min(5,Number(item.rating||5)));
    const stars='★'.repeat(rating)+'☆'.repeat(5-rating);
    const product=item.product_name && item.product_name!=='Genel' ? `<div class="tag" style="margin-bottom:.55rem">${item.product_name}</div>` : '';
    const reply=item.reply ? `<div class="info-box" style="margin-top:.8rem;padding:.75rem;font-size:13px"><strong>Gümüş Veteriner:</strong> ${item.reply}</div>` : '';
    return `<div class="rc"><div class="stars">${stars}</div>${product}<blockquote>"${item.message}"</blockquote>${reply}<cite>${item.author} — ${item.pet_type || 'Hasta Sahibi'}</cite></div>`;
  }).join('');
}
function renderAllSiteReviews(reviews){
  const wrap=document.getElementById('all-site-reviews');
  if(!wrap)return;
  if(!reviews.length){wrap.innerHTML='<div class="info-box">Henüz yorum yok.</div>';return;}
  wrap.innerHTML=reviews.map(item=>{
    const rating=Math.max(0,Math.min(5,Number(item.rating||5)));
    const stars='★'.repeat(rating)+'☆'.repeat(5-rating);
    const product=item.product_name ? `<div class="tag" style="margin-bottom:.55rem">${item.product_name}</div>` : '<div class="tag" style="margin-bottom:.55rem">Genel</div>';
    const reply=item.reply ? `<div class="info-box" style="margin-top:.8rem;padding:.75rem;font-size:13px"><strong>Gümüş Veteriner:</strong> ${item.reply}</div>` : '';
    return `<div class="rc"><div class="stars">${stars}</div>${product}<blockquote>"${item.message}"</blockquote>${reply}<cite>${item.author} — ${item.pet_type || 'Hasta Sahibi'}</cite></div>`;
  }).join('');
}
let cart = {};  // {id: {product, qty}}

// ── Sepet işlemleri ──────────────────────────────────────────────────────────
function addCart(id,name,price,emoji){
  // Urunu sepete ekler; zaten varsa miktarini 1 artirir.
  if(cart[id]){cart[id].qty++;}
  else{cart[id]={id,name,price,emoji,qty:1};}
  updateCartUI();
  showCartFlash();
}
function removeCart(id){
  delete cart[id];
  updateCartUI();
  renderOrderSummary();
}
function changeQty(id,delta){
  if(!cart[id])return;
  cart[id].qty+=delta;
  if(cart[id].qty<=0)delete cart[id];
  updateCartUI();
  renderOrderSummary();
}
function cartItems(){return Object.values(cart);}
function cartTotal(){return cartItems().reduce((s,i)=>s+i.price*i.qty,0);}
function cartCount(){return cartItems().reduce((s,i)=>s+i.qty,0);}

function updateCartUI(){
  // Sepet rozeti, sepet paneli ve toplam tutari ayni anda gunceller.
  const count=cartCount();
  const badge=document.getElementById('cart-count');
  badge.textContent=count;
  badge.style.display=count>0?'inline':'none';
  renderCartPanel();
}
function renderCartPanel(){
  const body=document.getElementById('cart-body');
  const foot=document.getElementById('cart-foot');
  const items=cartItems();
  if(!items.length){
    body.innerHTML='<div class="cart-empty">Sepetiniz boş.<br><small>Ürünler sayfasından ekleyin.</small></div>';
    foot.style.display='none';return;
  }
  body.innerHTML=items.map(i=>`
    <div class="ci">
      ${i.emoji ? `<div class="ci-emoji">${i.emoji}</div>` : ''}
      <div class="ci-info"><h4>${i.name}</h4><small>₺${i.price.toLocaleString('tr-TR')} × ${i.qty}</small></div>
      <div class="qty-ctrl">
        <button class="qty-btn" onclick="changeQty(${i.id},-1)">−</button>
        <span class="qty-num">${i.qty}</span>
        <button class="qty-btn" onclick="changeQty(${i.id},1)">+</button>
      </div>
      <button class="ci-del" onclick="removeCart(${i.id})">✕</button>
    </div>`).join('');
  document.getElementById('cart-total-val').textContent='₺'+cartTotal().toLocaleString('tr-TR');
  foot.style.display='block';
}
function openCart(){
  renderCartPanel();
  document.getElementById('cart-overlay').classList.add('open');
  document.getElementById('cart-panel').classList.add('open');
}
function closeCart(){
  document.getElementById('cart-overlay').classList.remove('open');
  document.getElementById('cart-panel').classList.remove('open');
}
function showCartFlash(){
  const b=document.querySelector('.nb[onclick="openCart()"]');
  b.style.background='var(--teal)';b.style.color='#fff';
  setTimeout(()=>{b.style.background='';b.style.color='';},800);
}

function renderOrderSummary(){
  // Siparis sayfasindaki sepet ozeti. Burada da adet artir/azalt ve sil islemi yapilabilir.
  const list=document.getElementById('order-items-list');
  const total=document.getElementById('order-total');
  if(!list || !total)return;
  const items=cartItems();
  if(!items.length){
    list.innerHTML='<div class="cart-empty" style="padding:1rem">Sepetiniz bos.<br><small>Urunler sayfasindan ekleyin.</small></div>';
    total.textContent='₺0';
    return;
  }
  list.innerHTML=items.map(i=>`
    <div class="order-line order-line-edit">
      <span>${i.emoji || ''} ${i.name}<small>Adet: ${i.qty} • Birim fiyat: ₺${i.price.toLocaleString('tr-TR')}</small></span>
      <div class="order-line-actions">
        <span class="order-line-total">₺${(i.price*i.qty).toLocaleString('tr-TR')}</span>
        <button class="qty-btn" type="button" onclick="changeQty(${i.id},-1)">−</button>
        <span class="qty-num">${i.qty}</span>
        <button class="qty-btn" type="button" onclick="changeQty(${i.id},1)">+</button>
        <button class="ci-del order-del" type="button" onclick="removeCart(${i.id})">Sil</button>
      </div>
    </div>`).join('');
  total.textContent='₺'+cartTotal().toLocaleString('tr-TR');
}

// ── Ürün listesi ─────────────────────────────────────────────────────────────
function escAttr(value){return String(value||'').replace(/'/g,'&#39;').replace(/"/g,'&quot;');}
function productMedia(p){
  if(p.image_emoji){return `<div class="pc-img">${p.image_emoji}</div>`;}
  if(!p.image_url){return '';}
  return `<div class="pc-img"><img src="${escAttr(p.image_url)}" alt="${escAttr(p.name)}" loading="lazy" onerror="this.closest('.pc-img').remove()"></div>`;
}
function normalizeProduct(p){
  return {
    id:p.id,
    name:p.name,
    cat:p.category || 'Genel',
    price:Number(p.price || 0),
    stock:Number(p.stock || 0),
    image_url:p.image_url || '',
    image_emoji:p.image_emoji || ''
  };
}
function renderCategoryPills(){
  const wrap=document.getElementById('cat-pills');
  const cats=[...new Set(PRODUCTS.map(p=>p.cat).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'tr'));
  wrap.innerHTML=`<button class="pill on" onclick="filterCat('all',this)">Tümü</button>`+
    cats.map(cat=>`<button class="pill" onclick="filterCat('${escAttr(cat)}',this)">${cat}</button>`).join('');
}
function renderHomeProducts(){
  const el=document.getElementById('home-products');
  if(!el)return;
  el.innerHTML=PRODUCTS.slice(0,4).map(p=>`
    <div class="pc">
      ${productMedia(p)}
      <div class="pc-body">
        <h3>${p.name}</h3>
        <div class="pc-footer">
          <span class="pc-price">₺${p.price.toLocaleString('tr-TR')}</span>
          <button class="btn-add" ${p.stock<1?'disabled':''} onclick="addCart(${p.id},'${escAttr(p.name)}',${p.price},'')">${p.stock<1?'Tükendi':'+ Ekle'}</button>
        </div>
      </div>
    </div>`).join('');
}
function renderProducts(filter='all'){
  const list=filter==='all'?PRODUCTS:PRODUCTS.filter(p=>p.cat===filter);
  const el=document.getElementById('all-products');
  if(!list.length){el.innerHTML='<div class="info-box">Bu kategoride ürün bulunamadı.</div>';return;}
  el.innerHTML=list.map(p=>`
    <div class="pc">
      ${productMedia(p)}
      <div class="pc-body">
        <h3>${p.name}</h3>
        <div class="pc-footer">
          <span class="pc-price">₺${p.price.toLocaleString('tr-TR')}</span>
          <button class="btn-add" ${p.stock<1?'disabled':''} onclick="addCart(${p.id},'${escAttr(p.name)}',${p.price},'')">
            ${p.stock<1?'Tükendi':'+ Ekle'}
          </button>
        </div>
      </div>
    </div>`).join('');
}
function filterCat(cat,btn){
  document.querySelectorAll('.pill').forEach(p=>p.classList.remove('on'));
  btn.classList.add('on');
  renderProducts(cat);
}

async function loadProducts(){
  // Urun listesini backend API'den alir ve ana sayfa/urunler bolumune basar.
  try{
    const res=await fetch('/api/products');
    const data=await res.json();
    if(!res.ok){throw new Error(data.error || 'Ürünler yüklenemedi.');}
    PRODUCTS=data.map(normalizeProduct);
    renderCategoryPills();
    renderHomeProducts();
    renderProducts();
  }catch(e){
    document.getElementById('all-products').innerHTML=`<div class="info-box">${e.message || 'Ürünler yüklenemedi.'}</div>`;
  }
}

// ── Profil, adres ve hayvan kayıtları ────────────────────────────────────────
function renderProfile(){
  // Profil sayfasinda kullanici bilgisi, adresler ve kayitli hayvanlar gosterilir.
  const user=PROFILE.user || currentUser || {};
  document.getElementById('profileName').textContent=user.full_name || 'Üye';
  document.getElementById('profileEmail').textContent=[user.email,user.phone].filter(Boolean).join(' • ') || 'Profil bilgileri';
  const avatar=document.getElementById('profileAvatar');
  const saved=currentUser?.avatar || user.profile_picture || currentUser?.profile_picture || localStorage.getItem(`gvAvatar:${user.email}`) || '';
  avatar.innerHTML=saved ? `<img src="${saved}" alt="Profil fotoğrafı">` : (user.full_name || 'GV').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();
  const addressList=document.getElementById('addressList');
  addressList.innerHTML=PROFILE.addresses.length ? PROFILE.addresses.map(a=>`
    <div class="profile-item">
      <div class="profile-item-head">
        <div><strong>${a.title || 'Adres'}</strong><small>${[a.district,a.city].filter(Boolean).join(' / ')}</small></div>
        <button class="danger-mini" onclick="deleteAddress(${a.id})">Sil</button>
      </div>
      <div>${a.address}</div>
    </div>`).join('') : '<div class="info-box" style="margin:0">Henüz kayıtlı adres yok.</div>';
  const petList=document.getElementById('petList');
  petList.innerHTML=PROFILE.pets.length ? PROFILE.pets.map(p=>`
    <div class="profile-item">
      <div class="profile-item-head">
        <div><strong>${p.name} • ${p.species}</strong><small>${p.age || 'Yaş belirtilmedi'}</small></div>
        <button class="danger-mini" onclick="deletePet(${p.id})">Sil</button>
      </div>
      <div>${p.notes || ''}</div>
    </div>`).join('') : '<div class="info-box" style="margin:0">Henüz kayıtlı hayvan yok.</div>';
}
async function loadProfile(){
  // Giris yapan kullanicinin profil, adres ve hayvan kayitlarini yukler.
  if(!userToken && !adminToken)return;
  const res=await fetch('/api/profile',{headers:authHeaders()});
  const data=await res.json();
  if(!res.ok){throw new Error(data.error || 'Profil yüklenemedi.');}
  PROFILE=data;
  renderProfile();
  loadPurchasedProducts().catch(()=>{});
  return data;
}
async function loadPurchasedProducts(){
  const select=document.getElementById('reviewProduct');
  if(!select || !userToken)return;
  const res=await fetch('/api/profile/purchased-products',{headers:authHeaders()});
  const payload=await res.json();
  if(!res.ok || payload.success===false)return;
  const products=payload.data || [];
  select.innerHTML='<option value="Genel">Genel klinik yorumu</option>'+products.map(p=>`<option value="${escAttr(p.name)}">${p.name}</option>`).join('');
}
async function submitAddress(){
  if(!userToken && !adminToken){go('auth');return;}
  const payload={
    title:document.getElementById('addrTitle').value.trim() || 'Adres',
    district:document.getElementById('addrDistrict').value.trim(),
    city:document.getElementById('addrCity').value.trim(),
    address:document.getElementById('addrText').value.trim()
  };
  if(payload.address.length<10){showMsg('addrOk','addrErr','err','Lütfen tam adres girin.');return;}
  try{
    const res=await fetch('/api/profile/addresses',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify(payload)});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error || 'Adres kaydedilemedi.');
    showMsg('addrOk','addrErr','ok','✅ Adres kaydedildi.');
    document.getElementById('addressForm').reset();
    await loadProfile();
    prepareOrderForm();
  }catch(e){showMsg('addrOk','addrErr','err',e.message || 'Adres kaydedilemedi.');}
}
async function submitPet(){
  if(!userToken && !adminToken){go('auth');return;}
  const payload={
    name:document.getElementById('petName').value.trim(),
    species:document.getElementById('petSpecies').value,
    age:document.getElementById('petAge').value.trim(),
    notes:document.getElementById('petNotes').value.trim()
  };
  if(!payload.name || !payload.species){showMsg('petOk','petErr','err','Hayvan adı ve türü zorunlu.');return;}
  try{
    const res=await fetch('/api/profile/pets',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify(payload)});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error || 'Hayvan kaydedilemedi.');
    showMsg('petOk','petErr','ok','✅ Hayvan kaydedildi.');
    document.getElementById('petForm').reset();
    await loadProfile();
  }catch(e){showMsg('petOk','petErr','err',e.message || 'Hayvan kaydedilemedi.');}
}
async function deleteAddress(id){
  if(!confirm('Adres silinsin mi?'))return;
  try{
    const res=await fetch(`/api/profile/addresses/${id}`,{method:'DELETE',headers:authHeaders()});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error || 'Adres silinemedi.');
    toast('Adres silindi');
    await loadProfile();
    prepareOrderForm();
  }catch(e){toast(e.message || 'Adres silinemedi.','err');}
}
async function deletePet(id){
  if(!confirm('Hayvan kaydı silinsin mi?'))return;
  try{
    const res=await fetch(`/api/profile/pets/${id}`,{method:'DELETE',headers:authHeaders()});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error || 'Hayvan silinemedi.');
    toast('Hayvan kaydı silindi');
    await loadProfile();
  }catch(e){toast(e.message || 'Hayvan silinemedi.','err');}
}

// ── Sipariş sayfası ──────────────────────────────────────────────────────────
function toggleOrderAddressBox(){
  const select=document.getElementById('orderAddressSelect');
  const box=document.getElementById('orderNewAddressBox');
  if(!select || !box)return;
  box.style.display=(!currentUser || select.value==='new' || !PROFILE.addresses.length) ? 'block' : 'none';
}
function prepareOrderForm(){
  const select=document.getElementById('orderAddressSelect');
  if(currentUser && select){
    select.innerHTML=PROFILE.addresses.length
      ? PROFILE.addresses.map(a=>`<option value="${a.id}">${a.title || 'Adres'} — ${a.address.slice(0,70)}${a.address.length>70?'...':''}</option>`).join('') + '<option value="new">Yeni adres ekle</option>'
      : '<option value="new">Adres ekle</option>';
    document.getElementById('memberOrderBox').textContent=PROFILE.addresses.length
      ? 'Üye bilgileriniz kullanılacak. Kayıtlı adresinizi seçebilir veya yeni adres ekleyebilirsiniz.'
      : 'Üye bilgileriniz kullanılacak. Sipariş için önce teslimat adresi ekleyin.';
    if(!document.getElementById('cardName').value && currentUser.full_name){document.getElementById('cardName').value=currentUser.full_name;}
  }
  toggleOrderAddressBox();
}
async function goOrder(){
  closeCart();
  const items=cartItems();
  if(!items.length){alert('Sepetiniz boş!');return;}
  if(currentUser && !PROFILE.user){
    try{await loadProfile();}catch(e){toast(e.message || 'Profil yüklenemedi','err');}
  }
  // Siparis ozeti render edilir; kullanici bu ekranda adetleri degistirebilir.
  renderOrderSummary();
  prepareOrderForm();
  go('order');
}

// ── Form validasyon yardımcısı ────────────────────────────────────────────────
function validPhone(v){return /^0[0-9]{10}$/.test(v.replace(/\s/g,''));}
function showMsg(okId,errId,type,text){
  const ok=document.getElementById(okId);const err=document.getElementById(errId);
  ok.style.display='none';err.style.display='none';
  if(type==='ok'){ok.textContent=text;ok.style.display='block';}
  else{err.textContent=text;err.style.display='block';}
  toast(text,type);
}

function updateAuthUI(){
  document.body.classList.toggle('admin-session', false);
  document.body.classList.toggle('user-session', !!userToken);
  const label=document.getElementById('nav-user');
  const logoutBtn=document.getElementById('logoutBtn');
  if(adminToken){
    if(label)label.textContent='Admin';
    if(logoutBtn)logoutBtn.style.display='inline-flex';
  }else if(currentUser){
    if(label)label.textContent=currentUser.full_name || currentUser.name || currentUser.email;
    if(logoutBtn)logoutBtn.style.display='inline-flex';
  }else{
    if(label)label.textContent='';
    if(logoutBtn)logoutBtn.style.display='none';
  }
}

async function logout(){
  // Oturumu kapatir, tarayicidaki tokenlari temizler ve ana sayfaya doner.
  try{
    const token=userToken || adminToken;
    if(token){
      await fetch('/api/logout',{method:'POST',headers:{Authorization:`Bearer ${token}`}});
    }
  }catch(e){
    console.warn('Cikis istegi tamamlanamadi:',e);
  }
  userToken='';
  adminToken='';
  currentUser=null;
  PROFILE={user:null,addresses:[],pets:[]};
  localStorage.removeItem('gvUserToken');
  localStorage.removeItem('gvAdminToken');
  localStorage.removeItem('gvUser');
  sessionStorage.removeItem('gvUserToken');
  sessionStorage.removeItem('gvAdminToken');
  sessionStorage.removeItem('gvUser');
  localStorage.removeItem('gvRememberMe');
  localStorage.removeItem('gvGoogleRemember');
  updateAuthUI();
  applyAppointmentMemberMode();
  toast('Çıkış yapıldı.','ok');
  go('home');
}

function googleLogin(){
  const remember=document.getElementById('rememberMe')?.checked || false;
  localStorage.setItem('gvGoogleRemember',remember ? '1' : '0');
  window.location.href=`/login/google?remember=${remember ? '1' : '0'}`;
}

async function forgotPassword(){
  // Kullanici mail adresini girince backend tek kullanimlik sifre sifirlama linki yollar.
  const emailInput=document.getElementById('lemail');
  const email=(emailInput?.value || prompt('Şifre sıfırlama linki için e-posta adresinizi yazın:') || '').trim();
  if(!email || !email.includes('@')){
    showMsg('loginOk','loginErr','err','Şifre sıfırlama için geçerli bir e-posta girin.');
    return;
  }
  try{
    const res=await fetch('/api/forgot-password',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email})
    });
    const payload=await res.json();
    if(!res.ok || payload.success===false)throw new Error(payload.message || 'Şifre sıfırlama maili gönderilemedi.');
    showMsg('loginOk','loginErr','ok',payload.message || 'Şifre sıfırlama bağlantısı gönderildi.');
  }catch(e){
    showMsg('loginOk','loginErr','err',e.message || 'Şifre sıfırlama maili gönderilemedi.');
  }
}

async function handlePasswordResetFromLink(){
  // Maildeki bağlantı siteyi reset_token parametresiyle açar; yeni şifreyi burada alırız.
  const params=new URLSearchParams(location.search);
  const token=params.get('reset_token');
  if(!token)return;
  history.replaceState({},'',location.pathname);
  const password=prompt('Yeni şifrenizi yazın:');
  if(!password)return;
  const again=prompt('Yeni şifrenizi tekrar yazın:');
  if(password!==again){
    toast('Şifreler eşleşmedi.','err');
    return;
  }
  try{
    const res=await fetch('/api/reset-password',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token,password})
    });
    const payload=await res.json();
    if(!res.ok || payload.success===false)throw new Error(payload.message || 'Şifre güncellenemedi.');
    toast(payload.message || 'Şifreniz güncellendi.','ok');
    go('auth');
  }catch(e){
    toast(e.message || 'Şifre güncellenemedi.','err');
  }
}

function setAnimal(kind,button){
  const face=document.getElementById('animalFace');
  face.className=`animal-face ${kind}`;
  face.style.setProperty('--eye-x','0px');
  face.style.setProperty('--eye-y','0px');
  document.querySelectorAll('.animal-picks button').forEach(b=>b.classList.remove('on'));
  button.classList.add('on');
}
function reactPet(type){
  document.querySelectorAll('.animal-face').forEach(face=>{
    face.classList.remove('happy','sad');
    void face.offsetWidth;
    face.classList.add(type);
    setTimeout(()=>face.classList.remove(type),900);
  });
}
function showAuthTab(name){
  document.querySelectorAll('[data-auth-tab]').forEach(tab=>tab.classList.toggle('on',tab.dataset.authTab===name));
  document.querySelectorAll('[data-auth-panel]').forEach(panel=>panel.classList.toggle('on',panel.dataset.authPanel===name));
}
function trackInput(input){
  const rect=input.getBoundingClientRect();
  const x=Math.max(-5,Math.min(5,(rect.left+rect.width/2-window.innerWidth/2)/70));
  const y=Math.max(-4,Math.min(5,(rect.top+rect.height/2-window.innerHeight/2)/80));
  document.querySelectorAll('.animal-face').forEach(face=>{
    face.style.setProperty('--eye-x',`${x}px`);
    face.style.setProperty('--eye-y',`${y}px`);
  });
}
function wireAnimalInputs(){
  document.querySelectorAll('[data-watch-input]').forEach(input=>{
    input.addEventListener('focus',()=>{trackInput(input);document.querySelectorAll('.animal-face').forEach(face=>{face.classList.add('look');face.classList.remove('hide');});});
    input.addEventListener('input',()=>trackInput(input));
    input.addEventListener('blur',()=>document.querySelectorAll('.animal-face').forEach(face=>face.classList.remove('look')));
  });
  document.querySelectorAll('[data-password-input]').forEach(input=>{
    input.addEventListener('focus',()=>document.querySelectorAll('.animal-face').forEach(face=>{face.classList.add('hide');face.classList.remove('look');}));
    input.addEventListener('blur',()=>document.querySelectorAll('.animal-face').forEach(face=>face.classList.remove('hide')));
  });
}

document.getElementById('ravatar')?.addEventListener('change',event=>{
  const file=event.target.files[0];
  if(!file)return;
  const reader=new FileReader();
  reader.onload=()=>{const img=document.getElementById('avatarPreview');img.src=reader.result;img.style.display='block';localStorage.setItem('gvPendingAvatar',reader.result);};
  reader.readAsDataURL(file);
});
document.getElementById('cardNumber')?.addEventListener('input',event=>{
  const digits=event.target.value.replace(/\D/g,'').slice(0,19);
  event.target.value=digits.replace(/(.{4})/g,'$1 ').trim();
});
document.getElementById('cardExpiry')?.addEventListener('input',event=>{
  const digits=event.target.value.replace(/\D/g,'').slice(0,4);
  event.target.value=digits.length>2 ? `${digits.slice(0,2)}/${digits.slice(2)}` : digits;
});
function initWhatsAppBubble(){
  const bubble=document.getElementById('whatsappFloat');
  if(!bubble)return;
  localStorage.removeItem('gvWhatsAppBubble');
  bubble.style.left='';
  bubble.style.top='';
  bubble.style.right='22px';
  bubble.style.bottom='22px';
}

// ── Randevu gönder ────────────────────────────────────────────────────────────
function splitFullName(fullName){
  const parts=String(fullName || 'Üye Gumus').trim().split(/\s+/).filter(Boolean);
  return {first:parts[0] || 'Üye', last:parts.slice(1).join(' ') || 'Gumus'};
}
function applyAppointmentMemberMode(){
  // Üye girişinde kişisel alanları gizler; backend yine üyeden gelen bilgileri doğrular.
  const isMember=!!userToken && !!currentUser;
  const note=document.getElementById('apptMemberNote');
  const personal=document.getElementById('apptPersonalFields');
  const petBox=document.getElementById('apptPetBox');
  if(note)note.style.display=isMember ? 'block' : 'none';
  if(personal)personal.style.display=isMember ? 'none' : 'block';
  if(petBox)petBox.style.display=isMember ? 'block' : 'none';
  if(isMember){
    const name=splitFullName(currentUser.full_name);
    document.getElementById('fn').value=name.first;
    document.getElementById('ln').value=name.last;
    document.getElementById('ph').value=currentUser.phone || '';
    document.getElementById('em').value=currentUser.email || '';
    if(!document.getElementById('pt').value)document.getElementById('pt').value='Diğer';
    if(!document.getElementById('sv').value)document.getElementById('sv').value='Genel Muayene';
    renderAppointmentPetSelect();
  }
}
function renderAppointmentPetSelect(){
  // Profilde kayıtlı hayvan varsa randevuda hızlı seçim listesi gösterir.
  const select=document.getElementById('apptPetSelect');
  if(!select)return;
  const pets=PROFILE.pets || [];
  select.innerHTML='<option value="">Seçim yapın</option>'+pets.map(p=>`<option value="${p.id}">${p.name} - ${p.species}</option>`).join('')+'<option value="new">Yeni hayvan gireceğim</option>';
  if(!pets.length)select.value='new';
  selectAppointmentPet();
}
function selectAppointmentPet(){
  const value=document.getElementById('apptPetSelect')?.value || '';
  const newBox=document.getElementById('apptNewPetFields');
  if(newBox)newBox.style.display=value==='new' ? 'block' : 'none';
  if(value==='new')return;
  const id=Number(value || 0);
  const pet=(PROFILE.pets || []).find(item=>Number(item.id)===id);
  if(!pet)return;
  document.getElementById('pn').value=pet.name || '';
  const species=pet.species || 'Diğer';
  const select=document.getElementById('pt');
  const hasOption=[...select.options].some(option=>option.value===species || option.textContent===species);
  select.value=hasOption ? species : 'Diğer';
}
async function loadAppointmentSlots(){
  // Seçilen güne göre dolu/kapalı randevu saatlerini backendden alır.
  const dateValue=document.getElementById('dt')?.value;
  const select=document.getElementById('tm');
  if(!dateValue || !select)return;
  const current=select.value;
  select.innerHTML='<option value="">Saatler yükleniyor...</option>';
  try{
    const res=await fetch(`/api/appointment-slots?date=${encodeURIComponent(dateValue)}`);
    const payload=await res.json();
    if(!res.ok || payload.success===false)throw new Error(payload.message || 'Saatler yüklenemedi.');
    const rows=payload.data || [];
    select.innerHTML='<option value="">Seçin...</option>'+rows.map(row=>{
      const disabled=row.available ? '' : 'disabled';
      const label=row.available ? row.time : `${row.time} - ${row.taken ? 'Dolu' : 'Kapalı'}`;
      return `<option value="${row.time}" ${disabled}>${label}</option>`;
    }).join('');
    if(rows.some(row=>row.time===current && row.available))select.value=current;
  }catch(e){
    select.innerHTML='<option value="">Saatler alınamadı</option>';
    toast(e.message || 'Saatler yüklenemedi','err');
  }
}
async function submitAppt(){
  applyAppointmentMemberMode();
  const fn=document.getElementById('fn').value.trim();
  const ln=document.getElementById('ln').value.trim();
  const ph=document.getElementById('ph').value.trim();
  const pt=document.getElementById('pt').value;
  const sv=document.getElementById('sv').value;
  const dt=document.getElementById('dt').value;
  const tm=document.getElementById('tm').value;

  if(!userToken && (!fn||!ln)){showMsg('apptOk','apptErr','err','Ad ve soyad zorunlu.');return;}
  if(!userToken && !validPhone(ph)){showMsg('apptOk','apptErr','err','Geçerli telefon: 05XX XXX XX XX');return;}
  if(!userToken && !pt){showMsg('apptOk','apptErr','err','Lütfen hayvan türü seçin.');return;}
  if(!userToken && !sv){showMsg('apptOk','apptErr','err','Lütfen hizmet türü seçin.');return;}
  const petChoice=document.getElementById('apptPetSelect')?.value || '';
  if(userToken && petChoice==='new'){
    const newName=document.getElementById('newPetName').value.trim();
    const newSpecies=document.getElementById('newPetSpecies').value;
    if(!newName || !newSpecies){showMsg('apptOk','apptErr','err','Yeni hayvan adı ve türü zorunlu.');return;}
    document.getElementById('pn').value=newName;
    document.getElementById('pt').value=newSpecies;
  }
  if(!dt||new Date(dt)<new Date().setHours(0,0,0,0)){showMsg('apptOk','apptErr','err','Lütfen gelecek bir tarih seçin.');return;}
  if(!tm){showMsg('apptOk','apptErr','err','Lütfen saat seçin.');return;}

  const btn=document.getElementById('apptBtn');
  btn.textContent='Gönderiliyor...';btn.disabled=true;

  const payload={
    first_name:fn, last_name:ln, phone:ph.replace(/\s/g,''),
    email:document.getElementById('em').value,
    pet_type:document.getElementById('pt').value || pt, pet_name:document.getElementById('pn').value,
    service:sv, appt_date:dt, appt_time:tm,
    notes:document.getElementById('nt').value,
    save_pet:userToken && petChoice==='new'
  };

  try{
    const res = await fetch('/api/appointments',{
      method:'POST',
      headers:authHeaders({'Content-Type':'application/json'}),
      body:JSON.stringify(payload)
    });
    const data = await res.json();
    if(!res.ok){throw new Error(data.error || 'Randevu oluşturulamadı.');}
    showMsg('apptOk','apptErr','ok',`✅ Randevunuz oluşturuldu! Randevu numaranız: #${data.id}`);
    document.getElementById('apptForm').reset();
    if(userToken)await loadProfile();
    applyAppointmentMemberMode();
    await loadAppointmentSlots();
  }catch(e){
    showMsg('apptOk','apptErr','err',e.message || 'Sunucu hatası. Lütfen tekrar deneyin veya telefonla arayın.');
  }finally{
    btn.textContent='Randevu Oluştur';btn.disabled=false;
  }
}

async function submitPurchaseReview(){
  // Satın alma yapan üyelerin ana sayfaya yorum bırakmasını sağlar.
  if(!userToken){go('auth');return;}
  const payload={
    rating:Number(document.getElementById('reviewRating').value || 5),
    pet_type:document.getElementById('reviewPetType').value.trim() || 'Hasta Sahibi',
    product_name:document.getElementById('reviewProduct').value || 'Genel',
    message:document.getElementById('reviewMessage').value.trim()
  };
  if(payload.message.length<8){showMsg('reviewOk','reviewErr','err','Yorum en az 8 karakter olmalı.');return;}
  try{
    const res=await fetch('/api/reviews',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify(payload)});
    const data=await res.json();
    if(!res.ok || data.success===false)throw new Error(data.message || data.error || 'Yorum kaydedilemedi.');
    showMsg('reviewOk','reviewErr','ok','✅ Yorumunuz yayınlandı.');
    document.getElementById('reviewForm').reset();
    await loadSiteContent();
  }catch(e){showMsg('reviewOk','reviewErr','err',e.message || 'Yorum kaydedilemedi.');}
}
// ── Siparişten ödeme sayfasına geçiş ─────────────────────────────────────────
async function goPayment(){
  // Teslimat bilgilerini kontrol eder; her sey tamamsa odeme sayfasina gecer.
  const fn=document.getElementById('ofn').value.trim();
  const ln=document.getElementById('oln').value.trim();
  const ph=document.getElementById('oph').value.trim();
  const ad=document.getElementById('oad').value.trim();

  if(!currentUser && (!fn||!ln)){showMsg('orderOk','orderErr','err','Ad ve soyad zorunlu.');return;}
  if(!currentUser && !validPhone(ph)){showMsg('orderOk','orderErr','err','Geçerli telefon: 05XX XXX XX XX');return;}
  const addressSelect=document.getElementById('orderAddressSelect');
  const useNewAddress=!currentUser || !addressSelect || addressSelect.value==='new' || !PROFILE.addresses.length;
  if(useNewAddress && ad.length<10){showMsg('orderOk','orderErr','err','Lütfen tam adresinizi girin.');return;}
  if(!cartItems().length){showMsg('orderOk','orderErr','err','Sepetiniz boş!');return;}

  const btn=document.getElementById('orderBtn');
  btn.textContent='Ödemeye Geçiliyor...';btn.disabled=true;

  let selectedAddressId=currentUser && addressSelect && addressSelect.value!=='new' ? Number(addressSelect.value) : null;
  if(currentUser && useNewAddress){
    try{
      const res=await fetch('/api/profile/addresses',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({title:'Teslimat',address:ad,city:'Samsun'})});
      const saved=await res.json();
      if(!res.ok)throw new Error(saved.error || 'Adres kaydedilemedi.');
      selectedAddressId=saved.id;
      await loadProfile();
    }catch(e){
      showMsg('orderOk','orderErr','err',e.message || 'Adres kaydedilemedi.');
      btn.textContent='Siparişi Onayla';btn.disabled=false;
      return;
    }
  }

  PENDING_ORDER={
    first_name:fn, last_name:ln,
    phone:ph.replace(/\s/g,''),
    email:document.getElementById('oem').value,
    address:ad,
    address_id:selectedAddressId,
    notes:document.getElementById('ont').value,
    items:cartItems().map(i=>({product_id:i.id,quantity:i.qty}))
  };
  document.getElementById('payment-items-list').innerHTML=cartItems().map(i=>`
    <div class="order-line">
      <span>${i.emoji || ''} ${i.name}<small>Adet: ${i.qty} • Birim fiyat: ₺${i.price.toLocaleString('tr-TR')}</small></span>
      <span style="font-weight:500">₺${(i.price*i.qty).toLocaleString('tr-TR')}</span>
    </div>`).join('');
  document.getElementById('payment-total').textContent='₺'+cartTotal().toLocaleString('tr-TR');
  if(!document.getElementById('cardName').value && currentUser?.full_name){document.getElementById('cardName').value=currentUser.full_name;}
  btn.textContent='Siparişi Onayla';btn.disabled=false;
  go('payment');
}

// ── Ödeme gönder ─────────────────────────────────────────────────────────────
async function submitPayment(){
  // Demo kart bilgilerini kontrol eder ve siparisi backend'e kaydeder.
  if(!PENDING_ORDER){showMsg('paymentOk','paymentErr','err','Teslimat bilgileri eksik.');go('order');return;}
  const cardName=document.getElementById('cardName').value.trim();
  const cardNumber=document.getElementById('cardNumber').value.replace(/\D/g,'');
  const cardExpiry=document.getElementById('cardExpiry').value.trim();
  const cardCvc=document.getElementById('cardCvc').value.replace(/\D/g,'');
  if(!cardName || !/^\d{12,19}$/.test(cardNumber) || !/^(0[1-9]|1[0-2])\/\d{2}$/.test(cardExpiry.replace(/\s/g,'')) || !/^\d{3,4}$/.test(cardCvc)){
    showMsg('paymentOk','paymentErr','err','Lütfen geçerli ödeme bilgileri girin.');return;
  }
  const btn=document.getElementById('paymentBtn');
  btn.textContent='Ödeme Alınıyor...';btn.disabled=true;
  const payload={
    ...PENDING_ORDER,
    card_name:cardName,
    card_number:cardNumber,
    card_expiry:cardExpiry.replace(/\s/g,''),
    card_cvc:cardCvc
  };

  try{
    const res = await fetch('/api/orders',{
      method:'POST',
      headers:authHeaders({'Content-Type':'application/json'}),
      body:JSON.stringify(payload)
    });
    const data = await res.json();
    if(!res.ok){throw new Error(data.error || 'Sipariş oluşturulamadı.');}
    const total=data.total;
    cart={};updateCartUI();
    PENDING_ORDER=null;
    const ok=document.getElementById('paymentOk');
    ok.innerHTML=`✅ Siparişiniz alındı!<br><small>Sipariş No: #${data.id} — Toplam: ₺${total.toLocaleString('tr-TR')} — SMS ile bilgilendirme yapılacaktır.</small>`;
    ok.style.display='block';
    document.getElementById('orderForm').reset();
    document.getElementById('paymentForm').reset();
    prepareOrderForm();
  }catch(e){
    showMsg('paymentOk','paymentErr','err',e.message || 'Sipariş oluşturulamadı. Lütfen tekrar deneyin.');
  }finally{
    btn.textContent='Ödemeyi Tamamla';btn.disabled=false;
  }
}

// ── İletişim gönder ───────────────────────────────────────────────────────────
async function submitContact(){
  const fullName=document.getElementById('cname').value.trim();
  const email=document.getElementById('cemail').value.trim();
  const message=document.getElementById('cmessage').value.trim();
  if(!fullName||!email){showMsg('contactOk','contactErr','err','Ad soyad ve e-posta zorunlu.');return;}
  if(message.length<10){showMsg('contactOk','contactErr','err','Mesaj en az 10 karakter olmalı.');return;}

  const btn=document.getElementById('contactBtn');
  btn.textContent='Gönderiliyor...';btn.disabled=true;
  try{
    const res=await fetch('/api/contact',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        full_name:fullName,
        email,
        subject:document.getElementById('csubject').value,
        message
      })
    });
    const data=await res.json();
    if(!res.ok){throw new Error(data.error || 'Mesaj gönderilemedi.');}
    showMsg('contactOk','contactErr','ok','✅ Mesajınız iletildi. En kısa sürede dönüş yapacağız.');
    document.getElementById('contactForm').reset();
  }catch(e){
    showMsg('contactOk','contactErr','err',e.message || 'Mesaj gönderilemedi.');
  }finally{
    btn.textContent='Mesaj Gönder';btn.disabled=false;
  }
}

// ── Üye kayıt gönder ─────────────────────────────────────────────────────────
async function submitLogin(){
  // Normal uye girisi yapar, token'i localStorage'a kaydeder.
  const email=document.getElementById('lemail').value.trim();
  const password=document.getElementById('lpass').value;
  const remember=document.getElementById('rememberMe')?.checked || false;
  if(!email.includes('@')){showMsg('loginOk','loginErr','err','Geçerli bir e-posta girin.');return;}
  if(!password){showMsg('loginOk','loginErr','err','Şifre zorunlu.');return;}
  const btn=document.getElementById('loginBtn');
  btn.textContent='Giriş yapılıyor...';btn.disabled=true;
  try{
    const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    const data=await res.json();
    if(!res.ok){throw new Error(data.error || 'Giriş yapılamadı.');}
    userToken=data.token;
    currentUser=data.user;
    currentUser.avatar=localStorage.getItem(`gvAvatar:${currentUser.email}`) || '';
    saveUserSession(userToken,currentUser,remember);
    showMsg('loginOk','loginErr','ok','✅ Giriş yapıldı.');
    reactPet('happy');
    updateAuthUI();
    await loadProfile().catch(()=>{});
    document.getElementById('loginForm').reset();
  }catch(e){
    reactPet('sad');
    showMsg('loginOk','loginErr','err',e.message || 'Giriş yapılamadı.');
  }finally{
    btn.textContent='Giriş Yap';btn.disabled=false;
  }
}

async function submitRegister(){
  // Yeni uye kaydi olusturur. Telefon zorunludur.
  const fullName=document.getElementById('rname').value.trim();
  const email=document.getElementById('remail').value.trim();
  const phone=document.getElementById('rphone').value.trim();
  const password=document.getElementById('rpass').value;

  if(!fullName){showMsg('registerOk','registerErr','err','Ad soyad zorunlu.');return;}
  if(!email.includes('@')){showMsg('registerOk','registerErr','err','Geçerli bir e-posta girin.');return;}
  if(!validPhone(phone)){showMsg('registerOk','registerErr','err','Telefon zorunlu. Geçerli format: 05XX XXX XX XX');return;}
  if(password.length<6){showMsg('registerOk','registerErr','err','Şifre en az 6 karakter olmalı.');return;}

  const btn=document.getElementById('registerBtn');
  btn.textContent='Kaydediliyor...';btn.disabled=true;

  try{
    const res=await fetch('/api/register',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        full_name:fullName,
        email,
        phone:phone.replace(/\s/g,''),
        password
      })
    });
    const data=await res.json();
    if(!res.ok){throw new Error(data.error || 'Üye kaydı oluşturulamadı.');}
    const avatar=localStorage.getItem('gvPendingAvatar') || '';
    if(avatar){localStorage.setItem(`gvAvatar:${data.email}`,avatar);localStorage.removeItem('gvPendingAvatar');}
    showMsg('registerOk','registerErr','ok',`✅ Üyelik oluşturuldu. Üye numarası: #${data.id}`);
    reactPet('happy');
    document.getElementById('registerForm').reset();
  }catch(e){
    reactPet('sad');
    showMsg('registerOk','registerErr','err',e.message || 'Üye kaydı oluşturulamadı.');
  }finally{
    btn.textContent='Üye Kaydı Oluştur';btn.disabled=false;
  }
}

// -- Sayfa navigasyon ---------------------------------------------------------
const pageMap={home:'page-home',about:'page-about',services:'page-services',shop:'page-shop',appt:'page-appt',blog:'page-blog',contact:'page-contact',auth:'page-auth',profile:'page-profile',reviews:'page-reviews',forbidden:'page-403',order:'page-order',payment:'page-payment'};
const navMap={home:'nb-home',about:'nb-about',services:'nb-services',shop:'nb-shop',blog:'nb-blog',contact:'nb-contact',auth:'nb-auth'};
function go(id){
  // Tek sayfa uygulamada sayfalar arasi gecisleri yoneten ana fonksiyon.
  // Yeni bir sayfa bolumu eklersen once pageMap'e, sonra HTML'de ilgili id'ye bak.
  if(id==='admin' || id==='adminLogin'){id='home';}
  if(id==='profile' && !userToken && !adminToken){id='auth';}
  if(id==='payment' && !PENDING_ORDER){id='order';}
  closeMobileMenu();
  Object.values(pageMap).forEach(p=>{const el=document.getElementById(p);if(el)el.classList.remove('on');});
  Object.values(navMap).forEach(n=>{const el=document.getElementById(n);if(el)el.classList.remove('on');});
  const page=document.getElementById(pageMap[id]);
  if(page){page.classList.add('on');window.scrollTo(0,0);}
  if(navMap[id]){
    const activeNav=document.getElementById(navMap[id]);
    if(activeNav)activeNav.classList.add('on');
  }
  if(id==='profile'){loadProfile().catch(e=>toast(e.message || 'Profil yüklenemedi','err'));}
  if(id==='appt'){
    if(currentUser && !PROFILE.user){
      loadProfile().then(()=>applyAppointmentMemberMode()).catch(()=>applyAppointmentMemberMode());
    }else{
      applyAppointmentMemberMode();
    }
    loadAppointmentSlots();
  }
}

// ── İlk yükleme ───────────────────────────────────────────────────────────────
async function bootSite(){
  // Sayfa ilk açıldığında hem klasik üyeliği hem de Google OAuth dönüşünü hazırlar.
  // Google girişinden dönen kullanıcı Flask session içinden okunur ve normal site oturumuna çevrilir.
  const dateInput=document.getElementById('dt');
  if(dateInput){
    dateInput.min=new Date().toISOString().split('T')[0];
    dateInput.addEventListener('change',loadAppointmentSlots);
  }

  const rememberInput=document.getElementById('rememberMe');
  if(rememberInput){
    rememberInput.checked=localStorage.getItem('gvRememberMe')==='1' || localStorage.getItem('gvGoogleRemember')==='1';
  }

  wireAnimalInputs();
  initWhatsAppBubble();
  await restoreServerSession();
  await handlePasswordResetFromLink();
  updateAuthUI();
  applyAppointmentMemberMode();
  loadProducts();
  loadSiteContent();
  if(currentUser){loadProfile().catch(()=>{});}
  if(location.pathname==='/admin/login' || location.pathname==='/admin')go('home');
  if(location.pathname==='/403')go('forbidden');
  if(new URLSearchParams(location.search).get('route')==='adminLogin')go('home');
}

bootSite();

