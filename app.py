from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import csv, io, os
from dotenv import load_dotenv
import pytz

load_dotenv()
TZ = os.getenv("TZ", "Asia/Tokyo")
JST = pytz.timezone(TZ)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ====== Models ======
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

class Punch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    kind = db.Column(db.String(16), nullable=False)  # 'in','out','break_in','break_out'
    ts = db.Column(db.DateTime, nullable=False, index=True)
    user = db.relationship('User', backref=db.backref('punches', lazy=True))

# ====== Helpers ======
def now_jst():
    return datetime.now(JST)

def to_local(dts):
    if dts.tzinfo is None:
        return JST.localize(dts)
    return dts.astimezone(JST)

def day_range(d):
    start = JST.localize(datetime(d.year, d.month, d.day, 0, 0, 0))
    end = start + timedelta(days=1)
    return start, end

def ensure_user(name: str) -> User:
    name = name.strip()
    u = User.query.filter_by(name=name).first()
    if not u:
        u = User(name=name)
        db.session.add(u)
        db.session.commit()
    return u

def get_break_intervals(punches):
    intervals, current = [], None
    for p in punches:
        if p.kind == 'break_in' and current is None:
            current = p.ts
        elif p.kind == 'break_out' and current is not None:
            intervals.append((current, p.ts))
            current = None
    return intervals

def calc_daily_summary(user: User, d: date):
    """
    不完全な打刻でも落ちない堅牢版。
    ルール：
      - 出勤中かつ休憩でない区間のみ加算
      - 休憩開始でその直前まで加算、休憩終了で再開
      - 出勤前の退勤/休憩終了など矛盾は無視（例外にしない）
      - 日またぎは当日範囲 [start, end) にクランプ
      - 開いたまま（出勤したまま/休憩のまま）なら、日末 or 現在時刻で自然に閉じる
    """
    start, end = day_range(d)  # JST aware
    punches = (Punch.query
               .filter(Punch.user_id == user.id, Punch.ts >= start, Punch.ts < end)
               .order_by(Punch.ts.asc())
               .all())

    # すべてJST awareへ統一 & クランプ
    events = []
    for p in punches:
        ts = to_local(p.ts)
        if ts < start:
            ts = start
        if ts >= end:
            ts = end - timedelta(microseconds=1)
        events.append((ts, p.kind))
    events.sort(key=lambda x: x[0])

    worked = timedelta(0)
    clocked_in = False
    on_break = False
    working_from = None

    for ts, kind in events:
        if kind == 'in':
            if on_break:
                on_break = False
                working_from = ts
                clocked_in = True
            elif clocked_in and working_from:
                if ts > working_from:
                    worked += ts - working_from
                working_from = ts
            else:
                clocked_in = True
                if not on_break:
                    working_from = ts

        elif kind == 'break_in':
            if clocked_in and not on_break:
                if working_from and ts > working_from:
                    worked += ts - working_from
                on_break = True
                working_from = None
            else:
                pass  # 出勤前/既に休憩中は無視

        elif kind == 'break_out':
            if clocked_in and on_break:
                on_break = False
                working_from = ts
            else:
                pass  # 出勤前/休憩してないのにbreak_outは無視

        elif kind == 'out':
            if clocked_in:
                if not on_break and working_from and ts > working_from:
                    worked += ts - working_from
                clocked_in = False
                on_break = False
                working_from = None
            else:
                pass  # 出勤していない退勤は無視

        else:
            pass  # 未知種別は無視

    # 開きっぱなしの実働を日末/現在で締める
    if clocked_in and not on_break and working_from:
        tail_end = min(now_jst(), end)
        if tail_end > working_from:
            worked += tail_end - working_from

    return {
        'date': d.isoformat(),
        'name': user.name,
        'worked_hours': round(worked.total_seconds() / 3600, 2),
        'punches': punches,
    }


# ====== Routes ======
@app.route('/', methods=['GET'])
def index():
    today = now_jst().date()
    start, end = day_range(today)
    punches = (Punch.query.filter(Punch.ts >= start, Punch.ts < end)
               .order_by(Punch.ts.desc()).limit(50).all())
    users = User.query.order_by(User.name.asc()).all()
    return render_template('index.html', punches=punches, users=users, today=today)

@app.route('/punch', methods=['POST'])
def punch():
    name = request.form.get('name', '').strip()
    kind = request.form.get('kind')
    if not name or kind not in {'in','out','break_in','break_out'}:
        flash('名前と打刻種別を確認してください', 'error')
        return redirect(url_for('index'))
    u = ensure_user(name)
    ts = now_jst()
    db.session.add(Punch(user_id=u.id, kind=kind, ts=ts))
    db.session.commit()
    flash(f"{u.name} の {kind} を記録しました ({ts.strftime('%H:%M:%S')})", 'ok')
    return redirect(url_for('index'))

@app.route('/me')
def me():
    name = request.args.get('name', '').strip()
    if not name:
        flash('名前を入力してください', 'error')
        return redirect(url_for('index'))
    u = ensure_user(name)
    days = []
    for i in range(7):
        d = now_jst().date() - timedelta(days=i)
        days.append(calc_daily_summary(u, d))
    return render_template('my.html', user=u, days=days)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        from_date = request.form.get('from')
        to_date = request.form.get('to')
        if not from_date or not to_date:
            flash('期間を指定してください', 'error')
            return redirect(url_for('admin'))
        f = datetime.fromisoformat(from_date).date()
        t = datetime.fromisoformat(to_date).date()
        if f > t:
            f, t = t, f

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['date','name','kind','timestamp'])
        cur = f
        while cur <= t:
            start, end = day_range(cur)
            q = (db.session.query(Punch, User)
                 .join(User, Punch.user_id==User.id)
                 .filter(Punch.ts >= start, Punch.ts < end)
                 .order_by(Punch.ts.asc()))
            for p, u in q.all():
                writer.writerow([cur.isoformat(), u.name, p.kind, to_local(p.ts).strftime('%Y-%m-%d %H:%M:%S')])
            cur += timedelta(days=1)
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        filename = f"attendance_{f.isoformat()}_{t.isoformat()}.csv"
        return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=filename)

    pw = request.args.get('p')
    admin_pw = os.getenv('ADMIN_PASSWORD')
    if admin_pw and pw != admin_pw:
        return "Unauthorized. Add ?p=YOUR_PASSWORD to URL or set ADMIN_PASSWORD in .env", 401

    today = now_jst().date()
    summaries = [calc_daily_summary(u, today) for u in User.query.order_by(User.name.asc()).all()]
    return render_template('admin.html', summaries=summaries, today=today)

# ====== CLI ======
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('DB initialized')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
