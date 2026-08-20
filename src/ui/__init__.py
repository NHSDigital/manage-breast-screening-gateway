from flask import Flask, flash, redirect, request, render_template, Response, send_file
from werkzeug.security import safe_join
from werkzeug.utils import secure_filename
import config
import logging
import os
import time
from services.clinic_exporter import ClinicExporter
from services.clinic_importer import ClinicImporter
from services.network import Rubie
from services.storage import MWLStorage, PACSStorage
from services.mwl import MWLStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


app = Flask(__name__)
app.secret_key = os.urandom(24)
mwl_storage = MWLStorage(db_path=config.mwl_db_path())
pacs_storage = PACSStorage(db_path=config.pacs_db_path(), storage_root=config.pacs_storage_path())

os.makedirs(config.export_directory(), exist_ok=True)
os.makedirs(config.import_directory(), exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"status": "ok", "rubie_available": Rubie.is_connected()}


@app.get("/worklist/import")
def import_worklist():
    return render_template("import_worklist.html")


@app.post("/worklist/import")
def import_worklist_post():
    try:
        if 'import-file' not in request.files:
            flash('Import file was not uploaded', 'error')
            return redirect("/worklist/import")

        file = request.files['import-file']
        filename = secure_filename(file.filename)
        if filename == '':
            flash('Please select a file to import', 'error')
            return redirect("/worklist/import")

        file_path = os.path.join(config.import_directory(), filename)
        file.save(file_path)

        logger.info(f'Importing worklist file from {file_path}')

        ClinicImporter(mwl_storage, {"source": "file", "file_path": file_path}).import_data()

        flash('Worklist file successfully imported')

        return redirect("/worklist")
    except Exception as e:
        flash(f'Error importing worklist file: {str(e)}', 'error')
        return redirect("/worklist/import")

@app.post("/worklist/export")
def export_worklist():
    try:
        clinic_id = request.form["clinic_id"]
        if not clinic_id:
            flash('Clinic ID is required for export', 'error')
            return redirect("/worklist")

        exporter = ClinicExporter(mwl_storage, pacs_storage, clinic_id)
        exporter.export_archive()

        logger.info(f'Worklist for clinic {clinic_id} successfully exported to {exporter.zip_file_path}')

        return send_file(exporter.zip_file_path, as_attachment=True)
    except Exception as e:
        flash(f'Error exporting worklist: {str(e)}', 'error')
        return redirect("/worklist")

@app.get("/worklist")
def view_worklist():
    worklist = mwl_storage.find_worklist_items()
    return render_template("worklist.html", worklist=worklist)

@app.get("/worklist/check-in/<accession_number>")
def check_in(accession_number: str):
    try:
        mwl_storage.update_status(accession_number, MWLStatus.ARRIVED)
        logger.info(f'Worklist item {accession_number} checked in successfully')
    except Exception as e:
        flash(f'Error checking in worklist item {accession_number}: {str(e)}')
    return redirect("/worklist")


@app.get("/worklist/start/<accession_number>")
def start_procedure(accession_number: str):
    try:
        mwl_storage.update_status(accession_number, "READY")
        item = mwl_storage.get_worklist_item(accession_number)

        logger.info(f'Worklist item {accession_number} started successfully')
    except Exception as e:
        flash(f'Error starting worklist item {accession_number}: {str(e)}')

    return render_template("appointment.html", item=item)

ORDERED_VIEWS = {"RCC": [], "RCCID": [], "RMLO": [], "LCC": [], "LCCID": [], "LMLO": []}

@app.get("/appointment/images/<accession_number>")
def appointment_images_stream(accession_number: str):
    def stream():
        existing_images = []
        with app.app_context():
            while True:
                new_images = pacs_storage.get_image_paths_by_accession_number(accession_number)
                if len(new_images) > len(existing_images):
                    item = mwl_storage.get_worklist_item(accession_number)
                    existing_images = new_images
                    ordered_views = {k: [] for k in ORDERED_VIEWS}
                    for path_str in new_images:
                        view = path_str.split(".")[1].upper()
                        if view in ordered_views:
                            if path_str not in ordered_views[view]:
                                ordered_views[view].append(path_str)
                    yield format_sse_event(
                        "images",
                        render_template(
                            "images.html",
                            accession_number=accession_number,
                            item=item,
                            images=ordered_views,
                        )
                    )

                time.sleep(1)

    response = Response(stream(), mimetype='text/event-stream')
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Accel-Buffering"] = "no"
    return response

@app.get("/appointment/<accession_number>/image/<path:image_path>")
def appointment_image(accession_number, image_path):
    full_path = safe_join(str(pacs_storage.storage_root), image_path)
    if full_path is None:
        return {"error": "invalid path"}, 404

    return send_file(open(full_path, "rb"), mimetype="image/jpeg")

def format_sse_event(event: str, data: str) -> str:
    """Format data as a Server-Sent Event."""
    lines = "\n".join(f"data: {line}" for line in data.splitlines())
    return f"event: {event}\n{lines}\n\n"
