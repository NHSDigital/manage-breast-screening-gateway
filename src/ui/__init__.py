from flask import Flask, flash, redirect, request, render_template
from werkzeug.utils import secure_filename
import config
import logging
import os
from services.clinic_importer import ClinicImporter
from services.storage import MWLStorage
from services.mwl import MWLStatus


app = Flask(__name__)
app.secret_key = os.urandom(24)
storage = MWLStorage(db_path="./worklist.db")



@app.route("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/worklist/import")
def import_worklist():
    return render_template("import_worklist.html")


@app.post("/worklist/import")
def import_worklist_post():
    try:
        if 'import-file' not in request.files:
            flash('Import file was not uploaded')
            return redirect(request.url)

        file = request.files['import-file']
        filename = secure_filename(file.filename)
        if filename == '':
            flash('Please select a file to import')
            return redirect(request.url)

        file_path = os.path.join(".", filename)
        file.save(file_path)

        ClinicImporter(storage, {"source": "file", "file_path": file_path}).import_data()

        app.logger.info('Worklist file successfully imported')

        return redirect("/worklist")
    except Exception as e:
        flash(f'Error importing worklist file: {str(e)}')
        return redirect(request.url)


@app.get("/worklist")
def view_worklist():
    worklist = storage.find_worklist_items()
    return render_template("worklist.html", worklist=worklist)

@app.get("/worklist/check-in/<accession_number>")
def check_in(accession_number: str):
    try:
        storage.update_status(accession_number, MWLStatus.ARRIVED)
        app.logger.info(f'Worklist item {accession_number} checked in successfully')
    except Exception as e:
        flash(f'Error checking in worklist item {accession_number}: {str(e)}')
    return redirect("/worklist")


@app.get("/worklist/start/<accession_number>")
def start_procedure(accession_number: str):
    try:
        storage.update_status(accession_number, "READY")
        item = storage.get_worklist_item(accession_number)
        app.logger.info(f'Worklist item {accession_number} started successfully')
    except Exception as e:
        flash(f'Error starting worklist item {accession_number}: {str(e)}')

    return render_template("appointment.html", item=item)
