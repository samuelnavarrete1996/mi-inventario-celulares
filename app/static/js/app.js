// app.js - Configuración global, estado, modo admin y utilidades

const App = {
    currentTab: 'inventario',
    isAdmin: false, // Por seguridad: el backend determina el rol mediante cookie HttpOnly
    currentUser: null,

    async init() {
        this.setupNavigation();
        await this.verificarSesion();
        this.updateHeaderStats();
        this.registerServiceWorker();
    },

    async verificarSesion() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.user && data.user.rol === 'dueno') {
                    this.isAdmin = true;
                    this.currentUser = data.user;
                } else {
                    this.isAdmin = false;
                    this.currentUser = (data.authenticated && data.user) ? data.user : null;
                }
            } else {
                this.isAdmin = false;
                this.currentUser = null;
            }
        } catch (e) {
            this.isAdmin = false;
            this.currentUser = null;
        }
        this.aplicarModoAdmin();
    },

    deferredPrompt: null,

    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js').then(reg => {
                    reg.update();
                }).catch(e => console.warn(e));

                let refreshing = false;
                navigator.serviceWorker.addEventListener('controllerchange', () => {
                    if (!refreshing) {
                        refreshing = true;
                        window.location.reload();
                    }
                });
            });
        }

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
        });
    },

    async instalarPWA() {
        if (this.deferredPrompt) {
            this.deferredPrompt.prompt();
            const { outcome } = await this.deferredPrompt.userChoice;
            if (outcome === 'accepted') {
                this.showToast("¡Aplicación instalada con éxito!", "success");
            }
            this.deferredPrompt = null;
        } else {
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
            if (isIOS) {
                alert("📱 Para instalar en tu iPhone:\n\n1. Toca el botón 'Compartir' (el cuadro con una flecha hacia arriba en Safari).\n2. Baja y pulsa 'Agregar a pantalla de inicio' (➕).\n3. Toca 'Agregar' arriba a la derecha.");
            } else {
                alert("📱 Para instalar en tu celular o PC:\n\n1. Toca los tres puntos (⋮) del navegador arriba a la derecha.\n2. Selecciona 'Instalar aplicación' o 'Agregar a la pantalla principal'.\n3. ¡Listo! Se creará el acceso con el icono de tu inventario.");
            }
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
        if (tabName === 'reportes' && !this.isAdmin) {
            this.showToast("El módulo de Reportes requiere permisos de Dueño.", "warning");
            return;
        }
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
            try {
                // Iniciar sesión como vendedor con PIN rápido (1234)
                await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin: '1234' })
                });
            } catch (e) {
                await fetch('/api/auth/logout', { method: 'POST' });
            }

            this.isAdmin = false;
            this.currentUser = { rol: 'vendedor', nombre: 'Vendedor' };
            this.aplicarModoAdmin();

            if (this.currentTab === 'reportes') {
                this.switchTab('inventario');
            }

            // Recargar datos para que el backend entregue respuestas sanitizadas sin costos
            if (typeof Inventario !== 'undefined' && Inventario.cargarEquipos) {
                Inventario.cargarEquipos();
            }
            if (typeof Accesorios !== 'undefined' && Accesorios.cargar) {
                Accesorios.cargar();
            }
            this.updateHeaderStats();
            this.showToast("🔒 Modo Vendedor activado. Costos y ganancias confidenciales ocultos.", "info");
        } else {
            // Solicitar contraseña o PIN de Dueño
            const pwd = prompt("[Seguridad] Ingresa la contraseña de administrador o PIN de Dueño:");
            if (!pwd) return;

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: pwd, username: 'admin' })
                });

                if (res.status === 429) {
                    const errData = await res.json().catch(() => ({}));
                    this.showToast(errData.detail || "Demasiados intentos fallidos. Bloqueado temporalmente.", "error");
                    return;
                }

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    this.showToast(errData.detail || "Contraseña o PIN incorrecto. Acceso denegado.", "error");
                    return;
                }

                const data = await res.json();
                if (data.user && data.user.rol === 'dueno') {
                    this.isAdmin = true;
                    this.currentUser = data.user;
                    this.aplicarModoAdmin();

                    // Recargar datos para que el backend entregue costos y ganancias reales
                    if (typeof Inventario !== 'undefined' && Inventario.cargarEquipos) {
                        Inventario.cargarEquipos();
                    }
                    if (typeof Accesorios !== 'undefined' && Accesorios.cargar) {
                        Accesorios.cargar();
                    }
                    this.updateHeaderStats();
                    this.showToast(`👑 Bienvenido, ${data.user.nombre}. Modo Dueño activado.`, "success");
                } else {
                    this.showToast("El usuario autenticado no cuenta con rol de Dueño.", "warning");
                }
            } catch (e) {
                this.showToast("Error de conexión al autenticar: " + e.message, "error");
            }
        }
    },

    aplicarModoAdmin() {
        const body = document.body;
        const btnToggle = document.getElementById('btn-toggle-modo-admin');
        const txtToggle = document.getElementById('txt-modo-admin');
        const headerGanancias = document.getElementById('box-header-ganancias');
        const txtMovil = document.getElementById('txt-modo-admin-movil');
        const iconMovil = document.getElementById('icon-modo-admin-movil');

        if (this.isAdmin) {
            body.classList.remove('modo-vendedor');
            if (txtToggle) txtToggle.textContent = '👑 Modo Dueño';
            if (btnToggle) {
                btnToggle.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 transition-all shadow-2xs';
            }
            if (txtMovil) txtMovil.textContent = 'Modo Dueño';
            if (iconMovil) iconMovil.textContent = '👑';
            if (headerGanancias) headerGanancias.classList.remove('hidden');
        } else {
            body.classList.add('modo-vendedor');
            if (txtToggle) txtToggle.textContent = '🔒 Modo Vendedor';
            if (btnToggle) {
                btnToggle.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 transition-all shadow-2xs';
            }
            if (txtMovil) txtMovil.textContent = 'Modo Vendedor';
            if (iconMovil) iconMovil.textContent = '🔒';
            if (headerGanancias) headerGanancias.classList.add('hidden');
            const boxMargen = document.getElementById('box-margen-proyectado');
            if (boxMargen) boxMargen.classList.add('hidden');
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
                if (gananciaEl) {
                    gananciaEl.textContent = data.total_ganancias_mes !== null && data.total_ganancias_mes !== undefined
                        ? this.formatCurrency(data.total_ganancias_mes)
                        : '••••••';
                }
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
