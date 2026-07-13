from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

try:
    from ..extensions import db
    from ..models import Trek, Booking
except ImportError:
    from extensions import db
    from models import Trek, Booking


staff_bp = Blueprint("staff", __name__, template_folder="../templates/staff")

ALLOWED_STAFF_TREK_STATUSES = {"Open", "Closed", "In Progress", "Completed"}


def staff_required(fn):
    from functools import wraps

    @wraps(fn)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "staff":
            flash("Access denied.", "danger")
            return redirect(url_for("index"))
        if current_user.is_blacklisted:
            flash("Your staff account is blacklisted.", "danger")
            return redirect(url_for("index"))
        if current_user.approval_status != "approved":
            flash("Your staff account is pending admin approval.", "warning")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)

    return decorated


@staff_bp.route("/staff")
@staff_required
def dashboard():
    assigned_trek = Trek.query.get(current_user.assigned_trek_id) if current_user.assigned_trek_id else None
    bookings = Booking.query.filter_by(trek_id=current_user.assigned_trek_id).filter(Booking.status != "cancelled").all() if current_user.assigned_trek_id else []
    return render_template("dashboard.html", assigned_trek=assigned_trek, bookings=bookings)


@staff_bp.route("/staff/trek/<int:trek_id>")
@staff_required
def trek_detail(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if current_user.assigned_trek_id != trek.id:
        flash("You can only view your assigned trek.", "danger")
        return redirect(url_for("staff.dashboard"))
    return render_template("trek_detail.html", trek=trek, bookings=Booking.query.filter_by(trek_id=trek.id).filter(Booking.status != "cancelled").all())


@staff_bp.route("/staff/trek/<int:trek_id>/slots", methods=["POST"])
@staff_required
def update_slots(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if current_user.assigned_trek_id != trek.id:
        flash("You can only manage your assigned trek.", "danger")
        return redirect(url_for("staff.dashboard"))

    slots_raw = request.form.get("available_slots", "").strip()
    try:
        new_slots = int(slots_raw) if slots_raw else trek.available_slots
    except ValueError:
        flash("Available slots must be a whole number.", "danger")
        return redirect(url_for("staff.trek_detail", trek_id=trek.id))

    if new_slots < 0 or new_slots > trek.capacity:
        flash("Available slots must stay between 0 and the trek capacity.", "danger")
        return redirect(url_for("staff.trek_detail", trek_id=trek.id))

    trek.available_slots = new_slots
    db.session.commit()
    flash("Slots updated.", "success")
    return redirect(url_for("staff.trek_detail", trek_id=trek.id))


@staff_bp.route("/staff/trek/<int:trek_id>/status", methods=["POST"])
@staff_required
def update_status(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if current_user.assigned_trek_id != trek.id:
        flash("You can only manage your assigned trek.", "danger")
        return redirect(url_for("staff.dashboard"))

    status = request.form.get("status", trek.status).strip()
    if status not in ALLOWED_STAFF_TREK_STATUSES:
        flash("Status is invalid.", "danger")
        return redirect(url_for("staff.trek_detail", trek_id=trek.id))

    trek.status = status
    db.session.commit()
    flash("Trek status updated.", "success")
    return redirect(url_for("staff.trek_detail", trek_id=trek.id))


@staff_bp.route("/staff/trek/<int:trek_id>/start", methods=["POST"])
@staff_required
def mark_started(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if current_user.assigned_trek_id != trek.id:
        flash("You can only manage your assigned trek.", "danger")
        return redirect(url_for("staff.dashboard"))
    trek.status = "In Progress"
    db.session.commit()
    flash("Trek marked as started.", "success")
    return redirect(url_for("staff.trek_detail", trek_id=trek.id))


@staff_bp.route("/staff/trek/<int:trek_id>/complete", methods=["POST"])
@staff_required
def mark_completed(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if current_user.assigned_trek_id != trek.id:
        flash("You can only manage your assigned trek.", "danger")
        return redirect(url_for("staff.dashboard"))
    trek.status = "Completed"
    db.session.commit()
    flash("Trek marked as completed.", "success")
    return redirect(url_for("staff.trek_detail", trek_id=trek.id))
