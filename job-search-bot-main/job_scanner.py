import os
import re
import smtplib
import urllib.parse
import sqlite3
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import pandas as pd
from dotenv import load_dotenv

# Resolve database path relative to the script's folder
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "jobs.db")

# Load local environment variables (if running locally)
load_dotenv()

# Check for required configuration
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

print("SMTP_EMAIL:", bool(SMTP_EMAIL))
print("SMTP_PASSWORD:", bool(SMTP_PASSWORD))
print("RECIPIENT_EMAIL:", bool(RECIPIENT_EMAIL))

# Target Job Search Config
CITIES = [
    "Hyderabad, India",
    "Bengaluru, India",
    "Pune, India",
    "Chennai, India",
    "Noida, India",
    "Gurugram, India"
]

# Target search keywords
KEYWORDS = [
    "Software Engineer",
    "Associate Software Engineer",
    "Graduate Engineer Trainee",
    "Python Developer",
    "Data Analyst",
    "Business Analyst",
    "Analayst",
    "Junior Data Scientist",
    "Machine Learning Engineer",
    "AI Engineer",
    "Frontend Developer",
    "Full Stack Developer",
    "Intern"
]
# Known Applicant Tracking Systems (ATS)
ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "workday.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "jobvite.com",
    "icims.com",
    "workable.com",
    "recruitee.com",
    "bamboohr.com",
    "teamtailor.com",
    "personio.com",
    "rippling.com",
    "successfactors.com"
]

# Third-party job boards to check against
JOB_BOARDS = [

    # Global
    "linkedin.com",
    "indeed.com",
    "indeed.co.in",
    "glassdoor.com",
    "glassdoor.co.in",
    "ziprecruiter.com",
    "monster.com",
    "monsterindia.com",
    "simplyhired.com",
    "simplyhired.co.in",
    "careerbuilder.com",
    "dice.com",

    # India
    "naukri.com",
    "foundit.in",
    "shine.com",
    "timesjobs.com",
    "freshersworld.com",
    "internshala.com",
    "cutshort.io",
    "hirist.com",
    "instahyre.com",
    "unstop.com",

    # Startup Jobs
    "wellfound.com",
    "angel.co",
    "ycombinator.com",
    "yc-startup-jobs.com",

    # Remote Jobs
    "remoteok.com",
    "weworkremotely.com",
    "remotive.com",
    "flexjobs.com",

    # Tech Communities
    "stackoverflow.com",
    "github.com",
    "hackerrank.com",
    "leetcode.com",

    # Google Jobs
    "google.com"

]
def requires_experience(title, description):
    """
    Checks if a job title or description indicates an experience requirement
    that is not suitable for freshers (e.g. 2+ years, mid-senior level).
    """
    title = str(title or "").lower()
    description = str(description or "").lower()
    
    # Remove markdown escaping backslashes (e.g., "3\+ years" -> "3+ years")
    title = title.replace("\\", "")
    description = description.replace("\\", "")
    
    # Remove leading zeros from numbers (e.g., "08 years" -> "8 years")
    title = re.sub(r'\b0+([1-9]\d*)\b', r'\1', title)
    description = re.sub(r'\b0+([1-9]\d*)\b', r'\1', description)
    
    # 1. Check for senior/lead/experience keywords in title
    senior_keywords = [
        "senior", "sr.", "sr ", "lead", "principal", "manager", "architect", 
        "mid-level", "mid level", "experienced", "expert", "head of", "director",
        "sr. engineer", "senior engineer", "lead engineer", "staff engineer",
        "staff developer", "tech lead", "technical lead", "solution architect",
        "solutions architect"
    ]
    for keyword in senior_keywords:
        if keyword in title:
            return True
            
    # Exclude levels like II, III, IV, 2, 3, 4, 5 in job title
    if re.search(r'\b(?:ii|iii|iv|v|2|3|4|5)\b', title):
        return True
            
    # 2. Check for experience patterns in title or description
    if re.search(r'\b[2-9]\d*\s*\+\s*(?:year|yr)', title) or re.search(r'\b[2-9]\d*\s*\+\s*(?:year|yr)', description):
        return True
        
    exp_regex = r'(?<!0-)(?<!0\s-)(?<!0\s-\s)(?<!0\sto\s)(?<!1-)(?<!1\s-)(?<!1\s-\s)(?<!1\sto\s)\b[2-9]\d*\s*(?:to\s*[0-9]+\s*)?(?:year|yr)'
    if re.search(exp_regex, title) or re.search(exp_regex, description):
        return True
        
    return False

def extract_deadline(description):
    """
    Scrapes the description for deadline keywords and date formats.
    Returns the extracted date, or 'N/A' if not found.
    """
    if not description or not isinstance(description, str):
        return "N/A"
        
    description_lower = description.lower()
    
    deadline_keywords = [
        "last date to apply", "last date", "application deadline", 
        "deadline", "apply before", "closing date", "end date"
    ]
    
    has_keyword = False
    for kw in deadline_keywords:
        if kw in description_lower:
            has_keyword = True
            break
            
    if not has_keyword:
        return "N/A"
        
    for kw in deadline_keywords:
        matches = list(re.finditer(re.escape(kw), description_lower))
        for match in matches:
            start = match.start()
            # Look at a snippet of 120 characters following the keyword
            snippet = description[start:start+120]
            
            # Format 1: dd-mm-yyyy or dd/mm/yyyy
            date_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[-/](0?[1-9]|1[012])[-/](202\d)\b', snippet)
            if date_match:
                return date_match.group(0)
                
            # Format 2: dd Month yyyy (e.g. 15 June 2026, 15th Jun 2026, 15-Jun-2026)
            date_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(202\d)\b', snippet, re.IGNORECASE)
            if date_match:
                day, month, year = date_match.groups()
                return f"{day} {month.capitalize()} {year}"
                
            # Format 3: Month dd, yyyy (e.g. June 15, 2026)
            date_match = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?,?\s+(202\d)\b', snippet, re.IGNORECASE)
            if date_match:
                month, day, year = date_match.groups()
                return f"{day} {month.capitalize()} {year}"
                
            # Format 4: yyyy-mm-dd or yyyy/mm/dd
            date_match = re.search(r'\b(202\d)[-/](0?[1-9]|1[012])[-/](0?[1-9]|[12][0-9]|3[01])\b', snippet)
            if date_match:
                return date_match.group(0)
                
    return "N/A"

def get_verification_status(url):
    """
    Evaluates the URL to verify if it is an official career page or a trusted ATS portal.
    """
    if not url or not isinstance(url, str):
        return "Unverified", "N/A"
    
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    
    # Remove 'www.' from the beginning of domain if present
    if domain.startswith("www."):
        domain = domain[4:]
        
    # Check if it matches a known ATS platform
    for ats in ATS_DOMAINS:
        if ats in domain or ats in url.lower():
            return "Verified: ATS Portal", ats.split('.')[0].capitalize()
            
    # Check if it is a major job board (unverified/indirect link)
    for board in JOB_BOARDS:
        if board in domain:
            return "Unverified / Third-Party", "Job Board Redirect"
            
    # If it's not a job board and has a domain, it's likely a direct company domain
    if domain:
        return "Verified: Direct Company Domain", domain
        
    return "Unverified", "N/A"

def scrape_job_listings():
    """
    Scrapes fresher jobs quickly.
    Stops after MAX_JOBS have been collected.
    """

    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("Install python-jobspy")
        return pd.DataFrame()

    all_jobs = []
    total_jobs = 0

    print("\n===== STARTING JOB SEARCH =====")

    for keyword in KEYWORDS:

        if total_jobs >= MAX_JOBS:
            break

        for location in CITIES:

            if total_jobs >= MAX_JOBS:
                break

            print(f"\nSearching: {keyword} | {location}")

            try:

                jobs = scrape_jobs(
                    site_name=["linkedin", "google"],
                    search_term=keyword,
                    location=location,
                    country_indeed="india",
                    results_wanted=20,
                    hours_old=48
                )

                if jobs.empty:
                    print("No jobs found.")
                    continue

                all_jobs.append(jobs)

                total_jobs += len(jobs)

                print(
                    f"Collected {len(jobs)} jobs | Total = {total_jobs}"
                )

            except Exception as e:
                print(e)

    if len(all_jobs) == 0:
        return pd.DataFrame()

    combined_df = pd.concat(all_jobs, ignore_index=True)

    combined_df.drop_duplicates(
        subset=["title", "company", "location", "job_url"],
        inplace=True
    )

    filtered_rows = []

    for _, row in combined_df.iterrows():

        title = row.get("title", "")
        description = row.get("description", "")

        if requires_experience(title, description):
            continue

        url = row.get("job_url_direct") or row.get("job_url")

        status, platform = get_verification_status(url)

        row_dict = dict(row)

        row_dict["Verification Status"] = status
        row_dict["Hosting/ATS Platform"] = platform
        row_dict["application_deadline"] = extract_deadline(description)

        filtered_rows.append(row_dict)

    if len(filtered_rows) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(filtered_rows)

    df.sort_values(
        by="Verification Status",
        ascending=False,
        inplace=True
    )

    print(f"\nFinal Jobs = {len(df)}")

    return df
    
    # Combine all DataFrames
    combined_df = pd.concat(all_jobs_list, ignore_index=True)
    
    # Drop duplicates based on title, company, and location
    combined_df.drop_duplicates(subset=["title","company","location","job_url"],keep="first",inplace=True)

    # Process Verification and filter out experienced jobs
    filtered_rows = []
    
    for idx, row in combined_df.iterrows():
        title = row.get("title", "")
        description = row.get("description", "")
        
        # Check experience filter
        if requires_experience(title, description):
            continue
            
        # Check both job_url and job_url_direct (depending on what jobspy provides)
        url_to_check = row.get("job_url_direct") or row.get("job_url")
        status, platform = get_verification_status(url_to_check)
        if any(x in domain for x in ["careers.","career.","jobs.","join.","apply."]):
            return "Verified: Company Careers", domain
        
        # Convert row to dict and add verification fields
        row_dict = dict(row)
        row_dict["Verification Status"] = status
        row_dict["Hosting/ATS Platform"] = platform
        # Extract application deadline
        row_dict["application_deadline"] = extract_deadline(description)
        filtered_rows.append(row_dict)
        
    if not filtered_rows:
        print("=== SCRAPING COMPLETED: Found 0 jobs matching fresher criteria. ===")
        return pd.DataFrame()
        
    filtered_df = pd.DataFrame(filtered_rows)
    
    # Sort: put verified jobs at the top
    filtered_df.sort_values(by="Verification Status", ascending=False, inplace=True)
    
    print(f"=== SCRAPING COMPLETED: Found {len(filtered_df)} unique jobs (filtered out experienced roles). ===")
    return filtered_df

def send_email_with_excel(df):
    """
    Generates the Excel file and emails it to the user.
    """
    filename = "verified_jobs.xlsx"
    
    # Select and order columns for the Excel sheet
    columns_to_keep = [
        "title", "company", "location", "date_posted", "application_deadline",
        "Verification Status", "Hosting/ATS Platform", "job_url"
    ]
    
    # Filter columns that actually exist in the dataframe
    existing_cols = [col for col in columns_to_keep if col in df.columns]
    report_df = df[existing_cols].copy()
    
    # Rename columns for presentation
    rename_dict = {
        "title": "Job Title",
        "company": "Company",
        "location": "Location",
        "date_posted": "Date Posted",
        "application_deadline": "Last Date to Apply",
        "job_url": "Job Link / Apply Link"
    }
    report_df.rename(columns=rename_dict, inplace=True)
    
        # Write to Excel
    try:
        verified_df = report_df[
            report_df["Verification Status"].str.contains("Verified", na=False)
        ]

        unverified_df = report_df[
            ~report_df["Verification Status"].str.contains("Verified", na=False)
        ]

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:

            pd.DataFrame([["===== VERIFIED JOBS ====="]]).to_excel(
                writer,
                sheet_name="Jobs",
                index=False,
                header=False,
                startrow=0
            )

            verified_df.to_excel(
                writer,
                sheet_name="Jobs",
                index=False,
                startrow=2
            )

            unverified_start = len(verified_df) + 5

            pd.DataFrame([["===== UNVERIFIED JOBS ====="]]).to_excel(
                writer,
                sheet_name="Jobs",
                index=False,
                header=False,
                startrow=unverified_start
            )

            unverified_df.to_excel(
                writer,
                sheet_name="Jobs",
                index=False,
                startrow=unverified_start + 2
            )

        print(f"Excel report saved locally as '{filename}'.")

    except Exception as e:
        print(f"[ERROR] Failed to save Excel file: {e}")
        return False

    if not SMTP_EMAIL or not SMTP_PASSWORD or not RECIPIENT_EMAIL:
        print("[ERROR] Email credentials not found in environment. Skipping email dispatch.")
        return False
        
    # Build Email Message
    msg = MIMEMultipart()
    msg["From"] = SMTP_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    date_str = datetime.now().strftime("%d-%b-%Y")
    msg["Subject"] = f"Daily Verified Job Report - {date_str}"
    
    # Count verified vs unverified
    total = len(df)
    verified_count = len(df[df["Verification Status"].str.startswith("Verified")])
    unverified_count = total - verified_count
    
    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #1a73e8;">Daily Verified Job Search Report</h2>
        <p>Hello,</p>
        <p>Please find attached your daily Excel job report for target IT, entry-level, and technical support positions in top Indian cities (Hyderabad, Bengaluru, Chennai, Coimbatore, Pune, and Mumbai).</p>
        
        <table style="border-collapse: collapse; width: 100%; max-width: 400px; margin-bottom: 20px;">
          <tr style="background-color: #f2f2f2;">
            <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Category</th>
            <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Count</th>
          </tr>
          <tr>
            <td style="border: 1px solid #ddd; padding: 8px;">Verified Career Page Jobs</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: right; font-weight: bold; color: #2e7d32;">{verified_count}</td>
          </tr>
          <tr>
            <td style="border: 1px solid #ddd; padding: 8px;">Unverified/Third-Party Jobs</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: right; color: #c62828;">{unverified_count}</td>
          </tr>
          <tr style="font-weight: bold; background-color: #e8f0fe;">
            <td style="border: 1px solid #ddd; padding: 8px;">Total Listings Found</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{total}</td>
          </tr>
        </table>
        
        <p><i>Note: Verified jobs are sorted to the top of the attached Excel sheet. These listings link directly to the official company domains or applicant tracking platforms (like Greenhouse, Lever, Workday) and are 100% real openings.</i></p>
        
        <p>Best regards,<br>Your Automated Job Search Bot</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(body, "html"))
    
    # Attach Excel sheet
    try:
        with open(filename, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename= {filename}",
        )
        msg.attach(part)
        
        # Connect and Send
        print(f"Connecting to SMTP server to send email from '{SMTP_EMAIL}' to '{RECIPIENT_EMAIL}'...")
        # Use Gmail/Standard SMTP config
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        
        print("[SUCCESS] Job report email sent successfully!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False

def save_jobs_to_db(df):
    """
    Saves the scraped jobs into the local SQLite database.
    Prevents duplicate entries for the same title, company, location, and scraped_date.
    """
    if df.empty:
        print("[INFO] No jobs to save to the database.")
        return
        
    print(f"Connecting to database at '{DB_PATH}'...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraped_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            date_posted TEXT,
            job_url TEXT,
            verification_status TEXT,
            platform TEXT,
            scraped_date TEXT,
            application_deadline TEXT,
            UNIQUE(title, company, location, scraped_date)
        )
    """)
    conn.commit()
    
    # Run a migration try to add the column if the table already exists from older code
    try:
        cursor.execute("ALTER TABLE scraped_jobs ADD COLUMN application_deadline TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists, safe to ignore
        pass
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    inserted_count = 0
    duplicate_count = 0
    
    def clean_val(val):
        if pd.isna(val) or val is None:
            return ""
        return str(val).strip()
        
    for idx, row in df.iterrows():
        title = clean_val(row.get("title"))
        company = clean_val(row.get("company"))
        location = clean_val(row.get("location"))
        date_posted = clean_val(row.get("date_posted"))
        
        url_direct = clean_val(row.get("job_url_direct"))
        url_standard = clean_val(row.get("job_url"))
        job_url = url_direct if url_direct else url_standard
        
        verification_status = clean_val(row.get("Verification Status"))
        if not verification_status:
            verification_status = "Unverified"
            
        platform = clean_val(row.get("Hosting/ATS Platform"))
        if not platform:
            platform = "N/A"
            
        # Extract and clean application deadline
        deadline = clean_val(row.get("application_deadline"))
        if not deadline:
            deadline = "N/A"
        
        # Check if already exists for today to prevent duplicates
        cursor.execute("""
            SELECT id FROM scraped_jobs 
            WHERE title = ? AND company = ? AND location = ? AND scraped_date = ?
        """, (title, company, location, today_str))
        
        existing = cursor.fetchone()
        if existing:
            duplicate_count += 1
            continue
            
        try:
            cursor.execute("""
                INSERT INTO scraped_jobs (title, company, location, date_posted, job_url, verification_status, platform, scraped_date, application_deadline)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, company, location, date_posted, job_url, verification_status, platform, today_str, deadline))
            inserted_count += 1
        except Exception as e:
            print(f"[WARNING] Failed to insert job '{title}' from '{company}': {e}")
            
    conn.commit()
    conn.close()
    print(f"[DATABASE] Saved jobs: {inserted_count} new inserted, {duplicate_count} skipped as duplicates.")

if __name__ == "__main__":
    jobs_df = scrape_job_listings()
    if not jobs_df.empty:
        save_jobs_to_db(jobs_df)
        send_email_with_excel(jobs_df)
    else:
        print("[INFO] No jobs found today to save or send.")
