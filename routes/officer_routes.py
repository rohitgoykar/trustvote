import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from database import get_db_connection

officer_bp = Blueprint('officer', __name__)

@officer_bp.route('/officer/login', methods=['GET'])
def officer_login():
    if session.get('officer_logged_in'):
        return redirect(url_for('register.register_page'))
    return render_template('officer_login.html')

@officer_bp.route('/officer/login_api', methods=['POST'])
def officer_login_api():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, location FROM officers WHERE username=? AND password=? AND role='Registration Officer'", (username, password))
        officer = cursor.fetchone()
        if officer:
            session['officer_logged_in'] = True
            session['officer_username'] = username
            session['officer_location'] = officer['location'] if isinstance(officer, sqlite3.Row) else officer[1]
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Invalid credentials or not a Registration Officer'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if 'conn' in locals() and conn:
            conn.close()

@officer_bp.route('/officer/logout')
def officer_logout():
    session.pop('officer_logged_in', None)
    session.pop('officer_username', None)
    session.pop('officer_location', None)
    return redirect(url_for('main.home'))

@officer_bp.route('/booth/login', methods=['GET'])
def booth_login():
    if session.get('booth_logged_in'):
        return redirect(url_for('verify.scan_page'))
    return render_template('booth_login.html')

@officer_bp.route('/booth/login_api', methods=['POST'])
def booth_login_api():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query booth officer along with booth details
        cursor.execute("""
            SELECT o.id, o.username, o.location, o.booth_id,
                   b.booth_code, b.booth_name, b.region
            FROM officers o
            LEFT JOIN booths b ON o.booth_id = b.id
            WHERE o.username=? AND o.password=? AND o.role='Booth Officer'
        """, (username, password))
        
        officer = cursor.fetchone()
        if officer:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            booth_id = officer['booth_id'] if officer['booth_id'] else 1
            booth_code = officer['booth_code'] or f"BOOTH-00{booth_id}"
            booth_name = officer['booth_name'] or f"Booth {booth_id} - {officer['location']}"
            booth_region = officer['region'] or officer['location'] or "Default Region"

            # Mark Polling Booth as ONLINE in Central Database
            cursor.execute("UPDATE booths SET status='ONLINE', last_active=? WHERE id=?", (now_str, booth_id))
            
            # Log Activity
            cursor.execute("""
                INSERT INTO booth_activity_log (booth_id, officer_username, action, details, timestamp)
                VALUES (?, ?, 'LOGIN', 'Officer signed in to polling booth station', ?)
            """, (booth_id, username, now_str))
            
            conn.commit()

            # Store in Session
            session['booth_logged_in'] = True
            session['booth_username']  = username
            session['booth_id']        = booth_id
            session['booth_code']      = booth_code
            session['booth_name']      = booth_name
            session['booth_location']  = booth_region

            return jsonify({
                'status': 'success',
                'booth_code': booth_code,
                'booth_name': booth_name,
                'region': booth_region
            })
        else:
            return jsonify({'status': 'error', 'message': 'Invalid credentials or you do not have Booth Officer access'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if 'conn' in locals() and conn:
            conn.close()

@officer_bp.route('/booth/info')
def booth_info():
    if not session.get('booth_logged_in'):
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    return jsonify({
        'status': 'success',
        'booth_id': session.get('booth_id'),
        'booth_code': session.get('booth_code'),
        'booth_name': session.get('booth_name'),
        'booth_location': session.get('booth_location'),
        'officer_username': session.get('booth_username')
    })

@officer_bp.route('/booth/heartbeat', methods=['POST'])
def booth_heartbeat():
    if not session.get('booth_logged_in'):
        return jsonify({'status': 'error'}), 401
    booth_id = session.get('booth_id')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE booths SET status='ONLINE', last_active=? WHERE id=?", (now_str, booth_id))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'timestamp': now_str})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@officer_bp.route('/booth/logout')
def booth_logout():
    booth_id = session.get('booth_id')
    username = session.get('booth_username')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        if booth_id:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE booths SET status='OFFLINE', last_active=? WHERE id=?", (now_str, booth_id))
            cursor.execute("""
                INSERT INTO booth_activity_log (booth_id, officer_username, action, details, timestamp)
                VALUES (?, ?, 'LOGOUT', 'Officer logged out of booth scanner', ?)
            """, (booth_id, username, now_str))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[BoothLogout] Status update error: {e}")

    session.pop('booth_logged_in', None)
    session.pop('booth_username', None)
    session.pop('booth_id', None)
    session.pop('booth_code', None)
    session.pop('booth_name', None)
    session.pop('booth_location', None)
    return redirect(url_for('main.home'))
