// inventario.js - Módulo de Inventario

const Inventario = {
    equipos: [],
    filtroGrado: '',
    filtroBusqueda: '',

    init() {
        this.setupFormListeners();
        this.setupFilterListeners();
        this.setupExcelImportListeners();
        this.cargarEquipos();
    },

    setupFormListeners() {
        const form = document.getElementById('form-nuevo-equipo');
        const inputCosto = document.getElementById('input-costo-compra');
        const inputPrecio = document.getElementById('input-precio-venta');

        // Cálculo automático en tiempo real del margen proyectado (Solo visible para Modo Dueño)
        const calcularMargen = () => {
            const boxMargen = document.getElementById('box-margen-proyectado');
            if (!boxMargen) return;

            if (!App.isAdmin) {
                boxMargen.classList.add('hidden');
                return;
            }

            const costo = parseFloat(inputCosto.value) || 0;
            const precio = parseFloat(inputPrecio.value) || 0;
            const margen = precio - costo;
            const porcentaje = costo > 0 ? ((margen / costo) * 100).toFixed(1) : 0;

            const txtMargen = document.getElementById('txt-margen-proyectado');
            const txtPorcentaje = document.getElementById('txt-porcentaje-margen');

            if (costo > 0 || precio > 0) {
                boxMargen.classList.remove('hidden');
                txtMargen.textContent = App.formatCurrency(margen);
                txtPorcentaje.textContent = `${porcentaje}%`;

                if (margen > 0) {
                    boxMargen.className = 'admin-only mt-3 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 transition-all';
                    txtMargen.className = 'font-bold text-emerald-700 text-lg';
                } else if (margen === 0) {
                    boxMargen.className = 'admin-only mt-3 p-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-900 transition-all';
                    txtMargen.className = 'font-bold text-slate-700 text-lg';
                } else {
                    boxMargen.className = 'admin-only mt-3 p-3 rounded-xl border border-rose-200 bg-rose-50 text-rose-900 transition-all';
                    txtMargen.className = 'font-bold text-rose-700 text-lg';
                }
            } else {
                boxMargen.classList.add('hidden');
            }
        };

        if (inputCosto && inputPrecio) {
            inputCosto.addEventListener('input', calcularMargen);
            inputPrecio.addEventListener('input', calcularMargen);
        }

        // Envío del formulario manual
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.guardarEquipo();
            });
        }
    },

    setupFilterListeners() {
        const searchInput = document.getElementById('search-inventario');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filtroBusqueda = e.target.value.trim();
                this.filtrarYRenderizar();
            });
        }

        const gradePills = document.querySelectorAll('.grade-filter-pill');
        gradePills.forEach(pill => {
            pill.addEventListener('click', () => {
                gradePills.forEach(p => p.classList.remove('bg-blue-600', 'text-white'));
                gradePills.forEach(p => p.classList.add('bg-slate-100', 'text-slate-700'));

                pill.classList.remove('bg-slate-100', 'text-slate-700');
                pill.classList.add('bg-blue-600', 'text-white');

                this.filtroGrado = pill.dataset.grado || '';
                this.filtrarYRenderizar();
            });
        });
    },

    setupExcelImportListeners() {
        const inputExcel = document.getElementById('input-archivo-excel');
        const dropZone = document.getElementById('dropzone-excel');

        if (inputExcel) {
            inputExcel.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) this.procesarSubidaExcel(file);
            });
        }

        if (dropZone) {
            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    dropZone.classList.add('border-blue-500', 'bg-blue-50/50');
                });
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    dropZone.classList.remove('border-blue-500', 'bg-blue-50/50');
                });
            });

            dropZone.addEventListener('drop', (e) => {
                const file = e.dataTransfer.files[0];
                if (file) this.procesarSubidaExcel(file);
            });
        }
    },

    abrirModalExcel() {
        const modal = document.getElementById('modal-importar-excel');
        const resultados = document.getElementById('resultado-importacion-excel');
        if (resultados) resultados.classList.add('hidden');
        if (modal) modal.classList.remove('hidden');
    },

    cerrarModalExcel() {
        const modal = document.getElementById('modal-importar-excel');
        const input = document.getElementById('input-archivo-excel');
        if (input) input.value = '';
        if (modal) modal.classList.add('hidden');
    },

    async procesarSubidaExcel(file) {
        const statusBox = document.getElementById('excel-loading-status');
        const resultBox = document.getElementById('resultado-importacion-excel');

        if (statusBox) statusBox.classList.remove('hidden');
        if (resultBox) resultBox.classList.add('hidden');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/equipos/importar-excel', {
                method: 'POST',
                body: formData
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Error al procesar el archivo Excel.");
            }

            if (statusBox) statusBox.classList.add('hidden');
            if (resultBox) {
                resultBox.classList.remove('hidden');
                
                let html = `
                    <div class="p-3.5 bg-emerald-50 rounded-xl border border-emerald-200 text-emerald-900 mb-3">
                        <div class="font-bold flex items-center gap-1.5 text-sm">
                            <svg class="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                            ${data.mensaje}
                        </div>
                        <p class="text-xs text-emerald-700 mt-1">Se agregaron ${data.importados_count} teléfonos al inventario disponible.</p>
                    </div>
                `;

                if (data.errores && data.errores.length > 0) {
                    html += `
                        <div class="p-3 bg-amber-50 rounded-xl border border-amber-200 text-amber-900 text-xs space-y-1 max-h-36 overflow-y-auto">
                            <div class="font-bold uppercase tracking-wider text-[11px] text-amber-800">Filas omitidas o con advertencias (${data.errores.length}):</div>
                            ${data.errores.map(err => `<div>• ${err}</div>`).join('')}
                        </div>
                    `;
                }

                resultBox.innerHTML = html;
            }

            App.showToast(`Importación completada: ${data.importados_count} teléfonos añadidos`, "success");
            await this.cargarEquipos();
            App.updateHeaderStats();

        } catch (err) {
            if (statusBox) statusBox.classList.add('hidden');
            App.showToast(err.message, "error");
        }
    },

    async guardarEquipo() {
        const btnSubmit = document.getElementById('btn-guardar-equipo');
        const originalText = btnSubmit.innerHTML;

        try {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = `
                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg> Registrando...
            `;

            const data = {
                modelo: document.getElementById('input-modelo').value.trim(),
                capacidad_gb: parseInt(document.getElementById('input-capacidad').value, 10),
                color: document.getElementById('input-color').value.trim(),
                imei: document.getElementById('input-imei').value.trim(),
                grado: document.getElementById('input-grado').value,
                costo_compra: parseFloat(document.getElementById('input-costo-compra').value),
                precio_venta: parseFloat(document.getElementById('input-precio-venta').value),
            };

            const res = await fetch('/api/equipos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await res.json();

            if (!res.ok) {
                throw new Error(result.detail || 'Error al guardar el equipo');
            }

            App.showToast(`Equipo "${result.modelo}" (${result.imei}) registrado con éxito`, 'success');
            
            // Limpiar formulario
            document.getElementById('form-nuevo-equipo').reset();
            document.getElementById('box-margen-proyectado').classList.add('hidden');

            await this.cargarEquipos();
            App.updateHeaderStats();

        } catch (error) {
            App.showToast(error.message, 'error');
        } finally {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = originalText;
        }
    },

    async cargarEquipos() {
        const tableBody = document.getElementById('tbody-inventario');
        if (!tableBody) return;

        try {
            const res = await fetch('/api/equipos?solo_disponibles=true');
            if (res.ok) {
                this.equipos = await res.json();
                this.filtrarYRenderizar();
                this.actualizarResumenInventario();
            } else {
                throw new Error("No se pudo obtener el inventario.");
            }
        } catch (err) {
            tableBody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-rose-500">Error al cargar inventario: ${err.message}</td></tr>`;
        }
    },

    filtroAntiguedad: '',

    filtrarYRenderizar() {
        let filtrados = this.equipos;

        if (this.filtroGrado) {
            filtrados = filtrados.filter(e => e.grado.toUpperCase() === this.filtroGrado.toUpperCase());
        }

        if (this.filtroAntiguedad) {
            filtrados = filtrados.filter(e => e.estado_antiguedad === this.filtroAntiguedad);
        }

        if (this.filtroBusqueda) {
            const term = this.filtroBusqueda.toLowerCase();
            filtrados = filtrados.filter(e => 
                e.modelo.toLowerCase().includes(term) ||
                e.imei.toLowerCase().includes(term) ||
                e.color.toLowerCase().includes(term)
            );
        }

        this.renderTabla(filtrados);
    },

    filtrarPorAntiguedad(antiguedad) {
        this.filtroAntiguedad = antiguedad;
        this.filtrarYRenderizar();
    },

    actualizarResumenInventario() {
        const totalItems = this.equipos.length;
        const totalCosto = this.equipos.reduce((acc, curr) => acc + curr.costo_compra, 0);
        const totalVenta = this.equipos.reduce((acc, curr) => acc + curr.precio_venta, 0);
        const gananciaPotencial = totalVenta - totalCosto;

        const countEl = document.getElementById('stat-inv-disponibles');
        const costoEl = document.getElementById('stat-inv-capital');
        const gananciaEl = document.getElementById('stat-inv-ganancia-potencial');

        if (countEl) countEl.textContent = `${totalItems} equipos`;
        if (costoEl) costoEl.textContent = App.formatCurrency(totalCosto);
        if (gananciaEl) gananciaEl.textContent = App.formatCurrency(gananciaPotencial);
    },

    renderTabla(lista) {
        const tableBody = document.getElementById('tbody-inventario');
        const emptyState = document.getElementById('inventario-empty-state');
        if (!tableBody) return;

        if (lista.length === 0) {
            tableBody.innerHTML = '';
            if (emptyState) emptyState.classList.remove('hidden');
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');

        tableBody.innerHTML = lista.map(equipo => {
            const margen = equipo.margen_proyectado || (equipo.precio_venta - equipo.costo_compra);
            const pct = equipo.porcentaje_margen || ((margen / equipo.costo_compra) * 100).toFixed(1);
            const agingBadge = App.getAgingBadge(equipo.dias_en_stock || 0, equipo.estado_antiguedad || 'Fresco');

            return `
            <tr class="hover:bg-slate-50 border-b border-slate-100 transition-colors">
                <td class="py-3 px-4 font-semibold text-slate-800">
                    <div class="flex items-center space-x-2">
                        <span class="p-1.5 bg-blue-50 text-blue-600 rounded-lg">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                        </span>
                        <div>
                            <div class="flex items-center gap-1.5">
                                <span>${equipo.modelo}</span>
                                ${agingBadge}
                            </div>
                            <span class="text-xs text-slate-400 font-normal">${equipo.capacidad_gb} GB</span>
                        </div>
                    </div>
                </td>
                <td class="py-3 px-4 text-slate-600">
                    <span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5 bg-slate-400"></span>
                    ${equipo.color}
                </td>
                <td class="py-3 px-4">
                    <span class="font-mono text-xs text-slate-700 bg-slate-100 px-2 py-1 rounded select-all font-medium">
                        ${equipo.imei}
                    </span>
                </td>
                <td class="py-3 px-4">
                    ${App.getGradeBadge(equipo.grado)}
                </td>
                <td class="py-3 px-4 text-slate-600 admin-only">
                    ${App.formatCurrency(equipo.costo_compra)}
                </td>
                <td class="py-3 px-4 font-bold text-slate-800">
                    ${App.formatCurrency(equipo.precio_venta)}
                </td>
                <td class="py-3 px-4 admin-only">
                    <span class="text-emerald-700 font-semibold text-sm">
                        +${App.formatCurrency(margen)}
                    </span>
                    <span class="text-xs text-emerald-600 block">(${pct}%)</span>
                </td>
                <td class="py-3 px-4 text-right space-x-1 whitespace-nowrap">
                    <button onclick="POS.iniciarVentaDirecta(${equipo.id})" class="inline-flex items-center px-2.5 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-all" title="Vender este equipo en POS">
                        <svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                        Vender
                    </button>
                    <button onclick="Etiquetas.abrirParaEquipo(${equipo.id})" class="inline-flex items-center p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="Generar e Imprimir Etiqueta">
                        🏷️
                    </button>
                    <button onclick="Garantias.consultarHistorialIMEI('${equipo.imei}')" class="inline-flex items-center p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Ver Historial Universal 360°">
                        📋
                    </button>
                    <button onclick="Inventario.eliminarEquipo(${equipo.id}, '${equipo.modelo}')" class="inline-flex items-center p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors admin-only" title="Eliminar equipo">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                </td>
            </tr>
            `;
        }).join('');
    },

    equipoAEliminar: null,

    eliminarEquipo(id, modelo) {
        this.equipoAEliminar = { id, modelo };
        const modal = document.getElementById('modal-confirmar-eliminar');
        const txtModelo = document.getElementById('delete-modal-modelo');
        const inputPwd = document.getElementById('delete-admin-password');
        const errBox = document.getElementById('delete-password-error');

        // Si el navegador tiene en caché una versión sin el modal, pedir contraseña con prompt obligatorio
        if (!modal) {
            const pwd = prompt(`[Seguridad] Autorización requerida.\nIngresa la contraseña de administrador para eliminar "${modelo}":`);
            if (!pwd) return;
            this.enviarEliminacionDirecta(id, modelo, pwd);
            return;
        }

        if (txtModelo) txtModelo.textContent = `"${modelo}"`;
        if (inputPwd) inputPwd.value = '';
        if (errBox) errBox.classList.add('hidden');
        modal.classList.remove('hidden');

        if (inputPwd) {
            setTimeout(() => inputPwd.focus(), 150);
        }
    },

    async enviarEliminacionDirecta(id, modelo, password) {
        try {
            const res = await fetch(`/api/equipos/${id}?password=${encodeURIComponent(password)}`, {
                method: 'DELETE',
                headers: { 'X-Admin-Password': password }
            });
            const data = await res.json();
            if (res.status === 401) {
                App.showToast("Contraseña incorrecta. No se eliminó el artículo.", "error");
                return;
            }
            if (!res.ok) {
                throw new Error(data.detail || 'No se pudo eliminar el equipo.');
            }
            App.showToast(`Equipo "${modelo}" eliminado exitosamente`, 'info');
            await this.cargarEquipos();
            App.updateHeaderStats();
        } catch (e) {
            App.showToast(e.message, 'error');
        }
    },

    cerrarModalEliminar() {
        const modal = document.getElementById('modal-confirmar-eliminar');
        if (modal) modal.classList.add('hidden');
        this.equipoAEliminar = null;
    },

    togglePasswordVisibility() {
        const input = document.getElementById('delete-admin-password');
        const txt = document.getElementById('txt-toggle-pwd');
        if (input) {
            if (input.type === 'password') {
                input.type = 'text';
                if (txt) txt.textContent = '🔒';
            } else {
                input.type = 'password';
                if (txt) txt.textContent = '👁️';
            }
        }
    },

    async ejecutarEliminacion() {
        if (!this.equipoAEliminar) return;

        const inputPwd = document.getElementById('delete-admin-password');
        const errBox = document.getElementById('delete-password-error');
        const btnSubmit = document.getElementById('btn-confirmar-eliminar-submit');
        const password = inputPwd ? inputPwd.value : '';

        if (!password) {
            if (errBox) {
                errBox.textContent = "Por favor ingresa la contraseña de autorización.";
                errBox.classList.remove('hidden');
            }
            return;
        }

        const originalText = btnSubmit.innerHTML;

        try {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = `
                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg> Verificando...
            `;

            const id = this.equipoAEliminar.id;
            const res = await fetch(`/api/equipos/${id}?password=${encodeURIComponent(password)}`, {
                method: 'DELETE',
                headers: {
                    'X-Admin-Password': password
                }
            });

            const data = await res.json();

            if (res.status === 401) {
                if (errBox) {
                    errBox.innerHTML = `
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        <span>Contraseña de administrador incorrecta.</span>
                    `;
                    errBox.classList.remove('hidden');
                }
                inputPwd.select();
                return;
            }

            if (!res.ok) {
                throw new Error(data.detail || 'No se pudo eliminar el equipo.');
            }

            App.showToast(`Equipo "${this.equipoAEliminar.modelo}" eliminado exitosamente`, 'info');
            this.cerrarModalEliminar();
            await this.cargarEquipos();
            App.updateHeaderStats();

        } catch (err) {
            App.showToast(err.message, 'error');
        } finally {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = originalText;
        }
    }
};
