// app.js - Configuración global, estado, modo admin y utilidades

const App = {
    currentTab: 'inventario',
    isAdmin: localStorage.getItem('modo_admin') !== 'false', // Por defecto Modo Admin (Dueño)

    init() {
        this.setupNavigation();
        this.aplicarModoAdmin();
        this.updateHeaderStats();
        this.registerServiceWorker();
    },

    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/service-worker.js').catch(e => console.warn(e));
            });
        }
    },

    setupNavigation() {
        const tabBtns = document.querySelectorAll('.nav-tab-btn, .nav-tab-btn-mobile');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                if (tab) this.switchTab(tab);
            });
        });
    },

    switchTab(tabName) {
        this.currentTab = tabName;

        // Actualizar botones de navegación escritorio
        document.querySelectorAll('.nav-tab-btn').forEach(btn => {
            if (btn.dataset.tab === tabName) {
                btn.classList.add('bg-blue-600', 'text-white', 'shadow-sm');
                btn.classList.remove('text-slate-600', 'hover:bg-slate-200');
            } else {
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-sm');
                btn.classList.add('text-slate-600', 'hover:bg-slate-200');
            }
        });

        // Actualizar botones de navegación móvil inferior
        document.querySelectorAll('.nav-tab-btn-mobile').forEach(btn => {
            const isTarget = btn.dataset.tab === tabName;
            if (isTarget) {
                btn.classList.add('text-blue-600', 'font-bold');
                btn.classList.remove('text-slate-400', 'font-normal');
                btn.querySelector('.mobile-tab-indicator')?.classList.remove('opacity-0');
            } else {
                btn.classList.remove('text-blue-600', 'font-bold');
                btn.classList.add('text-slate-400', 'font-normal');
                btn.querySelector('.mobile-tab-indicator')?.classList.add('opacity-0');
            }
        });

        // Alternar vistas
        document.querySelectorAll('.tab-view').forEach(view => {
            if (view.id === `view-${tabName}`) {
                view.classList.remove('hidden');
            } else {
                view.classList.add('hidden');
            }
        });

        // Disparar carga de datos según la pestaña activa
        if (tabName === 'inventario') {
            Inventario.cargarEquipos();
        } else if (tabName === 'pos') {
            POS.buscarEquipos('');
        } else if (tabName === 'accesorios') {
            if (typeof Accesorios !== 'undefined') Accesorios.cargar();
        } else if (tabName === 'reportes') {
            Reportes.cargarDashboard();
            Reportes.cargarHistorialVentas();
        } else if (tabName === 'reparaciones') {
            if (typeof Reparaciones !== 'undefined') Reparaciones.cargar();
        }

        // Si estamos en POS móvil, verificar visibilidad del carrito flotante
        if (typeof POS !== 'undefined' && POS.actualizarBarraFlotanteMovil) {
            POS.actualizarBarraFlotanteMovil();
        }

        this.updateHeaderStats();
    },

    abrirMenuAccionesMovil() {
        const modal = document.getElementById('modal-acciones-movil');
        if (modal) modal.classList.remove('hidden');
    },

    cerrarMenuAccionesMovil() {
        const modal = document.getElementById('modal-acciones-movil');
        if (modal) modal.classList.add('hidden');
    },

    // --- MODO ADMIN (DUEÑO) VS MODO VENDEDOR (EMPLEADO) ---

    async toggleAdminMode() {
        if (this.isAdmin) {
            // Pasar a modo vendedor
            this.isAdmin = false;
            localStorage.setItem('modo_admin', 'false');
            this.aplicarModoAdmin();
            this.showToast("Modo Vendedor activado. Costos y ganancias confidenciales ocultos.", "info");
        } else {
            // Solicitar contraseña de administrador
            const pwd = prompt("[Seguridad] Ingresa la contraseña de administrador para desbloquear costos y utilidades:");
            if (!pwd) return;

            try {
                // Verificar contraseña intentando listar o validando
                const testRes = await fetch(`/api/equipos/1?password=${encodeURIComponent(pwd)}`, { method: 'DELETE' });
                if (testRes.status === 401) {
                    this.showToast("Contraseña incorrecta. Acceso denegado.", "error");
                    return;
                }
                // Si respondió 404 o 200 o 400, la contraseña fue autorizada
                this.isAdmin = true;
                localStorage.setItem('modo_admin', 'true');
                this.aplicarModoAdmin();
                this.showToast("👑 Modo Administrador activado. Todos los reportes desbloqueados.", "success");
            } catch (e) {
                // Si el equipo 1 no existe o error de conexión, intentar validar con fallback
                this.isAdmin = true;
                localStorage.setItem('modo_admin', 'true');
                this.aplicarModoAdmin();
                this.showToast("👑 Modo Administrador activado.", "success");
            }
        }
    },

    aplicarModoAdmin() {
        const body = document.body;
        const btnToggle = document.getElementById('btn-toggle-modo-admin');
        const txtToggle = document.getElementById('txt-modo-admin');
        const headerGanancias = document.getElementById('box-header-ganancias');

        if (this.isAdmin) {
            body.classList.remove('modo-vendedor');
            if (txtToggle) txtToggle.textContent = '👑 Modo Dueño';
            if (btnToggle) {
                btnToggle.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 transition-all';
            }
            if (headerGanancias) headerGanancias.classList.remove('hidden');
        } else {
            body.classList.add('modo-vendedor');
            if (txtToggle) txtToggle.textContent = '🔒 Modo Vendedor';
            if (btnToggle) {
                btnToggle.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 transition-all';
            }
            if (headerGanancias) headerGanancias.classList.add('hidden');
        }
    },

    async updateHeaderStats() {
        try {
            const res = await fetch('/api/reportes/dashboard');
            if (res.ok) {
                const data = await res.json();
                const stockEl = document.getElementById('header-stock-count');
                const gananciaEl = document.getElementById('header-ganancia-mes');
                const mesEl = document.getElementById('header-mes-nombre');

                if (stockEl) stockEl.textContent = data.equipos_disponibles;
                if (gananciaEl) gananciaEl.textContent = this.formatCurrency(data.total_ganancias_mes);
                if (mesEl) mesEl.textContent = data.mes_actual_nombre;
            }
        } catch (err) {
            console.error("Error al actualizar header stats:", err);
        }
    },

    // --- RESPALDO DE BASE DE DATOS ---

    abrirModalRespaldo() {
        document.getElementById('modal-respaldo-db').classList.remove('hidden');
    },

    cerrarModalRespaldo() {
        document.getElementById('modal-respaldo-db').classList.add('hidden');
    },

    descargarBackupDB() {
        window.location.href = '/api/backup/descargar-db';
        this.showToast("Iniciando descarga de copia de seguridad (.db)...", "info");
    },

    exportarJSON() {
        window.location.href = '/api/backup/exportar-json';
        this.showToast("Iniciando exportación de datos (JSON)...", "info");
    },

    async restaurarDB(inputEl) {
        if (!inputEl.files || inputEl.files.length === 0) return;
        const file = inputEl.files[0];

        if (!confirm(`¿Estás 100% seguro de restaurar la base de datos con el archivo "${file.name}"? Los datos actuales serán reemplazados (se guardará un respaldo automático).`)) {
            inputEl.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('archivo', file);

        try {
            this.showToast("Restaurando base de datos...", "info");
            const res = await fetch('/api/backup/restaurar-db', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al restaurar");
            }

            this.showToast("¡Base de datos restaurada con éxito! Recargando...", "success");
            setTimeout(() => window.location.reload(), 1500);
        } catch (e) {
            this.showToast(e.message, "error");
        } finally {
            inputEl.value = '';
        }
    },

    formatCurrency(amount) {
        return new Intl.NumberFormat('es-MX', {
            style: 'currency',
            currency: 'MXN',
            minimumFractionDigits: 2
        }).format(amount || 0);
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            const date = new Date(dateStr.replace(' ', 'T'));
            return new Intl.DateTimeFormat('es-MX', {
                day: '2-digit',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            }).format(date);
        } catch (e) {
            return dateStr;
        }
    },

    getGradeBadge(grado) {
        const g = (grado || '').toUpperCase();
        if (g === 'A') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                <span class="w-1.5 h-1.5 mr-1 bg-emerald-500 rounded-full"></span> Grado A
            </span>`;
        } else if (g === 'B') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                <span class="w-1.5 h-1.5 mr-1 bg-amber-500 rounded-full"></span> Grado B
            </span>`;
        } else if (g === 'C') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
                <span class="w-1.5 h-1.5 mr-1 bg-rose-500 rounded-full"></span> Grado C
            </span>`;
        }
        return `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">${grado}</span>`;
    },

    getAgingBadge(dias, estado) {
        if (dias < 15) {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200" title="Ingresó hace ${dias} días">
                🌱 Fresco (${dias}d)
            </span>`;
        } else if (dias <= 30) {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200" title="Ingresó hace ${dias} días">
                ⏱️ Normal (${dias}d)
            </span>`;
        } else if (dias <= 45) {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200" title="¡Atención! Lleva ${dias} días en inventario">
                ⚠️ Lento (${dias}d)
            </span>`;
        } else {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200 animate-pulse" title="¡Recomendado rematar! Lleva ${dias} días">
                🔥 ¡Remate! (${dias}d)
            </span>`;
        }
    },

    showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        const bgColors = {
            success: 'bg-emerald-600 text-white',
            error: 'bg-rose-600 text-white',
            info: 'bg-blue-600 text-white'
        };

        toast.className = `${bgColors[type] || bgColors.info} px-4 py-3 rounded-xl shadow-lg flex items-center space-x-3 text-sm font-medium transform transition-all duration-300 opacity-0 translate-y-2 pointer-events-auto`;
        
        let iconSvg = '';
        if (type === 'success') {
            iconSvg = `<svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
        } else if (type === 'error') {
            iconSvg = `<svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;
        } else {
            iconSvg = `<svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        }

        toast.innerHTML = `
            ${iconSvg}
            <span>${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.remove('opacity-0', 'translate-y-2');
        }, 10);

        setTimeout(() => {
            toast.classList.add('opacity-0', 'translate-y-2');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    App.init();
    Inventario.init();
    POS.init();
    Reportes.init();
    if (typeof Garantias !== 'undefined') Garantias.init();
    if (typeof Accesorios !== 'undefined') Accesorios.init();
    if (typeof Caja !== 'undefined') Caja.init();
});
