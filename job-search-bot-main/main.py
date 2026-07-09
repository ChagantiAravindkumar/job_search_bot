import os
import sqlite3
import subprocess
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Job Search Bot Dashboard API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "jobs.db")
FRONTEND_DIR = os.path.join(SCRIPT_DIR, "frontend")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/dates")
def get_dates():
    """
    Returns all unique dates when job scraping was performed, sorted from newest to oldest.
    """
    if not os.path.exists(DB_PATH):
        return []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT scraped_date FROM scraped_jobs ORDER BY scraped_date DESC")
        dates = [row["scraped_date"] for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Table might not exist yet
        dates = []
    finally:
        conn.close()
    return dates

@app.get("/api/jobs")
def get_jobs(
    date: str = None,
    city: str = None,
    verified_only: bool = False,
    search: str = None
):
    """
    Returns job listings based on active filters.
    """
    if not os.path.exists(DB_PATH):
        return []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM scraped_jobs WHERE 1=1"
    params = []
    
    if date:
        query += " AND scraped_date = ?"
        params.append(date)
    if city:
        query += " AND location LIKE ?"
        params.append(f"%{city}%")
    if verified_only:
        query += " AND verification_status LIKE 'Verified%'"
    if search:
        query += " AND (title LIKE ? OR company LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        
    query += " ORDER BY verification_status DESC, id DESC"
    
    try:
        cursor.execute(query, params)
        jobs = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Table might not exist yet
        jobs = []
    finally:
        conn.close()
    return jobs

@app.get("/api/stats")
def get_stats(date: str = None):
    """
    Returns summary statistics for scraped jobs (total, verified, unverified, and by-city breakdown).
    """
    if not os.path.exists(DB_PATH):
        return {"total": 0, "verified": 0, "unverified": 0, "by_city": {}}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query_total = "SELECT COUNT(*) FROM scraped_jobs"
    query_verified = "SELECT COUNT(*) FROM scraped_jobs WHERE verification_status LIKE 'Verified%'"
    params = []
    
    if date:
        query_total += " WHERE scraped_date = ?"
        query_verified += " AND scraped_date = ?"
        params.append(date)
        
    try:
        cursor.execute(query_total, params)
        total = cursor.fetchone()[0]
        
        cursor.execute(query_verified, params)
        verified = cursor.fetchone()[0]
        
        # City breakdown
        query_city = "SELECT location, COUNT(*) as count FROM scraped_jobs"
        if date:
            query_city += " WHERE scraped_date = ?"
        query_city += " GROUP BY location"
        
        cursor.execute(query_city, params)
        city_counts = {}
        for row in cursor.fetchall():
            loc = row["location"].split(",")[0].strip()  # e.g., Extract "Bengaluru"
            city_counts[loc] = city_counts.get(loc, 0) + row["count"]
    except sqlite3.OperationalError:
        total = 0
        verified = 0
        city_counts = {}
    finally:
        conn.close()
        
    return {
        "total": total,
        "verified": verified,
        "unverified": total - verified,
        "by_city": city_counts
    }

@app.post("/api/scrape")
def trigger_scrape():
    """
    Triggers the job_scanner.py script locally to run in the background.
    """
    script_path = os.path.join(SCRIPT_DIR, "job_scanner.py")
    python_executable = os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")
    if not os.path.exists(python_executable):
        python_executable = "python"  # Fallback to system python
        
    try:
        # Run in background asynchronously without blocking the API
        subprocess.Popen([python_executable, script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {
            "status": "success", 
            "message": "Scraper started. It will update the database with fresh jobs in 2-3 minutes. Please refresh the page then."
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to start scraper: {str(e)}"}

# Serve Frontend static files if the frontend directory exists
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
