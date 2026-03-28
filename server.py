"""
DocFlow Pro — Servidor principal
Convierte PDF a Word preservando diseño completo
"""
import os
import uuid
import shutil
import subprocess
import threading
import tempfile
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

WORK_DIR = Path(tempfile.gettempdir()) / 'docflow'
WORK_DIR.mkdir(exist_ok=True)

# CORRECCIÓN: usar Lock para evitar race conditions entre hilos
jobs = {}
jobs_lock = threading.Lock()

# Tiempo máximo que un job se mantiene en memoria (1 hora)
JOB_TTL = 3600


# ─── Limpieza periódica de jobs ───────────────────────────────────────────

def cleanup_old_jobs():
    """Elimina jobs viejos de memoria y disco."""
    while True:
        time.sleep(600)  # cada 10 minutos
        now = time.time()
        to_delete = []
        with jobs_lock:
            for jid, job in jobs.items():
                if now - job.get('created_at', now) > JOB_TTL:
                    to_delete.append(jid)
            for jid in to_delete:
                job = jobs.pop(jid)
                # Eliminar archivo de salida del disco
                out = job.get('output_file')
                if out:
                    Path(out).unlink(missing_ok=True)

threading.Thread(target=cleanup_old_jobs, daemon=True).start()


# ─── Utilidades LibreOffice ────────────────────────────────────────────────

def get_soffice_env():
    env = os.environ.copy()
    env['SAL_USE_VCLPLUGIN'] = 'svp'
    env['HOME'] = '/tmp'
    return env


def run_libreoffice(args, timeout=120):
    env = get_soffice_env()
    cmd = ['soffice'] + args
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)


# ─── Remoción de contraseña / restricciones ───────────────────────────────

def remove_security(pdf_path: Path, password: str = '') -> tuple[Path, str]:
    """
    Intenta remover contraseña y restricciones del PDF usando qpdf.
    Retorna (pdf_sin_protección, mensaje).
    """
    out = pdf_path.parent / (pdf_path.stem + '_open.pdf')

    # Limpiar archivo de salida anterior si existe
    out.unlink(missing_ok=True)

    # Contraseñas a probar en orden
    candidates = []
    if password:
        candidates.append(password)
    candidates += ['', 'owner', 'user', '1234', 'password', 'pdf', 'admin', '0000']

    # 1. Intentar decrypt con cada contraseña
    for pwd in candidates:
        cmd = ['qpdf']
        if pwd:
            cmd += [f'--password={pwd}']
        cmd += ['--decrypt', str(pdf_path), str(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                msg = 'Contraseña removida ✓' if pwd else 'Sin contraseña detectada ✓'
                return out, msg
        except Exception:
            pass
        out.unlink(missing_ok=True)

    # 2. Fallback: qpdf sin decrypt (remueve restricciones de copia/edición)
    try:
        cmd = ['qpdf', '--qdf', '--object-streams=disable', str(pdf_path), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return out, 'Restricciones de edición removidas ✓'
    except Exception:
        pass

    # 3. Si todo falla, usar el original
    return pdf_path, 'Usando PDF original'


# ─── Conversión PDF → DOCX ────────────────────────────────────────────────

def update_job(job_id: str, **kwargs):
    """Actualiza el estado de un job de forma thread-safe."""
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def do_convert(pdf_path: Path, job_id: str):
    """Ejecuta la conversión completa en un hilo separado."""
    clean_pdf = None  # CORRECCIÓN: inicializar para el bloque finally

    try:
        update_job(job_id, step='Analizando seguridad del PDF...', progress=15)

        with jobs_lock:
            password = jobs[job_id].get('password', '')

        clean_pdf, security_msg = remove_security(pdf_path, password)

        update_job(job_id, step=f'{security_msg} — Convirtiendo con LibreOffice...', progress=35)

        out_dir = WORK_DIR
        first_error = ''

        # Intento 1: con filtro writer_pdf_import (mejor preservación de layout)
        result = run_libreoffice([
            '--headless',
            '--infilter=writer_pdf_import',
            '--convert-to', 'docx:MS Word 2007 XML',
            '--outdir', str(out_dir),
            str(clean_pdf)
        ], timeout=150)

        first_error = result.stderr[:300] if result.returncode != 0 else ''
        update_job(job_id, progress=75)

        docx_file = out_dir / (clean_pdf.stem + '.docx')

        if not docx_file.exists() or docx_file.stat().st_size == 0:
            # Intento 2: sin filtro específico
            update_job(job_id, step='Reintentando conversión...', progress=80)
            result2 = run_libreoffice([
                '--headless',
                '--convert-to', 'docx',
                '--outdir', str(out_dir),
                str(clean_pdf)
            ], timeout=150)
            docx_file = out_dir / (clean_pdf.stem + '.docx')
            if result2.returncode != 0 and not first_error:
                first_error = result2.stderr[:300]

        if not docx_file.exists() or docx_file.stat().st_size == 0:
            update_job(
                job_id,
                status='error',
                error=f'LibreOffice no pudo convertir el archivo. {first_error}'
            )
            return

        # Renombrar con job_id para evitar colisiones
        final = WORK_DIR / f'{job_id}.docx'
        shutil.move(str(docx_file), str(final))

        update_job(
            job_id,
            status='done',
            step='¡Conversión completada!',
            progress=100,
            output_file=str(final),
            security_msg=security_msg
        )

    except subprocess.TimeoutExpired:
        update_job(job_id, status='error', error='Tiempo de espera agotado. El PDF es muy grande o complejo.')
    except Exception as e:
        update_job(job_id, status='error', error=str(e))
    finally:
        # CORRECCIÓN: limpieza segura aunque clean_pdf no se haya asignado
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if clean_pdf and clean_pdf != pdf_path:
                clean_pdf.unlink(missing_ok=True)
        except Exception:
            pass


# ─── Rutas Flask ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No se recibió archivo'}), 400

    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Solo se aceptan archivos PDF'}), 400

    job_id = uuid.uuid4().hex[:10]
    safe_name = secure_filename(f.filename)
    upload_path = WORK_DIR / f'{job_id}_{safe_name}'
    f.save(str(upload_path))

    password = request.form.get('password', '')

    with jobs_lock:
        jobs[job_id] = {
            'status': 'processing',
            'step': 'Iniciando...',
            'progress': 5,
            'original_name': safe_name,
            'password': password,
            'output_file': None,
            'created_at': time.time(),  # para TTL de limpieza
        }

    t = threading.Thread(target=do_convert, args=(upload_path, job_id), daemon=True)
    t.start()

    return jsonify({'job_id': job_id, 'filename': safe_name})


@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Trabajo no encontrado'}), 404
    safe = {k: v for k, v in job.items() if k not in ('output_file', 'password', 'created_at')}
    return jsonify(safe)


@app.route('/download/<job_id>')
def download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get('status') != 'done':
        return jsonify({'error': 'No listo aún'}), 404

    out_file = Path(job['output_file'])
    if not out_file.exists():
        return jsonify({'error': 'Archivo no encontrado en servidor'}), 404

    original = Path(job.get('original_name', 'documento.pdf'))
    dl_name = original.stem + '_convertido.docx'
    return send_file(str(out_file), as_attachment=True, download_name=dl_name)


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'DocFlow Pro'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f'DocFlow Pro corriendo en http://0.0.0.0:{port}')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
