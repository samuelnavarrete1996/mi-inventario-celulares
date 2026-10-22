// configuracion.js - Gestión de Marca Blanca, datos del negocio y formato de tickets

const ConfiguracionTienda = {
    datos: null,
    anchoTicket: '80mm', // '58mm' o '80mm'

    async init() {
        this.cargarAnchoTicketPreferido();
        await this.cargar();
    },

    cargarAnchoTicketPreferido() {
        const guardado = localStorage.getItem('pos_ancho_ticket');
        if (guardado === '58mm' || guardado === '80mm') {
            this.anchoTicket = guardado;
        }
        this.actualizarBotonesAncho();
        this.aplicarClasesAnchoTickets();
    },

    setAnchoTicket(ancho) {
        if (ancho !== '58mm' && ancho !== '80mm') return;
        this.anchoTicket = ancho;
        localStorage.setItem('pos_ancho_ticket', ancho);
        this.actualizarBotonesAncho();
        this.aplicarClasesAnchoTickets();
        if (typeof App !== 'undefined' && App.showToast) {
            App.showToast(`Formato de ticket configurado a ${ancho}`, "info");
        }
    },

    actualizarBotonesAncho() {
        document.querySelectorAll('.btn-ancho-58mm').forEach(b => {
            if (this.anchoTicket === '58mm') {
                b.className = 'btn-ancho-58mm px-2.5 py-1 text-xs font-bold rounded-lg bg-blue-600 text-white shadow-xs';
            } else {
                b.className = 'btn-ancho-58mm px-2.5 py-1 text-xs font-bold rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200';
            }
        });
        document.querySelectorAll('.btn-ancho-80mm').forEach(b => {
            if (this.anchoTicket === '80mm') {
                b.className = 'btn-ancho-80mm px-2.5 py-1 text-xs font-bold rounded-lg bg-blue-600 text-white shadow-xs';
            } else {
                b.className = 'btn-ancho-80mm px-2.5 py-1 text-xs font-bold rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200';
            }
        });

        const r58 = document.getElementById('cfg-radio-58mm');
        const r80 = document.getElementById('cfg-radio-80mm');
        if (r58) r58.checked = (this.anchoTicket === '58mm');
        if (r80) r80.checked = (this.anchoTicket === '80mm');
    },

    aplicarClasesAnchoTickets() {
        const contenedores = document.querySelectorAll('.ticket-printable-container');
        contenedores.forEach(c => {
            c.classList.remove('ticket-58mm', 'ticket-80mm');
            c.classList.add(`ticket-${this.anchoTicket}`);
        });
    },

    async cargar() {
        try {
            const res = await fetch('/api/configuracion');
            if (res.status === 401 || res.status === 403) return;
            if (!res.ok) throw new Error("No se pudo cargar la configuración de tienda");
            this.datos = await res.json();
            this.llenarFormulario(this.datos);
            this.aplicarMarcaBlanca(this.datos);
            if (typeof Empleados !== 'undefined' && Empleados.cargar) {
                Empleados.cargar();
            }
        } catch (e) {
            console.error("Error cargando configuración:", e);
        }
    },

    llenarFormulario(d) {
        if (!d) return;
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val || '';
        };

        setVal('cfg-nombre-comercial', d.nombre_comercial);
        setVal('cfg-telefono', d.telefono);
        setVal('cfg-whatsapp', d.whatsapp_notificaciones);
        setVal('cfg-direccion', d.direccion);
        setVal('cfg-encabezado-ticket', d.encabezado_ticket);
        setVal('cfg-pie-ticket', d.pie_ticket_garantia);

        const logoImg = document.getElementById('cfg-logo-preview');
        const logoPlaceholder = document.getElementById('cfg-logo-placeholder');
        if (d.logo_url) {
            if (logoImg) {
                logoImg.src = d.logo_url;
                logoImg.classList.remove('hidden');
            }
            if (logoPlaceholder) logoPlaceholder.classList.add('hidden');
        } else {
            if (logoImg) logoImg.classList.add('hidden');
            if (logoPlaceholder) logoPlaceholder.classList.remove('hidden');
        }

        const infoSlug = document.getElementById('cfg-info-slug');
        if (infoSlug) infoSlug.textContent = d.slug || 'demo';
        const infoTenantId = document.getElementById('cfg-info-tenant-id');
        if (infoTenantId) infoTenantId.textContent = `#${d.tenant_id}`;

        this.actualizarBotonesAncho();
    },

    previsualizarLogo(input) {
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];
        if (file.size > 2 * 1024 * 1024) {
            App.showToast("El archivo seleccionado supera el límite de 2 MB.", "error");
            input.value = '';
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const logoImg = document.getElementById('cfg-logo-preview');
            const logoPlaceholder = document.getElementById('cfg-logo-placeholder');
            if (logoImg) {
                logoImg.src = e.target.result;
                logoImg.classList.remove('hidden');
            }
            if (logoPlaceholder) logoPlaceholder.classList.add('hidden');
        };
        reader.readAsDataURL(file);
    },

    async subirLogo() {
        const input = document.getElementById('cfg-logo-input');
        if (!input || !input.files || !input.files[0]) {
            App.showToast("Por favor selecciona una imagen primero.", "warning");
            return;
        }
        const file = input.files[0];
        if (file.size > 2 * 1024 * 1024) {
            App.showToast("La imagen supera los 2 MB permitidos.", "error");
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        const btn = document.getElementById('btn-subir-logo');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="animate-spin inline-block mr-1">⏳</span> Subiendo...`;
        }

        try {
            const res = await fetch('/api/configuracion/logo', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Error al subir logotipo.");
            }

            const data = await res.json();
            App.showToast("✅ Logotipo actualizado exitosamente.", "success");
            if (this.datos) this.datos.logo_url = data.logo_url;
            this.aplicarMarcaBlanca(this.datos);
            input.value = '';
        } catch (e) {
            App.showToast(e.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<span>Subir Logotipo</span>`;
            }
        }
    },

    async guardar() {
        const getVal = id => {
            const el = document.getElementById(id);
            return el ? el.value.trim() : '';
        };

        const payload = {
            nombre_comercial: getVal('cfg-nombre-comercial'),
            telefono: getVal('cfg-telefono'),
            whatsapp_notificaciones: getVal('cfg-whatsapp'),
            direccion: getVal('cfg-direccion'),
            encabezado_ticket: getVal('cfg-encabezado-ticket'),
            pie_ticket_garantia: getVal('cfg-pie-ticket')
        };

        if (!payload.nombre_comercial) {
            App.showToast("El nombre comercial no puede estar vacío.", "error");
            return;
        }

        const radio58 = document.getElementById('cfg-radio-58mm');
        const anchoSeleccionado = (radio58 && radio58.checked) ? '58mm' : '80mm';
        this.setAnchoTicket(anchoSeleccionado);

        const btn = document.getElementById('btn-guardar-cfg');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="animate-spin inline-block mr-1">⏳</span> Guardando...`;
        }

        try {
            const res = await fetch('/api/configuracion', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Error al guardar ajustes.");
            }

            this.datos = await res.json();
            this.aplicarMarcaBlanca(this.datos);
            App.showToast("✅ Configuración de tienda guardada exitosamente.", "success");
        } catch (e) {
            App.showToast(e.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<span>Guardar Configuración de Tienda</span>`;
            }
        }
    },

    aplicarMarcaBlanca(d) {
        if (!d) return;

        // 1. Encabezado principal de la app
        const headerTitle = document.getElementById('header-store-name');
        if (headerTitle) {
            headerTitle.innerHTML = `${App.escapeHtml(d.nombre_comercial)} <span class="font-normal text-slate-500 hidden sm:inline">| Celulares & POS</span>`;
        }
        document.title = `${d.nombre_comercial} - POS & Inventario`;

        // Logo en Header
        const headerLogoImg = document.getElementById('header-logo-img');
        const headerLogoIcon = document.getElementById('header-logo-icon');
        if (d.logo_url) {
            if (headerLogoImg) {
                headerLogoImg.src = d.logo_url;
                headerLogoImg.classList.remove('hidden');
            }
            if (headerLogoIcon) headerLogoIcon.classList.add('hidden');
        } else {
            if (headerLogoImg) headerLogoImg.classList.add('hidden');
            if (headerLogoIcon) headerLogoIcon.classList.remove('hidden');
        }

        // 2. Plantillas de Tickets (Recibo de Venta y Boleta de Taller)
        document.querySelectorAll('.ticket-nombre-comercial').forEach(el => {
            el.textContent = d.nombre_comercial;
        });
        document.querySelectorAll('.ticket-encabezado').forEach(el => {
            el.textContent = d.encabezado_ticket || `${d.nombre_comercial} | Compra, Venta y Servicio`;
        });
        document.querySelectorAll('.ticket-direccion').forEach(el => {
            el.textContent = d.direccion || 'Dirección de Matriz';
        });
        document.querySelectorAll('.ticket-telefono').forEach(el => {
            el.textContent = d.whatsapp_notificaciones || d.telefono || '';
        });
        document.querySelectorAll('.ticket-logo-img').forEach(el => {
            if (d.logo_url) {
                el.src = d.logo_url;
                el.classList.remove('hidden');
            } else {
                el.classList.add('hidden');
            }
        });
        const garantiaEl = document.getElementById('recibo-garantia-texto');
        if (garantiaEl && d.pie_ticket_garantia) {
            garantiaEl.textContent = d.pie_ticket_garantia;
        }

        this.aplicarClasesAnchoTickets();
    }
};
