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


def add_missing_columns(c):
    """
    Mevcut veritabanını silmeden yeni alanları ekler.
    """
    existing = {
        row['name']
        for row in c.execute("PRAGMA table_info(portfolios)").fetchall()
    }

    new_columns = {
        'gross_sqm': 'REAL',
        'net_sqm': 'REAL',
        'building_floors': 'INTEGER',
        'building_age': 'INTEGER',
        'owner_name': 'TEXT',
        'owner_phone': 'TEXT'
    }

    for column, column_type in new_columns.items():
        if column not in existing:
            c.execute(
                f'ALTER TABLE portfolios ADD COLUMN {column} {column_type}'
            )


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
        status TEXT NOT NULL DEFAULT 'active',
        removal_reason TEXT,
        removed_at TEXT,
        removed_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        gross_sqm REAL,
        net_sqm REAL,
        building_floors INTEGER,
        building_age INTEGER,
        owner_name TEXT,
        owner_phone TEXT,

        FOREIGN KEY(advisor_id) REFERENCES users(id)
    );
    ''')

    add_missing_columns(c)

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

        if u and check_password_hash(
            u['password'],
            request.form['password']
        ):
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
            """
            SELECT transaction_type, count(*) n
            FROM portfolios
            WHERE status='active'
            GROUP BY transaction_type
            """
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

    q = """
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id=p.advisor_id
        WHERE p.status='active'
        AND p.transaction_type=?
    """

    args = [tt]

    filters = [
        'property_type',
        'project_name',
        'rooms',
        'usage_status'
    ]

    for f in filters:
        v = request.args.get(f, '').strip()

        if v:
            q += f' AND p.{f}=?'
            args.append(v)

    if request.args.get('min_price'):
        q += ' AND price>=?'
        args.append(float(request.args['min_price']))

    if request.args.get('max_price'):
        q += ' AND price<=?'
        args.append(float(request.args['max_price']))

    q += ' ORDER BY updated_at DESC'

    c = db()

    rows = c.execute(q, args).fetchall()

    projects = [
        x[0]
        for x in c.execute(
            """
            SELECT DISTINCT project_name
            FROM portfolios
            WHERE project_name IS NOT NULL
            AND project_name<>''
            ORDER BY project_name
            """
        )
    ]

    c.close()

    return render_template(
        'portfolios.html',
        u=current_user(),
        rows=rows,
        tt=tt,
        projects=projects
    )


@app.route('/portfolio/new/<tt>', methods=['GET', 'POST'])
@login_required
def new_portfolio(tt):
    if tt not in ('Satılık', 'Kiralık'):
        return redirect(url_for('index'))

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

    advisor = (
        int(f.get('advisor_id') or u['id'])
        if u['role'] == 'admin'
        else u['id']
    )

    property_type = f.get('property_type', '').strip()

    # Eski sqm alanıyla uyumluluğu koruyoruz.
    gross_sqm = f.get('gross_sqm') or f.get('sqm') or None
    net_sqm = f.get('net_sqm') or None

    # Arsa için de mevcut sqm yapısının çalışmasını sağlar.
    sqm = gross_sqm or net_sqm

    if not sqm:
        flash('m² bilgisi gereklidir.')
        return redirect(request.url)

    price = f.get('price')

    if not price:
        flash('Fiyat bilgisi gereklidir.')
        return redirect(request.url)

    # Malik bilgileri yalnızca admin tarafından yazılabilir/değiştirilebilir.
    if u['role'] == 'admin':
        owner_name = f.get('owner_name', '').strip() or None
        owner_phone = f.get('owner_phone', '').strip() or None
    else:
        if pid:
            c = db()
            old = c.execute(
                'SELECT owner_name, owner_phone FROM portfolios WHERE id=?',
                (pid,)
            ).fetchone()
            c.close()

            owner_name = old['owner_name'] if old else None
            owner_phone = old['owner_phone'] if old else None
        else:
            owner_name = None
            owner_phone = None

    vals = [
        tt,
        property_type,
        f.get('project_name', '').strip() or None,
        f.get('block', '').strip() or None,
        f.get('apartment_no') or None,
        f.get('rooms') or None,
        f.get('floor') or None,
        float(sqm),
        f.get('facade') or None,
        float(price),
        f.get('usage_status') or None,
        f.get('province', '').strip() or None,
        f.get('district', '').strip() or None,
        f.get('neighborhood', '').strip() or None,
        f.get('island_no', '').strip() or None,
        f.get('parcel_no', '').strip() or None,
        advisor,
        f.get('description', '').strip() or None,
        float(gross_sqm) if gross_sqm else None,
        float(net_sqm) if net_sqm else None,
        int(f.get('building_floors')) if f.get('building_floors') else None,
        int(f.get('building_age')) if f.get('building_age') else None,
        owner_name,
        owner_phone,
        now
    ]

    c = db()

    if pid:
        c.execute(
            '''
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
                gross_sqm=?,
                net_sqm=?,
                building_floors=?,
                building_age=?,
                owner_name=?,
                owner_phone=?,
                updated_at=?
            WHERE id=?
            ''',
            vals + [pid]
        )

    else:
        c.execute(
            '''
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
                gross_sqm,
                net_sqm,
                building_floors,
                building_age,
                owner_name,
                owner_phone,
                created_at,
                updated_at
            )
            VALUES(
                ?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?
            )
            ''',
            vals[:-1] + [now, now]
        )

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

    rows = c.execute(
        """
        SELECT p.*, u.name advisor
        FROM portfolios p
        JOIN users u ON u.id=p.advisor_id
        WHERE p.status='archived'
        ORDER BY removed_at DESC
        """
    ).fetchall()

    c.close()

    return render_template(
        'archive.html',
        u=current_user(),
        rows=rows
    )


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
                INSERT INTO users(
                    username,
                    password,
                    name,
                    role
                )
                VALUES(?,?,?,?)
                ''',
                (
                    request.form['username'],
                    generate_password_hash(
                        request.form['password']
                    ),
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


@app.context_processor
def helpers():
    def advisors():
        c = db()

        x = c.execute(
            '''
            SELECT id, name
            FROM users
            WHERE active=1
            ORDER BY name
            '''
        ).fetchall()

        c.close()
        return x

    return dict(advisors=advisors)


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
