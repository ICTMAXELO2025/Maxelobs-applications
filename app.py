from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
import re
from datetime import datetime
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import io
import time

app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-for-development')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size

# Allowed file extensions for CVs
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_database_url(url):
    """Clean and fix malformed database URLs"""
    if not url:
        return None
    
    # Remove spaces and fix common issues
    url = url.strip()
    url = url.replace(' ', '')
    
    # Fix the typo in the protocol (postgresal -> postgres)
    url = url.replace('postgresal://', 'postgresql://')
    
    # Ensure it starts with postgresql://
    if not url.startswith('postgresql://'):
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql://', 1)
        else:
            # If it doesn't start with any protocol, add postgresql://
            url = 'postgresql://' + url
    
    return url

def get_database_url():
    database_url = os.environ.get('DATABASE_URL')
    print(f"Original DATABASE_URL: {database_url}")  # Debug
    
    if database_url:
        cleaned_url = clean_database_url(database_url)
        print(f"Cleaned DATABASE_URL: {cleaned_url}")  # Debug
        return cleaned_url
    else:
        # Fallback for local development
        return "postgresql://postgres:Maxelo%402023@localhost:5432/wil_database"

def get_db_connection():
    """Get database connection for Render with retry logic"""
    max_retries = 3
    database_url = get_database_url()
    
    print(f"Attempting to connect with URL: {database_url}")  # Debug
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                database_url,
                connect_timeout=10
            )
            print("✅ Database connection successful")
            return conn
        except Exception as e:
            print(f"❌ Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retrying
                continue
            return None

def init_database():
    """Initialize database tables with better error handling"""
    conn = get_db_connection()
    if not conn:
        print("❌ Cannot initialize database - no connection")
        return False
        
    try:
        cur = conn.cursor()
        
        # Check if applications table exists and has correct structure
        cur.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                institution VARCHAR(100) NOT NULL,
                course VARCHAR(100) NOT NULL,
                position VARCHAR(100) NOT NULL,
                cv_filename VARCHAR(255),
                cv_data BYTEA,
                application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'Pending'
            )
        ''')
        
        # Create admin table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id SERIAL PRIMARY KEY,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Default admin credentials
        DEFAULT_ADMIN_EMAIL = "admin@maxelo.co.za"
        DEFAULT_ADMIN_PASSWORD = "Admin@maxelo2025!"
        
        # Check if admin exists, if not create default admin
        cur.execute('SELECT * FROM admin WHERE email = %s', (DEFAULT_ADMIN_EMAIL,))
        if not cur.fetchone():
            hashed_password = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
            cur.execute(
                'INSERT INTO admin (email, password) VALUES (%s, %s)',
                (DEFAULT_ADMIN_EMAIL, hashed_password)
            )
            print("✅ Default admin created")
        
        conn.commit()
        print("✅ Database initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/application', methods=['GET', 'POST'])
def application():
    if request.method == 'POST':
        try:
            # Get form data
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            institution = request.form.get('institution')
            course = request.form.get('course')
            position = request.form.get('position')
            cv_file = request.files.get('cv')
            
            # Validate required fields
            if not all([full_name, email, phone, institution, course, position]):
                flash('Please fill in all required fields', 'error')
                return render_template('application.html')
            
            # Validate CV file
            if not cv_file or cv_file.filename == '':
                flash('Please upload your CV', 'error')
                return render_template('application.html')
            
            if not allowed_file(cv_file.filename):
                flash('Invalid file type. Please upload PDF or Word document.', 'error')
                return render_template('application.html')
            
            # Save CV file
            filename = secure_filename(cv_file.filename)
            cv_data = cv_file.read()
            
            # Validate file size (5MB max)
            if len(cv_data) > 5 * 1024 * 1024:
                flash('File size too large. Please upload a file smaller than 5MB.', 'error')
                return render_template('application.html')
            
            # Save to database
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO applications 
                    (full_name, email, phone, institution, course, position, cv_filename, cv_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (full_name, email, phone, institution, course, position, filename, cv_data))
                
                conn.commit()
                cur.close()
                conn.close()
                
                flash('Application submitted successfully! We will contact you soon.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Database connection error. Please try again.', 'error')
            
        except Exception as e:
            print(f"❌ Application submission error: {e}")
            flash('Error submitting application. Please try again.', 'error')
    
    return render_template('application.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please enter both email and password', 'error')
            return render_template('admin_login.html')
        
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('SELECT * FROM admin WHERE email = %s', (email,))
                admin = cur.fetchone()
                cur.close()
                conn.close()
                
                if admin and check_password_hash(admin[2], password):
                    session['admin_logged_in'] = True
                    session['admin_email'] = email
                    session['admin_id'] = admin[0]
                    flash('Login successful!', 'success')
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash('Invalid email or password', 'error')
            else:
                flash('Database connection error', 'error')
                
        except Exception as e:
            print(f"❌ Admin login error: {e}")
            flash('Login error. Please try again.', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([email, new_password, confirm_password]):
            flash('Please fill in all fields', 'error')
            return render_template('admin_forgot_password.html')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('admin_forgot_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('admin_forgot_password.html')
        
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('SELECT * FROM admin WHERE email = %s', (email,))
                admin = cur.fetchone()
                
                if admin:
                    hashed_password = generate_password_hash(new_password)
                    cur.execute(
                        'UPDATE admin SET password = %s WHERE email = %s',
                        (hashed_password, email)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    flash('Password reset successfully! You can now login with your new password.', 'success')
                    return redirect(url_for('admin_login'))
                else:
                    flash('Admin email not found', 'error')
            else:
                flash('Database connection error', 'error')
                
        except Exception as e:
            print(f"❌ Password reset error: {e}")
            flash('Error resetting password. Please try again.', 'error')
    
    return render_template('admin_forgot_password.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT id, full_name, email, phone, institution, course, position, 
                       cv_filename, application_date, status 
                FROM applications 
                ORDER BY application_date DESC
            ''')
            applications = cur.fetchall()
            cur.close()
            conn.close()
            return render_template('admin_dashboard.html', applications=applications)
        else:
            flash('Database connection error', 'error')
            return render_template('admin_dashboard.html', applications=[])
    except Exception as e:
        print(f"❌ Admin dashboard error: {e}")
        flash('Error loading applications', 'error')
        return render_template('admin_dashboard.html', applications=[])

@app.route('/admin/update-status/<int:app_id>', methods=['POST'])
def update_application_status(app_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    new_status = request.form.get('status')
    
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute(
                'UPDATE applications SET status = %s WHERE id = %s',
                (new_status, app_id)
            )
            conn.commit()
            cur.close()
            conn.close()
            
            flash(f'Application status updated to {new_status}', 'success')
        else:
            flash('Database connection error', 'error')
            
    except Exception as e:
        print(f"❌ Status update error: {e}")
        flash('Error updating application status', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/download-cv/<int:app_id>')
def download_cv(app_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT cv_filename, cv_data FROM applications WHERE id = %s', (app_id,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            
            if result and result[1]:
                filename, cv_data = result
                return send_file(
                    io.BytesIO(cv_data),
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/octet-stream'
                )
            else:
                flash('CV not found', 'error')
        else:
            flash('Database connection error', 'error')
            
    except Exception as e:
        print(f"❌ CV download error: {e}")
        flash('Error downloading CV', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('admin_login'))

@app.route('/test-db')
def test_db():
    """Test database connection"""
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT version()')
            db_version = cur.fetchone()
            
            # Test applications table
            cur.execute('SELECT COUNT(*) FROM applications')
            app_count = cur.fetchone()[0]
            
            cur.close()
            conn.close()
            
            return f"""
            <h2>✅ Database Connection Successful</h2>
            <p><strong>Database Version:</strong> {db_version[0]}</p>
            <p><strong>Applications in database:</strong> {app_count}</p>
            <p><strong>Database URL:</strong> {get_database_url()}</p>
            """
        else:
            return "<h2>❌ Database Connection Failed</h2>"
    except Exception as e:
        return f"<h2>❌ Database Error</h2><p>{str(e)}</p>"

@app.route('/debug-env')
def debug_env():
    """Debug environment variables"""
    import os
    db_url = os.environ.get('DATABASE_URL')
    return f"""
    <h2>Environment Debug</h2>
    <p><strong>DATABASE_URL exists:</strong> {bool(db_url)}</p>
    <p><strong>DATABASE_URL value:</strong> {db_url}</p>
    <p><strong>Cleaned DATABASE_URL:</strong> {get_database_url()}</p>
    """

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return "OK", 200
        else:
            return "Database connection failed", 500
    except:
        return "Database connection failed", 500

# Initialize database when app starts
print("🚀 Starting Maxelo Technologies WIL Application...")
print("🔧 Initializing database...")
if init_database():
    print("✅ Startup tasks completed successfully")
else:
    print("❌ Startup tasks failed")

if __name__ == '__main__':
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    # Start Flask application
    app.run(host='0.0.0.0', port=port, debug=False)