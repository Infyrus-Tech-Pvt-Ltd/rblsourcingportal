# =============================================================================
# IMPORTS AND INITIAL SETUP
# =============================================================================

from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify, Response
from pocketbase import PocketBase
from pocketbase.client import ClientResponseError
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta, timezone
import requests
import os
from math import ceil
from functools import wraps
from flask_login import login_required, LoginManager, UserMixin, login_user, logout_user, current_user

app = Flask(__name__)

# Load .env variables
load_dotenv()

app.secret_key = os.getenv('SECRET_KEY')
DEV_MODE = os.getenv('DEV_MODE', 'False') == 'True'

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================

POCKETBASE_URL = os.getenv('POCKETBASE_URL')
COLLECTION = "products"
CUSTOMER_COLLECTION="Customers"
INQUIRY_COLLECTION = "inquiries"
PRODUCT_COLLECTION = "products"
SUPPLIER_COLLECTION = "suppliers"

CUSTOMERS_PER_PAGE = 5
PRODUCTS_PER_PAGE = 7
INQUIRIES_PER_PAGE = 7
SUPPLIERS_PER_PAGE = 7

pb = PocketBase(POCKETBASE_URL)
# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def record_to_dict(record):
    return {k: getattr(record, k) for k in record.__fields__}  # if __fields__ exists

# Or fallback:
def record_to_dict(record):
    return vars(record)

def parse_iso_datetime_with_tz(dt_str):
    """Parse ISO datetime string and return timezone-aware datetime (assume UTC if naive)."""
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def build_file_urls(record):
    """Build file URLs for uploaded documents in a PocketBase record."""
    base_url = f"{POCKETBASE_URL}/api/files/{COLLECTION}/{record['id']}"
    files = record.get('uploaded_docs', [])
    if not isinstance(files, list):
        files = [files]
    return [f"{base_url}/{f}" for f in files]

def generate_next_product_id():
    res = requests.get(f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records", headers=HEADERS, params={"perPage": 100})
    res.raise_for_status()
    products = res.json().get("items", [])

    max_num = 0
    prefix = f"PROD_{os.getenv('CURRENT_YEAR', '2025')}_"
    for p in products:
        pid = p.get("product_id", "")
        if pid.startswith(prefix):
            try:
                num = int(pid[len(prefix):])
                if num > max_num:
                    max_num = num
            except:
                continue
    next_num = max_num + 1
    return f"{prefix}{str(next_num).zfill(4)}"

def generate_next_customer_id():
    res = requests.get(f"{POCKETBASE_URL}/api/collections/{CUSTOMER_COLLECTION}/records", headers=HEADERS, params={"perPage": 100})
    res.raise_for_status()
    products = res.json().get("items", [])

    max_num = 0
    prefix = f"CUST_{os.getenv('CURRENT_YEAR', '2025')}_"
    for p in products:
        pid = p.get("customer_id", "")
        if pid.startswith(prefix):
            try:
                num = int(pid[len(prefix):])
                if num > max_num:
                    max_num = num
            except:
                continue
    next_num = max_num + 1
    return f"{prefix}{str(next_num).zfill(4)}"

# =============================================================================
# EMAIL CONFIGURATION AND FUNCTIONS
# =============================================================================

SMTP_SERVER = os.getenv('HOST')
SMTP_PORT = os.getenv('PORT')
SMTP_USERNAME = os.getenv('LOGIN')
SMTP_PASSWORD = os.getenv('PASS')
SMTP_FROM = os.getenv('FROM')

def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

def check_and_send_reminders():
    try:
        now = datetime.now(timezone.utc)
        reminders = pb.collection("reminders").get_full_list()

        due_reminders = []
        for reminder in reminders:
            dt_str = getattr(reminder, "datetime", None)
            sent = getattr(reminder, "sent", False)

            if not dt_str:
                continue

            try:
                reminder_dt = parse_iso_datetime_with_tz(dt_str)
            except ValueError:
                # skip invalid datetime formats
                continue

            # Compare aware datetimes safely
            if reminder_dt <= now and not sent:
                due_reminders.append(reminder)

        for reminder in due_reminders:
            to_email = getattr(reminder, "email", None)
            if not to_email:
                continue

            subject = f"Reminder: {getattr(reminder, 'topic', '')}"
            body = (
                f"Hi,\n\nThis is your reminder:\n\n"
                f"Topic: {getattr(reminder, 'topic', '')}\n"
                f"Description: {getattr(reminder, 'description', '')}\n"
                f"Scheduled for: {getattr(reminder, 'datetime', '')}\n\n"
                f"Regards,\nRBL Sourcing Reminder Service"
            )

            send_email(to_email, subject, body)

            # Mark reminder as sent
            pb.collection("reminders").update(reminder.id, {"sent": True})

    except Exception as e:
        print(f"Error checking/sending reminders: {e}")

# =============================================================================
# POCKETBASE AUTHENTICATION AND CONFIGURATION
# =============================================================================

# Authenticate admin and get token for API requests
admin_auth = pb.admins.auth_with_password(
    os.getenv('POCKETBASE_ADMIN_EMAIL'),
    os.getenv('POCKETBASE_ADMIN_PASSWORD')
)
token = admin_auth.token

HEADERS = {
    "Authorization": f"Bearer {token}"
}

def ensure_admin_auth():
    """Ensure PocketBase client is authenticated as admin"""
    try:
        pb.admins.auth_with_password(
            os.getenv('POCKETBASE_ADMIN_EMAIL'),
            os.getenv('POCKETBASE_ADMIN_PASSWORD')
        )
    except Exception as e:
        print(f"Warning: Could not authenticate as admin: {e}")

status_order = [
    ("Inquiry", "🟡", "bg-yellow-500"),
    ("Quoting", "🟠", "bg-orange-600"),
    ("Quotation Finalized", "🟢", "bg-green-600"),
    ("Payment Received", "🔵", "bg-blue-600"),
    ("In Shipment", "🔄", "bg-indigo-600"),
    ("Arrived KTM", "🛬", "bg-purple-600"),
    ("Delivered", "✅", "bg-teal-600"),
    ("Closed", "🌟", "bg-pink-600"),
]

# =============================================================================
# FLASK-LOGIN CONFIGURATION
# =============================================================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email, name):
        self.id = id
        self.email = email
        self.name = name

@login_manager.user_loader
def load_user(user_id):
    # Fetch user from PocketBase by ID
    try:
        user = pb.collection("users").get_one(user_id)
        if user:
            return User(user.id, user.email, getattr(user, 'name', user.email.split('@')[0]))
    except Exception:
        pass
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        try:
            # Authenticate user
            auth_data = pb.collection("users").auth_with_password(email, password)
            # Create Flask-Login user and log in
            user = User(auth_data.record.id, auth_data.record.email, getattr(auth_data.record, 'name', auth_data.record.email.split('@')[0]))
            login_user(user)
            # Store user info in session (optional)
            session['user_id'] = auth_data.record.id
            session['user_email'] = auth_data.record.email
            session['user_name'] = getattr(auth_data.record, 'name', auth_data.record.email.split('@')[0])
            session['user_role'] = getattr(auth_data.record, 'role', 'staff')  # Get user role
            session['auth_token'] = auth_data.token
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash('Invalid credentials', 'error')
            
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        try:
            # Request password reset from PocketBase
            pb.collection('users').request_password_reset(email)
            flash('Password reset email sent! Please check your inbox.', 'success')
            return redirect(url_for('login'))
        except ClientResponseError as e:
            if e.status == 404:
                flash('No account found with that email address.', 'error')
            else:
                flash('Error sending password reset email. Please try again.', 'error')
    
    return render_template('forgot_password.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# =============================================================================
# MAIN DASHBOARD AND HOME ROUTES
# =============================================================================

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/')
def home():
    return render_template('welcome.html')

@app.route("/dashboard")
@login_required
def dashboard():
    # Existing code...
    customers_last_30 = pb.collection("customers").get_full_list()
    recent_customers_count = len(customers_last_30)

    inquiries_last_30 = pb.collection("inquiries").get_full_list()
    new_inquiries_count = len(inquiries_last_30)

    suppliers_last_30 = pb.collection("suppliers").get_full_list()
    supplier_count = len(suppliers_last_30)

    # New chart data preparation
    try:
        # Get all customers and their inquiries
        all_customers = pb.collection("customers").get_full_list()
        all_inquiries = pb.collection("inquiries").get_full_list()
        all_products = pb.collection("products").get_full_list()
        
        # Create product price lookup
        product_prices = {}
        for product in all_products:
            try:
                price = float(getattr(product, 'price', 0) or 0)
                product_prices[product.id] = price
            except:
                product_prices[product.id] = 0
        
        # Prepare customer inquiry data
        customer_inquiry_data = []
        customer_amount_data = []
        
        for customer in all_customers:
            customer_name = getattr(customer, 'name', 'Unknown')
            customer_inquiries = [inq for inq in all_inquiries if getattr(inq, 'customer_id', '') == customer.id]
            inquiry_count = len(customer_inquiries)
            
            # Calculate total amount for this customer
            total_amount = 0
            for inquiry in customer_inquiries:
                product_id = getattr(inquiry, 'product_id', '')
                quantity = getattr(inquiry, 'quantity', 1) or 1
                price = product_prices.get(product_id, 0)
                total_amount += price * quantity
            
            if inquiry_count > 0:  # Only include customers with inquiries
                customer_inquiry_data.append({
                    'customer': customer_name,
                    'inquiries': inquiry_count
                })
                customer_amount_data.append({
                    'customer': customer_name,
                    'amount': total_amount
                })
        
        # Sort by inquiry count for better visualization
        customer_inquiry_data.sort(key=lambda x: x['inquiries'], reverse=True)
        customer_amount_data.sort(key=lambda x: x['amount'], reverse=True)
        
        # Take top 10 for better chart readability
        customer_inquiry_data = customer_inquiry_data[:10]
        customer_amount_data = customer_amount_data[:10]
        
    except Exception as e:
        print(f"Error preparing chart data: {e}")
        customer_inquiry_data = []
        customer_amount_data = []

    return render_template(
        "dashboard.html",
        recent_customers=recent_customers_count,
        new_inquiries=new_inquiries_count,
        orders=supplier_count,
        customer_inquiry_data=customer_inquiry_data,
        customer_amount_data=customer_amount_data
    )

# =============================================================================
# PRODUCT MANAGEMENT ROUTES
# =============================================================================

@app.route('/product')
@login_required
def product_list():
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    filter_str = ''
    if search_query:
        filter_str = (
            f'product_id ~ "{search_query}" || '
            f'name ~ "{search_query}" || '
            f'model ~ "{search_query}"'
        )

    params = {
        "page": page,
        "perPage": PRODUCTS_PER_PAGE,
        "sort": "-created",  # newest first
        "_ts": datetime.utcnow().timestamp()  # avoid cache
    }
    if filter_str:
        params["filter"] = filter_str

    # Fetch products from PocketBase
    res = requests.get(
        f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records",
        headers=HEADERS,
        params=params
    )
    res.raise_for_status()
    data = res.json()
    products = data.get("items", [])
    total_products = data.get("totalItems", 0)

    total_pages = ceil(total_products / PRODUCTS_PER_PAGE)

    # Fetch all suppliers for mapping and full details
    suppliers_res = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records", headers=HEADERS)
    suppliers_res.raise_for_status()
    suppliers_data = suppliers_res.json().get("items", [])

    # Map supplier id → name and full data
    supplier_map = {s["id"]: s for s in suppliers_data}

    products_full = []
    for p in products:
        supplier_id = p.get("supplier")
        if isinstance(supplier_id, list):
            supplier_id = supplier_id[0] if supplier_id else None

        supplier_info = supplier_map.get(supplier_id, {})
        supplier_name = supplier_info.get("name", supplier_id if supplier_id else "Unknown Supplier")

        products_full.append({
            "id": p.get("id"),
            "product_id": p.get("product_id", ""),
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "gross_weight": p.get("gross_weight", ""),
            "product_size": p.get("product_size", ""),
            "hs_code": p.get("hs_code", ""),
            "tax_rate": p.get("tax_rate", ""),
            "vat": p.get("vat", ""),
            "qty_per_box": p.get("qty_per_box", ""),
            "box_size": p.get("box_size", ""),
            "box_weight": p.get("box_weight", ""),
            "buying_rate": p.get("buying_rate", ""),
            "selling_rate": p.get("selling_rate", ""),
            "terms": p.get("terms", ""),
            "specifications": p.get("specifications", ""),
            "supplier": supplier_name,
            "supplier_id": supplier_id,  # Add supplier_id for links
            "supplier_data": {   # send full supplier data for modal
                "name": supplier_info.get("name", ""),
                "email": supplier_info.get("email", ""),
                "phone": supplier_info.get("phone", ""),
                "address": supplier_info.get("address", ""),
                "notes": supplier_info.get("notes", "")
            },
            "model": p.get("model", ""),
            "price": p.get("price", ""),
            "files": build_file_urls(p)
        })

    return render_template(
        "product_list.html",
        products=products_full,
        current_page=page,
        total_pages=total_pages,
        search_query=search_query
    )

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    product_id = request.args.get('id')

    # Fetch all suppliers for dropdown
    suppliers_resp = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records", headers=HEADERS)
    suppliers = suppliers_resp.json().get("items", []) if suppliers_resp.status_code == 200 else []

    product = None
    supplier_name_for_product = None

    # Editing an existing product
    if product_id:
        pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
        resp = requests.get(pb_url, headers=HEADERS)
        if resp.status_code == 200:
            product = resp.json()
            supplier_id = product.get("supplier")
            if supplier_id:
                supplier_resp = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records/{supplier_id}", headers=HEADERS)
                if supplier_resp.status_code == 200:
                    supplier_data = supplier_resp.json()
                    supplier_name_for_product = supplier_data.get("name")

    if request.method == 'POST':
        data = request.form.to_dict()
        files = request.files.getlist('uploaded_docs')

        # Helpers to make sure PocketBase accepts the values
        def safe_str(value):
            return str(value) if value is not None else ""

        def safe_float_str(key):
            try:
                return str(float(data.get(key))) if data.get(key) else ""
            except:
                return ""

        def safe_int_str(key):
            try:
                return str(int(data.get(key))) if data.get(key) else ""
            except:
                return ""

        try:
            price = float(data.get("price", 0))
        except ValueError:
            return "Invalid price", 400

        # Prepare form data for PocketBase
        pb_data = {
            "product_id": data.get("product_id") or generate_next_product_id(),
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "gross_weight": safe_float_str("gross_weight"),
            "product_size": data.get("product_size", ""),
            "hs_code": data.get("hs_code", ""),
            "tax_rate": safe_float_str("tax_rate"),
            "vat": safe_float_str("vat"),
            "qty_per_box": safe_int_str("qty_per_box"),
            "box_size": data.get("box_size", ""),
            "box_weight": safe_float_str("box_weight"),
            "buying_rate": safe_float_str("buying_rate"),
            "selling_rate": safe_float_str("selling_rate"),
            "terms": data.get("terms", ""),
            "specifications": data.get("specifications", ""),
            "supplier": data.get("supplier", ""),  # Must be supplier ID
            "model": data.get("model", ""),
            "price": safe_str(price),
        }

        # Prepare files
        files_payload = []
        for f in files:
            if f.filename != '':
                files_payload.append(('uploaded_docs', (f.filename, f.stream, f.mimetype)))

        # Send request to PocketBase
        if product_id:
            pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
            resp = requests.patch(pb_url, data=pb_data, files=files_payload, headers=HEADERS)
        else:
            pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records"
            resp = requests.post(pb_url, data=pb_data, files=files_payload, headers=HEADERS)

        # Debug output to terminal
        print("PocketBase Response:", resp.status_code, resp.text)

        if resp.status_code in (200, 201):
            flash("Product saved successfully!", "success")
            return redirect(url_for("product_list"))
        else:
            flash(f"Error saving product: {resp.text}", "error")
            return f"Error saving product: {resp.text}", resp.status_code

    # Render form
    return render_template(
        "add_product.html",
        product=product,
        suppliers=suppliers,
        supplier_name_for_product=supplier_name_for_product
    )

@app.route('/delete_product/<product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
    resp = requests.delete(pb_url, headers=HEADERS)

    if resp.status_code == 204:
        flash("Product deleted successfully!", "success")
    else:
        flash(f"Failed to delete product: {resp.text}", "error")

    return redirect(url_for('product_list'))

@app.route('/product/<product_id>')
@login_required
def product_detail(product_id):
    # Fetch product details
    pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
    resp = requests.get(pb_url, headers=HEADERS)
    
    if resp.status_code != 200:
        flash("Product not found!", "error")
        return redirect(url_for('product_list'))
    
    product = resp.json()
    
    # Fetch supplier details if product has a supplier
    supplier_info = None
    supplier_id = product.get("supplier")
    if supplier_id:
        # Handle supplier_id as list (similar to product_list logic)
        if isinstance(supplier_id, list):
            supplier_id = supplier_id[0] if supplier_id else None
        
        if supplier_id:
            try:
                supplier_resp = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records/{supplier_id}", headers=HEADERS)
                if supplier_resp.status_code == 200:
                    supplier_info = supplier_resp.json()
                    print(f"DEBUG: Fetched supplier for product {product_id}: {supplier_info}")
                else:
                    print(f"DEBUG: Supplier request failed with status {supplier_resp.status_code}: {supplier_resp.text}")
            except Exception as e:
                print(f"DEBUG: Error fetching supplier {supplier_id}: {e}")
    
    # Build file URLs
    product_files = build_file_urls(product)
    
    return render_template(
        'product_detail.html',
        product=product,
        supplier=supplier_info,
        files=product_files
    )

@app.route('/product/<product_id>/edit', methods=['GET', 'POST'])
@login_required
def product_edit(product_id):
    # Fetch all suppliers for dropdown
    suppliers_resp = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records", headers=HEADERS)
    suppliers = suppliers_resp.json().get("items", []) if suppliers_resp.status_code == 200 else []

    # Fetch product details
    pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
    resp = requests.get(pb_url, headers=HEADERS)
    
    if resp.status_code != 200:
        flash("Product not found!", "error")
        return redirect(url_for('product_list'))
    
    product = resp.json()
    
    # Normalize supplier ID (handle case where it might be a list)
    supplier_id = product.get("supplier")
    if isinstance(supplier_id, list):
        supplier_id = supplier_id[0] if supplier_id else None
    
    # Update the product dict with normalized supplier ID for template
    product["supplier"] = supplier_id
    
    # Fetch supplier name for display
    supplier_name_for_product = None
    if supplier_id:
        supplier_resp = requests.get(f"{POCKETBASE_URL}/api/collections/suppliers/records/{supplier_id}", headers=HEADERS)
        if supplier_resp.status_code == 200:
            supplier_data = supplier_resp.json()
            supplier_name_for_product = supplier_data.get("name")

    if request.method == 'POST':
        data = request.form.to_dict()
        files = request.files.getlist('uploaded_docs')

        # Helpers to make sure PocketBase accepts the values
        def safe_str(value):
            return str(value) if value is not None else ""

        def safe_float_str(key):
            try:
                return str(float(data.get(key))) if data.get(key) else ""
            except:
                return ""

        def safe_int_str(key):
            try:
                return str(int(data.get(key))) if data.get(key) else ""
            except:
                return ""

        try:
            price = float(data.get("price", 0))
        except ValueError:
            flash("Invalid price format!", "error")
            return redirect(url_for('product_edit', product_id=product_id))

        # Prepare form data for PocketBase
        pb_data = {
            "product_id": data.get("product_id") or product.get("product_id"),
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "gross_weight": safe_float_str("gross_weight"),
            "product_size": data.get("product_size", ""),
            "hs_code": data.get("hs_code", ""),
            "tax_rate": safe_float_str("tax_rate"),
            "vat": safe_float_str("vat"),
            "qty_per_box": safe_int_str("qty_per_box"),
            "box_size": data.get("box_size", ""),
            "box_weight": safe_float_str("box_weight"),
            "buying_rate": safe_float_str("buying_rate"),
            "selling_rate": safe_float_str("selling_rate"),
            "terms": data.get("terms", ""),
            "specifications": data.get("specifications", ""),
            "supplier": data.get("supplier", ""),  # Must be supplier ID
            "model": data.get("model", ""),
            "price": safe_str(price),
        }

        # Handle file removal
        files_to_remove = data.get("files_to_remove", "")
        if files_to_remove:
            files_to_remove_list = [f.strip() for f in files_to_remove.split(',') if f.strip()]
            
            # Get current uploaded_docs
            current_files = product.get("uploaded_docs", [])
            if isinstance(current_files, str):
                current_files = [current_files]
            
            # Filter out files to be removed
            remaining_files = [f for f in current_files if f not in files_to_remove_list]
            pb_data["uploaded_docs"] = remaining_files

        # Prepare files
        files_payload = []
        for f in files:
            if f.filename != '':
                files_payload.append(('uploaded_docs', (f.filename, f.stream, f.mimetype)))

        # Send PATCH request to PocketBase
        pb_url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records/{product_id}"
        resp = requests.patch(pb_url, data=pb_data, files=files_payload, headers=HEADERS)

        # Debug output to terminal
        print("PocketBase Response:", resp.status_code, resp.text)

        if resp.status_code == 200:
            flash("Product updated successfully!", "success")
            return redirect(url_for("product_detail", product_id=product_id))
        else:
            flash(f"Error updating product: {resp.text}", "error")
            return redirect(url_for('product_edit', product_id=product_id))

    # Build file URLs for existing files
    product_files = build_file_urls(product)

    # Render edit form
    return render_template(
        "product_edit.html",
        product=product,
        suppliers=suppliers,
        supplier_name_for_product=supplier_name_for_product,
        product_files=product_files
    )

# =============================================================================
# INQUIRY MANAGEMENT ROUTES
# =============================================================================

@app.route('/inquiries')
@login_required
def inquiry_page():
    return render_template('inquiry.html')

@app.route("/api/inquiries")
@login_required
def get_inquiries():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("perPage", INQUIRIES_PER_PAGE, type=int)
        customer_id = request.args.get("customer_id", None)
        search_query = request.args.get("search", "").strip()

        # Build filter string
        filters = []
        
        if customer_id:
            filters.append(f'customer_id = "{customer_id}"')

        # For search, we'll get all records and filter in Python since we need to search across related records
        if search_query:
            # Get all inquiries first
            all_inquiries = pb.collection(INQUIRY_COLLECTION).get_full_list(
                query_params={"sort": "-created"} if not filters else {"filter": " && ".join(filters), "sort": "-created"}
            )
            
            # Get customers and products for searching
            all_customers = pb.collection(CUSTOMER_COLLECTION).get_full_list()
            all_products = pb.collection(PRODUCT_COLLECTION).get_full_list()
            
            # Create lookup dictionaries
            customer_lookup = {c.id: c for c in all_customers}
            product_lookup = {p.id: p for p in all_products}
            
            # Filter inquiries based on search query
            filtered_inquiries = []
            for inq in all_inquiries:
                # Check if search matches inquiry fields
                search_fields = [
                    str(getattr(inq, "inquiry_no", "")).lower(),
                    str(getattr(inq, "status", "")).lower(),
                    str(getattr(inq, "remarks", "")).lower(),
                    str(getattr(inq, "quantity", "")).lower(),
                    str(getattr(inq, "amount", "")).lower()
                ]
                
                # Add customer and product names to search
                customer = customer_lookup.get(getattr(inq, "customer_id", ""))
                if customer:
                    search_fields.extend([
                        str(getattr(customer, "name", "")).lower(),
                        str(getattr(customer, "email", "")).lower(),
                        str(getattr(customer, "phone", "")).lower(),
                        str(getattr(customer, "customer_id", "")).lower()
                    ])
                
                product = product_lookup.get(getattr(inq, "product_id", ""))
                if product:
                    search_fields.extend([
                        str(getattr(product, "name", "")).lower(),
                        str(getattr(product, "category", "")).lower(),
                        str(getattr(product, "brand", "")).lower()
                    ])
                
                # Check if search query matches any field
                if any(search_query.lower() in field for field in search_fields):
                    filtered_inquiries.append(inq)
            
            all_inquiries_sorted = filtered_inquiries
        else:
            # Regular filtering without search
            if filters:
                all_inquiries = pb.collection(INQUIRY_COLLECTION).get_full_list(
                    query_params={"filter": " && ".join(filters), "sort": "-created"}
                )
            else:
                all_inquiries = pb.collection(INQUIRY_COLLECTION).get_full_list(
                    query_params={"sort": "-created"}
                )
            all_inquiries_sorted = all_inquiries

        # Paginate manually
        start = (page - 1) * per_page
        end = start + per_page
        items = all_inquiries_sorted[start:end]

        total_items = len(all_inquiries_sorted)
        total_pages = ceil(total_items / per_page) if total_items > 0 else 1

        inquiries = []
        for inq in items:
            try:
                cust = pb.collection(CUSTOMER_COLLECTION).get_one(inq.customer_id) if hasattr(inq, "customer_id") else None
            except Exception:
                cust = None

            try:
                prod = pb.collection(PRODUCT_COLLECTION).get_one(inq.product_id) if hasattr(inq, "product_id") else None
            except Exception:
                prod = None

            inquiries.append({
                "id": getattr(inq, "id", ""),
                "inquiry_no": getattr(inq, "inquiry_no", ""),
                "customer_id": getattr(inq, "customer_id", ""),
                "customer_name": getattr(cust, "name", "Unknown") if cust else "Unknown",
                "product_id": getattr(inq, "product_id", ""),
                "product_name": getattr(prod, "name", "Unknown") if prod else "Unknown",
                "quantity": getattr(inq, "quantity", ""),
                "amount": getattr(inq, "amount", ""),
                "remarks": getattr(inq, "remarks", ""),
                "status": getattr(inq, "status", ""),
            })

        return jsonify({
            "items": inquiries,
            "totalItems": total_items,
            "totalPages": total_pages,
            "currentPage": page,
            "perPage": per_page,
            "stats": {
                "total": len(all_inquiries_sorted),
                "active": len([inq for inq in all_inquiries_sorted if getattr(inq, "status", "") != "Closed"]),
                "closed": len([inq for inq in all_inquiries_sorted if getattr(inq, "status", "") == "Closed"])
            }
        })
    except Exception as e:
        print("Error in /api/inquiries:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/inquiries", methods=["POST"])
@login_required
def create_inquiry():
    data = request.json
    customer_id = data.get("customer_id")
    product_id = data.get("product_id")
    if not customer_id or not product_id:
        return jsonify({"error": "Customer and Product are required"}), 400

    try:
        # Get customer and product records to generate proper inquiry number
        customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
        product = pb.collection(PRODUCT_COLLECTION).get_one(product_id)
        
        # Extract customer number from customer_id (e.g., CUST_2025_0011 -> 0011)
        customer_number = "0000"
        if hasattr(customer, "customer_id"):
            cust_id = getattr(customer, "customer_id", "")
            if "_" in cust_id:
                parts = cust_id.split("_")
                if len(parts) >= 3:
                    customer_number = parts[2]
        
        # Extract product number from product ID format (assuming similar format)
        product_number = "0000"
        if hasattr(product, "product_id"):
            prod_id = getattr(product, "product_id", "")
            if "_" in prod_id:
                parts = prod_id.split("_")
                if len(parts) >= 3:
                    product_number = parts[2]
        
        # Generate inquiry number: INQ-YEAR-CUSTNUM-PRODNUM
        current_year = datetime.now().year
        inquiry_no = f"INQ-{current_year}-{customer_number}-{product_number}"
        
        quantity = int(data.get("quantity", 1))
    except Exception as e:
        return jsonify({"error": f"Error processing customer/product data: {str(e)}"}), 400

    try:
        print(f"Creating inquiry with customer_id={customer_id}, product_id={product_id}, inquiry_no={inquiry_no}")
        record = pb.collection(INQUIRY_COLLECTION).create({
            "inquiry_no": inquiry_no,
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "amount": data.get("amount", ""),
            "remarks": data.get("remarks", ""),
            "status": data.get("status", "Inquiry")
        })
        print(f"Inquiry created: {record}")
        return jsonify({"message": "Inquiry created", "id": record.id}), 201
    except ClientResponseError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/inquiries/<inquiry_id>", methods=["PUT"])
@login_required
def update_inquiry(inquiry_id):
    data = request.json
    try:
        record = pb.collection(INQUIRY_COLLECTION).get_one(inquiry_id)
        if not record:
            return jsonify({"error": "Inquiry not found"}), 404

        # Validate customer_id and product_id if you want
        customer_id = data.get("customer_id", getattr(record, "customer_id", None))
        product_id = data.get("product_id", getattr(record, "product_id", None))
        quantity = data.get("quantity", getattr(record, "quantity", 1))
        amount = data.get("amount", getattr(record, "amount", ""))
        remarks = data.get("remarks", getattr(record, "remarks", ""))
        status = data.get("status", getattr(record, "status", "Inquiry"))

        # Recompute inquiry_no if customer_id or product_id changed
        try:
            # Get customer and product records to generate proper inquiry number
            customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
            product = pb.collection(PRODUCT_COLLECTION).get_one(product_id)
            
            # Extract customer number from customer_id (e.g., CUST_2025_0011 -> 0011)
            customer_number = "0000"
            if hasattr(customer, "customer_id"):
                cust_id = getattr(customer, "customer_id", "")
                if "_" in cust_id:
                    parts = cust_id.split("_")
                    if len(parts) >= 3:
                        customer_number = parts[2]
            
            # Extract product number from product ID format
            product_number = "0000"
            if hasattr(product, "product_id"):
                prod_id = getattr(product, "product_id", "")
                if "_" in prod_id:
                    parts = prod_id.split("_")
                    if len(parts) >= 3:
                        product_number = parts[2]
            
            # Generate inquiry number: INQ-YEAR-CUSTNUM-PRODNUM
            current_year = datetime.now().year
            inquiry_no = f"INQ-{current_year}-{customer_number}-{product_number}"
        except:
            # Fallback to old format if error
            inquiry_no = f"{customer_id}-{product_id}"

        update_data = {
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "amount": amount,
            "remarks": remarks,
            "status": status,
            "inquiry_no": inquiry_no,
        }

        pb.collection(INQUIRY_COLLECTION).update(inquiry_id, update_data)
        return jsonify({"message": "Inquiry updated"})
    except Exception as e:
        print("Error in update_inquiry:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/inquiries/<inquiry_id>", methods=["DELETE"])
@login_required
def delete_inquiry(inquiry_id):
    try:
        pb.collection(INQUIRY_COLLECTION).delete(inquiry_id)
        return jsonify({"message": "Inquiry deleted"})
    except ClientResponseError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/customers")
@login_required
def get_customers():
    try:
        records = pb.collection(CUSTOMER_COLLECTION).get_full_list()
        return jsonify([{"id": r.id, "name": r.name} for r in records])
    except ClientResponseError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/products")
@login_required
def get_products():
    try:
        records = pb.collection(PRODUCT_COLLECTION).get_full_list()
        return jsonify([{
            "id": r.id, 
            "name": r.name,
            "price": getattr(r, "price", 0)
        } for r in records])
    except ClientResponseError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/customers/<customer_id>/history")
@login_required
def customer_history(customer_id):
    try:
        customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
        purchases = pb.collection(INQUIRY_COLLECTION).get_full_list(
            query_params={
                "filter": f"customer_id = '{customer_id}'",
                "expand": "product_id"
            }
        )

        purchase_data = []
        for p in purchases:
            prod = getattr(p.expand, "product_id", None) if hasattr(p, "expand") else None
            prod_name = getattr(prod, "name", "") if prod else ""
            purchase_data.append({
                "product_name": prod_name,
                "quantity": getattr(p, "quantity", 0),
                "date": getattr(p, "created", "")
            })
        return jsonify({
            "customer": {"id": customer.id, "name": customer.name},
            "purchases": purchase_data
        })
    except ClientResponseError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers/<customer_id>/details')
@login_required
def get_customer_details(customer_id):
    try:
        print(f"Fetching customer details for ID: {customer_id}")  # Debug print
        customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
        if not customer:
            print(f"Customer not found for ID: {customer_id}")  # Debug print
            return jsonify({'error': 'Customer not found'}), 404
        # Convert to dict for JSON response
        cust_dict = {
            'id': getattr(customer, 'id', ''),
            'customer_id': getattr(customer, 'customer_id', ''),
            'name': getattr(customer, 'name', ''),
            'email': getattr(customer, 'email', ''),
            'phone': getattr(customer, 'phone', ''),
            'address': getattr(customer, 'address', ''),
            'notes': getattr(customer, 'notes', ''),
            'created': str(getattr(customer, 'created', '')),
        }
        print(f"Customer found: {cust_dict}")  # Debug print
        return jsonify({'customer': cust_dict})
    except Exception as e:
        print(f"Error in /api/customers/<customer_id>/details: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# STAFF MANAGEMENT ROUTES
# =============================================================================

# View Staff
@app.route('/staff')
@login_required
def staff():
    # Block access for Staff users
    if session.get('user_role') == 'staff':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Ensure admin authentication for fetching all users
        ensure_admin_auth()
        # Fetch all users from PocketBase users collection
        users = pb.collection('users').get_full_list()
    except ClientResponseError as e:
        flash(f"Error fetching users: {e}", 'error')
        users = []

    return render_template('staff.html', users=users)

# Add Staff
@app.route('/add_staff', methods=['GET', 'POST'])
@login_required
def add_staff():
    if request.method == 'POST':
        try:
            # Ensure admin authentication for user operations
            ensure_admin_auth()
            
            name = request.form.get('name')
            email = request.form.get('email')
            role = request.form.get('role')
            password = request.form.get('password')
            verified = 'verified' in request.form
            
            # Create new user in PocketBase
            user_data = {
                'Name': name,  # Changed from 'name' to 'Name'
                'email': email,
                'role': role,
                'password': password,
                'passwordConfirm': password,
                'verified': verified,
                'emailVisibility': True  # Added this field
            }
            
            pb.collection('users').create(user_data)
            flash('Staff member created successfully!', 'success')
            return redirect(url_for('staff'))
            
        except ClientResponseError as e:
            flash(f'Error creating staff member: {e}', 'error')
    
    return render_template('add_staff.html')

# Edit Staff
@app.route('/edit_staff/<user_id>', methods=['GET', 'POST'])
@login_required
def edit_staff(user_id):
    try:
        # Ensure admin authentication for user operations
        ensure_admin_auth()
        
        # Get user data
        user = pb.collection('users').get_one(user_id)
        
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            role = request.form.get('role')
            password = request.form.get('password')
            verified = 'verified' in request.form
            
            # Prepare update data
            update_data = {
                'Name': name,  # Changed from 'name' to 'Name'
                'email': email,
                'role': role,
                'verified': verified,
                'emailVisibility': True  # Added this field
            }
            
            # Only update password if provided
            if password:
                update_data['password'] = password
                update_data['passwordConfirm'] = password
            
            # Update user in PocketBase
            pb.collection('users').update(user_id, update_data)
            flash('Staff member updated successfully!', 'success')
            return redirect(url_for('staff'))
        
        return render_template('edit_staff.html', user=user)
        
    except ClientResponseError as e:
        flash(f'Error: {e}', 'error')
        return redirect(url_for('staff'))

# Delete Staff
@app.route('/delete_staff', methods=['POST'])
@login_required
def delete_staff():
    user_id = request.form.get('user_id')
    if not user_id:
        flash('No user ID provided', 'error')
        return redirect(url_for('staff'))

    try:
        # Ensure admin authentication for user operations
        ensure_admin_auth()
        
        # Get user data first to check if it exists
        user = pb.collection('users').get_one(user_id)
        
        # Delete user from PocketBase
        pb.collection('users').delete(user_id)
        flash(f'Staff member "{user.email}" has been deleted successfully!', 'success')
        
    except ClientResponseError as e:
        if e.status == 404:
            flash('Staff member not found', 'error')
        else:
            flash(f'Error deleting staff member: {e}', 'error')
    except Exception as e:
        flash(f'Unexpected error: {e}', 'error')

    return redirect(url_for('staff'))

# =============================================================================
# REMINDER MANAGEMENT ROUTES
# =============================================================================

from datetime import datetime, timedelta

@app.route('/add_reminder', methods=['POST'])
@login_required
def add_reminder():
    topic = request.form.get("topic")
    description = request.form.get("description")
    datetime_str = request.form.get("datetime_utc")  # Get the UTC converted time from frontend
    email = request.form.get("email")

    # Fallback to original datetime if UTC conversion wasn't done
    if not datetime_str:
        datetime_str = request.form.get("datetime")

    if not (topic and description and datetime_str and email):
        flash("All fields are required.", "error")
        return redirect(url_for("reminders"))

    try:
        # If we have datetime_utc, use it directly, otherwise convert from Nepal time
        if request.form.get("datetime_utc"):
            # Frontend already converted Nepal time to UTC
            utc_dt_str = datetime_str
        else:
            # Fallback: Parse the input datetime (assumed naive Nepal Time) and convert to UTC
            nepali_dt = datetime.fromisoformat(datetime_str)
            utc_offset = timedelta(hours=5, minutes=45)
            utc_dt = nepali_dt - utc_offset
            utc_dt_str = utc_dt.strftime("%Y-%m-%dT%H:%M")

    except Exception as e:
        flash(f"Invalid datetime format: {e}", "error")
        return redirect(url_for("reminders"))

    reminder_data = {
        "topic": topic,
        "description": description,
        "datetime": utc_dt_str,  # saved as UTC time string
        "email": email,
        "sent": False,
    }

    try:
        pb.collection("reminders").create(reminder_data)
        flash("Reminder saved successfully!", "success")
    except Exception as e:
        flash(f"Failed to save reminder: {e}", "error")

    return redirect(url_for("reminders"))

@app.route('/reminders')
@login_required
def reminders():
    try:
        reminders_list = pb.collection("reminders").get_list(
            page=1, 
            per_page=100, 
            query_params={"sort": "-created"}
        )
    except ClientResponseError as e:
        flash(f"Error fetching reminders: {e}", "error")
        reminders_list = []
    return render_template('reminders.html', reminders=reminders_list.items)

@app.route('/delete_reminder/<string:reminder_id>', methods=['POST'])
@login_required
def delete_reminder(reminder_id):
    try:
        pb.collection("reminders").delete(reminder_id)
        flash("Reminder deleted successfully!", "success")
    except ClientResponseError as e:
        flash(f"Error deleting reminder: {e}", "error")
    return redirect(url_for('reminders'))

@app.route('/edit_reminder/<string:reminder_id>', methods=['GET', 'POST'])
@login_required
def edit_reminder(reminder_id):
    try:
        # Get reminder data
        reminder = pb.collection("reminders").get_one(reminder_id)
        
        if request.method == 'POST':
            topic = request.form.get("topic")
            description = request.form.get("description")
            datetime_str = request.form.get("datetime_utc")  # Get UTC time from frontend
            email = request.form.get("email")

            if not (topic and description and datetime_str and email):
                flash("All fields are required.", "error")
                return render_template('edit_reminder.html', reminder=reminder)

            try:
                # Parse the UTC datetime from frontend
                utc_dt = datetime.fromisoformat(datetime_str)
                # Convert to ISO format string without tz info
                utc_dt_str = utc_dt.strftime("%Y-%m-%dT%H:%M")

            except Exception as e:
                flash(f"Invalid datetime format: {e}", "error")
                return render_template('edit_reminder.html', reminder=reminder)

            update_data = {
                "topic": topic,
                "description": description,
                "datetime": utc_dt_str,
                "email": email,
                "sent": False,  # Reset sent status when editing
            }

            try:
                pb.collection("reminders").update(reminder_id, update_data)
                flash("Reminder updated successfully!", "success")
                return redirect(url_for("reminders"))
            except Exception as e:
                flash(f"Failed to update reminder: {e}", "error")

        return render_template('edit_reminder.html', reminder=reminder)
        
    except ClientResponseError as e:
        if e.status == 404:
            flash("Reminder not found", "error")
        else:
            flash(f"Error: {e}", "error")
        return redirect(url_for('reminders'))

# =============================================================================
# SUPPLIER MANAGEMENT ROUTES
# =============================================================================

@app.route('/suppliers')
@login_required
def suppliers():
    # Block access for Staff users
    if session.get('user_role') == 'staff':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    try:
        print(f"DEBUG: Fetching suppliers, page={page}, search='{search_query}'")
        
        # Build filter string
        filter_str = ''
        if search_query:
            filter_str = (
                f'name ~ "{search_query}" || '
                f'email ~ "{search_query}" || '
                f'contact ~ "{search_query}"'
            )

        # Fetch paginated supplier records - Use lowercase "suppliers"
        if filter_str:
            print(f"DEBUG: Using filter: {filter_str}")
            result = pb.collection("suppliers").get_list(
                page=page,
                per_page=SUPPLIERS_PER_PAGE,
                query_params={
                    "filter": filter_str
                }
            )
        else:
            print("DEBUG: No filter, fetching all suppliers")
            result = pb.collection("suppliers").get_list(
                page=page,
                per_page=SUPPLIERS_PER_PAGE
            )

        print(f"DEBUG: Result - items count: {len(result.items)}, total: {result.total_items}")
        
        records = result.items
        total_suppliers = result.total_items
        total_pages = ceil(total_suppliers / SUPPLIERS_PER_PAGE)

        # Convert Record objects to dicts
        suppliers_full = []
        for s in records:
            supplier_data = {
                "id": s.id,
                "name": getattr(s, "name", ""),
                "email": getattr(s, "email", ""),
                "contact": getattr(s, "contact", ""),
                "address": getattr(s, "address", ""),
                "created": getattr(s, "created", None)
            }
            suppliers_full.append(supplier_data)
            print(f"DEBUG: Added supplier: {supplier_data}")

        # Get count for active suppliers (for now, assume all are active)
        active_suppliers = total_suppliers
        
        print(f"DEBUG: Final counts - total: {total_suppliers}, active: {active_suppliers}")

    except Exception as e:
        print(f"ERROR: Exception fetching suppliers: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error fetching suppliers: {e}", 'error')
        suppliers_full = []
        total_suppliers = 0
        total_pages = 1
        active_suppliers = 0

    return render_template('suppliers.html', 
                         suppliers=suppliers_full,
                         total_suppliers=total_suppliers,
                         active_suppliers=active_suppliers,
                         current_page=page,
                         total_pages=total_pages,
                         search_query=search_query)

@app.route('/add_supplier', methods=['GET', 'POST'])
@login_required
def add_supplier():
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            # Validate required fields
            name = data.get('name', '').strip()
            contact = data.get('contact', '').strip()
            
            if not name or not contact:
                flash('Name and contact are required fields.', 'error')
                return render_template('add_supplier.html')
            
            # Prepare supplier data for PocketBase
            pb_data = {
                "name": name,
                "contact": contact,
                "email": data.get('email', '').strip(),
                "address": data.get('address', '').strip()
            }
            
            # Send request to PocketBase API (same pattern as add_product)
            pb_url = f"{POCKETBASE_URL}/api/collections/suppliers/records"
            resp = requests.post(pb_url, data=pb_data, headers=HEADERS)
            
            # Debug output to terminal
            print("PocketBase Response:", resp.status_code, resp.text)
            
            if resp.status_code in (200, 201):
                flash('Supplier added successfully!', 'success')
                return redirect(url_for('suppliers'))
            else:
                flash(f'Error adding supplier: {resp.text}', 'error')
                print(f"Error adding supplier: {resp.text}")
                
        except Exception as e:
            flash(f'Unexpected error: {str(e)}', 'error')
            print(f"Unexpected error in add_supplier: {e}")
    
    return render_template('add_supplier.html')

@app.route("/supplier/<supplier_id>")
@login_required
def supplier_details(supplier_id):
    # Just render the template with supplier_id, data fetched client-side
    return render_template("supplier_details.html", supplier_id=supplier_id)

@app.route('/api/suppliers/<supplier_id>/details')
@login_required
def get_supplier_details(supplier_id):
    try:
        # Get supplier details
        supplier = pb.collection("suppliers").get_one(supplier_id)
        if not supplier:
            return jsonify({'error': 'Supplier not found'}), 404
        
        # Convert to dict for JSON response
        supplier_dict = {
            'id': getattr(supplier, 'id', ''),
            'name': getattr(supplier, 'name', ''),
            'email': getattr(supplier, 'email', ''),
            'contact': getattr(supplier, 'contact', ''),
            'address': getattr(supplier, 'address', ''),
            'notes': getattr(supplier, 'notes', ''),
            'created': str(getattr(supplier, 'created', '')),
        }
        
        return jsonify({'supplier': supplier_dict})
    except Exception as e:
        print(f"Error in /api/suppliers/{supplier_id}/details: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/suppliers/<supplier_id>/products')
@login_required
def get_supplier_products(supplier_id):
    try:
        # Get all products for this supplier (supplier field is an array)
        products = pb.collection("products").get_full_list(
            query_params={
                "filter": f'supplier ~ "{supplier_id}"'
            }
        )
        
        # Convert products to list of dicts
        products_list = []
        for product in products:
            product_dict = {
                'id': getattr(product, 'id', ''),
                'product_id': getattr(product, 'product_id', ''),
                'name': getattr(product, 'name', ''),
                'description': getattr(product, 'description', ''),
                'price': getattr(product, 'price', ''),
                'model': getattr(product, 'model', ''),
                'buying_rate': getattr(product, 'buying_rate', ''),
                'selling_rate': getattr(product, 'selling_rate', ''),
                'specifications': getattr(product, 'specifications', ''),
                'hs_code': getattr(product, 'hs_code', ''),
                'created': str(getattr(product, 'created', '')),
            }
            products_list.append(product_dict)
        
        return jsonify({'products': products_list})
    except Exception as e:
        print(f"Error in /api/suppliers/{supplier_id}/products: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete_supplier', methods=['POST'])
@login_required
def delete_supplier():
    supplier_id = request.form.get('supplier_id')
    if not supplier_id:
        flash('Supplier ID not provided', 'error')
        return redirect(url_for('suppliers'))
    
    try:
        pb.collection(SUPPLIER_COLLECTION).delete(supplier_id)
        flash('Supplier deleted successfully', 'success')
    except ClientResponseError as e:
        flash(f'Error deleting supplier: {e}', 'error')
    
    return redirect(url_for('suppliers'))

# =============================================================================
# CUSTOMER MANAGEMENT ROUTES
# =============================================================================

@app.route('/customers', methods=['GET'])
@login_required
def customers():
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    try:
        # Build filter string
        filter_str = ''
        if search_query:
            filter_str = (
                f'name ~ "{search_query}" || '
                f'email ~ "{search_query}" || '
                f'phone ~ "{search_query}" || '
                f'customer_id ~ "{search_query}"'
            )

        # Fetch paginated customer records
        if filter_str:
            result = pb.collection(CUSTOMER_COLLECTION).get_list(
                page=page,
                per_page=CUSTOMERS_PER_PAGE,
                query_params={
                    "filter": filter_str,
                    "sort": "-created"
                }
            )
        else:
            result = pb.collection(CUSTOMER_COLLECTION).get_list(
                page=page,
                per_page=CUSTOMERS_PER_PAGE,
                query_params={
                    "sort": "-created"
                }
            )

        records = result.items
        total_customers = result.total_items
        total_pages = ceil(total_customers / CUSTOMERS_PER_PAGE)

        # Convert Record objects to dicts and add inquiry counts
        customers_full = []
        for c in records:
            exported = vars(c)  # <-- converts Record to dictionary
            
            # Get inquiry count for this customer
            try:
                inquiry_count = len(pb.collection(INQUIRY_COLLECTION).get_full_list(
                    query_params={"filter": f'customer_id = "{c.id}"'}
                ))
            except:
                inquiry_count = 0
            
            customers_full.append({
                "id": c.id,
                "customer_id": exported.get("customer_id", ""),
                "name": exported.get("name", ""),
                "email": exported.get("email", ""),
                "phone": exported.get("phone", ""),
                "address": exported.get("address", ""),
                "notes": exported.get("notes", ""),
                "created": exported.get("created", None),
                "inquiry_count": inquiry_count
            })

        # Summary counts
        now = datetime.now(timezone.utc)
        recent_days_ago = now - timedelta(days=1)
        one_week_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        recent_customers = pb.collection(CUSTOMER_COLLECTION).get_full_list(
            query_params={
                "filter": f'created >= "{recent_days_ago.isoformat()}Z"',
                "sort": "-created"
            }
        )
        weekly_customers = pb.collection(CUSTOMER_COLLECTION).get_full_list(
            query_params={
                "filter": f'created >= "{one_week_ago.isoformat()}Z"',
                "sort": "-created"
            }
        )
        monthly_customers = pb.collection(CUSTOMER_COLLECTION).get_full_list(
            query_params={
                "filter": f'created >= "{thirty_days_ago.isoformat()}Z"',
                "sort": "-created"
            }
        )

        recent_count = len(recent_customers)
        weekly_count = len(weekly_customers)
        monthly_count = len(monthly_customers)

    except ClientResponseError as e:
        flash(f"Error fetching customers: {e}", 'error')
        customers_full = []
        total_customers = 0
        total_pages = 1
        recent_count = 0
        weekly_count = 0
        monthly_count = 0

    return render_template(
        'customer.html',
        customers=customers_full,
        count=total_customers,
        recent_count=recent_count,
        weekly_count=weekly_count,
        monthly_count=monthly_count,
        current_page=page,
        total_pages=total_pages,
        search_query=search_query
    )

@app.route('/customers/<customer_id>')
@login_required
def customer_details(customer_id):
    try:
        # Get customer details
        customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
        customer_data = {
            "id": customer.id,
            "customer_id": getattr(customer, "customer_id", ""),
            "name": getattr(customer, "name", ""),
            "email": getattr(customer, "email", ""),
            "phone": getattr(customer, "phone", ""),
            "address": getattr(customer, "address", ""),
            "notes": getattr(customer, "notes", ""),
            "created": getattr(customer, "created", None)
        }
        
        # Get all inquiries for this customer
        inquiries_records = pb.collection(INQUIRY_COLLECTION).get_full_list(
            query_params={
                "filter": f'customer_id = "{customer_id}"',
                "sort": "-created"
            }
        )
        
        inquiries = []
        for inquiry in inquiries_records:
            # Get customer details
            try:
                cust = pb.collection(CUSTOMER_COLLECTION).get_one(getattr(inquiry, "customer_id", "")) if hasattr(inquiry, "customer_id") else None
            except Exception:
                cust = None

            # Get product details
            try:
                prod = pb.collection(PRODUCT_COLLECTION).get_one(getattr(inquiry, "product_id", "")) if hasattr(inquiry, "product_id") else None
            except Exception:
                prod = None

            inquiry_data = {
                "id": inquiry.id,
                "inquiry_no": getattr(inquiry, "inquiry_no", ""),
                "customer_id": getattr(inquiry, "customer_id", ""),
                "customer_name": getattr(cust, "name", "Unknown") if cust else "Unknown",
                "product_id": getattr(inquiry, "product_id", ""),
                "product_name": getattr(prod, "name", "Unknown") if prod else "Unknown",
                "quantity": getattr(inquiry, "quantity", ""),
                "amount": getattr(inquiry, "amount", ""),
                "remarks": getattr(inquiry, "remarks", ""),
                "status": getattr(inquiry, "status", ""),
                "created": getattr(inquiry, "created", None)
            }
            inquiries.append(inquiry_data)
        
    except ClientResponseError as e:
        flash(f"Customer not found: {e}", 'error')
        return redirect(url_for('customers'))
    except Exception as e:
        flash(f"Error loading customer details: {e}", 'error')
        return redirect(url_for('customers'))
    
    return render_template(
        'customer_details.html',
        customer=customer_data,
        inquiries=inquiries
    )

@app.route('/customers/edit/<customer_id>', methods=['GET', 'POST'])
@login_required
def edit_customer_page(customer_id):
    try:
        customer = pb.collection(CUSTOMER_COLLECTION).get_one(customer_id)
        
        if request.method == 'POST':
            # Get form data
            updated_data = {
                "name": request.form['name'],
                "email": request.form.get('email', ''),
                "phone": request.form['phone'],
                "address": request.form.get('address', ''),
                "notes": request.form.get('notes', '')
            }
            
            try:
                # Update customer with new data
                pb.collection(CUSTOMER_COLLECTION).update(customer_id, updated_data)
                flash("Customer updated successfully!", "success")
                return redirect(url_for('customer_details', customer_id=customer_id))
                
            except ClientResponseError as e:
                flash(f"Error updating customer: {e}", 'error')
        
        # Convert customer to dict for template
        customer_data = {
            "id": customer.id,
            "customer_id": getattr(customer, "customer_id", ""),
            "name": getattr(customer, "name", ""),
            "email": getattr(customer, "email", ""),
            "phone": getattr(customer, "phone", ""),
            "address": getattr(customer, "address", ""),
            "notes": getattr(customer, "notes", "")
        }
        
    except ClientResponseError as e:
        flash(f"Customer not found: {e}", 'error')
        return redirect(url_for('customers'))
    except Exception as e:
        flash(f"Error loading customer: {e}", 'error')
        return redirect(url_for('customers'))
    
    return render_template('edit_customer.html', customer=customer_data)

@app.route('/add_customer', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email', '')
        phone = request.form['phone']
        address = request.form.get('address', '')
        notes = request.form.get('notes', '')
        customer_id = generate_next_customer_id()

        try:
            customer_data = {
                "customer_id": customer_id,
                "name": name,
                "email": email,
                "phone": phone,
                "address": address,
                "notes": notes
            }
            
            new_customer = pb.collection(CUSTOMER_COLLECTION).create(customer_data)
            flash('Customer added successfully!', 'success')
            
        except ClientResponseError as e:
            flash(f"Error adding customer: {e}", 'error')

        return redirect(url_for('customers'))

    return render_template('add_customer.html')

@app.route('/delete_customer', methods=['POST'])
@login_required
def delete_customer():
    customer_id = request.form.get('customer_id')
    if not customer_id:
        flash("Customer ID is required to delete.", "error")
        return redirect(url_for('customers'))

    try:
        pb.collection(CUSTOMER_COLLECTION).delete(customer_id)
        flash("Customer deleted successfully!", "success")
    except ClientResponseError as e:
        flash(f"Error deleting customer: {e}", "error")

    return redirect(url_for('customers'))


# =============================================================================
# TEMPLATE FILTERS AND UTILITY FUNCTIONS
# =============================================================================

@app.template_filter('datetimeformat')
@login_required
def datetimeformat(value):
    from datetime import datetime
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").strftime("%b %d, %Y")

# =============================================================================
# APPLICATION STARTUP
# =============================================================================

if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_send_reminders, 'interval', minutes=1)
    scheduler.start()
    app.run(host="0.0.0.0", port=5050, debug=DEV_MODE)

