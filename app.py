from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
DB = 'deba.db'


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()

    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS portfolios(
        id INTEGER PRIMARY KEY,
        transaction_type TEXT NOT NULL,
        property_type TEXT NOT NULL,
        project_name TEXT,
        block TEXT,
        apartment_no INTEGER,
        rooms TEXT,
        floor INTEGER,
        sqm REAL NOT NULL,
        facade TEXT,
        price REAL NOT NULL,
        usage_status TEXT,
        province TEXT,
        district TEXT,
        neighborhood TEXT,
        island_no TEXT,
        parcel_no TEXT,
        advisor_id INTEGER NOT NULL,
        description TEXT,
        owner_name TEXT,
        owner_phone TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        removal_reason TEXT,
        removed_at TEXT,
        removed_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(advisor_id) REFERENCES users(id)
    );
    ''')

    # Mevcut veritabanına yeni alanları güvenli şekilde ekle
    columns = [row['name'] for row in c.execute("PRAGMA table_info(portfolios)").fetchall()]

    if 'owner_name' not in columns:
        c.execute("ALTER TABLE portfolios ADD COLUMN owner_name TEXT")

    if 'owner_phone' not in columns:
        c.execute("ALTER TABLE portfolios ADD COLUMN owner_phone TEXT")
    if 'rejection_reason' not in columns:
        c.execute("ALTER TABLE portfolios ADD COLUMN rejection_reason TEXT")

    if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        c.execute(
            'INSERT INTO users(username,password,name,role) VALUES(?,?,?,?)',
            (
                'admin',
                generate_password_hash('Deba2026!'),
                'Deba Admin',
                'admin'
            )
        )

    c.commit()
    c.close()


init_db()


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return w


def current_user():
    if 'uid' not in session:
        return None

    c = db()
    u = c.execute(
        'SELECT * FROM users WHERE id=?',
        (session['uid'],)
    ).fetchone()
    c.close()
    return u


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        c = db()
        u = c.execute(
            'SELECT * FROM users WHERE username=? AND active=1',
            (request.form['username'],)
        ).fetchone()
        c.close()

        if u and check_password_hash(u['password'], request.form['password']):
            session['uid'] = u['id']
            return redirect(url_for('index'))

        flash('Kullanıcı adı veya şifre hatalı.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    c = db()

    counts = {
        r['transaction_type']: r['n']
        for r in c.execute(
            "SELECT transaction_type,count(*) n "
            "FROM portfolios "
            "WHERE status='active' "
            "GROUP BY transaction_type"
        )
    }

    c.close()

    return render_template(
        'index.html',
        u=current_user(),
        counts=counts
    )


@app.route('/portfolios/<tt>')
@login_required
def portfolios(tt):
    if tt not in ('Satılık', 'Kiralık'):
        return redirect(url_for('index'))

    u = current_user()

    q = """
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id = p.advisor_id
        WHERE p.status='active'
        AND p.transaction_type=?
    """
    args = [tt]

    # Standart filtreler
    filters = ['property_type', 'project_name', 'rooms', 'usage_status']

    for f in filters:
        v = request.args.get(f, '').strip()
        if v:
            q += f" AND p.{f}=?"
            args.append(v)

    # Konum filtreleri
    province = request.args.get('province', '').strip()
    district = request.args.get('district', '').strip()
    neighborhood = request.args.get('neighborhood', '').strip()

    if province:
        q += " AND LOWER(p.province) LIKE LOWER(?)"
        args.append('%' + province + '%')

    if district:
        q += " AND LOWER(p.district) LIKE LOWER(?)"
        args.append('%' + district + '%')

    if neighborhood:
        q += " AND LOWER(p.neighborhood) LIKE LOWER(?)"
        args.append('%' + neighborhood + '%')

    # m² filtreleri
    min_sqm = request.args.get('min_sqm', '').strip()
    max_sqm = request.args.get('max_sqm', '').strip()

    if min_sqm:
        q += " AND p.sqm>=?"
        args.append(float(min_sqm))

    if max_sqm:
        q += " AND p.sqm<=?"
        args.append(float(max_sqm))

    # Fiyat filtreleri
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()

    if min_price:
        q += " AND p.price>=?"
        args.append(float(min_price))

    if max_price:
        q += " AND p.price<=?"
        args.append(float(max_price))

    # Sadece admin: portföy sahibi veya telefonla arama
    owner_search = request.args.get('owner_search', '').strip()

    if u['role'] == 'admin' and owner_search:
        q += " AND (LOWER(p.owner_name) LIKE LOWER(?) OR p.owner_phone LIKE ?)"
        args.extend([
            '%' + owner_search + '%',
            '%' + owner_search + '%'
        ])

    q += " ORDER BY p.updated_at DESC"

    c = db()
    rows = c.execute(q, args).fetchall()

    projects = [
        x[0] for x in c.execute("""
            SELECT DISTINCT project_name
            FROM portfolios
            WHERE project_name IS NOT NULL
            AND project_name<>''
            ORDER BY project_name
        """)
    ]

    c.close()

    return render_template(
        'portfolios.html',
        u=u,
        rows=rows,
        tt=tt,
        projects=projects
    )
@app.route('/portfolio/new/<tt>', methods=['GET', 'POST'])
@login_required
def new_portfolio(tt):
    u = current_user()

    if request.method == 'POST':
        return save_portfolio(None, tt, u)

    return render_template(
        'form.html',
        u=u,
        p=None,
        tt=tt
    )


def save_portfolio(pid, tt, u):
    f = request.form
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    # Admin tarafından girilen portföy doğrudan yayınlanır.
    # Danışman tarafından girilen veya düzenlenen portföy admin onayına gider.
    new_status = 'active' if u['role'] == 'admin' else 'pending'
    advisor = (
        int(f.get('advisor_id') or u['id'])
        if u['role'] == 'admin'
        else u['id']
    )

       # Portföy sahibi ve telefon bilgisi portföyü giren kişi tarafından kaydedilir.
    # Bu bilgilerin kimlere gösterileceğini ekran tarafında ayrıca kontrol ediyoruz.
    owner_name = f.get('owner_name', '').strip()
    owner_phone = f.get('owner_phone', '').strip()

    c = db()

    if pid:
        

        vals = [
            tt,
            f['property_type'],
            f.get('project_name'),
            f.get('block'),
            f.get('apartment_no') or None,
            f.get('rooms'),
            f.get('floor') or None,
            f['sqm'],
            f.get('facade'),
            f['price'],
            f.get('usage_status'),
            f.get('province'),
            f.get('district'),
            f.get('neighborhood'),
            f.get('island_no'),
            f.get('parcel_no'),
            advisor,
            f.get('description'),
            owner_name,
            owner_phone,
            new_status,
            now,
            pid
        ]

        c.execute('''
            UPDATE portfolios SET
                transaction_type=?,
                property_type=?,
                project_name=?,
                block=?,
                apartment_no=?,
                rooms=?,
                floor=?,
                sqm=?,
                facade=?,
                price=?,
                usage_status=?,
                province=?,
                district=?,
                neighborhood=?,
                island_no=?,
                parcel_no=?,
                advisor_id=?,
                description=?,
                owner_name=?,
                owner_phone=?,
                status=?,
                updated_at=?
            WHERE id=?
        ''', vals)

    else:
        vals = [
            tt,
            f['property_type'],
            f.get('project_name'),
            f.get('block'),
            f.get('apartment_no') or None,
            f.get('rooms'),
            f.get('floor') or None,
            f['sqm'],
            f.get('facade'),
            f['price'],
            f.get('usage_status'),
            f.get('province'),
            f.get('district'),
            f.get('neighborhood'),
            f.get('island_no'),
            f.get('parcel_no'),
            advisor,
            f.get('description'),
            owner_name,
            owner_phone,
            new_status,
            now,
            now
        ]

        c.execute('''
            INSERT INTO portfolios(
                transaction_type,
                property_type,
                project_name,
                block,
                apartment_no,
                rooms,
                floor,
                sqm,
                facade,
                price,
                usage_status,
                province,
                district,
                neighborhood,
                island_no,
                parcel_no,
                advisor_id,
                description,
                owner_name,
                owner_phone,
                status,               
                created_at,
                updated_at
            )
            VALUES(
                ?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?
            )
        ''', vals)

    c.commit()
    c.close()

    return redirect(url_for('portfolios', tt=tt))


@app.route('/portfolio/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
def edit_portfolio(pid):
    c = db()

    p = c.execute(
        'SELECT * FROM portfolios WHERE id=?',
        (pid,)
    ).fetchone()

    c.close()

    u = current_user()

    if not p:
        return redirect(url_for('index'))

    if u['role'] != 'admin' and p['advisor_id'] != u['id']:
        flash('Bu portföyü değiştirme yetkiniz yok.')
        return redirect(
            url_for(
                'portfolios',
                tt=p['transaction_type']
            )
        )

    if request.method == 'POST':
        return save_portfolio(
            pid,
            p['transaction_type'],
            u
        )

    return render_template(
        'form.html',
        u=u,
        p=p,
        tt=p['transaction_type']
    )


@app.route('/portfolio/<int:pid>/archive', methods=['POST'])
@login_required
def archive(pid):
    c = db()

    p = c.execute(
        'SELECT * FROM portfolios WHERE id=?',
        (pid,)
    ).fetchone()

    u = current_user()

    if p and (
        u['role'] == 'admin'
        or p['advisor_id'] == u['id']
    ):
        now = datetime.now().strftime('%Y-%m-%d %H:%M')

        c.execute(
            """
            UPDATE portfolios
            SET status='archived',
                removal_reason=?,
                removed_at=?,
                removed_by=?,
                updated_at=?
            WHERE id=?
            """,
            (
                request.form['reason'],
                now,
                u['id'],
                now,
                pid
            )
        )

        c.commit()

    c.close()

    return redirect(
        url_for(
            'portfolios',
            tt=p['transaction_type'] if p else 'Satılık'
        )
    )


@app.route('/archive')
@login_required
def archive_list():
    c = db()

    reason = request.args.get('reason', '').strip()

    q = """
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id=p.advisor_id
        WHERE p.status='archived'
    """

    args = []

    if reason:
        q += " AND p.removal_reason=?"
        args.append(reason)

    q += " ORDER BY p.removed_at DESC"

    rows = c.execute(q, args).fetchall()

    c.close()

    return render_template(
        'archive.html',
        u=current_user(),
        rows=rows
    )
@app.route('/portfolio/<int:pid>/reactivate', methods=['POST'])
@login_required
def reactivate_portfolio(pid):
    u = current_user()

    # Sadece admin tekrar aktife alabilir
    if u['role'] != 'admin':
        return redirect(url_for('index'))

    c = db()

    c.execute("""
        UPDATE portfolios
        SET status='active',
            removal_reason=NULL,
            removed_at=NULL,
            removed_by=NULL,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        AND status='archived'
    """, (pid,))

    c.commit()
    c.close()

    return redirect(url_for('archive_list'))
@app.route('/rejected')
@login_required
def rejected_portfolios():
    u = current_user()

    # Bu ekran danışmanların kendi reddedilen portföyleri içindir.
    # Admin bu ekrana girerse ana sayfaya döner.
    if u['role'] == 'admin':
        return redirect(url_for('index'))

    c = db()

    rows = c.execute("""
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id = p.advisor_id
        WHERE p.status='rejected'
        AND p.advisor_id=?
        ORDER BY p.updated_at DESC
    """, (u['id'],)).fetchall()

    c.close()

    return render_template(
        'rejected.html',
        u=u,
        rows=rows
    )
@app.route('/admin/pending')
@login_required
def pending_portfolios():
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    c = db()

    rows = c.execute("""
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id = p.advisor_id
        WHERE p.status='pending'
        ORDER BY p.updated_at DESC
    """).fetchall()

    c.close()

    return render_template(
        'pending.html',
        u=u,
        rows=rows
    )


@app.route('/admin/portfolio/<int:pid>/approve', methods=['POST'])
@login_required
def approve_portfolio(pid):
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    c = db()

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    c.execute("""
        UPDATE portfolios
        SET status='active',
            updated_at=?
        WHERE id=? AND status='pending'
    """, (now, pid))

    c.commit()
    c.close()

    flash('Portföy onaylandı ve yayına alındı.')

    return redirect(url_for('pending_portfolios'))


@app.route('/admin/portfolio/<int:pid>/reject', methods=['POST'])
@login_required
def reject_portfolio(pid):
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    rejection_reason = request.form.get('rejection_reason', '').strip()

    if not rejection_reason:
        flash('Portföyü reddetmek için red sebebi yazmalısınız.')
        return redirect(url_for('pending_portfolios'))

    c = db()

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    c.execute("""
        UPDATE portfolios
        SET status='rejected',
            rejection_reason=?,
            updated_at=?
        WHERE id=? AND status='pending'
    """, (rejection_reason, now, pid))

    c.commit()
    c.close()

    flash('Portföy reddedildi. Red sebebi danışmana iletildi.')

    return redirect(url_for('pending_portfolios'))
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def users():
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    c = db()

    if request.method == 'POST':
        try:
            c.execute(
                '''
                INSERT INTO users(username,password,name,role)
                VALUES(?,?,?,?)
                ''',
                (
                    request.form['username'],
                    generate_password_hash(request.form['password']),
                    request.form['name'],
                    request.form['role']
                )
            )

            c.commit()

        except sqlite3.IntegrityError:
            flash('Bu kullanıcı adı zaten var.')

    rows = c.execute(
        'SELECT * FROM users ORDER BY name'
    ).fetchall()

    c.close()

    return render_template(
        'users.html',
        u=u,
        rows=rows
    )

@app.route('/admin/user/<int:uid>/toggle', methods=['POST'])
@login_required
def toggle_user(uid):
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    c = db()
    target = c.execute(
        'SELECT * FROM users WHERE id=?',
        (uid,)
    ).fetchone()

    if not target:
        c.close()
        return redirect(url_for('users'))

    # Ana admin hesabı pasif yapılamaz
    if target['username'] == 'admin':
        c.close()
        flash('Ana admin hesabı pasif yapılamaz.')
        return redirect(url_for('users'))

    new_status = 0 if target['active'] else 1

    c.execute(
        'UPDATE users SET active=? WHERE id=?',
        (new_status, uid)
    )

    c.commit()
    c.close()

    flash('Kullanıcı durumu güncellendi.')
    return redirect(url_for('users'))


@app.route('/admin/user/<int:uid>/password', methods=['POST'])
@login_required
def reset_password(uid):
    u = current_user()

    if u['role'] != 'admin':
        return redirect(url_for('index'))

    new_password = request.form.get('new_password', '').strip()

    if len(new_password) < 6:
        flash('Yeni şifre en az 6 karakter olmalıdır.')
        return redirect(url_for('users'))

    c = db()
    target = c.execute(
        'SELECT * FROM users WHERE id=?',
        (uid,)
    ).fetchone()

    if not target:
        c.close()
        return redirect(url_for('users'))

    c.execute(
        'UPDATE users SET password=? WHERE id=?',
        (generate_password_hash(new_password), uid)
    )

    c.commit()
    c.close()

    flash('Kullanıcının şifresi değiştirildi.')
    return redirect(url_for('users'))
@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    u = current_user()

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not check_password_hash(u['password'], current_password):
            flash('Mevcut şifreniz yanlış.')
            return redirect(url_for('change_password'))

        if len(new_password) < 6:
            flash('Yeni şifre en az 6 karakter olmalıdır.')
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash('Yeni şifreler birbiriyle aynı değil.')
            return redirect(url_for('change_password'))

        c = db()

        c.execute(
            'UPDATE users SET password=? WHERE id=?',
            (generate_password_hash(new_password), u['id'])
        )

        c.commit()
        c.close()

        flash('Şifreniz başarıyla değiştirildi.')
        return redirect(url_for('index'))

    return render_template(
        'change_password.html',
        u=u
    )
@app.context_processor
def helpers():
    def advisors():
        c = db()

        x = c.execute(
            'SELECT id,name FROM users '
            'WHERE active=1 ORDER BY name'
        ).fetchall()

        c.close()
        return x

    pending_count = 0
    rejected_count = 0

    u = current_user()

    if u:
        c = db()

        if u['role'] == 'admin':
            row = c.execute(
                "SELECT COUNT(*) n FROM portfolios WHERE status='pending'"
            ).fetchone()

            pending_count = row['n']

        else:
            row = c.execute(
                """
                SELECT COUNT(*) n
                FROM portfolios
                WHERE status='rejected'
                AND advisor_id=?
                """,
                (u['id'],)
            ).fetchone()

            rejected_count = row['n']

        c.close()

    return dict(
        advisors=advisors,
        pending_count=pending_count,
        rejected_count=rejected_count
    )


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
