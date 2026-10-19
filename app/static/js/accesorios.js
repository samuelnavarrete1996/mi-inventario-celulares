// accesorios.js - Gestión de catálogo de accesorios, conteo masivo, kardex y pedidos
const Accesorios = {
    items: [],
    categoriaFiltro: 'Todos',
    busqueda: '',
    semaforoFiltro: 'todos', // 'todos', 'agotados', 'bajos', 'disponibles'
    cargaRapidaItems: [],
    pedidoSugeridoData: null,

    init() {
        this.cargar();
    },

    async cargar() {
        const tbody = document.getElementById('tbody-accesorios');
        if (!tbody) return;

        try {
            let url = '/api/accesorios?';
            if (this.categoriaFiltro !== 'Todos') url += `categoria=${encodeURIComponent(this.categoriaFiltro)}&`;
            if (this.busqueda) url += `search=${encodeURIComponent(this.busqueda)}&`;

            const res = await fetch(url);
            if (res.ok) {
                this.items = await res.json();
                this.renderizar();
            }
        } catch (e) {
            console.error("Error al cargar accesorios:", e);
        }
    },

    filtrarCategoria(cat) {
        this.categoriaFiltro = cat;
        document.querySelectorAll('.btn-cat-acc').forEach(b => {
            if (b.dataset.cat === cat) {
                b.classList.add('bg-blue-600', 'text-white');
                b.classList.remove('bg-slate-100', 'text-slate-600');
            } else {
                b.classList.remove('bg-blue-600', 'text-white');
                b.classList.add('bg-slate-100', 'text-slate-600');
            }
        });
        this.cargar();
    },

    filtrarSemaforo(tipo, btn) {
        this.semaforoFiltro = tipo;
        document.querySelectorAll('.btn-semaforo').forEach(b => {
            b.classList.remove('bg-blue-600', 'text-white', 'shadow-xs');
            b.classList.add('border');
        });
        if (btn) {
            btn.classList.add('bg-blue-600', 'text-white', 'shadow-xs');
            btn.classList.remove('border');
        }
        this.renderizar();
    },

    _searchTimeout: null,
    buscar(q) {
        this.busqueda = q;
        const btnClear = document.getElementById('btn-limpiar-acc-search');
        if (btnClear) {
            btnClear.classList.toggle('hidden', !q || q.trim() === '');
        }
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
            this.cargar();
        }, 180);
    },

    limpiarBusqueda() {
        const input = document.getElementById('acc-search-input');
        if (input) input.value = '';
        const btnClear = document.getElementById('btn-limpiar-acc-search');
        if (btnClear) btnClear.classList.add('hidden');
        this.busqueda = '';
        clearTimeout(this._searchTimeout);
        this.cargar();
        if (input) input.focus();
    },

    renderizar() {
        const tbody = document.getElementById('tbody-accesorios');
        if (!tbody) return;

        // Actualizar contadores del semáforo
        const fisicos = this.items.filter(x => !x.es_servicio);
        const countAgotados = fisicos.filter(x => x.stock <= 0).length;
        const countBajos = fisicos.filter(x => x.stock > 0 && x.stock < 5).length;
        const countDisponibles = fisicos.filter(x => x.stock >= 5).length;

        const badgeTodos = document.getElementById('badge-semaforo-todos');
        const badgeAgotados = document.getElementById('badge-semaforo-agotados');
        const badgeBajos = document.getElementById('badge-semaforo-bajos');
        const badgeDisponibles = document.getElementById('badge-semaforo-disponibles');

        if (badgeTodos) badgeTodos.textContent = this.items.length;
        if (badgeAgotados) badgeAgotados.textContent = countAgotados;
        if (badgeBajos) badgeBajos.textContent = countBajos;
        if (badgeDisponibles) badgeDisponibles.textContent = countDisponibles;

        // Filtrar según el semáforo seleccionado
        let itemsRender = this.items;
        if (this.semaforoFiltro === 'agotados') {
            itemsRender = this.items.filter(x => !x.es_servicio && x.stock <= 0);
        } else if (this.semaforoFiltro === 'bajos') {
            itemsRender = this.items.filter(x => !x.es_servicio && x.stock > 0 && x.stock < 5);
        } else if (this.semaforoFiltro === 'disponibles') {
            itemsRender = this.items.filter(x => !x.es_servicio && x.stock >= 5);
        }

        if (itemsRender.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No hay accesorios en esta categoría o filtro de stock</td></tr>`;
            return;
        }

        tbody.innerHTML = itemsRender.map(acc => {
            const stockBadge = acc.es_servicio 
                ? `<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700">Servicio</span>`
                : (acc.stock <= 0
                    ? `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-700 border border-rose-200">🔴 0 pzas</span>`
                    : (acc.stock < 5 
                        ? `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700 border border-amber-200">🟡 Bajo (${acc.stock})</span>`
                        : `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200">🟢 ${acc.stock} pzas</span>`));

            const pMay = acc.precio_mayoreo || acc.precio_venta || 0;
            const p20 = acc.precio_20_pzs || pMay;
            const pCaja = acc.precio_caja || acc.costo_compra || p20;

            const imgHtml = acc.imagen_url 
                ? `<img src="${App.sanitizeUrl(acc.imagen_url)}" class="w-10 h-10 object-contain rounded-xl border border-slate-200 bg-white p-1 flex-shrink-0 shadow-2xs" alt="${App.escapeHtml(acc.nombre)}" onerror="this.onerror=null; this.src='/static/icons/icon-192.png'">`
                : `<span class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center text-base flex-shrink-0">${acc.es_servicio ? '🔧' : '🔌'}</span>`;

            return `
            <tr class="border-b border-slate-100 hover:bg-slate-50 transition-colors text-xs sm:text-sm">
                <td class="py-3 px-4 font-bold text-slate-800">
                    <div class="flex items-center gap-3">
                        ${imgHtml}
                        <div>
                            <div class="leading-snug">${App.escapeHtml(acc.nombre)}</div>
                            <span class="text-xs text-slate-400 font-normal">${App.escapeHtml(acc.categoria)}</span>
                        </div>
                    </div>
                </td>
                <td class="py-3 px-4 text-slate-600 whitespace-nowrap">${App.escapeHtml(acc.categoria)}</td>
                <td class="py-3 px-4 font-bold text-slate-900 whitespace-nowrap">${App.formatCurrency(pMay)}</td>
                <td class="py-3 px-4 whitespace-nowrap"><span class="font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-100">${App.formatCurrency(p20)}</span></td>
                <td class="py-3 px-4 whitespace-nowrap"><span class="font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">${App.formatCurrency(pCaja)}</span></td>
                <td class="py-3 px-4">${stockBadge}</td>
                <td class="py-3 px-4 text-right space-x-1 whitespace-nowrap">
                    <button onclick="POS.agregarAccesorioAlCarrito(${acc.id})" class="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-2xs transition-all" title="Vender en POS">
                        + Vender
                    </button>
                    ${!acc.es_servicio ? `
                    <button onclick="Accesorios.abrirModalAjusteStock(${acc.id})" class="admin-only p-1.5 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Ajuste de Stock / Conteo / Merma">
                        ⚖️
                    </button>
                    <button onclick="Accesorios.abrirModalKardex(${acc.id})" class="p-1.5 text-slate-500 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition-colors" title="Ver Historial Kardex">
                        📜
                    </button>
                    ` : ''}
                    <button onclick="Accesorios.imprimirEtiqueta(${acc.id})" class="p-1.5 text-slate-400 hover:text-amber-600 rounded-lg transition-colors" title="Imprimir Etiqueta con Código">
                        🏷️
                    </button>
                    <button onclick="Accesorios.editar(${acc.id})" class="p-1.5 text-slate-400 hover:text-blue-600 admin-only rounded-lg transition-colors" title="Editar">
                        ✏️
                    </button>
                    <button onclick="Accesorios.eliminar(${acc.id})" class="p-1.5 text-slate-400 hover:text-rose-600 admin-only rounded-lg transition-colors" title="Eliminar">
                        🗑️
                    </button>
                </td>
            </tr>
            `;
        }).join('');
    },

    abrirModalNuevo() {
        document.getElementById('form-accesorio').reset();
        document.getElementById('input-acc-id').value = '';
        if (document.getElementById('input-acc-stock')) document.getElementById('input-acc-stock').value = '0';
        if (document.getElementById('input-acc-costo')) document.getElementById('input-acc-costo').value = '0.00';
        if (document.getElementById('input-acc-20-pzs')) document.getElementById('input-acc-20-pzs').value = '';
        if (document.getElementById('input-acc-caja')) document.getElementById('input-acc-caja').value = '';
        document.getElementById('modal-accesorio-titulo').textContent = 'Nuevo Accesorio / Servicio';
        document.getElementById('modal-accesorio').classList.remove('hidden');
    },

    cerrarModal() {
        document.getElementById('modal-accesorio').classList.add('hidden');
    },

    editar(id) {
        const item = this.items.find(x => x.id === id);
        if (!item) return;

        document.getElementById('input-acc-id').value = item.id;
        document.getElementById('input-acc-nombre').value = item.nombre;
        document.getElementById('input-acc-categoria').value = item.categoria;
        document.getElementById('input-acc-costo').value = item.costo_compra;
        document.getElementById('input-acc-precio').value = item.precio_mayoreo || item.precio_venta;
        if (document.getElementById('input-acc-20-pzs')) {
            document.getElementById('input-acc-20-pzs').value = item.precio_20_pzs || item.precio_mayoreo || item.precio_venta;
        }
        if (document.getElementById('input-acc-caja')) {
            document.getElementById('input-acc-caja').value = item.precio_caja || item.costo_compra;
        }
        document.getElementById('input-acc-stock').value = item.stock;
        document.getElementById('input-acc-servicio').checked = Boolean(item.es_servicio);

        document.getElementById('modal-accesorio-titulo').textContent = 'Editar Accesorio / Servicio';
        document.getElementById('modal-accesorio').classList.remove('hidden');
    },

    async guardar() {
        const id = document.getElementById('input-acc-id').value;
        const nombre = document.getElementById('input-acc-nombre').value.trim();
        const categoria = document.getElementById('input-acc-categoria').value;
        const precio_mayoreo = parseFloat(document.getElementById('input-acc-precio').value) || 0;
        const precio_20_pzs = parseFloat(document.getElementById('input-acc-20-pzs')?.value) || precio_mayoreo;
        const precio_caja = parseFloat(document.getElementById('input-acc-caja')?.value) || 0;
        let costo_compra = parseFloat(document.getElementById('input-acc-costo').value) || 0;
        
        if (!costo_compra && precio_caja > 0) costo_compra = precio_caja;
        if (!costo_compra && precio_mayoreo > 0) costo_compra = precio_mayoreo;

        const precio_venta = precio_mayoreo;
        const stock = parseInt(document.getElementById('input-acc-stock').value, 10) || 0;
        const es_servicio = document.getElementById('input-acc-servicio').checked;

        if (!nombre || precio_venta <= 0) {
            App.showToast("Ingresa un nombre y precio de mayoreo válidos", "error");
            return;
        }

        const data = { 
            nombre, 
            categoria, 
            costo_compra, 
            precio_venta, 
            precio_mayoreo, 
            precio_20_pzs, 
            precio_caja: precio_caja || costo_compra,
            stock, 
            es_servicio 
        };

        try {
            let res;
            if (id) {
                res = await fetch(`/api/accesorios/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            } else {
                res = await fetch('/api/accesorios', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            }

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al guardar");
            }

            App.showToast(id ? "Accesorio actualizado" : "Accesorio registrado con éxito", "success");
            this.cerrarModal();
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    async eliminar(id) {
        if (!confirm("¿Deseas eliminar este accesorio o servicio?")) return;

        try {
            const res = await fetch(`/api/accesorios/${id}`, { method: 'DELETE' });
            if (res.ok) {
                App.showToast("Accesorio eliminado", "info");
                this.cargar();
            } else {
                const err = await res.json();
                throw new Error(err.detail || "Error al eliminar");
            }
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    imprimirEtiqueta(id) {
        const acc = this.items.find(x => x.id === id);
        if (acc && typeof Etiquetas !== 'undefined') {
            Etiquetas.abrirParaAccesorio(acc);
        }
    },

    // ========================================================
    // PILAR 1: PLANTILLA GOOGLE SHEETS / EXCEL Y SUBIDA MASIVA
    // ========================================================
    descargarPlantillaStock(formato = 'sheets') {
        const nombre = (formato === 'sheets' || formato === 'csv') ? 'Google Sheets (.csv)' : 'Excel (.xlsx)';
        App.showToast(`Descargando plantilla para ${nombre}...`, "info");
        window.open(`/api/accesorios/plantilla-stock?formato=${formato}`, '_blank');
    },

    seleccionarArchivoStockExcel() {
        const input = document.getElementById('input-excel-stock');
        if (input) input.click();
    },

    async procesarArchivoStockExcel(input) {
        if (!input.files || input.files.length === 0) return;
        const file = input.files[0];

        if (!confirm(`¿Deseas actualizar el stock masivamente con el archivo "${file.name}"? Se registrarán las entradas en el Kardex.`)) {
            input.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('archivo', file);

        App.showToast("Procesando archivo de stock (Google Sheets / Excel)...", "info");

        try {
            const res = await fetch('/api/accesorios/importar-stock-excel', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al procesar el archivo Excel");
            }

            const data = await res.json();
            App.showToast(`Éxito: ${data.total_actualizados} accesorios actualizados correctamente.`, "success");
            input.value = '';
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
            input.value = '';
        }
    },

    // ========================================================
    // PILAR 1: CARGA RÁPIDA INTERACTIVA EN PANTALLA
    // ========================================================
    abrirModalCargaRapida() {
        this.cargaRapidaItems = this.items
            .filter(x => !x.es_servicio)
            .map(x => ({
                id: x.id,
                nombre: x.nombre,
                categoria: x.categoria,
                stock_actual: x.stock,
                nuevo_stock: x.stock,
                modificado: false
            }));

        const inputFiltro = document.getElementById('filtro-carga-rapida');
        if (inputFiltro) inputFiltro.value = '';

        this.renderTablaCargaRapida();
        this.actualizarContadorModificados();
        document.getElementById('modal-carga-rapida-stock').classList.remove('hidden');
    },

    cerrarModalCargaRapida() {
        document.getElementById('modal-carga-rapida-stock').classList.add('hidden');
    },

    renderTablaCargaRapida() {
        const tbody = document.getElementById('tbody-carga-rapida');
        const filtro = (document.getElementById('filtro-carga-rapida')?.value || '').toLowerCase().trim();
        if (!tbody) return;

        const itemsFiltrados = this.cargaRapidaItems.filter(item => {
            if (!filtro) return true;
            return item.nombre.toLowerCase().includes(filtro) || item.categoria.toLowerCase().includes(filtro);
        });

        if (itemsFiltrados.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-6 text-slate-400">No hay artículos que coincidan con la búsqueda</td></tr>`;
            return;
        }

        tbody.innerHTML = itemsFiltrados.map(item => {
            const modClass = item.modificado ? 'bg-amber-50/70 font-bold' : '';
            return `
            <tr id="row-cr-${item.id}" class="hover:bg-slate-50 transition-colors ${modClass}">
                <td class="py-2.5 px-3">
                    <p class="font-bold text-slate-800 text-xs">${App.escapeHtml(item.nombre)}</p>
                    <span class="text-[10px] text-slate-400">${App.escapeHtml(item.categoria)}</span>
                </td>
                <td class="py-2.5 px-3 text-center text-slate-500 font-semibold text-xs">${item.stock_actual}</td>
                <td class="py-2.5 px-3 text-center">
                    <input type="number" min="0" value="${item.nuevo_stock}" 
                           oninput="Accesorios.modificarStockCargaRapida(${item.id}, this.value)"
                           class="w-20 px-2 py-1 text-center font-bold text-xs bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:outline-none">
                </td>
                <td class="py-2.5 px-3 text-right space-x-1 whitespace-nowrap">
                    <button type="button" onclick="Accesorios.sumarStockCargaRapida(${item.id}, 1)" class="px-2 py-0.5 bg-slate-100 hover:bg-amber-100 text-slate-700 hover:text-amber-800 rounded font-bold text-[11px]">+1</button>
                    <button type="button" onclick="Accesorios.sumarStockCargaRapida(${item.id}, 5)" class="px-2 py-0.5 bg-slate-100 hover:bg-amber-100 text-slate-700 hover:text-amber-800 rounded font-bold text-[11px]">+5</button>
                    <button type="button" onclick="Accesorios.sumarStockCargaRapida(${item.id}, 10)" class="px-2 py-0.5 bg-slate-100 hover:bg-amber-100 text-slate-700 hover:text-amber-800 rounded font-bold text-[11px]">+10</button>
                    <button type="button" onclick="Accesorios.sumarStockCargaRapida(${item.id}, 50)" class="px-2 py-0.5 bg-slate-100 hover:bg-amber-100 text-slate-700 hover:text-amber-800 rounded font-bold text-[11px]">+50</button>
                </td>
            </tr>
            `;
        }).join('');
    },

    filtrarTablaCargaRapida(query) {
        this.renderTablaCargaRapida();
    },

    sumarStockCargaRapida(id, delta) {
        const item = this.cargaRapidaItems.find(x => x.id === id);
        if (!item) return;
        item.nuevo_stock = Math.max(0, (parseInt(item.nuevo_stock, 10) || 0) + delta);
        item.modificado = (item.nuevo_stock !== item.stock_actual);
        this.renderTablaCargaRapida();
        this.actualizarContadorModificados();
    },

    modificarStockCargaRapida(id, valStr) {
        const item = this.cargaRapidaItems.find(x => x.id === id);
        if (!item) return;
        const val = parseInt(valStr, 10);
        item.nuevo_stock = isNaN(val) ? 0 : Math.max(0, val);
        item.modificado = (item.nuevo_stock !== item.stock_actual);
        this.actualizarContadorModificados();
    },

    actualizarContadorModificados() {
        const count = this.cargaRapidaItems.filter(x => x.modificado).length;
        const el = document.getElementById('carga-rapida-contador-modificados');
        if (el) el.textContent = `${count} modificados`;
    },

    async guardarCargaRapida() {
        const modificados = this.cargaRapidaItems
            .filter(x => x.modificado)
            .map(x => ({ id: x.id, nuevo_stock: x.nuevo_stock }));

        if (modificados.length === 0) {
            App.showToast("No has modificado el stock de ningún accesorio.", "info");
            return;
        }

        const btn = document.getElementById('btn-guardar-carga-rapida');
        if (btn) btn.disabled = true;

        try {
            const res = await fetch('/api/accesorios/actualizacion-masiva-rapida', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items: modificados })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al guardar el nuevo stock");
            }

            const data = await res.json();
            App.showToast(`¡Listo! Se actualizaron ${data.total_actualizados} accesorios en Kardex.`, "success");
            this.cerrarModalCargaRapida();
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    // ========================================================
    // PILAR 4: SUGERIDO DE REABASTECIMIENTO Y WHATSAPP
    // ========================================================
    async abrirModalPedidoProveedor() {
        try {
            App.showToast("Calculando sugerido de reabastecimiento...", "info");
            const res = await fetch('/api/accesorios/sugerido-reabastecimiento');
            if (!res.ok) throw new Error("Error al obtener el reporte de reabastecimiento");

            this.pedidoSugeridoData = await res.json();

            const itemsCountEl = document.getElementById('pedido-items-count');
            const agotadosCountEl = document.getElementById('pedido-agotados-count');
            const totalPiezasEl = document.getElementById('pedido-total-piezas');
            const inversionEl = document.getElementById('pedido-inversion-estimada');

            if (itemsCountEl) itemsCountEl.textContent = this.pedidoSugeridoData.total_items_surtir;
            if (agotadosCountEl) agotadosCountEl.textContent = this.pedidoSugeridoData.total_agotados;
            if (totalPiezasEl) totalPiezasEl.textContent = this.pedidoSugeridoData.total_piezas_sugeridas;
            if (inversionEl) inversionEl.textContent = App.formatCurrency(this.pedidoSugeridoData.inversion_estimada_total);

            const tbody = document.getElementById('tbody-pedido-proveedor');
            if (tbody) {
                if (this.pedidoSugeridoData.sugeridos.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-emerald-600 font-bold">¡Excelente! Todos los accesorios cuentan con stock suficiente.</td></tr>`;
                } else {
                    tbody.innerHTML = this.pedidoSugeridoData.sugeridos.map(item => {
                        const subtotal = item.cantidad_sugerida * item.costo_unitario;
                        const badgeStock = item.stock_actual <= 0 
                            ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700">0 pzas (Agotado)</span>`
                            : `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700">${item.stock_actual} pzas (Bajo)</span>`;

                        return `
                        <tr id="pedido-row-${item.id}">
                            <td class="py-2 px-3">
                                <p class="font-bold text-slate-800 text-xs">${App.escapeHtml(item.nombre)}</p>
                                <span class="text-[10px] text-slate-400">${App.escapeHtml(item.categoria)}</span>
                            </td>
                            <td class="py-2 px-3 text-center">${badgeStock}</td>
                            <td class="py-2 px-3 text-center">
                                <input type="number" min="0" value="${item.cantidad_sugerida}" 
                                       oninput="Accesorios.recalcularPedidoProveedor(${item.id}, this.value)"
                                       class="w-20 px-2 py-1 text-center font-bold text-xs bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                            </td>
                            <td class="py-2 px-3 text-right text-slate-600 font-semibold">${App.formatCurrency(item.costo_unitario)}</td>
                            <td class="py-2 px-3 text-right font-black text-slate-900" id="pedido-subtotal-${item.id}">${App.formatCurrency(subtotal)}</td>
                        </tr>
                        `;
                    }).join('');
                }
            }

            document.getElementById('modal-pedido-proveedor').classList.remove('hidden');
        } catch (e) {
            App.showToast(e.message, "error");
        }
    },

    cerrarModalPedidoProveedor() {
        document.getElementById('modal-pedido-proveedor').classList.add('hidden');
    },

    recalcularPedidoProveedor(id, nuevaCantStr) {
        if (!this.pedidoSugeridoData) return;
        const item = this.pedidoSugeridoData.sugeridos.find(x => x.id === id);
        if (!item) return;

        const val = parseInt(nuevaCantStr, 10);
        item.cantidad_sugerida = isNaN(val) ? 0 : Math.max(0, val);

        const subtotal = item.cantidad_sugerida * item.costo_unitario;
        const elSub = document.getElementById(`pedido-subtotal-${id}`);
        if (elSub) elSub.textContent = App.formatCurrency(subtotal);

        // Recalcular métricas generales
        const totalPzas = this.pedidoSugeridoData.sugeridos.reduce((acc, it) => acc + (it.cantidad_sugerida || 0), 0);
        const inversion = this.pedidoSugeridoData.sugeridos.reduce((acc, it) => acc + ((it.cantidad_sugerida || 0) * it.costo_unitario), 0);

        const totalPiezasEl = document.getElementById('pedido-total-piezas');
        const inversionEl = document.getElementById('pedido-inversion-estimada');
        if (totalPiezasEl) totalPiezasEl.textContent = totalPzas;
        if (inversionEl) inversionEl.textContent = App.formatCurrency(inversion);
    },

    copiarPedidoWhatsApp() {
        if (!this.pedidoSugeridoData || this.pedidoSugeridoData.sugeridos.length === 0) {
            App.showToast("No hay productos sugeridos en la lista.", "info");
            return;
        }

        const itemsConCantidad = this.pedidoSugeridoData.sugeridos.filter(x => x.cantidad_sugerida > 0);
        if (itemsConCantidad.length === 0) {
            App.showToast("No hay productos con cantidad mayor a 0 para pedir.", "warning");
            return;
        }

        const totalPzas = itemsConCantidad.reduce((acc, it) => acc + (it.cantidad_sugerida || 0), 0);
        const inversion = itemsConCantidad.reduce((acc, it) => acc + ((it.cantidad_sugerida || 0) * it.costo_unitario), 0);

        let texto = `*¡Hola! Buen día. Te paso la lista de accesorios que requerimos surtir:* 📦\n\n`;
        itemsConCantidad.forEach((it, idx) => {
            texto += `${idx + 1}. *${it.nombre}* (${it.categoria})\n`;
            texto += `   • Cantidad a surtir: *${it.cantidad_sugerida} pzas*\n`;
        });
        texto += `\n─────────────────────\n`;
        texto += `📊 *Total de piezas requeridas:* ${totalPzas} piezas\n`;
        texto += `💰 *Presupuesto estimado:* $${inversion.toLocaleString('es-MX', {minimumFractionDigits: 2})} MXN\n\n`;
        texto += `¿Me confirmas cuáles tienes disponibles de entrega inmediata para coordinar pago y envío? ¡Gracias!`;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(texto).then(() => {
                App.showToast("¡Pedido copiado al portapapeles! Pégalo en WhatsApp.", "success");
            }).catch(() => {
                this.fallbackCopiarTexto(texto);
            });
        } else {
            this.fallbackCopiarTexto(texto);
        }

        // Abre WhatsApp Web o App en una ventana aparte
        const urlWA = `https://wa.me/?text=${encodeURIComponent(texto)}`;
        window.open(urlWA, '_blank');
    },

    fallbackCopiarTexto(texto) {
        const textArea = document.createElement("textarea");
        textArea.value = texto;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            App.showToast("¡Pedido copiado! Pégalo en WhatsApp.", "success");
        } catch (err) {
            prompt("Copia este mensaje para enviarlo por WhatsApp:", texto);
        }
        document.body.removeChild(textArea);
    },

    // ========================================================
    // PILAR 5: AJUSTE INDIVIDUAL AUDITADO (MERMAS / CONTEO)
    // ========================================================
    abrirModalAjusteStock(id) {
        const item = this.items.find(x => x.id === id);
        if (!item) return;

        document.getElementById('ajuste-acc-id').value = item.id;
        document.getElementById('ajuste-acc-nombre').textContent = item.nombre;
        document.getElementById('ajuste-acc-categoria').textContent = item.categoria;
        document.getElementById('ajuste-acc-stock-actual').textContent = item.stock;
        document.getElementById('ajuste-acc-nuevo-stock').value = item.stock;
        document.getElementById('ajuste-acc-motivo').value = 'AJUSTE_AUDITORIA';
        document.getElementById('ajuste-acc-notas').value = '';

        document.getElementById('modal-ajuste-stock').classList.remove('hidden');
    },

    cerrarModalAjusteStock() {
        document.getElementById('modal-ajuste-stock').classList.add('hidden');
    },

    async guardarAjusteStock() {
        const id = document.getElementById('ajuste-acc-id').value;
        const nuevo_stock = parseInt(document.getElementById('ajuste-acc-nuevo-stock').value, 10);
        const tipo_movimiento = document.getElementById('ajuste-acc-motivo').value;
        const notas = document.getElementById('ajuste-acc-notas').value.trim();

        if (isNaN(nuevo_stock) || nuevo_stock < 0) {
            App.showToast("El nuevo stock no puede ser un número negativo", "error");
            return;
        }

        const btn = document.getElementById('btn-confirmar-ajuste-stock');
        if (btn) btn.disabled = true;

        try {
            const res = await fetch(`/api/accesorios/${id}/ajuste-stock`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nuevo_stock, tipo_movimiento, notas })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error al registrar el ajuste");
            }

            App.showToast("Movimiento de inventario auditado y registrado en Kardex", "success");
            this.cerrarModalAjusteStock();
            this.cargar();
        } catch (e) {
            App.showToast(e.message, "error");
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    // ========================================================
    // PILAR 5: BITÁCORA KARDEX DE AUDITORÍA
    // ========================================================
    async abrirModalKardexGeneral() {
        const sub = document.getElementById('kardex-subtitulo');
        if (sub) sub.textContent = "Bitácora cronológica general (últimos 100 movimientos de almacén)";

        document.getElementById('modal-kardex-historial').classList.remove('hidden');
        await this.cargarMovimientosKardex('/api/accesorios/kardex?limit=100');
    },

    async abrirModalKardex(id) {
        const item = this.items.find(x => x.id === id);
        const sub = document.getElementById('kardex-subtitulo');
        if (sub && item) sub.textContent = `Historial auditado para: ${item.nombre}`;

        document.getElementById('modal-kardex-historial').classList.remove('hidden');
        await this.cargarMovimientosKardex(`/api/accesorios/${id}/kardex`);
    },

    cerrarModalKardex() {
        document.getElementById('modal-kardex-historial').classList.add('hidden');
    },

    async cargarMovimientosKardex(url) {
        const tbody = document.getElementById('tbody-kardex');
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">Cargando bitácora Kardex...</td></tr>`;

        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error("Error al obtener bitácora Kardex");
            const movs = await res.json();

            if (movs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No hay movimientos registrados aún para este artículo</td></tr>`;
                return;
            }

            tbody.innerHTML = movs.map(m => {
                const esEntrada = m.cantidad > 0;
                const badgeTipo = {
                    'VENTA': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-100 text-blue-700">Venta POS</span>',
                    'COMPRA': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-100 text-emerald-700">Entrada Compra</span>',
                    'MERMA': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-100 text-rose-700">Merma / Daño</span>',
                    'AJUSTE_AUDITORIA': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-100 text-purple-700">Conteo Auditoría</span>',
                    'CARGA_MASIVA': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-100 text-amber-800">Carga Masiva</span>',
                    'DEVOLUCION_PROVEEDOR': '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-700">Devolución</span>'
                }[m.tipo_movimiento] || `<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-600">${App.escapeHtml(m.tipo_movimiento)}</span>`;

                const cantTxt = esEntrada 
                    ? `<span class="text-emerald-600 font-extrabold">+${m.cantidad}</span>` 
                    : `<span class="text-rose-600 font-extrabold">${m.cantidad}</span>`;

                return `
                <tr class="hover:bg-slate-50 transition-colors">
                    <td class="py-2.5 px-3 text-slate-500 whitespace-nowrap">${App.escapeHtml(m.fecha)}</td>
                    <td class="py-2.5 px-3 font-bold text-slate-800">${App.escapeHtml(m.accesorio_nombre || 'Artículo #' + m.accesorio_id)}</td>
                    <td class="py-2.5 px-3 text-center whitespace-nowrap">${badgeTipo}</td>
                    <td class="py-2.5 px-3 text-center">${cantTxt}</td>
                    <td class="py-2.5 px-3 text-center font-mono text-[11px] text-slate-600 whitespace-nowrap">${m.stock_anterior} ➔ <strong class="text-slate-900">${m.stock_nuevo}</strong></td>
                    <td class="py-2.5 px-3 text-slate-600 text-xs">${App.escapeHtml(m.motivo || '--')}</td>
                    <td class="py-2.5 px-3 text-slate-500 text-xs whitespace-nowrap font-medium">${App.escapeHtml(m.usuario)}</td>
                </tr>
                `;
            }).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-rose-500 font-bold">${e.message}</td></tr>`;
        }
    }
};
