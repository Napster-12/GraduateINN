from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = "graduate_inn_secret_key"

DATABASE = "database.db"


# DATABASE CONNECTION
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# INITIALIZE DATABASE
def init_db():
    conn = get_db()

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


init_db()


# ==========================
# HOME PAGE
# ==========================
@app.route("/")
def index():

    conn = get_db()

    jobs = conn.execute("""
    SELECT * FROM jobs
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("index.html", jobs=jobs)


# ==========================
# JOB DETAILS
# ==========================
@app.route("/job/<int:id>")
def job_details(id):

    conn = get_db()

    job = conn.execute("""
    SELECT * FROM jobs
    WHERE id = ?
    """, (id,)).fetchone()

    conn.close()

    return render_template("job_details.html", job=job)


# ==========================
# SEARCH JOBS
# ==========================
@app.route("/search")
def search():

    query = request.args.get("q")

    conn = get_db()

    jobs = conn.execute("""
    SELECT * FROM jobs
    WHERE title LIKE ?
    OR company LIKE ?
    OR field LIKE ?
    OR location LIKE ?
    """,
    (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%")
    ).fetchall()

    conn.close()

    return render_template("index.html", jobs=jobs)


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

            return redirect(url_for("dashboard"))

    return render_template("admin_login.html")


# ==========================
# ADMIN DASHBOARD
# ==========================
@app.route("/dashboard")
def dashboard():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    jobs = conn.execute("""
    SELECT * FROM jobs
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("admin_dashboard.html", jobs=jobs)


# ==========================
# ADD JOB
# ==========================
@app.route("/add_job", methods=["GET", "POST"])
def add_job():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    if request.method == "POST":

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

        conn.execute("""
        INSERT INTO jobs
        (title, company, location, field, qualification,
        description, requirements, application_link, closing_date)

        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (title, company, location, field,
         qualification, description,
         requirements, application_link,
         closing_date)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("add_job.html")


# ==========================
# EDIT JOB
# ==========================
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_job(id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    job = conn.execute("""
    SELECT * FROM jobs
    WHERE id = ?
    """, (id,)).fetchone()

    if request.method == "POST":

        title = request.form["title"]
        company = request.form["company"]
        location = request.form["location"]
        field = request.form["field"]
        qualification = request.form["qualification"]
        description = request.form["description"]
        requirements = request.form["requirements"]
        application_link = request.form["application_link"]
        closing_date = request.form["closing_date"]

        conn.execute("""
        UPDATE jobs SET
        title=?,
        company=?,
        location=?,
        field=?,
        qualification=?,
        description=?,
        requirements=?,
        application_link=?,
        closing_date=?

        WHERE id=?
        """,
        (title, company, location, field,
         qualification, description,
         requirements, application_link,
         closing_date, id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("edit_job.html", job=job)


# ==========================
# DELETE JOB
# ==========================
@app.route("/delete/<int:id>")
def delete_job(id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db()

    conn.execute("""
    DELETE FROM jobs
    WHERE id = ?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


# ==========================
# LOGOUT
# ==========================
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    app.run(debug=True)