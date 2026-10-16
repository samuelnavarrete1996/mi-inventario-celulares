// reportes.js - Módulo de Reportes y Métricas

const Reportes = {
    ventas: [],
    graficoVentas: null,

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

    async cargarDashboard() {
        try {
            const res = await fetch('/api/reportes/dashboard');
            if (!res.ok) throw new Error("Error al obtener métricas del dashboard.");

            const data = await res.json();

            // Actualizar tarjetas de KPI
            document.getElementById('dash-mes-titulo').textContent = data.mes_actual_nombre;
            document.getElementById('dash-ganancias-mes').textContent = App.formatCurrency(data.total_ganancias_mes);
            document.getElementById('dash-ventas-mes').textContent = App.formatCurrency(data.total_ventas_mes);
            document.getElementById('dash-unidades-mes').textContent = `${data.equipos_vendidos_mes} equipos`;
            document.getElementById('dash-margen-pct').textContent = `${data.margen_promedio_mes}%`;

            document.getElementById('dash-stock-disponible').textContent = `${data.equipos_disponibles} equipos`;
            document.getElementById('dash-capital-inventario').textContent = App.formatCurrency(data.capital_inventario);
            document.getElementById('dash-valor-venta-inventario').textContent = App.formatCurrency(data.valor_venta_inventario);

            // Renderizar gráfico
            this.renderGrafico(data.ventas_por_dia || []);

        } catch (err) {
            console.error("Error cargando dashboard:", err);
            App.showToast("Error al cargar métricas del mes", "error");
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
        const ganancias = datosDias.map(d => d.ganancias);
        const ventas = datosDias.map(d => d.ventas);

        this.graficoVentas = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels.length > 0 ? labels : ['Sin datos recientes'],
                datasets: [
                    {
                        label: 'Ganancia Neta ($)',
                        data: ganancias.length > 0 ? ganancias : [0],
                        backgroundColor: 'rgba(16, 185, 129, 0.85)',
                        borderColor: 'rgb(16, 185, 129)',
                        borderRadius: 6,
                        borderWidth: 1,
                        order: 2
                    },
                    {
                        label: 'Venta Total ($)',
                        data: ventas.length > 0 ? ventas : [0],
                        type: 'line',
                        borderColor: 'rgb(37, 99, 235)',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        tension: 0.3,
                        borderWidth: 2.5,
                        fill: true,
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: { family: 'Inter', size: 12, weight: 500 }
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
        return `<span class="text-xs text-slate-600">${metodo}</span>`;
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

            if (this.ventas.length === 0) {
                tbody.innerHTML = '';
                if (emptyState) emptyState.classList.remove('hidden');
                return;
            }

            if (emptyState) emptyState.classList.add('hidden');

            tbody.innerHTML = this.ventas.map(v => {
                const totalCosto = v.items && v.items.length > 0 
                    ? v.items.reduce((acc, it) => acc + (it.costo_compra || 0), 0)
                    : (v.costo_compra || 0);

                const margen = v.margen_ganancia || 0;
                const pct = totalCosto > 0 ? ((margen / totalCosto) * 100).toFixed(1) : 0;
                const totalEquipos = v.total_equipos || (v.items ? v.items.length : 1);
                const primerImei = (v.items && v.items.length > 0) ? v.items[0].imei : (v.imei || '');

                return `
                <tr class="hover:bg-slate-50 border-b border-slate-100 transition-colors">
                    <td class="py-3 px-4 font-mono text-xs font-bold text-slate-700">
                        #${String(v.id).padStart(5, '0')}
                    </td>
                    <td class="py-3 px-4 text-xs text-slate-600 whitespace-nowrap">
                        ${App.formatDate(v.fecha_venta)}
                    </td>
                    <td class="py-3 px-4">
                        <div class="font-medium text-slate-800 text-sm">${v.cliente_nombre}</div>
                        <div class="text-xs text-slate-400 font-mono">${v.cliente_telefono}</div>
                    </td>
                    <td class="py-3 px-4">
                        <div class="flex items-center gap-1.5">
                            <span class="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 text-[11px] font-bold">
                                ${totalEquipos} ${totalEquipos === 1 ? 'teléfono' : 'teléfonos'}
                            </span>
                        </div>
                        <div class="text-xs text-slate-600 font-medium mt-1 truncate max-w-xs" title="${v.resumen_modelos}">
                            ${v.resumen_modelos || v.modelo}
                        </div>
                    </td>
                    <td class="py-3 px-4">
                        ${this.getMetodoPagoBadge(v.metodo_pago, v)}
                    </td>
                    <td class="py-3 px-4 font-bold text-slate-900 text-sm whitespace-nowrap">
                        ${App.formatCurrency(v.precio_final)}
                    </td>
                    <td class="py-3 px-4 whitespace-nowrap">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                            +${App.formatCurrency(v.margen_ganancia)}
                        </span>
                        <span class="text-[11px] text-emerald-600 font-medium block mt-0.5">(${pct}%)</span>
                    </td>
                    <td class="py-3 px-4 text-right">
                        <div class="inline-flex items-center gap-1.5">
                            <button onclick="Reportes.reimprimirRecibo(${v.id})" class="inline-flex items-center px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg shadow-2xs transition-all gap-1" title="Ver / Imprimir Nota de Venta">
                                <svg class="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                                Recibo
                            </button>
                            <button onclick="Garantias.abrirModal('${primerImei}')" class="inline-flex items-center px-2.5 py-1.5 text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg shadow-2xs transition-all gap-1" title="Regresar celular por garantía / reclamo">
                                <span>🛡️</span>
                                <span>Garantía</span>
                            </button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');

        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-rose-500">Error: ${err.message}</td></tr>`;
        }
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
