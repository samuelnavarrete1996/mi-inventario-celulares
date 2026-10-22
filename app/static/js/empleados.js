// empleados.js - Gestión de Empleados y Cajeros Multi-Tenant
// Exclusivo para rol 'dueno'

const Empleados = {
    lista: [],

    async init() {
        await this.cargar();
    },

    async cargar() {
        const tbody = document.getElementById('tabla-empleados-body');
        if (!tbody) return;

        try {
            const res = await fetch('/api/empleados');
            if (res.status === 401 || res.status === 403) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-slate-400 font-semibold">Acceso restringido: Se requieren permisos de Dueño.</td></tr>`;
                return;
            }
            if (!res.ok) throw new Error("No se pudo obtener la lista de empleados.");

            this.lista = await res.json();
            this.renderizar();
        } catch (e) {
            console.error("Error al cargar empleados:", e);
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-rose-500 font-semibold">Error al cargar personal: ${App.escapeHtml(e.message)}</td></tr>`;
        }
    },

    renderizar() {
        const tbody = document.getElementById('tabla-empleados-body');
        if (!tbody) return;

        if (!this.lista || this.lista.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-8 text-slate-400">
                        <span class="text-3xl block mb-2">👥</span>
                        No hay empleados registrados en tu negocio todavía.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = this.lista.map(emp => {
            const esDueno = emp.rol === 'dueno';

            // Badge de Rol
            let rolBadge = '';
            if (emp.rol === 'dueno') {
                rolBadge = '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-extrabold bg-amber-50 text-amber-700 border border-amber-200">👑 Dueño</span>';
            } else if (emp.rol === 'tecnico') {
                rolBadge = '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-extrabold bg-purple-50 text-purple-700 border border-purple-200">🔧 Técnico</span>';
            } else {
                rolBadge = '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-extrabold bg-blue-50 text-blue-700 border border-blue-200">🛒 Vendedor</span>';
            }

            // Badge de Estado
            const estadoBadge = emp.activo
                ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Activo</span>'
                : '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200"><span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> Suspendido</span>';

            // Botón de Acción rápida en 1 clic
            let btnAccion = '';
            if (esDueno) {
                btnAccion = '<span class="text-[11px] text-slate-400 italic">Cuenta Principal</span>';
            } else {
                if (emp.activo) {
                    btnAccion = `
                        <button type="button" onclick="Empleados.toggleEstado(${emp.id}, false, '${App.escapeHtml(emp.nombre)}')" 
                                class="px-3 py-1.5 rounded-xl text-xs font-bold bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 transition-colors shadow-xs cursor-pointer">
                            ⏸️ Suspender
                        </button>
                    `;
                } else {
                    btnAccion = `
                        <button type="button" onclick="Empleados.toggleEstado(${emp.id}, true, '${App.escapeHtml(emp.nombre)}')" 
                                class="px-3 py-1.5 rounded-xl text-xs font-bold bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 transition-colors shadow-xs cursor-pointer">
                            ▶️ Reactivar
                        </button>
                    `;
                }
            }

            return `
                <tr class="hover:bg-slate-50/80 transition-colors">
                    <td class="p-3.5 font-bold text-slate-800">
                        ${App.escapeHtml(emp.nombre)}
                    </td>
                    <td class="p-3.5">
                        <code class="px-2 py-0.5 bg-slate-100 rounded text-slate-700 font-mono text-[11px] font-bold">${App.escapeHtml(emp.username)}</code>
                    </td>
                    <td class="p-3.5">${rolBadge}</td>
                    <td class="p-3.5">${estadoBadge}</td>
                    <td class="p-3.5 text-right">${btnAccion}</td>
                </tr>
            `;
        }).join('');
    },

    abrirModalNuevo() {
        const form = document.getElementById('form-nuevo-empleado');
        if (form) form.reset();
        const modal = document.getElementById('modal-nuevo-empleado');
        if (modal) modal.classList.remove('hidden');
        const inputNom = document.getElementById('emp-nombre');
        if (inputNom) inputNom.focus();
    },

    cerrarModalNuevo() {
        const modal = document.getElementById('modal-nuevo-empleado');
        if (modal) modal.classList.add('hidden');
    },

    async guardarNuevo(e) {
        if (e) e.preventDefault();

        const nombre = (document.getElementById('emp-nombre')?.value || '').trim();
        const username = (document.getElementById('emp-username')?.value || '').trim().toLowerCase();
        const password = (document.getElementById('emp-password')?.value || '').trim();
        const rol = (document.getElementById('emp-rol')?.value || 'vendedor').trim().toLowerCase();

        if (!nombre || !username || !password) {
            App.showToast("Todos los campos marcados con asterisco (*) son obligatorios.", "warning");
            return;
        }

        if (password.length < 4) {
            App.showToast("La contraseña debe tener al menos 4 caracteres.", "warning");
            return;
        }

        const btn = document.getElementById('btn-guardar-empleado');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="animate-spin mr-1.5">⏳</span> Creando...`;
        }

        try {
            const res = await fetch('/api/empleados', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nombre, username, password, rol })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Error al registrar el empleado.");
            }

            const nuevo = await res.json();
            App.showToast(`✅ Empleado '${nuevo.nombre}' creado exitosamente.`, "success");
            this.cerrarModalNuevo();
            await this.cargar();
        } catch (err) {
            App.showToast(err.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<span>Guardar Empleado</span>`;
            }
        }
    },

    async toggleEstado(id, nuevoEstado, nombre) {
        const accion = nuevoEstado ? "reactivar" : "suspender";
        const accionPasada = nuevoEstado ? "reactivada" : "suspendida";

        if (!confirm(`¿Estás seguro de que deseas ${accion} el acceso de "${nombre}"?`)) {
            return;
        }

        try {
            const res = await fetch(`/api/empleados/${id}/estado`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ activo: nuevoEstado })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Error al ${accion} empleado.`);
            }

            App.showToast(`✅ Cuenta de ${nombre} ${accionPasada} correctamente.`, "success");
            await this.cargar();
        } catch (err) {
            App.showToast(err.message, "error");
        }
    }
};
