import asyncio
import tornado.ioloop
import tornado.web
import sqlite3
import json
import os.path

API_VERIFY_TOKEN = "testtest"
SQLITE_DB_PATH = "/data/binss_api.db"

init_db = True

if os.path.isfile(SQLITE_DB_PATH):
    init_db = False

conn = sqlite3.connect(SQLITE_DB_PATH)
cursor = conn.cursor()

if init_db:
    print("Create table xiaomi_scale")
    cursor.execute("CREATE TABLE xiaomi_scale (id INTEGER PRIMARY KEY, datetime TEXT, weight REAL, impedance REAL, fat_percentage REAL)")
    conn.commit()

    # cursor.execute("INSERT INTO xiaomi_scale VALUES (?, ?, ?, ?, ?)", (None, "2020-09-08 21:39:07", 70.6, 468, 0.001))
    # conn.commit()

    # cursor.execute("SELECT * FROM xiaomi_scale ORDER BY id DESC LIMIT 1")
    # result = cursor.fetchone()
    # print(result)
    # response = json.dumps({'datetime': result[1], 'weight': result[2], 'impedance': result[3], 'fat_percentage': result[4]})
    # print(response)


class XiaomiScaleHandler(tornado.web.RequestHandler):
    def get(self):
        if self.get_argument('token') != API_VERIFY_TOKEN:
            self.write("Fuck off")
            return
        cursor.execute("SELECT * FROM xiaomi_scale ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        response = json.dumps({'datetime': result[1], 'weight': result[2], 'impedance': result[3], 'fat_percentage': result[4]})
        self.write(response)

    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        print("Receive post request", data)
        if data["token"] != API_VERIFY_TOKEN:
            self.write("Fuck off")
            return
        cursor.execute("INSERT INTO xiaomi_scale VALUES (?, ?, ?, ?, ?)", (None, data["datetime"], data["weight"], data["impedance"], data["fat_percentage"]))
        conn.commit()
        self.write("OK")


def make_app():
    return tornado.web.Application([
        (r"/xiaomi_scale", XiaomiScaleHandler),
    ])

if __name__ == "__main__":
    app = make_app()
    app.listen(10086)
    tornado.ioloop.IOLoop.current().start()
