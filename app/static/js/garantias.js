// garantias.js - Módulo de Devoluciones y Reclamos por Garantía

const Garantias = {
    equipoEncontrado: null,

    init() {
        this.setupListeners();
    },

    setupListeners() {
        const btnConsultar = document.getElementById('btn-consultar-garantia-imei');
        const inputImei = document.getElementById('garantia-buscar-imei');

        if (btnConsultar && inputImei) {
            btnConsultar.addEventListener('click', () => {
                const imei = inputImei.value.trim();
                if (imei) this.consultarImei(imei);
            });

            inputImei.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const imei = inputImei.value.trim();
                    if (imei) this.consultarImei(imei);
                }
            });
        }

        const formDevolucion = document.getElementById('form-procesar-garantia');
        if (formDevolucion) {
            formDevolucion.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.procesarDevolucion();
            });
        }
    },

    abrirModal(imeiPredefinido = '') {
        const modal = document.getElementById('modal-devolucion-garantia');
        const inputImei = document.getElementById('garantia-buscar-imei');
        const boxDetalles = document.getElementById('garantia-detalles-venta');
        
        if (boxDetalles) boxDetalles.classList.add('hidden');
        this.equipoEncontrado = null;

        if (inputImei) {
            inputImei.value = imeiPredefinido;
            if (imeiPredefinido) {
                setTimeout(() => this.consultarImei(imeiPredefinido), 100);
            }
        }

        if (modal) modal.classList.remove('hidden');
    },

    cerrarModal() {
        const modal = document.getElementById('modal-devolucion-garantia');
        if (modal) modal.classList.add('hidden');
        this.equipoEncontrado = null;
    },

    async consultarImei(imei) {
        const btn = document.getElementById('btn-consultar-garantia-imei');
        const boxDetalles = document.getElementById('garantia-detalles-venta');
        const loading = document.getElementById('garantia-loading');

        try {
            if (btn) btn.disabled = true;
            if (loading) loading.classList.remove('hidden');
            if (boxDetalles) boxDetalles.classList.add('hidden');

            const res = await fetch(`/api/garantias/verificar-imei?imei=${encodeURIComponent(imei)}`);
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "No se encontró el equipo vendido.");
            }

            this.equipoEncontrado = data;

            // Renderizar datos del equipo vendido
            document.getElementById('garantia-info-modelo').textContent = `${data.equipo.modelo} (${data.equipo.capacidad_gb}GB • ${data.equipo.color})`;
            document.getElementById('garantia-info-imei').textContent = data.equipo.imei;
            document.getElementById('garantia-info-grado').innerHTML = App.getGradeBadge(data.equipo.grado);
            document.getElementById('garantia-info-cliente').textContent = `${data.venta.cliente_nombre} (${data.venta.cliente_telefono})`;
            document.getElementById('garantia-info-fecha-venta').textContent = App.formatDate(data.venta.fecha_venta);
            document.getElementById('garantia-info-precio').textContent = App.formatCurrency(data.venta.precio_final);

            // Estado de vigencia de garantía
            const badgeVigencia = document.getElementById('garantia-badge-vigencia');
            const txtDias = document.getElementById('garantia-dias-info');

            if (data.dentro_garantia) {
                badgeVigencia.textContent = "✓ Dentro del periodo de garantía";
                badgeVigencia.className = "px-3 py-1 text-xs font-bold rounded-lg bg-emerald-100 text-emerald-800 border border-emerald-300";
                txtDias.textContent = `Han pasado ${data.dias_transcurridos} días de los ${data.dias_permitidos} días estipulados para Grado ${data.equipo.grado}.`;
            } else {
                badgeVigencia.textContent = "⚠️ Periodo de garantía expirado";
                badgeVigencia.className = "px-3 py-1 text-xs font-bold rounded-lg bg-rose-100 text-rose-800 border border-rose-300";
                txtDias.textContent = `Garantía vencida: Han transcurrido ${data.dias_transcurridos} días (Plazo máximo: ${data.dias_permitidos} días).`;
            }

            // Sugerir monto cubierto
            const inputMonto = document.getElementById('garantia-monto-cubierto');
            if (inputMonto) inputMonto.value = data.venta.precio_final;

            if (boxDetalles) boxDetalles.classList.remove('hidden');

        } catch (err) {
            App.showToast(err.message, "error");
        } finally {
            if (btn) btn.disabled = false;
            if (loading) loading.classList.add('hidden');
        }
    },

    async procesarDevolucion() {
        if (!this.equipoEncontrado) {
            App.showToast("Primero consulta y verifica el IMEI del equipo.", "error");
            return;
        }

        const motivo = document.getElementById('garantia-select-motivo').value;
        const fallaDesc = document.getElementById('garantia-falla-desc').value.trim();
        const estadoDestino = document.getElementById('garantia-estado-destino').value;
        const solucion = document.getElementById('garantia-solucion').value;
        const montoCubierto = parseFloat(document.getElementById('garantia-monto-cubierto').value) || 0;
        const notas = document.getElementById('garantia-notas').value.trim();

        const btnSubmit = document.getElementById('btn-confirmar-devolucion-garantia');
        const originalText = btnSubmit.innerHTML;

        try {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = `
                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg> Procesando devolución...
            `;

            const payload = {
                imei: this.equipoEncontrado.equipo.imei,
                motivo: motivo,
                falla_descripcion: fallaDesc,
                estado_equipo_recibido: estadoDestino,
                solucion: solucion,
                monto_cubierto: montoCubierto,
                notas: notas
            };

            const res = await fetch('/api/garantias/devolucion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await res.json();

            if (!res.ok) {
                throw new Error(result.detail || "Error al procesar la devolución.");
            }

            App.showToast(`Devolución por garantía registrada (Folio G-${result.id})`, "success");
            this.cerrarModal();

            // Si la solución fue reemplazo por otro celular, pre-cargar el POS con el crédito y el cliente
            if (solucion === 'Reemplazo') {
                App.switchTab('pos');
                // Prellenar cliente en POS
                const inputNombre = document.getElementById('pos-cliente-nombre');
                const inputTel = document.getElementById('pos-cliente-telefono');
                if (inputNombre) inputNombre.value = result.cliente_nombre;
                if (inputTel) inputTel.value = result.cliente_telefono;

                // Seleccionar método de pago Equipo Garantía
                POS.seleccionarMetodoPago('Equipo Garantía');

                // Notificar al vendedor
                App.showToast(`Cliente '${result.cliente_nombre}' listo. Selecciona en el catálogo el equipo de reemplazo.`, "info");
            }

            // Recargar datos de inventario y reportes
            Inventario.cargarEquipos();
            App.updateHeaderStats();

        } catch (err) {
            App.showToast(err.message, "error");
        } finally {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = originalText;
        }
    }
};
