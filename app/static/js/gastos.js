// gastos.js - Módulo de Control de Gastos Operativos y Ganancia Neta Real
// Compatible con Multi-Tenant SaaS y control de acceso exclusivo para Dueño

const Gastos = {
    gastos: [],

    init() {
        const inpMes = document.getElementById('gastos-filtro-mes');
        if (inpMes && !inpMes.value) {
            const hoy = new Date();
            const yyyy = hoy.getFullYear();
            const mm = String(hoy.getMonth() + 1).padStart(2, '0');
            inpMes.value = `${yyyy}-${mm}`;
        }
        const inpFecha = document.getElementById('gasto-fecha');
        if (inpFecha && !inpFecha.value) {
            inpFecha.value = new Date().toISOString().split('T')[0];
        }
    },

    abrirModalNuevo() {
        const modal = document.getElementById('modal-nuevo-gasto');
        if (!modal) return;
        document.getElementById('form-nuevo-gasto')?.reset();
        const inpFecha = document.getElementById('gasto-fecha');
        if (inpFecha) inpFecha.value = new Date().toISOString().split('T')[0];
        modal.classList.remove('hidden');
        document.getElementById('gasto-concepto')?.focus();
    },

    cerrarModal() {
        const modal = document.getElementById('modal-nuevo-gasto');
        if (modal) modal.classList.add('hidden');
    },

    async cargar() {
        this.init();
        const mes = document.getElementById('gastos-filtro-mes')?.value || '';
        const cat = document.getElementById('gastos-filtro-categoria')?.value || 'Todas';

        try {
            let url = '/api/gastos?';
            if (mes) url += `mes=${encodeURIComponent(mes)}&`;
            if (cat && cat !== 'Todas') url += `categoria=${encodeURIComponent(cat)}&`;

            const res = await fetch(url);
            if (!res.ok) {
                if (res.status === 403) return; // No es dueño
                throw new Error("Error al obtener lista de gastos");
            }
            this.gastos = await res.json();
            this.render();
            this.actualizarMetricas(mes);
        } catch (e) {
            console.error("Error cargando gastos:", e);
        }
    },

    actualizarMetricas(mesSeleccionado) {
        const hoyStr = new Date().toISOString().split('T')[0];
        let totalMes = 0;
        let totalHoy = 0;
        let countHoy = 0;
        const porCat = {};

        this.gastos.forEach(g => {
            const m = parseFloat(g.monto) || 0;
            totalMes += m;
            if (g.fecha && g.fecha.startsWith(hoyStr)) {
                totalHoy += m;
                countHoy++;
            }
            const c = g.categoria || 'General';
            porCat[c] = (porCat[c] || 0) + m;
        });

        // Top categoría
        let topCat = '--';
        let topMonto = 0;
        for (const [c, m] of Object.entries(porCat)) {
            if (m > topMonto) {
                topMonto = m;
                topCat = c;
            }
        }

        const statMes = document.getElementById('gastos-stat-mes');
        const statHoy = document.getElementById('gastos-stat-hoy');
        const statCountHoy = document.getElementById('gastos-stat-count-hoy');
        const statTopCat = document.getElementById('gastos-stat-top-cat');
        const statTopMonto = document.getElementById('gastos-stat-top-monto');
        const lblFiltrado = document.getElementById('gastos-total-filtrado-txt');

        if (statMes) statMes.textContent = App.formatCurrency(totalMes);
        if (statHoy) statHoy.textContent = App.formatCurrency(totalHoy);
        if (statCountHoy) statCountHoy.textContent = countHoy;
        if (statTopCat) statTopCat.textContent = topCat;
        if (statTopMonto) statTopMonto.textContent = `${App.formatCurrency(topMonto)} acumulado`;
        if (lblFiltrado) lblFiltrado.textContent = `Total en vista: ${App.formatCurrency(totalMes)} (${this.gastos.length} egresos)`;
    },

    render() {
        const tbody = document.getElementById('tbody-gastos');
        const empty = document.getElementById('gastos-empty-state');
        if (!tbody) return;

        if (this.gastos.length === 0) {
            tbody.innerHTML = '';
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');

        tbody.innerHTML = this.gastos.map(g => {
            const fechaStr = App.formatDate(g.fecha);
            const montoStr = App.formatCurrency(g.monto);

            let catColor = "bg-slate-100 text-slate-700 border-slate-200";
            if (g.categoria === 'Renta') catColor = "bg-indigo-50 text-indigo-700 border-indigo-200";
            else if (g.categoria === 'Luz / Servicios') catColor = "bg-amber-50 text-amber-700 border-amber-200";
            else if (g.categoria === 'Sueldos') catColor = "bg-purple-50 text-purple-700 border-purple-200";
            else if (g.categoria === 'Refacciones') catColor = "bg-blue-50 text-blue-700 border-blue-200";
            else if (g.categoria === 'Publicidad') catColor = "bg-pink-50 text-pink-700 border-pink-200";
            else if (g.categoria === 'Comida / Viáticos') catColor = "bg-emerald-50 text-emerald-700 border-emerald-200";

            return `
                <tr class="hover:bg-slate-50/80 transition-colors">
                    <td class="p-3 text-slate-500 whitespace-nowrap font-medium">${fechaStr}</td>
                    <td class="p-3 font-bold text-slate-800">
                        ${App.escapeHtml(g.concepto)}
                        ${g.notas ? `<span class="block text-[10px] text-slate-400 font-normal italic">${App.escapeHtml(g.notas)}</span>` : ''}
                    </td>
                    <td class="p-3">
                        <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${catColor}">
                            ${App.escapeHtml(g.categoria)}
                        </span>
                    </td>
                    <td class="p-3">
                        <span class="text-[11px] font-semibold text-slate-600">${App.escapeHtml(g.metodo_pago || 'Efectivo')}</span>
                    </td>
                    <td class="p-3 font-black text-rose-600 whitespace-nowrap">
                        -${montoStr}
                    </td>
                    <td class="p-3 text-slate-500 text-[11px]">
                        ${App.escapeHtml(g.usuario || 'Admin')}
                    </td>
                    <td class="p-3 text-right">
                        <button type="button" onclick="Gastos.eliminar(${g.id})" class="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer" title="Eliminar gasto">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    async guardar() {
        const concepto = document.getElementById('gasto-concepto')?.value.trim();
        const categoria = document.getElementById('gasto-categoria')?.value || 'General';
        const monto = parseFloat(document.getElementById('gasto-monto')?.value) || 0;
        const metodo = document.getElementById('gasto-metodo-pago')?.value || 'Efectivo';
        const fecha = document.getElementById('gasto-fecha')?.value || null;
        const notas = document.getElementById('gasto-notas')?.value.trim() || null;

        if (!concepto || monto <= 0) {
            App.showToast("Ingresa un concepto válido y un monto mayor a cero", "warning");
            return;
        }

        try {
            const res = await fetch('/api/gastos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    concepto: concepto,
                    categoria: categoria,
                    monto: monto,
                    metodo_pago: metodo,
                    fecha: fecha,
                    notas: notas
                })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Error al registrar el gasto");
            }

            App.showToast("Gasto registrado correctamente", "success");
            this.cerrarModal();
            this.cargar();

            // Refrescar métricas del dashboard si Reportes está cargado
            if (typeof Reportes !== 'undefined' && Reportes.cargarDashboard) {
                Reportes.cargarDashboard();
            }
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    async eliminar(gastoId) {
        if (!confirm("¿Seguro que deseas eliminar este registro de gasto?")) return;

        try {
            const res = await fetch(`/api/gastos/${gastoId}`, {
                method: 'DELETE'
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Error al eliminar gasto");
            }

            App.showToast("Gasto eliminado", "info");
            this.cargar();

            if (typeof Reportes !== 'undefined' && Reportes.cargarDashboard) {
                Reportes.cargarDashboard();
            }
        } catch (e) {
            App.showToast(e.message, "error");
        }
    }
};
