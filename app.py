from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import io
import time

app = Flask(__name__)

# ✅ FIXED: Corrected secret_key (lowercase k) and proper quotes
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-for-development')

# Allowed file extensions for CVs
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Get database connection using External Database URL"""
    try:
        # Get the External Database URL from environment variables
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            print("❌ DATABASE_URL environment variable not found")
            print("💡 Please set DATABASE_URL in Render environment variables")
            return None
        
        print(f"🔗 Using Database URL: {database_url.split('@')[0]}@***")  # Hide password in logs
        
        # Connect using the external URL
        conn = psycopg2.connect(database_url, connect_timeout=10)
        print("✅ Database connection successful")
        return conn
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def init_database():
    """Initialize database tables"""
    print("🔧 Initializing database...")
    conn = get_db_connection()
    if not conn:
        print("❌ Cannot initialize database - no connection")
        return False
        
    try:
        cur = conn.cursor()
        
        # Create applications table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                institution VARCHAR(100) NOT NULL,
                course VARCHAR(100) NOT NULL,
                
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

# Initialize database when app starts
print("🚀 Starting Maxelo Technologies WIL Application...")
init_database()

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
           
            cv_file = request.files.get('cv')
            
            print(f"📝 Application submitted: {full_name}, {email}")  # Debug print
            
            # Validate required fields
            if not all([full_name, email, phone, institution, course]):
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
                    (full_name, email, phone, institution, course, cv_filename, cv_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s,)
                ''', (full_name, email, phone, institution, course, filename, cv_data))
                
                conn.commit()
                cur.close()
                conn.close()
                
                print(f"✅ Application saved to database: {full_name}")  # Debug print
                flash('Application submitted successfully! We will contact you soon.', 'success')
                return redirect(url_for('index'))
            else:
                print("❌ Database connection failed during application submission")
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
                SELECT id, full_name, email, phone, institution, course, 
                       cv_filename, application_date, status 
                FROM applications 
                ORDER BY application_date DESC
            ''')
            columns = [desc[0] for desc in cur.description]
            applications = []
            for row in cur.fetchall():
                applications.append(dict(zip(columns, row)))
            
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
            
            # Test admin table
            cur.execute('SELECT COUNT(*) FROM admin')
            admin_count = cur.fetchone()[0]
            
            cur.close()
            conn.close()
            
            return f"""
            <h2>✅ Database Connection Successful</h2>
            <p><strong>Database Version:</strong> {db_version[0]}</p>
            <p><strong>Applications in database:</strong> {app_count}</p>
            <p><strong>Admin users:</strong> {admin_count}</p>
            <p style="color: green; font-weight: bold;">✅ Your database is properly connected!</p>
            """
        else:
            return """
            <h2>❌ Database Connection Failed</h2>
            <p>Please check your DATABASE_URL environment variable.</p>
            """
    except Exception as e:
        return f"<h2>❌ Database Error</h2><p>{str(e)}</p>"

@app.route('/debug-env')
def debug_env():
    """Debug environment variables"""
    database_url = os.environ.get('DATABASE_URL', 'NOT_SET')
    secret_key = os.environ.get('SECRET_KEY', 'NOT_SET')
    
    # Hide password for security
    safe_url = database_url
    if '@' in database_url:
        safe_url = database_url.split('@')[0] + '@***'
    
    return f"""
    <h2>Environment Debug</h2>
    <p><strong>DATABASE_URL:</strong> {safe_url}</p>
    <p><strong>DATABASE_URL exists:</strong> {bool(database_url)}</p>
    <p><strong>SECRET_KEY exists:</strong> {bool(secret_key)}</p>
    <p><strong>SECRET_KEY length:</strong> {len(secret_key) if secret_key != 'NOT_SET' else 0}</p>
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

# ✅ FIXED: These routes were incorrectly indented inside health_check function
@app.route('/debug-applications')
def debug_applications():
    """Debug route to check applications directly"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            
            # Check if applications table exists
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'applications'
            """)
            table_exists = cur.fetchone()
            
            # Get all applications with detailed info
            cur.execute('''
                SELECT id, full_name, email, phone, institution, course, 
                       cv_filename, application_date, status 
                FROM applications 
                ORDER BY application_date DESC
            ''')
            applications = cur.fetchall()
            
            # Get table structure
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'applications' 
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()
            
            cur.close()
            conn.close()
            
            return f"""
            <h2>Applications Debug Info</h2>
            <p><strong>Applications table exists:</strong> {bool(table_exists)}</p>
            <p><strong>Number of applications:</strong> {len(applications)}</p>
            <p><strong>Table columns:</strong> {columns}</p>
            <h3>Applications Data:</h3>
            <pre>{applications}</pre>
            """
        else:
            return "<h2>Database connection failed</h2>"
    except Exception as e:
        return f"<h2>Error: {str(e)}</h2>"

@app.route('/check-db-tables')
def check_db_tables():
    """Check all tables in the database"""
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = cur.fetchall()
            cur.close()
            conn.close()
            
            table_list = [table[0] for table in tables]
            return f"""
            <h2>Database Tables</h2>
            <p><strong>Tables found:</strong> {table_list}</p>
            <p><strong>Total tables:</strong> {len(tables)}</p>
            """
        else:
            return "<h2>Database connection failed</h2>"
    except Exception as e:
        return f"<h2>Error: {str(e)}</h2>"

@app.route('/add-test-application')
def add_test_application():
    """Add a test application for debugging"""
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO applications 
                (full_name, email, phone, institution, course,  cv_filename)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                'Test Student', 
                'test@student.com', 
                '1234567890', 
                'Test University', 
                 
                'Software Development', 
                'test_cv.pdf'
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return "✅ Test application added successfully! Check your admin dashboard."
        else:
            return "❌ Database connection failed"
    except Exception as e:
        return f"❌ Error: {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)