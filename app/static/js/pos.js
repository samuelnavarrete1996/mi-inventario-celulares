// pos.js - Módulo de Punto de Venta (POS) con Carrito Múltiple, Teléfonos, Accesorios, Pagos y Barcode Scanner

const POS = {
    debounceTimer: null,
    carrito: [], // Array de { tipo: 'equipo'|'accesorio', id, equipo|accesorio, cantidad, precio_unitario, precio_final, costo_unitario }
    metodoPago: 'Efectivo', // 'Efectivo', 'Transferencia', 'Combinado', 'Equipo Garantía'
    reciboActual: null,
    catalogoTab: 'equipos', // 'equipos' o 'accesorios'
    compatibilidadFiltro: '',

    init() {
        this.setupSearch();
        this.setupPhoneLookup();
        this.setupPaymentMethodListeners();
        this.setupCartListeners();
        this.setupBarcodeScanner();
        this.renderCarrito();
    },

    setupSearch() {
        const searchInput = document.getElementById('pos-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                clearTimeout(this.debounceTimer);
                const query = e.target.value.trim();
                this.debounceTimer = setTimeout(() => {
                    if (this.catalogoTab === 'accesorios') {
                        this.buscarAccesoriosPOS(query);
                    } else {
                        this.buscarEquipos(query);
                    }
                }, 200);
            });

            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const query = searchInput.value.trim();
                    if (query) {
                        this.procesarCodigoEscaneado(query);
                    }
                }
            });
        }
    },

    setupPhoneLookup() {
        const inputTel = document.getElementById('pos-cliente-telefono');
        const inputNombre = document.getElementById('pos-cliente-nombre');
        const badgeCliente = document.getElementById('badge-cliente-existente');

        if (inputTel && inputNombre) {
            const buscarCliente = async () => {
                const tel = inputTel.value.trim();
                if (tel.length >= 7) {
                    try {
                        const res = await fetch(`/api/clientes/buscar-telefono?telefono=${encodeURIComponent(tel)}`);
                        if (res.ok) {
                            const cliente = await res.json();
                            if (cliente && cliente.nombre) {
                                inputNombre.value = cliente.nombre;
                                if (badgeCliente) {
                                    badgeCliente.textContent = "Cliente registrado ✓";
                                    badgeCliente.classList.remove('hidden');
                                }
                            } else {
                                if (badgeCliente) badgeCliente.classList.add('hidden');
                            }
                        }
                    } catch (e) {
                        console.error("Error buscando cliente:", e);
                    }
                } else {
                    if (badgeCliente) badgeCliente.classList.add('hidden');
                }
            };

            inputTel.addEventListener('input', buscarCliente);
            inputTel.addEventListener('blur', buscarCliente);
        }
    },

    setupPaymentMethodListeners() {
        const btns = document.querySelectorAll('.payment-method-btn');
        btns.forEach(btn => {
            btn.addEventListener('click', () => {
                const metodo = btn.dataset.metodo;
                this.seleccionarMetodoPago(metodo);
            });
        });

        // Inputs de pago combinado (Efectivo, Transferencia, Garantía)
        const inputsCombinados = ['pago-monto-efectivo', 'pago-monto-transferencia', 'pago-monto-garantia'];
        inputsCombinados.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', () => this.calcularBalanceCombinado());
            }
        });

        // Input de cambio para efectivo
        const inputPagaCon = document.getElementById('efectivo-paga-con');
        if (inputPagaCon) {
            inputPagaCon.addEventListener('input', () => {
                this.calcularCambioEfectivo();
            });
        }
    },

    setupCartListeners() {
        const formCheckout = document.getElementById('form-checkout-pos');
        if (formCheckout) {
            formCheckout.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.procesarVenta();
            });
        }
    },

    seleccionarMetodoPago(metodo) {
        this.metodoPago = metodo;

        // Actualizar botones de método
        document.querySelectorAll('.payment-method-btn').forEach(btn => {
            if (btn.dataset.metodo === metodo) {
                btn.classList.add('bg-blue-600', 'text-white', 'border-blue-600', 'shadow-xs');
                btn.classList.remove('bg-white', 'text-slate-700', 'border-slate-200');
            } else {
                btn.classList.remove('bg-blue-600', 'text-white', 'border-blue-600', 'shadow-xs');
                btn.classList.add('bg-white', 'text-slate-700', 'border-slate-200');
            }
        });

        // Mostrar / Ocultar paneles según el método
        const panelEfectivo = document.getElementById('panel-pago-efectivo');
        const panelTransferencia = document.getElementById('panel-pago-transferencia');
        const panelCombinado = document.getElementById('panel-pago-combinado');
        const panelGarantia = document.getElementById('panel-pago-garantia');

        if (panelEfectivo) panelEfectivo.classList.toggle('hidden', metodo !== 'Efectivo');
        if (panelTransferencia) panelTransferencia.classList.toggle('hidden', metodo !== 'Transferencia');
        if (panelCombinado) panelCombinado.classList.toggle('hidden', metodo !== 'Combinado');
        if (panelGarantia) panelGarantia.classList.toggle('hidden', metodo !== 'Equipo Garantía');

        if (metodo === 'Combinado') {
            this.inicializarMontosCombinados();
            this.calcularBalanceCombinado();
        } else if (metodo === 'Efectivo') {
            this.calcularCambioEfectivo();
        } else if (metodo === 'Equipo Garantía') {
            const elTotalGarantia = document.getElementById('resumen-monto-garantia');
            if (elTotalGarantia) elTotalGarantia.textContent = App.formatCurrency(this.obtenerTotalCarrito());
        }
    },

    inicializarMontosCombinados() {
        const total = this.obtenerTotalCarrito();
        const inputEf = document.getElementById('pago-monto-efectivo');
        const inputTr = document.getElementById('pago-monto-transferencia');
        const inputGt = document.getElementById('pago-monto-garantia');

        if (inputEf && inputTr && inputGt) {
            const ef = parseFloat(inputEf.value) || 0;
            const tr = parseFloat(inputTr.value) || 0;
            const gt = parseFloat(inputGt.value) || 0;

            if (ef === 0 && tr === 0 && gt === 0 && total > 0) {
                inputEf.value = (total / 2).toFixed(2);
                inputTr.value = (total - (total / 2)).toFixed(2);
                inputGt.value = '0.00';
            }
        }
    },

    calcularBalanceCombinado() {
        const totalVenta = this.obtenerTotalCarrito();
        const inputEf = document.getElementById('pago-monto-efectivo');
        const inputTr = document.getElementById('pago-monto-transferencia');
        const inputGt = document.getElementById('pago-monto-garantia');

        const ef = parseFloat(inputEf?.value) || 0;
        const tr = parseFloat(inputTr?.value) || 0;
        const gt = parseFloat(inputGt?.value) || 0;

        const sumaPagos = ef + tr + gt;
        const diferencia = totalVenta - sumaPagos;

        const badgeBalance = document.getElementById('badge-balance-combinado');
        const txtAsignado = document.getElementById('txt-monto-asignado');

        if (txtAsignado) txtAsignado.textContent = App.formatCurrency(sumaPagos);

        if (badgeBalance) {
            if (Math.abs(diferencia) < 0.05) {
                badgeBalance.textContent = "✓ Monto exacto cubierto";
                badgeBalance.className = "text-xs font-bold text-emerald-700 bg-emerald-100 border border-emerald-300 px-2.5 py-1 rounded-lg";
            } else if (diferencia > 0) {
                badgeBalance.textContent = `Faltan: ${App.formatCurrency(diferencia)}`;
                badgeBalance.className = "text-xs font-bold text-amber-700 bg-amber-100 border border-amber-300 px-2.5 py-1 rounded-lg animate-pulse";
            } else {
                badgeBalance.textContent = `Sobran: ${App.formatCurrency(Math.abs(diferencia))}`;
                badgeBalance.className = "text-xs font-bold text-rose-700 bg-rose-100 border border-rose-300 px-2.5 py-1 rounded-lg";
            }
        }
    },

    calcularCambioEfectivo() {
        const totalVenta = this.obtenerTotalCarrito();
        const inputPagaCon = document.getElementById('efectivo-paga-con');
        const txtCambio = document.getElementById('txt-cambio-efectivo');
        const boxCambio = document.getElementById('box-cambio-efectivo');

        const pagaCon = parseFloat(inputPagaCon?.value) || 0;

        if (pagaCon > 0 && boxCambio && txtCambio) {
            boxCambio.classList.remove('hidden');
            const cambio = pagaCon - totalVenta;
            if (cambio >= 0) {
                txtCambio.textContent = App.formatCurrency(cambio);
                txtCambio.className = "font-extrabold text-emerald-600 text-base";
            } else {
                txtCambio.textContent = `Faltan ${App.formatCurrency(Math.abs(cambio))}`;
                txtCambio.className = "font-extrabold text-rose-600 text-sm";
            }
        } else if (boxCambio) {
            boxCambio.classList.add('hidden');
        }
    },

    obtenerTotalCarrito() {
        return this.carrito.reduce((acc, item) => acc + (parseFloat(item.precio_final) || 0), 0);
    },

    obtenerMargenTotalCarrito() {
        return this.carrito.reduce((acc, item) => {
            const precio = parseFloat(item.precio_final) || 0;
            const costo = (parseFloat(item.costo_unitario) || 0) * (item.cantidad || 1);
            return acc + (precio - costo);
        }, 0);
    },

    // --- GESTIÓN DEL CARRITO (TELÉFONOS Y ACCESORIOS) ---

    agregarAlCarrito(equipo) {
        const existe = this.carrito.some(it => it.tipo === 'equipo' && it.id === equipo.id);
        if (existe) {
            App.showToast(`"${equipo.modelo}" (IMEI: ${equipo.imei}) ya está en el carrito.`, "info");
            return;
        }

        this.carrito.push({
            tipo: 'equipo',
            id: equipo.id,
            equipo: equipo,
            cantidad: 1,
            precio_unitario: equipo.precio_venta,
            precio_final: equipo.precio_venta,
            costo_unitario: equipo.costo_compra
        });

        App.showToast(`Agregado: ${equipo.modelo}`, "success");
        this.renderCarrito();
        this.actualizarBotonCatalogo(equipo.id, true);
    },

    async agregarAccesorioAlCarrito(accesorioOrId) {
        let accesorio = accesorioOrId;
        if (typeof accesorioOrId === 'number' || typeof accesorioOrId === 'string') {
            if (typeof Accesorios !== 'undefined' && Accesorios.items && Accesorios.items.length > 0) {
                accesorio = Accesorios.items.find(x => x.id === parseInt(accesorioOrId, 10));
            }
            if (!accesorio) {
                try {
                    const res = await fetch(`/api/accesorios`);
                    if (res.ok) {
                        const lista = await res.json();
                        accesorio = lista.find(x => x.id === parseInt(accesorioOrId, 10));
                    }
                } catch (e) {
                    console.error(e);
                }
            }
        }
        if (!accesorio) {
            App.showToast("No se encontró el accesorio especificado.", "error");
            return;
        }

        const item = this.carrito.find(it => it.tipo === 'accesorio' && it.id === accesorio.id);
        if (item) {
            if (!accesorio.es_servicio && item.cantidad >= accesorio.stock) {
                App.showToast(`Stock máximo alcanzado para ${accesorio.nombre} (${accesorio.stock} disp.)`, "warning");
                return;
            }
            item.cantidad += 1;
            item.precio_final = item.cantidad * item.precio_unitario;
        } else {
            if (accesorio.stock <= 0 && !accesorio.es_servicio) {
                App.showToast(`No hay stock de "${accesorio.nombre}".`, "error");
                return;
            }
            this.carrito.push({
                tipo: 'accesorio',
                id: accesorio.id,
                accesorio: accesorio,
                cantidad: 1,
                precio_unitario: accesorio.precio_venta,
                precio_final: accesorio.precio_venta,
                costo_unitario: accesorio.costo_compra
            });
        }

        const colorTxt = accesorio.color ? ` (${accesorio.color})` : '';
        App.showToast(`Accesorio agregado: ${accesorio.nombre}${colorTxt}`, "success");
        this.renderCarrito();
    },

    modificarCantidadAccesorio(id, delta) {
        const item = this.carrito.find(it => it.tipo === 'accesorio' && it.id === id);
        if (!item) return;

        const nuevaCant = item.cantidad + delta;
        if (nuevaCant <= 0) {
            this.quitarDelCarrito(id, 'accesorio');
            return;
        }
        if (nuevaCant > item.accesorio.stock) {
            App.showToast(`Stock máximo alcanzado (${item.accesorio.stock} disponibles)`, "warning");
            return;
        }

        item.cantidad = nuevaCant;
        item.precio_final = item.cantidad * item.precio_unitario;
        this.renderCarrito();
    },

    quitarDelCarrito(id, tipo = 'equipo') {
        this.carrito = this.carrito.filter(it => !(it.id === id && it.tipo === tipo));
        this.renderCarrito();
        if (tipo === 'equipo') {
            this.actualizarBotonCatalogo(id, false);
        }
    },

    actualizarPrecioItem(id, nuevoPrecio, tipo = 'equipo') {
        const item = this.carrito.find(it => it.id === id && it.tipo === tipo);
        if (item) {
            item.precio_final = parseFloat(nuevoPrecio) || 0;
            this.actualizarTotalesCarrito();
            if (this.metodoPago === 'Combinado') {
                this.calcularBalanceCombinado();
            } else if (this.metodoPago === 'Efectivo') {
                this.calcularCambioEfectivo();
            }
        }
    },

    vaciarCarrito() {
        if (this.carrito.length === 0) return;
        this.carrito = [];
        this.renderCarrito();
        this.buscarEquipos(document.getElementById('pos-search-input')?.value.trim() || '');
    },

    actualizarBotonCatalogo(equipoId, enCarrito) {
        const btn = document.getElementById(`btn-add-cart-${equipoId}`);
        if (!btn) return;

        if (enCarrito) {
            btn.innerHTML = `
                <svg class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                <span>En Carrito ✓</span>
            `;
            btn.className = "w-full bg-emerald-50 text-emerald-700 border border-emerald-300 font-semibold py-2 px-3 rounded-xl flex items-center justify-center gap-1.5 text-xs transition-all";
        } else {
            btn.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                <span>+ Agregar al Carrito</span>
            `;
            btn.className = "w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold py-2 px-3 rounded-xl shadow-xs flex items-center justify-center gap-1.5 text-xs transition-all";
        }
    },

    renderCarrito() {
        const container = document.getElementById('cart-items-container');
        const emptyState = document.getElementById('cart-empty-state');
        const badgeCount = document.getElementById('cart-badge-count');
        const cartContent = document.getElementById('cart-active-content');

        const totalItems = this.carrito.reduce((acc, it) => acc + (it.cantidad || 1), 0);
        if (badgeCount) badgeCount.textContent = `${totalItems} ${totalItems === 1 ? 'artículo' : 'artículos'}`;

        if (this.carrito.length === 0) {
            if (emptyState) emptyState.classList.remove('hidden');
            if (cartContent) cartContent.classList.add('hidden');
            if (container) container.innerHTML = '';
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');
        if (cartContent) cartContent.classList.remove('hidden');

        if (container) {
            container.innerHTML = this.carrito.map((item) => {
                if (item.tipo === 'accesorio') {
                    const acc = item.accesorio;
                    const costoTotal = (item.costo_unitario || 0) * item.cantidad;
                    const margen = item.precio_final - costoTotal;
                    const pct = costoTotal > 0 ? ((margen / costoTotal) * 100).toFixed(1) : 0;

                    return `
                    <div class="p-3 bg-white rounded-xl border border-blue-200/80 shadow-2xs hover:border-blue-300 transition-all space-y-2">
                        <div class="flex justify-between items-start gap-2">
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-1.5 flex-wrap">
                                    <span class="text-sm">🎧</span>
                                    <h5 class="font-bold text-slate-800 text-sm truncate">${App.escapeHtml(acc.nombre)}</h5>
                                </div>
                                <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5 flex-wrap">
                                    <span class="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-medium">${App.escapeHtml(acc.categoria)}</span>
                                    ${acc.color ? `<span class="bg-violet-100 text-violet-800 px-1.5 py-0.5 rounded text-[10px] font-bold border border-violet-200">🎨 ${App.escapeHtml(acc.color)}</span>` : ''}
                                    ${acc.codigo_barras ? `<span>•</span><span class="font-mono text-[10px] text-slate-500">${App.escapeHtml(acc.codigo_barras)}</span>` : ''}
                                    <span>•</span>
                                    <span class="text-[10px] text-slate-500">Stock: ${acc.stock}</span>
                                </div>
                            </div>
                            <div class="flex items-center gap-1">
                                <button type="button" onclick="POS.quitarDelCarrito(${acc.id}, 'accesorio')" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors" title="Quitar accesorio">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                </button>
                            </div>
                        </div>

                        <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-3">
                            <!-- Cantidad -->
                            <div class="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2 py-0.5">
                                <button type="button" onclick="POS.modificarCantidadAccesorio(${acc.id}, -1)" class="text-slate-500 hover:text-slate-800 font-bold px-1 text-sm leading-none">−</button>
                                <span class="font-bold text-slate-800 text-xs px-1 min-w-[20px] text-center">${item.cantidad}</span>
                                <button type="button" onclick="POS.modificarCantidadAccesorio(${acc.id}, 1)" class="text-slate-500 hover:text-slate-800 font-bold px-1 text-sm leading-none">+</button>
                            </div>

                            <!-- Precio Final -->
                            <div class="flex items-center gap-1.5">
                                <div class="relative w-24">
                                    <span class="absolute inset-y-0 left-0 pl-2 flex items-center text-slate-400 text-xs font-bold">$</span>
                                    <input type="number" step="0.50" min="0" value="${item.precio_final}" 
                                        onchange="POS.actualizarPrecioItem(${acc.id}, this.value, 'accesorio')"
                                        oninput="POS.actualizarPrecioItem(${acc.id}, this.value, 'accesorio')"
                                        class="w-full pl-5 pr-2 py-1 text-xs font-bold text-slate-800 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-blue-500 focus:outline-none">
                                </div>
                            </div>

                            <!-- Margen (Admin Only) -->
                            <div class="text-right admin-only">
                                <span class="text-[10px] text-slate-400 block">Margen:</span>
                                <span class="text-xs font-bold ${margen >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                                    +${App.formatCurrency(margen)} (${pct}%)
                                </span>
                            </div>
                        </div>
                    </div>
                    `;
                } else {
                    const eq = item.equipo;
                    const margen = item.precio_final - eq.costo_compra;
                    const pct = eq.costo_compra > 0 ? ((margen / eq.costo_compra) * 100).toFixed(1) : 0;

                    return `
                    <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs hover:border-slate-300 transition-all space-y-2">
                        <div class="flex justify-between items-start gap-2">
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-1.5">
                                    <h5 class="font-bold text-slate-800 text-sm truncate">${App.escapeHtml(eq.modelo)}</h5>
                                    <span class="text-[11px] bg-slate-100 text-slate-600 px-1.5 py-0.2 rounded font-medium">${eq.capacidad_gb}GB</span>
                                </div>
                                <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                                    <span>${App.escapeHtml(eq.color)}</span>
                                    <span>•</span>
                                    <span class="font-mono text-[11px] text-slate-600">IMEI: ${App.escapeHtml(eq.imei)}</span>
                                </div>
                            </div>
                            <div class="flex items-center gap-1">
                                ${App.getGradeBadge(eq.grado)}
                                <button type="button" onclick="POS.quitarDelCarrito(${eq.id}, 'equipo')" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors" title="Quitar este equipo">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                </button>
                            </div>
                        </div>

                        <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-3">
                            <div class="flex items-center gap-1.5">
                                <label class="text-[11px] uppercase font-bold text-slate-400">Precio:</label>
                                <div class="relative w-28">
                                    <span class="absolute inset-y-0 left-0 pl-2 flex items-center text-slate-400 text-xs font-bold">$</span>
                                    <input type="number" step="0.50" min="0" value="${item.precio_final}" 
                                        onchange="POS.actualizarPrecioItem(${eq.id}, this.value, 'equipo')"
                                        oninput="POS.actualizarPrecioItem(${eq.id}, this.value, 'equipo')"
                                        class="w-full pl-5 pr-2 py-1 text-xs font-bold text-slate-800 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-blue-500 focus:outline-none">
                                </div>
                            </div>
                            <div class="text-right admin-only">
                                <span class="text-[10px] text-slate-400 block">Margen:</span>
                                <span class="text-xs font-bold ${margen >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                                    +${App.formatCurrency(margen)} (${pct}%)
                                </span>
                            </div>
                        </div>
                    </div>
                    `;
                }
            }).join('');
        }

        this.actualizarTotalesCarrito();
        if (this.metodoPago === 'Combinado') {
            this.calcularBalanceCombinado();
        } else if (this.metodoPago === 'Efectivo') {
            this.calcularCambioEfectivo();
        } else if (this.metodoPago === 'Equipo Garantía') {
            const elTotalGarantia = document.getElementById('resumen-monto-garantia');
            if (elTotalGarantia) elTotalGarantia.textContent = App.formatCurrency(this.obtenerTotalCarrito());
        }
    },

    actualizarTotalesCarrito() {
        const total = this.obtenerTotalCarrito();
        const margen = this.obtenerMargenTotalCarrito();
        const totalCosto = this.carrito.reduce((acc, it) => acc + ((parseFloat(it.costo_unitario) || 0) * (it.cantidad || 1)), 0);
        const pctMargen = totalCosto > 0 ? ((margen / totalCosto) * 100).toFixed(1) : 0;

        const elTotal = document.getElementById('cart-total-cobrar');
        const elMargen = document.getElementById('cart-total-margen');
        const elMargenPct = document.getElementById('cart-total-margen-pct');

        if (elTotal) elTotal.textContent = App.formatCurrency(total);
        if (elMargen) elMargen.textContent = `+${App.formatCurrency(margen)}`;
        if (elMargenPct) elMargenPct.textContent = `(${pctMargen}%)`;

        const elTotalEfectivo = document.getElementById('resumen-monto-efectivo');
        const elTotalTransf = document.getElementById('resumen-monto-transferencia');
        const elTotalGarantia = document.getElementById('resumen-monto-garantia');
        if (elTotalEfectivo) elTotalEfectivo.textContent = App.formatCurrency(total);
        if (elTotalTransf) elTotalTransf.textContent = App.formatCurrency(total);
        if (elTotalGarantia) elTotalGarantia.textContent = App.formatCurrency(total);

        this.actualizarBarraFlotanteMovil();
    },

    actualizarBarraFlotanteMovil() {
        const bar = document.getElementById('pos-floating-bar-mobile');
        const countEl = document.getElementById('mobile-cart-count');
        const totalEl = document.getElementById('mobile-cart-total');
        if (!bar) return;

        const totalItems = this.carrito.reduce((acc, it) => acc + (it.cantidad || 1), 0);
        const totalDinero = this.obtenerTotalCarrito();

        if (totalItems > 0 && App.currentTab === 'pos') {
            if (countEl) countEl.textContent = totalItems;
            if (totalEl) totalEl.textContent = App.formatCurrency(totalDinero);
            bar.classList.remove('hidden');
        } else {
            bar.classList.add('hidden');
        }
    },

    cambiarCatalogoTab(tab) {
        this.catalogoTab = tab;
        const btnEq = document.getElementById('pos-tab-equipos-btn');
        const btnAcc = document.getElementById('pos-tab-accesorios-btn');
        const containerEq = document.getElementById('pos-container-equipos');
        const containerAcc = document.getElementById('pos-container-accesorios');
        const inputSearch = document.getElementById('pos-search-input');

        if (tab === 'equipos') {
            if (btnEq) {
                btnEq.className = "px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-xs transition-all";
            }
            if (btnAcc) {
                btnAcc.className = "px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all";
            }
            if (containerEq) containerEq.classList.remove('hidden');
            if (containerAcc) containerAcc.classList.add('hidden');
            if (inputSearch) inputSearch.placeholder = "🔍 Escribe IMEI o modelo (ej. iPhone 14, 356789...)";
            this.buscarEquipos(inputSearch?.value.trim() || '');
        } else {
            if (btnEq) {
                btnEq.className = "px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all";
            }
            if (btnAcc) {
                btnAcc.className = "px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-xs transition-all";
            }
            if (containerEq) containerEq.classList.add('hidden');
            if (containerAcc) containerAcc.classList.remove('hidden');
            if (inputSearch) inputSearch.placeholder = "🔍 Buscar accesorio, mica, funda, cargador o servicio...";
            this.buscarAccesoriosPOS(inputSearch?.value.trim() || '');
        }
    },

    filtrarAccesoriosRapido(termino) {
        const inputSearch = document.getElementById('pos-search-input');
        if (inputSearch) {
            inputSearch.value = termino;
        }
        this.buscarAccesoriosPOS(termino);
    },

    filtrarCompatibilidad(marca, btn) {
        this.compatibilidadFiltro = marca;
        document.querySelectorAll('.btn-pos-chip').forEach(b => {
            b.classList.remove('bg-blue-600', 'text-white');
            b.classList.add('bg-slate-100', 'text-slate-600');
        });
        if (btn) {
            btn.classList.add('bg-blue-600', 'text-white');
            btn.classList.remove('bg-slate-100', 'text-slate-600');
        }
        const query = document.getElementById('pos-search-input')?.value.trim() || '';
        this.buscarAccesoriosPOS(query);
    },

    async buscarAccesoriosPOS(query = '') {
        const container = document.getElementById('pos-grid-accesorios');
        const emptyState = document.getElementById('pos-accesorios-empty-state');
        if (!container) return;

        try {
            const url = `/api/accesorios?search=${encodeURIComponent(query)}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Error cargando catálogo de accesorios");
            let items = await res.json();

            // Filtrado por compatibilidad de modelo / marca
            if (this.compatibilidadFiltro) {
                const f = this.compatibilidadFiltro.toLowerCase();
                if (f === 'universal') {
                    items = items.filter(acc => {
                        const n = acc.nombre.toLowerCase();
                        return n.includes('universal') || (!n.includes('iphone') && !n.includes('samsung') && !n.includes('xiaomi') && !n.includes('motorola'));
                    });
                } else {
                    items = items.filter(acc => acc.nombre.toLowerCase().includes(f) || acc.categoria.toLowerCase().includes(f));
                }
            }

            if (items.length === 0) {
                container.innerHTML = '';
                if (emptyState) emptyState.classList.remove('hidden');
                return;
            }
            if (emptyState) emptyState.classList.add('hidden');

            container.innerHTML = items.map(acc => {
                const itemEnCarro = this.carrito.find(it => it.tipo === 'accesorio' && it.id === acc.id);
                const stockTxt = acc.es_servicio ? 'Servicio' : `${acc.stock} disponibles`;
                const hermanosConColor = items.filter(x => x.nombre.trim().toLowerCase() === acc.nombre.trim().toLowerCase() && x.color);
                const tieneMasColores = hermanosConColor.length > 1;

                return `
                <div class="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs hover:shadow-sm hover:border-blue-300 transition-all flex flex-col justify-between group">
                    <div>
                        <div class="flex items-center justify-between gap-1 mb-1.5 flex-wrap">
                            <div class="flex items-center gap-1 flex-wrap">
                                <span class="text-[10px] uppercase font-bold text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-100">${App.escapeHtml(acc.categoria)}</span>
                                ${acc.color ? `<span class="text-[10px] uppercase font-bold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-200">🎨 ${App.escapeHtml(acc.color)}</span>` : ''}
                            </div>
                            <span class="text-xs ${acc.stock <= 3 && !acc.es_servicio ? 'text-rose-600 font-bold' : 'text-slate-500 font-medium'}">${stockTxt}</span>
                        </div>
                        <h4 class="font-bold text-slate-800 text-sm group-hover:text-blue-600 transition-colors mb-0.5">${App.escapeHtml(acc.nombre)}</h4>
                        ${acc.codigo_barras ? `<p class="font-mono text-[11px] text-slate-400">SKU: ${App.escapeHtml(acc.codigo_barras)}</p>` : ''}
                        ${tieneMasColores ? `
                        <button type="button" onclick="POS.abrirSelectorColor('${App.escapeHtml(acc.nombre).replace(/'/g, "\\'")}')" class="mt-1 text-[11px] font-bold text-violet-600 hover:text-violet-800 flex items-center gap-1 cursor-pointer">
                            <span>🎨 Ver todos los colores (${hermanosConColor.length})</span>
                        </button>` : ''}
                    </div>

                    <div class="pt-3 border-t border-slate-100 mt-2 flex items-center justify-between gap-2">
                        <div>
                            <span class="text-[10px] text-slate-400 uppercase font-bold block">Precio</span>
                            <span class="text-base font-extrabold text-slate-900">${App.formatCurrency(acc.precio_venta)}</span>
                        </div>
                        <button onclick="POS.agregarAccesorioAlCarrito(${acc.id})" class="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-xs transition-all">
                            <span>+ Agregar</span>
                            ${itemEnCarro ? `<span class="bg-white/25 px-1.5 py-0.2 rounded-full text-[10px]">x${itemEnCarro.cantidad}</span>` : ''}
                        </button>
                    </div>
                </div>
                `;
            }).join('');
        } catch (e) {
            console.error(e);
        }
    },

    iniciarVentaDirecta(equipoId) {
        fetch(`/api/equipos/${equipoId}`)
            .then(res => res.json())
            .then(equipo => {
                App.switchTab('pos');
                this.agregarAlCarrito(equipo);
            })
            .catch(() => {
                App.showToast("No se pudo cargar el equipo.", "error");
            });
    },

    // --- BÚSQUEDA Y CATÁLOGO POS ---

    async buscarEquipos(query) {
        const container = document.getElementById('pos-grid-equipos');
        const emptyState = document.getElementById('pos-empty-state');
        if (!container) return;

        try {
            const url = `/api/pos/buscar${query ? '?q=' + encodeURIComponent(query) : ''}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Error al consultar equipos disponibles");

            const equipos = await res.json();

            if (equipos.length === 0) {
                container.innerHTML = '';
                if (emptyState) emptyState.classList.remove('hidden');
                return;
            }

            if (emptyState) emptyState.classList.add('hidden');

            container.innerHTML = equipos.map(equipo => {
                const enCarrito = this.carrito.some(it => it.tipo === 'equipo' && it.id === equipo.id);

                return `
                <div class="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs hover:shadow-sm hover:border-blue-300 transition-all flex flex-col justify-between group">
                    <div>
                        <div class="flex justify-between items-start gap-1.5 mb-2">
                            <span class="text-[11px] font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-medium select-all">
                                ${App.escapeHtml(equipo.imei)}
                            </span>
                            <div class="flex items-center gap-1">
                                ${App.getGradeBadge(equipo.grado)}
                                ${App.getAgingBadge ? App.getAgingBadge(equipo.estado_antiguedad, equipo.dias_en_stock) : ''}
                            </div>
                        </div>
                        <h4 class="font-bold text-slate-800 text-sm group-hover:text-blue-600 transition-colors">
                            ${App.escapeHtml(equipo.modelo)}
                        </h4>
                        <div class="flex items-center gap-2 text-xs text-slate-500 mt-0.5 mb-3">
                            <span class="font-semibold text-slate-700">${equipo.capacidad_gb} GB</span>
                            <span>•</span>
                            <span>${App.escapeHtml(equipo.color)}</span>
                        </div>
                    </div>

                    <div class="pt-3 border-t border-slate-100 mt-1">
                        <div class="flex justify-between items-baseline mb-2.5">
                            <div>
                                <span class="text-[10px] uppercase font-bold text-slate-400 block">Precio</span>
                                <span class="text-base font-extrabold text-slate-900">${App.formatCurrency(equipo.precio_venta)}</span>
                            </div>
                            <div class="text-right admin-only">
                                <span class="text-[10px] text-slate-400 block">Margen</span>
                                <span class="text-xs font-bold text-emerald-600">+${App.formatCurrency(equipo.precio_venta - equipo.costo_compra)}</span>
                            </div>
                        </div>

                        ${enCarrito ? `
                            <button id="btn-add-cart-${equipo.id}" onclick="POS.quitarDelCarrito(${equipo.id}, 'equipo')" class="w-full bg-emerald-50 text-emerald-700 border border-emerald-300 font-semibold py-2 px-3 rounded-xl flex items-center justify-center gap-1.5 text-xs transition-all">
                                <svg class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                                <span>En Carrito ✓</span>
                            </button>
                        ` : `
                            <button id="btn-add-cart-${equipo.id}" onclick="POS.agregarAlCarrito(${JSON.stringify(equipo).replace(/"/g, '&quot;')})" class="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold py-2 px-3 rounded-xl shadow-xs flex items-center justify-center gap-1.5 text-xs transition-all">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                <span>+ Agregar al Carrito</span>
                            </button>
                        `}
                    </div>
                </div>
                `;
            }).join('');

        } catch (err) {
            container.innerHTML = `<div class="col-span-full text-center text-rose-500 py-6">Error: ${App.escapeHtml(err.message)}</div>`;
        }
    },

    // --- PROCESAR VENTA FINAL ---

    async procesarVenta() {
        if (this.carrito.length === 0) {
            App.showToast("Agrega al menos un artículo (teléfono o accesorio) al carrito.", "error");
            return;
        }

        const clienteNombre = document.getElementById('pos-cliente-nombre').value.trim();
        const clienteTelefono = document.getElementById('pos-cliente-telefono').value.trim();

        if (!clienteNombre || !clienteTelefono) {
            App.showToast("Por favor ingresa el nombre y teléfono del cliente.", "error");
            return;
        }

        const totalVenta = this.obtenerTotalCarrito();

        // Validaciones de pagos
        let mEf = 0.0, mTr = 0.0, mGt = 0.0;

        if (this.metodoPago === 'Efectivo') {
            mEf = totalVenta;
        } else if (this.metodoPago === 'Transferencia') {
            mTr = totalVenta;
        } else if (this.metodoPago === 'Equipo Garantía') {
            mGt = totalVenta;
        } else if (this.metodoPago === 'Combinado') {
            mEf = parseFloat(document.getElementById('pago-monto-efectivo')?.value) || 0;
            mTr = parseFloat(document.getElementById('pago-monto-transferencia')?.value) || 0;
            mGt = parseFloat(document.getElementById('pago-monto-garantia')?.value) || 0;

            const suma = mEf + mTr + mGt;
            if (Math.abs(suma - totalVenta) > 0.05) {
                App.showToast(`En pago combinado, la suma ($${suma.toLocaleString('es-MX', {minimumFractionDigits: 2})}) debe coincidir con el total ($${totalVenta.toLocaleString('es-MX', {minimumFractionDigits: 2})}).`, "error");
                return;
            }
        }

        const btnConfirm = document.getElementById('btn-finalizar-venta-carrito');
        const originalText = btnConfirm.innerHTML;

        try {
            btnConfirm.disabled = true;
            btnConfirm.innerHTML = `
                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg> Registrando Venta...
            `;

            const payload = {
                cliente_nombre: clienteNombre,
                cliente_telefono: clienteTelefono,
                metodo_pago: this.metodoPago,
                monto_efectivo: mEf,
                monto_transferencia: mTr,
                monto_garantia: mGt,
                items: this.carrito.map(it => {
                    if (it.tipo === 'accesorio') {
                        const nombreFinal = it.accesorio.color 
                            ? `${it.accesorio.nombre} (${it.accesorio.color})` 
                            : it.accesorio.nombre;
                        return {
                            tipo_item: 'accesorio',
                            accesorio_id: it.id,
                            nombre_item: nombreFinal,
                            cantidad: it.cantidad,
                            precio_final: it.precio_final
                        };
                    } else {
                        return {
                            tipo_item: 'equipo',
                            equipo_id: it.id,
                            nombre_item: `${it.equipo.modelo} ${it.equipo.capacidad_gb}GB`,
                            cantidad: 1,
                            precio_final: it.precio_final
                        };
                    }
                })
            };

            const res = await fetch('/api/pos/vender', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await res.json();

            if (!res.ok) {
                throw new Error(result.detail || "Error al completar la venta");
            }

            App.showToast(`¡Venta completada con éxito! Folio #${result.id}`, "success");

            // Limpiar formulario y carrito
            this.vaciarCarrito();
            document.getElementById('pos-cliente-nombre').value = '';
            document.getElementById('pos-cliente-telefono').value = '';
            const inputPagaCon = document.getElementById('efectivo-paga-con');
            if (inputPagaCon) inputPagaCon.value = '';

            // Mostrar Recibo / Ticket
            this.mostrarRecibo(result);

            // Refrescar inventario y estadísticas de cabecera
            App.updateHeaderStats();
            if (typeof Accesorios !== 'undefined') Accesorios.cargarAccesorios();

        } catch (err) {
            App.showToast(err.message, "error");
        } finally {
            btnConfirm.disabled = false;
            btnConfirm.innerHTML = originalText;
        }
    },

    // --- NOTA DE VENTA / TICKET TÉRMICO / WHATSAPP ---

    mostrarRecibo(datosVenta) {
        this.reciboActual = datosVenta;

        document.getElementById('recibo-folio').textContent = `FOLIO #${String(datosVenta.id).padStart(5, '0')}`;
        document.getElementById('recibo-fecha').textContent = App.formatDate(datosVenta.fecha_venta);
        document.getElementById('recibo-cliente-nombre').textContent = datosVenta.cliente_nombre;
        document.getElementById('recibo-cliente-telefono').textContent = datosVenta.cliente_telefono;

        const containerItems = document.getElementById('recibo-items-lista');
        const items = datosVenta.items && datosVenta.items.length > 0 ? datosVenta.items : [{
            modelo: datosVenta.modelo,
            capacidad_gb: datosVenta.capacidad_gb,
            color: datosVenta.color,
            imei: datosVenta.imei,
            grado: datosVenta.grado,
            precio_final: datosVenta.precio_final
        }];

        if (containerItems) {
            containerItems.innerHTML = items.map((it, idx) => {
                const esAccesorio = it.tipo_item === 'accesorio' || (!it.imei && it.accesorio_id);

                if (esAccesorio) {
                    return `
                    <div class="py-2 ${idx > 0 ? 'border-t border-slate-100' : ''}">
                        <div class="flex justify-between items-start text-xs">
                            <div class="font-bold text-slate-800">
                                🎧 ${App.escapeHtml(it.nombre_item || it.modelo)} <span class="font-medium text-slate-500">x${it.cantidad || 1}</span>
                            </div>
                            <div class="font-extrabold text-slate-900 ml-2">
                                ${App.formatCurrency(it.precio_final)}
                            </div>
                        </div>
                    </div>
                    `;
                }

                return `
                <div class="py-2.5 ${idx > 0 ? 'border-t border-slate-100' : ''}">
                    <div class="flex justify-between items-start text-xs">
                        <div class="font-bold text-slate-800">
                            📱 ${App.escapeHtml(it.modelo)} <span class="font-normal text-slate-500">(${App.escapeHtml(it.capacidad_gb || '')}GB • ${App.escapeHtml(it.color || '')})</span>
                        </div>
                        <div class="font-extrabold text-slate-900 ml-2">
                            ${App.formatCurrency(it.precio_final)}
                        </div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-slate-500 mt-1">
                        <span class="font-mono bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200 select-all font-semibold">
                            IMEI: ${App.escapeHtml(it.imei || 'N/A')}
                        </span>
                        <div>${it.grado ? App.getGradeBadge(it.grado) : ''}</div>
                    </div>
                </div>
                `;
            }).join('');
        }

        // Totales y Desglose de Pago
        document.getElementById('recibo-precio-total').textContent = App.formatCurrency(datosVenta.precio_final);

        const containerMetodo = document.getElementById('recibo-desglose-pago');
        if (containerMetodo) {
            const mp = datosVenta.metodo_pago;
            if (mp === 'Combinado') {
                containerMetodo.innerHTML = `
                    <div class="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs space-y-1">
                        <div class="font-bold text-slate-700 flex justify-between">
                            <span>Forma de Pago:</span>
                            <span class="text-blue-700">Combinado</span>
                        </div>
                        <div class="border-t border-slate-200 pt-1 space-y-0.5 text-[11px] text-slate-600">
                            ${datosVenta.monto_efectivo > 0 ? `<div class="flex justify-between"><span>• Efectivo:</span><span class="font-bold">${App.formatCurrency(datosVenta.monto_efectivo)}</span></div>` : ''}
                            ${datosVenta.monto_transferencia > 0 ? `<div class="flex justify-between"><span>• Transferencia:</span><span class="font-bold">${App.formatCurrency(datosVenta.monto_transferencia)}</span></div>` : ''}
                            ${datosVenta.monto_garantia > 0 ? `<div class="flex justify-between"><span>• Equipo Garantía:</span><span class="font-bold text-indigo-700">${App.formatCurrency(datosVenta.monto_garantia)}</span></div>` : ''}
                        </div>
                    </div>
                `;
            } else if (mp === 'Equipo Garantía') {
                containerMetodo.innerHTML = `
                    <div class="p-2.5 bg-indigo-50/70 rounded-lg border border-indigo-200 text-xs space-y-0.5">
                        <div class="flex justify-between text-indigo-900 font-bold">
                            <span>Forma de Pago:</span>
                            <span>🛡️ Equipo por Garantía</span>
                        </div>
                        <p class="text-[11px] text-indigo-700">Cubierto 100% por cambio bajo póliza de garantía.</p>
                    </div>
                `;
            } else {
                containerMetodo.innerHTML = `
                    <div class="flex justify-between text-xs py-1">
                        <span class="text-slate-500">Método de Pago:</span>
                        <span class="font-bold text-slate-800">${App.escapeHtml(mp)} (${App.formatCurrency(datosVenta.precio_final)})</span>
                    </div>
                `;
            }
        }

        const garantiaEl = document.getElementById('recibo-garantia-texto');
        if (garantiaEl) {
            garantiaEl.textContent = "Garantía de 30 días válida únicamente con este comprobante original o número registrado. Aplica en placa base y componentes lógicos de fábrica (no cubre humedad, sobrecargas eléctricas, golpes o intervenciones ajenas).";
        }

        const modal = document.getElementById('modal-recibo-venta');
        if (modal) modal.classList.remove('hidden');
    },

    imprimirRecibo() {
        window.print();
    },

    cerrarRecibo() {
        const modal = document.getElementById('modal-recibo-venta');
        if (modal) modal.classList.add('hidden');
        this.reciboActual = null;
    },

    enviarWhatsApp() {
        if (!this.reciboActual) return;
        const v = this.reciboActual;
        const tel = (v.cliente_telefono || '').replace(/\D/g, '');
        if (!tel) {
            App.showToast("El cliente no tiene un teléfono válido registrado.", "error");
            return;
        }

        // Si son 10 dígitos (México), anteponemos el código 52
        const phoneNum = tel.length === 10 ? `52${tel}` : tel;
        const fecha = App.formatDate(v.fecha_venta);
        const folio = String(v.id).padStart(5, '0');

        let itemsTexto = '';
        if (v.items && v.items.length > 0) {
            itemsTexto = v.items.map(it => {
                if (it.tipo_item === 'accesorio' || (!it.imei && it.accesorio_id)) {
                    return `• 🎧 *${it.nombre_item || it.modelo}* x${it.cantidad || 1} - $${(it.precio_final || 0).toLocaleString('es-MX', {minimumFractionDigits: 2})}`;
                } else {
                    return `• 📱 *${it.modelo}* ${it.capacidad_gb || ''}GB (${it.color || ''})
  IMEI: \`${it.imei || 'N/A'}\`
  Precio: $${(it.precio_final || 0).toLocaleString('es-MX', {minimumFractionDigits: 2})}`;
                }
            }).join('\n\n');
        } else {
            itemsTexto = `• 📱 *${v.modelo}* ${v.capacidad_gb || ''}GB (${v.color || ''})
  IMEI: \`${v.imei || 'N/A'}\`
  Precio: $${(v.precio_final || 0).toLocaleString('es-MX', {minimumFractionDigits: 2})}`;
        }

        const mensaje = `¡Hola, *${v.cliente_nombre}*! 👋
Muchas gracias por tu compra en *Mi Inventario Celulares*. Aquí tienes tu comprobante digital y póliza oficial:

📋 *COMPROBANTE DE VENTA*
━━━━━━━━━━━━━━━━━━━━
*Folio:* #${folio}
*Fecha:* ${fecha}
*Forma de Pago:* ${v.metodo_pago}
*Total Pagado:* $${(v.precio_final || 0).toLocaleString('es-MX', {minimumFractionDigits: 2})}

🛒 *DETALLE DE ARTÍCULOS:*
${itemsTexto}

🛡️ *PÓLIZA DE GARANTÍA (30 DÍAS):*
Garantía de 30 días válida presentando este comprobante o tu número registrado. Aplica directamente en placa base y funcionamiento de fábrica. No aplica en daños por humedad, golpes o intervención ajena.

¡Estamos a tus órdenes para lo que necesites! 🚀`;

        const url = `https://wa.me/${phoneNum}?text=${encodeURIComponent(mensaje)}`;
        window.open(url, '_blank');
    },

    // --- ESCÁNER DE CÓDIGOS DE BARRA / QR (PISTOLA USB O TECLADO) ---

    setupBarcodeScanner() {
        let barcodeBuffer = '';
        let lastKeyTime = Date.now();

        window.addEventListener('keydown', (e) => {
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
            const activeId = document.activeElement ? document.activeElement.id : '';

            // Si está escribiendo en otro input que NO sea el de búsqueda POS, no interceptar
            if (activeTag === 'input' && activeId !== 'pos-search-input') {
                return;
            }
            if (activeTag === 'textarea' || activeTag === 'select') {
                return;
            }

            const currentTime = Date.now();
            // Las pistolas de código de barras disparan las teclas en menos de 100ms
            if (currentTime - lastKeyTime > 120) {
                barcodeBuffer = '';
            }
            lastKeyTime = currentTime;

            if (e.key === 'Enter') {
                if (barcodeBuffer.length >= 4) {
                    e.preventDefault();
                    this.procesarCodigoEscaneado(barcodeBuffer);
                    barcodeBuffer = '';
                }
            } else if (e.key.length === 1) {
                barcodeBuffer += e.key;
            }
        });
    },

    async procesarCodigoEscaneado(codigo) {
        codigo = (codigo || '').trim();
        if (!codigo) return;

        try {
            // 1. Intentar buscar en teléfonos disponibles (IMEI o modelo)
            const resEq = await fetch(`/api/pos/buscar?q=${encodeURIComponent(codigo)}`);
            if (resEq.ok) {
                const equipos = await resEq.json();
                const exacto = equipos.find(eq => eq.imei.toLowerCase() === codigo.toLowerCase() || eq.modelo.toLowerCase() === codigo.toLowerCase());
                if (exacto) {
                    this.agregarAlCarrito(exacto);
                    App.showToast(`Escaneado: ${exacto.modelo} (${exacto.imei})`, "success");
                    return;
                } else if (equipos.length === 1) {
                    this.agregarAlCarrito(equipos[0]);
                    App.showToast(`Escaneado: ${equipos[0].modelo}`, "success");
                    return;
                }
            }

            // 2. Intentar buscar en accesorios por código de barras o nombre
            const resAcc = await fetch(`/api/accesorios?q=${encodeURIComponent(codigo)}`);
            if (resAcc.ok) {
                const accesorios = await resAcc.json();
                const exactoAcc = accesorios.find(a => (a.codigo_barras && a.codigo_barras.toLowerCase() === codigo.toLowerCase()) || a.nombre.toLowerCase().includes(codigo.toLowerCase()));
                if (exactoAcc) {
                    this.agregarAccesorioAlCarrito(exactoAcc);
                    return;
                } else if (accesorios.length === 1) {
                    this.agregarAccesorioAlCarrito(accesorios[0]);
                    return;
                }
            }

            App.showToast(`No se encontró producto con código "${codigo}".`, "warning");
        } catch (e) {
            console.error("Error al procesar escáner:", e);
        }
    },

    // --- SELECTOR DE COLOR PARA ACCESORIOS CON VARIANTES ---
    async abrirSelectorColor(nombreBase) {
        try {
            let variantes = [];
            if (typeof Accesorios !== 'undefined' && Accesorios.items && Accesorios.items.length > 0) {
                variantes = Accesorios.items.filter(x => x.nombre.trim().toLowerCase() === nombreBase.trim().toLowerCase());
            }
            if (variantes.length === 0) {
                const res = await fetch(`/api/accesorios?search=${encodeURIComponent(nombreBase)}`);
                if (res.ok) {
                    const todos = await res.json();
                    variantes = todos.filter(x => x.nombre.trim().toLowerCase() === nombreBase.trim().toLowerCase());
                }
            }

            if (variantes.length <= 1) {
                if (variantes.length === 1) this.agregarAccesorioAlCarrito(variantes[0]);
                return;
            }

            const titulo = document.getElementById('modal-color-acc-titulo');
            const grid = document.getElementById('modal-color-acc-grid');
            const modal = document.getElementById('modal-seleccionar-color-acc');
            if (!modal || !grid) return;

            if (titulo) titulo.textContent = nombreBase;

            grid.innerHTML = variantes.map(v => {
                const sinStock = v.stock <= 0 && !v.es_servicio;
                const colorLabel = v.color || 'Estándar';
                const stockLabel = v.es_servicio ? 'Servicio' : `${v.stock} disp.`;
                const badgeClass = sinStock 
                    ? 'bg-rose-50 text-rose-700 border-rose-200' 
                    : (v.stock < 3 ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200');

                return `
                <button type="button" 
                    onclick="POS.seleccionarColorVariante(${v.id})"
                    class="p-3 rounded-xl border border-slate-200 hover:border-violet-500 hover:bg-violet-50/50 transition-all flex items-center justify-between text-left group cursor-pointer ${sinStock ? 'opacity-70 bg-slate-50' : 'bg-white shadow-2xs'}">
                    <div class="flex items-center gap-2.5 min-w-0">
                        <span class="w-3.5 h-3.5 rounded-full border border-slate-300 shadow-2xs flex-shrink-0" style="background-color: ${POS.obtenerHexColor(colorLabel)};"></span>
                        <div class="min-w-0">
                            <span class="block font-bold text-slate-800 text-xs truncate group-hover:text-violet-700">🎨 ${App.escapeHtml(colorLabel)}</span>
                            <span class="text-[10px] text-slate-500 font-medium">${App.formatCurrency(v.precio_venta)}</span>
                        </div>
                    </div>
                    <span class="px-2 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass} flex-shrink-0">
                        ${stockLabel}
                    </span>
                </button>
                `;
            }).join('');

            modal.classList.remove('hidden');
        } catch (e) {
            console.error("Error abriendo selector de color:", e);
        }
    },

    cerrarSelectorColor() {
        const modal = document.getElementById('modal-seleccionar-color-acc');
        if (modal) modal.classList.add('hidden');
    },

    seleccionarColorVariante(id) {
        this.cerrarSelectorColor();
        this.agregarAccesorioAlCarrito(id);
    },

    obtenerHexColor(nombreColor) {
        if (!nombreColor) return '#94a3b8';
        const n = nombreColor.toLowerCase();
        if (n.includes('rosa')) return '#f472b6';
        if (n.includes('negro')) return '#1e293b';
        if (n.includes('blanco')) return '#f8fafc';
        if (n.includes('azul')) return '#38bdf8';
        if (n.includes('verde')) return '#4ade80';
        if (n.includes('lila') || n.includes('lavanda') || n.includes('morado')) return '#c084fc';
        if (n.includes('crema') || n.includes('beige')) return '#fef08a';
        if (n.includes('rojo')) return '#f87171';
        if (n.includes('gris') || n.includes('plata')) return '#cbd5e1';
        if (n.includes('dorado') || n.includes('oro')) return '#fde047';
        if (n.includes('naranja')) return '#fb923c';
        return '#8b5cf6';
    }
};

window.POS = POS;
