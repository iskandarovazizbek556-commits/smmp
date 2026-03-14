import sqlite3
from flask import g

DATABASE = "smm_panel.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def execute(query, params=()):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    db.commit()
    return cursor


def r2d(row):
    if row is None:
        return None
    return dict(row)


def r2l(rows):
    return [dict(row) for row in rows]


def close_db(e=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()