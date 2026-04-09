import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), 'wise_local.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            status TEXT NOT NULL, 
            total_records INTEGER DEFAULT 0,
            completed_records INTEGER DEFAULT 0,
            failed_records INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            business_name TEXT,
            phone TEXT,
            email TEXT,
            location TEXT,
            website TEXT,
            linkedin TEXT,
            facebook TEXT,
            twitter TEXT,
            instagram TEXT,
            niche TEXT,
            summary TEXT,
            decision_maker TEXT,
            opening_line TEXT,
            pitch_angle TEXT,
            status TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')
    
    # Check for stalled jobs on startup and cleanly mark them as failed
    c.execute("UPDATE jobs SET status = 'failed' WHERE status = 'running'")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    
    conn.commit()
    conn.close()

def create_job(filename, total_records):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO jobs (filename, status, total_records) VALUES (?, 'running', ?)", (filename, total_records))
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id

def update_job_progress(job_id, delta_completed=0, delta_failed=0):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT completed_records, failed_records, total_records FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    if not row: return
    
    new_completed = row['completed_records'] + delta_completed
    new_failed = row['failed_records'] + delta_failed
    
    c.execute("UPDATE jobs SET completed_records = ?, failed_records = ? WHERE id = ?", (new_completed, new_failed, job_id))
    
    if (new_completed + new_failed) >= row['total_records']:
        c.execute("UPDATE jobs SET status = 'completed' WHERE id = ?", (job_id,))
        
    conn.commit()
    conn.close()

def fail_job(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = 'failed' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

def delete_job(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM leads WHERE job_id = ?", (job_id,))
    c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

def insert_lead(job_id, lead_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO leads (
            job_id, business_name, phone, email, location, website, 
            linkedin, facebook, twitter, instagram, niche, summary, 
            decision_maker, opening_line, pitch_angle, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        job_id, 
        lead_data.get('company_name', ''), 
        lead_data.get('phone', ''), 
        lead_data.get('email', ''), 
        lead_data.get('location', ''), 
        lead_data.get('website_link', ''),
        lead_data.get('socials', {}).get('LinkedIn', 'Not Found'),
        lead_data.get('socials', {}).get('Facebook', 'Not Found'),
        lead_data.get('socials', {}).get('Twitter', 'Not Found'),
        lead_data.get('socials', {}).get('Instagram', 'Not Found'),
        lead_data.get('niche', ''),
        lead_data.get('summary', ''),
        lead_data.get('decision_maker', ''),
        lead_data.get('opening_line', ''),
        lead_data.get('pitch_angle', ''),
        lead_data.get('status', 'Success')
    ))
    lead_id = c.lastrowid
    conn.commit()
    conn.close()
    return lead_id

def get_job_status(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status, total_records, completed_records, failed_records FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_job_results(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE job_id = ?", (job_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]
    
def get_recent_jobs(limit=10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_job_state(job_id, new_state):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_state, job_id))
    conn.commit()
    conn.close()

def get_lead_by_id(lead_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_lead(lead_id, lead_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE leads SET
            phone = ?, email = ?, location = ?, website = ?,
            linkedin = ?, facebook = ?, twitter = ?, instagram = ?,
            niche = ?, summary = ?, decision_maker = ?,
            opening_line = ?, pitch_angle = ?, status = ?
        WHERE id = ?
    ''', (
        lead_data.get('phone', ''),
        lead_data.get('email', ''),
        lead_data.get('location', ''),
        lead_data.get('website_link', ''),
        lead_data.get('socials', {}).get('LinkedIn', 'Not Found'),
        lead_data.get('socials', {}).get('Facebook', 'Not Found'),
        lead_data.get('socials', {}).get('Twitter', 'Not Found'),
        lead_data.get('socials', {}).get('Instagram', 'Not Found'),
        lead_data.get('niche', ''),
        lead_data.get('summary', ''),
        lead_data.get('decision_maker', ''),
        lead_data.get('opening_line', ''),
        lead_data.get('pitch_angle', ''),
        lead_data.get('status', 'Success'),
        lead_id
    ))
    # If the previous status was Missing_Website and now it's success/failed, we don't strictly update the jobs counter 
    # but we will just leave the job counter as is since this is a manual override.
    conn.commit()
    conn.close()

def get_agency_profile():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'agency_profile'")
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row['value'])
        except:
            pass
    return {"name": "", "services": "", "cta": ""}

def save_agency_profile(profile_dict):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('agency_profile', ?)", (json.dumps(profile_dict),))
    conn.commit()
    conn.close()

def search_all_leads(query: str):
    conn = get_connection()
    c = conn.cursor()
    term = f"%{query}%"
    c.execute('''
        SELECT * FROM leads
        WHERE business_name LIKE ? 
           OR decision_maker LIKE ? 
           OR email LIKE ? 
           OR niche LIKE ?
        ORDER BY id DESC LIMIT 200
    ''', (term, term, term, term))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
