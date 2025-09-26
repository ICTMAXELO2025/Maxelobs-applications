from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
from datetime import datetime
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ✅ Use environment variables for configuration
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-for-development')

# ✅ Fixed database configuration for Render
def get_database_url():
    # Render automatically provides DATABASE_URL environment variable
    database_url = os.environ.get('DATABASE_URL')
    
    # If DATABASE_URL exists (on Render), use it directly
    if database_url:
        # Render's DATABASE_URL might be in postgres:// format, convert to postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    else:
        # Fallback for local development only
        return "postgresql://postgres:Maxelo%402023@localhost:5432/wil_database"

def get_db_connection():
    """Get database connection for Render"""
    try:
        conn = psycopg2.connect(get_database_url())
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_database():
    """Initialize database tables"""
    conn = get_db_connection()
    if not conn:
        print("Cannot initialize database - no connection")
        return
        
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
                position VARCHAR(100) NOT NULL,
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
            print("Default admin created")
        
        conn.commit()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# ✅ Test database connection route
@app.route('/test-db')
def test_db():
    """Test database connection"""
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT version()')
            db_version = cur.fetchone()
            cur.close()
            conn.close()
            return f"✅ Database connected successfully. Version: {db_version[0]}"
        else:
            return "❌ Database connection failed"
    except Exception as e:
        return f"❌ Database error: {str(e)}"

# ✅ Application route
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
            
            # Validate required fields
            if not all([full_name, email, phone, institution, course, position]):
                flash('Please fill in all required fields', 'error')
                return render_template('application.html')
            
            # Save to database
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO applications 
                    (full_name, email, phone, institution, course, position)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (full_name, email, phone, institution, course, position))
                
                conn.commit()
                cur.close()
                conn.close()
                
                flash('Application submitted successfully! We will contact you soon.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Database connection error. Please try again.', 'error')
            
        except Exception as e:
            print(f"Application submission error: {e}")
            flash('Error submitting application. Please try again.', 'error')
    
    return render_template('application.html')

# ✅ Basic routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/apply')
def apply():
    return redirect(url_for('application'))

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
            print(f"Admin login error: {e}")
            flash('Login error. Please try again.', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM applications ORDER BY application_date DESC')
            applications = cur.fetchall()
            cur.close()
            conn.close()
            return render_template('admin_dashboard.html', applications=applications)
        else:
            flash('Database connection error', 'error')
            return render_template('admin_dashboard.html', applications=[])
    except Exception as e:
        print(f"Admin dashboard error: {e}")
        flash('Error loading applications', 'error')
        return render_template('admin_dashboard.html', applications=[])

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    # Initialize database
    print("Starting Maxelo Technologies WIL Application...")
    init_database()
    
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    # Start Flask application
    app.run(host='0.0.0.0', port=port, debug=False)