// reparaciones.js - Módulo de Gestión de Taller Técnico y Órdenes de Servicio

const Reparaciones = {
    estadoFiltro: 'Todos',
    reparaciones: [],
    reparacionActual: null,

    init() {
        this.setupListeners();
        this.cargar();
    },

    setupListeners() {
        const searchInput = document.getElementById('search-reparaciones');
        if (searchInput) {
            let timer;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(timer);
                timer = setTimeout(() => this.cargar(), 250);
            });
        }

        const inputPrecio = document.getElementById('rep-input-precio');
        const inputAnticipo = document.getElementById('rep-input-anticipo');
        if (inputPrecio && inputAnticipo) {
            const recalcular = () => {
                const precio = parseFloat(inputPrecio.value) || 0;
                const anticipo = parseFloat(inputAnticipo.value) || 0;
                const saldo = Math.max(0, precio - anticipo);
                const saldoEl = document.getElementById('rep-txt-saldo-calculado');
                if (saldoEl) saldoEl.textContent = App.formatCurrency(saldo);
            };
            inputPrecio.addEventListener('input', recalcular);
            inputAnticipo.addEventListener('input', recalcular);
        }
    },

    async cargar() {
        const searchInput = document.getElementById('search-reparaciones');
        const query = searchInput ? searchInput.value.trim() : '';

        try {
            let url = `/api/reparaciones?search=${encodeURIComponent(query)}`;
            if (this.estadoFiltro && this.estadoFiltro !== 'Todos') {
                url += `&estado=${encodeURIComponent(this.estadoFiltro)}`;
            }

            const res = await fetch(url);
            if (!res.ok) throw new Error('Error al cargar reparaciones');
            this.reparaciones = await res.json();
            this.render();
            this.actualizarContadores();
        } catch (e) {
            console.error(e);
        }
    },

    filtrarEstado(estado, btn) {
        this.estadoFiltro = estado;
        document.querySelectorAll('.rep-filter-pill').forEach(b => {
            b.className = "rep-filter-pill px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all";
        });
        if (btn) {
            btn.className = "rep-filter-pill px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white transition-all";
        }
        this.cargar();
    },

    actualizarContadores() {
        const total = this.reparaciones.length;
        const pendientes = this.reparaciones.filter(r => r.estado !== 'Entregado' && r.estado !== 'Cancelado').length;
        const listos = this.reparaciones.filter(r => r.estado === 'Listo para Entrega').length;

        const statTotal = document.getElementById('stat-rep-total');
        const statPendientes = document.getElementById('stat-rep-taller');
        const statListos = document.getElementById('stat-rep-listos');

        if (statTotal) statTotal.textContent = total;
        if (statPendientes) statPendientes.textContent = pendientes;
        if (statListos) statListos.textContent = listos;
    },

    render() {
        const tbody = document.getElementById('tbody-reparaciones');
        const empty = document.getElementById('reparaciones-empty-state');
        if (!tbody) return;

        if (this.reparaciones.length === 0) {
            tbody.innerHTML = '';
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');

        tbody.innerHTML = this.reparaciones.map(r => {
            let badgeEstado = '';
            let bgRow = '';

            switch (r.estado) {
                case 'Recibido':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">📥 Recibido</span>';
                    break;
                case 'En Revision':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">🔍 En Revisión</span>';
                    break;
                case 'Esperando Refaccion':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">⏳ Esperando Pieza</span>';
                    break;
                case 'Listo para Entrega':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 animate-pulse">✨ ¡Listo!</span>';
                    bgRow = 'bg-emerald-50/20';
                    break;
                case 'Entregado':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">✓ Entregado</span>';
                    break;
                case 'Cancelado':
                    badgeEstado = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-600">✕ Cancelado</span>';
                    break;
            }

            return `
            <tr class="border-b border-slate-100 hover:bg-slate-50/80 transition-colors ${bgRow}">
                <td class="py-3 px-4 font-mono font-bold text-xs text-blue-700 whitespace-nowrap">
                    ${App.escapeHtml(r.folio)}
                </td>
                <td class="py-3 px-4">
                    <div class="font-bold text-slate-900 text-xs">${App.escapeHtml(r.dispositivo_modelo)}</div>
                    <div class="text-[11px] text-slate-500 truncate max-w-xs">${App.escapeHtml(r.falla_reportada)}</div>
                    ${r.codigo_patron ? `<div class="text-[10px] text-amber-700 font-mono">Clave: ${App.escapeHtml(r.codigo_patron)}</div>` : ''}
                </td>
                <td class="py-3 px-4 whitespace-nowrap">
                    <div class="font-semibold text-slate-800 text-xs">${App.escapeHtml(r.cliente_nombre)}</div>
                    <div class="text-[11px] text-slate-400 font-mono">${App.escapeHtml(r.cliente_telefono)}</div>
                </td>
                <td class="py-3 px-4 whitespace-nowrap">
                    <select onchange="Reparaciones.cambiarEstado(${r.id}, this.value)" class="text-xs font-bold rounded-lg border border-slate-200 py-1 px-2 bg-white focus:ring-1 focus:ring-blue-500 focus:outline-none">
                        <option value="Recibido" ${r.estado === 'Recibido' ? 'selected' : ''}>📥 Recibido</option>
                        <option value="En Revision" ${r.estado === 'En Revision' ? 'selected' : ''}>🔍 En Revisión</option>
                        <option value="Esperando Refaccion" ${r.estado === 'Esperando Refaccion' ? 'selected' : ''}>⏳ Esperando Refacción</option>
                        <option value="Listo para Entrega" ${r.estado === 'Listo para Entrega' ? 'selected' : ''}>✨ Listo para Entrega</option>
                        <option value="Entregado" ${r.estado === 'Entregado' ? 'selected' : ''}>✓ Entregado</option>
                        <option value="Cancelado" ${r.estado === 'Cancelado' ? 'selected' : ''}>✕ Cancelado</option>
                    </select>
                </td>
                <td class="py-3 px-4 text-xs whitespace-nowrap">
                    <div class="font-bold text-slate-800">${App.formatCurrency(r.precio_servicio)}</div>
                    <div class="text-[10px] text-slate-400">Anticipo: ${App.formatCurrency(r.anticipo)}</div>
                </td>
                <td class="py-3 px-4 whitespace-nowrap">
                    ${r.saldo_pendiente > 0 ? `<span class="font-bold text-rose-600 text-xs">${App.formatCurrency(r.saldo_pendiente)}</span>` : '<span class="font-bold text-emerald-600 text-xs">Liquidado ✓</span>'}
                </td>
                <td class="py-3 px-4 text-right whitespace-nowrap">
                    <div class="flex items-center justify-end gap-1">
                        <button onclick="Reparaciones.enviarWhatsApp(${r.id})" class="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Enviar aviso por WhatsApp">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/></svg>
                        </button>
                        <button onclick="Reparaciones.abrirBoleta(${r.id})" class="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Imprimir Boleta de Recepción">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                        </button>
                        <button onclick="Reparaciones.abrirModalAbono(${r.id})" class="p-1.5 text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="Registrar Abono o Liquidación">
                            💵
                        </button>
                        <button onclick="Reparaciones.eliminar(${r.id})" class="admin-only p-1.5 text-slate-400 hover:text-rose-600 rounded-lg transition-colors" title="Eliminar orden">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
    },

    async guardar() {
        const nombre = document.getElementById('rep-input-cliente')?.value.trim();
        const telefono = document.getElementById('rep-input-telefono')?.value.trim();
        const modelo = document.getElementById('rep-input-modelo')?.value.trim();
        const color = document.getElementById('rep-input-color')?.value.trim() || '';
        const imei = document.getElementById('rep-input-imei')?.value.trim() || '';
        const patron = document.getElementById('rep-input-patron')?.value.trim() || '';
        const falla = document.getElementById('rep-input-falla')?.value.trim();
        const diag = document.getElementById('rep-input-diag')?.value.trim() || '';
        const condicion = document.getElementById('rep-input-condicion')?.value.trim() || '';
        const costo = parseFloat(document.getElementById('rep-input-costo')?.value) || 0;
        const precio = parseFloat(document.getElementById('rep-input-precio')?.value) || 0;
        const anticipo = parseFloat(document.getElementById('rep-input-anticipo')?.value) || 0;
        const fechaProm = document.getElementById('rep-input-fecha-prom')?.value || null;

        if (!nombre || !telefono || !modelo || !falla) {
            App.showToast("Completa los campos obligatorios (*).", "warning");
            return;
        }

        try {
            const res = await fetch('/api/reparaciones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cliente_nombre: nombre,
                    cliente_telefono: telefono,
                    dispositivo_modelo: modelo,
                    color: color,
                    imei_serie: imei,
                    codigo_patron: patron,
                    falla_reportada: falla,
                    diagnostico_tecnico: diag,
                    condicion_recepcion: condicion,
                    costo_refaccion: costo,
                    precio_servicio: precio,
                    anticipo: anticipo,
                    fecha_prometida: fechaProm
                })
            });

            if (!res.ok) throw new Error('Error al registrar orden de servicio');
            const nueva = await res.json();
            App.showToast(`Orden ${nueva.folio} creada con éxito`, "success");

            // Limpiar formulario
            document.getElementById('form-nueva-reparacion')?.reset();
            const saldoEl = document.getElementById('rep-txt-saldo-calculado');
            if (saldoEl) saldoEl.textContent = '$0.00';

            this.cargar();

            // Preguntar si quiere abrir la boleta
            this.abrirBoleta(nueva.id);
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    async cambiarEstado(id, nuevoEstado) {
        try {
            const res = await fetch(`/api/reparaciones/${id}/estado?nuevo_estado=${encodeURIComponent(nuevoEstado)}`, {
                method: 'PATCH'
            });
            if (!res.ok) throw new Error('Error al cambiar estado');
            App.showToast(`Estado actualizado a: ${nuevoEstado}`, "success");
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    abrirModalAbono(id) {
        const rep = this.reparaciones.find(r => r.id === id);
        if (!rep) return;
        this.reparacionActual = rep;

        document.getElementById('abono-rep-id').value = rep.id;
        document.getElementById('abono-rep-folio').textContent = rep.folio;
        document.getElementById('abono-rep-cliente').textContent = `${rep.cliente_nombre} (${rep.dispositivo_modelo})`;
        document.getElementById('abono-rep-precio').textContent = App.formatCurrency(rep.precio_servicio);
        document.getElementById('abono-rep-anticipo').textContent = App.formatCurrency(rep.anticipo);
        document.getElementById('abono-rep-saldo').textContent = App.formatCurrency(rep.saldo_pendiente);
        document.getElementById('abono-monto-input').value = rep.saldo_pendiente;

        const modal = document.getElementById('modal-abono-reparacion');
        if (modal) modal.classList.remove('hidden');
    },

    cerrarModalAbono() {
        const modal = document.getElementById('modal-abono-reparacion');
        if (modal) modal.classList.add('hidden');
        this.reparacionActual = null;
    },

    async guardarAbono() {
        const id = document.getElementById('abono-rep-id')?.value;
        const monto = parseFloat(document.getElementById('abono-monto-input')?.value) || 0;
        if (!id || monto <= 0) {
            App.showToast("Ingresa un monto válido para abonar.", "warning");
            return;
        }

        try {
            const res = await fetch(`/api/reparaciones/${id}/abono`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ monto_abono: monto })
            });

            if (!res.ok) throw new Error('Error registrando abono');
            App.showToast(`Abono de ${App.formatCurrency(monto)} registrado correctamente`, "success");
            this.cerrarModalAbono();
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    abrirBoleta(id) {
        const rep = this.reparaciones.find(r => r.id === id);
        if (!rep) return;
        this.reparacionActual = rep;

        document.getElementById('boleta-folio').textContent = rep.folio;
        document.getElementById('boleta-fecha').textContent = rep.fecha_ingreso;
        document.getElementById('boleta-cliente-nombre').textContent = rep.cliente_nombre;
        document.getElementById('boleta-cliente-telefono').textContent = rep.cliente_telefono;
        document.getElementById('boleta-modelo').textContent = rep.dispositivo_modelo + (rep.color ? ` (${rep.color})` : '');
        document.getElementById('boleta-falla').textContent = rep.falla_reportada;
        document.getElementById('boleta-condicion').textContent = rep.condicion_recepcion || 'Sin detalles estéticos reportados';
        document.getElementById('boleta-total').textContent = App.formatCurrency(rep.precio_servicio);
        document.getElementById('boleta-anticipo').textContent = App.formatCurrency(rep.anticipo);
        document.getElementById('boleta-saldo').textContent = App.formatCurrency(rep.saldo_pendiente);

        // IMEI / Serie, Contraseña, Accesorios y Técnico
        const elImei = document.getElementById('boleta-imei');
        if (elImei) elImei.textContent = rep.imei_serie || 'No registrado';
        const elPass = document.getElementById('boleta-password');
        if (elPass) elPass.textContent = rep.codigo_patron || 'Sin contraseña / Desbloqueado';
        const elTecnico = document.getElementById('boleta-tecnico');
        if (elTecnico) elTecnico.textContent = rep.tecnico_responsable || 'Samuel N.';

        // Generar QR para la boleta de servicio (consulta en línea o WhatsApp con folio)
        const qrContainer = document.getElementById('boleta-qr-container');
        if (qrContainer && typeof QRCode !== 'undefined') {
            qrContainer.innerHTML = '';
            const wsp = (typeof ConfiguracionTienda !== 'undefined' && ConfiguracionTienda.datos && ConfiguracionTienda.datos.whatsapp_notificaciones) || '';
            const telLimpio = wsp.replace(/\D/g, '');
            const qrUrl = telLimpio
                ? 'https://wa.me/' + telLimpio + '?text=' + encodeURIComponent('Hola, quisiera consultar el estatus de mi orden #' + rep.folio)
                : window.location.origin + '/catalogo?check_rep=' + encodeURIComponent(rep.folio);
            try {
                new QRCode(qrContainer, {
                    text: qrUrl,
                    width: 100,
                    height: 100,
                    colorDark: '#000000',
                    colorLight: '#ffffff',
                    correctLevel: QRCode.CorrectLevel.M
                });
            } catch (e) {
                console.warn('Error generando QR boleta:', e);
            }
        }

        if (typeof ConfiguracionTienda !== 'undefined' && ConfiguracionTienda.aplicarClasesAnchoTickets) {
            ConfiguracionTienda.aplicarClasesAnchoTickets();
        }

        const modal = document.getElementById('modal-boleta-reparacion');
        if (modal) modal.classList.remove('hidden');
    },

    cerrarBoleta() {
        const modal = document.getElementById('modal-boleta-reparacion');
        if (modal) modal.classList.add('hidden');
    },

    imprimirBoleta() {
        const content = document.getElementById('boleta-modal-content');
        if (content) content.classList.add('print-ticket-active');
        window.print();
        setTimeout(() => {
            if (content) content.classList.remove('print-ticket-active');
        }, 500);
    },

    enviarWhatsApp(id) {
        const rep = this.reparaciones.find(r => r.id === id);
        if (!rep) return;

        const tel = (rep.cliente_telefono || '').replace(/\D/g, '');
        if (!tel) {
            App.showToast("El cliente no tiene un teléfono válido.", "error");
            return;
        }

        let mensaje = "";
        if (rep.estado === 'Listo para Entrega') {
            mensaje = `¡Hola, *${rep.cliente_nombre}*! 👋
Te saludamos de *Samuel Navarrete Celulares*.
Tu dispositivo ya está reparado y probado con éxito:

📱 *Equipo:* ${rep.dispositivo_modelo}
📋 *Folio:* ${rep.folio}
🔧 *Servicio realizado:* ${rep.falla_reportada}
💵 *Saldo pendiente a liquidar:* $${rep.saldo_pendiente.toLocaleString('es-MX', {minimumFractionDigits: 2})}

¡Ya puedes pasar a recogerlo en nuestro horario de atención! Muchas gracias por tu confianza. 🚀`;
        } else {
            mensaje = `¡Hola, *${rep.cliente_nombre}*! 👋
Confirmamos la recepción de tu equipo en nuestro Taller Técnico:

📋 *Folio de Servicio:* ${rep.folio}
📱 *Equipo:* ${rep.dispositivo_modelo}
⚠️ *Falla reportada:* ${rep.falla_reportada}
💰 *Presupuesto total:* $${rep.precio_servicio.toLocaleString('es-MX', {minimumFractionDigits: 2})}
💵 *Anticipo recibido:* $${rep.anticipo.toLocaleString('es-MX', {minimumFractionDigits: 2})}
🏷️ *Saldo al entregar:* $${rep.saldo_pendiente.toLocaleString('es-MX', {minimumFractionDigits: 2})}

Te notificaremos en cuanto quede listo. Puedes consultar cualquier duda respondiendo a este mensaje.`;
        }

        window.open(`https://wa.me/${tel}?text=${encodeURIComponent(mensaje)}`, '_blank');
    },

    async eliminar(id) {
        if (!confirm("¿Deseas eliminar esta orden de reparación definitivamente?")) return;
        try {
            const res = await fetch(`/api/reparaciones/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Error al eliminar');
            App.showToast("Orden eliminada", "info");
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        }
    }
};

window.Reparaciones = Reparaciones;

document.addEventListener('DOMContentLoaded', () => {
    Reparaciones.init();
});
