"""
web/auth.py - Authentication for the web portal.

Implements single-user authentication using Flask-Login. The admin
username and password are loaded from environment variables (set in .env).
The password is hashed on first run and compared using werkzeug's
secure password hashing.

Routes:
  GET  /login  - Show the login form
  POST /login  - Validate credentials and log in
  GET  /logout - Log out and redirect to login page
"""

import os

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

# Create the auth blueprint — all auth routes are registered under this
auth_bp = Blueprint("auth", __name__)

# =============================================================================
# User Model (simple single-user setup)
# =============================================================================

class User(UserMixin):
    """
    Represents the single admin user for Flask-Login.

    Flask-Login requires a user object with an 'id' property.
    Since we only have one user, the id is always "admin".
    """

    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


# The single admin user — created during app initialization
_admin_user = None
_password_hash = None


def init_auth(app):
    """
    Initialize the authentication system.

    Sets up Flask-Login, loads admin credentials from environment
    variables, and configures the login manager.

    Args:
        app: The Flask application instance.

    Returns:
        The configured LoginManager instance.
    """
    global _admin_user, _password_hash

    # Load credentials from environment (set in .env file)
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")

    # Hash the password for secure comparison
    _password_hash = generate_password_hash(admin_password)

    # Create the admin user object
    _admin_user = User(user_id="admin", username=admin_username)

    # Set up Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    # Where to redirect when @login_required fails
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access the control panel."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        """
        Flask-Login callback to reload the user from the session.

        Since we only have one user, we just check if the id matches.
        """
        if user_id == "admin":
            return _admin_user
        return None

    return login_manager


# =============================================================================
# Routes
# =============================================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Handle the login page.

    GET: Show the login form.
    POST: Validate credentials and log the user in.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Check if the credentials match
        if (
            _admin_user
            and username == _admin_user.username
            and check_password_hash(_password_hash, password)
        ):
            # Credentials valid — log the user in
            login_user(_admin_user)
            # Redirect to the page they were trying to access, or dashboard
            next_page = request.args.get("next")
            return redirect(next_page or url_for("status.dashboard"))
        else:
            # Invalid credentials
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Log the user out and redirect to the login page."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
