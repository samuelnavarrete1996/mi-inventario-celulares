// app.js - Configuración global, estado y utilidades

const App = {
    currentTab: 'inventario',

    init() {
        this.setupNavigation();
        this.updateHeaderStats();
    },

    setupNavigation() {
        const tabBtns = document.querySelectorAll('.nav-tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                this.switchTab(tab);
            });
        });
    },

    switchTab(tabName) {
        this.currentTab = tabName;

        // Actualizar botones de navegación
        document.querySelectorAll('.nav-tab-btn').forEach(btn => {
            if (btn.dataset.tab === tabName) {
                btn.classList.add('bg-blue-600', 'text-white', 'shadow-sm');
                btn.classList.remove('text-slate-600', 'hover:bg-slate-100');
            } else {
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-sm');
                btn.classList.add('text-slate-600', 'hover:bg-slate-100');
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
        } else if (tabName === 'reportes') {
            Reportes.cargarDashboard();
            Reportes.cargarHistorialVentas();
        }

        this.updateHeaderStats();
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
            return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                <span class="w-1.5 h-1.5 mr-1.5 bg-emerald-500 rounded-full"></span> Grado A (Excelente)
            </span>`;
        } else if (g === 'B') {
            return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                <span class="w-1.5 h-1.5 mr-1.5 bg-amber-500 rounded-full"></span> Grado B (Regular)
            </span>`;
        } else if (g === 'C') {
            return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
                <span class="w-1.5 h-1.5 mr-1.5 bg-rose-500 rounded-full"></span> Grado C (Maltratado)
            </span>`;
        }
        return `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">${grado}</span>`;
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

        toast.className = `${bgColors[type] || bgColors.info} px-4 py-3 rounded-xl shadow-lg flex items-center space-x-3 text-sm font-medium transform transition-all duration-300 opacity-0 translate-y-2`;
        
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

        // Animar entrada
        setTimeout(() => {
            toast.classList.remove('opacity-0', 'translate-y-2');
        }, 10);

        // Eliminar después de 4 segundos
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
    if (typeof Garantias !== 'undefined') {
        Garantias.init();
    }
});
