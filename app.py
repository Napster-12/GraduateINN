from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Mail, Message
import sqlite3
from datetime import datetime, timedelta
import re
import secrets
from functools import wraps
import hashlib
import csv
from io import StringIO
from flask import Response

app = Flask(__name__)
app.secret_key = "graduate_inn_secret_key_change_this_in_production"
app.permanent_session_lifetime = timedelta(hours=2)

# ==========================
# FLASK-MAIL CONFIGURATION
# ==========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'codnellsmall@gmail.com'
app.config['MAIL_PASSWORD'] = 'seob qyjh sqzu ifoq'
app.config['MAIL_DEFAULT_SENDER'] = ('GraduateINN', 'codnellsmall@gmail.com')

mail = Mail(app)

DATABASE = "database.db"

# ==========================
# DATABASE CONNECTION
# ==========================
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================
# CHECK IF COLUMN EXISTS
# ==========================
def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    conn = get_db()
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    conn.close()
    return column_name in columns

# ==========================
# GET AVAILABLE FEATURES
# ==========================
def get_available_features():
    """Check which features are available in the database"""
    return {
        'is_featured': column_exists('jobs', 'is_featured'),
        'views': column_exists('jobs', 'views'),
        'job_type': column_exists('jobs', 'job_type'),
        'experience_level': column_exists('jobs', 'experience_level'),
        'salary_range': column_exists('jobs', 'salary_range')
    }

# ==========================
# HASH PASSWORD
# ==========================
def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    """Verify a password against its hash"""
    return hash_password(password) == hashed

# ==========================
# INITIALIZE DATABASE
# ==========================
def init_db():
    """Initialize database with all tables"""
    conn = get_db()
    
    # Create jobs table
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
        closing_date TEXT,
        created_date TEXT DEFAULT CURRENT_DATE,
        salary_range TEXT,
        job_type TEXT,
        experience_level TEXT,
        views INTEGER DEFAULT 0,
        is_featured INTEGER DEFAULT 0,
        posted_by INTEGER,
        FOREIGN KEY (posted_by) REFERENCES users(id)
    )
    """)
    
    # Create categories table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS categories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        icon TEXT,
        job_count INTEGER DEFAULT 0
    )
    """)
    
    # Create saved jobs table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS saved_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        user_id INTEGER,
        saved_date TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    
    # Create applications table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        user_id INTEGER,
        applicant_name TEXT,
        applicant_email TEXT,
        applicant_phone TEXT,
        cover_letter TEXT,
        application_date TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
   
    conn.commit()
    
    # Insert default categories if empty
    categories = conn.execute("SELECT COUNT(*) as count FROM categories").fetchone()
    if categories['count'] == 0:
        default_cats = [
            ('Engineering', 'bi-tools'),
            ('Information Technology', 'bi-laptop'),
            ('Accounting', 'bi-calculator'),
            ('Marketing', 'bi-megaphone'),
            ('Finance', 'bi-graph-up'),
            ('Human Resources', 'bi-people'),
            ('Sales', 'bi-phone'),
            ('Logistics', 'bi-truck'),
            ('Healthcare', 'bi-heart-pulse'),
            ('Education', 'bi-book')
        ]
        conn.executemany("INSERT INTO categories (name, icon) VALUES (?, ?)", default_cats)
        conn.commit()
    
    # Insert default admin user if not exists
    admin = conn.execute("SELECT * FROM users WHERE email = ?", ("admin@graduateinn.com",)).fetchone()
    if not admin:
        hashed_password = hash_password("admin123")
        conn.execute("""
        INSERT INTO users (full_name, email, password, is_admin, is_verified)
        VALUES (?, ?, ?, ?, ?)
        """, ("Administrator", "admin@graduateinn.com", hashed_password, 1, 1))
        conn.commit()
    
    conn.close()
    print("Database initialized successfully")

init_db()



# ==========================
# HELPER FUNCTIONS
# ==========================

def get_session_id():
    """Get or create session ID for saved jobs (backward compatibility)"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return session['session_id']

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    return True, "Password is valid"

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def increment_job_views(job_id):
    """Increment view count for a job"""
    if column_exists('jobs', 'views'):
        conn = get_db()
        try:
            conn.execute("UPDATE jobs SET views = views + 1 WHERE id = ?", (job_id,))
            conn.commit()
        except:
            pass
        finally:
            conn.close()


@app.route("/logout")
def logout():
    """User logout route"""
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))





# ==========================
# HOME PAGE
# ==========================
@app.route("/")
def index():
    features = get_available_features()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    conn = get_db()
    
    # Get paginated jobs
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
    
    # Get categories
    try:
        categories = conn.execute("""
        SELECT c.*, COUNT(j.id) as job_count 
        FROM categories c
        LEFT JOIN jobs j ON j.field = c.name
        GROUP BY c.id
        ORDER BY job_count DESC
        """).fetchall()
    except:
        categories = []
    
    # Get top companies
    top_companies = conn.execute("""
    SELECT company, COUNT(*) as job_count 
    FROM jobs 
    GROUP BY company 
    ORDER BY job_count DESC 
    LIMIT 10
    """).fetchall()
    
    # Get featured jobs
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
# JOB DETAILS
# ==========================
@app.route("/job/<int:id>")
def job_details(id):
    features = get_available_features()
    
    # Increment view count
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
    
    # Check if job is saved by user
    is_saved = False
    if 'user_id' in session:
        saved = conn.execute("""
        SELECT id FROM saved_jobs 
        WHERE job_id = ? AND user_id = ?
        """, (id, session['user_id'])).fetchone()
        is_saved = bool(saved)
    
    conn.close()
    
    return render_template("job_details.html", 
                         job=job, 
                         similar_jobs=similar_jobs,
                         is_saved=is_saved,
                         features=features)

# ==========================
# SEARCH JOBS
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
# SAVE JOB
# ==========================
@app.route("/save_job/<int:job_id>")
@login_required
def save_job(job_id):
    try:
        conn = get_db()
        
        # Check if already saved
        existing = conn.execute("""
        SELECT id FROM saved_jobs 
        WHERE job_id = ? AND user_id = ?
        """, (job_id, session['user_id'])).fetchone()
        
        if not existing:
            conn.execute("""
            INSERT INTO saved_jobs (job_id, user_id)
            VALUES (?, ?)
            """, (job_id, session['user_id']))
            conn.commit()
            flash('Job saved successfully!', 'success')
        else:
            flash('Job already saved', 'info')
        
        conn.close()
    except Exception as e:
        flash('Error saving job', 'error')
    
    return redirect(request.referrer or url_for('index'))

# ==========================
# REMOVE SAVED JOB
# ==========================
@app.route("/remove_saved_job/<int:job_id>")
@login_required
def remove_saved_job(job_id):
    try:
        conn = get_db()
        conn.execute("""
        DELETE FROM saved_jobs 
        WHERE job_id = ? AND user_id = ?
        """, (job_id, session['user_id']))
        conn.commit()
        conn.close()
        
        flash('Job removed from saved', 'success')
    except:
        flash('Error removing job', 'error')
    
    return redirect(url_for('saved_jobs'))

# ==========================
# SAVED JOBS PAGE
# ==========================
@app.route("/saved_jobs")
@login_required
def saved_jobs():
    jobs = []
    
    try:
        conn = get_db()
        jobs = conn.execute("""
        SELECT j.*, sj.saved_date 
        FROM saved_jobs sj
        JOIN jobs j ON sj.job_id = j.id
        WHERE sj.user_id = ?
        ORDER BY sj.saved_date DESC
        """, (session['user_id'],)).fetchall()
        conn.close()
    except Exception as e:
        flash('Error loading saved jobs', 'error')
        print(f"Error: {e}")
    
    return render_template("saved_jobs.html", jobs=jobs)

# ==========================
# APPLY FOR JOB
# ==========================
@app.route("/apply/<int:job_id>", methods=["GET", "POST"])
@login_required
def apply_job(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('index'))
    
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        cover_letter = request.form.get("cover_letter")
        
        # Validate email
        if not validate_email(email):
            flash('Please enter a valid email address', 'error')
            return render_template("apply.html", job=job)
        
        # Save application
        conn.execute("""
        INSERT INTO applications (job_id, user_id, applicant_name, applicant_email, applicant_phone, cover_letter)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, session['user_id'], name, email, phone, cover_letter))
        conn.commit()
        conn.close()
        
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('job_details', id=job_id))
    
    # Pre-fill with user data
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    conn.close()
    
    return render_template("apply.html", job=job, user=user)

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
    except:
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
    conn.execute("""
    INSERT INTO applications (job_id, applicant_email, application_date)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (job_id, email))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Application submitted!"})



# ==========================
# ADMIN DASHBOARD
# ==========================
@app.route("/dashboard")
@admin_required
def dashboard():
    features = get_available_features()
    conn = get_db()
    
    # Get all jobs
    jobs = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
    
    # Get users count
    users_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    verified_users = conn.execute("SELECT COUNT(*) as count FROM users WHERE is_verified = 1").fetchone()['count']
    
    # Get subscribers count
    subscribers_count = 0
    verified_subscribers = 0
    try:
        subscribers_count = conn.execute("SELECT COUNT(*) as count FROM subscribers").fetchone()['count']
        verified_subscribers = conn.execute("SELECT COUNT(*) as count FROM subscribers WHERE verified = 1").fetchone()['count']
    except:
        pass
    
    # Get statistics
    stats = {
        'total_jobs': conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()['count'],
        'total_applications': 0,
        'total_views': 0,
        'total_users': users_count,
        'verified_users': verified_users,
        'total_subscribers': subscribers_count,
        'verified_subscribers': verified_subscribers,
        'recent_applications': []
    }
    
    # Try to get applications
    try:
        stats['total_applications'] = conn.execute("SELECT COUNT(*) as count FROM applications").fetchone()['count']
        stats['recent_applications'] = conn.execute("""
            SELECT a.*, j.title 
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            ORDER BY a.application_date DESC
            LIMIT 5
        """).fetchall()
    except:
        pass
    
    # Try to get total views
    if features['views']:
        try:
            total_views = conn.execute("SELECT SUM(views) as total FROM jobs").fetchone()
            stats['total_views'] = total_views['total'] if total_views and total_views['total'] else 0
        except:
            pass
    
    conn.close()
    
    return render_template("admin_dashboard.html", 
                         jobs=jobs, 
                         stats=stats,
                         features=features)


# ==========================
# ADD JOB
# ==========================
@app.route("/add_job", methods=["GET", "POST"])
@admin_required
def add_job():
    features = get_available_features()
    
    if request.method == "POST":
        # Get form data
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
        
        # Insert job
        if all(features.values()):
            salary_range = request.form.get("salary_range", "")
            job_type = request.form.get("job_type", "Full-time")
            experience_level = request.form.get("experience_level", "Entry Level")
            is_featured = 1 if request.form.get("is_featured") else 0
            
            conn.execute("""
            INSERT INTO jobs
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date,
             salary_range, job_type, experience_level, is_featured, posted_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date,
             salary_range, job_type, experience_level, is_featured, session['user_id']))
        else:
            conn.execute("""
            INSERT INTO jobs
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date, posted_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date, session['user_id']))
        
        conn.commit()
        conn.close()
        
        flash('Job added successfully!', 'success')
        return redirect(url_for("dashboard"))
    
    return render_template("add_job.html", features=features)

# ==========================
# EDIT JOB
# ==========================
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_job(id):
    features = get_available_features()
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (id,)).fetchone()
    
    if request.method == "POST":
        # Get form data
        title = request.form["title"]
        company = request.form["company"]
        location = request.form["location"]
        field = request.form["field"]
        qualification = request.form["qualification"]
        description = request.form["description"]
        requirements = request.form["requirements"]
        application_link = request.form["application_link"]
        closing_date = request.form["closing_date"]
        
        # Update job
        if all(features.values()):
            salary_range = request.form.get("salary_range", "")
            job_type = request.form.get("job_type", "Full-time")
            experience_level = request.form.get("experience_level", "Entry Level")
            is_featured = 1 if request.form.get("is_featured") else 0
            
            conn.execute("""
            UPDATE jobs SET
            title=?, company=?, location=?, field=?, qualification=?,
            description=?, requirements=?, application_link=?, closing_date=?,
            salary_range=?, job_type=?, experience_level=?, is_featured=?
            WHERE id=?
            """,
            (title, company, location, field, qualification,
             description, requirements, application_link, closing_date,
             salary_range, job_type, experience_level, is_featured, id))
        else:
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
@admin_required
def delete_job(id):
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
@admin_required
def bulk_delete():
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
@admin_required
def export_jobs():
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
# ADMIN LOGIN (Legacy)
# ==========================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db()
        # First check if user exists with admin@graduateinn.com
        user = conn.execute("SELECT * FROM users WHERE email = ? AND is_admin = 1", ("admin@graduateinn.com",)).fetchone()
        
        if user and verify_password(password, user['password']):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']
            session['is_admin'] = user['is_admin']
            session.permanent = True
            
            flash('Login successful!', 'success')
            return redirect(url_for("dashboard"))
        else:
            flash('Invalid credentials', 'error')
        conn.close()
    
    return render_template("admin_login.html")

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
    return jsonify({
        "error": "Not Found",
        "message": "The requested resource was not found",
        "status": 404
    }), 404


@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({
        "error": "Internal Server Error",
        "message": "Something went wrong on the server",
        "status": 500
    }), 500

# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    app.run(debug=True)
