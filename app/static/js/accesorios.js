// accesorios.js - Gestión de catálogo de accesorios y servicios
const Accesorios = {
    items: [],
    categoriaFiltro: 'Todos',
    busqueda: '',

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

    buscar(q) {
        this.busqueda = q;
        this.cargar();
    },

    renderizar() {
        const tbody = document.getElementById('tbody-accesorios');
        if (!tbody) return;

        if (this.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No hay accesorios ni servicios registrados</td></tr>`;
            return;
        }

        tbody.innerHTML = this.items.map(acc => {
            const stockBadge = acc.es_servicio 
                ? `<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700">Servicio</span>`
                : (acc.stock <= 0
                    ? `<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">0 pzas</span>`
                    : (acc.stock <= 5 
                        ? `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700">Bajo (${acc.stock})</span>`
                        : `<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">${acc.stock} pzas</span>`));

            const pMay = acc.precio_mayoreo || acc.precio_venta || 0;
            const p20 = acc.precio_20_pzs || pMay;
            const pCaja = acc.precio_caja || acc.costo_compra || p20;

            const imgHtml = acc.imagen_url 
                ? `<img src="${App.sanitizeUrl(acc.imagen_url)}" class="w-11 h-11 object-contain rounded-xl border border-slate-200 bg-white p-1 flex-shrink-0 shadow-2xs" alt="${App.escapeHtml(acc.nombre)}" onerror="this.onerror=null; this.src='/static/icons/icon-192.png'">`
                : `<span class="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center text-lg flex-shrink-0">${acc.es_servicio ? '🔧' : '🔌'}</span>`;

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
                <td class="py-3 px-4 text-right space-x-1">
                    <button onclick="POS.agregarAccesorioAlCarrito(${acc.id})" class="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-2xs transition-all" title="Vender en POS">
                        + Vender
                    </button>
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
        
        // El costo más bajo por modelo
        if (!costo_compra && precio_caja > 0) costo_compra = precio_caja;
        if (!costo_compra && precio_mayoreo > 0) costo_compra = precio_mayoreo;

        // El precio al que venderemos es precio mayoreo
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
    }
};
