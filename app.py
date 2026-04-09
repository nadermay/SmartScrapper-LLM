import os
import csv
import threading
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from werkzeug.utils import secure_filename

import db
from sse_logger import job_logger
import scraper

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file and file.filename.endswith('.csv'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Count total records
        total_records = 0
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            total_records = sum(1 for row in reader if any(row))
            
        job_id = db.create_job(filename, total_records)
        
        use_ai = request.form.get('use_ai', 'true') == 'true'
        threads = int(request.form.get('threads', 5))
        
        threading.Thread(target=run_background_job, args=(job_id, filepath, threads, use_ai)).start()
        
        return jsonify({"job_id": job_id})
    return jsonify({"error": "Must upload a .csv file"}), 400

def run_background_job(job_id, filepath, threads, use_ai):
    job_logger.log(job_id, f"Started scraping {filepath} with {threads} threads.", "info")
    try:
        scraper.process_csv_for_job(job_id, filepath, threads, use_ai)
    except Exception as e:
        job_logger.log(job_id, f"Fatal Job Error: {str(e)}", "error")
        db.fail_job(job_id)

@app.route('/api/stream/<int:job_id>')
def stream(job_id):
    def event_stream():
        q = job_logger.get_queue(job_id)
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        except GeneratorExit:
            job_logger.remove_queue(job_id, q)
            
    return Response(stream_with_context(event_stream()), content_type='text/event-stream')

@app.route('/api/jobs')
def list_jobs():
    return jsonify(db.get_recent_jobs())

@app.route('/api/leads/<int:job_id>')
def list_leads(job_id):
    status = db.get_job_status(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": status,
        "leads": db.get_job_results(job_id)
    })

@app.route('/api/job/<int:job_id>/pause', methods=['POST'])
def pause_job(job_id):
    db.update_job_state(job_id, 'paused')
    return jsonify({"success": True, "status": "paused"})

@app.route('/api/job/<int:job_id>/resume', methods=['POST'])
def resume_job(job_id):
    db.update_job_state(job_id, 'running')
    return jsonify({"success": True, "status": "running"})

@app.route('/api/job/<int:job_id>/stop', methods=['POST'])
def stop_job(job_id):
    db.update_job_state(job_id, 'stopped')
    return jsonify({"success": True, "status": "stopped"})

@app.route('/api/retry/lead/<int:lead_id>', methods=['POST'])
def retry_lead(lead_id):
    data = request.json
    manual_url = data.get('url')
    if not manual_url:
        return jsonify({"error": "URL is required"}), 400
        
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
        
    job_id = lead['job_id']
    company_name = lead['business_name']
    
    def run_retry():
        try:
            # Re-scrape bypassing discovery
            scraped_data = scraper.scrape_company(company_name, manual_url=manual_url)
            # Update the existing lead row
            db.update_lead(lead_id, scraped_data)
            
            job_logger.log(job_id, f"[*] Manual retry finished for {company_name}", "success", lead_id=lead_id, lead_data=scraped_data)
        except Exception as e:
            job_logger.log(job_id, f"[!] Manual retry error for {company_name}: {str(e)}", "error")

    # Run silently in background so UI returns instantly
    threading.Thread(target=run_retry).start()
    return jsonify({"success": True})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify(db.get_agency_profile())

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    db.save_agency_profile(data)
    return jsonify({"success": True})

@app.route('/api/draft_email/<int:lead_id>', methods=['GET'])
def draft_email(lead_id):
    from llm_processor import generate_cold_email
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
        
    agency_context = db.get_agency_profile()
    draft = generate_cold_email(lead, agency_context)
    return jsonify({"draft": draft})

@app.route('/api/quick_search', methods=['POST'])
def quick_search():
    data = request.json
    company_name = data.get('company_name')
    if not company_name:
        return jsonify({"error": "No company name provided"}), 400
        
    from scraper import scrape_company
    job_id = db.create_job(f"Quick Search: {company_name}", 1)
    
    # Run the scrape synchronously so it returns to the modal immediately
    try:
        res = scrape_company(company_name)
        lead_id = db.insert_lead(job_id, res)
        # Mark job completed safely
        db.update_job_progress(job_id, delta_completed=1 if res.get('status') == 'Success' else 0, delta_failed=1 if res.get('status') != 'Success' else 0)
        res['id'] = lead_id
        res['job_id'] = job_id
        return jsonify({"success": True, "lead_data": res})
    except Exception as e:
        db.fail_job(job_id)
        return jsonify({"error": str(e)}), 500

@app.route('/api/job/<int:job_id>/delete', methods=['DELETE'])
def delete_job(job_id):
    db.delete_job(job_id)
    return jsonify({"success": True})

@app.route('/api/ollama-status')
def ollama_status():
    import requests
    try:
        res = requests.get('http://localhost:11434', timeout=2)
        return jsonify({"online": res.status_code == 200})
    except:
        return jsonify({"online": False})


@app.route('/api/leads/search', methods=['GET'])
def api_search_leads():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'leads': []})
        
    leads = db.search_all_leads(query)
    return jsonify({'leads': leads})

@app.route('/api/download/<int:job_id>')
def download_csv(job_id):
    import io
    from flask import send_file
    
    leads = db.get_job_results(job_id)
    if not leads:
        return jsonify({"error": "No leads found"}), 404
        
    output = io.StringIO()
    fieldnames = [
        'Business Name', 'Phone', 'Email', 'Location', 'Website', 
        'LinkedIn', 'Facebook', 'Twitter', 'Instagram',
        'Niche', 'Summary', 'Decision Maker', 'Opening Line', 'Pitch Angle'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for lead in leads:
        writer.writerow({
            'Business Name': lead.get('business_name', ''),
            'Phone': lead.get('phone', ''),
            'Email': lead.get('email', ''),
            'Location': lead.get('location', ''),
            'Website': lead.get('website', ''),
            'LinkedIn': lead.get('linkedin', ''),
            'Facebook': lead.get('facebook', ''),
            'Twitter': lead.get('twitter', ''),
            'Instagram': lead.get('instagram', ''),
            'Niche': lead.get('niche', ''),
            'Summary': lead.get('summary', ''),
            'Decision Maker': lead.get('decision_maker', ''),
            'Opening Line': lead.get('opening_line', ''),
            'Pitch Angle': lead.get('pitch_angle', '')
        })
        
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    
    filename = f"wise_local_leads_job_{job_id}.csv"
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    # We explicitly disable the Werkzeug reloader `use_reloader=False`.
    # Windows Store Python installations use a virtual filesystem that natively
    # reports phantom timestamp shifts on Standard Library files (like asyncio),
    # causing Flask to constantly restart mid-scrape and throw EPIPE broken pipe errors.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
