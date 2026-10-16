// caja.js - Módulo de Corte de Caja Diario (Arqueo / Reporte Z)
const Caja = {
    datosCorte: null,

    init() {},

    async abrirModalCorte() {
        try {
            const res = await fetch('/api/caja/resumen-actual');
            if (!res.ok) throw new Error("Error al obtener balance de caja");
            this.datosCorte = await res.json();
            this.renderizarResumen();
            document.getElementById('modal-corte-caja').classList.remove('hidden');
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    cerrarModal() {
        document.getElementById('modal-corte-caja').classList.add('hidden');
    },

    renderizarResumen() {
        const d = this.datosCorte;
        if (!d) return;

        document.getElementById('corte-fecha-hora').textContent = App.formatDate(d.fecha_corte);
        document.getElementById('corte-periodo-inicio').textContent = App.formatDate(d.fecha_inicio_periodo);
        document.getElementById('corte-total-ventas').textContent = App.formatCurrency(d.total_ventas);
        document.getElementById('corte-total-efectivo-sistema').textContent = App.formatCurrency(d.total_efectivo);
        document.getElementById('corte-total-transferencia').textContent = App.formatCurrency(d.total_transferencia);
        document.getElementById('corte-total-garantia').textContent = App.formatCurrency(d.total_garantia);
        document.getElementById('corte-total-operaciones').textContent = `${d.cantidad_ventas} ventas`;

        const inputDeclarado = document.getElementById('corte-efectivo-declarado');
        if (inputDeclarado) {
            inputDeclarado.value = '';
        }
        this.calcularDiferencia();
    },

    calcularDiferencia() {
        const inputDeclarado = document.getElementById('corte-efectivo-declarado');
        const badgeDiferencia = document.getElementById('corte-badge-diferencia');
        const txtDiferencia = document.getElementById('corte-txt-diferencia');
        if (!this.datosCorte || !inputDeclarado) return;

        const declarado = parseFloat(inputDeclarado.value) || 0;
        const sistema = this.datosCorte.total_efectivo;
        const diff = declarado - sistema;

        if (inputDeclarado.value === '') {
            badgeDiferencia.className = "hidden";
            return;
        }

        badgeDiferencia.classList.remove('hidden');
        if (Math.abs(diff) < 0.05) {
            badgeDiferencia.className = "p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center justify-between";
            txtDiferencia.textContent = "✅ Caja Cuadrada ($0.00)";
        } else if (diff > 0) {
            badgeDiferencia.className = "p-3 rounded-xl bg-blue-50 border border-blue-200 text-blue-800 text-xs font-bold flex items-center justify-between";
            txtDiferencia.textContent = `🟢 Sobrante en caja: +${App.formatCurrency(diff)}`;
        } else {
            badgeDiferencia.className = "p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-bold flex items-center justify-between animate-pulse";
            txtDiferencia.textContent = `🔴 Faltante en caja: -${App.formatCurrency(Math.abs(diff))}`;
        }
    },

    async confirmarCorte() {
        const inputDeclarado = document.getElementById('corte-efectivo-declarado');
        const notas = document.getElementById('corte-notas')?.value || '';
        const declarado = parseFloat(inputDeclarado?.value);

        if (isNaN(declarado) || declarado < 0) {
            App.showToast("Ingresa el monto de efectivo físico en caja", "error");
            return;
        }

        if (!confirm(`¿Confirmas el cierre de caja con ${App.formatCurrency(declarado)} en efectivo?`)) return;

        try {
            const res = await fetch('/api/caja/corte', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    efectivo_declarado: declarado,
                    notas: notas
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al registrar el corte");
            }

            const corteGuardado = await res.json();
            App.showToast(`¡Corte de caja guardado con éxito! Folio #${corteGuardado.id}`, "success");
            this.cerrarModal();
            App.updateHeaderStats();
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    async verHistorial() {
        const modalHistorial = document.getElementById('modal-historial-cortes');
        const container = document.getElementById('tbody-historial-cortes');
        if (!container) return;

        try {
            const res = await fetch('/api/caja/historial');
            if (res.ok) {
                const cortes = await res.json();
                if (cortes.length === 0) {
                    container.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400">No hay cortes previos registrados</td></tr>`;
                } else {
                    container.innerHTML = cortes.map(c => `
                        <tr class="border-b border-slate-100 text-xs">
                            <td class="py-2.5 px-3 font-mono font-bold text-slate-800">#${c.id}</td>
                            <td class="py-2.5 px-3 text-slate-600">${App.formatDate(c.fecha_corte)}</td>
                            <td class="py-2.5 px-3 font-bold text-slate-900">${App.formatCurrency(c.total_ventas)}</td>
                            <td class="py-2.5 px-3 text-slate-700">${App.formatCurrency(c.total_efectivo)}</td>
                            <td class="py-2.5 px-3 text-slate-700">${App.formatCurrency(c.efectivo_declarado)}</td>
                            <td class="py-2.5 px-3 font-bold ${c.diferencia >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                                ${c.diferencia >= 0 ? '+' : ''}${App.formatCurrency(c.diferencia)}
                            </td>
                            <td class="py-2.5 px-3 text-slate-500 italic">${c.notas || '--'}</td>
                        </tr>
                    `).join('');
                }
                modalHistorial.classList.remove('hidden');
            }
        } catch (e) {
            App.showToast("Error al cargar historial de cortes", "error");
        }
    },

    cerrarHistorial() {
        document.getElementById('modal-historial-cortes').classList.add('hidden');
    }
};
