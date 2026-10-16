// etiquetas_scanner.js - Escáner con Cámara del Celular y Generador de Etiquetas Imprimibles

const ScannerCamara = {
    html5QrCode: null,
    onScanCallback: null,
    isScanning: false,

    reproducirBeep() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = "sine";
            osc.frequency.setValueAtTime(1200, ctx.currentTime);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            osc.start();
            osc.stop(ctx.currentTime + 0.12);
        } catch (e) {
            // AudioContext no disponible o bloqueado por navegador
        }
        if (navigator.vibrate) {
            navigator.vibrate(100);
        }
    },

    abrir(callbackDestino) {
        this.onScanCallback = callbackDestino;
        const modal = document.getElementById('modal-camara-scanner');
        if (modal) modal.classList.remove('hidden');

        const readerDiv = document.getElementById('reader-camara');
        if (!readerDiv) return;

        if (typeof Html5Qrcode === 'undefined') {
            App.showToast("Cargando módulo de cámara, espera un momento...", "info");
            return;
        }

        this.html5QrCode = new Html5Qrcode("reader-camara");
        const config = { fps: 15, qrbox: { width: 260, height: 160 } };

        this.html5QrCode.start(
            { facingMode: "environment" },
            config,
            (decodedText) => {
                this.reproducirBeep();
                this.cerrar();
                App.showToast(`Escaneado: ${decodedText}`, "success");
                if (typeof this.onScanCallback === 'function') {
                    this.onScanCallback(decodedText);
                } else if (this.onScanCallback === 'inventario') {
                    const inp = document.getElementById('search-input');
                    if (inp) {
                        inp.value = decodedText;
                        inp.dispatchEvent(new Event('input'));
                        if (typeof Inventario !== 'undefined') Inventario.cargarEquipos(decodedText);
                    }
                } else if (this.onScanCallback === 'pos') {
                    const inp = document.getElementById('pos-search-input');
                    if (inp) {
                        inp.value = decodedText;
                        inp.dispatchEvent(new Event('input'));
                        if (typeof POS !== 'undefined') POS.buscarEquipos(decodedText);
                    }
                } else if (this.onScanCallback === 'garantias') {
                    const inp = document.getElementById('garantia-buscar-imei');
                    if (inp) {
                        inp.value = decodedText;
                        const btn = document.getElementById('btn-consultar-garantia-imei');
                        if (btn) btn.click();
                    }
                }
            },
            (errorMessage) => {
                // Escaneo continuo sin coincidencia
            }
        ).then(() => {
            this.isScanning = true;
        }).catch((err) => {
            console.error("Error abriendo cámara:", err);
            App.showToast("No se pudo acceder a la cámara. Revisa los permisos.", "error");
            this.cerrar();
        });
    },

    cerrar() {
        if (this.html5QrCode && this.isScanning) {
            this.html5QrCode.stop().then(() => {
                this.html5QrCode.clear();
                this.isScanning = false;
            }).catch(e => console.warn(e));
        }
        const modal = document.getElementById('modal-camara-scanner');
        if (modal) modal.classList.add('hidden');
    }
};

const Etiquetas = {
    equipoActual: null,

    async abrirParaEquipo(equipoId) {
        try {
            const res = await fetch(`/api/equipos/${equipoId}`);
            if (!res.ok) throw new Error("Equipo no encontrado");
            const eq = await res.json();
            this.equipoActual = eq;

            document.getElementById('etiqueta-preview-modelo').textContent = eq.modelo;
            document.getElementById('etiqueta-preview-detalles').textContent = `${eq.capacidad_gb}GB • ${eq.color} • Grado ${eq.grado}`;
            document.getElementById('etiqueta-preview-precio').textContent = App.formatCurrency(eq.precio_venta);

            if (typeof JsBarcode !== 'undefined') {
                JsBarcode("#etiqueta-barcode-svg", eq.imei, {
                    format: "CODE128",
                    width: 1.8,
                    height: 40,
                    displayValue: true,
                    fontSize: 11,
                    textMargin: 2,
                    margin: 2
                });
            }

            const modal = document.getElementById('modal-imprimir-etiqueta');
            if (modal) modal.classList.remove('hidden');
        } catch (e) {
            App.showToast("Error al generar etiqueta: " + e.message, "error");
        }
    },

    abrirParaAccesorio(acc) {
        document.getElementById('etiqueta-preview-modelo').textContent = acc.nombre;
        document.getElementById('etiqueta-preview-detalles').textContent = `Categoría: ${acc.categoria}`;
        document.getElementById('etiqueta-preview-precio').textContent = App.formatCurrency(acc.precio_venta);

        const codigo = acc.codigo_barras || `ACC-${acc.id}`;
        if (typeof JsBarcode !== 'undefined') {
            JsBarcode("#etiqueta-barcode-svg", codigo, {
                format: "CODE128",
                width: 1.8,
                height: 40,
                displayValue: true,
                fontSize: 11,
                textMargin: 2,
                margin: 2
            });
        }

        const modal = document.getElementById('modal-imprimir-etiqueta');
        if (modal) modal.classList.remove('hidden');
    },

    cerrar() {
        const modal = document.getElementById('modal-imprimir-etiqueta');
        if (modal) modal.classList.add('hidden');
    },

    imprimir() {
        window.print();
    }
};

window.ScannerCamara = ScannerCamara;
window.Etiquetas = Etiquetas;
