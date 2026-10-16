// pos.js - Módulo de Punto de Venta (POS) con Carrito Múltiple, Pagos y Equipo Garantía

const POS = {
    debounceTimer: null,
    carrito: [], // Array de { equipo, precio_final }
    metodoPago: 'Efectivo', // 'Efectivo', 'Transferencia', 'Combinado', 'Equipo Garantía'
    reciboActual: null,

    init() {
        this.setupSearch();
        this.setupPhoneLookup();
        this.setupPaymentMethodListeners();
        this.setupCartListeners();
        this.renderCarrito();
    },

    setupSearch() {
        const searchInput = document.getElementById('pos-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                clearTimeout(this.debounceTimer);
                const query = e.target.value.trim();
                this.debounceTimer = setTimeout(() => {
                    this.buscarEquipos(query);
                }, 200);
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
                                    badgeCliente.textContent = "Cliente registrado";
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
            const costo = parseFloat(item.equipo.costo_compra) || 0;
            return acc + (precio - costo);
        }, 0);
    },

    // --- GESTIÓN DEL CARRITO ---

    agregarAlCarrito(equipo) {
        const existe = this.carrito.some(it => it.equipo.id === equipo.id);
        if (existe) {
            App.showToast(`"${equipo.modelo}" (IMEI: ${equipo.imei}) ya está en el carrito.`, "info");
            return;
        }

        this.carrito.push({
            equipo: equipo,
            precio_final: equipo.precio_venta
        });

        App.showToast(`Agregado al carrito: ${equipo.modelo}`, "success");
        this.renderCarrito();
        this.actualizarBotonCatalogo(equipo.id, true);
    },

    quitarDelCarrito(equipoId) {
        this.carrito = this.carrito.filter(it => it.equipo.id !== equipoId);
        this.renderCarrito();
        this.actualizarBotonCatalogo(equipoId, false);
    },

    actualizarPrecioItem(equipoId, nuevoPrecio) {
        const item = this.carrito.find(it => it.equipo.id === equipoId);
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

        const totalItems = this.carrito.length;
        if (badgeCount) badgeCount.textContent = `${totalItems} ${totalItems === 1 ? 'equipo' : 'equipos'}`;

        if (totalItems === 0) {
            if (emptyState) emptyState.classList.remove('hidden');
            if (cartContent) cartContent.classList.add('hidden');
            if (container) container.innerHTML = '';
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');
        if (cartContent) cartContent.classList.remove('hidden');

        if (container) {
            container.innerHTML = this.carrito.map((item) => {
                const eq = item.equipo;
                const margen = item.precio_final - eq.costo_compra;
                const pct = eq.costo_compra > 0 ? ((margen / eq.costo_compra) * 100).toFixed(1) : 0;

                return `
                <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs hover:border-slate-300 transition-all space-y-2">
                    <div class="flex justify-between items-start gap-2">
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-1.5">
                                <h5 class="font-bold text-slate-800 text-sm truncate">${eq.modelo}</h5>
                                <span class="text-[11px] bg-slate-100 text-slate-600 px-1.5 py-0.2 rounded font-medium">${eq.capacidad_gb}GB</span>
                            </div>
                            <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                                <span>${eq.color}</span>
                                <span>•</span>
                                <span class="font-mono text-[11px] text-slate-600">IMEI: ${eq.imei}</span>
                            </div>
                        </div>
                        <div class="flex items-center gap-1">
                            ${App.getGradeBadge(eq.grado)}
                            <button type="button" onclick="POS.quitarDelCarrito(${eq.id})" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors" title="Quitar este equipo">
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
                                    onchange="POS.actualizarPrecioItem(${eq.id}, this.value)"
                                    oninput="POS.actualizarPrecioItem(${eq.id}, this.value)"
                                    class="w-full pl-5 pr-2 py-1 text-xs font-bold text-slate-800 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-blue-500 focus:outline-none">
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="text-[10px] text-slate-400 block">Margen:</span>
                            <span class="text-xs font-bold ${margen >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                                +${App.formatCurrency(margen)} (${pct}%)
                            </span>
                        </div>
                    </div>
                </div>
                `;
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
        const totalCosto = this.carrito.reduce((acc, it) => acc + it.equipo.costo_compra, 0);
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

    // --- BÚSQUEDA Y CATÁLOGO ---

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
                const enCarrito = this.carrito.some(it => it.equipo.id === equipo.id);

                return `
                <div class="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs hover:shadow-sm hover:border-blue-300 transition-all flex flex-col justify-between group">
                    <div>
                        <div class="flex justify-between items-start gap-1.5 mb-2">
                            <span class="text-[11px] font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-medium select-all">
                                ${equipo.imei}
                            </span>
                            ${App.getGradeBadge(equipo.grado)}
                        </div>
                        <h4 class="font-bold text-slate-800 text-sm group-hover:text-blue-600 transition-colors">
                            ${equipo.modelo}
                        </h4>
                        <div class="flex items-center gap-2 text-xs text-slate-500 mt-0.5 mb-3">
                            <span class="font-semibold text-slate-700">${equipo.capacidad_gb} GB</span>
                            <span>•</span>
                            <span>${equipo.color}</span>
                        </div>
                    </div>

                    <div class="pt-3 border-t border-slate-100 mt-1">
                        <div class="flex justify-between items-baseline mb-2.5">
                            <div>
                                <span class="text-[10px] uppercase font-bold text-slate-400 block">Precio</span>
                                <span class="text-base font-extrabold text-slate-900">${App.formatCurrency(equipo.precio_venta)}</span>
                            </div>
                            <div class="text-right">
                                <span class="text-[10px] text-slate-400 block">Margen</span>
                                <span class="text-xs font-bold text-emerald-600">+${App.formatCurrency(equipo.precio_venta - equipo.costo_compra)}</span>
                            </div>
                        </div>

                        ${enCarrito ? `
                            <button id="btn-add-cart-${equipo.id}" onclick="POS.quitarDelCarrito(${equipo.id})" class="w-full bg-emerald-50 text-emerald-700 border border-emerald-300 font-semibold py-2 px-3 rounded-xl flex items-center justify-center gap-1.5 text-xs transition-all">
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
            container.innerHTML = `<div class="col-span-full text-center text-rose-500 py-6">Error: ${err.message}</div>`;
        }
    },

    // --- PROCESAR VENTA FINAL ---

    async procesarVenta() {
        if (this.carrito.length === 0) {
            App.showToast("Agrega al menos un teléfono al carrito antes de cobrar.", "error");
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
                App.showToast(`En pago combinado, la suma ($${suma.toLocaleString('es-MX', {minimumFractionDigits: 2})}) debe coincidir exactamente con el total ($${totalVenta.toLocaleString('es-MX', {minimumFractionDigits: 2})}).`, "error");
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
                items: this.carrito.map(it => ({
                    equipo_id: it.equipo.id,
                    precio_final: it.precio_final
                }))
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

            // Mostrar Nota de Venta / Recibo con todos los equipos
            this.mostrarRecibo(result);

            // Refrescar inventario y estadísticas de cabecera
            App.updateHeaderStats();

        } catch (err) {
            App.showToast(err.message, "error");
        } finally {
            btnConfirm.disabled = false;
            btnConfirm.innerHTML = originalText;
        }
    },

    // --- NOTA DE VENTA / RECIBO ---

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
            containerItems.innerHTML = items.map((it, idx) => `
                <div class="py-2.5 ${idx > 0 ? 'border-t border-slate-100' : ''}">
                    <div class="flex justify-between items-start text-xs">
                        <div class="font-bold text-slate-800">
                            ${it.modelo} <span class="font-normal text-slate-500">(${it.capacidad_gb}GB • ${it.color})</span>
                        </div>
                        <div class="font-extrabold text-slate-900 ml-2">
                            ${App.formatCurrency(it.precio_final)}
                        </div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-slate-500 mt-1">
                        <span class="font-mono bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200 select-all font-semibold">
                            IMEI: ${it.imei}
                        </span>
                        <div>${App.getGradeBadge(it.grado)}</div>
                    </div>
                </div>
            `).join('');
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
                        <p class="text-[11px] text-indigo-700">Cubierto 100% por cambio de equipo bajo póliza de garantía.</p>
                    </div>
                `;
            } else {
                containerMetodo.innerHTML = `
                    <div class="flex justify-between text-xs py-1">
                        <span class="text-slate-500">Método de Pago:</span>
                        <span class="font-bold text-slate-800">${mp} (${App.formatCurrency(datosVenta.precio_final)})</span>
                    </div>
                `;
            }
        }

        const garantiaEl = document.getElementById('recibo-garantia-texto');
        if (garantiaEl) {
            garantiaEl.textContent = "Garantía válida únicamente con este comprobante original. Aplica en funcionamiento de placa base y componentes lógicos (no aplica en equipos mojados, sobrecargados, golpeados o intervenidos por terceros).";
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
    }
};
