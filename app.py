import os, sqlite3
from datetime import datetime, timedelta
from flask import Flask, g, jsonify, request

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["DB"] = os.environ.get("DB_PATH", "avia.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS countries(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS airports(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, city TEXT NOT NULL,
  country_id INTEGER NOT NULL REFERENCES countries(id));
CREATE TABLE IF NOT EXISTS flights(id INTEGER PRIMARY KEY, number TEXT NOT NULL,
  from_id INTEGER NOT NULL REFERENCES airports(id), to_id INTEGER NOT NULL REFERENCES airports(id),
  depart_at TEXT NOT NULL, arrive_at TEXT NOT NULL, price REAL NOT NULL, seats INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, flight_id INTEGER NOT NULL REFERENCES flights(id),
  passenger TEXT NOT NULL, email TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
AIRPORTS = [("OVB", "Новосибирск", "Россия"), ("SVO", "Москва", "Россия"), ("LED", "Санкт-Петербург", "Россия"),
            ("IST", "Стамбул", "Турция"), ("DXB", "Дубай", "ОАЭ")]
ROUTES = [("OVB", "SVO", 8, 245, 9800), ("SVO", "OVB", 14, 250, 9500), ("SVO", "LED", 9, 90, 3200),
          ("LED", "SVO", 19, 90, 3100), ("SVO", "IST", 11, 195, 15400), ("IST", "SVO", 16, 200, 14900),
          ("SVO", "DXB", 7, 340, 24800), ("DXB", "SVO", 22, 335, 23900)]


def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    c = sqlite3.connect(app.config["DB"])
    c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM airports").fetchone():
        for code, city, country in AIRPORTS:
            c.execute("INSERT OR IGNORE INTO countries(name) VALUES(?)", (country,))
            cid = c.execute("SELECT id FROM countries WHERE name=?", (country,)).fetchone()[0]
            c.execute("INSERT INTO airports(code,city,country_id) VALUES(?,?,?)", (code, city, cid))
        ids = dict(c.execute("SELECT code,id FROM airports").fetchall())
        today = datetime.now().replace(minute=0, second=0, microsecond=0)
        for day in range(30):
            for n, (a, b, hour, mins, price) in enumerate(ROUTES):
                dep = (today + timedelta(days=day)).replace(hour=hour)
                arr = dep + timedelta(minutes=mins)
                c.execute("INSERT INTO flights(number,from_id,to_id,depart_at,arrive_at,price,seats) VALUES(?,?,?,?,?,?,?)",
                          (f"AV{100 + n}", ids[a], ids[b], dep.isoformat(timespec="minutes"),
                           arr.isoformat(timespec="minutes"), price + day % 5 * 300, 20))
        c.commit()
    c.close()


FLIGHT_SQL = """SELECT f.id, f.number, f.depart_at, f.arrive_at, f.price, f.seats,
  a.code AS from_code, a.city AS from_city, b.code AS to_code, b.city AS to_city
  FROM flights f JOIN airports a ON a.id=f.from_id JOIN airports b ON b.id=f.to_id"""


@app.get("/api/airports")
def airports():
    rows = db().execute("""SELECT a.code, a.city, c.name AS country FROM airports a
                           JOIN countries c ON c.id=a.country_id ORDER BY a.city""").fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/flights")
def flights():
    src, dst, day = request.args.get("from"), request.args.get("to"), request.args.get("date")
    sql, args = FLIGHT_SQL + " WHERE f.seats>0", []
    for col, val in (("a.code", src), ("b.code", dst)):
        if val:
            sql += f" AND {col}=?"; args.append(val)
    if day:
        sql += " AND substr(f.depart_at,1,10)=?"; args.append(day)
    rows = db().execute(sql + " ORDER BY f.depart_at LIMIT 50", args).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/tickets")
def buy():
    d = request.get_json(silent=True) or {}
    name, email, fid = (d.get("passenger") or "").strip(), (d.get("email") or "").strip(), d.get("flight_id")
    if not name or "@" not in email or not fid:
        return jsonify(error="Укажите рейс, ФИО и корректный email"), 400
    con = db()
    cur = con.execute("UPDATE flights SET seats=seats-1 WHERE id=? AND seats>0", (fid,))
    if cur.rowcount == 0:
        return jsonify(error="Рейс не найден или мест нет"), 409
    tid = con.execute("INSERT INTO tickets(flight_id,passenger,email) VALUES(?,?,?)", (fid, name, email)).lastrowid
    con.commit()
    return jsonify(id=tid, passenger=name, flight_id=fid), 201


@app.get("/api/tickets/<int:tid>")
def ticket(tid):
    r = db().execute("SELECT t.id, t.passenger, t.email, f.number, f.depart_at FROM tickets t "
                     "JOIN flights f ON f.id=t.flight_id WHERE t.id=?", (tid,)).fetchone()
    return (jsonify(dict(r)), 200) if r else (jsonify(error="Билет не найден"), 404)


@app.get("/")
def index():
    return app.send_static_file("index.html")


init_db()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
