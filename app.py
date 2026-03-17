from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
import re
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = "graduate_inn_secret_key_change_this_in_production"
app.permanent_session_lifetime = timedelta(hours=2)

DATABASE = "database.db"

# DATABASE CONNECTION
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# CHECK IF COLUMN EXISTS
def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    conn = get_db()
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    conn.close()
    return column_name in columns

# GET AVAILABLE FEATURES
def get_available_features():
    """Check which features are available in the database"""
    return {
        'is_featured': column_exists('jobs', 'is_featured'),
        'views': column_exists('jobs', 'views'),
        'job_type': column_exists('jobs', 'job_type'),
        'experience_level': column_exists('jobs', 'experience_level'),
        'salary_range': column_exists('jobs', 'salary_range'),
        'created_date': column_exists('jobs', 'created_date')
    }

# SAFE QUERY EXECUTION
def execute_safe_query(query, params=None, fetch_one=False, fetch_all=False):
    """Execute query safely, handling missing columns"""
    conn = get_db()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            result = None
            conn.commit()
        
        conn.close()
        return result
    except sqlite3.OperationalError as e:
        conn.close()
        if "no such column" in str(e):
            print(f"Warning: {e}")
            if fetch_one:
                return None
            elif fetch_all:
                return []
            else:
                return None
        else:
            raise e

# INITIALIZE DATABASE (SAFE VERSION)
def init_db():
    """Initialize database with base tables"""
    conn = get_db()
    
    # Create base jobs table if not exists
    conn.execute("""
    CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        company TEXT,
        location TEXT,
        field TEXT,
        qualification TEXT,
        description TEXT,
        requirements TEXT,
        application_link TEXT,
        closing_date TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("Base database initialized")

init_db()

# ==========================
# HELPER FUNCTIONS
# ==========================

def get_session_id():
    """Get or create session ID for saved jobs"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def increment_job_views(job_id):
    """Increment view count for a job if column exists"""
    if column_exists('jobs', 'views'):
        conn = get_db()
        try:
            conn.execute("UPDATE jobs SET views = views + 1 WHERE id = ?", (job_id,))
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column doesn't exist yet
        finally:
            conn.close()

def get_featured_jobs(limit=3):
    """Get featured jobs if column exists"""
    if column_exists('jobs', 'is_featured'):
        conn = get_db()
        jobs = conn.execute("""
        SELECT * FROM jobs 
        WHERE is_featured = 1 
        ORDER BY id DESC 
        LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return jobs
    return []

# ==========================
# HOME PAGE (SAFE VERSION)
# ==========================
@app.route("/")
def index():
    features = get_available_features()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    conn = get_db()
    
    # Build query based on available features
    if features['is_featured']:
        jobs = conn.execute("""
        SELECT * FROM jobs
        ORDER BY is_featured DESC, id DESC
        LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()
    else:
        jobs = conn.execute("""
        SELECT * FROM jobs
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()
    
    # Get total count for pagination
    total_jobs = conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()['count']
    total_pages = (total_jobs + per_page - 1) // per_page
    
    # Get categories safely
    try:
        categories = conn.execute("""
        SELECT c.*, COUNT(j.id) as job_count 
        FROM categories c
        LEFT JOIN jobs j ON j.field = c.name
        GROUP BY c.id
        ORDER BY job_count DESC
        """).fetchall()
    except sqlite3.OperationalError:
        categories = []
    
    # Get top companies
    top_companies = conn.execute("""
    SELECT company, COUNT(*) as job_count 
    FROM jobs 
    GROUP BY company 
    ORDER BY job_count DESC 
    LIMIT 10
    """).fetchall()
    
    # Get featured jobs safely
    if features['is_featured']:
        featured_jobs = conn.execute("""
        SELECT * FROM jobs 
        WHERE is_featured = 1 
        ORDER BY id DESC 
        LIMIT 3
        """).fetchall()
    else:
        featured_jobs = []
    
    # Get stats
    stats = {
        'total_jobs': total_jobs,
        'total_companies': conn.execute("SELECT COUNT(DISTINCT company) as count FROM jobs").fetchone()['count'],
        'total_locations': conn.execute("SELECT COUNT(DISTINCT location) as count FROM jobs").fetchone()['count']
    }
    
    conn.close()
    
    return render_template("index.html", 
                         jobs=jobs, 
                         categories=categories,
                         top_companies=top_companies,
                         featured_jobs=featured_jobs,
                         stats=stats,
                         current_page=page,
                         total_pages=total_pages,
                         features=features)

# ==========================
# JOB DETAILS (SAFE VERSION)
# ==========================
@app.route("/job/<int:id>")
def job_details(id):
    features = get_available_features()
    
    # Increment view count if feature available
    if features['views']:
        increment_job_views(id)
    
    conn = get_db()
    
    # Get job details
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (id,)).fetchone()
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('index'))
    
    # Get similar jobs
    similar_jobs = conn.execute("""
    SELECT * FROM jobs
    WHERE field = ? AND id != ?
    ORDER BY id DESC
    LIMIT 3
    """, (job['field'], id)).fetchall()
    
    # Check if job is saved (if table exists)
    is_saved = False
    try:
        session_id = get_session_id()
        saved = conn.execute("""
        SELECT id FROM saved_jobs 
        WHERE job_id = ? AND session_id = ?
        """, (id, session_id)).fetchone()
        is_saved = bool(saved)
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet
    
    conn.close()
    
    return render_template("job_details.html", 
                         job=job, 
                         similar_jobs=similar_jobs,
                         is_saved=is_saved,
                         features=features)

# ==========================
# SEARCH JOBS (SAFE VERSION)
# ==========================
@app.route("/search")
def search():
    features = get_available_features()
    query = request.args.get("q", "")
    field = request.args.get("field", "")
    location = request.args.get("location", "")
    job_type = request.args.get("job_type", "")
    sort_by = request.args.get("sort_by", "recent")
    
    conn = get_db()
    
    # Build dynamic query
    sql = "SELECT * FROM jobs WHERE 1=1"
    params = []
    
    if query:
        sql += """ AND (title LIKE ? 
                       OR company LIKE ? 
                       OR field LIKE ? 
                       OR location LIKE ?
                       OR description LIKE ?)"""
        search_term = f"%{query}%"
        params.extend([search_term] * 5)
    
    if field:
        sql += " AND field = ?"
        params.append(field)
    
    if location:
        sql += " AND location LIKE ?"
        params.append(f"%{location}%")
    
    if job_type and features['job_type']:
        sql += " AND job_type = ?"
        params.append(job_type)
    
    # Sorting
    if sort_by == "recent":
        sql += " ORDER BY id DESC"
    elif sort_by == "company":
        sql += " ORDER BY company"
    elif sort_by == "location":
        sql += " ORDER BY location"
    
    jobs = conn.execute(sql, params).fetchall()
    
    # Get filter options
    fields = conn.execute("SELECT DISTINCT field FROM jobs ORDER BY field").fetchall()
    locations = conn.execute("SELECT DISTINCT location FROM jobs ORDER BY location").fetchall()
    
    # Get job types if available
    job_types = []
    if features['job_type']:
        job_types = conn.execute("SELECT DISTINCT job_type FROM jobs WHERE job_type IS NOT NULL").fetchall()
    
    conn.close()
    
    return render_template("search.html", 
                         jobs=jobs, 
                         query=query,
                         fields=fields,
                         locations=locations,
                         job_types=job_types,
                         selected_field=field,
                         selected_location=location,
                         selected_job_type=job_type,
                         sort_by=sort_by,
                         features=features)

# ==========================
# SAVE JOB (SAFE VERSION)
# ==========================
@app.route("/save_job/<int:job_id>")
def save_job(job_id):
    try:
        session_id = get_session_id()
        
        conn = get_db()
        
        # Create table if not exists
        conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            session_id TEXT,
            saved_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Check if already saved
        existing = conn.execute("""
        SELECT id FROM saved_jobs 
        WHERE job_id = ? AND session_id = ?
        """, (job_id, session_id)).fetchone()
        
        if not existing:
            conn.execute("""
            INSERT INTO saved_jobs (job_id, session_id)
            VALUES (?, ?)
            """, (job_id, session_id))
            conn.commit()
            flash('Job saved successfully!', 'success')
        else:
            flash('Job already saved', 'info')
        
        conn.close()
    except sqlite3.OperationalError as e:
        flash('Error saving job', 'error')
        print(f"Error: {e}")
    
    return redirect(request.referrer or url_for('index'))

# ==========================
# REMOVE SAVED JOB
# ==========================
@app.route("/remove_saved_job/<int:job_id>")
def remove_saved_job(job_id):
    try:
        session_id = get_session_id()
        
        conn = get_db()
        conn.execute("""
        DELETE FROM saved_jobs 
        WHERE job_id = ? AND session_id = ?
        """, (job_id, session_id))
        conn.commit()
        conn.close()
        
        flash('Job removed from saved', 'success')
    except sqlite3.OperationalError:
        flash('Error removing job', 'error')
    
    return redirect(url_for('saved_jobs'))

# ==========================
# SAVED JOBS PAGE
# ==========================
@app.route("/saved_jobs")
def saved_jobs():
    session_id = get_session_id()
    jobs = []
    
    try:
        conn = get_db()
        jobs = conn.execute("""
        SELECT j.*, sj.saved_date 
        FROM saved_jobs sj
        JOIN jobs j ON sj.job_id = j.id
        WHERE sj.session_id = ?
        ORDER BY sj.saved_date DESC
        """, (session_id,)).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        flash('No saved jobs yet', 'info')
    
    return render_template("saved_jobs.html", jobs=jobs)

# ==========================
# APPLY FOR JOB
# ==========================
@app.route("/apply/<int:job_id>", methods=["GET", "POST"])
def apply_job(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('index'))
    
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        
        # Validate email
        if not validate_email(email):
            flash('Please enter a valid email address', 'error')
            return render_template("apply.html", job=job)
        
        # Create applications table if not exists
        conn.execute("""
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            applicant_name TEXT,
            applicant_email TEXT,
            applicant_phone TEXT,
            application_date TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
        """)
        
        # Save application
        conn.execute("""
        INSERT INTO applications (job_id, applicant_name, applicant_email, applicant_phone)
        VALUES (?, ?, ?, ?)
        """, (job_id, name, email, phone))
        conn.commit()
        conn.close()
        
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('job_details', id=job_id))
    
    conn.close()
    return render_template("apply.html", job=job)

# ==========================
# BROWSE BY FIELD
# ==========================
@app.route("/field/<field_name>")
def browse_by_field(field_name):
    conn = get_db()
    jobs = conn.execute("""
    SELECT * FROM jobs
    WHERE field LIKE ?
    ORDER BY id DESC
    """, (f"%{field_name}%",)).fetchall()
    
    try:
        field_info = conn.execute("""
        SELECT * FROM categories WHERE name LIKE ?
        """, (f"%{field_name}%",)).fetchone()
    except sqlite3.OperationalError:
        field_info = None
    
    conn.close()
    
    return render_template("browse_field.html", 
                         jobs=jobs, 
                         field_name=field_name,
                         field_info=field_info)

# ==========================
# BROWSE BY COMPANY
# ==========================
@app.route("/company/<company_name>")
def browse_by_company(company_name):
    conn = get_db()
    jobs = conn.execute("""
    SELECT * FROM jobs
    WHERE company = ?
    ORDER BY id DESC
    """, (company_name,)).fetchall()
    
    # Get company stats
    stats = conn.execute("""
    SELECT COUNT(*) as job_count, 
           COUNT(DISTINCT location) as location_count,
           COUNT(DISTINCT field) as field_count
    FROM jobs
    WHERE company = ?
    """, (company_name,)).fetchone()
    
    conn.close()
    
    return render_template("browse_company.html", 
                         jobs=jobs, 
                         company_name=company_name,
                         stats=stats)

# ==========================
# QUICK APPLY (AJAX)
# ==========================
@app.route("/quick_apply", methods=["POST"])
def quick_apply():
    job_id = request.form.get("job_id")
    email = request.form.get("email")
    
    if not validate_email(email):
        return jsonify({"success": False, "message": "Invalid email"})
    
    conn = get_db()
    
    # Create applications table if not exists
    conn.execute("""
    CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        applicant_name TEXT,
        applicant_email TEXT,
        applicant_phone TEXT,
        application_date TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending'
    )
    """)
    
    conn.execute("""
    INSERT INTO applications (job_id, applicant_email, application_date)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (job_id, email))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Application submitted!"})

# ==========================
# JOB ALERTS
# ==========================
@app.route("/job_alerts", methods=["GET", "POST"])
def job_alerts():
    if request.method == "POST":
        email = request.form["email"]
        field = request.form.get("field", "")
        
        if validate_email(email):
            # Store in session for now
            session['alert_email'] = email
            session['alert_field'] = field
            flash('Job alert set up successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email address', 'error')
    
    return render_template("job_alerts.html")

# ==========================
# ADMIN LOGIN
# ==========================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        if username == "admin" and password == "admin123":
            session["admin"] = True
            session.permanent = True
            flash('Login successful!', 'success')
            return redirect(url_for("dashboard"))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template("admin_login.html")

# ==========================
# ADMIN DASHBOARD (SAFE VERSION)
# ==========================
@app.route("/dashboard")
def dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    features = get_available_features()
    conn = get_db()
    
    # Get all jobs
    jobs = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
    
    # Get statistics safely
    stats = {
        'total_jobs': conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()['count'],
        'total_applications': 0,
        'total_views': 0,
        'recent_applications': []
    }
    
    # Try to get applications if table exists
    try:
        stats['total_applications'] = conn.execute("SELECT COUNT(*) as count FROM applications").fetchone()['count']
        stats['recent_applications'] = conn.execute("""
            SELECT a.*, j.title 
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            ORDER BY a.application_date DESC
            LIMIT 5
        """).fetchall()
    except sqlite3.OperationalError:
        pass
    
    # Try to get total views if column exists
    if features['views']:
        try:
            total_views = conn.execute("SELECT SUM(views) as total FROM jobs").fetchone()
            stats['total_views'] = total_views['total'] if total_views and total_views['total'] else 0
        except sqlite3.OperationalError:
            pass
    
    conn.close()
    
    return render_template("admin_dashboard.html", 
                         jobs=jobs, 
                         stats=stats,
                         features=features)

# ==========================
# ADD JOB (SAFE VERSION)
# ==========================
@app.route("/add_job", methods=["GET", "POST"])
def add_job():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    features = get_available_features()
    
    if request.method == "POST":
        # Get base form data
        title = request.form["title"]
        company = request.form["company"]
        location = request.form["location"]
        field = request.form["field"]
        qualification = request.form["qualification"]
        description = request.form["description"]
        requirements = request.form["requirements"]
        application_link = request.form["application_link"]
        closing_date = request.form["closing_date"]
        
        conn = get_db()
        
        # Build dynamic insert based on available columns
        if features['salary_range'] or features['job_type'] or features['experience_level'] or features['is_featured']:
            # Get optional fields
            salary_range = request.form.get("salary_range", "")
            job_type = request.form.get("job_type", "Full-time")
            experience_level = request.form.get("experience_level", "Entry Level")
            is_featured = 1 if request.form.get("is_featured") else 0
            
            # Check which columns actually exist
            columns = ["title", "company", "location", "field", "qualification",
                      "description", "requirements", "application_link", "closing_date"]
            values = [title, company, location, field, qualification,
                     description, requirements, application_link, closing_date]
            placeholders = ["?"] * 9
            
            if features['salary_range'] and 'salary_range' in request.form:
                columns.append("salary_range")
                values.append(salary_range)
                placeholders.append("?")
            
            if features['job_type'] and 'job_type' in request.form:
                columns.append("job_type")
                values.append(job_type)
                placeholders.append("?")
            
            if features['experience_level'] and 'experience_level' in request.form:
                columns.append("experience_level")
                values.append(experience_level)
                placeholders.append("?")
            
            if features['is_featured']:
                columns.append("is_featured")
                values.append(is_featured)
                placeholders.append("?")
            
            query = f"""
            INSERT INTO jobs ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            """
            conn.execute(query, values)
        else:
            # Basic insert only
            conn.execute("""
            INSERT INTO jobs
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date))
        
        conn.commit()
        conn.close()
        
        flash('Job added successfully!', 'success')
        return redirect(url_for("dashboard"))
    
    return render_template("add_job.html", features=features)

# ==========================
# EDIT JOB (SAFE VERSION)
# ==========================
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_job(id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    features = get_available_features()
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (id,)).fetchone()
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        # Get base form data
        title = request.form["title"]
        company = request.form["company"]
        location = request.form["location"]
        field = request.form["field"]
        qualification = request.form["qualification"]
        description = request.form["description"]
        requirements = request.form["requirements"]
        application_link = request.form["application_link"]
        closing_date = request.form["closing_date"]
        
        # Build dynamic update based on available columns
        if features['salary_range'] or features['job_type'] or features['experience_level'] or features['is_featured']:
            # Get optional fields
            salary_range = request.form.get("salary_range", "")
            job_type = request.form.get("job_type", "Full-time")
            experience_level = request.form.get("experience_level", "Entry Level")
            is_featured = 1 if request.form.get("is_featured") else 0
            
            # Build SET clause dynamically
            set_clause = "title=?, company=?, location=?, field=?, qualification=?, description=?, requirements=?, application_link=?, closing_date=?"
            values = [title, company, location, field, qualification,
                     description, requirements, application_link, closing_date]
            
            if features['salary_range']:
                set_clause += ", salary_range=?"
                values.append(salary_range)
            
            if features['job_type']:
                set_clause += ", job_type=?"
                values.append(job_type)
            
            if features['experience_level']:
                set_clause += ", experience_level=?"
                values.append(experience_level)
            
            if features['is_featured']:
                set_clause += ", is_featured=?"
                values.append(is_featured)
            
            values.append(id)  # for WHERE clause
            
            query = f"UPDATE jobs SET {set_clause} WHERE id=?"
            conn.execute(query, values)
        else:
            # Basic update only
            conn.execute("""
            UPDATE jobs SET
            title=?, company=?, location=?, field=?, qualification=?,
            description=?, requirements=?, application_link=?, closing_date=?
            WHERE id=?
            """,
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date, id))
        
        conn.commit()
        flash('Job updated successfully!', 'success')
        return redirect(url_for("dashboard"))
    
    conn.close()
    return render_template("edit_job.html", job=job, features=features)

# ==========================
# DELETE JOB
# ==========================
@app.route("/delete/<int:id>")
def delete_job(id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    flash('Job deleted successfully!', 'success')
    return redirect(url_for("dashboard"))

# ==========================
# BULK DELETE JOBS
# ==========================
@app.route("/bulk_delete", methods=["POST"])
def bulk_delete():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    job_ids = request.form.getlist("job_ids")
    
    if job_ids:
        conn = get_db()
        placeholders = ','.join(['?'] * len(job_ids))
        conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
        conn.commit()
        conn.close()
        flash(f'{len(job_ids)} jobs deleted successfully!', 'success')
    
    return redirect(url_for("dashboard"))

# ==========================
# EXPORT JOBS TO CSV
# ==========================
@app.route("/export_jobs")
def export_jobs():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    import csv
    from io import StringIO
    from flask import Response
    
    features = get_available_features()
    conn = get_db()
    jobs = conn.execute("SELECT * FROM jobs").fetchall()
    conn.close()
    
    # Create CSV
    si = StringIO()
    cw = csv.writer(si)
    
    # Write headers
    headers = ['ID', 'Title', 'Company', 'Location', 'Field', 'Qualification',
               'Description', 'Requirements', 'Application Link', 'Closing Date']
    
    if features['views']:
        headers.append('Views')
    if features['is_featured']:
        headers.append('Featured')
    
    cw.writerow(headers)
    
    # Write data
    for job in jobs:
        row = [job['id'], job['title'], job['company'], job['location'],
               job['field'], job['qualification'], job['description'],
               job['requirements'], job['application_link'], job['closing_date']]
        
        if features['views']:
            row.append(job['views'] if job['views'] else 0)
        if features['is_featured']:
            row.append(job['is_featured'] if job['is_featured'] else 0)
        
        cw.writerow(row)
    
    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=jobs_export.csv"}
    )

# ==========================
# STATISTICS PAGE
# ==========================
@app.route("/statistics")
def statistics():
    features = get_available_features()
    conn = get_db()
    
    # Jobs by field
    jobs_by_field = conn.execute("""
    SELECT field, COUNT(*) as count 
    FROM jobs 
    GROUP BY field 
    ORDER BY count DESC
    """).fetchall()
    
    # Jobs by location
    jobs_by_location = conn.execute("""
    SELECT location, COUNT(*) as count 
    FROM jobs 
    GROUP BY location 
    ORDER BY count DESC 
    LIMIT 10
    """).fetchall()
    
    # Jobs by company
    jobs_by_company = conn.execute("""
    SELECT company, COUNT(*) as count 
    FROM jobs 
    GROUP BY company 
    ORDER BY count DESC 
    LIMIT 10
    """).fetchall()
    
    # Monthly trends (if created_date exists)
    monthly_trends = []
    if features['created_date']:
        try:
            monthly_trends = conn.execute("""
            SELECT strftime('%Y-%m', created_date) as month, 
                   COUNT(*) as count 
            FROM jobs 
            WHERE created_date IS NOT NULL 
            GROUP BY month 
            ORDER BY month DESC 
            LIMIT 12
            """).fetchall()
        except sqlite3.OperationalError:
            pass
    
    conn.close()
    
    return render_template("statistics.html",
                         jobs_by_field=jobs_by_field,
                         jobs_by_location=jobs_by_location,
                         jobs_by_company=jobs_by_company,
                         monthly_trends=monthly_trends,
                         features=features)

# ==========================
# API ENDPOINTS
# ==========================

@app.route("/api/jobs")
def api_jobs():
    """API endpoint to get jobs in JSON format"""
    features = get_available_features()
    conn = get_db()
    
    if features['views']:
        jobs = conn.execute("""
        SELECT id, title, company, location, field, 
               qualification, closing_date, views 
        FROM jobs 
        ORDER BY id DESC
        """).fetchall()
    else:
        jobs = conn.execute("""
        SELECT id, title, company, location, field, 
               qualification, closing_date 
        FROM jobs 
        ORDER BY id DESC
        """).fetchall()
    
    conn.close()
    
    return jsonify([dict(job) for job in jobs])

@app.route("/api/job/<int:id>")
def api_job(id):
    """API endpoint to get single job in JSON format"""
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (id,)).fetchone()
    conn.close()
    
    if job:
        return jsonify(dict(job))
    return jsonify({"error": "Job not found"}), 404

# ==========================
# ERROR HANDLERS
# ==========================

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

# ==========================
# LOGOUT
# ==========================
@app.route("/logout")
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for("index"))

# ==========================
# RUN MIGRATION CHECK
# ==========================
@app.route("/check_migration")
def check_migration():
    """Check database migration status"""
    features = get_available_features()
    missing_features = [name for name, available in features.items() if not available]
    
    if missing_features:
        message = f"Missing features: {', '.join(missing_features)}. Please run migrate_db.py"
        flash(message, 'warning')
    else:
        flash('All features are available!', 'success')
    
    return redirect(url_for('index'))

# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    app.run(debug=True)