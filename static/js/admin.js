(() => {
  const state = {
    token: localStorage.getItem("gumusAdminToken") || "",
    section: "dashboard",
    products: [],
    appointments: [],
    orders: [],
    users: [],
    pets: [],
  };

  const labels = {
    pending: "Beklemede",
    confirmed: "Onaylandı",
    shipped: "Kargoya verildi",
    delivered: "Teslim edildi",
    cancelled: "Reddedildi / İptal",
    completed: "Tamamlandı",
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || "";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
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
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    const tokenForCsrf = csrfToken();
    if (tokenForCsrf) headers["X-CSRF-Token"] = tokenForCsrf;
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(path, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      localStorage.removeItem("gumusAdminToken");
      if (!document.body.dataset.loginOnly || document.body.dataset.loginOnly === "false") {
        window.location.href = "/admin/login";
      }
      throw new Error(payload.message || "Admin girişi gerekli");
    }
    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || "İşlem tamamlanamadı");
    }
    return payload.data;
  }

  function showLoginOnly() {
    $("#adminLogin").hidden = false;
    $("#adminApp").hidden = true;
  }

  function showApp() {
    $("#adminLogin").hidden = true;
    $("#adminApp").hidden = false;
    $("#adminName").textContent = document.body.dataset.adminName || "admin";
  }

  async function handleLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = $("#loginMessage");
    message.textContent = "";
    try {
      const data = await api("/api/admin/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
      });
      state.token = data.token;
      localStorage.setItem("gumusAdminToken", state.token);
      document.body.dataset.loginOnly = "false";
      history.replaceState(null, "", "/admin");
      showApp();
      await loadDashboard();
    } catch (error) {
      message.textContent = error.message;
    }
  }

  async function logout() {
    try {
      await api("/api/admin/logout", { method: "POST" });
    } catch (_) {
      // Çıkışta ağ hatası olsa bile yerel token temizlenir.
    }
    localStorage.removeItem("gumusAdminToken");
    window.location.href = "/admin/login";
  }

  function setSection(section) {
    state.section = section;
    $$(".panel-section").forEach((el) => el.classList.toggle("active-section", el.id === `section-${section}`));
    $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.section === section));
    $("#pageTitle").textContent = document.querySelector(`[data-section="${section}"]`)?.textContent || "Admin";
    closeSidebar();
    loadSection(section);
  }

  function openSidebar() {
    $("#adminSidebar").classList.add("open");
    $("#sidebarOverlay").classList.add("open");
  }

  function closeSidebar() {
    $("#adminSidebar").classList.remove("open");
    $("#sidebarOverlay").classList.remove("open");
  }

  function setTheme(theme) {
    document.body.classList.toggle("dark", theme === "dark");
    localStorage.setItem("gumusAdminTheme", theme);
    $("#themeToggle").textContent = theme === "dark" ? "Açık Tema" : "Karanlık Tema";
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
    $("#dashboardStats").innerHTML = stats.map(([title, value]) => `
      <article class="stat-card"><span class="muted">${title}</span><strong>${escapeHtml(value)}</strong></article>
    `).join("");

    const monthly = data.monthly_sales || [];
    const max = Math.max(...monthly.map((item) => Number(item.total || 0)), 1);
    $("#salesChart").innerHTML = monthly.map((item) => {
      const height = Math.max(6, (Number(item.total || 0) / max) * 100);
      return `
        <div class="bar-item">
          <div class="bar" style="height:${height}%"></div>
          <strong>₺${Number(item.total || 0).toFixed(0)}</strong>
          <span>${escapeHtml(item.month)}</span>
        </div>
      `;
    }).join("");

    const activity = data.notifications || [];
    $("#recentActivity").innerHTML = activity.length ? activity.map((item) => `
      <div class="activity-item">
        <strong>${escapeHtml(item.title)}</strong>
        <p class="muted">${escapeHtml(item.message)}</p>
      </div>
    `).join("") : `<p class="muted">Henüz işlem bulunmuyor.</p>`;
  }

  async function loadDashboard() {
    renderDashboard(await api("/api/admin/dashboard"));
  }

  function filtered(items, inputId, fields) {
    const query = ($(inputId)?.value || "").trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => fields.some((field) => String(item[field] || "").toLowerCase().includes(query)));
  }

  function renderProducts() {
    const rows = filtered(state.products, "#productSearch", ["name", "category", "stock"]);
    $("#productsTable").innerHTML = rows.map((product) => `
      <tr>
        <td><strong>${escapeHtml(product.name)}</strong></td>
        <td>${escapeHtml(product.category)}</td>
        <td>₺${Number(product.price || 0).toFixed(2)}</td>
        <td>${escapeHtml(product.stock)}</td>
        <td><span class="status-pill">${product.active ? "Aktif" : "Pasif"}</span></td>
        <td>
          <button class="small-btn" data-edit-product="${product.id}">Düzenle</button>
          <button class="danger-btn" data-delete-product="${product.id}">Sil</button>
        </td>
      </tr>
    `).join("") || `<tr><td colspan="6">Ürün bulunamadı.</td></tr>`;
  }

  async function loadProducts() {
    state.products = await api("/api/admin/products");
    renderProducts();
  }

  function fillProductForm(product = {}) {
    const form = $("#productForm");
    const fields = form.elements;
    form.hidden = false;
    fields.id.value = product.id || "";
    fields.name.value = product.name || "";
    fields.category.value = product.category || "Genel";
    fields.price.value = product.price ?? 0;
    fields.stock.value = product.stock ?? 0;
    fields.image_url.value = product.image_url || "";
    fields.active.checked = product.active !== 0;
  }

  async function saveProduct(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    data.active = form.active.checked ? 1 : 0;
    data.price = Number(data.price || 0);
    data.stock = Number.parseInt(data.stock || 0, 10);
    const path = data.id ? `/api/admin/products/update/${data.id}` : "/api/admin/products/add";
    await api(path, { method: data.id ? "PATCH" : "POST", body: JSON.stringify(data) });
    form.reset();
    form.hidden = true;
    toast("Ürün kaydedildi");
    await loadProducts();
  }

  function statusSelect(value, kind, id) {
    const options = kind === "order"
      ? ["pending", "confirmed", "shipped", "delivered", "cancelled"]
      : ["pending", "confirmed", "completed", "cancelled"];
    return `<select data-status-${kind}="${id}">${options.map((option) => `
      <option value="${option}" ${option === value ? "selected" : ""}>${labels[option]}</option>
    `).join("")}</select>`;
  }

  function renderAppointments() {
    const rows = filtered(state.appointments, "#appointmentSearch", ["first_name", "last_name", "phone", "pet_name", "service", "appt_date"]);
    $("#appointmentsList").innerHTML = rows.map((item) => `
      <article class="record-card">
        <div class="record-top">
          <div>
            <strong>${escapeHtml(item.pet_name || "İsimsiz hasta")}</strong>
            <p class="muted">${escapeHtml(item.first_name)} ${escapeHtml(item.last_name)} • ${escapeHtml(item.phone)}</p>
            <p>${escapeHtml(item.service)} • ${escapeHtml(item.appt_date)} ${escapeHtml(item.appt_time)}</p>
            <p class="muted">${escapeHtml(item.notes || "Talep notu yok")}</p>
          </div>
          <span class="status-pill">${labels[item.status] || item.status}</span>
        </div>
        <div class="record-actions">
          ${statusSelect(item.status, "appointment", item.id)}
          <button class="primary-btn" data-save-appointment="${item.id}">Durumu Kaydet</button>
          ${item.pet_registered ? "" : `<button class="small-btn" data-add-appointment-pet="${item.id}">Peti Kaydet</button>`}
          <button class="danger-btn" data-delete-appointment="${item.id}">Sil</button>
        </div>
      </article>
    `).join("") || `<p class="muted">Randevu bulunamadı.</p>`;
  }

  async function loadAppointments() {
    state.appointments = await api("/api/admin/appointments");
    renderAppointments();
  }

  function renderOrders() {
    const rows = filtered(state.orders, "#orderSearch", ["first_name", "last_name", "phone", "email", "status", "tracking_number"]);
    $("#ordersList").innerHTML = rows.map((order) => `
      <article class="record-card">
        <div class="record-top">
          <div>
            <strong>#${order.id} ${escapeHtml(order.first_name)} ${escapeHtml(order.last_name)}</strong>
            <p class="muted">${escapeHtml(order.phone)} • ${escapeHtml(order.email || order.notification_email || "")}</p>
            <p>Toplam: ₺${Number(order.total || 0).toFixed(2)} • ${escapeHtml(order.created_at || "")}</p>
            <p class="muted">${(order.items || []).map((item) => `${escapeHtml(item.name)} x${item.quantity}`).join(", ")}</p>
          </div>
          <span class="status-pill">${labels[order.status] || order.status}</span>
        </div>
        <div class="record-actions">
          ${statusSelect(order.status, "order", order.id)}
          <input data-tracking-order="${order.id}" placeholder="Takip numarası" value="${escapeHtml(order.tracking_number || "")}">
          <button class="primary-btn" data-save-order="${order.id}">Kaydet</button>
          <button class="danger-btn" data-delete-order="${order.id}">Sil</button>
        </div>
      </article>
    `).join("") || `<p class="muted">Sipariş bulunamadı.</p>`;
  }

  async function loadOrders() {
    state.orders = await api("/api/admin/orders");
    renderOrders();
  }

  function renderUsers() {
    const rows = filtered(state.users, "#userSearch", ["full_name", "email", "phone", "role"]);
    $("#usersList").innerHTML = rows.map((user) => `
      <article class="record-card">
        <div class="record-top">
          <div>
            <strong>${escapeHtml(user.full_name)}</strong>
            <p class="muted">${escapeHtml(user.email)} • ${escapeHtml(user.phone || "Telefon yok")}</p>
            <p>${escapeHtml(user.role)} ${user.is_banned ? "• Banlı" : ""}</p>
          </div>
          <button class="small-btn" data-toggle-detail="${user.id}">Detay</button>
        </div>
        <div id="user-detail-${user.id}" hidden>
          <p><strong>Adresler:</strong> ${(user.addresses || []).map((a) => escapeHtml(a.address)).join(" | ") || "Yok"}</p>
          <p><strong>Hayvanlar:</strong> ${(user.pets || []).map((p) => escapeHtml(`${p.name} (${p.species})`)).join(", ") || "Yok"}</p>
        </div>
      </article>
    `).join("") || `<p class="muted">Kullanıcı bulunamadı.</p>`;
  }

  async function loadUsers() {
    state.users = await api("/api/admin/users");
    renderUsers();
  }

  function renderPets() {
    const rows = filtered(state.pets, "#petSearch", ["name", "species", "owner", "phone", "notes"]);
    $("#petsList").innerHTML = rows.map((pet) => `
      <article class="record-card">
        <div class="record-top">
          <div>
            <strong>${escapeHtml(pet.name)}</strong>
            <p class="muted">${escapeHtml(pet.species)} ${pet.breed ? `• ${escapeHtml(pet.breed)}` : ""} ${pet.age ? `• ${escapeHtml(pet.age)}` : ""}</p>
            <p>${escapeHtml(pet.owner || "Sahip bilgisi yok")} • ${escapeHtml(pet.phone || "")}</p>
            <p class="muted">${escapeHtml(pet.notes || "")}</p>
          </div>
          <span class="status-pill">${escapeHtml(pet.source)}</span>
        </div>
        <div class="record-actions">
          <button class="small-btn" data-edit-pet="${pet.record_key}">Düzenle</button>
          <button class="danger-btn" data-delete-pet="${pet.source}:${pet.id}">Sil</button>
        </div>
      </article>
    `).join("") || `<p class="muted">Hasta kaydı bulunamadı.</p>`;
  }

  async function loadPets() {
    state.pets = await api("/api/admin/pets");
    renderPets();
  }

  function fillPetForm(pet = {}) {
    const form = $("#petForm");
    const fields = form.elements;
    form.hidden = false;
    fields.id.value = pet.id || "";
    fields.source.value = pet.source || "clinic";
    fields.name.value = pet.name || "";
    fields.species.value = pet.species || "";
    fields.breed.value = pet.breed || "";
    fields.age.value = pet.age || "";
    fields.owner_name.value = pet.owner || pet.owner_name || "";
    fields.phone.value = pet.phone || "";
    fields.notes.value = pet.notes || "";
  }

  async function savePet(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const path = data.id ? `/api/admin/pets/update/${data.source}/${data.id}` : "/api/admin/pets/add";
    await api(path, { method: data.id ? "PATCH" : "POST", body: JSON.stringify(data) });
    form.reset();
    form.elements.source.value = "clinic";
    form.hidden = true;
    toast("Hasta kaydı kaydedildi");
    await loadPets();
  }

  async function loadSection(section) {
    try {
      if (section === "dashboard") await loadDashboard();
      if (section === "products") await loadProducts();
      if (section === "appointments") await loadAppointments();
      if (section === "orders") await loadOrders();
      if (section === "users") await loadUsers();
      if (section === "pets") await loadPets();
    } catch (error) {
      toast(error.message, true);
    }
  }

  function bindEvents() {
    $("#adminLoginForm")?.addEventListener("submit", handleLogin);
    $("#adminLogout")?.addEventListener("click", logout);
    $("#sidebarToggle")?.addEventListener("click", openSidebar);
    $("#sidebarOverlay")?.addEventListener("click", closeSidebar);
    $("#themeToggle")?.addEventListener("click", () => setTheme(document.body.classList.contains("dark") ? "light" : "dark"));
    $$(".nav-item").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.section)));
    $$("[data-refresh]").forEach((button) => button.addEventListener("click", () => loadSection(button.dataset.refresh)));
    $$("[data-open-form]").forEach((button) => button.addEventListener("click", () => {
      const form = $(`#${button.dataset.openForm}`);
      form.reset();
      form.hidden = false;
      if (form.elements.source) form.elements.source.value = "clinic";
    }));
    $$("[data-close-form]").forEach((button) => button.addEventListener("click", () => {
      $(`#${button.dataset.closeForm}`).hidden = true;
    }));

    $("#productForm")?.addEventListener("submit", saveProduct);
    $("#petForm")?.addEventListener("submit", savePet);
    ["productSearch", "appointmentSearch", "orderSearch", "userSearch", "petSearch"].forEach((id) => {
      $(`#${id}`)?.addEventListener("input", () => {
        if (id === "productSearch") renderProducts();
        if (id === "appointmentSearch") renderAppointments();
        if (id === "orderSearch") renderOrders();
        if (id === "userSearch") renderUsers();
        if (id === "petSearch") renderPets();
      });
    });

    document.addEventListener("click", async (event) => {
      const target = event.target;
      try {
        const productId = target.dataset.editProduct;
        if (productId) fillProductForm(state.products.find((item) => String(item.id) === productId));

        const deleteProduct = target.dataset.deleteProduct;
        if (deleteProduct && confirm("Ürünü silmek istiyor musunuz?")) {
          await api(`/api/admin/products/delete/${deleteProduct}`, { method: "DELETE" });
          toast("Ürün silindi");
          await loadProducts();
        }

        const appointmentId = target.dataset.saveAppointment;
        if (appointmentId) {
          const status = document.querySelector(`[data-status-appointment="${appointmentId}"]`).value;
          await api(`/api/admin/appointments/update/${appointmentId}`, { method: "PATCH", body: JSON.stringify({ status }) });
          toast("Randevu güncellendi");
          await loadAppointments();
        }

        const addPetAppointment = target.dataset.addAppointmentPet;
        if (addPetAppointment) {
          await api(`/api/admin/appointments/${addPetAppointment}/add-pet`, { method: "POST" });
          toast("Pet kaydedildi");
          await loadAppointments();
          await loadPets();
        }

        const deleteAppointment = target.dataset.deleteAppointment;
        if (deleteAppointment && confirm("Randevu admin listesinden kaldırılsın mı?")) {
          await api(`/api/admin/appointments/delete/${deleteAppointment}`, { method: "DELETE" });
          await loadAppointments();
        }

        const orderId = target.dataset.saveOrder;
        if (orderId) {
          const status = document.querySelector(`[data-status-order="${orderId}"]`).value;
          const tracking = document.querySelector(`[data-tracking-order="${orderId}"]`).value;
          await api(`/api/admin/orders/update/${orderId}`, {
            method: "PATCH",
            body: JSON.stringify({ status, tracking_number: tracking }),
          });
          toast("Sipariş güncellendi");
          await loadOrders();
        }

        const deleteOrder = target.dataset.deleteOrder;
        if (deleteOrder && confirm("Sipariş admin listesinden kaldırılsın mı?")) {
          await api(`/api/admin/orders/delete/${deleteOrder}`, { method: "DELETE" });
          await loadOrders();
        }

        const detailId = target.dataset.toggleDetail;
        if (detailId) {
          const detail = $(`#user-detail-${detailId}`);
          detail.hidden = !detail.hidden;
        }

        const petKey = target.dataset.editPet;
        if (petKey) fillPetForm(state.pets.find((item) => item.record_key === petKey));

        const deletePet = target.dataset.deletePet;
        if (deletePet && confirm("Hasta kaydı admin listesinden kaldırılsın mı?")) {
          const [source, id] = deletePet.split(":");
          await api(`/api/admin/pets/delete/${source}/${id}`, { method: "DELETE" });
          await loadPets();
        }
      } catch (error) {
        toast(error.message, true);
      }
    });
  }

  async function boot() {
    bindEvents();
    setTheme(localStorage.getItem("gumusAdminTheme") || "light");
    if (document.body.dataset.loginOnly === "true") {
      if (state.token) {
        try {
          showApp();
          await loadDashboard();
          document.body.dataset.loginOnly = "false";
          history.replaceState(null, "", "/admin");
          return;
        } catch (_) {
          localStorage.removeItem("gumusAdminToken");
          state.token = "";
        }
      }
      showLoginOnly();
      return;
    }
    showApp();
    await loadDashboard();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
