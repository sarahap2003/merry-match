import os, sqlite3, secrets, random, re, hmac
from datetime import datetime
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template, flash, abort, session

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
DB = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'merry.sqlite3'))

def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=5000')
    return c

def init_db():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, admin_token TEXT NOT NULL, title TEXT NOT NULL, budget TEXT, exchange_date TEXT, notes TEXT, drawn INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE, token TEXT NOT NULL, name TEXT NOT NULL, wishes TEXT DEFAULT '', interests TEXT DEFAULT '', size TEXT DEFAULT '', recipient_id TEXT REFERENCES people(id), joined_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS exclusions (event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE, giver_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE, receiver_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE, PRIMARY KEY(event_id,giver_id,receiver_id));''')
init_db()

def get_event(eid):
    with connect() as c: event=c.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
    if event is None: abort(404)
    return event

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(24)
    return session['csrf']
app.jinja_env.globals['csrf_token']=csrf

@app.before_request
def validate_csrf():
    if request.method=='POST' and not hmac.compare_digest(request.form.get('csrf',''),csrf()): abort(400,'Invalid form security token. Refresh and try again.')

@app.after_request
def headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Referrer-Policy']='no-referrer'
    resp.headers['Cache-Control']='no-store'
    resp.headers['X-Frame-Options']='DENY'
    return resp

def check_token(provided, actual):
    return bool(provided) and hmac.compare_digest(str(provided),str(actual))

def person_by_token(eid, token):
    with connect() as c: person=c.execute('SELECT * FROM people WHERE event_id=? AND token=?',(eid,token)).fetchone()
    if not person: abort(403,'This private participant link is invalid.')
    return person

@app.get('/')
def home(): return render_template('home.html')

@app.post('/create')
def create():
    title=request.form.get('title','').strip()[:100]
    if not title: flash('Give your exchange a name.');return redirect(url_for('home'))
    eid=secrets.token_urlsafe(9); admin=secrets.token_urlsafe(32)
    with connect() as c:
        c.execute('INSERT INTO events(id,admin_token,title,budget,exchange_date,notes,created_at) VALUES(?,?,?,?,?,?,?)',(eid,admin,title,request.form.get('budget','').strip()[:40],request.form.get('exchange_date','')[:20],request.form.get('notes','').strip()[:2000],datetime.utcnow().isoformat()))
    return redirect(url_for('admin',eid=eid,token=admin))

@app.get('/e/<eid>')
def join_page(eid):
    event=get_event(eid)
    return render_template('join.html',event=event)

@app.post('/e/<eid>/join')
def join(eid):
    event=get_event(eid)
    if event['drawn']: abort(403,'Names have already been drawn; ask the organizer.')
    name=request.form.get('name','').strip()[:100]
    if not name: flash('Enter your name.');return redirect(url_for('join_page',eid=eid))
    pid=secrets.token_urlsafe(12); token=secrets.token_urlsafe(32)
    with connect() as c:
        c.execute('INSERT INTO people(id,event_id,token,name,joined_at) VALUES(?,?,?,?,?)',(pid,eid,token,name,datetime.utcnow().isoformat()))
    return redirect(url_for('participant',eid=eid,token=token))

@app.route('/e/<eid>/p/<token>',methods=['GET','POST'])
def participant(eid,token):
    event=get_event(eid); person=person_by_token(eid,token)
    if request.method=='POST':
        with connect() as c:
            c.execute('UPDATE people SET wishes=?,interests=?,size=? WHERE id=?',(request.form.get('wishes','').strip()[:4000],request.form.get('interests','').strip()[:1000],request.form.get('size','').strip()[:200],person['id']))
        flash('Wishlist saved!');return redirect(url_for('participant',eid=eid,token=token))
    recipient=None
    if event['drawn'] and person['recipient_id']:
        with connect() as c: recipient=c.execute('SELECT name,wishes,interests,size FROM people WHERE id=? AND event_id=?',(person['recipient_id'],eid)).fetchone()
    return render_template('participant.html',event=event,person=person,recipient=recipient)

def solve(people, forbidden):
    ids=[p['id'] for p in people]; options={g:[r for r in ids if r!=g and (g,r) not in forbidden] for g in ids}
    if any(not v for v in options.values()): return None
    def search(todo, taken, matches):
        if not todo: return dict(matches)
        giver=min(todo,key=lambda g:sum(r not in taken for r in options[g]))
        choices=[r for r in options[giver] if r not in taken]
        random.SystemRandom().shuffle(choices)
        for r in choices:
            result=search([g for g in todo if g!=giver],taken|{r},{**matches,giver:r})
            if result: return result
        return None
    return search(ids,set(),{})

@app.route('/e/<eid>/admin/<token>',methods=['GET','POST'])
def admin(eid,token):
    event=get_event(eid)
    if not check_token(token,event['admin_token']): abort(403,'Invalid organizer link.')
    if request.method=='POST':
        action=request.form.get('action','')
        with connect() as c:
            if action=='settings':
                c.execute('UPDATE events SET title=?,budget=?,exchange_date=?,notes=? WHERE id=?',(request.form.get('title','').strip()[:100] or event['title'],request.form.get('budget','').strip()[:40],request.form.get('exchange_date','')[:20],request.form.get('notes','').strip()[:2000],eid));flash('Settings saved.')
            elif action=='exclude':
                g=request.form.get('giver','');r=request.form.get('receiver','')
                valid={p['id'] for p in c.execute('SELECT id FROM people WHERE event_id=?',(eid,))}
                if g in valid and r in valid and g!=r and not event['drawn']:
                    c.execute('INSERT OR IGNORE INTO exclusions VALUES(?,?,?)',(eid,g,r));flash('Restriction added.')
                else: flash('Could not add that restriction.')
            elif action=='remove_exclusion' and not event['drawn']:
                c.execute('DELETE FROM exclusions WHERE event_id=? AND giver_id=? AND receiver_id=?',(eid,request.form.get('giver',''),request.form.get('receiver','')));flash('Restriction removed.')
            elif action=='draw' and not event['drawn']:
                people=c.execute('SELECT * FROM people WHERE event_id=?',(eid,)).fetchall()
                forbidden={(row['giver_id'],row['receiver_id']) for row in c.execute('SELECT giver_id,receiver_id FROM exclusions WHERE event_id=?',(eid,))}
                if len(people)<3: flash('Add at least 3 participants before drawing.')
                else:
                    matches=solve(people,forbidden)
                    if not matches: flash('No valid draw is possible with these exclusions. Remove a restriction.')
                    else:
                        for g,r in matches.items(): c.execute('UPDATE people SET recipient_id=? WHERE id=? AND event_id=?',(r,g,eid))
                        c.execute('UPDATE events SET drawn=1 WHERE id=?',(eid,));flash('Names drawn! Each participant can now open their own private link.')
            elif action=='reset' and event['drawn'] and request.form.get('confirm')=='RESET':
                c.execute('UPDATE people SET recipient_id=NULL WHERE event_id=?',(eid,));c.execute('UPDATE events SET drawn=0 WHERE id=?',(eid,));flash('Draw reset. Prior assignments are no longer valid.')
        return redirect(url_for('admin',eid=eid,token=token))
    with connect() as c:
        people=c.execute('SELECT id,name,token FROM people WHERE event_id=? ORDER BY joined_at',(eid,)).fetchall()
        restrictions=c.execute('SELECT x.giver_id,x.receiver_id,g.name AS giver_name,r.name AS receiver_name FROM exclusions x JOIN people g ON g.id=x.giver_id JOIN people r ON r.id=x.receiver_id WHERE x.event_id=?',(eid,)).fetchall()
    return render_template('admin.html',event=event,people=people,restrictions=restrictions,token=token)

if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1',port=int(os.environ.get('PORT',8000)))
