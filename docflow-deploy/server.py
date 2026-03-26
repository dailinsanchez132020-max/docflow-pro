"""
DocFlow Pro — Servidor principal
Convierte PDF a Word preservando diseño completo
"""
import os
import sys
import uuid
import shutil
import subprocess
import threading
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

WORK_DIR = Path(tempfile.gettempdir()) / 'docflow'
WORK_DIR.mkdir(exist_ok=True)

jobs = {}  # job_id -> {status, step, progress, ...}


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
        if out.exists():
            out.unlink(missing_ok=True)

    # 2. Fallback: qpdf sin decrypt (remueve restricciones de copia/edición)
    try:
        cmd = ['qpdf', '--qdf', '--object-streams=disable', str(pdf_path), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and out.exists():
            return out, 'Restricciones de edición removidas ✓'
    except Exception:
        pass

    # 3. Si todo falla, usar el original
    return pdf_path, 'Usando PDF original'


# ─── Conversión PDF → DOCX ────────────────────────────────────────────────

def do_convert(pdf_path: Path, job_id: str):
    """Ejecuta la conversión completa en un hilo separado."""
    try:
        jobs[job_id].update(step='Analizando seguridad del PDF...', progress=15)

        password = jobs[job_id].get('password', '')
        clean_pdf, security_msg = remove_security(pdf_path, password)

        jobs[job_id].update(step=f'{security_msg} — Convirtiendo con LibreOffice...', progress=35)

        out_dir = WORK_DIR

        # Conversión con writer_pdf_import (mejor preservación de layout)
        result = run_libreoffice([
            '--headless',
            '--infilter=writer_pdf_import',
            '--convert-to', 'docx:MS Word 2007 XML',
            '--outdir', str(out_dir),
            str(clean_pdf)
        ], timeout=150)

        jobs[job_id].update(progress=75)

        # Buscar el archivo generado
        docx_file = out_dir / (clean_pdf.stem + '.docx')

        if not docx_file.exists() or docx_file.stat().st_size == 0:
            # Reintento sin filtro específico
            jobs[job_id].update(step='Reintentando conversión...', progress=80)
            run_libreoffice([
                '--headless',
                '--convert-to', 'docx',
                '--outdir', str(out_dir),
                str(clean_pdf)
            ], timeout=150)
            docx_file = out_dir / (clean_pdf.stem + '.docx')

        if not docx_file.exists() or docx_file.stat().st_size == 0:
            jobs[job_id].update(
                status='error',
                error=f'LibreOffice no pudo convertir el archivo. {result.stderr[:200]}'
            )
            return

        # Renombrar con job_id para evitar colisiones
        final = WORK_DIR / f'{job_id}.docx'
        shutil.move(str(docx_file), str(final))

        jobs[job_id].update(
            status='done',
            step='¡Conversión completada!',
            progress=100,
            output_file=str(final),
            security_msg=security_msg
        )

    except subprocess.TimeoutExpired:
        jobs[job_id].update(status='error', error='Tiempo de espera agotado. El PDF es muy grande o complejo.')
    except Exception as e:
        jobs[job_id].update(status='error', error=str(e))
    finally:
        # Limpiar archivos temporales de entrada
        try:
            pdf_path.unlink(missing_ok=True)
            clean_pdf_try = pdf_path.parent / (pdf_path.stem + '_open.pdf')
            clean_pdf_try.unlink(missing_ok=True)
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

    jobs[job_id] = {
        'status': 'processing',
        'step': 'Iniciando...',
        'progress': 5,
        'original_name': safe_name,
        'password': password,
        'output_file': None,
    }

    t = threading.Thread(target=do_convert, args=(upload_path, job_id), daemon=True)
    t.start()

    return jsonify({'job_id': job_id, 'filename': safe_name})


@app.route('/status/<job_id>')
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Trabajo no encontrado'}), 404
    # No exponer la ruta del archivo al cliente
    safe = {k: v for k, v in job.items() if k not in ('output_file', 'password')}
    return jsonify(safe)


@app.route('/download/<job_id>')
def download(job_id):
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
