(() => {
  const state = {
    token: localStorage.getItem("gumusAdminToken") || "",
    products: [],
    appointments: [],
    pets: [],
    hospitalizations: [],
    orders: [],
    reviews: [],
    contacts: [],
    siteTexts: [],
    users: [],
    slots: [],
    services: [],
  };

  const statusLabels = {
    pending: "Beklemede",
    confirmed: "Onaylandı",
    completed: "Tamamlandı",
    cancelled: "İptal",
    shipped: "Kargoya verildi",
    delivered: "Teslim edildi",
    discharged: "Taburcu",
    active: "Aktif",
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const text = (value) => String(value ?? "");
  const escapeHtml = (value) => text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || "";
  }

  function toast(message, danger = false) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.style.background = danger ? "#b93434" : "#18251f";
    el.classList.add("show");
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => el.classList.remove("show"), 2600);
  }

  async function api(path, options = {}) {
    const headers = {"Content-Type": "application/json", ...(options.headers || {})};
    const tokenForCsrf = csrfToken();
    if (tokenForCsrf) headers["X-CSRF-Token"] = tokenForCsrf;
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(path, {...options, headers, credentials: "same-origin"});
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      localStorage.removeItem("gumusAdminToken");
      if (document.body.dataset.loginOnly !== "true") window.location.href = "/admin/login";
      throw new Error(payload.message || "Admin girişi gerekli");
    }
    if (!response.ok || payload.success === false) throw new Error(payload.message || "İşlem tamamlanamadı");
    return payload.data;
  }

  function showLoginOnly() {
    if ($("#adminLogin")) $("#adminLogin").hidden = false;
    if ($("#adminApp")) $("#adminApp").hidden = true;
  }

  function showApp() {
    if ($("#adminLogin")) $("#adminLogin").hidden = true;
    if ($("#adminApp")) $("#adminApp").hidden = false;
    if ($("#adminName")) $("#adminName").textContent = document.body.dataset.adminName || "admin";
  }

  async function handleLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = $("#loginMessage");
    if (message) message.textContent = "";
    try {
      const data = await api("/api/admin/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
      });
      state.token = data.token;
      localStorage.setItem("gumusAdminToken", state.token);
      window.location.href = "/admin";
    } catch (error) {
      if (message) message.textContent = error.message;
    }
  }

  async function logout() {
    try { await api("/api/admin/logout", {method: "POST"}); } catch (_) {}
    localStorage.removeItem("gumusAdminToken");
    window.location.href = "/admin/login";
  }

  function setTheme(theme) {
    document.body.classList.toggle("dark", theme === "dark");
    localStorage.setItem("gumusAdminTheme", theme);
    if ($("#themeToggle")) $("#themeToggle").textContent = theme === "dark" ? "Açık Tema" : "Karanlık Tema";
  }

  function setSection(section) {
    $$(".panel-section").forEach((el) => el.classList.toggle("active-section", el.id === `section-${section}`));
    $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.section === section));
    if ($("#pageTitle")) $("#pageTitle").textContent = document.querySelector(`[data-section="${section}"]`)?.textContent || "Admin";
    closeSidebar();
    loadSection(section);
  }

  function openSidebar() {
    $("#adminSidebar")?.classList.add("open");
    $("#sidebarOverlay")?.classList.add("open");
  }

  function closeSidebar() {
    $("#adminSidebar")?.classList.remove("open");
    $("#sidebarOverlay")?.classList.remove("open");
  }

  function filtered(items, inputId, fields) {
    const query = ($(inputId)?.value || "").trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => fields.some((field) => text(item[field]).toLowerCase().includes(query)));
  }

  function statusSelect(value, kind, id) {
    const options = kind === "order"
      ? ["pending", "confirmed", "shipped", "delivered", "cancelled"]
      : ["pending", "confirmed", "completed", "cancelled"];
    return `<select data-status-${kind}="${id}">${options.map((option) => `<option value="${option}" ${option === value ? "selected" : ""}>${statusLabels[option]}</option>`).join("")}</select>`;
  }

  function renderDashboard(data) {
    const stats = [
      ["Toplam Kullanıcı", data.total_users || 0],
      ["Toplam Ürün", data.total_products || 0],
      ["Toplam Randevu", data.total_appointments || 0],
      ["Toplam Sipariş", data.total_orders || 0],
      ["Toplam Hasta", data.total_pets || 0],
      ["Aktif Yatış", data.active_hospitalizations || 0],
      ["Bu Ay Gelir", `₺${Number(data.current_month_sales || 0).toFixed(2)}`],
      ["Satış Değişimi", `%${Number(data.sales_change_percent || 0).toFixed(1)}`],
    ];
    $("#dashboardStats").innerHTML = stats.map(([title, value]) => `<article class="stat-card"><span class="muted">${title}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
    const monthly = data.monthly_sales || [];
    const max = Math.max(...monthly.map((item) => Number(item.total || 0)), 1);
    $("#salesChart").innerHTML = monthly.map((item) => {
      const height = Math.max(6, (Number(item.total || 0) / max) * 100);
      return `<div class="bar-item"><div class="bar" style="height:${height}%"></div><strong>₺${Number(item.total || 0).toFixed(0)}</strong><span>${escapeHtml(item.month)}</span></div>`;
    }).join("");
    $("#recentActivity").innerHTML = (data.notifications || []).map((item) => `<div class="activity-item"><strong>${escapeHtml(item.title)}</strong><p class="muted">${escapeHtml(item.message)}</p></div>`).join("") || `<p class="muted">Henüz işlem bulunmuyor.</p>`;
  }

  async function loadDashboard() {
    renderDashboard(await api("/api/admin/dashboard"));
  }

  function renderProducts() {
    const rows = filtered(state.products, "#productSearch", ["name", "category", "stock"]);
    $("#productsTable").innerHTML = rows.map((product) => `<tr><td><strong>${escapeHtml(product.name)}</strong></td><td>${escapeHtml(product.category)}</td><td>₺${Number(product.price || 0).toFixed(2)}</td><td>${escapeHtml(product.stock)}</td><td><span class="status-pill">${product.active ? "Aktif" : "Pasif"}</span></td><td><button class="small-btn" data-edit-product="${product.id}">Düzenle</button> <button class="danger-btn" data-delete-product="${product.id}">Sil</button></td></tr>`).join("") || `<tr><td colspan="6">Ürün bulunamadı.</td></tr>`;
  }
  async function loadProducts() { state.products = await api("/api/admin/products"); renderProducts(); }
  function fillProductForm(product = {}) {
    const f = $("#productForm").elements; $("#productForm").hidden = false;
    f.id.value = product.id || ""; f.name.value = product.name || ""; f.category.value = product.category || "Genel"; f.price.value = product.price ?? 0; f.stock.value = product.stock ?? 0; f.image_url.value = product.image_url || ""; f.active.checked = product.active !== 0;
  }
  async function saveProduct(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    data.active = form.elements.active.checked ? 1 : 0;
    data.price = Number(data.price || 0); data.stock = Number.parseInt(data.stock || 0, 10);
    await api(data.id ? `/api/admin/products/update/${data.id}` : "/api/admin/products/add", {method: data.id ? "PATCH" : "POST", body: JSON.stringify(data)});
    form.reset(); form.hidden = true; toast("Ürün kaydedildi"); await loadProducts();
  }

  function renderAppointments() {
    const rows = filtered(state.appointments, "#appointmentSearch", ["first_name", "last_name", "phone", "pet_name", "service", "appt_date"]);
    $("#appointmentsList").innerHTML = rows.map((item) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(item.pet_name || "İsimsiz hasta")}</strong><p class="muted">${escapeHtml(item.first_name)} ${escapeHtml(item.last_name)} • ${escapeHtml(item.phone)}</p><p>${escapeHtml(item.service)} • ${escapeHtml(item.appt_date)} ${escapeHtml(item.appt_time)}</p><p class="muted">${escapeHtml(item.notes || "Talep notu yok")}</p></div><span class="status-pill">${statusLabels[item.status] || item.status}</span></div><div class="record-actions">${statusSelect(item.status, "appointment", item.id)}<button class="primary-btn" data-save-appointment="${item.id}">Durumu Kaydet</button>${item.pet_registered ? "" : `<button class="small-btn" data-add-appointment-pet="${item.id}">Peti Kaydet</button>`}<button class="danger-btn" data-delete-appointment="${item.id}">Sil</button></div></article>`).join("") || `<p class="muted">Randevu bulunamadı.</p>`;
  }
  async function loadAppointments() { state.appointments = await api("/api/admin/appointments"); renderAppointments(); }

  function renderPets() {
    const rows = filtered(state.pets, "#petSearch", ["name", "species", "owner", "phone", "notes"]);
    $("#petsList").innerHTML = rows.map((pet) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(pet.name)}</strong><p class="muted">${escapeHtml(pet.species)} ${pet.breed ? `• ${escapeHtml(pet.breed)}` : ""} ${pet.age ? `• ${escapeHtml(pet.age)}` : ""}</p><p>${escapeHtml(pet.owner || "Sahip bilgisi yok")} • ${escapeHtml(pet.phone || "")}</p><p class="muted">${escapeHtml(pet.notes || "")}</p></div><span class="status-pill">${escapeHtml(pet.source)}</span></div><div class="record-actions"><button class="small-btn" data-edit-pet="${pet.record_key}">Düzenle</button><button class="danger-btn" data-delete-pet="${pet.source}:${pet.id}">Sil</button></div></article>`).join("") || `<p class="muted">Hasta kaydı bulunamadı.</p>`;
    fillHospitalPetSelect();
  }
  async function loadPets() { state.pets = await api("/api/admin/pets"); renderPets(); }
  function fillPetForm(pet = {}) {
    const form = $("#petForm"); const f = form.elements; form.hidden = false;
    f.id.value = pet.id || ""; f.source.value = pet.source || "clinic"; f.name.value = pet.name || ""; f.species.value = pet.species || ""; f.breed.value = pet.breed || ""; f.age.value = pet.age || ""; f.owner_name.value = pet.owner || pet.owner_name || ""; f.phone.value = pet.phone || ""; f.notes.value = pet.notes || "";
  }
  async function savePet(event) {
    event.preventDefault();
    const form = event.currentTarget; const data = Object.fromEntries(new FormData(form).entries());
    await api(data.id ? `/api/admin/pets/update/${data.source}/${data.id}` : "/api/admin/pets/add", {method: data.id ? "PATCH" : "POST", body: JSON.stringify(data)});
    form.reset(); form.elements.source.value = "clinic"; form.hidden = true; toast("Hasta kaydı kaydedildi"); await loadPets();
  }

  function fillHospitalPetSelect() {
    const select = $("#hospitalPetSelect");
    if (!select) return;
    select.innerHTML = `<option value="">Yeni hasta</option>` + state.pets.map((p) => `<option value="${escapeHtml(p.record_key)}">${escapeHtml(p.name)} • ${escapeHtml(p.owner || "")}</option>`).join("");
  }
  function renderHospitalizations() {
    const rows = filtered(state.hospitalizations, "#hospitalSearch", ["pet_name", "owner_name", "phone", "room", "diagnosis", "treatment", "status"]);
    $("#hospitalizationsList").innerHTML = rows.map((h) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(h.pet_name)}</strong><p class="muted">${escapeHtml(h.owner_name || "")} • ${escapeHtml(h.phone || "")} • ${escapeHtml(h.room || "")}</p><p><strong>Tanı:</strong> ${escapeHtml(h.diagnosis)}</p><p><strong>Tedavi:</strong> ${escapeHtml(h.treatment)}</p><p class="muted">${escapeHtml(h.notes || "")}</p>${(h.previous_stays || []).length ? `<p class="muted">Geçmiş yatış: ${(h.previous_stays || []).length}</p>` : ""}</div><span class="status-pill">${statusLabels[h.status] || h.status}</span></div><div class="record-actions"><button class="small-btn" data-edit-hospital="${h.id}">Düzenle</button>${h.status === "active" ? `<button class="primary-btn" data-discharge-hospital="${h.id}">Taburcu Et</button>` : ""}</div></article>`).join("") || `<p class="muted">Yatış kaydı bulunamadı.</p>`;
  }
  async function loadHospitalizations() { state.hospitalizations = await api("/api/admin/hospitalizations"); renderHospitalizations(); if (!state.pets.length) await loadPets(); }
  async function saveHospital(event) {
    event.preventDefault();
    const form = event.currentTarget; const data = Object.fromEntries(new FormData(form).entries());
    await api("/api/admin/hospitalizations", {method: "POST", body: JSON.stringify(data)});
    form.reset(); form.hidden = true; toast("Hasta yatışı kaydedildi"); await loadHospitalizations(); await loadPets();
  }

  function renderOrders() {
    const rows = filtered(state.orders, "#orderSearch", ["first_name", "last_name", "phone", "email", "status", "tracking_number"]);
    $("#ordersList").innerHTML = rows.map((order) => `<article class="record-card"><div class="record-top"><div><strong>#${order.id} ${escapeHtml(order.first_name)} ${escapeHtml(order.last_name)}</strong><p class="muted">${escapeHtml(order.phone)} • ${escapeHtml(order.email || order.notification_email || "")}</p><p>Toplam: ₺${Number(order.total || 0).toFixed(2)} • ${escapeHtml(order.created_at || "")}</p><p class="muted">${(order.items || []).map((item) => `${escapeHtml(item.name)} x${item.quantity}`).join(", ")}</p></div><span class="status-pill">${statusLabels[order.status] || order.status}</span></div><div class="record-actions">${statusSelect(order.status, "order", order.id)}<input data-tracking-order="${order.id}" placeholder="Takip numarası" value="${escapeHtml(order.tracking_number || "")}"><button class="primary-btn" data-save-order="${order.id}">Kaydet</button><button class="danger-btn" data-delete-order="${order.id}">Sil</button></div></article>`).join("") || `<p class="muted">Sipariş bulunamadı.</p>`;
  }
  async function loadOrders() { state.orders = await api("/api/admin/orders"); renderOrders(); }

  function renderReviews() {
    const rows = filtered(state.reviews, "#reviewSearch", ["author", "pet_type", "product_name", "message", "reply"]);
    $("#reviewsList").innerHTML = rows.map((r) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(r.author)} • ${"★".repeat(Number(r.rating || 5))}</strong><p class="muted">${escapeHtml(r.pet_type || "Hasta Sahibi")} • Ürün: ${escapeHtml(r.product_name || "Genel")}</p><p>${escapeHtml(r.message)}</p><label>Yanıt<textarea data-review-reply="${r.id}" rows="2">${escapeHtml(r.reply || "")}</textarea></label></div><span class="status-pill">${r.active ? "Yayında" : "Pasif"}</span></div><div class="record-actions"><button class="primary-btn" data-save-review="${r.id}">Yanıtı Kaydet</button><button class="small-btn" data-toggle-review="${r.id}" data-active="${r.active ? 0 : 1}">${r.active ? "Pasifleştir" : "Yayınla"}</button><button class="danger-btn" data-delete-review="${r.id}">Sil</button></div></article>`).join("") || `<p class="muted">Yorum bulunamadı.</p>`;
  }
  async function loadReviews() { state.reviews = await api("/api/admin/reviews"); renderReviews(); }

  function renderContacts() {
    const rows = filtered(state.contacts, "#contactSearch", ["full_name", "email", "subject", "message", "reply"]);
    $("#contactsList").innerHTML = rows.map((c) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(c.full_name)}</strong><p class="muted">${escapeHtml(c.email)} • ${escapeHtml(c.subject || "Konu yok")}</p><p>${escapeHtml(c.message)}</p><label>Yanıt<textarea data-contact-reply="${c.id}" rows="3">${escapeHtml(c.reply || "")}</textarea></label></div><span class="status-pill">${c.reply ? "Yanıtlandı" : "Bekliyor"}</span></div><div class="record-actions"><button class="primary-btn" data-save-contact="${c.id}">Yanıtla ve Mail Gönder</button></div></article>`).join("") || `<p class="muted">Soru bulunamadı.</p>`;
  }
  async function loadContacts() { state.contacts = await api("/api/admin/contacts"); renderContacts(); }

  function renderSiteTexts() {
    const rows = filtered(state.siteTexts, "#siteTextSearch", ["label", "text_key", "value"]);
    $("#siteTextsList").innerHTML = rows.map((t) => `<article class="record-card"><strong>${escapeHtml(t.label)}</strong><p class="muted">${escapeHtml(t.text_key)}</p><textarea data-site-text="${escapeHtml(t.text_key)}" rows="3">${escapeHtml(t.value)}</textarea><div class="record-actions"><button class="primary-btn" data-save-site-text="${escapeHtml(t.text_key)}">Kaydet</button></div></article>`).join("") || `<p class="muted">Site yazısı bulunamadı.</p>`;
  }
  async function loadSiteTexts() { state.siteTexts = await api("/api/admin/site-texts"); renderSiteTexts(); }

  function renderUsers() {
    const rows = filtered(state.users, "#userSearch", ["full_name", "email", "phone", "role"]);
    $("#usersList").innerHTML = rows.map((u) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(u.full_name)}</strong><p class="muted">${escapeHtml(u.email)} • ${escapeHtml(u.phone || "Telefon yok")}</p><p>${escapeHtml(u.role)} ${u.is_banned ? "• Banlı" : ""}</p></div><button class="small-btn" data-toggle-detail="${u.id}">Detay</button></div><div id="user-detail-${u.id}" hidden><p><strong>Adresler:</strong> ${(u.addresses || []).map((a) => escapeHtml(a.address)).join(" | ") || "Yok"}</p><p><strong>Hayvanlar:</strong> ${(u.pets || []).map((p) => escapeHtml(`${p.name} (${p.species})`)).join(", ") || "Yok"}</p><div class="record-actions"><button class="small-btn" data-user-role="${u.id}" data-role="${u.role === "admin" ? "member" : "admin"}">${u.role === "admin" ? "Üyeye Çevir" : "Admin Yap"}</button><button class="small-btn" data-user-ban="${u.id}" data-ban="${u.is_banned ? 0 : 1}">${u.is_banned ? "Banı Kaldır" : "Banla"}</button><button class="danger-btn" data-delete-user="${u.id}">Sil</button></div></div></article>`).join("") || `<p class="muted">Kullanıcı bulunamadı.</p>`;
  }
  async function loadUsers() { state.users = await api("/api/admin/users"); renderUsers(); }

  function renderSlots() {
    $("#slotsList").innerHTML = state.slots.map((s) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(s.appt_time || s.time)}</strong><p class="muted">${escapeHtml(s.note || "")}</p></div><span class="status-pill">${s.is_available ? "Uygun" : "Kapalı"}</span></div></article>`).join("") || `<p class="muted">Bu tarih için özel saat kaydı yok.</p>`;
  }
  async function loadSlots() {
    const date = $("#slotDate")?.value || new Date().toISOString().slice(0, 10);
    if ($("#slotDate") && !$("#slotDate").value) $("#slotDate").value = date;
    state.slots = await api(`/api/admin/appointment-slots?date=${encodeURIComponent(date)}`);
    renderSlots();
  }
  async function saveSlot(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    data.date = $("#slotDate").value;
    data.is_available = data.is_available === "true";
    await api("/api/admin/appointment-slots", {method: "POST", body: JSON.stringify(data)});
    toast("Randevu saati kaydedildi"); await loadSlots();
  }

  function renderServices() {
    $("#servicesList").innerHTML = state.services.map((s) => `<article class="record-card"><div class="record-top"><div><strong>${escapeHtml(s.name)}</strong><p class="muted">₺${Number(s.price || 0).toFixed(2)} • ${escapeHtml(s.description || "")}</p></div><span class="status-pill">${s.active ? "Aktif" : "Pasif"}</span></div><div class="record-actions"><button class="small-btn" data-edit-service="${s.id}">Düzenle</button><button class="danger-btn" data-delete-service="${s.id}">Sil</button></div></article>`).join("") || `<p class="muted">Hizmet bulunamadı.</p>`;
  }
  async function loadServices() { state.services = await api("/api/admin/services"); renderServices(); }
  function fillServiceForm(s = {}) {
    const form = $("#serviceForm"); const f = form.elements; form.hidden = false;
    f.id.value = s.id || ""; f.name.value = s.name || ""; f.price.value = s.price || 0; f.description.value = s.description || ""; f.active.checked = s.active !== 0;
  }
  async function saveService(event) {
    event.preventDefault();
    const form = event.currentTarget; const data = Object.fromEntries(new FormData(form).entries());
    data.active = form.elements.active.checked ? 1 : 0; data.price = Number(data.price || 0);
    await api(data.id ? `/api/admin/services/update/${data.id}` : "/api/admin/services/add", {method: data.id ? "PATCH" : "POST", body: JSON.stringify(data)});
    form.reset(); form.hidden = true; toast("Hizmet kaydedildi"); await loadServices();
  }

  async function loadProfile() {
    const profile = await api("/api/admin/profile");
    if ($("#profileForm")) $("#profileForm").elements.username.value = profile.username || profile.email || "";
  }
  async function saveProfile(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const result = await api("/api/admin/profile", {method: "PATCH", body: JSON.stringify(data)});
    if (result.token) { state.token = result.token; localStorage.setItem("gumusAdminToken", state.token); }
    toast("Profil güncellendi");
  }

  async function sendSms(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    await api("/api/admin/send-sms", {method: "POST", body: JSON.stringify(data)});
    event.currentTarget.reset(); $("#smsCounter").textContent = "0 / 480"; toast("SMS gönderildi");
  }

  async function loadSection(section) {
    try {
      if (section === "dashboard") await loadDashboard();
      if (section === "appointments") await loadAppointments();
      if (section === "pets") await loadPets();
      if (section === "hospitalizations") await loadHospitalizations();
      if (section === "products") await loadProducts();
      if (section === "orders") await loadOrders();
      if (section === "reviews") await loadReviews();
      if (section === "contacts") await loadContacts();
      if (section === "site-texts") await loadSiteTexts();
      if (section === "users") await loadUsers();
      if (section === "slots") await loadSlots();
      if (section === "services") await loadServices();
      if (section === "profile") await loadProfile();
    } catch (error) {
      toast(error.message, true);
    }
  }

  function bindStaticEvents() {
    $("#adminLoginForm")?.addEventListener("submit", handleLogin);
    $("#adminLogout")?.addEventListener("click", logout);
    $("#sidebarToggle")?.addEventListener("click", openSidebar);
    $("#sidebarOverlay")?.addEventListener("click", closeSidebar);
    $("#themeToggle")?.addEventListener("click", () => setTheme(document.body.classList.contains("dark") ? "light" : "dark"));
    $$(".nav-item").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.section)));
    $$("[data-refresh]").forEach((button) => button.addEventListener("click", () => loadSection(button.dataset.refresh)));
    $$("[data-open-form]").forEach((button) => button.addEventListener("click", () => { const form = $(`#${button.dataset.openForm}`); form.reset(); form.hidden = false; if (form.elements.source) form.elements.source.value = "clinic"; }));
    $$("[data-close-form]").forEach((button) => button.addEventListener("click", () => { $(`#${button.dataset.closeForm}`).hidden = true; }));
    $("#productForm")?.addEventListener("submit", saveProduct);
    $("#petForm")?.addEventListener("submit", savePet);
    $("#hospitalForm")?.addEventListener("submit", saveHospital);
    $("#serviceForm")?.addEventListener("submit", saveService);
    $("#slotForm")?.addEventListener("submit", saveSlot);
    $("#smsForm")?.addEventListener("submit", sendSms);
    $("#profileForm")?.addEventListener("submit", saveProfile);
    $("#slotDate")?.addEventListener("change", loadSlots);
    $("#smsForm textarea[name='message']")?.addEventListener("input", (event) => { $("#smsCounter").textContent = `${event.target.value.length} / 480`; });
    ["productSearch", "appointmentSearch", "orderSearch", "userSearch", "petSearch", "hospitalSearch", "reviewSearch", "contactSearch", "siteTextSearch"].forEach((id) => {
      $(`#${id}`)?.addEventListener("input", () => {
        if (id === "productSearch") renderProducts();
        if (id === "appointmentSearch") renderAppointments();
        if (id === "orderSearch") renderOrders();
        if (id === "userSearch") renderUsers();
        if (id === "petSearch") renderPets();
        if (id === "hospitalSearch") renderHospitalizations();
        if (id === "reviewSearch") renderReviews();
        if (id === "contactSearch") renderContacts();
        if (id === "siteTextSearch") renderSiteTexts();
      });
    });
  }

  function bindDelegatedEvents() {
    document.addEventListener("click", async (event) => {
      const target = event.target;
      try {
        if (target.dataset.editProduct) fillProductForm(state.products.find((p) => String(p.id) === target.dataset.editProduct));
        if (target.dataset.deleteProduct && confirm("Ürünü silmek istiyor musunuz?")) { await api(`/api/admin/products/delete/${target.dataset.deleteProduct}`, {method: "DELETE"}); toast("Ürün silindi"); await loadProducts(); }
        if (target.dataset.saveAppointment) { const id = target.dataset.saveAppointment; const status = document.querySelector(`[data-status-appointment="${id}"]`).value; await api(`/api/admin/appointments/update/${id}`, {method: "PATCH", body: JSON.stringify({status})}); toast("Randevu güncellendi"); await loadAppointments(); }
        if (target.dataset.addAppointmentPet) { await api(`/api/admin/appointments/${target.dataset.addAppointmentPet}/add-pet`, {method: "POST"}); toast("Pet kaydedildi"); await loadAppointments(); await loadPets(); }
        if (target.dataset.deleteAppointment && confirm("Randevu admin listesinden kaldırılsın mı?")) { await api(`/api/admin/appointments/delete/${target.dataset.deleteAppointment}`, {method: "DELETE"}); await loadAppointments(); }
        if (target.dataset.editPet) fillPetForm(state.pets.find((p) => p.record_key === target.dataset.editPet));
        if (target.dataset.deletePet && confirm("Hasta kaydı admin listesinden kaldırılsın mı?")) { const [source, id] = target.dataset.deletePet.split(":"); await api(`/api/admin/pets/delete/${source}/${id}`, {method: "DELETE"}); await loadPets(); }
        if (target.dataset.dischargeHospital && confirm("Hasta taburcu edilsin mi?")) { await api(`/api/admin/hospitalizations/${target.dataset.dischargeHospital}/discharge`, {method: "POST"}); toast("Hasta taburcu edildi"); await loadHospitalizations(); }
        if (target.dataset.editHospital) {
          const h = state.hospitalizations.find((item) => String(item.id) === target.dataset.editHospital);
          const diagnosis = prompt("Tanı / yatış nedeni", h?.diagnosis || "");
          if (diagnosis !== null) { await api(`/api/admin/hospitalizations/${target.dataset.editHospital}`, {method: "PATCH", body: JSON.stringify({diagnosis})}); await loadHospitalizations(); }
        }
        if (target.dataset.saveOrder) { const id = target.dataset.saveOrder; const status = document.querySelector(`[data-status-order="${id}"]`).value; const tracking_number = document.querySelector(`[data-tracking-order="${id}"]`).value; await api(`/api/admin/orders/update/${id}`, {method: "PATCH", body: JSON.stringify({status, tracking_number})}); toast("Sipariş güncellendi"); await loadOrders(); }
        if (target.dataset.deleteOrder && confirm("Sipariş admin listesinden kaldırılsın mı?")) { await api(`/api/admin/orders/delete/${target.dataset.deleteOrder}`, {method: "DELETE"}); await loadOrders(); }
        if (target.dataset.saveReview) { const id = target.dataset.saveReview; const reply = document.querySelector(`[data-review-reply="${id}"]`).value; await api(`/api/admin/reviews/update/${id}`, {method: "PATCH", body: JSON.stringify({reply})}); toast("Yorum yanıtlandı"); await loadReviews(); }
        if (target.dataset.toggleReview) { await api(`/api/admin/reviews/update/${target.dataset.toggleReview}`, {method: "PATCH", body: JSON.stringify({active: Number(target.dataset.active)})}); await loadReviews(); }
        if (target.dataset.deleteReview && confirm("Yorum silinsin mi?")) { await api(`/api/admin/reviews/delete/${target.dataset.deleteReview}`, {method: "DELETE"}); await loadReviews(); }
        if (target.dataset.saveContact) { const id = target.dataset.saveContact; const reply = document.querySelector(`[data-contact-reply="${id}"]`).value; await api(`/api/admin/contacts/reply/${id}`, {method: "PATCH", body: JSON.stringify({reply})}); toast("Yanıt kaydedildi"); await loadContacts(); }
        if (target.dataset.saveSiteText) { const key = target.dataset.saveSiteText; const value = document.querySelector(`[data-site-text="${CSS.escape(key)}"]`).value; await api(`/api/admin/site-texts/update/${encodeURIComponent(key)}`, {method: "PATCH", body: JSON.stringify({value})}); toast("Site yazısı güncellendi"); await loadSiteTexts(); }
        if (target.dataset.toggleDetail) { const detail = $(`#user-detail-${target.dataset.toggleDetail}`); detail.hidden = !detail.hidden; }
        if (target.dataset.userRole) { await api(`/api/admin/users/update/${target.dataset.userRole}`, {method: "PATCH", body: JSON.stringify({role: target.dataset.role})}); await loadUsers(); }
        if (target.dataset.userBan) { await api(`/api/admin/users/update/${target.dataset.userBan}`, {method: "PATCH", body: JSON.stringify({is_banned: Number(target.dataset.ban)})}); await loadUsers(); }
        if (target.dataset.deleteUser && confirm("Üye silinsin mi?")) { await api(`/api/admin/users/delete/${target.dataset.deleteUser}`, {method: "DELETE"}); await loadUsers(); }
        if (target.dataset.editService) fillServiceForm(state.services.find((s) => String(s.id) === target.dataset.editService));
        if (target.dataset.deleteService && confirm("Hizmet silinsin mi?")) { await api(`/api/admin/services/delete/${target.dataset.deleteService}`, {method: "DELETE"}); await loadServices(); }
      } catch (error) {
        toast(error.message, true);
      }
    });
  }

  async function boot() {
    bindStaticEvents();
    bindDelegatedEvents();
    setTheme(localStorage.getItem("gumusAdminTheme") || "light");
    if (document.body.dataset.loginOnly === "true") { showLoginOnly(); return; }
    showApp();
    await loadDashboard();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
