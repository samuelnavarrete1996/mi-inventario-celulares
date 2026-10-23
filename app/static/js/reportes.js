// reportes.js - Módulo de Reportes y Métricas Separadas (Celulares vs Accesorios)

const Reportes = {
    ventas: [],
    graficoVentas: null,
    filtroTipo: 'todos',        // 'todos', 'celulares', 'accesorios'
    modoGrafico: 'ambos',       // 'ambos', 'celulares', 'accesorios'
    vistaDashboard: 'todos',    // 'todos', 'celulares', 'accesorios'
    datosDashboard: null,

    init() {
        this.setupFiltros();
    },

    setupFiltros() {
        const btnFiltrar = document.getElementById('btn-filtrar-reportes');
        const btnLimpiar = document.getElementById('btn-limpiar-filtros-reportes');

        if (btnFiltrar) {
            btnFiltrar.addEventListener('click', () => {
                const fInicio = document.getElementById('reporte-fecha-inicio').value;
                const fFin = document.getElementById('reporte-fecha-fin').value;
                this.cargarHistorialVentas(fInicio, fFin);
            });
        }

        if (btnLimpiar) {
            btnLimpiar.addEventListener('click', () => {
                document.getElementById('reporte-fecha-inicio').value = '';
                document.getElementById('reporte-fecha-fin').value = '';
                this.cargarHistorialVentas();
            });
        }
    },

    cambiarVistaDashboard(vista) {
        this.vistaDashboard = vista;

        const btnTodos = document.getElementById('btn-vista-dash-todos');
        const btnCel = document.getElementById('btn-vista-dash-celulares');
        const btnAcc = document.getElementById('btn-vista-dash-accesorios');

        const panelCel = document.getElementById('panel-dash-celulares');
        const panelAcc = document.getElementById('panel-dash-accesorios');
        const panelCons = document.getElementById('panel-dash-consolidado');

        // Reset button classes
        [btnTodos, btnCel, btnAcc].forEach(btn => {
            if (btn) {
                btn.className = "px-3.5 py-1.5 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5";
            }
        });

        if (vista === 'celulares') {
            if (btnCel) btnCel.className = "px-3.5 py-1.5 text-xs font-bold rounded-lg bg-white text-blue-700 shadow-2xs transition-all flex items-center gap-1.5";
            if (panelCel) panelCel.classList.remove('hidden');
            if (panelAcc) panelAcc.classList.add('hidden');
            if (panelCons) panelCons.classList.remove('hidden');
        } else if (vista === 'accesorios') {
            if (btnAcc) btnAcc.className = "px-3.5 py-1.5 text-xs font-bold rounded-lg bg-white text-purple-700 shadow-2xs transition-all flex items-center gap-1.5";
            if (panelCel) panelCel.classList.add('hidden');
            if (panelAcc) panelAcc.classList.remove('hidden');
            if (panelCons) panelCons.classList.remove('hidden');
        } else {
            // Todos
            if (btnTodos) btnTodos.className = "px-3.5 py-1.5 text-xs font-bold rounded-lg bg-white text-blue-700 shadow-2xs transition-all flex items-center gap-1.5";
            if (panelCel) panelCel.classList.remove('hidden');
            if (panelAcc) panelAcc.classList.remove('hidden');
            if (panelCons) panelCons.classList.remove('hidden');
        }
    },

    async cargarDashboard() {
        try {
            const res = await fetch('/api/reportes/dashboard');
            if (!res.ok) throw new Error("Error al obtener métricas del dashboard.");

            const data = await res.json();
            this.datosDashboard = data;

            // 1. Métricas Consolidadas / Retrocompatibilidad
            if (document.getElementById('dash-mes-titulo')) {
                document.getElementById('dash-mes-titulo').textContent = data.mes_actual_nombre || 'Mes Actual';
            }
            if (document.getElementById('dash-ganancias-mes')) {
                document.getElementById('dash-ganancias-mes').textContent = App.formatCurrency(data.total_ganancias_mes);
            }
            if (document.getElementById('dash-ventas-mes')) {
                document.getElementById('dash-ventas-mes').textContent = App.formatCurrency(data.total_ventas_mes);
            }
            if (document.getElementById('dash-unidades-mes')) {
                document.getElementById('dash-unidades-mes').textContent = `${data.equipos_vendidos_mes || 0} equipos`;
            }
            if (document.getElementById('dash-margen-pct')) {
                document.getElementById('dash-margen-pct').textContent = `${data.margen_promedio_mes || 0}%`;
            }
            if (document.getElementById('dash-stock-disponible')) {
                document.getElementById('dash-stock-disponible').textContent = `${data.equipos_disponibles || 0}`;
            }
            if (document.getElementById('dash-capital-inventario')) {
                document.getElementById('dash-capital-inventario').textContent = App.formatCurrency(data.capital_inventario_total || data.capital_inventario);
            }
            if (document.getElementById('dash-valor-venta-inventario')) {
                const totalValor = (data.valor_venta_inventario || 0) + (data.accesorios_valor_venta_inventario || 0);
                document.getElementById('dash-valor-venta-inventario').textContent = App.formatCurrency(totalValor);
            }

            // 2. 📱 Métricas Separadas de Celulares
            if (document.getElementById('dash-cel-ganancias')) {
                document.getElementById('dash-cel-ganancias').textContent = App.formatCurrency(data.celulares_ganancias_mes);
            }
            if (document.getElementById('dash-cel-margen-pct')) {
                document.getElementById('dash-cel-margen-pct').textContent = `${data.celulares_margen_pct || 0}%`;
            }
            if (document.getElementById('dash-cel-ventas')) {
                document.getElementById('dash-cel-ventas').textContent = App.formatCurrency(data.celulares_ventas_mes);
            }
            if (document.getElementById('dash-cel-unidades')) {
                document.getElementById('dash-cel-unidades').textContent = `${data.celulares_unidades_mes || 0} equipos`;
            }
            if (document.getElementById('dash-cel-capital')) {
                document.getElementById('dash-cel-capital').textContent = App.formatCurrency(data.celulares_capital_inventario);
            }
            if (document.getElementById('dash-cel-stock')) {
                document.getElementById('dash-cel-stock').textContent = `${data.celulares_stock_disponible || 0}`;
            }
            if (document.getElementById('dash-cel-valor')) {
                document.getElementById('dash-cel-valor').textContent = App.formatCurrency(data.celulares_valor_venta_inventario);
            }

            // 3. 🎧 Métricas Separadas de Accesorios
            if (document.getElementById('dash-acc-ganancias')) {
                document.getElementById('dash-acc-ganancias').textContent = App.formatCurrency(data.accesorios_ganancias_mes);
            }
            if (document.getElementById('dash-acc-margen-pct')) {
                document.getElementById('dash-acc-margen-pct').textContent = `${data.accesorios_margen_pct || 0}%`;
            }
            if (document.getElementById('dash-acc-ventas')) {
                document.getElementById('dash-acc-ventas').textContent = App.formatCurrency(data.accesorios_ventas_mes);
            }
            if (document.getElementById('dash-acc-unidades')) {
                document.getElementById('dash-acc-unidades').textContent = `${data.accesorios_unidades_mes || 0} piezas`;
            }
            if (document.getElementById('dash-acc-capital')) {
                document.getElementById('dash-acc-capital').textContent = App.formatCurrency(data.accesorios_capital_inventario);
            }
            if (document.getElementById('dash-acc-stock')) {
                document.getElementById('dash-acc-stock').textContent = `${data.accesorios_stock_disponible || 0}`;
            }
            if (document.getElementById('dash-acc-valor')) {
                document.getElementById('dash-acc-valor').textContent = App.formatCurrency(data.accesorios_valor_venta_inventario);
            }

            // 4. Renderizar Gráfico
            this.renderGrafico(data.ventas_por_dia || []);

        } catch (err) {
            console.error("Error cargando dashboard:", err);
            App.showToast("Error al cargar métricas del mes", "error");
        }
    },

    cambiarModoGrafico(modo) {
        this.modoGrafico = modo;

        const btnAmbos = document.getElementById('btn-chart-ambos');
        const btnCel = document.getElementById('btn-chart-celulares');
        const btnAcc = document.getElementById('btn-chart-accesorios');

        [btnAmbos, btnCel, btnAcc].forEach(btn => {
            if (btn) {
                btn.className = "px-3 py-1 font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all";
            }
        });

        if (modo === 'celulares') {
            if (btnCel) btnCel.className = "px-3 py-1 font-bold rounded-lg bg-white text-blue-700 shadow-2xs transition-all";
        } else if (modo === 'accesorios') {
            if (btnAcc) btnAcc.className = "px-3 py-1 font-bold rounded-lg bg-white text-purple-700 shadow-2xs transition-all";
        } else {
            if (btnAmbos) btnAmbos.className = "px-3 py-1 font-bold rounded-lg bg-white text-slate-800 shadow-2xs transition-all";
        }

        if (this.datosDashboard && this.datosDashboard.ventas_por_dia) {
            this.renderGrafico(this.datosDashboard.ventas_por_dia);
        }
    },

    renderGrafico(datosDias) {
        const canvas = document.getElementById('chart-ventas-dias');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        if (this.graficoVentas) {
            this.graficoVentas.destroy();
        }

        const labels = datosDias.map(d => {
            const partes = d.dia.split('-');
            return `${partes[2]}/${partes[1]}`;
        });

        let datasets = [];

        if (this.modoGrafico === 'celulares') {
            // Solo celulares
            datasets = [
                {
                    label: 'Ganancia Celulares ($)',
                    data: datosDias.map(d => d.ganancias_celulares || 0),
                    backgroundColor: 'rgba(37, 99, 235, 0.85)',
                    borderColor: 'rgb(37, 99, 235)',
                    borderRadius: 6,
                    borderWidth: 1,
                    order: 2
                },
                {
                    label: 'Ventas Celulares ($)',
                    data: datosDias.map(d => d.ventas_celulares || 0),
                    type: 'line',
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.3,
                    borderWidth: 2,
                    fill: true,
                    order: 1
                }
            ];
        } else if (this.modoGrafico === 'accesorios') {
            // Solo accesorios
            datasets = [
                {
                    label: 'Ganancia Accesorios ($)',
                    data: datosDias.map(d => d.ganancias_accesorios || 0),
                    backgroundColor: 'rgba(168, 85, 247, 0.85)',
                    borderColor: 'rgb(168, 85, 247)',
                    borderRadius: 6,
                    borderWidth: 1,
                    order: 2
                },
                {
                    label: 'Ventas Accesorios ($)',
                    data: datosDias.map(d => d.ventas_accesorios || 0),
                    type: 'line',
                    borderColor: 'rgb(217, 70, 239)',
                    backgroundColor: 'rgba(217, 70, 239, 0.1)',
                    tension: 0.3,
                    borderWidth: 2,
                    fill: true,
                    order: 1
                }
            ];
        } else {
            // Ambos / Comparativa
            datasets = [
                {
                    label: '📱 Ganancia Celulares ($)',
                    data: datosDias.map(d => d.ganancias_celulares || 0),
                    backgroundColor: 'rgba(37, 99, 235, 0.85)',
                    borderColor: 'rgb(37, 99, 235)',
                    borderRadius: 5,
                    borderWidth: 1,
                    order: 3
                },
                {
                    label: '🎧 Ganancia Accesorios ($)',
                    data: datosDias.map(d => d.ganancias_accesorios || 0),
                    backgroundColor: 'rgba(168, 85, 247, 0.85)',
                    borderColor: 'rgb(168, 85, 247)',
                    borderRadius: 5,
                    borderWidth: 1,
                    order: 2
                },
                {
                    label: 'Total Facturado ($)',
                    data: datosDias.map(d => d.ventas || 0),
                    type: 'line',
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    tension: 0.3,
                    borderWidth: 2.5,
                    fill: true,
                    order: 1
                }
            ];
        }

        this.graficoVentas = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels.length > 0 ? labels : ['Sin datos recientes'],
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: { family: 'Inter', size: 12, weight: 600 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ` ${context.dataset.label}: ${App.formatCurrency(context.raw)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString('es-MX');
                            }
                        },
                        grid: {
                            color: '#f1f5f9'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    },

    getMetodoPagoBadge(metodo, v) {
        const m = (metodo || 'Efectivo').toLowerCase();
        if (m === 'efectivo') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                💵 Efectivo
            </span>`;
        } else if (m === 'transferencia') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
                📱 Transferencia
            </span>`;
        } else if (m === 'equipo garantía' || m === 'equipo garantia') {
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">
                🛡️ Equipo Garantía
            </span>`;
        } else if (m === 'combinado') {
            const parts = [
                `Ef: ${App.formatCurrency(v.monto_efectivo)}`,
                `Tr: ${App.formatCurrency(v.monto_transferencia)}`
            ];
            if (v.monto_garantia && v.monto_garantia > 0) {
                parts.push(`Gt: ${App.formatCurrency(v.monto_garantia)}`);
            }
            const detalle = parts.join(' | ');
            return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-900 border border-amber-200 cursor-help" title="${detalle}">
                🔀 Combinado
            </span>`;
        }
        return `<span class="text-xs text-slate-600">${App.escapeHtml(metodo)}</span>`;
    },

    filtrarPorTipoVenta(tipo) {
        this.filtroTipo = tipo;

        const btnTodos = document.getElementById('btn-filtro-tipo-todos');
        const btnCel = document.getElementById('btn-filtro-tipo-celulares');
        const btnAcc = document.getElementById('btn-filtro-tipo-accesorios');
        const btnRep = document.getElementById('btn-filtro-tipo-reparaciones');

        [btnTodos, btnCel, btnAcc, btnRep].forEach(btn => {
            if (btn) {
                btn.className = "btn-tipo-venta px-3 py-1 font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all";
            }
        });

        if (tipo === 'celulares') {
            if (btnCel) btnCel.className = "btn-tipo-venta px-3 py-1 font-bold rounded-lg bg-white text-blue-700 shadow-2xs transition-all";
        } else if (tipo === 'accesorios') {
            if (btnAcc) btnAcc.className = "btn-tipo-venta px-3 py-1 font-bold rounded-lg bg-white text-purple-700 shadow-2xs transition-all";
        } else if (tipo === 'reparaciones') {
            if (btnRep) btnRep.className = "btn-tipo-venta px-3 py-1 font-bold rounded-lg bg-white text-indigo-700 shadow-2xs transition-all";
        } else {
            if (btnTodos) btnTodos.className = "btn-tipo-venta px-3 py-1 font-bold rounded-lg bg-white text-slate-800 shadow-2xs transition-all";
        }

        this.renderHistorialVentas();
    },

    async cargarHistorialVentas(fechaInicio = null, fechaFin = null) {
        const tbody = document.getElementById('tbody-historial-ventas');
        const emptyState = document.getElementById('ventas-empty-state');
        if (!tbody) return;

        try {
            let url = '/api/reportes/ventas?limit=300';
            if (fechaInicio) url += `&fecha_inicio=${encodeURIComponent(fechaInicio)}`;
            if (fechaFin) url += `&fecha_fin=${encodeURIComponent(fechaFin)}`;

            const res = await fetch(url);
            if (!res.ok) throw new Error("Error al obtener historial de ventas.");

            this.ventas = await res.json();

            // Actualizar contadores en botones
            const totalCount = this.ventas.length;
            const celCount = this.ventas.filter(v => (v.total_equipos || 0) > 0 && v.tipo_venta !== 'reparacion').length;
            const accCount = this.ventas.filter(v => (v.total_accesorios || 0) > 0 && v.tipo_venta !== 'reparacion').length;
            const repCount = this.ventas.filter(v => v.tipo_venta === 'reparacion' || v.reparacion_id).length;

            if (document.getElementById('count-ventas-todos')) {
                document.getElementById('count-ventas-todos').textContent = totalCount;
            }
            if (document.getElementById('count-ventas-celulares')) {
                document.getElementById('count-ventas-celulares').textContent = celCount;
            }
            if (document.getElementById('count-ventas-accesorios')) {
                document.getElementById('count-ventas-accesorios').textContent = accCount;
            }
            if (document.getElementById('count-ventas-reparaciones')) {
                document.getElementById('count-ventas-reparaciones').textContent = repCount;
            }

            this.renderHistorialVentas();

        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-rose-500">Error: ${App.escapeHtml(err.message)}</td></tr>`;
        }
    },

    renderHistorialVentas() {
        const tbody = document.getElementById('tbody-historial-ventas');
        const emptyState = document.getElementById('ventas-empty-state');
        if (!tbody) return;

        let filtradas = this.ventas;
        if (this.filtroTipo === 'celulares') {
            filtradas = this.ventas.filter(v => (v.total_equipos || 0) > 0 && v.tipo_venta !== 'reparacion');
        } else if (this.filtroTipo === 'accesorios') {
            filtradas = this.ventas.filter(v => (v.total_accesorios || 0) > 0 && v.tipo_venta !== 'reparacion');
        } else if (this.filtroTipo === 'reparaciones') {
            filtradas = this.ventas.filter(v => v.tipo_venta === 'reparacion' || v.reparacion_id);
        }

        // Totales calculados de las ventas filtradas
        let totVentas = 0;
        let totGanCel = 0;
        let totGanAcc = 0;
        let totGanRep = 0;
        let totGanTotal = 0;

        filtradas.forEach(v => {
            totVentas += (v.precio_final || 0);
            totGanCel += (v.ganancia_celulares || 0);
            totGanAcc += (v.ganancia_accesorios || 0);
            if (v.tipo_venta === 'reparacion' || v.reparacion_id) {
                totGanRep += (v.margen_ganancia || 0);
            }
            totGanTotal += (v.margen_ganancia || 0);
        });

        if (document.getElementById('lbl-filtro-total-ventas')) {
            document.getElementById('lbl-filtro-total-ventas').textContent = App.formatCurrency(totVentas);
        }
        if (document.getElementById('lbl-filtro-ganancia-cel')) {
            document.getElementById('lbl-filtro-ganancia-cel').textContent = `+${App.formatCurrency(totGanCel)}`;
        }
        if (document.getElementById('lbl-filtro-ganancia-acc')) {
            document.getElementById('lbl-filtro-ganancia-acc').textContent = `+${App.formatCurrency(totGanAcc)}`;
        }
        if (document.getElementById('lbl-filtro-ganancia-rep')) {
            document.getElementById('lbl-filtro-ganancia-rep').textContent = `+${App.formatCurrency(totGanRep)}`;
        }
        if (document.getElementById('lbl-filtro-ganancia-total')) {
            document.getElementById('lbl-filtro-ganancia-total').textContent = `+${App.formatCurrency(totGanTotal)}`;
        }

        if (filtradas.length === 0) {
            tbody.innerHTML = '';
            if (emptyState) emptyState.classList.remove('hidden');
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');

        tbody.innerHTML = filtradas.map(v => {
            const totalCosto = v.items && v.items.length > 0 
                ? v.items.reduce((acc, it) => acc + (it.costo_compra || 0), 0)
                : (v.costo_compra || 0);

            const margen = v.margen_ganancia || 0;
            const pct = totalCosto > 0 ? ((margen / totalCosto) * 100).toFixed(1) : 0;
            const totalEquipos = v.total_equipos || 0;
            const totalAccesorios = v.total_accesorios || 0;

            const primerItemCel = (v.items || []).find(it => it.tipo_item === 'equipo' || it.equipo_id);
            const primerImei = primerItemCel ? primerItemCel.imei : (v.imei || '');

            // Badge de Categoría
            let tipoBadge = '';
            if (v.tipo_venta === 'reparacion' || v.reparacion_id) {
                tipoBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-indigo-100 text-indigo-900 border border-indigo-200">
                    🔧 Taller / Reparación
                </span>`;
            } else if (v.tipo_venta === 'mixta') {
                tipoBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-200">
                    🔀 Mixta (📱${totalEquipos} + 🎧${totalAccesorios})
                </span>`;
            } else if (v.tipo_venta === 'accesorios' || (totalAccesorios > 0 && totalEquipos === 0)) {
                tipoBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-100 text-purple-900 border border-purple-200">
                    🎧 Accesorio (${totalAccesorios} pz${totalAccesorios > 1 ? 's' : ''})
                </span>`;
            } else {
                tipoBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-100 text-blue-900 border border-blue-200">
                    📱 Celular (${totalEquipos} eq)
                </span>`;
            }

            // Desglose de Ganancia si es Mixta
            let margenHtml = '';
            if (v.tipo_venta === 'mixta') {
                margenHtml = `
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                        +${App.formatCurrency(v.margen_ganancia)}
                    </span>
                    <div class="text-[10px] text-slate-500 font-medium mt-1 space-x-1">
                        <span class="text-blue-700">📱 +${App.formatCurrency(v.ganancia_celulares)}</span>
                        <span>•</span>
                        <span class="text-purple-700">🎧 +${App.formatCurrency(v.ganancia_accesorios)}</span>
                    </div>
                `;
            } else {
                margenHtml = `
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                        +${App.formatCurrency(v.margen_ganancia)}
                    </span>
                    <span class="text-[11px] text-emerald-600 font-medium block mt-0.5">(${pct}%)</span>
                `;
            }

            return `
            <tr class="hover:bg-slate-50 border-b border-slate-100 transition-colors">
                <td class="py-3 px-4 font-mono text-xs font-bold text-slate-700">
                    ${v.folio ? App.escapeHtml(v.folio) : '#' + String(v.id).padStart(5, '0')}
                </td>
                <td class="py-3 px-4 text-xs text-slate-600 whitespace-nowrap">
                    ${App.formatDate(v.fecha_venta)}
                </td>
                <td class="py-3 px-4">
                    <div class="font-medium text-slate-800 text-sm">${App.escapeHtml(v.cliente_nombre)}</div>
                    <div class="text-xs text-slate-400 font-mono">${App.escapeHtml(v.cliente_telefono)}</div>
                </td>
                <td class="py-3 px-4">
                    <div class="mb-1">${tipoBadge}</div>
                    <div class="text-xs text-slate-700 font-medium truncate max-w-xs" title="${App.escapeHtml(v.resumen_modelos)}">
                        ${App.escapeHtml(v.resumen_modelos || v.modelo || 'Artículos')}
                    </div>
                </td>
                <td class="py-3 px-4">
                    ${this.getMetodoPagoBadge(v.metodo_pago, v)}
                </td>
                <td class="py-3 px-4 font-bold text-slate-900 text-sm whitespace-nowrap">
                    ${App.formatCurrency(v.precio_final)}
                </td>
                <td class="py-3 px-4 whitespace-nowrap">
                    ${margenHtml}
                </td>
                <td class="py-3 px-4 text-right">
                    <div class="inline-flex items-center gap-1.5">
                        ${(v.tipo_venta === 'reparacion' || v.reparacion_id) ? `
                        <button onclick="Reparaciones.abrirBoleta(${v.reparacion_id || (v.id > 900000 ? v.id - 900000 : v.id)})" class="inline-flex items-center px-2.5 py-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg shadow-2xs transition-all gap-1" title="Ver / Imprimir Boleta de Taller">
                            <svg class="w-3.5 h-3.5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                            <span>Boleta Taller</span>
                        </button>` : `
                        <button onclick="Reportes.reimprimirRecibo(${v.id})" class="inline-flex items-center px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg shadow-2xs transition-all gap-1" title="Ver / Imprimir Recibo">
                            <svg class="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                            <span>Recibo</span>
                        </button>`}
                        ${primerImei ? `
                        <button onclick="Garantias.abrirModal('${App.escapeJsArg(primerImei)}')" class="inline-flex items-center px-2.5 py-1.5 text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg shadow-2xs transition-all gap-1" title="Regresar celular por garantía">
                            <span>🛡️</span>
                            <span>Garantía</span>
                        </button>` : ''}
                    </div>
                </td>
            </tr>
            `;
        }).join('');
    },

    async reimprimirRecibo(ventaId) {
        try {
            const res = await fetch(`/api/pos/recibo/${ventaId}`);
            if (res.ok) {
                const venta = await res.json();
                POS.mostrarRecibo(venta);
            } else {
                App.showToast("No se encontró el recibo.", "error");
            }
        } catch (e) {
            App.showToast("Error al obtener recibo: " + e.message, "error");
        }
    }
};
