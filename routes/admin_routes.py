from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

try:
    from ..extensions import db
    from ..models import User, Trek, Booking
except ImportError:
    from extensions import db
    from models import User, Trek, Booking


admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

ALLOWED_TREK_DIFFICULTIES = {"Easy", "Moderate", "Hard"}
ALLOWED_TREK_STATUSES = {"Open", "Closed", "In Progress", "Completed"}


def admin_required(fn):
    from functools import wraps

    @wraps(fn)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            flash("Access denied.", "danger")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)

    return decorated


def _parse_optional_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _validate_trek_input(name, location, description, duration_days, price, capacity, available_slots, difficulty, status,
                         start_date, end_date):
    errors = []
    if not name.strip():
        errors.append("Trek name cannot be empty.")
    if not location.strip():
        errors.append("Location cannot be empty.")
    if not description.strip():
        errors.append("Description cannot be empty.")
    if duration_days is None or duration_days <= 0:
        errors.append("Duration must be a valid positive number.")
    if price is None or price < 0:
        errors.append("Price cannot be negative.")
    if capacity is None or capacity <= 0:
        errors.append("Capacity must be a positive integer.")
    if available_slots is None or available_slots < 0:
        errors.append("Available slots cannot be negative.")
    if capacity is not None and available_slots is not None and available_slots > capacity:
        errors.append("Available slots cannot exceed capacity.")
    if difficulty not in ALLOWED_TREK_DIFFICULTIES:
        errors.append("Difficulty must be only Easy, Moderate, or Hard.")
    if status not in ALLOWED_TREK_STATUSES:
        errors.append("Status must use a valid application status.")
    if start_date and end_date and end_date < start_date:
        errors.append("End date cannot be before start date.")
    return errors


@admin_bp.route("/admin")
@admin_required
def dashboard():
    treks = Trek.query.all()
    users = User.query.filter(User.role != "admin").all()
    staff_members = User.query.filter_by(role="staff").all()
    bookings = Booking.query.all()
    return render_template("dashboard.html", treks=treks, users=users, staff_members=staff_members, bookings=bookings)


@admin_bp.route("/admin/treks", methods=["GET", "POST"])
@admin_required
def manage_treks():
    query = request.args.get("query", "").strip()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        duration_days_raw = request.form.get("duration_days", "").strip()
        price_raw = request.form.get("price", "").strip()
        capacity_raw = request.form.get("capacity", "").strip()
        available_slots_raw = request.form.get("available_slots", "").strip()
        difficulty = request.form.get("difficulty", "Easy").strip()
        status = request.form.get("status", "Open").strip()
        start_date = _parse_optional_date(request.form.get("start_date", "").strip())
        end_date = _parse_optional_date(request.form.get("end_date", "").strip())

        try:
            duration_days = int(duration_days_raw) if duration_days_raw else None
            price = float(price_raw) if price_raw else None
            capacity = int(capacity_raw) if capacity_raw else None
            available_slots = int(available_slots_raw) if available_slots_raw else capacity
        except ValueError:
            flash("Duration, price, capacity, and available slots must be numeric.", "danger")
            return redirect(url_for("admin.manage_treks"))

        errors = _validate_trek_input(name, location, description, duration_days, price, capacity, available_slots,
                                      difficulty, status, start_date, end_date)
        if errors:
            flash("; ".join(errors), "danger")
            return redirect(url_for("admin.manage_treks"))

        trek = Trek(
            name=name,
            location=location,
            description=description,
            duration_days=duration_days,
            price=price,
            capacity=capacity,
            available_slots=available_slots,
            difficulty=difficulty,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )
        db.session.add(trek)
        db.session.commit()
        flash("Trek created successfully.", "success")
        return redirect(url_for("admin.manage_treks"))

    treks = Trek.query
    if query:
        try:
            trek_id = int(query)
            treks = treks.filter((Trek.id == trek_id) | (Trek.name.ilike(f"%{query}%")))
        except ValueError:
            treks = treks.filter(Trek.name.ilike(f"%{query}%"))
    treks = treks.all()
    return render_template("manage_treks.html", treks=treks, query=query)


@admin_bp.route("/admin/treks/edit/<int:trek_id>", methods=["GET", "POST"])
@admin_required
def edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if request.method == "POST":
        trek.name = request.form.get("name", trek.name).strip()
        trek.location = request.form.get("location", trek.location).strip()
        trek.description = request.form.get("description", trek.description).strip()
        difficulty = request.form.get("difficulty", trek.difficulty).strip()
        status = request.form.get("status", trek.status).strip()
        start_date = _parse_optional_date(request.form.get("start_date", "").strip())
        end_date = _parse_optional_date(request.form.get("end_date", "").strip())

        try:
            duration_days = int(request.form.get("duration_days", trek.duration_days))
            price = float(request.form.get("price", trek.price))
            capacity = int(request.form.get("capacity", trek.capacity))
        except ValueError:
            flash("Duration, price, and capacity must be numeric.", "danger")
            return redirect(url_for("admin.edit_trek", trek_id=trek.id))

        active_bookings = sum(1 for booking in trek.bookings if booking.status != "cancelled")
        available_slots_value = request.form.get("available_slots", "").strip()
        if available_slots_value:
            try:
                available_slots = int(available_slots_value)
            except ValueError:
                flash("Available slots must be numeric.", "danger")
                return redirect(url_for("admin.edit_trek", trek_id=trek.id))
        else:
            available_slots = max(0, capacity - active_bookings)

        errors = _validate_trek_input(trek.name, trek.location, trek.description, duration_days, price, capacity,
                                      available_slots, difficulty, status, start_date, end_date)
        if errors:
            flash("; ".join(errors), "danger")
            return redirect(url_for("admin.edit_trek", trek_id=trek.id))

        trek.duration_days = duration_days
        trek.price = price
        trek.capacity = capacity
        trek.available_slots = available_slots
        trek.difficulty = difficulty
        trek.status = status
        trek.start_date = start_date
        trek.end_date = end_date
        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("admin.manage_treks"))
    return render_template("edit_trek.html", trek=trek)


@admin_bp.route("/admin/treks/delete/<int:trek_id>", methods=["POST"])
@admin_required
def delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    Booking.query.filter_by(trek_id=trek.id).delete()
    db.session.delete(trek)
    db.session.commit()
    flash("Trek deleted successfully.", "success")
    return redirect(url_for("admin.manage_treks"))


@admin_bp.route("/admin/users")
@admin_required
def manage_users():
    query = request.args.get("query", "").strip()
    users = User.query.filter(User.role != "admin")
    if query:
        try:
            user_id = int(query)
            users = users.filter((User.id == user_id) | (User.username.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%")))
        except ValueError:
            users = users.filter((User.username.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%")))
    users = users.all()
    return render_template("manage_users.html", users=users, query=query)


@admin_bp.route("/admin/staff", methods=["GET", "POST"])
@admin_required
def manage_staff():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not username or not email or not password:
            flash("All staff fields are required.", "danger")
            return redirect(url_for("admin.manage_staff"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for("admin.manage_staff"))
        staff = User(username=username, email=email, role="staff", approval_status="pending")
        staff.set_password(password)
        db.session.add(staff)
        db.session.commit()
        flash("Staff created successfully. Approval is required before dashboard access.", "success")
        return redirect(url_for("admin.manage_staff"))
    query = request.args.get("query", "").strip()
    staff_members = User.query.filter_by(role="staff")
    if query:
        try:
            staff_id = int(query)
            staff_members = staff_members.filter((User.id == staff_id) | (User.username.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%")))
        except ValueError:
            staff_members = staff_members.filter((User.username.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%")))
    staff_members = staff_members.all()
    treks = Trek.query.all()
    return render_template("manage_staff.html", staff_members=staff_members, treks=treks, query=query)


@admin_bp.route("/admin/staff/assign/<int:staff_id>", methods=["POST"])
@admin_required
def assign_trek(staff_id):
    staff = User.query.get_or_404(staff_id)
    trek_id = request.form.get("trek_id", type=int)
    if trek_id is None:
        flash("Please select a trek.", "danger")
        return redirect(url_for("admin.manage_staff"))

    trek = Trek.query.get_or_404(trek_id)
    staff.assigned_trek_id = trek.id
    db.session.commit()
    flash("Trek assigned successfully.", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/admin/staff/approve/<int:staff_id>", methods=["POST"])
@admin_required
def approve_staff(staff_id):
    staff = User.query.get_or_404(staff_id)
    staff.approval_status = "approved"
    db.session.commit()
    flash("Staff account approved.", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/admin/staff/blacklist/<int:staff_id>", methods=["POST"])
@admin_required
def blacklist_staff(staff_id):
    staff = User.query.get_or_404(staff_id)
    staff.is_blacklisted = True
    db.session.commit()
    flash("Staff account blacklisted.", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/admin/staff/unblacklist/<int:staff_id>", methods=["POST"])
@admin_required
def unblacklist_staff(staff_id):
    staff = User.query.get_or_404(staff_id)
    staff.is_blacklisted = False
    db.session.commit()
    flash("Staff account unblacklisted.", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/admin/user/blacklist/<int:user_id>", methods=["POST"])
@admin_required
def blacklist_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blacklisted = True
    db.session.commit()
    flash("User blacklisted.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/admin/user/unblacklist/<int:user_id>", methods=["POST"])
@admin_required
def unblacklist_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blacklisted = False
    db.session.commit()
    flash("User unblacklisted.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/admin/bookings")
@admin_required
def bookings():
    bookings = Booking.query.order_by(Booking.booked_at.desc()).all()
    return render_template("bookings.html", bookings=bookings)


@admin_bp.route("/admin/history")
@admin_required
def history():
    treks = Trek.query.order_by(Trek.end_date.desc().nullslast(), Trek.start_date.desc().nullslast(), Trek.id.desc()).all()
    historical_treks = []
    today = datetime.utcnow().date()
    for trek in treks:
        if trek.status == "Completed" or (trek.end_date and trek.end_date < today):
            bookings = Booking.query.filter_by(trek_id=trek.id).filter(Booking.status != "cancelled").all()
            historical_treks.append({
                "trek": trek,
                "bookings": bookings,
                "participant_count": len(bookings),
                "assigned_staff": User.query.filter_by(assigned_trek_id=trek.id).first(),
            })
    return render_template("history.html", historical_treks=historical_treks)
