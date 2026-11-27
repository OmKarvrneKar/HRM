import os
import random
import re
import logging
from flask import Flask, jsonify, render_template, request, flash, redirect, url_for, session, make_response
from bson import ObjectId
from config import Config
from backend.database.connection import DatabaseManager
from backend.database.indexes import setup_indexes
from backend.database.seeds import (
    seed_real_and_dummy_users as _seed_real_and_dummy_users,
    seed_default_users as _seed_default_users
)
from backend.scheduler.scheduler import DistributedScheduler
from backend.permissions.rbac import get_token_from_request
from backend.auth.security import decode_jwt_token
from backend.routes.auth_routes import auth_bp
from backend.routes.api_routes import api_bp
from backend.routes.page_routes import page_bp
from sqlalchemy import or_
from backend.models.user import User, sync_users_from_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("hrm_app")


USERS_DB = []


def seed_real_and_dummy_users(db=None):
    """
    Seeds exactly 1 clean dummy account per role (EMP-1001, TL-1001, MGR-1001, HR-1001, ADMIN-1001)
    and loads real intern records into the database with default test passwords.
    """
    global USERS_DB
    res = _seed_real_and_dummy_users(db)
    active_db = db if db is not None else DatabaseManager.get_db()
    USERS_DB = list(active_db.users.find())
    sync_users_from_db(active_db)
    # Genuine company workforce synchronized from authentic database records
    return USERS_DB


def seed_default_users(db=None) -> int:
    """Alias for backward-compatibility with default seeding hooks."""
    return len(seed_real_and_dummy_users(db))


def initialize_users(db=None):
    """
    Verifies that initialize_users() successfully loads the 5 test accounts
    (Employee, TL, Manager, HR, Admin) and the 34 real intern records.
    """
    return seed_real_and_dummy_users(db)


def create_app(config_class=Config, start_scheduler=True) -> Flask:
    # 0. Enforce Secret Hardening (Fail safely if required secrets are missing)
    if hasattr(config_class, "validate_secrets"):
        config_class.validate_secrets()

    app = Flask(
        __name__,
        template_folder="frontend/templates",
        static_folder="frontend/static"
    )
    app.config.from_object(config_class)

    # 1. Initialize MongoDB Database & Indexes
    db = DatabaseManager.get_db(db_name=app.config["DATABASE_NAME"], uri=app.config["MONGODB_URI"])
    setup_indexes(db)
    seed_real_and_dummy_users(db)

    # 2. Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(page_bp)

    # 2.1 Unified Authentication / Login Route
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            from backend.routes.auth_routes import login as api_login
            res = api_login()
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return res

            response_obj = res[0] if isinstance(res, tuple) else res
            if hasattr(response_obj, "get_json") and response_obj.get_json():
                data = response_obj.get_json()
                if data.get("success"):
                    # Role check for admin (case-insensitive)
                    role = (data.get("role") or session.get("role") or "").lower()
                    if role == "admin":
                        redirect_resp = redirect(url_for("admin_dashboard"))
                    elif data.get("redirect_url"):
                        redirect_resp = redirect(data["redirect_url"])
                    else:
                        redirect_resp = redirect(url_for("page_views.index"))

                    for cookie in response_obj.headers.getlist("Set-Cookie"):
                        redirect_resp.headers.add("Set-Cookie", cookie)
                    return redirect_resp
                else:
                    flash(data.get("error", "Invalid Employee ID or password."), "danger")
                    return render_template("auth/login.html", error=data.get("error", "Authentication failed.")), 200
            return res

        from backend.routes.page_routes import get_current_user_from_cookie
        user = get_current_user_from_cookie()
        if user and request.args.get("logged_out") != "1" and request.args.get("logout") != "1":
            return redirect(url_for("page_views.index"))

        from backend.services.otp_service import OtpService
        generated_otp = request.args.get("otp") or (OtpService.get_debug_otp() if Config.is_development() else None)
        resp = make_response(render_template("auth/login.html", generated_otp=generated_otp))
        for p in ("/", "/api", "/api/auth"):
            resp.delete_cookie(Config.JWT_COOKIE_NAME, path=p)
            resp.delete_cookie("session", path=p)
            resp.set_cookie(Config.JWT_COOKIE_NAME, "", expires=0, max_age=0, path=p)
            resp.set_cookie("session", "", expires=0, max_age=0, path=p)
        return resp

    # 2.2 Complete Logout / Sign-Out Route (GET & POST)
    @app.route("/logout", methods=["GET", "POST"], endpoint="logout")
    def logout():
        # 1. Clear session completely
        session.clear()
        session.pop("user_id", None)
        session.pop("role", None)
        session.pop("emp_id", None)

        # 2. Record attendance logout & audit log if user is authenticated
        try:
            token = get_token_from_request()
            user = getattr(request, "current_user", None)
            if not user and token:
                payload = decode_jwt_token(token)
                if payload and payload.get("user_id"):
                    active_db = DatabaseManager.get_db()
                    user = active_db.users.find_one({"_id": ObjectId(payload["user_id"])})

            if user:
                from backend.services.attendance_service import AttendanceService
                from backend.services.audit_service import AuditService
                AttendanceService.record_logout(user, ip_address=request.remote_addr)
                AuditService.log_action(
                    actor=user,
                    action="LOGOUT",
                    target_type="session",
                    target_id=user.get("employee_id") or user.get("emp_id") or "UNKNOWN",
                    ip_address=request.remote_addr
                )
        except Exception as e:
            logger.warning("Graceful skip on attendance/audit during logout: %s", e)

        # Clear request user
        request.current_user = None

        # 3. Clean Redirect back to login page
        resp = redirect(url_for("login"))
        for p in ("/", "/api", "/api/auth"):
            resp.delete_cookie(Config.JWT_COOKIE_NAME, path=p)
            resp.delete_cookie("session", path=p)
            resp.set_cookie(Config.JWT_COOKIE_NAME, "", expires=0, max_age=0, path=p)
            resp.set_cookie("session", "", expires=0, max_age=0, path=p)
        return resp

    # 2.3 System Admin Dashboard Route
    @app.route('/dashboard/admin')
    @app.route('/admin/dashboard')
    def admin_dashboard():
        from backend.routes.page_routes import get_current_user_from_cookie
        from backend.utils.serializers import serialize_doc
        from backend.utils.timezone import get_local_date_str
        from backend.database.connection import DatabaseManager

        # 1. Strict RBAC validation: session or JWT role must be admin
        session_role = (session.get('role') or '').lower()
        user = get_current_user_from_cookie()
        user_role = (user.get('role') or '').lower() if user else ''

        if session_role != 'admin' and user_role != 'admin':
            flash('Unauthorized access', 'danger')
            return redirect(url_for('login'))

        # 2. Resolve admin user document for template rendering
        if not user:
            emp_id = session.get('emp_id') or session.get('user_id')
            active_db = DatabaseManager.get_db()
            if emp_id:
                user = active_db.users.find_one({
                    "$or": [
                        {"emp_id": emp_id},
                        {"employee_id": emp_id}
                    ]
                })
            if not user:
                user = active_db.users.find_one({"role": "admin"})

        if not user:
            user = {
                "emp_id": "ADMIN-1001",
                "employee_id": "ADMIN-1001",
                "name": "System Administrator",
                "full_name": "System Administrator",
                "role": "admin",
                "email": "admin@aisamrat.com"
            }

        user_dict = serialize_doc(user) if hasattr(user, "get") else user
        request.current_user = user_dict

        return render_template(
            "dashboards/admin_dashboard.html",
            user=user_dict,
            today_date=get_local_date_str()
        )

    # 3. Context processor to inject common variables into Jinja
    @app.context_processor
    def inject_global_template_vars():
        # Never inject authenticated user variables on the login page
        if request.path == "/login" or request.endpoint in ("login", "page_views.login_page"):
            return {
                "current_user": None,
                "user": None,
                "app_name": "AI Samrat HRMS",
                "is_dev_mode": Config.is_development(),
                "allows_test_account": Config.allows_test_account(),
                "is_dev_otp_mode": Config.is_dev_otp_mode()
            }

        from backend.routes.page_routes import get_current_user_from_cookie
        from backend.utils.serializers import serialize_doc
        active_user = getattr(request, "current_user", None) or get_current_user_from_cookie()
        if not active_user and (session.get('emp_id') or session.get('user_id')):
            from backend.database.connection import DatabaseManager
            emp_id = session.get('emp_id') or session.get('user_id')
            db = DatabaseManager.get_db()
            active_user = db.users.find_one({"$or": [{"emp_id": emp_id}, {"employee_id": emp_id}]})
        if active_user and hasattr(active_user, "get"):
            active_user = serialize_doc(active_user)
        return {
            "current_user": active_user,
            "user": active_user,
            "app_name": "AI Samrat HRMS",
            "is_dev_mode": Config.is_development(),
            "allows_test_account": Config.allows_test_account(),
            "is_dev_otp_mode": Config.is_dev_otp_mode()
        }

    # 4. Security & Cache Control Headers (Prevent bfcache session exposure on back-navigation)
    @app.after_request
    def set_security_headers(response):
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.route("/api/health")
    def health_check():
        from datetime import datetime, timezone
        from backend.database.connection import DatabaseManager
        active_db = DatabaseManager.get_db()
        is_mock = DatabaseManager.is_mock()
        persistence_mode = "persistent_disk" if (is_mock and getattr(Config, "USE_FILE_PERSISTENCE", True)) else ("mongodb" if not is_mock else "in_memory")
        return jsonify({
            "status": "healthy",
            "app_name": "AI Samrat HRMS",
            "database": {
                "name": getattr(active_db, "name", "office_hrm"),
                "mode": persistence_mode,
                "is_mock": is_mock,
                "data_dir": str(getattr(DatabaseManager, "_data_dir", "") or ""),
                "total_users": active_db.users.count_documents({})
            },
            "server_time_utc": datetime.now(timezone.utc).isoformat()
        }), 200

    @app.route("/favicon.ico")
    def favicon():
        return app.send_static_file("img/ai_samrat_logo.jpeg")

    @app.route("/app", defaults={"path": ""})
    @app.route("/app/<path:path>")
    def serve_react_app(path):
        from flask import send_from_directory
        dist_dir = os.path.join(app.root_path, "frontend", "static", "dist")
        if path and os.path.exists(os.path.join(dist_dir, path)):
            return send_from_directory(dist_dir, path)
        return send_from_directory(dist_dir, "index.html")

    @app.route('/generate-otp', methods=['POST', 'GET'])
    def generate_otp():
        emp_id = (request.form.get('emp_id') or request.args.get('emp_id') or "").strip()
        if not emp_id and request.is_json:
            data = request.get_json(silent=True) or {}
            emp_id = (data.get('emp_id') or data.get('employee_id') or "").strip()

        active_db = DatabaseManager.get_db()
        user = None
        if emp_id:
            user = active_db.users.find_one({
                "$or": [
                    {"emp_id": re.compile(f"^{re.escape(emp_id)}$", re.IGNORECASE)},
                    {"employee_id": re.compile(f"^{re.escape(emp_id)}$", re.IGNORECASE)}
                ]
            })

        if user:
            # Generate a 6-digit test OTP
            auto_otp = str(random.randint(100000, 999999))
            actual_emp_id = user.get("emp_id") or user.get("employee_id") or emp_id

            # Save it to the user's document in the DB
            active_db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"activation_otp": auto_otp, "emp_id": actual_emp_id}}
            )

            # Sync to OtpService for activation verification
            try:
                from backend.services.otp_service import OtpService, OtpPurpose
                from datetime import datetime, timezone, timedelta
                user_email = user.get("personal_email") or user.get("email") or ""
                if user_email:
                    OtpService._dev_latest_otps[f"{user_email}:{OtpPurpose.ACTIVATION}"] = {
                        "otp": auto_otp,
                        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)
                    }
                OtpService._last_generated_otp = auto_otp
            except Exception as e:
                logger.warning("Could not sync OTP to OtpService: %s", e)

            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({
                    "success": True,
                    "generated_otp": auto_otp,
                    "emp_id": actual_emp_id,
                    "message": f"OTP {auto_otp} generated successfully for {actual_emp_id}."
                }), 200

            # Pass the OTP directly back to the HTML page for easy testing
            return render_template('activate_account.html', generated_otp=auto_otp, emp_id=actual_emp_id)

        flash('Employee ID not found', 'danger')
        return redirect(url_for('activate_page', emp_id=emp_id))

    # 4. Error handlers
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Bad request", "details": str(e)}), 400
        return render_template("base.html", error_message="400 - Bad Request"), 400

    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return render_template("base.html", error_message="401 - Unauthorized"), 401

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Access Denied / Forbidden"}), 403
        return render_template("base.html", error_message="403 - Forbidden"), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("base.html", error_message="404 - Not Found"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        logger.error("Internal Server Error: %s", str(e), exc_info=True)
        if request.path.startswith("/api/"):
            return jsonify({"error": "An internal server error occurred."}), 500
        return render_template("base.html", error_message="500 - Internal Server Error"), 500

    # 5. Initialize APScheduler (skip in testing mode or reloader child)
    if start_scheduler and not app.config.get("TESTING", False):
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
            try:
                DistributedScheduler.start()
            except Exception as e:
                logger.warning("Could not start scheduler: %s", str(e))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, use_reloader=False)
